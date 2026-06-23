"""
ATVED Phase 7: Live End-to-End Demo

This script runs the AI inference pipeline on a video stream, detects violations (Helmet, Speeding),
and pushes them in real-time to the API server to update the dual dashboards.

Usage:
    python demo_live_end_to_end.py <path_to_video.mp4_or_camera_index>
"""

# FILE: computer_vision_models/demo_live_end_to_end.py
# DEBUG-FIX: Added missing buffer_complete and ocr_source fields to payload for compound routing
import sys
import os
import time
import cv2
import json
import requests
import random
from datetime import datetime
import torch
from ultralytics import YOLO

# Determine best compute device (GPU if available)
compute_device = 0 if torch.cuda.is_available() else "cpu"
print(f"\n[SYSTEM] Initializing models on: {'GPU (CUDA)' if compute_device == 0 else 'CPU'}")

try:
    from fast_plate_ocr import LicensePlateRecognizer
    # Enable GPU and text orientation
    OCR_READER = LicensePlateRecognizer('cct-s-v2-global-model')
    OCR_ENGINE = "FAST_PLATE"
    print("Loaded Fast Plate OCR Engine (GPU Enabled via ONNXRuntime)")
except Exception as e:
    print(f"Failed to load Fast Plate OCR: {e}")
    OCR_READER = None
    OCR_ENGINE = "NONE"

# Initialize EasyOCR as a robust fallback
try:
    import easyocr
    EASY_OCR_READER = easyocr.Reader(['en'], gpu=torch.cuda.is_available())
    print("Loaded EasyOCR Fallback Engine")
except Exception as e:
    print(f"EasyOCR Fallback not available: {e}")
    EASY_OCR_READER = None

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
        "AS 03 PM 7823", # Registered to Purba Pratim Mahanta
        "AS 01 KK 4521", # Registered to Kunaljit Kashyap
        "KA 01 HG 9999", # Unregistered
        "DL 8C NC 1111"  # Unregistered
    ]
    # 50% chance to be the requested registered user for demo purposes
    if random.random() < 0.5:
        return plates[0]
    return random.choice(plates[1:])

def send_violation_to_api(violation, plate_text, evidence_image_path=None, plate_confidence=1.0):
    """
    Sends a confirmed violation to the central FastAPI server.
    """
    import base64
    
    # In a real system, we'd wait for a good streak. 
    # For demo, we just say buffer is complete.
    buffer_complete = getattr(violation, 'buffer_complete', True)
    ocr_source = getattr(violation, 'ocr_source', 'primary')
    
    print(f"[DIAG-1] DISPATCHING: plate={plate_text} | vtype={violation.violation_type.name.upper()} | "
          f"conf={round(violation.raw_confidence, 2):.2f} | ocr_source={ocr_source} | "
          f"ocr_conf={plate_confidence:.2f} | "
          f"buffer_complete={buffer_complete}")
          
    payload = {
        "camera_external_id": "DEMO-LIVE-CAM",
        "violation_type": violation.violation_type.name.upper(),
        "confidence_score": round(violation.raw_confidence, 2),
        "vehicle_type": "motorcycle",
        "plate_text": plate_text if plate_text else "UNREADABLE", # DEBUG-FIX: Send string to prevent 422 API error
        "plate_confidence": float(plate_confidence),
        "ocr_source": ocr_source,
        "ocr_confidence": float(plate_confidence),
        "buffer_complete": buffer_complete,
        "evidence_image_path": os.path.abspath(evidence_image_path) if evidence_image_path else None
    }
    
    try:
        response = requests.post(API_URL, json=payload, timeout=2)
        if response.status_code not in [200, 202]:
            print(f"    [API ERROR] Status {response.status_code}: {response.text}")
        else:
            data = response.json()
            score = data.get("new_score")
            created_rto = data.get("new_driver_created_from_rto", False)
            print(f"    [API SUCCESS] Ingested {payload['violation_type']} for {plate_text}.")
            print(f"                  New Score: {score} | RTO Mock Used: {created_rto}")
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

import threading
import queue
import cv2 as cv2_local
import numpy as np
import os
import json
import traceback

# Import standalone OCR preprocessing module
try:
    from ocr_preprocessing import (
        preprocess_plate_for_ocr, deskew_plate,
        is_valid_indian_plate, clean_ocr_text, apply_indian_plate_corrections
    )
    print("Loaded OCR Preprocessing Module (ocr_preprocessing.py)")
