"""
ATVED Phase 5 Demo: Automatic License Plate Recognition (ALPR)

Runs object detection, evaluates traffic rules (Helmet Violation), 
and upon violation, crops the vehicle and reads its license plate.

Usage:
    python demo_alpr.py <CAMERA_URL>
"""

import sys
import os
import time
import cv2
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from atved.config import get_settings
from atved.detection import DetectionResult, FrameDetections
from atved.detection.tracker import ObjectTracker
from atved.violations.registry import ViolationRegistry

# Plate imports
from atved.plate.detector import PlateDetector
from atved.plate.ocr import PlateOCR
from atved.plate.pipeline import PlateRecognitionPipeline
from atved.plate.post_correct import PostCorrector
from atved.plate.rectifier import PlateRectifier
from atved.plate.super_resolve import SuperResolver

# ---- Color palette ----
COLORS = {
    "car":            (0, 255, 0),
    "motorcycle":     (255, 165, 0),
    "person":         (255, 255, 0),
    "helmet":         (0, 255, 0),   
    "no-helmet":      (0, 0, 255),   
    "head":           (0, 0, 255),   
    "Without Helmet": (0, 0, 255),   
    "With Helmet":    (0, 255, 0),   
}


def draw_frame(frame, detections, violations, frame_num, plate_result=None):
    """Draw bounding boxes, violations, and ALPR results on the frame."""
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

    # 3. Draw Plate Result if available
    if plate_result:
        px1, py1, px2, py2 = [int(c) for c in plate_result.bbox_in_frame]
        
        # Yellow box for plate
        cv2.rectangle(annotated, (px1, py1), (px2, py2), (0, 255, 255), 3)
        
        # Plate text
        plate_text = f"PLATE: {plate_result.corrected_text}"
        (text_w, text_h), _ = cv2.getTextSize(plate_text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
        
        # Draw text block below the plate
        cv2.rectangle(annotated, (px1, py2 + 5), (px1 + text_w + 10, py2 + 5 + text_h + 10), (0, 255, 255), -1)
        cv2.putText(annotated, plate_text, (px1 + 5, py2 + 5 + text_h + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)

    # 4. Draw live stats bar at the top
    h, w = annotated.shape[:2]
    cv2.rectangle(annotated, (0, 0), (w, 40), (0, 0, 0), -1)
    
    status_color = (0, 0, 255) if violations else (0, 255, 0)
    stats_text = f"ATVED Phase 5 | ALPR Active | Frame: {frame_num} | Violations: {len(violations)}"
    cv2.putText(annotated, stats_text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

    return annotated


def init_alpr_pipeline(settings):
    """Initialize the Plate Recognition Pipeline"""
    print("  [Init] Loading ALPR components (PaddleOCR + Plate Detector)...")
    
    # 1. Plate Detector
    plate_model_path = os.path.join(os.path.dirname(__file__), "models", "plate_detector_best.pt")
    if not os.path.exists(plate_model_path):
        plate_model_path = os.path.join(os.path.dirname(__file__), "plate_detector_best.pt")
        
    if not os.path.exists(plate_model_path):
        print(f"  ERROR: Could not find Plate Detector model at {plate_model_path}")
        print("  Did you run the Colab Notebook to train the Plate model?")
        sys.exit(1)
        
    settings.plate_recognition.detector.weights_path = plate_model_path
    detector = PlateDetector(settings.plate_recognition.detector)
    
    # 2. Rectifier & Corrector
    rectifier = PlateRectifier()
    corrector = PostCorrector(settings.plate_recognition.post_correction)
    
    # 3. Super Resolver (Disabled for speed by default on CPU)
    sr_config = settings.plate_recognition.super_resolution
    sr_config.enabled = False
    super_resolver = SuperResolver(enabled=sr_config.enabled)
    
    # 4. OCR
    ocr_config = settings.plate_recognition.ocr
    ocr_config.use_gpu = False # Default to CPU to prevent crashes on non-NVIDIA laptops
    ocr = PlateOCR(ocr_config)
    
    return PlateRecognitionPipeline(
        detector=detector,
        rectifier=rectifier,
        ocr=ocr,
        corrector=corrector,
        super_resolver=super_resolver
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: python demo_alpr.py <CAMERA_URL>")
        sys.exit(1)

    camera_url = sys.argv[1]
    output_dir = os.path.join(os.path.dirname(__file__), "demo_output", "citations")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  ATVED Phase 5 - Automatic License Plate Recognition")
    print(f"{'='*60}")
    
    # --- Step 1: Initialize ATVED Components ---
    print("[1/4] Initializing Engine & AI Models...")
    
    try:
        from ultralytics import YOLO
    except ImportError:
        print("  ERROR: Missing dependencies. Run: pip install ultralytics")
        sys.exit(1)
        
    # Main object detector (Helmet/Vehicle)
    helmet_model_path = os.path.join(os.path.dirname(__file__), "models", "atved_helmet_best.pt")
    if not os.path.exists(helmet_model_path):
        helmet_model_path = os.path.join(os.path.dirname(__file__), "atved_helmet_best.pt")
    
    if not os.path.exists(helmet_model_path):
         print(f"  ERROR: Could not find Helmet model at {helmet_model_path}")
         sys.exit(1)
         
    model = YOLO(helmet_model_path)
    
    # ATVED Settings
    settings = get_settings()
    settings.violations.helmet.min_consecutive_frames = 5
    
    from atved.violations.helmet import HelmetViolationDetector
    HelmetViolationDetector.RIDER_CLASSES = {"person", "rider", "no-helmet", "head", "Without Helmet"}
    HelmetViolationDetector.HELMET_CLASS = "helmet"
    
    tracker = ObjectTracker()
    registry = ViolationRegistry(settings.violations)
    
    # Initialize ALPR
    alpr_pipeline = init_alpr_pipeline(settings)
    
    print("  Engine ready.")

    # --- Step 2: Connect to camera ---
    print("\n[2/4] Connecting to camera...")
    cap = cv2.VideoCapture(camera_url)

    if not cap.isOpened():
        print(f"  ERROR: Could not connect to {camera_url}")
        sys.exit(1)

    # --- Step 3: Run Engine ---
    print("\n[3/4] Running Engine... (Press Ctrl+C to stop)")
    print(f"      Waiting for violation to trigger ALPR read...\n")

    frame_num = 0
    history = []
    total_citations = 0
    alpr_reads = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            frame_num += 1
            timestamp = datetime.utcnow()

            # 1. Detect Objects (Vehicles/Helmets)
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

            # 4. Handle Violation + ALPR Read
            if violations:
                total_citations += len(violations)
                print(f"\n  🚨 CITATION ISSUED! (Frame {frame_num:04d})")
                
                # We will pick the first vehicle involved in the violation to read the plate
                plate_result = None
                
                for v in violations:
                    print(f"      Type   : {v.violation_type.value.upper()}")
                    
                    # Find the vehicle detection (motorcycle, car, etc.)
                    vehicle_det = next((d for d in v.detections if d.class_name in {"motorcycle", "car"}), None)
                    
                    if vehicle_det and not plate_result:
                        print(f"      -> Running ALPR on {vehicle_det.class_name}...")
                        
                        # RUN ALPR PIPELINE!
                        plate_result = alpr_pipeline.recognize(
                            frame=frame, 
                            vehicle_bbox=vehicle_det.bbox
                        )
                        
                        if plate_result:
                            alpr_reads += 1
                            print(f"      -> PLATE FOUND : {plate_result.corrected_text}")
                            print(f"      -> Confidence  : {plate_result.confidence:.0%}")
                        else:
                            print(f"      -> PLATE FOUND : (No plate detected or unreadable)")
                
                # Save evidence
                annotated = draw_frame(frame, tracked_detections, violations, frame_num, plate_result)
                path = os.path.join(output_dir, f"citation_alpr_{frame_num:04d}.jpg")
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
        print(f"  Total plates read      : {alpr_reads}")
        print(f"  Evidence photos saved  : {output_dir}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
