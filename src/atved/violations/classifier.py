"""
Unified violation classifier with temperature-scaled confidence calibration.

Neural network softmax outputs are systematically overconfident. Temperature
scaling (Guo et al., 2017) applies a learned scalar T to logits before
softmax, reducing Expected Calibration Error (ECE) by 50-70%. We fit T on a
held-out validation set using NLL minimization.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog

from atved.violations.base import ViolationCandidate

logger = structlog.get_logger(__name__)


@dataclass
class TriageResult:
    """Categorisation of a violation candidate by confidence level."""

    candidate: ViolationCandidate
    priority: str  # "high", "standard", "low"


class UnifiedClassifier:
    """
    Applies post-hoc temperature scaling to raw violation confidences and
    assigns review priority based on calibrated scores.

    Temperature scaling works as follows:
        calibrated = sigmoid(logit(raw_confidence) / T)

    where ``T`` is a single scalar learned from validation data. Higher T
    spreads out the confidence distribution (reduces overconfidence).

    Parameters
    ----------
    temperature:
        The calibration temperature. Default 1.5 (a reasonable starting
        point; should be fit on your validation data via ``calibrate()``).
    auto_queue_threshold:
        Calibrated confidence above which the violation is high-priority.
    standard_threshold:
        Above this threshold → standard priority.
    low_priority_threshold:
        Above this → low priority. Below → discard.
    discard_threshold:
        Below this calibrated confidence the candidate is dropped entirely.
    """

    def __init__(
        self,
        temperature: float = 1.5,
        auto_queue_threshold: float = 0.95,
        standard_threshold: float = 0.80,
        low_priority_threshold: float = 0.60,
        discard_threshold: float = 0.60,
    ) -> None:
        self._temperature = temperature
        self._auto_queue = auto_queue_threshold
        self._standard = standard_threshold
        self._low_priority = low_priority_threshold
        self._discard = discard_threshold

    @property
    def temperature(self) -> float:
        return self._temperature

    def classify(
        self, candidates: list[ViolationCandidate]
    ) -> list[TriageResult]:
        """
        Calibrate confidences and assign triage priority.

        Candidates below the discard threshold are dropped. Remaining
        candidates are returned sorted by calibrated confidence (desc).
        """
        results: list[TriageResult] = []

        for candidate in candidates:
            calibrated = self._calibrate_score(candidate.raw_confidence)
            candidate.calibrated_confidence = calibrated

            if calibrated < self._discard:
                logger.debug(
                    "classifier.discarded",
                    type=candidate.violation_type.value,
                    raw=round(candidate.raw_confidence, 3),
                    calibrated=round(calibrated, 3),
                )
                continue

            priority = self._assign_priority(calibrated)
            results.append(TriageResult(candidate=candidate, priority=priority))

        results.sort(key=lambda r: r.candidate.calibrated_confidence, reverse=True)
        return results

    def calibrate_batch(
        self, candidates: list[ViolationCandidate]
    ) -> list[ViolationCandidate]:
        """Apply calibration to a batch, returning only non-discarded candidates."""
        triaged = self.classify(candidates)
        return [t.candidate for t in triaged]

    def _calibrate_score(self, raw_confidence: float) -> float:
        """Apply temperature scaling: sigmoid(logit(p) / T)."""
        # Clamp to avoid log(0) or log(inf)
        p = max(1e-7, min(1 - 1e-7, raw_confidence))
        logit = math.log(p / (1 - p))
        scaled_logit = logit / self._temperature
        return 1.0 / (1.0 + math.exp(-scaled_logit))

    def _assign_priority(self, calibrated: float) -> str:
        if calibrated >= self._auto_queue:
            return "high"
        if calibrated >= self._standard:
            return "standard"
        return "low"

    # ── Calibration fitting ─────────────────────────────────────────

    def calibrate(
        self,
        raw_scores: np.ndarray,
        labels: np.ndarray,
    ) -> float:
        """
        Fit the temperature parameter T on a validation set.

        Uses grid search over T ∈ [0.1, 10.0] to minimise negative
        log-likelihood (NLL). This is simple, robust, and sufficient
        for a single-parameter model.

        Parameters
        ----------
        raw_scores:
            Model's raw confidence scores (N,).
        labels:
            Binary ground truth (1 = true violation, 0 = false positive).

        Returns
        -------
        Optimal temperature T.
        """
        best_t = 1.0
        best_nll = float("inf")

        for t_candidate in np.arange(0.1, 10.05, 0.05):
            nll = self._compute_nll(raw_scores, labels, t_candidate)
            if nll < best_nll:
                best_nll = nll
                best_t = float(t_candidate)

        self._temperature = best_t
        logger.info(
            "classifier.calibrated",
            optimal_temperature=round(best_t, 3),
            nll=round(best_nll, 4),
            n_samples=len(labels),
        )
        return best_t

    @staticmethod
    def _compute_nll(
        raw_scores: np.ndarray,
        labels: np.ndarray,
        temperature: float,
    ) -> float:
        """Compute negative log-likelihood for a given temperature."""
        eps = 1e-7
        p = np.clip(raw_scores, eps, 1 - eps)
        logits = np.log(p / (1 - p))
        scaled = logits / temperature
        calibrated = 1.0 / (1.0 + np.exp(-scaled))
        calibrated = np.clip(calibrated, eps, 1 - eps)

        nll = -np.mean(
            labels * np.log(calibrated) + (1 - labels) * np.log(1 - calibrated)
        )
        return float(nll)