except ImportError:
    # Fallback: try relative import
    try:
        from computer_vision_models.ocr_preprocessing import (
            preprocess_plate_for_ocr, deskew_plate,
            is_valid_indian_plate, clean_ocr_text, apply_indian_plate_corrections
        )
        print("Loaded OCR Preprocessing Module (computer_vision_models.ocr_preprocessing)")
    except ImportError:
        print("WARNING: ocr_preprocessing.py not found, using built-in pipeline")
        preprocess_plate_for_ocr = None

# Thread-safe queue for async OCR
ocr_queue = queue.Queue()
from deduplicator import ViolationDeduplicator
deduplicator = ViolationDeduplicator(cooldown_seconds=30)

def advanced_anpr_pipeline(img_bgr):
    """Applies Simple Image Enhancement (No dangerous warping)."""
    gray = cv2_local.cvtColor(img_bgr, cv2_local.COLOR_BGR2GRAY)
    
    # Upscale for EasyOCR
    target_img = cv2_local.resize(gray, None, fx=2, fy=2, interpolation=cv2_local.INTER_CUBIC)
    
    # CLAHE for contrast
    clahe = cv2_local.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(target_img)
    
    # Otsu thresholding
    _, thresh = cv2_local.threshold(enhanced, 0, 255, cv2_local.THRESH_BINARY + cv2_local.THRESH_OTSU)
    
    return target_img, enhanced, thresh

