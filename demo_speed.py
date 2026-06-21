"""
ATVED Phase 5b Demo: Speed / Over-speed Violation Detection

Detects and tracks vehicles, estimates their speed via pixel displacement
and a configurable pixels_per_meter calibration, and flags over-speed
violations.

Usage:
    python demo_speed.py <CAMERA_URL>

Calibration:
    Before running, you need to estimate pixels_per_meter for your camera.
    A quick method:
      1. Open a still frame from the camera.
      2. Identify a known real-world distance (e.g., lane width = 3.5 m).
      3. Measure the same distance in pixels (e.g., 210 px).
      4. pixels_per_meter = 210 / 3.5 = 60

    You can also set these values via command-line arguments.
"""

import sys
import os
import time
import math
import cv2
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from atved.config import get_settings
from atved.detection import DetectionResult, FrameDetections
from atved.detection.tracker import ObjectTracker
from atved.violations.speed import SpeedViolationDetector
from atved.db.models import ViolationType

# ---- Color palette ----
COLORS = {
    "car":            (0, 255, 0),
    "motorcycle":     (255, 165, 0),
    "bus":            (255, 200, 0),
    "truck":          (0, 200, 200),
    "person":         (255, 255, 0),
}

# Speed display colors
SPEED_OK_COLOR    = (0, 255, 0)    # Green
SPEED_WARN_COLOR  = (0, 200, 255)  # Orange
SPEED_OVER_COLOR  = (0, 0, 255)    # Red


