"""
End-to-end license plate recognition pipeline.

Orchestrates: vehicle crop → plate detection → super-resolution →
perspective rectification → OCR → post-correction → PlateResult.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import structlog
from prometheus_client import Counter, Histogram

from atved.plate.detector import PlateDetector
from atved.plate.rectifier import PlateRectifier
from atved.plate.ocr import PlateOCR
from atved.plate.post_correct import PostCorrector, CorrectedPlate
from atved.plate.super_resolve import SuperResolver

logger = structlog.get_logger(__name__)

PLATE_ATTEMPTS = Counter("atved_plate_attempts_total", "Total plate recognition attempts")
PLATE_SUCCESS = Counter("atved_plate_success_total", "Successful plate reads")
PLATE_LATENCY = Histogram(
    "atved_plate_pipeline_seconds", "Plate recognition pipeline latency",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
)


@dataclass(frozen=True, slots=True)
class PlateResult:
    """Final output of the plate recognition pipeline."""

    plate_text: str
    corrected_text: str
    confidence: float
    plate_crop: np.ndarray
    bbox_in_frame: tuple[float, float, float, float]
    format_matched: bool
    correction_confidence: float


class PlateRecognitionPipeline:
    """
    Full plate recognition pipeline. Call ``recognize()`` with a frame
    and the vehicle bounding box to get a PlateResult (or None if no
    plate is found/readable).
    """

    def __init__(
        self,
        detector: PlateDetector,
        rectifier: PlateRectifier,
        ocr: PlateOCR,
        corrector: PostCorrector,
        super_resolver: SuperResolver,
        min_confidence: float = 0.4,
        jurisdiction: str = "IN",
    ) -> None:
        self._detector = detector
        self._rectifier = rectifier
        self._ocr = ocr
        self._corrector = corrector
        self._sr = super_resolver
        self._min_confidence = min_confidence
        self._jurisdiction = jurisdiction

    @PLATE_LATENCY.time()
    def recognize(
        self,
        frame: np.ndarray,
        vehicle_bbox: tuple[float, float, float, float],
        jurisdiction: str | None = None,
    ) -> PlateResult | None:
        """
        Run the full plate recognition pipeline on a vehicle region.

        Parameters
        ----------
        frame:
            Full camera frame (BGR, uint8).
        vehicle_bbox:
            Vehicle bounding box (x1, y1, x2, y2) in frame coordinates.
        jurisdiction:
            Override jurisdiction for post-correction.

        Returns
        -------
        PlateResult if a plate was successfully read, None otherwise.
        """
        PLATE_ATTEMPTS.inc()
        jur = jurisdiction or self._jurisdiction

        # 1. Crop vehicle region from frame
        x1, y1, x2, y2 = [int(v) for v in vehicle_bbox]
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return None

        vehicle_crop = frame[y1:y2, x1:x2]

        # 2. Detect plate within vehicle crop
        plates = self._detector.detect(vehicle_crop)
        if not plates:
            return None

        # Take the highest-confidence plate
        best_plate = max(plates, key=lambda p: p.confidence)

        # 3. Super-resolve if plate is too small
        plate_crop = best_plate.crop
        plate_crop = self._sr.upscale(plate_crop)

        # 4. Rectify (perspective correction)
        rectified = self._rectifier.rectify(plate_crop)

        # 5. OCR
        ocr_result = self._ocr.recognize(rectified)
        if not ocr_result.text or ocr_result.confidence < self._min_confidence:
            return None

        # 6. Post-correction
        corrected = self._corrector.correct(ocr_result.text, jur)

        # Compute plate bbox in full frame coordinates
        px1 = x1 + best_plate.bbox[0]
        py1 = y1 + best_plate.bbox[1]
        px2 = x1 + best_plate.bbox[2]
        py2 = y1 + best_plate.bbox[3]

        PLATE_SUCCESS.inc()

        return PlateResult(
            plate_text=ocr_result.text,
            corrected_text=corrected.corrected_text,
            confidence=ocr_result.confidence,
            plate_crop=rectified,
            bbox_in_frame=(px1, py1, px2, py2),
            format_matched=corrected.format_matched,
            correction_confidence=corrected.correction_confidence,
        )
