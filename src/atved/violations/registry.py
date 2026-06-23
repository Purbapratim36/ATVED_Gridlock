"""
Dynamic violation module registry.

Auto-discovers all violation detector classes and provides a single
entry point to run all enabled detectors against a frame's detections.
"""

from __future__ import annotations

from typing import Any

import structlog

from atved.config import ViolationModuleConfig, ViolationsConfig
from atved.db.models import ViolationType
from atved.detection import FrameDetections
from atved.violations.base import BaseViolationDetector, ViolationCandidate
from atved.violations.helmet import HelmetViolationDetector
from atved.violations.seatbelt import SeatbeltViolationDetector
from atved.violations.triple_riding import TripleRidingDetector
from atved.violations.wrong_side import WrongSideDetector
from atved.violations.stop_line import StopLineDetector
from atved.violations.red_light import RedLightDetector
from atved.violations.illegal_parking import IllegalParkingDetector
from atved.violations.speed import SpeedViolationDetector

logger = structlog.get_logger(__name__)

# Mapping from ViolationType to detector class and config attribute name.
_DETECTOR_MAP: dict[ViolationType, tuple[type[BaseViolationDetector], str]] = {
    ViolationType.HELMET: (HelmetViolationDetector, "helmet"),
    ViolationType.SEATBELT: (SeatbeltViolationDetector, "seatbelt"),
    ViolationType.TRIPLE_RIDING: (TripleRidingDetector, "triple_riding"),
    ViolationType.WRONG_SIDE: (WrongSideDetector, "wrong_side"),
    ViolationType.STOP_LINE: (StopLineDetector, "stop_line"),
    ViolationType.RED_LIGHT: (RedLightDetector, "red_light"),
    ViolationType.ILLEGAL_PARKING: (IllegalParkingDetector, "illegal_parking"),
    ViolationType.SPEEDING: (SpeedViolationDetector, "speed"),
}


class ViolationRegistry:
    """
    Central registry that instantiates, configures, and orchestrates
    all violation detector modules.

    Usage::

        registry = ViolationRegistry(settings.violations)
        candidates = registry.analyze_all(frame_detections, history)
    """

    def __init__(self, config: ViolationsConfig) -> None:
        self._detectors: list[BaseViolationDetector] = []
        self._detector_map: dict[ViolationType, BaseViolationDetector] = {}

        for vtype, (cls, config_attr) in _DETECTOR_MAP.items():
            module_config: ViolationModuleConfig = getattr(config, config_attr)
            detector = cls(config=module_config, violation_type=vtype)

            if detector.is_enabled:
                self._detectors.append(detector)
                self._detector_map[vtype] = detector
                logger.info(
                    "registry.loaded",
                    violation_type=vtype.value,
                    min_confidence=module_config.min_confidence,
                )
            else:
                logger.info("registry.skipped_disabled", violation_type=vtype.value)

        logger.info("registry.initialized", active_detectors=len(self._detectors))

    @property
    def active_detectors(self) -> list[BaseViolationDetector]:
        """Return list of currently active (enabled) detectors."""
        return list(self._detectors)

    def get_detector(self, violation_type: ViolationType) -> BaseViolationDetector | None:
        """Get a specific detector by type, or None if disabled."""
        return self._detector_map.get(violation_type)

    def analyze_all(
        self,
        frame_detections: FrameDetections,
        history: list[FrameDetections],
    ) -> list[ViolationCandidate]:
        """
        Run all enabled detectors against the current frame and return
        aggregated violation candidates.

        Parameters
        ----------
        frame_detections:
            Current frame's detection results with track IDs.
        history:
            Recent history of FrameDetections for the same camera,
            used by detectors that need temporal context (e.g., wrong-side,
            illegal parking).

        Returns
        -------
        Combined list of ViolationCandidates from all detectors.
        """
        all_candidates: list[ViolationCandidate] = []

        for detector in self._detectors:
            try:
                candidates = detector.analyze(frame_detections, history)
                if candidates:
                    import sys
                    import os
                    # Ensure computer_vision_models is in path to import the map
                    cv_models_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'computer_vision_models')
                    if cv_models_path not in sys.path:
                        sys.path.insert(0, cv_models_path)
                        
                    from violation_mapping import vehicle_violation_map
                    
                    filtered_candidates = []
                    for c in candidates:
                        # Assuming the first detection is the primary vehicle
                        vehicle_class = c.detections[0].class_name if c.detections else None
                        violation_type_str = detector.violation_type.name.upper()
                        
                        if vehicle_violation_map.is_eligible(vehicle_class, violation_type_str):
                            filtered_candidates.append(c)
                            
                    if filtered_candidates:
                        all_candidates.extend(filtered_candidates)
                    logger.debug(
                        "registry.violations_found",
                        detector=detector.violation_type.value,
                        count=len(candidates),
                        camera_id=frame_detections.camera_id,
                    )
            except Exception:
                logger.exception(
                    "registry.detector_error",
                    detector=detector.violation_type.value,
                    camera_id=frame_detections.camera_id,
                )

        return all_candidates

    def configure_camera(
        self,
        camera_config: dict[str, Any],
    ) -> None:
        """
        Apply per-camera configuration to detectors that need it.

        Camera-specific settings (stop line position, expected direction,
        no-parking zones) are stored in ``camera.config_json`` and must
        be injected into the relevant detectors when processing frames
        from that camera.
        """
        # Stop line position
        stop_line_y = camera_config.get("stop_line_y")
        if stop_line_y is not None:
            sl_det = self._detector_map.get(ViolationType.STOP_LINE)
            if sl_det and isinstance(sl_det, StopLineDetector):
                sl_det.set_stop_line(float(stop_line_y))

            rl_det = self._detector_map.get(ViolationType.RED_LIGHT)
            if rl_det and isinstance(rl_det, RedLightDetector):
                rl_det.set_stop_line(float(stop_line_y))

        # Expected traffic direction
        direction = camera_config.get("expected_direction_deg")
        if direction is not None:
            ws_det = self._detector_map.get(ViolationType.WRONG_SIDE)
            if ws_det and isinstance(ws_det, WrongSideDetector):
                ws_det.set_expected_direction(float(direction))

        # No-parking zones
        zones = camera_config.get("no_parking_zones")
        if zones is not None:
            ip_det = self._detector_map.get(ViolationType.ILLEGAL_PARKING)
            if ip_det and isinstance(ip_det, IllegalParkingDetector):
                ip_det.set_zones(zones)

        # Speed calibration
        # Speed calibration is now loaded dynamically via load_calibration() inside SpeedViolationDetector.
        # We no longer pass pixels_per_meter from camera_config.
        pass
