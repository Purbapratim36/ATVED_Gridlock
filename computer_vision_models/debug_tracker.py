import cv2
import sys
import os
import json
from datetime import datetime
from ultralytics import YOLO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from atved.detection import DetectionResult, FrameDetections
from atved.detection.tracker import ObjectTracker

model = YOLO("atved_helmet_best.pt")
seatbelt_model = YOLO("atved_seatbelt_best.pt")
tracker = ObjectTracker()

img = cv2.imread(r"C:\Users\mahan\OneDrive\Documents\Desktop\Projects\Gridlock_sunny\confusion_matrix.png")
results = model.predict(img, conf=0.3, verbose=False)
raw = []
if results[0].boxes is not None:
    for box in results[0].boxes:
        cls_id = int(box.cls[0])
        raw.append(DetectionResult(
            bbox=tuple(box.xyxy[0].tolist()),
            class_name=model.names[cls_id],
            class_id=cls_id,
            confidence=float(box.conf[0])
        ))

tracked = tracker.update("test", raw, img)

print("RAW:", [r.class_name for r in raw])
print("TRACKED:", [t.class_name for t in tracked])
