"""
License-plate localisation using YOLOv8.

Detects one or more plates within a frame and returns cropped regions with
confidence scores.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import structlog

from atved.config import PlateDetectorConfig

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True, slots=True)
class PlateRegion:
    """A single detected license-plate region."""

    bbox: tuple[int, int, int, int]
    """(x1, y1, x2, y2) in the input frame's coordinate space."""

    confidence: float
    """Detection confidence in [0, 1]."""

    crop: np.ndarray
    """Cropped plate image extracted from the source frame."""


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class PlateDetector:
    """YOLOv8-based license-plate detector.

    Parameters
    ----------
    config:
        ``PlateDetectorConfig`` carrying *weights_path* and
        *confidence_threshold*.
    """

    def __init__(self, config: PlateDetectorConfig) -> None:
        self._config = config
        self._model = self._load_model(config.weights_path)
        log.info(
            "plate_detector.loaded",
            weights=config.weights_path,
            confidence_threshold=config.confidence_threshold,
        )

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_model(weights_path: str):  # noqa: ANN205
        """Import ultralytics lazily and load the YOLO weights."""
        from ultralytics import YOLO  # type: ignore[import-untyped]

        path = Path(weights_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Plate-detection weights not found at {path.resolve()}"
            )
        return YOLO(str(path))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> list[PlateRegion]:
        """Run inference on *frame* and return all detected plate regions.

        Parameters
        ----------
        frame:
            BGR image as a NumPy array (H × W × 3).

        Returns
        -------
        list[PlateRegion]
            Zero or more detected plates sorted by descending confidence.
        """
        results = self._model(
            frame,
            conf=self._config.confidence_threshold,
            verbose=False,
        )

        regions: list[PlateRegion] = []

        for result in results:
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue

            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf: float = float(box.conf[0])

                # Clamp to frame boundaries.
                h, w = frame.shape[:2]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                if x2 <= x1 or y2 <= y1:
                    continue

                crop = frame[y1:y2, x1:x2].copy()
                regions.append(PlateRegion(bbox=(x1, y1, x2, y2), confidence=conf, crop=crop))

        # Highest confidence first.
        regions.sort(key=lambda r: r.confidence, reverse=True)

        log.debug("plate_detector.detect", plates_found=len(regions))
        return regions
