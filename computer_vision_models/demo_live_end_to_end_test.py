"""
ATVED Phase 7: Live End-to-End Demo

This script runs the AI inference pipeline on a video stream, detects violations (Helmet, Speeding),
and pushes them in real-time to the API server to update the dual dashboards.

Usage:
    python demo_live_end_to_end.py <path_to_video.mp4_or_camera_index>
"""

import sys
import os
import time
import cv2
import json
import requests
import random
from datetime import datetime
from ultralytics import YOLO

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from atved.config import get_settings
from atved.detection import DetectionResult, FrameDetections
from atved.detection.tracker import ObjectTracker
from atved.violations.registry import ViolationRegistry

API_URL = "http://localhost:8000/api/v1/ingest"

# ---- Color palette ----
COLORS = {
    "car":            (0, 255, 0),
    "motorcycle":     (255, 165, 0),
    "person":         (255, 255, 0),
    "helmet":         (0, 255, 0),   # Green
    "no-helmet":      (0, 0, 255),   # Red
}

def assign_mock_plate():
    """Assigns a mock plate to test registered vs unregistered flows."""
    plates = [
        "MH 12 AB 1234", # Our registered test user "John Doe"
        "DL 8C NC 1111", # Unregistered
        "KA 01 HG 9999", # Unregistered
        "TS 09 XY 4444"  # Unregistered
    ]
    # 30% chance to be the registered user for demo purposes
    if random.random() < 0.3:
        return plates[0]
    return random.choice(plates[1:])

