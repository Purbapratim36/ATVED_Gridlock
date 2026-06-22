"""ATVED automated test suite configurations."""
import pytest
import numpy as np
from datetime import datetime, timezone

from atved.db.models import ViolationType
from atved.detection import DetectionResult, FrameDetections

@pytest.fixture
def sample_frame():
    """Return a blank 1920x1080 BGR image."""
    return np.zeros((1080, 1920, 3), dtype=np.uint8)

@pytest.fixture
def sample_helmet_detections():
    """Return mock detections for a helmet violation."""
    return FrameDetections(
        frame_index=1,
        camera_id="CAM-1",
        timestamp=datetime.now(timezone.utc),
        inference_time_ms=12.5,
        detections=[
            DetectionResult(bbox=(100, 100, 300, 500), class_name="motorcycle", class_id=1, confidence=0.95, track_id=1),
            DetectionResult(bbox=(150, 50, 250, 350), class_name="rider", class_id=2, confidence=0.92, track_id=2),
            # Notice: No helmet detection present
        ]
    )
