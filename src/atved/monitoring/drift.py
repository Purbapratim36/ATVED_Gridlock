"""
Data distribution drift detection.

Detects when the incoming data streams (e.g., brightness, vehicle counts)
or model predictions deviate significantly from the training distribution.
"""

from __future__ import annotations

import numpy as np
import structlog
from prometheus_client import Gauge

logger = structlog.get_logger(__name__)

# Drift Metrics
FEATURE_DRIFT_SCORE = Gauge(
    "atved_drift_feature_score",
    "Wasserstein distance between reference and current feature distributions",
    ["feature_name"]
)
CONCEPT_DRIFT_SCORE = Gauge(
    "atved_drift_concept_score",
    "KL divergence of model output probabilities",
    ["model_name"]
)

class DriftMonitor:
    """
    Computes statistical distance between reference distributions
    (from training) and online production data over a sliding window.
    """

    def __init__(self, reference_data: dict[str, np.ndarray]):
        self.reference_data = reference_data

    def compute_wasserstein_distance(self, feature_name: str, current_data: np.ndarray) -> float:
        """
        Compute the 1D Wasserstein distance (Earth Mover's Distance)
        between the reference and current distributions.
        """
        from scipy.stats import wasserstein_distance
        
        ref = self.reference_data.get(feature_name)
        if ref is None or len(current_data) == 0:
            return 0.0
            
        distance = wasserstein_distance(ref, current_data)
        
        FEATURE_DRIFT_SCORE.labels(feature_name=feature_name).set(distance)
        
        if distance > 0.15: # Arbitrary threshold for demo
            logger.warning(
                "drift.detected",
                feature=feature_name,
                distance=round(distance, 4)
            )
            
        return distance
