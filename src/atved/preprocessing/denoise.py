"""Noise reduction for the ATVED preprocessing pipeline.

Wraps ``cv2.fastNlMeansDenoisingColored`` — a non-local-means filter that
averages similar patches across the image.  The algorithm is heavier than a
simple Gaussian blur but preserves edges and textures far better, which is
critical for downstream licence-plate and vehicle detection.

Denoising is *only* triggered when the noise estimate in the upstream
``QualityReport`` exceeds a configurable threshold, so clean frames pass
through with zero overhead.
"""

from __future__ import annotations

import cv2
import numpy as np
import structlog

from atved.preprocessing.quality import QualityReport

logger = structlog.get_logger(__name__)


class Denoiser:
    """Conditionally applies non-local-means denoising.

    Parameters
    ----------
    noise_threshold:
        Minimum ``QualityReport.noise_estimate`` required before denoising
        is applied.  Frames below this threshold are returned unchanged.
    h:
        Filter strength for luminance component.  Higher removes more noise
        but may blur fine detail.
    h_color:
        Filter strength for chrominance components.
    template_window_size:
        Size (in pixels) of the patch used to compute pixel weights.
        Must be odd.
    search_window_size:
        Size (in pixels) of the area searched for similar patches.
        Must be odd.
    """

    def __init__(
        self,
        *,
        noise_threshold: float = 15.0,
        h: float = 10.0,
        h_color: float = 10.0,
        template_window_size: int = 7,
        search_window_size: int = 21,
    ) -> None:
        self._noise_threshold = noise_threshold
        self._h = h
        self._h_color = h_color
        self._template_window_size = template_window_size
        self._search_window_size = search_window_size

        logger.debug(
            "denoiser.init",
            noise_threshold=noise_threshold,
            h=h,
            h_color=h_color,
        )

    # ----- public API -------------------------------------------------------

    def denoise(self, frame: np.ndarray, quality: QualityReport) -> np.ndarray:
        """Denoise *frame* if noise exceeds the configured threshold.

        Parameters
        ----------
        frame:
            BGR uint8 HWC input.
        quality:
            Quality metrics from ``QualityAssessor``.

        Returns
        -------
        np.ndarray
            Denoised (or unchanged) BGR uint8 HWC image.
        """
        if quality.noise_estimate < self._noise_threshold:
            return frame

        logger.debug(
            "denoiser.apply",
            noise_estimate=round(quality.noise_estimate, 2),
            threshold=self._noise_threshold,
        )

        return cv2.fastNlMeansDenoisingColored(
            frame,
            None,
            h=self._h,
            hForColorComponents=self._h_color,
            templateWindowSize=self._template_window_size,
            searchWindowSize=self._search_window_size,
        )
