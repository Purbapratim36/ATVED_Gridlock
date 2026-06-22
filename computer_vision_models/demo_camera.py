"""
ATVED Demo: Single-camera live feed test.

Connects directly to a phone camera (IP Webcam app), grabs frames,
runs the preprocessing pipeline, and saves sample output images
so you can verify the system is working.

Usage:
    pip install opencv-python-headless numpy structlog prometheus-client pyyaml
    python demo_camera.py http://100.91.114.197:8080/video
"""

import sys
import os
import time
import cv2
import numpy as np

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def main():
    if len(sys.argv) < 2:
        print("Usage: python demo_camera.py <CAMERA_URL>")
        print("Examples:")
        print("  python demo_camera.py http://192.168.1.50:8080/video")
        print("  python demo_camera.py rtsp://192.168.1.50:8080/h264_pcm.sdp")
        sys.exit(1)

    camera_url = sys.argv[1]
    output_dir = os.path.join(os.path.dirname(__file__), "demo_output")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  ATVED Demo - Live Camera Test")
    print(f"{'='*60}")
    print(f"  Camera URL : {camera_url}")
    print(f"  Output Dir : {output_dir}")
    print(f"{'='*60}\n")

    # --- Step 1: Connect to camera ---
    print("[1/4] Connecting to camera...")
    cap = cv2.VideoCapture(camera_url)

    if not cap.isOpened():
        print(f"  ERROR: Could not connect to {camera_url}")
        print("  Make sure:")
        print("    - IP Webcam app is running on your phone")
        print("    - Phone and computer are on the SAME WiFi")
        print("    - The IP address is correct")
        sys.exit(1)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"  SUCCESS! Connected. Resolution: {width}x{height}")

    # --- Step 2: Grab test frames ---
    print("\n[2/4] Capturing frames from your phone camera...")
    frames = []
    frame_count = 10  # Grab 10 frames for the demo

    for i in range(frame_count):
        ret, frame = cap.read()
        if not ret:
            print(f"  WARNING: Failed to read frame {i+1}")
            continue
        frames.append(frame)
        print(f"  Captured frame {i+1}/{frame_count}")
        time.sleep(0.3)  # Small delay between frames

    cap.release()
    print(f"  Done! Captured {len(frames)} frames total.")

    if len(frames) == 0:
        print("  ERROR: Could not capture any frames. Check camera connection.")
        sys.exit(1)

    # --- Step 3: Save raw frames ---
    print(f"\n[3/4] Saving raw frames to {output_dir}...")
    for i, frame in enumerate(frames):
        path = os.path.join(output_dir, f"raw_frame_{i+1:02d}.jpg")
        cv2.imwrite(path, frame)
        print(f"  Saved: {path}")

    # --- Step 4: Run preprocessing pipeline ---
    print("\n[4/4] Running ATVED preprocessing pipeline...")
    try:
        from atved.preprocessing.pipeline import PreprocessingPipeline

        pipeline = PreprocessingPipeline()

        for i, frame in enumerate(frames):
            processed, quality, metadata = pipeline.process(frame)
            status = "ENHANCED" if quality.needs_enhancement else "OK"
            print(
                f"  Frame {i+1:02d}: "
                f"Brightness={quality.brightness:.1f}, "
                f"Blur={quality.blur_score:.1f}, "
                f"Noise={quality.noise_estimate:.1f}, "
                f"Status={status}"
            )

        print(f"\n  Preprocessing pipeline is working correctly!")

    except ImportError as e:
        print(f"  NOTE: Could not load full preprocessing pipeline ({e})")
        print(f"  But camera connection and frame capture work perfectly!")

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"  DEMO COMPLETE!")
    print(f"{'='*60}")
    print(f"  {len(frames)} frames captured from your phone camera")
    print(f"  Raw images saved to: {output_dir}")
    print(f"  Your camera feed is working with ATVED!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
