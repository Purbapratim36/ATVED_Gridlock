"""
ATVED Phase 6 Demo: Live Database Ingestion

Runs the AI models to detect violations (Helmet & License Plate) and pushes
the citations to the FastAPI backend, which updates the database and the User's
Traffic Score.
"""

import sys
import os
import time
import requests
import cv2
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ultralytics import YOLO
from atved.config import get_settings
from atved.detection import DetectionResult, FrameDetections
from atved.detection.tracker import ObjectTracker
from atved.violations.helmet import HelmetViolationDetector
from atved.db.models import ViolationType
import atved.plate.pipeline as alpr

API_URL = "http://localhost:8000/api/v1/ingest"
CAMERA_ID = "DEMO-CAM-01"

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("camera_url")
    args = parser.parse_args()
    
    print("Initializing ATVED Inference Engine...")
    model = YOLO("yolov8n.pt")
    helmet_model_path = os.path.join("models", "helmet_detector_best.pt")
    if os.path.exists(helmet_model_path):
        model = YOLO(helmet_model_path)
    
    settings = get_settings()
    detector = HelmetViolationDetector(config=settings.violations.helmet)
    tracker = ObjectTracker()
    
    try:
        plate_pipeline = alpr.PlateRecognitionPipeline()
    except Exception as e:
        print(f"Warning: Plate pipeline failed to load: {e}")
        plate_pipeline = None

    cap = cv2.VideoCapture(args.camera_url)
    if not cap.isOpened():
        print("Failed to open camera.")
        return

    print(f"\nConnected to camera. Sending violations to {API_URL} ...\n")
    frame_num = 0
    history = []
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret: break
            frame_num += 1
            
            # Simple simulation if no complex video: we just force a violation
            # For the demo we run inference
            results = model.predict(frame, conf=0.5, verbose=False)
            
            raw_detections = []
            if results[0].boxes:
                for box in results[0].boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    cls_id = int(box.cls[0])
                    name = model.names[cls_id]
                    raw_detections.append(DetectionResult(
                        bbox=(x1, y1, x2, y2), class_name=name, class_id=cls_id, confidence=float(box.conf[0])
                    ))
                    
            tracked = tracker.update(CAMERA_ID, raw_detections, frame)
            
            f_data = FrameDetections(
                frame_index=frame_num,
                camera_id=CAMERA_ID,
                timestamp=datetime.now(timezone.utc),
                detections=tracked
            )
            history.append(f_data)
            if len(history) > 30: history.pop(0)
            
            violations = detector.analyze(f_data, history)
            for v in violations:
                plate_text = "MH 12 AB 1234" # Default mock plate
                plate_conf = 0.99
                
                # Try real OCR if available
                if plate_pipeline and v.detections:
                    veh_box = v.detections[0].bbox
                    try:
                        veh_crop = frame[int(veh_box[1]):int(veh_box[3]), int(veh_box[0]):int(veh_box[2])]
                        res = plate_pipeline.process_vehicle_crop(veh_crop)
                        if res:
                            plate_text = res.text
                            plate_conf = res.confidence
                    except: pass
                
                print(f"🚨 VIOLATION DETECTED! Plate: {plate_text}")
                
                # Push to backend
                payload = {
                    "camera_external_id": CAMERA_ID,
                    "violation_type": "HELMET",
                    "confidence_score": v.raw_confidence,
                    "vehicle_type": "motorcycle",
                    "plate_text": plate_text,
                    "plate_confidence": plate_conf,
                }
                
                try:
                    resp = requests.post(API_URL, json=payload)
                    if resp.status_code == 200:
                        print(f"   -> Successfully ingested to database! ID: {resp.json()['id']}")
                    else:
                        print(f"   -> Failed to ingest: {resp.text}")
                except Exception as e:
                    print(f"   -> API Connection Error: {e}")
                    
                time.sleep(1) # Prevent spam
                
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        cap.release()

if __name__ == "__main__":
    main()
