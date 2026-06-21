"""
PaddleOCR wrapper for license-plate text recognition.

Handles GPU/CPU fallback and consolidates multi-line OCR output into a
single plate string.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import structlog

from atved.config import PlateOCRConfig

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True, slots=True)
class OCRResult:
    """Result of OCR on a single plate image."""

    text: str
    """Concatenated recognised text (whitespace stripped, upper-cased)."""

    confidence: float
    """Average character-level confidence in [0, 1]."""

    char_confidences: list[float]
    """Per-character confidence scores (empty if unavailable)."""


# ---------------------------------------------------------------------------
# OCR engine
# ---------------------------------------------------------------------------

class PlateOCR:
    """Thin wrapper around PaddleOCR tuned for plate recognition.

    Parameters
    ----------
    config:
        ``PlateOCRConfig`` with *lang* and *use_gpu* flags.
    """

    def __init__(self, config: PlateOCRConfig) -> None:
        self._config = config
        self._engine = self._init_engine(config)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    @staticmethod
    def _init_engine(config: PlateOCRConfig):  # noqa: ANN205
        """Initialise PaddleOCR with GPU/CPU fallback."""
        from paddleocr import PaddleOCR as _PaddleOCR  # type: ignore[import-untyped]

        try:
            engine = _PaddleOCR(
                use_angle_cls=True,
                lang=config.lang,
                use_gpu=config.use_gpu,
                show_log=False,
            )
            log.info("plate_ocr.init", gpu=config.use_gpu, lang=config.lang)
            return engine
        except Exception:
            if config.use_gpu:
                log.warning("plate_ocr.gpu_fallback", reason="GPU init failed, using CPU")
                engine = _PaddleOCR(
                    use_angle_cls=True,
                    lang=config.lang,
                    use_gpu=False,
                    show_log=False,
                )
                return engine
            raise

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recognize(self, plate_image: np.ndarray) -> OCRResult:
        """Run OCR on *plate_image* and return consolidated text.

        Parameters
        ----------
        plate_image:
            Pre-processed plate crop (BGR, uint8).

        Returns
        -------
        OCRResult
            Recognised text with confidence scores.
        """
        results = self._engine.ocr(plate_image, cls=True)

        if not results or not results[0]:
            log.debug("plate_ocr.empty_result")
            return OCRResult(text="", confidence=0.0, char_confidences=[])

        # PaddleOCR returns list of lists:
        #   [ [ [bbox, (text, conf)], ... ] ]
        # Flatten across all detected text lines.
        texts: list[str] = []
        confidences: list[float] = []

        for line in results[0]:
            # line = [bbox_points, (text, confidence)]
            if line is None or len(line) < 2:
                continue
            text_conf = line[1]
            if isinstance(text_conf, (list, tuple)) and len(text_conf) >= 2:
                text_str, conf = str(text_conf[0]), float(text_conf[1])
            else:
                continue

            texts.append(text_str)
            confidences.append(conf)

        if not texts:
            return OCRResult(text="", confidence=0.0, char_confidences=[])

        combined_text = "".join(texts).upper().strip()
        # Remove spaces — plate numbers are contiguous.
        combined_text = combined_text.replace(" ", "")

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        log.debug(
            "plate_ocr.recognized",
            text=combined_text,
            confidence=round(avg_confidence, 4),
            lines=len(texts),
        )

        return OCRResult(
            text=combined_text,
            confidence=avg_confidence,
            char_confidences=confidences,
        )
