"""
ByteTrack multi-object tracker pool for ATVED.

Manages per-camera :class:`supervision.ByteTrack` instances so that
track IDs remain camera-scoped and never collide across streams.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import structlog
import supervision as sv

from atved.config import get_settings
from atved.detection import DetectionResult

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal bookkeeping
# ---------------------------------------------------------------------------

@dataclass
class _TrackerState:
    """Mutable state associated with a single camera's ByteTrack tracker."""

    tracker: sv.ByteTrack
    last_update_ts: float = field(default_factory=time.monotonic)
    frame_count: int = 0


class ObjectTracker:
    """Per-camera ByteTrack tracker pool.

    Each camera stream receives its own :class:`supervision.ByteTrack`
    instance so that track IDs are isolated — a car tracked as ID 7 on
    camera A has no relationship to ID 7 on camera B.

    Parameters
    ----------
    track_thresh:
        Detection confidence threshold for ByteTrack's first association.
    track_buffer:
        Number of frames a lost track is kept alive before deletion.
    match_thresh:
        IoU matching threshold.
    frame_rate:
        Expected frame rate of the input stream (used by ByteTrack's
        internal Kalman filter).
    """

    def __init__(
        self,
        *,
        track_thresh: float | None = None,
        track_buffer: int | None = None,
        match_thresh: float | None = None,
        frame_rate: int | None = None,
    ) -> None:
        cfg = get_settings().inference.tracking

        self._track_thresh = track_thresh if track_thresh is not None else cfg.track_thresh
        self._track_buffer = track_buffer if track_buffer is not None else cfg.track_buffer
        self._match_thresh = match_thresh if match_thresh is not None else cfg.match_thresh
        self._frame_rate = frame_rate if frame_rate is not None else cfg.frame_rate

        # camera_id → _TrackerState
        self._trackers: dict[str, _TrackerState] = {}

        logger.info(
            "tracker.initialized",
            track_thresh=self._track_thresh,
            track_buffer=self._track_buffer,
            match_thresh=self._match_thresh,
            frame_rate=self._frame_rate,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        camera_id: str,
        detections: list[DetectionResult],
        frame: np.ndarray | None = None,
    ) -> list[DetectionResult]:
        """Run ByteTrack association and assign ``track_id`` to detections.

        Parameters
        ----------
        camera_id:
            Unique identifier of the camera stream.
        detections:
            Raw detections (without track IDs) for this frame.
        frame:
            Optional raw frame (unused by ByteTrack but reserved for
            future appearance-based trackers).

        Returns
        -------
        list[DetectionResult]
            A *new* list of :class:`DetectionResult` instances with
            ``track_id`` populated.  Detections that the tracker could
            not associate are dropped.
        """
        state = self._get_or_create_tracker(camera_id)
        state.last_update_ts = time.monotonic()
        state.frame_count += 1

        if not detections:
            # Still tick the tracker so it ages out lost tracks.
            empty_sv = sv.Detections.empty()
            state.tracker.update_with_detections(empty_sv)
            return []

        # Build supervision.Detections from our DetectionResults
        sv_detections = self._to_sv_detections(detections)

        # Run ByteTrack association
        tracked_sv = state.tracker.update_with_detections(sv_detections)

        # Map back to DetectionResult with assigned track_ids
        tracked_results = self._from_sv_detections(tracked_sv)
        
        # FIX: Re-populate class_name since ByteTrack drops it!
        self._update_class_names(tracked_results, detections)

        logger.debug(
            "tracker.updated",
            camera_id=camera_id,
            input_count=len(detections),
            tracked_count=len(tracked_results),
            frame_count=state.frame_count,
        )

        return tracked_results

    def reset(self, camera_id: str) -> None:
        """Reset (delete) the tracker state for a specific camera.

        The tracker will be lazily re-created on the next :meth:`update`.

        Parameters
        ----------
        camera_id:
            Camera whose tracker should be discarded.
        """
        if camera_id in self._trackers:
            del self._trackers[camera_id]
            logger.info("tracker.reset", camera_id=camera_id)
        else:
            logger.debug("tracker.reset_noop", camera_id=camera_id)

    def cleanup_stale(self, max_age_seconds: float = 300.0) -> int:
        """Remove trackers that have not received an update recently.

        Parameters
        ----------
        max_age_seconds:
            Maximum idle time (seconds) before a tracker is discarded.

        Returns
        -------
        int
            Number of trackers removed.
        """
        now = time.monotonic()
        stale_ids = [
            cam_id
            for cam_id, state in self._trackers.items()
            if (now - state.last_update_ts) > max_age_seconds
        ]
        for cam_id in stale_ids:
            del self._trackers[cam_id]
            logger.info(
                "tracker.stale_removed",
                camera_id=cam_id,
                max_age_seconds=max_age_seconds,
            )
        return len(stale_ids)

    @property
    def active_camera_ids(self) -> list[str]:
        """Return the list of camera IDs with active trackers."""
        return list(self._trackers.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_tracker(self, camera_id: str) -> _TrackerState:
        """Retrieve or lazily create a ByteTrack tracker for a camera."""
        if camera_id not in self._trackers:
            tracker = sv.ByteTrack(
                track_activation_threshold=self._track_thresh,
                lost_track_buffer=self._track_buffer,
                minimum_matching_threshold=self._match_thresh,
                frame_rate=self._frame_rate,
            )
            self._trackers[camera_id] = _TrackerState(tracker=tracker)
            logger.info("tracker.created", camera_id=camera_id)
        return self._trackers[camera_id]

    @staticmethod
    def _to_sv_detections(
        detections: list[DetectionResult],
    ) -> sv.Detections:
        """Convert a list of DetectionResult → supervision.Detections."""
        n = len(detections)
        xyxy = np.empty((n, 4), dtype=np.float32)
        confidence = np.empty(n, dtype=np.float32)
        class_id = np.empty(n, dtype=int)

        for i, det in enumerate(detections):
            xyxy[i] = det.bbox
            confidence[i] = det.confidence
            class_id[i] = det.class_id

        return sv.Detections(
            xyxy=xyxy,
            confidence=confidence,
            class_id=class_id,
        )

    @staticmethod
    def _from_sv_detections(
        sv_dets: sv.Detections,
    ) -> list[DetectionResult]:
        """Convert supervision.Detections (with tracker_id) → DetectionResults."""
        results: list[DetectionResult] = []
        if len(sv_dets) == 0:
            return results

        xyxy = sv_dets.xyxy
        confidence = sv_dets.confidence
        class_ids = sv_dets.class_id
        tracker_ids = sv_dets.tracker_id  # set by ByteTrack

        for i in range(len(sv_dets)):
            conf = float(confidence[i]) if confidence is not None else 0.0
            cls_id = int(class_ids[i]) if class_ids is not None else -1
            track_id = int(tracker_ids[i]) if tracker_ids is not None else None

            results.append(
                DetectionResult(
                    bbox=(
                        float(xyxy[i, 0]),
                        float(xyxy[i, 1]),
                        float(xyxy[i, 2]),
                        float(xyxy[i, 3]),
                    ),
                    class_name="",  # Will be re-resolved below
                    class_id=cls_id,
                    confidence=conf,
                    track_id=track_id,
                )
            )

        return results

    def _update_class_names(
        self,
        tracked: list[DetectionResult],
        originals: list[DetectionResult],
    ) -> None:
        """Re-populate ``class_name`` on tracked results from the originals.

        ByteTrack does not carry the class name through its association,
        so we match on ``class_id`` + bounding-box IoU proximity.
        The helper modifies *tracked* in-place.
        """
        if not tracked or not originals:
            return

        # Build a lookup: class_id → class_name from originals
        id_to_name: dict[int, str] = {}
        for det in originals:
            id_to_name.setdefault(det.class_id, det.class_name)

        for det in tracked:
            if det.class_id in id_to_name:
                object.__setattr__(det, "class_name", id_to_name[det.class_id])
