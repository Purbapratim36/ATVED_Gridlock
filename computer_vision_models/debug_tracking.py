import sys
import os
sys.path.insert(0, r"C:\Users\mahan\OneDrive\Documents\Desktop\Projects\Gridlock_sunny\src")
import numpy as np
from atved.detection import DetectionResult
from atved.detection.tracker import ObjectTracker
from atved.violations.registry import ViolationRegistry

tracker = ObjectTracker()
registry = ViolationRegistry() # default loaded from config?

raw_detections = []
for i in range(5):
    raw_detections.append(DetectionResult(bbox=(10.0+i, 10.0, 50.0+i, 50.0), class_name="motorcycle", class_id=3, confidence=0.9))
    raw_detections.append(DetectionResult(bbox=(15.0+i, 5.0, 30.0+i, 20.0), class_name="person", class_id=0, confidence=0.9))
    # mock helmet missing
    
    tracked = tracker.update("cam", raw_detections, np.zeros((100,100,3), dtype=np.uint8))
    print(f"Frame {i}: {[ (t.class_name, getattr(t, 'track_id', None)) for t in tracked]}")
