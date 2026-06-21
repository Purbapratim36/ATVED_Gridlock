"""
ATVED Phase 4 Demo: Violation Logic and Issuance Workflow

Runs object detection, assigns persistent tracking IDs (ByteTrack),
evaluates traffic rules (Helmet Violation), and triggers mock citations.

Usage:
    pip install supervision
    python demo_violations.py http://100.91.114.197:8080/video
"""

import sys
import os
import time
import cv2
import numpy as np
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from atved.config import get_settings
from atved.detection import DetectionResult, FrameDetections
from atved.detection.tracker import ObjectTracker
from atved.violations.registry import ViolationRegistry

# ---- Color palette ----
COLORS = {
    "car":            (0, 255, 0),
    "motorcycle":     (255, 165, 0),
    "person":         (255, 255, 0),
    "helmet":         (0, 255, 0),   # Green
    "no-helmet":      (0, 0, 255),   # Red
    "head":           (0, 0, 255),   # Red
    "Without Helmet": (0, 0, 255),   # Red
    "With Helmet":    (0, 255, 0),   # Green
}


def draw_frame(frame, detections, violations, frame_num):
    """Draw bounding boxes and violations on the frame."""
    annotated = frame.copy()
    
    # 1. Draw regular tracked objects
    for det in detections:
        x1, y1, x2, y2 = [int(c) for c in det.bbox]
        label = det.class_name
        track_id = getattr(det, "track_id", "?")
        
        # Determine color (default to gray if not in palette)
        color = COLORS.get(label, (200, 200, 200))
        
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        
        text = f"ID:{track_id} {label}"
        (text_w, text_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(annotated, (x1, y1 - text_h - 10), (x1 + text_w + 5, y1), color, -1)
        cv2.putText(annotated, text, (x1 + 2, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    # 2. Draw active violations in RED
    for v in violations:
        # Highlight all objects involved in the violation
        for det in v.detections:
            x1, y1, x2, y2 = [int(c) for c in det.bbox]
            
            # Thick red box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 4)
            
            # Violation banner
            v_text = f"VIOLATION: {v.violation_type.value.upper()}!"
            (text_w, text_h), _ = cv2.getTextSize(v_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(annotated, (x1, y2), (x1 + text_w + 5, y2 + text_h + 10), (0, 0, 255), -1)
            cv2.putText(annotated, v_text, (x1 + 2, y2 + text_h + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # 3. Draw live stats bar at the top
    h, w = annotated.shape[:2]
    cv2.rectangle(annotated, (0, 0), (w, 40), (0, 0, 0), -1)
    
    status_color = (0, 0, 255) if violations else (0, 255, 0)
    stats_text = f"ATVED Phase 4 | Frame: {frame_num} | Tracked: {len(detections)} | Violations: {len(violations)}"
    cv2.putText(annotated, stats_text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

    return annotated


def main():
    if len(sys.argv) < 2:
        print("Usage: python demo_violations.py <CAMERA_URL>")
        sys.exit(1)

    camera_url = sys.argv[1]
    output_dir = os.path.join(os.path.dirname(__file__), "demo_output", "citations")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  ATVED Phase 4 - Violation & Tracking Engine")
    print(f"{'='*60}")
    
    # --- Step 1: Initialize ATVED Components ---
    print("[1/4] Initializing ATVED modules...")
    
    try:
        from ultralytics import YOLO
        import supervision
    except ImportError:
        print("  ERROR: Missing dependencies.")
        print("  Run: pip install ultralytics supervision")
        sys.exit(1)
        
    model_path = os.path.join(os.path.dirname(__file__), "models", "atved_helmet_best.pt")
    if not os.path.exists(model_path):
        # Fallback to root just in case
        model_path = os.path.join(os.path.dirname(__file__), "atved_helmet_best.pt")
        if not os.path.exists(model_path):
            print(f"  ERROR: Could not find your custom model at {model_path}")
            print("  Did you download it from Colab and place it in the Gridlock_sunny folder?")
            sys.exit(1)
        
    model = YOLO(model_path)
    settings = get_settings()
    
    # Configure the rule to trigger fast for the demo
    # We want a helmet violation to trigger if seen for 5 frames
    settings.violations.helmet.min_consecutive_frames = 5
    
    # We no longer need to pretend 'person' is 'rider' because our custom 
    # model can detect 'no-helmet' or 'head' directly!
    from atved.violations.helmet import HelmetViolationDetector
    HelmetViolationDetector.RIDER_CLASSES = {"person", "rider", "no-helmet", "head", "Without Helmet"}
    HelmetViolationDetector.HELMET_CLASS = "helmet"  # or "With Helmet" depending on the dataset
    
    # Optional: tell the detector to also accept "With Helmet" just in case
    HelmetViolationDetector._check_helmet_in_region = lambda self, head_region, helmets: any(
        (h.class_name in {"helmet", "With Helmet"}) for h in helmets
    )
    
    tracker = ObjectTracker()
    registry = ViolationRegistry(settings.violations)
    
    print("  Engine ready. (Configured to detect No-Helmet violations)")

    # --- Step 2: Connect to camera ---
    print("\n[2/4] Connecting to camera...")
    cap = cv2.VideoCapture(camera_url)

    if not cap.isOpened():
        print(f"  ERROR: Could not connect to {camera_url}")
        sys.exit(1)

    # --- Step 3: Run Engine ---
    print("\n[3/4] Running Engine... (Press Ctrl+C to stop)")
    print(f"      Point the camera at a motorcycle and a person to trigger a citation!\n")

    frame_num = 0
    history = []
    total_citations = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            frame_num += 1
            timestamp = datetime.utcnow()

            # 1. Detect
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

            # 2. Track (assign IDs)
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
            
            # Maintain history for rules engine
            history.append(frame_data)
            if len(history) > 30:
                history.pop(0)

            # 3. Analyze for Violations
            violations = registry.analyze_all(frame_data, history)

            # 4. Handle Mock Issuance
            if violations:
                total_citations += len(violations)
                print(f"\n  🚨 CITATION ISSUED! (Frame {frame_num:04d})")
                for v in violations:
                    print(f"      Type   : {v.violation_type.value.upper()}")
                    print(f"      Score  : {v.raw_confidence:.0%}")
                    print(f"      Reason : Sustained observation (Track ID: {v.evidence_signals.get('rider_track_id')})")
                
                # Save evidence
                annotated = draw_frame(frame, tracked_detections, violations, frame_num)
                path = os.path.join(output_dir, f"citation_{frame_num:04d}.jpg")
                cv2.imwrite(path, annotated)
                print(f"      Proof  : {path}\n")
                
                # Pause briefly to highlight the issuance
                time.sleep(1)

            elif frame_num % 10 == 0:
                print(f"  Frame {frame_num:04d} | Tracking {len(tracked_detections)} objects | No violations")

            # Small delay
            time.sleep(0.05)

    except KeyboardInterrupt:
        print(f"\n\n{'='*60}")
        print(f"  STOPPED BY USER")
        print(f"{'='*60}")

    finally:
        cap.release()
        print(f"  Total citations issued : {total_citations}")
        print(f"  Evidence photos saved  : {output_dir}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