def validate_and_ocr(image, raw_bgr_crop=None):
    """Run OCR and return best text + confidence, with Indian plate validation.
    
    Args:
        image: Preprocessed image (grayscale or BGR) for primary OCR.
        raw_bgr_crop: Optional un-binarized BGR crop for EasyOCR fallback path.
                      When provided, EasyOCR reads from this instead of the binarized image.
    """
    import re
    global OCR_ENGINE, OCR_READER
    best_text = None
    best_conf = 0.0
    all_texts = []
    
    # Strict Indian License Plate Regex Patterns
    # Standard format: AA00AA0000 or AA00A0000 (e.g., NL07CD3217, AS03PM7823)
    INDIAN_PLATE_STRICT = re.compile(r'^[A-Z]{2}\d{2}[A-Z]{1,3}\d{4}$')
    # Relaxed for partial reads (fewer trailing digits or series chars)
    INDIAN_PLATE_RELAXED = re.compile(r'^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{1,4}$')
    
    # Blacklist: annotation words that should NEVER be treated as plate text
    BLACKLIST = {'MOTORCYCLE', 'PERSON', 'CAR', 'TRUCK', 'BUS', 'DRIVER', 'HELMET',
                 'VIOLATION', 'SPEEDING', 'SEATBELT', 'MUBIN', 'DEMO', 'LIVE', 'FRAME'}
    
    if len(image.shape) == 2:
        image = cv2_local.cvtColor(image, cv2_local.COLOR_GRAY2BGR)
    
    if OCR_ENGINE == "FAST_PLATE":
        h, w = image.shape[:2]
        from plate_type_classifier import PlateTypeClassifier
        classifier = PlateTypeClassifier()
        is_two_line, plate_color_type = classifier.classify(image)
        
        crops_to_read = [image]
            
        for crop in crops_to_read:
            try:
                results = OCR_READER.run(crop)
            except Exception as e:
                results = []
                
            if not results:
                # Fast-plate-ocr completely failed to find any text. Trigger EasyOCR directly.
                if 'EASY_OCR_READER' in globals() and EASY_OCR_READER is not None:
                    easyocr_input = raw_bgr_crop if raw_bgr_crop is not None else crop
                    try:
                        easy_res = EASY_OCR_READER.readtext(easyocr_input, detail=0)
                        if easy_res:
                            easy_combined = "".join(easy_res).upper()
                            cleaned = "".join(c for c in easy_combined if c.isalnum())
                            if cleaned and not any(bw in cleaned for bw in BLACKLIST):
                                conf = 0.85
                                all_texts.append((cleaned, conf))
                                if conf > best_conf and len(cleaned) >= 3:
                                    best_text = cleaned
                                    best_conf = conf
                    except Exception as e:
                        pass
                continue
                
            for res in results:
                text = res.plate
                conf = 0.9  # fast-plate-ocr doesn't return full-string confidence by default
                cleaned = "".join(c for c in text.upper() if c.isalnum())
                
                # --- REGEX-DRIVEN EASYOCR FALLBACK GATE ---
                # STEP B: Sanitize and evaluate against Indian plate regex
                # Apply quick positional fixes before regex check
                temp_corrected = cleaned
                if len(temp_corrected) >= 2:
                    first_two = temp_corrected[:2].replace('0', 'O').replace('1', 'I').replace('5', 'S')
                    temp_corrected = first_two + temp_corrected[2:]
                if len(temp_corrected) >= 4:
                    mid = temp_corrected[2:4].replace('O', '0').replace('I', '1').replace('S', '5').replace('B', '8')
                    temp_corrected = temp_corrected[:2] + mid + temp_corrected[4:]
                
                # STEP C: Enforce Strict 10-character Indian Plate length
                regex_passed = bool(INDIAN_PLATE_STRICT.match(temp_corrected)) and len(temp_corrected) == 10
                
                # STEP D: If it misses characters, trigger efficient multi-pass rescanning!
                if not regex_passed and 'EASY_OCR_READER' in globals() and EASY_OCR_READER is not None:
                    easyocr_input = raw_bgr_crop if raw_bgr_crop is not None else crop
                    
                    # Create variants for aggressive rescanning
                    gray = cv2_local.cvtColor(easyocr_input, cv2_local.COLOR_BGR2GRAY)
                    _, thresh1 = cv2_local.threshold(gray, 100, 255, cv2_local.THRESH_BINARY)
                    _, thresh2 = cv2_local.threshold(gray, 0, 255, cv2_local.THRESH_BINARY + cv2_local.THRESH_OTSU)
                    
                    # Efficiently try variants until we hit 10 characters
                    best_easy_cleaned = ""
                    for variant in [easyocr_input, thresh1, thresh2, gray]:
                        try:
                            easy_res = EASY_OCR_READER.readtext(variant, detail=0)
                            if easy_res:
                                easy_cleaned = "".join(c for c in "".join(easy_res).upper() if c.isalnum())
                                if len(easy_cleaned) == 10 and INDIAN_PLATE_STRICT.match(easy_cleaned):
                                    best_easy_cleaned = easy_cleaned
                                    break # We found the perfect 10-char plate!
                                elif len(easy_cleaned) > len(best_easy_cleaned) and len(easy_cleaned) <= 11:
                                    best_easy_cleaned = easy_cleaned
                        except Exception:
                            pass
                            
                    if best_easy_cleaned:
                        if len(best_easy_cleaned) > len(cleaned) and len(best_easy_cleaned) <= 13:
                            cleaned = best_easy_cleaned
                            conf = 0.85
                
                if any(bw in cleaned for bw in BLACKLIST) or not cleaned:
                    continue
                all_texts.append((cleaned, conf))
                if conf > best_conf and len(cleaned) >= 3:
                    best_text = cleaned
                    best_conf = conf
                
    # ALWAYS try combining all reads (Indian plates are often split into 2 lines by OCR)
    # e.g. "MP04Z" (conf 0.27) + "F9619" (conf 0.99) = "MP04ZF9619"
    # BUT only accept the combined result if it looks like a valid plate
    if len(all_texts) >= 2:
        combined = "".join(t[0] for t in all_texts)
        avg_conf = sum(t[1] for t in all_texts) / len(all_texts)
        # Only prefer combined if it's plate-length AND passes validation
        if 8 <= len(combined) <= 13:
            # Import validation (may or may not be available)
            try:
                from ocr_preprocessing import is_valid_indian_plate as _validate
                if _validate(combined, plate_type=plate_color_type):
                    best_text = combined
                    best_conf = max(avg_conf, best_conf * 0.9)
                # else: keep the best single read
            except ImportError:
                # No validation available, accept if reasonable length
                best_text = combined
                best_conf = max(avg_conf, best_conf * 0.9)
    elif not best_text and all_texts:
        combined = "".join(t[0] for t in all_texts)
        avg_conf = sum(t[1] for t in all_texts) / len(all_texts)
        if len(combined) >= 4:
            best_text = combined
            best_conf = avg_conf
    
    # Apply Indian plate character corrections (preserved from original)
    if best_text:
        corrected = best_text
        if len(corrected) >= 2:
            first_two = corrected[:2].replace('0', 'O').replace('1', 'I').replace('5', 'S')
            corrected = first_two + corrected[2:]
        if len(corrected) >= 4:
            mid = corrected[2:4].replace('O', '0').replace('I', '1').replace('S', '5').replace('B', '8')
            corrected = corrected[:2] + mid + corrected[4:]
        best_text = corrected
        
    return best_text, best_conf, plate_color_type

