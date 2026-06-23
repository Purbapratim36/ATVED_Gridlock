"""
Condition-aware Hybrid OCR Pipeline for License Plates.

Implements the 7-stage OCR pipeline with PaddleOCR as primary,
EasyOCR as fallback, and white-canvas padding.
"""

from __future__ import annotations

import re
import cv2
import numpy as np
import structlog
from typing import Tuple

logger = structlog.get_logger(__name__)

STANDARD_PATTERN = r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$'
BH_PATTERN = r'^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$'

class OCRPipeline:
    def __init__(self):
        try:
            from paddleocr import PaddleOCR
            # Disable logger to avoid spamming the console
            self.paddle = PaddleOCR(use_angle_cls=False, lang='en', rec_model='en_PP-OCRv4', show_log=False)
        except ImportError:
            logger.error("PaddleOCR not installed.")
            self.paddle = None

        try:
            import easyocr
            self.easyocr = easyocr.Reader(['en'], gpu=True, verbose=False)
        except ImportError:
            logger.error("EasyOCR not installed.")
            self.easyocr = None

    def preprocess_primary(self, crop: np.ndarray) -> np.ndarray:
        """Condition-aware preprocessing for PaddleOCR."""
        if crop is None or crop.size == 0:
            return crop

        # 1. Padding (White canvas instead of black)
        padded = cv2.copyMakeBorder(crop, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=[255, 255, 255])
        
        # 2. Lanczos4 Upscaling to 300px height
        h, w = padded.shape[:2]
        target_h = 300
        target_w = int((target_h / h) * w)
        upscaled = cv2.resize(padded, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
        
        # 3. Condition-aware CLAHE
        lab = cv2.cvtColor(upscaled, cv2.COLOR_BGR2LAB)
        l_channel, a, b = cv2.split(lab)
        
        mean_brightness = np.mean(l_channel)
        if mean_brightness < 80:
            # Night mode CLAHE (stronger)
            clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        else:
            # Day mode CLAHE (lighter)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            
        cl = clahe.apply(l_channel)
        limg = cv2.merge((cl, a, b))
        enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
        
        # 4. Grayscale and light blur for denoising
        gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        
        return blurred

    def process_plate(self, crop_bgr: np.ndarray) -> Tuple[str | None, str, float]:
        """
        Process the plate crop using the hybrid OCR pipeline.
        Returns: (text, ocr_source, confidence)
        """
        if self.paddle is None or self.easyocr is None:
            raise RuntimeError("OCR models are not initialized properly.")

        # -- PRIMARY STAGE: PaddleOCR --
        preprocessed = self.preprocess_primary(crop_bgr)
        
        paddle_res = self.paddle.ocr(preprocessed, cls=False)
        if paddle_res and paddle_res[0]:
            # Can be multiple lines
            texts = []
            confs = []
            for line in paddle_res[0]:
                text, conf = line[1]
                # Filter out non-alphanumeric chars
                clean_text = re.sub(r'[^A-Z0-9]', '', text.upper())
                if clean_text:
                    texts.append(clean_text)
                    confs.append(conf)
            
            if texts:
                combined_text = "".join(texts)
                avg_conf = sum(confs) / len(confs)
                
                # Sequential Regex Validation
                if re.match(STANDARD_PATTERN, combined_text):
                    logger.debug("ocr.primary.matched_standard", text=combined_text)
                    return combined_text, "primary", avg_conf
                    
                if re.match(BH_PATTERN, combined_text):
                    logger.debug("ocr.primary.matched_bh", text=combined_text)
                    return combined_text, "primary", avg_conf

        # -- FALLBACK STAGE: EasyOCR --
        logger.debug("ocr.fallback_triggered")
        
        # Light preprocessing for EasyOCR
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        
        easy_res = self.easyocr.readtext(
            gray, 
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        )
        
        if easy_res:
            texts = []
            confs = []
            for (bbox, text, conf) in easy_res:
                clean_text = re.sub(r'[^A-Z0-9]', '', text.upper())
                if clean_text:
                    texts.append(clean_text)
                    confs.append(conf)
                    
            if texts:
                combined_text = "".join(texts)
                avg_conf = sum(confs) / len(confs)
                
                # Penalize fallback confidence
                penalized_conf = avg_conf * 0.85
                return combined_text, "fallback", penalized_conf

        return None, "none", 0.0
