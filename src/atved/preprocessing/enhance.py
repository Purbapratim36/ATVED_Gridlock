"""Illumination enhancement for the ATVED preprocessing pipeline.

Provides two complementary techniques:

* **CLAHE** (Contrast Limited Adaptive Histogram Equalisation) applied to the
  L channel in CIE-LAB colour space.  This boosts local contrast without
  amplifying colour noise — ideal for low-light traffic camera footage.

* **Adaptive gamma correction** that maps the frame's mean luminance toward a
  configurable target (default 120).  Over-exposed frames receive γ > 1
  (darkens), under-exposed frames receive γ < 1 (brightens).

The ``enhance`` method orchestrates both techniques based on the quality
flags computed by ``QualityAssessor``.
"""

from __future__ import annotations

import cv2
import numpy as np
import structlog

from atved.preprocessing.quality import QualityReport

logger = structlog.get_logger(__name__)


class IlluminationEnhancer:
    """Applies illumination corrections driven by quality metrics.

    Parameters
    ----------
    target_brightness:
        The mean luminance that adaptive gamma correction aims for.
    """

    def __init__(self, *, target_brightness: float = 120.0) -> None:
        self._target_brightness = target_brightness

    # ----- CLAHE -----------------------------------------------------------

    def apply_clahe(
        self,
        frame: np.ndarray,
        clip_limit: float = 2.0,
        grid_size: tuple[int, int] = (8, 8),
    ) -> np.ndarray:
        """Enhance local contrast via CLAHE on the luminance channel.

        The frame is converted to CIE-LAB, CLAHE is applied to the L
        channel only, and the result is converted back to BGR.  This avoids
        the colour shifts that direct histogram equalisation would cause.

        Parameters
        ----------
        frame:
            BGR uint8 HWC input.
        clip_limit:
            CLAHE clip limit — higher values allow more contrast enhancement
            but risk amplifying noise.
        grid_size:
            Size of the contextual tiling grid (rows, cols).

        Returns
        -------
        np.ndarray
            Enhanced BGR uint8 HWC image.
        """
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=grid_size)
        l_enhanced = clahe.apply(l_channel)

        lab_enhanced = cv2.merge([l_enhanced, a_channel, b_channel])
        return cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

    # ----- Gamma correction ------------------------------------------------

    def apply_gamma(
        self,
        frame: np.ndarray,
        gamma: float | None = None,
    ) -> np.ndarray:
        """Apply gamma correction, optionally computing an adaptive value.

        When *gamma* is ``None`` the method estimates an appropriate value
        from the frame's mean luminance so that the result sits near
        ``target_brightness``.

        The mapping is::

            pixel_out = 255 * (pixel_in / 255) ** gamma

        * γ < 1 → brightens the image  (low-light scenes)
        * γ > 1 → darkens the image    (over-exposed scenes)

        Parameters
        ----------
        frame:
            BGR uint8 HWC input.
        gamma:
            Explicit gamma value.  If ``None``, an adaptive gamma is
            computed from mean luminance.

        Returns
        -------
        np.ndarray
            Gamma-corrected BGR uint8 HWC image.
        """
        if gamma is None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_luminance = float(np.mean(gray))
            # Avoid division by zero / log domain errors for nearly-black
            # frames.  Clamp mean to [1, 254].
            mean_luminance = max(1.0, min(mean_luminance, 254.0))
            # Solve  (mean/255)^γ = target/255  →  γ = log(target/255) / log(mean/255)
            gamma = float(
                np.log(self._target_brightness / 255.0)
                / np.log(mean_luminance / 255.0)
            )
            logger.debug(
                "enhance.adaptive_gamma",
                mean_luminance=round(mean_luminance, 2),
                computed_gamma=round(gamma, 4),
            )

        # Build a uint8 look-up table for the power-law transform.
        inv_gamma = 1.0 / gamma
        table = np.array(
            [((i / 255.0) ** inv_gamma) * 255.0 for i in range(256)],
            dtype=np.uint8,
        )
        return cv2.LUT(frame, table)

    # ----- Orchestrator ----------------------------------------------------

    def enhance(self, frame: np.ndarray, quality: QualityReport) -> np.ndarray:
        """Conditionally enhance a frame based on its quality report.

        * **Low-light** → CLAHE (boosts local contrast without colour shift).
        * **Over-exposed / under-exposed** → adaptive gamma correction.
        * **Good quality** → frame is returned unchanged.

        Parameters
        ----------
        frame:
            BGR uint8 HWC input.
        quality:
            The ``QualityReport`` produced by ``QualityAssessor.assess``.

        Returns
        -------
        np.ndarray
            Enhanced (or unchanged) BGR uint8 HWC image.
        """
        if not quality.needs_enhancement:
            return frame

        result = frame

        if quality.is_low_light:
            logger.debug("enhance.clahe", brightness=quality.brightness)
            result = self.apply_clahe(result)

        if quality.is_overexposed or quality.is_low_light:
            logger.debug(
                "enhance.gamma",
                brightness=quality.brightness,
                is_overexposed=quality.is_overexposed,
                is_low_light=quality.is_low_light,
            )
            result = self.apply_gamma(result)

        return result
