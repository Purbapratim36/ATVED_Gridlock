"""
Plate recognition module for ATVED.

Provides end-to-end license-plate extraction: detection → rectification →
super-resolution → OCR → jurisdiction-aware post-correction.
"""

from __future__ import annotations

from atved.plate.detector import PlateDetector, PlateRegion
from atved.plate.rectifier import PlateRectifier
from atved.plate.ocr import PlateOCR, OCRResult
from atved.plate.post_correct import PostCorrector, CorrectedPlate
from atved.plate.super_resolve import SuperResolver
from atved.plate.pipeline import PlateRecognitionPipeline, PlateResult

__all__ = [
    "PlateDetector",
    "PlateRegion",
    "PlateRectifier",
    "PlateOCR",
    "OCRResult",
    "PostCorrector",
    "CorrectedPlate",
    "SuperResolver",
    "PlateRecognitionPipeline",
    "PlateResult",
]
