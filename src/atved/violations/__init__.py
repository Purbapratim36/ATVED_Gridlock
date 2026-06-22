"""
ATVED violations package.

Provides modular violation detection, confidence calibration,
and a registry for dynamic module orchestration.
"""

from __future__ import annotations

from atved.violations.base import BaseViolationDetector, ViolationCandidate
from atved.violations.classifier import UnifiedClassifier, TriageResult
from atved.violations.registry import ViolationRegistry
from atved.violations.helmet import HelmetViolationDetector
from atved.violations.seatbelt import SeatbeltViolationDetector
from atved.violations.triple_riding import TripleRidingDetector
from atved.violations.wrong_side import WrongSideDetector
from atved.violations.stop_line import StopLineDetector
from atved.violations.red_light import RedLightDetector
from atved.violations.illegal_parking import IllegalParkingDetector
from atved.violations.speed import SpeedViolationDetector

__all__ = [
    "BaseViolationDetector",
    "ViolationCandidate",
    "UnifiedClassifier",
    "TriageResult",
    "ViolationRegistry",
    "HelmetViolationDetector",
    "SeatbeltViolationDetector",
    "TripleRidingDetector",
    "WrongSideDetector",
    "StopLineDetector",
    "RedLightDetector",
    "IllegalParkingDetector",
    "SpeedViolationDetector",
]
