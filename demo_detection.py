"""
ATVED Phase 3 Demo: Continuous Vehicle & Road User Detection with YOLOv8.

Connects to a phone camera, runs YOLOv8 object detection continuously,
draws bounding boxes on detected objects, and saves annotated output images.
Press Ctrl+C to stop.

Usage:
    python demo_detection.py http://100.91.114.197:8080/video
"""

import sys
import os
import time
import cv2
import numpy as np

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# ---- Color palette for different object classes ----
COLORS = {
    "car":            (0, 255, 0),     # Green
    "motorcycle":     (255, 165, 0),   # Orange
    "bus":            (255, 0, 0),     # Blue
    "truck":          (0, 0, 255),     # Red
    "van":            (128, 0, 128),   # Purple
    "bicycle":        (0, 255, 255),   # Yellow
    "pedestrian":     (255, 255, 0),   # Cyan
    "person":         (255, 255, 0),   # Cyan
    "rider":          (255, 0, 255),   # Magenta
    "driver":         (0, 128, 255),   # Orange-ish
    "auto_rickshaw":  (128, 255, 0),   # Lime
}


def draw_detections(frame, detections, frame_num, fps):
    """Draw bounding boxes, labels, and a live stats bar on the frame."""
    annotated = frame.copy()

    for det in detections:
        x1, y1, x2, y2 = [int(c) for c in det["bbox"]]
        label = det["class_name"]
        confidence = det["confidence"]
        color = COLORS.get(label, (255, 255, 255))

        # Draw bounding box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        # Draw label background
        text = f"{label} {confidence:.0%}"
        (text_w, text_h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(annotated, (x1, y1 - text_h - 10), (x1 + text_w + 5, y1), color, -1)

        # Draw label text
        cv2.putText(annotated, text, (x1 + 2, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    # Draw live stats bar at the top
    h, w = annotated.shape[:2]
    cv2.rectangle(annotated, (0, 0), (w, 40), (0, 0, 0), -1)
    stats_text = f"ATVED LIVE | Frame: {frame_num} | Objects: {len(detections)} | FPS: {fps:.1f}"
    cv2.putText(annotated, stats_text, (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    return annotated


def main():
    if len(sys.argv) < 2:
        print("Usage: python demo_detection.py <CAMERA_URL>")
        print("Examples:")
        print("  python demo_detection.py http://192.168.1.50:8080/video")
        sys.exit(1)

    camera_url = sys.argv[1]
    output_dir = os.path.join(os.path.dirname(__file__), "demo_output", "detections")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  ATVED - Continuous Live Detection")
    print(f"{'='*60}")
    print(f"  Camera URL : {camera_url}")
    print(f"  Output Dir : {output_dir}")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*60}\n")

    # --- Step 1: Load YOLOv8 Model ---
    print("[1/3] Loading YOLOv8 detection model...")
    try:
        from ultralytics import YOLO
    except ImportError:
        print("  ERROR: ultralytics not installed!")
        print("  Run: pip install ultralytics")
        sys.exit(1)

    model_name = "yolov8n.pt"
    print(f"  Loading model: {model_name}")
    model = YOLO(model_name)
    print(f"  Model loaded!\n")

    # --- Step 2: Connect to camera ---
    print("[2/3] Connecting to camera...")
    cap = cv2.VideoCapture(camera_url)

    if not cap.isOpened():
        print(f"  ERROR: Could not connect to {camera_url}")
        sys.exit(1)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"  Connected! Resolution: {width}x{height}\n")

    # --- Step 3: Continuous detection loop ---
    print("[3/3] Running continuous detection... (Press Ctrl+C to stop)\n")

    frame_num = 0
    total_objects = {}
    fps = 0.0
    save_every_n = 5  # Save an annotated image every 5 frames

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("  WARNING: Lost camera connection. Reconnecting...")
                cap.release()
                time.sleep(2)
                cap = cv2.VideoCapture(camera_url)
                continue

            frame_num += 1

            # Run YOLOv8 detection
            t0 = time.perf_counter()
            results = model.predict(frame, conf=0.4, verbose=False)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            fps = 1000.0 / max(elapsed_ms, 1)

            # Parse detections
            detections = []
            if results[0].boxes is not None:
                for box in results[0].boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = model.names[cls_id]
                    detections.append({
                        "bbox": (x1, y1, x2, y2),
                        "class_name": cls_name,
                        "confidence": conf,
                    })
                    total_objects[cls_name] = total_objects.get(cls_name, 0) + 1

            # Print live output
            det_summary = ", ".join([f"{d['class_name']}({d['confidence']:.0%})" for d in detections[:5]])
            if len(detections) > 5:
                det_summary += f" +{len(detections)-5} more"
            print(f"  Frame {frame_num:04d} | {len(detections):2d} objects | {elapsed_ms:6.0f}ms | {det_summary or 'no objects'}")

            # Save annotated image every N frames
            if frame_num % save_every_n == 0:
                annotated = draw_detections(frame, detections, frame_num, fps)
                path = os.path.join(output_dir, f"detected_frame_{frame_num:04d}.jpg")
                cv2.imwrite(path, annotated)

            # Small delay to avoid overloading CPU
            time.sleep(0.1)

    except KeyboardInterrupt:
        print(f"\n\n{'='*60}")
        print(f"  STOPPED BY USER")
        print(f"{'='*60}")

    finally:
        cap.release()

        # --- Final Summary ---
        print(f"\n  SESSION SUMMARY")
        print(f"  {'─'*40}")
        print(f"  Total frames processed : {frame_num}")
        print(f"  Last FPS               : {fps:.1f}")

        if total_objects:
            total_count = sum(total_objects.values())
            print(f"  Total detections       : {total_count}")
            print(f"\n  Objects detected across all frames:")
            for name, count in sorted(total_objects.items(), key=lambda x: -x[1]):
                print(f"    {name:20s} : {count}")

        saved_count = len([f for f in os.listdir(output_dir) if f.startswith("detected_")])
        print(f"\n  Annotated images saved : {saved_count}")
        print(f"  Output folder          : {output_dir}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
