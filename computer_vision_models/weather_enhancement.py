import cv2
import numpy as np

class WeatherEnhancer:
    def __init__(self):
        pass

    def detect_weather_condition(self, frame_bgr):
        """
        Detects weather/lighting conditions to apply conditional processing.
        Returns one of: ['fog', 'night', 'rain', 'normal']
        """
        # Downscale for performance (weather is a global property, no need for 720p)
        thumb = cv2.resize(frame_bgr, (256, 144), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(thumb, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:, :, 2]
        mean_v = np.mean(v_channel)
        std_v = np.std(v_channel)

        # 1. Night Detection
        if mean_v < 40:
            return 'night'
            
        # 2. Fog/Haze Detection (Low contrast, grayish)
        if std_v < 30 and mean_v > 80:
            return 'fog'
            
        # 3. Rain Detection (Simplified: vertical edge variance vs horizontal)
        # Convert to 64F for variance calculation to avoid overflow
        v_float = np.float32(v_channel)
        sobel_x = cv2.Sobel(v_float, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(v_float, cv2.CV_32F, 0, 1, ksize=3)
        var_x = np.var(sobel_x)
        var_y = np.var(sobel_y)
        # If strong vertical edges dominate horizontal (rain streaks)
        if var_y > (var_x * 1.5) and var_y > 500:
            return 'rain'
            
        return 'normal'

    def apply_gamma_correction(self, img_bgr, gamma=0.5):
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        return cv2.LUT(img_bgr, table)

    def apply_dehaze_fast(self, img_bgr):
        """Fast approximation of Dark Channel Prior dehaze."""
        # A true DCP algorithm is slow (needs min filtering & guided filter).
        # We use a fast histogram equalization approach on the L channel for speed.
        lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_eq = cv2.equalizeHist(l)
        lab_eq = cv2.merge((l_eq, a, b))
        return cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)

    def apply_rain_filter(self, img_bgr):
        """Removes rain streaks using directional median blur."""
        # Approximate by applying a median blur that is taller than it is wide
        # OpenCV medianBlur only supports square kernels.
        # So we use a custom vertical filter.
        kernel = np.zeros((7, 7), np.float32)
        kernel[:, 3] = 1.0 / 7.0
        return cv2.filter2D(img_bgr, -1, kernel)

    def process(self, frame_bgr):
        condition = self.detect_weather_condition(frame_bgr)
        
        if condition == 'normal':
            return frame_bgr
        elif condition == 'night':
            return self.apply_gamma_correction(frame_bgr, gamma=0.5)
        elif condition == 'fog':
            return self.apply_dehaze_fast(frame_bgr)
        elif condition == 'rain':
            return self.apply_rain_filter(frame_bgr)
            
        return frame_bgr
