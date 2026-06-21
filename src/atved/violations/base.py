"""
Base classes and shared types for violation detection.

Every concrete violation detector inherits from :class:`BaseViolationDetector`
and implements the :meth:`analyze` method.  Candidates produced by detectors
are represented as :class:`ViolationCandidate` dataclasses.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from atved.config import ViolationModuleConfig
from atved.db.models import ViolationType
from atved.detection import DetectionResult, FrameDetections

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Violation candidate
# ---------------------------------------------------------------------------

@dataclass
class ViolationCandidate:
    """Intermediate representation of a potential violation.

    Produced by a detector's :meth:`analyze` call and refined by the
    :class:`~atved.violations.classifier.UnifiedClassifier` before being
    persisted or discarded.

    Attributes
    ----------
    violation_type:
        Category of the violation.
    raw_confidence:
        Detector-assigned confidence before calibration.
    calibrated_confidence:
        Calibrated confidence set by the unified classifier (initially 0.0).
    detections:
        Contributing object detections from one or more frames.
    evidence_signals:
        Module-specific key/value evidence (e.g. rider count, signal state).
    frame_indices:
        Frame indices that contributed to the candidate.
    camera_id:
        Source camera identifier.
    timestamp:
        Earliest timestamp among evidence frames.
    trajectory:
        Optional ordered list of ``(x, y)`` positions for trajectory-based
        violations (wrong-side, stop-line, etc.).
    priority:
        Triage priority assigned by the classifier (lower = higher urgency).
    """

    violation_type: ViolationType
    raw_confidence: float
    calibrated_confidence: float = 0.0
    detections: list[DetectionResult] = field(default_factory=list)
    evidence_signals: dict[str, Any] = field(default_factory=dict)
    frame_indices: list[int] = field(default_factory=list)
    camera_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    trajectory: list[tuple[float, float]] | None = None
    priority: int = 99


# ---------------------------------------------------------------------------
# Abstract base detector
# ---------------------------------------------------------------------------

class BaseViolationDetector(abc.ABC):
    """Abstract base for all violation detection modules.

    Parameters
    ----------
    config:
        Per-module configuration (thresholds, enable flags, etc.).
    violation_type:
        The :class:`ViolationType` this detector is responsible for.
    """

    def __init__(
        self,
        config: ViolationModuleConfig,
        violation_type: ViolationType,
    ) -> None:
        self._config = config
        self._violation_type = violation_type
        self._log = structlog.get_logger(
            __name__,
            module=self.__class__.__name__,
            violation_type=violation_type.value,
        )

    # -- Public API ---------------------------------------------------------

    @abc.abstractmethod
    def analyze(
        self,
        frame_detections: FrameDetections,
        history: list[FrameDetections],
    ) -> list[ViolationCandidate]:
        """Analyze a frame (plus recent history) for violations.

        Parameters
        ----------
        frame_detections:
            Detections for the current frame.
        history:
            Ordered list of prior :class:`FrameDetections` (oldest first).

        Returns
        -------
        list[ViolationCandidate]
            Zero or more candidate violations found in the current frame.
        """

    @property
    def is_enabled(self) -> bool:
        """Whether this detector is active per configuration."""
        return self._config.enabled

    @property
    def violation_type(self) -> ViolationType:
        """The violation type handled by this detector."""
        return self._violation_type

    @property
    def config(self) -> ViolationModuleConfig:
        """Read-only access to the module configuration."""
        return self._config

    # -- Helpers for subclasses ---------------------------------------------

    def _filter_by_confidence(
        self,
        detections: list[DetectionResult],
    ) -> list[DetectionResult]:
        """Return only detections meeting the minimum confidence threshold."""
        return [d for d in detections if d.confidence >= self._config.min_confidence]

    def _filter_by_class(
        self,
        detections: list[DetectionResult],
        class_names: set[str],
    ) -> list[DetectionResult]:
        """Return detections whose class_name is in *class_names*."""
        return [d for d in detections if d.class_name in class_names]


__all__ = ["BaseViolationDetector", "ViolationCandidate"]