def ocr_worker_loop():
    while True:
        job = ocr_queue.get()
        if job is None:
            break
            
        track_id = job['track_id']
        frame_num = job['frame_num']
        v = job['violation']
        frames_to_check = job['frames_to_check']
        plate_model = job['plate_model']
        compute_device = job['compute_device']
        full_evidence_path = job['full_evidence_path']
        
        # SMART BLUR FILTERING (Laplacian Variance)
        # Calculate sharpness of the pre-extracted vehicle crops
        crops_with_sharpness = []
        for vehicle_crop in frames_to_check:
            if vehicle_crop.size == 0: continue
            gray = cv2_local.cvtColor(vehicle_crop, cv2_local.COLOR_BGR2GRAY)
            sharpness = cv2_local.Laplacian(gray, cv2_local.CV_64F).var()
            crops_with_sharpness.append((sharpness, vehicle_crop))
            
        # Sort by sharpness descending, keep top 5
        crops_with_sharpness.sort(key=lambda x: x[0], reverse=True)
        top_crops = [x[1] for x in crops_with_sharpness[:5]]
        
        print(f"      [OCR Worker] Filtered {len(frames_to_check)} frames down to top {len(top_crops)} sharpest crops for Track {track_id}")

        global_best_text = None
        global_best_conf = 0.0
        best_vehicle_crop = None
        best_plate_crop = None
        best_enhanced = None
        
        all_readings = []

        for vehicle_crop in top_crops:
            # 1. YOLO Plate Detection (v2 single-class detector)
            p_res = plate_model.predict(vehicle_crop, conf=0.25, verbose=False, device=compute_device)
            plate_crop = None
            plate_detected_by_yolo = False
            
            if p_res[0].boxes is not None and len(p_res[0].boxes) > 0:
                # Pick highest confidence detection
                best_box_idx = 0
                best_box_conf = 0
                for bi, box in enumerate(p_res[0].boxes):
                    c = float(box.conf[0])
                    if c > best_box_conf:
                        best_box_conf = c
                        best_box_idx = bi
                px1, py1, px2, py2 = [int(c) for c in p_res[0].boxes[best_box_idx].xyxy[0].cpu().numpy()]
                
                # Add 8% padding to prevent edge characters from being cropped out
                bw, bh = px2 - px1, py2 - py1
                pad_x = int(bw * 0.08)
                pad_y = int(bh * 0.08)
                
                vh, vw = vehicle_crop.shape[:2]
                px1 = max(0, px1 - pad_x)
                py1 = max(0, py1 - pad_y)
                px2 = min(vw, px2 + pad_x)
                py2 = min(vh, py2 + pad_y)
                
                plate_crop = vehicle_crop[py1:py2, px1:px2]
                plate_detected_by_yolo = True
                print(f"      [Plate YOLO] Detected plate at conf={best_box_conf:.3f}, size={px2-px1}x{py2-py1}")
            else:
                # Fallback: bottom half of vehicle crop
                h, w = vehicle_crop.shape[:2]
                plate_crop = vehicle_crop[int(h*0.5):h, 0:w]
            
            if plate_crop is None or plate_crop.size == 0:
                continue
            
            # 2. OCR Preprocessing (new standalone module)
            found_text = None
            ocr_confidence = 0.0
            plate_type_detected = 'standard'
            
            if preprocess_plate_for_ocr is not None:
                # Returns: (padded_upscaled_bgr, enhanced_gray, adaptive_binary)
                padded_upscaled_bgr, enhanced, binary = preprocess_plate_for_ocr(plate_crop)
                if enhanced is not None:
                    # Try deskewing if plate was detected at angle
                    deskewed = deskew_plate(enhanced)
                    
                    # Try OCR on multiple preprocessed variants
                    # Pass the un-binarized BGR as raw_bgr_crop for EasyOCR fallback
                    if OCR_ENGINE == "FAST_PLATE":
                        variants_to_try = [plate_crop, padded_upscaled_bgr, enhanced]
                    else:
                        variants_to_try = [enhanced, binary, deskewed]
                        
                    for ocr_input in variants_to_try:
                        text, conf, plate_type = validate_and_ocr(ocr_input, raw_bgr_crop=padded_upscaled_bgr)
                        if text:
                            # Apply Indian plate corrections
                            text = apply_indian_plate_corrections(clean_ocr_text(text))
                            if not is_valid_indian_plate(text, plate_type=plate_type):
                                conf *= 0.5
                            all_readings.append((text, conf, vehicle_crop, plate_crop))
                            
                            # Keep track of the absolute best for fallback
                            if conf > ocr_confidence:
                                found_text = text
                                ocr_confidence = conf
                                plate_type_detected = plate_type

            else:
                # Fallback to old built-in pipeline
                original, enhanced, thresh = advanced_anpr_pipeline(plate_crop)
                for ocr_input in [enhanced, thresh, plate_crop]:
                    text, conf, plate_type = validate_and_ocr(ocr_input)
                    if text:
                        text = apply_indian_plate_corrections(clean_ocr_text(text))
                        if not is_valid_indian_plate(text, plate_type=plate_type):
                            conf *= 0.5
                        all_readings.append((text, conf, vehicle_crop, plate_crop))
                        if conf > ocr_confidence:
                            found_text = text
                            ocr_confidence = conf
                            plate_type_detected = plate_type
            
            # 3. Try Plate Recognizer API as backup if OCR confidence is low
            if (not all_readings or max([x[1] for x in all_readings]) < 0.5):
                pr_token = os.environ.get("PLATE_RECOGNIZER_TOKEN")
                if pr_token:
                    try:
                        _, img_encoded = cv2_local.imencode('.jpg', vehicle_crop)
                        response = requests.post(
                            'https://api.platerecognizer.com/v1/plate-reader/',
                            files=dict(upload=img_encoded.tobytes()),
                            headers={'Authorization': f'Token {pr_token}'},
                            timeout=5
                        )
                        res = response.json()
                        if res.get('results'):
                            api_best = res['results'][0]
                            api_text = api_best['plate'].upper()
                            api_conf = api_best['score']
                            found_text = clean_ocr_text(api_text)
                            all_readings.append((found_text, api_conf, vehicle_crop, plate_crop))
                            print(f"      [Plate API] Got: {found_text} conf={api_conf:.3f}")
                    except Exception as e:
                        print(f"      [API Error] Plate Recognizer failed: {e}")
                
        # --- TEMPORAL VOTING ---
        if all_readings:
            from collections import Counter
            text_counts = Counter([x[0] for x in all_readings])
            most_common_text = text_counts.most_common(1)[0][0]
            
            # Find the highest confidence reading for this most common text
            best_reading = max([x for x in all_readings if x[0] == most_common_text], key=lambda x: x[1])
            
            # Apply deterministic positional correction
            from ocr_correction import apply_positional_correction
            global_best_text = apply_positional_correction(best_reading[0])
            
            global_best_conf = best_reading[1]
            best_vehicle_crop = best_reading[2]
            best_plate_crop = best_reading[3]
            best_enhanced = best_vehicle_crop
            print(f"      [OCR Voting] Selected {global_best_text} from {len(all_readings)} readings (votes: {text_counts[most_common_text]})")

        # --- EMERGENCY DEMO FALLBACK (disabled by default) ---
        # Enable with --use-mock-fallback flag. When enabled, if OCR fails or
        # confidence is too low, returns a hardcoded Indian plate for demo purposes.
        USE_MOCK_FALLBACK = '--use-mock-fallback' in sys.argv
        if USE_MOCK_FALLBACK and (global_best_text is None or global_best_conf < 0.5):
            print("      [OCR Worker] Using emergency presentation fallback!")
            global_best_text = "MP04ZF9619" if int(track_id) % 2 == 0 else "MP04SH7500"
            global_best_conf = 0.95
            best_vehicle_crop = crops_with_sharpness[0][1] if crops_with_sharpness else np.zeros((100,100,3), dtype=np.uint8)
            best_enhanced = best_vehicle_crop
        elif global_best_text is None:
            print(f"      [OCR Worker] No plate text found for Track {track_id} (best conf: {global_best_conf:.3f})")
            global_best_text = "UNKNOWN"
            global_best_conf = 0.0
            best_vehicle_crop = crops_with_sharpness[0][1] if crops_with_sharpness else np.zeros((100,100,3), dtype=np.uint8)
            best_enhanced = best_vehicle_crop

        ocr_confidence = global_best_conf
        found_text = global_best_text
        plate_text = None
        challan_status = "Generated"
        
        os.makedirs("output/manual_verification", exist_ok=True)
        base_filename = f"violation_{track_id}_{frame_num}"
        evidence_path = None
        
        if found_text and ocr_confidence >= 0.75:
            plate_text = found_text
            if best_vehicle_crop is not None:
                cv2_local.imwrite(f"output/{base_filename}_vehicle_crop.jpg", best_vehicle_crop)
                cv2_local.imwrite(f"output/{base_filename}_plate_crop.jpg", best_plate_crop)
                evidence_path = f"output/{base_filename}_plate_enhanced.jpg"
                cv2_local.imwrite(evidence_path, best_enhanced)
        elif found_text and ocr_confidence >= 0.5:
            plate_text = found_text
            challan_status = "Generated (Low Confidence - Review Recommended)"
            if best_vehicle_crop is not None:
                cv2_local.imwrite(f"output/{base_filename}_vehicle_crop.jpg", best_vehicle_crop)
                cv2_local.imwrite(f"output/{base_filename}_plate_crop.jpg", best_plate_crop)
                evidence_path = f"output/manual_verification/{base_filename}_plate_enhanced.jpg"
                cv2_local.imwrite(evidence_path, best_enhanced)
        else:
            challan_status = "Failed OCR / Low Confidence"
            plate_text = None
            # Use the first crop as fallback
            if len(top_crops) > 0:
                plate_evidence_path = f"output/manual_verification/{base_filename}_vehicle_crop.jpg"
                cv2_local.imwrite(plate_evidence_path, top_crops[0])
            
        print("\n" + "="*40)
        print(json.dumps({
            "vehicle_type": "motorcycle",
            "violation": v.violation_type.name.replace('_', ' ').title(),
            "number_plate": plate_text if plate_text else "NOT DETECTED",
            "ocr_confidence": round(float(ocr_confidence), 2) if ocr_confidence else 0.0,
            "challan_status": challan_status
        }, indent=2))
        print("="*40 + "\n")
        
        # We NO LONGER discard unreadable plates. Every violation must generate a DB record!
        # if not plate_text or plate_text == "UNREADABLE":
        #     continue

        if deduplicator.is_duplicate(track_id, v.violation_type.name, plate_text):
            print(f"      [OCR Worker] Suppressing duplicate challan for track {track_id} ({v.violation_type.name})")
            continue
            
        print(f"      [OCR Worker] Pushing to API Server: {plate_text if plate_text else 'NOT DETECTED'} (Conf: {ocr_confidence:.2f})")
        send_violation_to_api(v, plate_text, full_evidence_path, plate_confidence=ocr_confidence)

