"""Image quality assessment for the ATVED preprocessing pipeline.

Computes per-frame quality metrics (brightness, contrast, blur, noise) from
a single grayscale conversion to keep latency well under 1 ms on typical
1080p frames.  The resulting ``QualityReport`` drives downstream enhancement
and denoising decisions.

Metrics
-------
* **Brightness** – mean luminance (0-255).
* **Contrast** – standard deviation of luminance.
* **Blur score** – variance of the Laplacian operator; higher → sharper.
* **Noise estimate** – median absolute deviation (MAD) of the Laplacian,
  scaled by 1.4826 to approximate σ for Gaussian noise.

All thresholds are configurable at construction time so that operators can
tune the pipeline for varying camera hardware and lighting conditions.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class QualityReport:
    """Immutable snapshot of frame quality metrics.

    Attributes
    ----------
    brightness:
        Mean luminance in [0, 255].
    contrast:
        Standard deviation of luminance.
    blur_score:
        Variance of the Laplacian – higher values indicate a sharper image.
    noise_estimate:
        Estimated noise σ via scaled MAD of the Laplacian response.
    is_low_light:
        ``True`` when *brightness* falls below the low-light threshold.
    is_overexposed:
        ``True`` when *brightness* exceeds the overexposure threshold.
    is_blurry:
        ``True`` when *blur_score* falls below the blur threshold.
    needs_enhancement:
        ``True`` when at least one correctable quality issue is detected.
    """

    brightness: float
    contrast: float
    blur_score: float
    noise_estimate: float
    is_low_light: bool
    is_overexposed: bool
    is_blurry: bool
    needs_enhancement: bool


# ---------------------------------------------------------------------------
# Assessor
# ---------------------------------------------------------------------------

class QualityAssessor:
    """Fast, single-pass image quality analyser.

    Parameters
    ----------
    brightness_low:
        Luminance mean below which the frame is classified as low-light.
    brightness_high:
        Luminance mean above which the frame is classified as overexposed.
    blur_threshold:
        Laplacian variance below which the frame is classified as blurry.
    noise_threshold:
        Noise σ estimate above which downstream denoising is recommended.
    """

    def __init__(
        self,
        *,
        brightness_low: float = 60.0,
        brightness_high: float = 200.0,
        blur_threshold: float = 100.0,
        noise_threshold: float = 15.0,
    ) -> None:
        self._brightness_low = brightness_low
        self._brightness_high = brightness_high
        self._blur_threshold = blur_threshold
        self._noise_threshold = noise_threshold

        logger.debug(
            "quality_assessor.init",
            brightness_low=brightness_low,
            brightness_high=brightness_high,
            blur_threshold=blur_threshold,
            noise_threshold=noise_threshold,
        )

    # ----- public API -------------------------------------------------------

    def assess(self, frame: np.ndarray) -> QualityReport:
        """Assess quality of a single BGR uint8 frame.

        The entire analysis is performed on the grayscale conversion of the
        input frame so that only *one* colour-space conversion is needed.

        Parameters
        ----------
        frame:
            Input image in BGR uint8 HWC format (standard OpenCV).

        Returns
        -------
        QualityReport
            Frozen dataclass with all computed metrics and boolean flags.
        """
        # Single grayscale conversion – reused by every metric.
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))

        # Laplacian for simultaneous blur + noise estimation.
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        blur_score = float(np.var(laplacian))

        # Noise σ estimated via the Median Absolute Deviation of the
        # Laplacian response.  The 1.4826 scale factor converts MAD to an
        # estimate of σ under a Gaussian assumption.
        median_lap = float(np.median(np.abs(laplacian)))
        noise_estimate = median_lap * 1.4826

        is_low_light = brightness < self._brightness_low
        is_overexposed = brightness > self._brightness_high
        is_blurry = blur_score < self._blur_threshold

        # Enhancement is warranted for illumination issues (correctable).
        # Blur is *not* flagged here because sharpening is typically
        # counter-productive for detection models.
        needs_enhancement = is_low_light or is_overexposed

        return QualityReport(
            brightness=brightness,
            contrast=contrast,
            blur_score=blur_score,
            noise_estimate=noise_estimate,
            is_low_light=is_low_light,
            is_overexposed=is_overexposed,
            is_blurry=is_blurry,
            needs_enhancement=needs_enhancement,
        )
