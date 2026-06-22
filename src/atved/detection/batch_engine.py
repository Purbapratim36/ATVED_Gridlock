"""
Batch inference engine for multi-camera GPU processing.

Collects frames from multiple cameras, batches them for GPU inference,
and fans results back out with per-camera tracking. This is the core
throughput multiplier: cross-camera batching keeps the GPU saturated
even when individual cameras produce frames at modest rates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import structlog

from prometheus_client import Gauge, Histogram

from atved.detection import DetectionResult, FrameDetections

if TYPE_CHECKING:
    from atved.detection.detector import Detector
    from atved.detection.tracker import ObjectTracker
    from atved.preprocessing.pipeline import PreprocessingPipeline

logger = structlog.get_logger(__name__)

# ── Prometheus metrics ──────────────────────────────────────────────
BATCH_SIZE_GAUGE = Gauge(
    "atved_batch_size", "Number of frames in the current inference batch"
)
BATCH_PROCESSING_SECONDS = Histogram(
    "atved_batch_processing_seconds",
    "End-to-end batch processing time",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)
PIPELINE_STAGE_SECONDS = Histogram(
    "atved_pipeline_stage_seconds",
    "Time spent in each pipeline stage",
    labelnames=["stage"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
)


@dataclass(frozen=True, slots=True)
class FrameInput:
    """A single frame submitted for inference."""

    camera_id: str
    timestamp: datetime
    frame: np.ndarray  # Raw BGR uint8 HWC


@dataclass
class BatchResult:
    """Results for a complete batch of frames."""

    frame_detections: list[FrameDetections]
    total_time_ms: float
    preprocess_time_ms: float
    inference_time_ms: float
    tracking_time_ms: float
    batch_size: int


class BatchInferenceEngine:
    """
    Orchestrates the full detection pipeline across multi-camera frames.

    Pipeline stages per batch:
        1. Preprocess each frame (quality-adaptive enhancement, resize, normalize)
        2. Stack into a GPU-ready tensor batch
        3. Run YOLOv8 batch inference
        4. Per-camera tracker update (assigns persistent track IDs)
        5. Package into FrameDetections results

    Thread-safety: this class is NOT thread-safe. Each inference worker
    process should own its own BatchInferenceEngine instance.
    """

    def __init__(
        self,
        detector: Detector,
        tracker: ObjectTracker,
        preprocessor: PreprocessingPipeline,
        max_batch_size: int = 16,
    ) -> None:
        self._detector = detector
        self._tracker = tracker
        self._preprocessor = preprocessor
        self._max_batch_size = max_batch_size
        self._frame_counter = 0

        logger.info(
            "batch_engine.initialized",
            max_batch_size=max_batch_size,
        )

    # ── Public API ──────────────────────────────────────────────────

    def warmup(self) -> None:
        """Run a dummy batch through the full pipeline to warm up GPU kernels."""
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self._detector.warmup()
        logger.info("batch_engine.warmup_complete")

    def process_batch(
        self,
        frames: list[FrameInput],
    ) -> BatchResult:
        """
        Process a batch of frames from (potentially) different cameras.

        Parameters
        ----------
        frames:
            Up to ``max_batch_size`` FrameInput items. If more are provided
            the list is silently truncated (caller should chunk).

        Returns
        -------
        BatchResult with per-frame FrameDetections and timing breakdown.
        """
        if not frames:
            return BatchResult([], 0.0, 0.0, 0.0, 0.0, 0)

        batch = frames[: self._max_batch_size]
        batch_size = len(batch)
        BATCH_SIZE_GAUGE.set(batch_size)

        t_total_start = time.perf_counter()

        # ── Stage 1: Preprocess ──────────────────────────────────
        t_pre = time.perf_counter()
        preprocessed_frames: list[np.ndarray] = []
        resize_metas = []

        for item in batch:
            processed, _quality, meta = self._preprocessor.process(item.frame)
            preprocessed_frames.append(processed)
            resize_metas.append(meta)

        preprocess_ms = (time.perf_counter() - t_pre) * 1000
        PIPELINE_STAGE_SECONDS.labels(stage="preprocess").observe(
            preprocess_ms / 1000
        )

        # ── Stage 2: Batch detection ─────────────────────────────
        t_infer = time.perf_counter()
        batch_detections = self._detector.detect_batch(
            preprocessed_frames, resize_metas
        )
        inference_ms = (time.perf_counter() - t_infer) * 1000
        PIPELINE_STAGE_SECONDS.labels(stage="detection").observe(
            inference_ms / 1000
        )

        # ── Stage 3: Per-camera tracking ─────────────────────────
        t_track = time.perf_counter()
        results: list[FrameDetections] = []

        for i, (item, detections) in enumerate(zip(batch, batch_detections)):
            self._frame_counter += 1

            tracked = self._tracker.update(
                camera_id=item.camera_id,
                detections=detections,
            )

            results.append(
                FrameDetections(
                    frame_index=self._frame_counter,
                    camera_id=item.camera_id,
                    timestamp=item.timestamp,
                    detections=tracked,
                    inference_time_ms=inference_ms / batch_size,
                )
            )

        tracking_ms = (time.perf_counter() - t_track) * 1000
        PIPELINE_STAGE_SECONDS.labels(stage="tracking").observe(
            tracking_ms / 1000
        )

        total_ms = (time.perf_counter() - t_total_start) * 1000
        BATCH_PROCESSING_SECONDS.observe(total_ms / 1000)

        logger.debug(
            "batch_engine.processed",
            batch_size=batch_size,
            total_ms=round(total_ms, 2),
            preprocess_ms=round(preprocess_ms, 2),
            inference_ms=round(inference_ms, 2),
            tracking_ms=round(tracking_ms, 2),
            total_detections=sum(len(fd.detections) for fd in results),
        )

        return BatchResult(
            frame_detections=results,
            total_time_ms=total_ms,
            preprocess_time_ms=preprocess_ms,
            inference_time_ms=inference_ms,
            tracking_time_ms=tracking_ms,
            batch_size=batch_size,
        )

    def process_single(
        self,
        camera_id: str,
        timestamp: datetime,
        frame: np.ndarray,
    ) -> FrameDetections:
        """Convenience wrapper for single-frame inference."""
        result = self.process_batch([
            FrameInput(camera_id=camera_id, timestamp=timestamp, frame=frame)
        ])
        return result.frame_detections[0]

    def cleanup_stale_trackers(self, max_age_seconds: float = 60.0) -> int:
        """Remove trackers for cameras that haven't sent frames recently."""
        return self._tracker.cleanup_stale(max_age_seconds)
