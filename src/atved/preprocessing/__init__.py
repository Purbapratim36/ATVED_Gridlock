"""ATVED preprocessing pipeline — image quality, enhancement, and normalisation.

Public API
----------
.. autosummary::

    PreprocessingPipeline
    PipelineConfig
    QualityAssessor
    QualityReport
    IlluminationEnhancer
    Denoiser
    FrameNormalizer
    ResizeMetadata
"""

from __future__ import annotations

from atved.preprocessing.denoise import Denoiser
from atved.preprocessing.enhance import IlluminationEnhancer
from atved.preprocessing.normalize import FrameNormalizer, ResizeMetadata
from atved.preprocessing.pipeline import PipelineConfig, PreprocessingPipeline
from atved.preprocessing.quality import QualityAssessor, QualityReport

__all__ = [
    "Denoiser",
    "FrameNormalizer",
    "IlluminationEnhancer",
    "PipelineConfig",
    "PreprocessingPipeline",
    "QualityAssessor",
    "QualityReport",
    "ResizeMetadata",
]