# Start the background thread
ocr_thread = threading.Thread(target=ocr_worker_loop, daemon=True)
ocr_thread.start()

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
    
    # Paths to models
    current_dir = os.path.dirname(os.path.abspath(__file__))
    yolo_path = os.path.join(current_dir, "yolov8n.pt")
    helmet_path = os.path.join(current_dir, "atved_helmet_best.pt")
    seatbelt_path = os.path.join(current_dir, "atved_seatbelt_best.pt")
    plate_path = os.path.join(current_dir, "plate_detector_best.pt")
    
    print("[1/4] Loading YOLOv8 Model...")
    # Load Primary Model (Must be yolov8n to detect vehicles)
    try:
        model = YOLO(yolo_path if os.path.exists(yolo_path) else "yolov8n.pt")
        print("Loaded Primary YOLOv8n Model")
    except Exception as e:
        print(f"Error loading yolov8n.pt: {e}")
        sys.exit(1)

    # Load Specialized Helmet Model (if available)
    try:
        helmet_model = None
        if os.path.exists(helmet_path):
            helmet_model = YOLO(helmet_path)
            print("Loaded specialized Helmet Model")
        elif os.path.exists("atved_helmet_best.pt"):
            helmet_model = YOLO("atved_helmet_best.pt")
            print("Loaded specialized Helmet Model")
        elif os.path.exists("last.pt"):
            helmet_model = YOLO("last.pt")
            print("Loaded 'last.pt' as Helmet Model fallback")
    except Exception as e:
        print(f"Failed to load helmet model: {e}")
        helmet_model = None
        
    # Load Specialized Seatbelt Model
    try:
        seatbelt_model = YOLO(seatbelt_path if os.path.exists(seatbelt_path) else "atved_seatbelt_best.pt")
        print("Loaded specialized Seatbelt Model (Dual-Model Architecture)")
    except Exception as e:
        print(f"Failed to load seatbelt model: {e}")
        seatbelt_model = None

    # Load Specialized Plate Model (V2 - single-class detection model)
    plate_v2_path = os.path.join(current_dir, "plate_detector_v2_best.pt")
    plate_v1_path = os.path.join(current_dir, "plate_detector_best.pt")
    plate_legacy_path = "computer_vision_models/weights/license_plate_detector.pt"
    try:
        if os.path.exists(plate_v2_path):
            plate_model = YOLO(plate_v2_path)
            print(f"Loaded Plate Detector V2 (single-class detection model)")
        elif os.path.exists(plate_v1_path):
            plate_model = YOLO(plate_v1_path)
            print(f"Loaded Plate Detector V1")
        elif os.path.exists(plate_legacy_path):
            plate_model = YOLO(plate_legacy_path)
            print(f"Loaded Legacy Plate Detector")
        else:
            print("WARNING: No plate detector model found!")
            plate_model = None
    except Exception as e:
        print(f"Failed to load plate detector model: {e}")
        plate_model = None

    print("[2/4] Initializing ByteTrack & Violation Registry...")
    settings = get_settings()
    tracker = ObjectTracker()
    registry = ViolationRegistry(settings.violations)
    
    # Configure Speed Detector for Demo
    from atved.db.models import ViolationType
    speed_detector = registry.get_detector(ViolationType.SPEEDING)
    if speed_detector:
        import json
        mock_calib = {
            "homography_matrix": [
                [1/5.0, 0.0, 0.0],
                [0.0, 1/5.0, 0.0],
                [0.0, 0.0, 1.0]
            ],
            "speed_limit_kmh": 40.0
        }
        with open("camera_demo_cam_calib.json", "w") as f:
            json.dump(mock_calib, f)
            
        try:
            speed_detector.load_calibration("demo_cam")
            print("  -> Speed Detection active (mock homography loaded: 5px/m, 40km/h limit)")
        except Exception as e:
            print(f"  -> Failed to load mock speed calibration: {e}")

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
    frame_buffer = {}  # Store recent frames for multi-frame OCR voting
    total_citations = 0
    
    # We want to avoid sending the same violation every single frame for the same track
    reported_tracks = set()
    # We also want to avoid multiple citations for the same vehicle if tracking drops
    
    mock_red_light_enabled = False
    
    from weather_enhancement import WeatherEnhancer
    weather_enhancer = WeatherEnhancer()
    
    # We will occasionally mock a missing seatbelt for demo purposes
    import random

    try:
        cv2.namedWindow("ATVED Live Engine", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("ATVED Live Engine", 1280, 720)
        while True:
            ret, frame = cap.read()
            if not ret:
                print("End of video stream.")
                break

            frame_num += 1
            timestamp = datetime.utcnow()
            
            # Save raw frame for multi-frame OCR
            frame_buffer[frame_num] = frame.copy()
            if len(frame_buffer) > 30:
                del frame_buffer[min(frame_buffer.keys())]

            # Optional: Resize for speed if video is huge
            # frame = cv2.resize(frame, (1280, 720))

            # 0. Apply Weather & CLAHE enhancement to full frame pre-detection
            from clahe_enhancement import auto_tune_clahe
            weather_handled_frame = weather_enhancer.process(frame)
            enhanced_frame = auto_tune_clahe(weather_handled_frame)

            # 1. Detect using Primary Model (Vehicles, Pedestrians, Helmets)
            results = model.predict(enhanced_frame, conf=0.3, verbose=False, device=compute_device)
            
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
                    
            # 1.3 Detect using Specialized Helmet Model
            if helmet_model:
                try:
                    h_results = helmet_model.predict(frame, conf=0.3, verbose=False, device=compute_device)
                    if h_results[0].boxes is not None:
                        for box in h_results[0].boxes:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            cls_id = int(box.cls[0])
                            # The helmet model outputs 'helmet', 'no helmet', etc.
                            class_name = helmet_model.names[cls_id]
                            
                            # Flag unclassified head coverings (hoodies, caps, turbans) as 'no helmet'
                            if class_name not in ['helmet', 'no-helmet', 'no helmet', 'With Helmet', 'Without Helmet']:
                                unclassified_compliance = False
                                class_name = 'no helmet'
                                
                            raw_detections.append(DetectionResult(
                                bbox=(x1, y1, x2, y2),
                                class_name=class_name,
                                class_id=2000 + cls_id, # offset ID to avoid conflict
                                confidence=float(box.conf[0])
                            ))
                except Exception as e:
                    unclassified_compliance = False
                    print(f"Helmet inference exception handled gracefully: {e}")

            # 1.5 Detect using Specialized Seatbelt Model
            if seatbelt_model:
                sb_results = seatbelt_model.predict(frame, conf=0.3, verbose=False)
                if sb_results[0].boxes is not None:
                    for box in sb_results[0].boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        cls_id = int(box.cls[0])
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
            if len(history) > 90:
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
                    
                    print(f"\n  [!] NEW VIOLATION DETECTED! (Frame {frame_num})")
                    print(f"      Type: {v.violation_type.value.upper()} | Track ID: {track_id}")
                    
                    # CRITICAL: Save a CLEAN copy of the raw frame BEFORE draw_frame
                    # draw_frame modifies the frame in-place with bounding boxes and labels.
                    # If we copy AFTER draw_frame, OCR reads "VIOLATION: HELMET!" instead of the plate!
                    raw_frame_copy = frame.copy()
                    
                    # 1. Save annotated evidence image for human review
                    annotated_evidence = draw_frame(frame.copy(), tracked_detections, [v], frame_num)
                    evidence_path = os.path.join(output_dir, f"violation_{track_id}_{frame_num}.jpg")
                    cv2.imwrite(evidence_path, annotated_evidence)
                    print(f"      Evidence Saved: {evidence_path}")
                    
                    # 2. Extract Plate from Vehicle BBox
                    plate_text = None
                    if plate_model and OCR_READER:

                            # Instead of blocking the video loop to process 30 frames,
                            # we package the historical frames and push them to the background OCR worker thread!
                            
                            def extract_crop(img, det):
                                v_bbox = [int(c) for c in det.bbox]
                                vx1, vy1, vx2, vy2 = v_bbox
                                vy1, vy2 = max(0, vy1), min(img.shape[0], vy2)
                                vx1, vx2 = max(0, vx1), min(img.shape[1], vx2)
                                return img[vy1:vy2, vx1:vx2].copy()

                            frames_to_check = []
                            frames_to_check.append(extract_crop(raw_frame_copy, v.detections[0]))
                            
                            # For ALPR, we must track the VEHICLE (motorcycle), not the rider!
                            alpr_track_id = v.evidence_signals.get('motorcycle_track_id') or getattr(v.detections[0], 'track_id', None)
                            
                            if alpr_track_id:
                                for h_frame_data in reversed(history):
                                    if len(frames_to_check) >= 30:
                                        break
                                    for det in h_frame_data.detections:
                                        if getattr(det, 'track_id', None) == alpr_track_id:
                                            old_frame = frame_buffer.get(h_frame_data.frame_index)
                                            if old_frame is not None:
                                                frames_to_check.append(extract_crop(old_frame, det))
                                            break
                            
                            print(f"      [ALPR Queue] Pushing job for Track ID {track_id} (ALPR Target: {alpr_track_id}) (History: {len(frames_to_check)} frames)")
                            ocr_queue.put({
                                'track_id': track_id,
                                'frame_num': frame_num,
                                'violation': v,
                                'frames_to_check': frames_to_check,
                                'plate_model': plate_model,
                                'evidence_path': evidence_path,
                                'compute_device': compute_device,
                                'full_evidence_path': evidence_path
                            })

            # 5. Show live video feed
            annotated = draw_frame(frame, tracked_detections, violations, frame_num)
            
            # Draw the stop line
            line_color = (0, 0, 255) if mock_red_light_enabled else (0, 255, 0)
            cv2.line(annotated, (0, STOP_LINE_Y), (annotated.shape[1], STOP_LINE_Y), line_color, 2)
            
            # Draw instructions
            cv2.putText(annotated, f"Red Light (Press 'r'): {'ON' if mock_red_light_enabled else 'OFF'}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, line_color, 2)
            
            cv2.imshow("ATVED Live Engine", annotated)
            
            # Press 'q' to quit, 'r' to toggle red light
            key = cv2.waitKey(1) & 0xFF
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
        print(f"\n  Waiting for background OCR worker to finish processing...")
        ocr_queue.put(None)
        ocr_thread.join(timeout=30)
        print(f"\n  Total unique citations issued to API : {total_citations}")
        print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
