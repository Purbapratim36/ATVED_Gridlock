import cv2
import numpy as np

class PlateTypeClassifier:
    """
    Classifies Indian License Plates based on color and aspect ratio.
    """
    def __init__(self):
        pass

    def classify(self, plate_bgr):
        """
        Returns a tuple: (is_two_line, plate_color_type)
        is_two_line: bool
        plate_color_type: 'commercial', 'ev', 'standard', 'temporary'
        """
        if plate_bgr is None or plate_bgr.size == 0:
            return False, 'standard'

        h, w = plate_bgr.shape[:2]
        aspect_ratio = h / w

        # Indian motorcycle plates are typically square-ish (aspect ratio > 0.6)
        # Often w/h < 2.0 which means h/w > 0.5
        is_two_line = aspect_ratio > 0.6

        # Color classification using HSV
        hsv = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2HSV)
        
        # Calculate mean Hue and Saturation of the central region
        center_hsv = hsv[int(h*0.2):int(h*0.8), int(w*0.2):int(w*0.8)]
        if center_hsv.size == 0:
            center_hsv = hsv

        median_h = np.median(center_hsv[:, :, 0])
        median_s = np.median(center_hsv[:, :, 1])
        median_v = np.median(center_hsv[:, :, 2])

        # Color thresholds (OpenCV Hue is 0-179)
        # Yellow (Commercial): H 15-45, high S
        # Green (EV): H 45-85, high S
        # Red (Temp): H 0-10 or 160-179, high S
        # White/Standard: low S or high V

        if median_s > 40 and median_v > 60:
            if 15 <= median_h <= 45:
                return is_two_line, 'commercial'
            elif 45 <= median_h <= 85:
                return is_two_line, 'ev'
            elif median_h <= 10 or median_h >= 160:
                return is_two_line, 'temporary'
                
        return is_two_line, 'standard'