def draw_frame(frame, detections, violations, frame_num, speed_data, speed_limit):
    """Draw bounding boxes with speed annotations."""
    annotated = frame.copy()
    
    # 1. Draw tracked vehicles with speed
    for det in detections:
        x1, y1, x2, y2 = [int(c) for c in det.bbox]
        label = det.class_name
        track_id = getattr(det, "track_id", None)
        
        color = COLORS.get(label, (200, 200, 200))
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        
        # Show track ID and class
        text = f"ID:{track_id} {label}"
        (text_w, text_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x1, y1 - text_h - 8), (x1 + text_w + 4, y1), color, -1)
        cv2.putText(annotated, text, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        
        # Show speed if available
        if track_id is not None and track_id in speed_data:
            speed = speed_data[track_id]
            if speed > speed_limit:
                sp_color = SPEED_OVER_COLOR
            elif speed > speed_limit * 0.8:
                sp_color = SPEED_WARN_COLOR
            else:
                sp_color = SPEED_OK_COLOR
                
            speed_text = f"{speed:.0f} km/h"
            (sw, sh), _ = cv2.getTextSize(speed_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(annotated, (x1, y2 + 2), (x1 + sw + 8, y2 + sh + 12), sp_color, -1)
            cv2.putText(annotated, speed_text, (x1 + 4, y2 + sh + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

    # 2. Draw violations
    for v in violations:
        for det in v.detections:
            x1, y1, x2, y2 = [int(c) for c in det.bbox]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 4)
            
            speed_val = v.evidence_signals.get("estimated_speed_kmh", 0)
            v_text = f"OVERSPEEDING! {speed_val:.0f} km/h (Limit: {speed_limit:.0f})"
            (text_w, text_h), _ = cv2.getTextSize(v_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(annotated, (x1, y2), (x1 + text_w + 5, y2 + text_h + 10), (0, 0, 255), -1)
            cv2.putText(annotated, v_text, (x1 + 2, y2 + text_h + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # 3. Stats bar
    h, w = annotated.shape[:2]
    cv2.rectangle(annotated, (0, 0), (w, 40), (0, 0, 0), -1)
    
    status_color = (0, 0, 255) if violations else (0, 255, 0)
    stats_text = f"ATVED Speed Detection | Frame: {frame_num} | Speed Limit: {speed_limit:.0f} km/h | Violations: {len(violations)}"
    cv2.putText(annotated, stats_text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)

    return annotated


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ATVED Speed Detection Demo")
    parser.add_argument("camera_url", help="Camera stream URL")
    parser.add_argument("--speed-limit", type=float, default=40.0,
                        help="Speed limit in km/h (default: 40)")
    parser.add_argument("--ppm", type=float, default=30.0,
                        help="Pixels per meter calibration (default: 30). "
                             "Measure a known distance on camera to calibrate.")
    args = parser.parse_args()

    camera_url = args.camera_url
    speed_limit = args.speed_limit
    pixels_per_meter = args.ppm
    
    output_dir = os.path.join(os.path.dirname(__file__), "demo_output", "speed_violations")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  ATVED Phase 5b - Speed Violation Detection")
    print(f"{'='*60}")
    
    # --- Step 1: Initialize ---
    print("[1/3] Initializing Engine...")
    
    try:
        from ultralytics import YOLO
    except ImportError:
        print("  ERROR: Missing ultralytics. Run: pip install ultralytics")
        sys.exit(1)
    
    # Use the standard YOLOv8n for vehicle detection (COCO classes)
    model_path = os.path.join(os.path.dirname(__file__), "yolov8n.pt")
    if not os.path.exists(model_path):
        print(f"  Downloading YOLOv8n model...")
        model = YOLO("yolov8n.pt")
    else:
        model = YOLO(model_path)
    
    # COCO vehicle class IDs
    VEHICLE_COCO_IDS = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
    
    settings = get_settings()
    
    # Configure speed detector
    speed_config = settings.violations.speed
    speed_config.min_consecutive_frames = 3
    speed_config.min_duration_seconds = 1.0
    speed_config.min_confidence = 0.6
    
    speed_detector = SpeedViolationDetector(config=speed_config)
    speed_detector.set_calibration(
        pixels_per_meter=pixels_per_meter,
        speed_limit_kmh=speed_limit,
    )
    
    tracker = ObjectTracker()
    
    print(f"  Speed Limit     : {speed_limit} km/h")
    print(f"  Pixels/Metre    : {pixels_per_meter}")
    print(f"  Engine ready.")
    
    # --- Step 2: Connect ---
    print(f"\n[2/3] Connecting to camera...")
    cap = cv2.VideoCapture(camera_url)
    if not cap.isOpened():
        print(f"  ERROR: Could not connect to {camera_url}")
        sys.exit(1)
    
    # --- Step 3: Run ---
    print(f"\n[3/3] Running Speed Detection... (Press Ctrl+C to stop)")
    print(f"      Move objects quickly in front of the camera to trigger!\n")
    
    frame_num = 0
    history = []
    total_violations = 0
    
    # For computing live speed of each tracked vehicle
    track_positions: dict[int, list[tuple[float, float, float]]] = {}
    speed_data: dict[int, float] = {}
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            
            frame_num += 1
            timestamp = datetime.utcnow()
            now = timestamp.timestamp()
            
            # 1. Detect vehicles only (COCO classes)
            results = model.predict(frame, conf=0.3, verbose=False, classes=list(VEHICLE_COCO_IDS.keys()))
            
            raw_detections = []
            if results[0].boxes is not None:
                for box in results[0].boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    cls_id = int(box.cls[0])
                    if cls_id in VEHICLE_COCO_IDS:
                        raw_detections.append(DetectionResult(
                            bbox=(x1, y1, x2, y2),
                            class_name=VEHICLE_COCO_IDS[cls_id],
                            class_id=cls_id,
                            confidence=float(box.conf[0])
                        ))
            
            # 2. Track
            tracked_detections = tracker.update(
                camera_id="demo_cam",
                detections=raw_detections,
                frame=frame
            )
            
            # 3. Compute live speed for display
            for det in tracked_detections:
                if det.track_id is None:
                    continue
                cx = (det.bbox[0] + det.bbox[2]) / 2
                cy = (det.bbox[1] + det.bbox[3]) / 2
                
                traj = track_positions.setdefault(det.track_id, [])
                traj.append((now, cx, cy))
                if len(traj) > 30:
                    traj[:] = traj[-30:]
                
                if len(traj) >= 3:
                    t0, x0, y0 = traj[-3]
                    t1, x1, y1 = traj[-1]
                    dt = t1 - t0
                    if dt > 0.05:
                        px_dist = math.sqrt((x1 - x0)**2 + (y1 - y0)**2)
                        metres = px_dist / pixels_per_meter
                        speed_data[det.track_id] = (metres / dt) * 3.6
            
            # 4. Build FrameDetections for violation analyzer
            frame_data = FrameDetections(
                frame_index=frame_num,
                camera_id="demo_cam",
                timestamp=timestamp,
                detections=tracked_detections
            )
            
            history.append(frame_data)
            if len(history) > 30:
                history.pop(0)
            
            # 5. Analyze for speed violations
            violations = speed_detector.analyze(frame_data, history)
            
            # 6. Handle violations
            if violations:
                total_violations += len(violations)
                for v in violations:
                    est_speed = v.evidence_signals.get("estimated_speed_kmh", 0)
                    over_by = v.evidence_signals.get("over_by_kmh", 0)
                    print(f"\n  🚨 SPEED VIOLATION! (Frame {frame_num:04d})")
                    print(f"      Speed    : {est_speed:.1f} km/h")
                    print(f"      Limit    : {speed_limit:.0f} km/h")
                    print(f"      Over by  : {over_by:.1f} km/h")
                    print(f"      Track ID : {v.evidence_signals.get('vehicle_track_id')}")
                
                annotated = draw_frame(frame, tracked_detections, violations, frame_num, speed_data, speed_limit)
                path = os.path.join(output_dir, f"speed_violation_{frame_num:04d}.jpg")
                cv2.imwrite(path, annotated)
                print(f"      Proof    : {path}\n")
                time.sleep(1)
            
            elif frame_num % 10 == 0:
                active_speeds = {tid: f"{s:.0f}" for tid, s in speed_data.items() 
                                if tid in {d.track_id for d in tracked_detections}}
                print(f"  Frame {frame_num:04d} | Vehicles: {len(tracked_detections)} | Speeds: {active_speeds}")
            
            time.sleep(0.05)
    
    except KeyboardInterrupt:
        print(f"\n\n{'='*60}")
        print(f"  STOPPED BY USER")
        print(f"{'='*60}")
    
    finally:
        cap.release()
        print(f"  Total speed violations : {total_violations}")
        print(f"  Evidence saved         : {output_dir}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
