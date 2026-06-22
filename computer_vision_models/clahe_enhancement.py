import cv2
import numpy as np
import time
import os
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')

def is_clahe_enabled():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = yaml.safe_load(f)
                return config.get('enable_clahe', True)
        except Exception:
            return True
    return True

def auto_tune_clahe(bgr_image):
    """
    Applies CLAHE correctly by converting to LAB color space and
    applying it only to the L (Lightness) channel.
    Dynamically adjusts clip_limit and tile_grid based on image brightness.
    """
    if not is_clahe_enabled() or bgr_image is None or bgr_image.size == 0:
        return bgr_image

    # Convert BGR to LAB
    lab = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    # Determine brightness
    mean_l = np.mean(l_channel)

    if mean_l < 60:
        # Dark crop
        clip_limit = 3.5
        tile_grid = (4, 4)
    elif mean_l > 160:
        # Glare
        clip_limit = 1.0
        tile_grid = (16, 16)
    else:
        # Normal
        clip_limit = 2.0
        tile_grid = (8, 8)

    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
    cl = clahe.apply(l_channel)

    # Merge channels and convert back to BGR
    merged_lab = cv2.merge((cl, a_channel, b_channel))
    enhanced_bgr = cv2.cvtColor(merged_lab, cv2.COLOR_LAB2BGR)

    return enhanced_bgr