def send_violation_to_api(violation, plate_text):
    """Sends the detected violation to the API Server."""
    payload = {
        "camera_external_id": "DEMO-LIVE-CAM",
        "violation_type": violation.violation_type.value.upper(),
        "confidence_score": round(violation.raw_confidence, 2),
        "vehicle_type": "motorcycle", # Hardcoded for this demo, should be dynamic
        "plate_text": plate_text,
        "plate_confidence": 0.95
    }
    
    try:
        response = requests.post(API_URL, json=payload, timeout=2)
        if response.status_code == 200:
            data = response.json()
            score = data.get("new_score")
            created_rto = data.get("new_driver_created_from_rto", False)
            print(f"    [API SUCCESS] Ingested {payload['violation_type']} for {plate_text}.")
            print(f"                  New Score: {score} | RTO Mock Used: {created_rto}")
        else:
            print(f"    [API ERROR] Status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"    [API FAILED] Could not reach {API_URL}. Is the server running? Error: {e}")

def draw_frame(frame, detections, violations, frame_num):
    """Draw bounding boxes and violations on the frame."""
    annotated = frame.copy()
    
    # 1. Draw regular tracked objects
    for det in detections:
        x1, y1, x2, y2 = [int(c) for c in det.bbox]
        label = det.class_name
        track_id = getattr(det, "track_id", "?")
        
        color = COLORS.get(label, (200, 200, 200))
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        
        text = f"ID:{track_id} {label}"
        (text_w, text_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(annotated, (x1, y1 - text_h - 10), (x1 + text_w + 5, y1), color, -1)
        cv2.putText(annotated, text, (x1 + 2, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    # 2. Draw active violations in RED
    for v in violations:
        for det in v.detections:
            x1, y1, x2, y2 = [int(c) for c in det.bbox]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 4)
            
            v_text = f"VIOLATION: {v.violation_type.value.upper()}!"
            (text_w, text_h), _ = cv2.getTextSize(v_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(annotated, (x1, y2), (x1 + text_w + 5, y2 + text_h + 10), (0, 0, 255), -1)
            cv2.putText(annotated, v_text, (x1 + 2, y2 + text_h + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # 3. Draw live stats bar at the top
    h, w = annotated.shape[:2]
    cv2.rectangle(annotated, (0, 0), (w, 40), (0, 0, 0), -1)
    
    status_color = (0, 0, 255) if violations else (0, 255, 0)
    stats_text = f"LIVE END-TO-END DEMO | Frame: {frame_num} | Violations: {len(violations)}"
    cv2.putText(annotated, stats_text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

    return annotated

def main():
    if len(sys.argv) < 2:
        print("Usage: python demo_live_end_to_end.py <VIDEO_PATH_OR_0>")
        sys.exit(1)

    video_source = sys.argv[1]
    if video_source.isdigit():
        video_source = int(video_source)
        
    print(f"\n{'='*60}")
    print(f"  ATVED Phase 7 - Live End-to-End Demo")
    print(f"{'='*60}")
    
    print("[1/4] Loading YOLOv8 Model...")
    # Use yolov8n or atved_helmet_best.pt if available
    model_path = "atved_helmet_best.pt" if os.path.exists("atved_helmet_best.pt") else "yolov8n.pt"
    try:
        model = YOLO(model_path)
    except Exception as e:
        print(f"Failed to load model {model_path}: {e}")
        sys.exit(1)
        
    try:
        seatbelt_model = YOLO("atved_seatbelt_best.pt")
        print("Loaded specialized Seatbelt Model (Dual-Model Architecture)")
    except Exception as e:
        print(f"Failed to load seatbelt model: {e}")
        seatbelt_model = None

    print("[2/4] Initializing ByteTrack & Violation Registry...")
    settings = get_settings()
    tracker = ObjectTracker()
    registry = ViolationRegistry(settings.violations)
    
    # Configure Speed Detector for Demo
    from atved.db.models import ViolationType
    speed_detector = registry.get_detector(ViolationType.SPEEDING)
    if speed_detector:
        # Mock calibration: 30 pixels per meter, 40 km/h speed limit
        speed_detector.set_calibration(pixels_per_meter=30.0, speed_limit_kmh=40.0)
        print("  -> Speed Detection active (mock calibration: 30px/m, 40km/h limit)")

    # Configure Red Light Detector
    red_light_detector = registry.get_detector(ViolationType.RED_LIGHT)
    STOP_LINE_Y = 300
    if red_light_detector:
        red_light_detector.set_stop_line(STOP_LINE_Y)
        print(f"  -> Red Light Detection active (Stop Line at Y={STOP_LINE_Y})")
        
    seatbelt_detector = registry.get_detector(ViolationType.SEATBELT)
    if seatbelt_detector:
        print("  -> Seatbelt Detection active (mocking driver classes inside cars)")

    print(f"[3/4] Opening Video Stream: {video_source}")
    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        print(f"Error: Cannot open video source {video_source}")
        sys.exit(1)

    output_dir = os.path.join(os.path.dirname(__file__), "demo_output", "live_citations")
    os.makedirs(output_dir, exist_ok=True)
    
    print("\n[4/4] Running Engine... (Press 'q' in the video window to stop or Ctrl+C here)\n")

    frame_num = 0
    history = []
    total_citations = 0
    
    # We want to avoid sending the same violation every single frame for the same track
    reported_tracks = set()
    
    mock_red_light_enabled = False
    
    # We will occasionally mock a missing seatbelt for demo purposes
    import random

    try:
        for _ in range(5):
            ret, frame = cap.read()
            if not ret:
                print("End of video stream.")
                break

            frame_num += 1
            timestamp = datetime.utcnow()

            # Optional: Resize for speed if video is huge
            # frame = cv2.resize(frame, (1280, 720))

            # 1. Detect using Primary Model (Vehicles, Pedestrians, Helmets)
            results = model.predict(frame, conf=0.3, verbose=False)
            
            raw_detections = []
            if results[0].boxes is not None:
                for box in results[0].boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    cls_id = int(box.cls[0])
                    raw_detections.append(DetectionResult(
                        bbox=(x1, y1, x2, y2),
                        class_name=model.names[cls_id],
                        class_id=cls_id,
                        confidence=float(box.conf[0])
                    ))
                    
            # 1.5 Detect using Specialized Seatbelt Model
            if seatbelt_model:
                sb_results = seatbelt_model.predict(frame, conf=0.3, verbose=False)
                if sb_results[0].boxes is not None:
                    for box in sb_results[0].boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        cls_id = int(box.cls[0])
                        # The seatbelt model might output 'seatbelt', 'drinking', etc.
                        raw_detections.append(DetectionResult(
                            bbox=(x1, y1, x2, y2),
                            class_name=seatbelt_model.names[cls_id],
                            class_id=1000 + cls_id, # offset ID to avoid conflict
                            confidence=float(box.conf[0])
                        ))
            
            # --- MOCK INJECTIONS FOR SEATBELT & RED LIGHT ---
            # 1. Red Light Injection
            if mock_red_light_enabled:
                # Add a fake red light detection so the RedLightDetector knows the state is RED
                raw_detections.append(DetectionResult(
                    bbox=(10, 10, 50, 50),
                    class_name="traffic_light_red",
                    class_id=999,
                    confidence=0.99
                ))
            
            # 2. Driver Bounding Box Injection
            # We still need a "driver" bounding box since neither model outputs one.
            # If we see a car, we map out a "driver" box. 
            # The SeatbeltViolationDetector will now check if the REAL 'seatbelt' detection from the 2nd model
            # overlaps with this injected driver box!
            for det in list(raw_detections):
                if det.class_name in ["car", "truck"]:
                    x1, y1, x2, y2 = det.bbox
                    # Driver is roughly top-right or top-left inside the car box
                    dx1 = x1 + (x2 - x1) * 0.6
                    dy1 = y1 + (y2 - y1) * 0.2
                    dx2 = dx1 + (x2 - x1) * 0.3
                    dy2 = dy1 + (y2 - y1) * 0.4
                    
                    raw_detections.append(DetectionResult(
                        bbox=(dx1, dy1, dx2, dy2),
                        class_name="driver",
                        class_id=998,
                        confidence=0.9
                    ))
            # ------------------------------------------------

            # 2. Track
            tracked_detections = tracker.update(
                camera_id="demo_cam",
                detections=raw_detections,
                frame=frame
            )

            frame_data = FrameDetections(
                frame_index=frame_num,
                camera_id="demo_cam",
                timestamp=timestamp,
                detections=tracked_detections
            )
            
            history.append(frame_data)
            if len(history) > 30:
                history.pop(0)

            # 3. Analyze for Violations
            violations = registry.analyze_all(frame_data, history)

            # 4. Handle Mock Issuance & API ingestion
            for v in violations:
                # The helmet detector might trigger on the person or the motorcycle
                track_id = v.evidence_signals.get('rider_track_id') or getattr(v.detections[0], 'track_id', None)
                
                # Only report once per track ID to avoid flooding the API
                if track_id and track_id not in reported_tracks:
                    reported_tracks.add(track_id)
                    total_citations += 1
                    
                    plate_text = assign_mock_plate()
                    print(f"\n  🚨 NEW VIOLATION DETECTED! (Frame {frame_num})")
                    print(f"      Type: {v.violation_type.value.upper()} | Track ID: {track_id}")
                    print(f"      Pushing to API Server...")
                    
                    # Push to API
                    send_violation_to_api(v, plate_text)
                    
                    # Save ONLY the frame with the violation (Evidence)
                    annotated_evidence = draw_frame(frame, tracked_detections, [v], frame_num)
                    evidence_path = os.path.join(output_dir, f"violation_{track_id}_{frame_num}.jpg")
                    cv2.imwrite(evidence_path, annotated_evidence)
                    print(f"      Evidence Saved: {evidence_path}")

            # 5. Show live video feed
            annotated = draw_frame(frame, tracked_detections, violations, frame_num)
            
            # Draw the stop line
            line_color = (0, 0, 255) if mock_red_light_enabled else (0, 255, 0)
            cv2.line(annotated, (0, STOP_LINE_Y), (annotated.shape[1], STOP_LINE_Y), line_color, 2)
            
            # Draw instructions
            cv2.putText(annotated, f"Red Light (Press 'r'): {'ON' if mock_red_light_enabled else 'OFF'}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, line_color, 2)
            
            # cv2.imshow("ATVED Live Engine", annotated)
            
            # Press 'q' to quit, 'r' to toggle red light
            key = ord('x') & 0xFF
            if key == ord('q'):
                break
            elif key == ord('r'):
                mock_red_light_enabled = not mock_red_light_enabled
                print(f"\n[DEMO] Traffic Signal State toggled to: {'RED' if mock_red_light_enabled else 'GREEN'}")

    except KeyboardInterrupt:
        print(f"\n\n{'='*60}")
        print(f"  STOPPED BY USER")
        print(f"{'='*60}")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(f"\n  Total unique citations issued to API : {total_citations}")
        print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
