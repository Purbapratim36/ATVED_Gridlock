"""
ATVED - OCR Preprocessing Module

Standalone, testable functions for license plate image preprocessing
and Indian plate format validation. Used by demo_live_end_to_end.py.
"""

import cv2
import numpy as np
import re

from clahe_enhancement import auto_tune_clahe

def preprocess_plate_for_ocr(plate_crop_bgr):
    """
    Applies advanced preprocessing to a license plate crop to prepare it for OCR.

    Upgraded Pipeline (v2 — Adaptive Local Binarization):
        1. 15% Black Canvas Padding (prevents edge-character clipping)
        2. Cubic Upscale on BGR (preserves color info for CLAHE)
        3. CLAHE (handles uneven lighting/shadows via LAB color space)
        4. Grayscale conversion
        5. Gaussian Blur (denoise)
        6. Adaptive Gaussian Thresholding (preserves character loops: 3, 6, 8, 9)
        7. Morphological Close (fills small gaps in characters)

    Args:
        plate_crop_bgr: BGR image of the cropped license plate region.

    Returns:
        Tuple of (padded_upscaled_bgr, enhanced_gray, adaptive_binary).
        - padded_upscaled_bgr: Un-binarized BGR crop for EasyOCR fallback path
        - enhanced_gray: CLAHE-enhanced grayscale for fast-plate-ocr
        - adaptive_binary: Adaptively binarized image (structurally safe)
        Returns (None, None, None) if the input is invalid.
    """
    if plate_crop_bgr is None or plate_crop_bgr.size == 0:
        return None, None, None

    # 0. Motion Deblur & ESRGAN (existing pipeline step — preserved)
    from motion_deblur import apply_motion_deblur_pipeline
    plate_crop_bgr = apply_motion_deblur_pipeline(plate_crop_bgr)

    # 1. 15% Black Canvas Padding — prevents edge characters from being clipped
    h, w = plate_crop_bgr.shape[:2]
    pad_x = int(w * 0.15)
    pad_y = int(h * 0.15)
    padded = cv2.copyMakeBorder(
        plate_crop_bgr,
        top=pad_y, bottom=pad_y, left=pad_x, right=pad_x,
        borderType=cv2.BORDER_CONSTANT,
        value=(0, 0, 0)
    )

    # 2. Cubic Upscale on BGR (upscale BEFORE grayscale to maximize pixel density)
    ph, pw = padded.shape[:2]
    if ph < 40 or pw < 80:
        scale = max(3, 80 // max(pw, 1))
    else:
        scale = 2
    upscaled_bgr = cv2.resize(padded, (pw * scale, ph * scale), interpolation=cv2.INTER_CUBIC)

    # 3. CLAHE (Adaptive via LAB color space — existing auto_tune_clahe)
    enhanced_bgr = auto_tune_clahe(upscaled_bgr)

    # 4. Grayscale conversion
    enhanced_gray = cv2.cvtColor(enhanced_bgr, cv2.COLOR_BGR2GRAY)

    # 5. Gaussian Blur to remove high-frequency noise
    blurred = cv2.GaussianBlur(enhanced_gray, (3, 3), 0)

    # 6. Adaptive Gaussian Thresholding (replaces global Otsu)
    #    - blockSize=21: Large neighbourhood captures full character strokes on upscaled plates
    #    - C=8: Moderate constant preserves thin loops in 3, 6, 8, 9 without noise artefacts
    #    - ADAPTIVE_THRESH_GAUSSIAN_C: Gaussian weighting preserves character curvature
    adaptive_binary = cv2.adaptiveThreshold(
        blurred,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY,
        blockSize=21,
        C=8
    )

    # 7. Morphological cleanup (close small holes in characters)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    cleaned = cv2.morphologyEx(adaptive_binary, cv2.MORPH_CLOSE, kernel)

    return upscaled_bgr, enhanced_gray, cleaned


def deskew_plate(gray_image, max_angle=15):
    """
    Attempts to correct skew on an angled license plate.

    Uses Hough Line Transform to detect the dominant angle and rotates
    the image to straighten it.

    Args:
        gray_image: Grayscale plate image.
        max_angle: Maximum correction angle in degrees. Ignores larger angles.

    Returns:
        Deskewed grayscale image, or original if no correction needed.
    """
    if gray_image is None or gray_image.size == 0:
        return gray_image

    edges = cv2.Canny(gray_image, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=30)

    if lines is None:
        return gray_image

    # Calculate median angle from detected lines
    angles = []
    for rho, theta in lines[:, 0]:
        angle = (theta * 180 / np.pi) - 90
        if abs(angle) < max_angle:
            angles.append(angle)

    if not angles:
        return gray_image

    median_angle = np.median(angles)
    if abs(median_angle) < 0.5:
        return gray_image  # negligible skew

    h, w = gray_image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(gray_image, M, (w, h),
                              flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    return rotated


def is_valid_indian_plate(text, plate_type='standard'):
    """
    Validates OCR text against common Indian license plate formats based on plate type.
    """
    if not text or len(text) < 6:
        return False

    cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())

    if len(cleaned) < 6 or len(cleaned) > 13:
        return False

    # Temporary plates often start with T or have different formatting
    if plate_type == 'temporary':
        temp_pattern = r'^(T[A-Z0-9]{5,10}|[A-Z]{2}[0-9]{1,2}TC[0-9]{1,4})$'
        if re.match(temp_pattern, cleaned) or re.search(r'TC', cleaned):
            return True

    # Standard / Commercial / EV format: State(2) District(1-2) Series(0-3) Number(1-4)
    strict = r'^([A-Z]{2})[0-9]{1,2}[A-Z]{0,3}[0-9]{1,4}$'
    match = re.match(strict, cleaned)
    if match:
        state_code = match.group(1)
        # Check against valid states to reduce false positives from garbage OCR
        valid_states = {'AP','AR','AS','BR','CG','GA','GJ','HR','HP','JH','KA','KL','MP','MH','MN','ML','MZ','NL','OD','PB','RJ','SK','TN','TS','TR','UP','UK','WB','AN','CH','DN','DD','DL','JK','LA','LD','PY'}
        if state_code in valid_states:
            return True
        # If it matches regex but state code is invalid, it's likely an OCR error
        return False

    # Relaxed for fast-moving blurry plates (only accept if it has a valid state code)
    relaxed = r'^([A-Z]{2})[0-9]{1,2}[A-Z]{0,3}'
    match = re.search(relaxed, cleaned)
    if match:
        state_code = match.group(1)
        valid_states = {'AP','AR','AS','BR','CG','GA','GJ','HR','HP','JH','KA','KL','MP','MH','MN','ML','MZ','NL','OD','PB','RJ','SK','TN','TS','TR','UP','UK','WB','AN','CH','DN','DD','DL','JK','LA','LD','PY'}
        if state_code in valid_states:
            return True

    return False


def clean_ocr_text(text):
    """Strips unwanted characters from OCR output, uppercases."""
    if not text:
        return ""
    return re.sub(r'[^A-Z0-9]', '', text.upper())


def apply_indian_plate_corrections(text):
    """
    Applies common OCR misread corrections specific to Indian plates.

    First 2 chars should be letters (state code):
        0 -> O, 1 -> I, 5 -> S
    Chars 3-4 should be digits (district code):
        O -> 0, I -> 1, S -> 5, B -> 8
    """
    if not text or len(text) < 4:
        return text

    corrected = list(text.upper())

    # State code (positions 0-1): should be letters, and handle common misreads
    letter_map = {'0': 'O', '1': 'I', '5': 'S', '8': 'B'}
    for i in range(min(2, len(corrected))):
        if corrected[i] in letter_map:
            corrected[i] = letter_map[corrected[i]]
            
    # Fix common state code OCR errors (e.g. W instead of M/N)
    if len(corrected) >= 2:
        state = "".join(corrected[:2])
        state_fixes = {
            'WL': 'NL', # NL is Nagaland
            'WJ': 'MH', # MH is Maharashtra
            'N1': 'NL',
            'M1': 'MH',
            '0D': 'OD',
            '0L': 'DL',
            'D1': 'DL',
            'U0': 'UP'
        }
        if state in state_fixes:
            corrected[0], corrected[1] = state_fixes[state][0], state_fixes[state][1]

    # District code (positions 2-3): should be digits
    digit_map = {'O': '0', 'I': '1', 'S': '5', 'B': '8', 'Z': '2', 'G': '6'}
    for i in range(2, min(4, len(corrected))):
        if corrected[i] in digit_map:
            corrected[i] = digit_map[corrected[i]]

    return ''.join(corrected)
