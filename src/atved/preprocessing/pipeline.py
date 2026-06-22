"""Preprocessing pipeline orchestrator for the ATVED system.

Chains the individual processing stages in the correct order:

1. **Quality assessment** – compute brightness, contrast, blur, and noise
   metrics to drive conditional processing.
2. **Illumination enhancement** – CLAHE and/or adaptive gamma correction
   when the frame is too dark or overexposed.
3. **Denoising** – non-local-means denoising when noise exceeds threshold.
4. **Normalisation** – letterbox resize + pad → BGR-to-RGB → CHW float32.

Prometheus metrics are registered at module level so the histogram and
counters survive pipeline re-instantiation without ``ValueError`` on
duplicate registration.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import structlog
from prometheus_client import Counter, Histogram

from atved.preprocessing.denoise import Denoiser
from atved.preprocessing.enhance import IlluminationEnhancer
from atved.preprocessing.normalize import FrameNormalizer, ResizeMetadata
from atved.preprocessing.quality import QualityAssessor, QualityReport

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics (module-level singletons)
# ---------------------------------------------------------------------------

PREPROCESSING_DURATION = Histogram(
    "preprocessing_duration_seconds",
    "Time spent in the full preprocessing pipeline per frame.",
    buckets=(0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
)

FRAMES_ENHANCED = Counter(
    "frames_enhanced_total",
    "Total number of frames that received illumination enhancement.",
)

FRAMES_DENOISED = Counter(
    "frames_denoised_total",
    "Total number of frames that received denoising.",
)


# ---------------------------------------------------------------------------
# Pipeline configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Centralised configuration for the preprocessing pipeline.

    All fields carry sensible defaults so the pipeline works out of the box
    for typical traffic-camera footage.
    """

    # Quality thresholds
    brightness_low: float = 60.0
    brightness_high: float = 200.0
    blur_threshold: float = 100.0
    noise_threshold: float = 15.0

    # Enhancement
    target_brightness: float = 120.0

    # Denoiser
    denoise_h: float = 10.0
    denoise_h_color: float = 10.0
    denoise_template_window: int = 7
    denoise_search_window: int = 21

    # Normaliser
    target_size: tuple[int, int] = (640, 640)
    pad_color: tuple[int, int, int] = (114, 114, 114)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class PreprocessingPipeline:
    """End-to-end preprocessing orchestrator.

    Parameters
    ----------
    config:
        A ``PipelineConfig`` instance.  When ``None`` the default
        configuration is used.

    Example
    -------
    >>> import cv2
    >>> from atved.preprocessing.pipeline import PreprocessingPipeline
    >>> pipe = PreprocessingPipeline()
    >>> frame = cv2.imread("traffic.jpg")
    >>> tensor, quality, meta = pipe.process(frame)
    """

    def __init__(self, config: PipelineConfig | None = None) -> None:
        cfg = config or PipelineConfig()

        self._assessor = QualityAssessor(
            brightness_low=cfg.brightness_low,
            brightness_high=cfg.brightness_high,
            blur_threshold=cfg.blur_threshold,
            noise_threshold=cfg.noise_threshold,
        )
        self._enhancer = IlluminationEnhancer(
            target_brightness=cfg.target_brightness,
        )
        self._denoiser = Denoiser(
            noise_threshold=cfg.noise_threshold,
            h=cfg.denoise_h,
            h_color=cfg.denoise_h_color,
            template_window_size=cfg.denoise_template_window,
            search_window_size=cfg.denoise_search_window,
        )
        self._normalizer = FrameNormalizer(
            target_size=cfg.target_size,
            pad_color=cfg.pad_color,
        )

        logger.info("preprocessing_pipeline.init", config=cfg)

    # ----- Single frame ----------------------------------------------------

    def process(
        self,
        frame: np.ndarray,
    ) -> tuple[np.ndarray, QualityReport, ResizeMetadata]:
        """Run the full preprocessing pipeline on a single frame.

        Parameters
        ----------
        frame:
            BGR uint8 HWC image captured from a traffic camera.

        Returns
        -------
        processed:
            Float32 CHW array normalised to [0, 1] and sized for the
            detection model.
        quality:
            ``QualityReport`` describing the *original* frame's quality.
        metadata:
            ``ResizeMetadata`` needed to remap detections back to the
            original coordinate system.
        """
        start = time.perf_counter()

        # 1. Assess quality on the raw frame.
        quality = self._assessor.assess(frame)

        # 2. Conditional illumination enhancement.
        current = frame
        if quality.needs_enhancement:
            current = self._enhancer.enhance(current, quality)
            FRAMES_ENHANCED.inc()

        # 3. Conditional denoising.
        pre_denoise = current
        current = self._denoiser.denoise(current, quality)
        if current is not pre_denoise:
            FRAMES_DENOISED.inc()

        # 4. Resize + pad → normalise to CHW float32.
        resized, metadata = self._normalizer.resize_with_pad(current)
        processed = self._normalizer.normalize(resized)

        elapsed = time.perf_counter() - start
        PREPROCESSING_DURATION.observe(elapsed)

        logger.debug(
            "preprocessing_pipeline.process",
            elapsed_ms=round(elapsed * 1000, 2),
            enhanced=quality.needs_enhancement,
            denoised=current is not pre_denoise,
            brightness=round(quality.brightness, 1),
        )

        return processed, quality, metadata

    # ----- Batch -----------------------------------------------------------

    def process_batch(
        self,
        frames: list[np.ndarray],
    ) -> tuple[np.ndarray, list[QualityReport], list[ResizeMetadata]]:
        """Process multiple frames and stack the results into a batch tensor.

        Each frame is processed independently (quality assessment and
        conditional enhancement are per-frame decisions).

        Parameters
        ----------
        frames:
            List of BGR uint8 HWC images.

        Returns
        -------
        batch:
            Float32 NCHW array of shape ``(N, 3, H, W)``.
        quality_reports:
            One ``QualityReport`` per input frame.
        resize_metadata:
            One ``ResizeMetadata`` per input frame.
        """
        processed_frames: list[np.ndarray] = []
        quality_reports: list[QualityReport] = []
        resize_metadata: list[ResizeMetadata] = []

        for frame in frames:
            tensor, quality, meta = self.process(frame)
            processed_frames.append(tensor)
            quality_reports.append(quality)
            resize_metadata.append(meta)

        batch = self._normalizer.to_tensor_batch(processed_frames)
        return batch, quality_reports, resize_metadata
