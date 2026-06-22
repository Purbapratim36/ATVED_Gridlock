"""
Face detection and blurring for privacy protection.

Blurs all incidental faces in evidence frames before sealing.
Uses OpenCV's DNN face detector (lightweight, no extra deps)
with Gaussian blur for obfuscation.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class FaceBlur:
    """
    Detects and blurs faces in frames for PII protection.

    Primary detector: OpenCV DNN face detector (Caffe model).
    Fallback: Haar cascade (ships with OpenCV, always available).

    Applies Gaussian blur with a large kernel (51×51) to ensure
    faces are fully unrecognisable.
    """

    BLUR_KERNEL = (51, 51)
    DNN_CONFIDENCE_THRESHOLD = 0.5
    HAAR_SCALE_FACTOR = 1.1
    HAAR_MIN_NEIGHBORS = 5
    HAAR_MIN_SIZE = (30, 30)

    def __init__(
        self,
        dnn_prototxt: str | None = None,
        dnn_model: str | None = None,
    ) -> None:
        self._dnn_net = None
        self._haar_cascade = None

        # Try loading DNN face detector
        if dnn_prototxt and dnn_model:
            if Path(dnn_prototxt).exists() and Path(dnn_model).exists():
                try:
                    self._dnn_net = cv2.dnn.readNetFromCaffe(dnn_prototxt, dnn_model)
                    logger.info("face_blur.dnn_loaded")
                except Exception:
                    logger.warning("face_blur.dnn_load_failed")

        # Fallback: Haar cascade (always available in OpenCV)
        haar_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._haar_cascade = cv2.CascadeClassifier(haar_path)
        if self._haar_cascade.empty():
            logger.warning("face_blur.haar_load_failed")
            self._haar_cascade = None

        if self._dnn_net is None and self._haar_cascade is None:
            logger.error("face_blur.no_detector_available")

    def blur_faces(
        self,
        frame: np.ndarray,
        exclude_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> np.ndarray:
        """
        Detect and blur all faces in the frame.

        Parameters
        ----------
        frame:
            BGR uint8 image.
        exclude_regions:
            Bounding boxes where faces should NOT be blurred
            (reserved for future use).

        Returns
        -------
        Frame with faces blurred.
        """
        faces = self._detect_faces(frame)

        if not faces:
            return frame

        result = frame.copy()
        for x1, y1, x2, y2 in faces:
            # Check exclusion regions
            if exclude_regions and self._is_excluded(
                (x1, y1, x2, y2), exclude_regions
            ):
                continue

            # Clamp to frame bounds
            h, w = result.shape[:2]
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(w, int(x2)), min(h, int(y2))

            if x2 <= x1 or y2 <= y1:
                continue

            roi = result[y1:y2, x1:x2]
            result[y1:y2, x1:x2] = cv2.GaussianBlur(roi, self.BLUR_KERNEL, 30)

        return result

    def _detect_faces(
        self, frame: np.ndarray
    ) -> list[tuple[int, int, int, int]]:
        """Detect faces using the best available detector."""
        if self._dnn_net is not None:
            return self._detect_dnn(frame)
        if self._haar_cascade is not None:
            return self._detect_haar(frame)
        return []

    def _detect_dnn(
        self, frame: np.ndarray
    ) -> list[tuple[int, int, int, int]]:
        """Detect faces using OpenCV DNN."""
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame, 1.0, (300, 300), (104.0, 177.0, 123.0), False, False
        )
        self._dnn_net.setInput(blob)
        detections = self._dnn_net.forward()

        faces = []
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence < self.DNN_CONFIDENCE_THRESHOLD:
                continue
            x1 = int(detections[0, 0, i, 3] * w)
            y1 = int(detections[0, 0, i, 4] * h)
            x2 = int(detections[0, 0, i, 5] * w)
            y2 = int(detections[0, 0, i, 6] * h)
            faces.append((x1, y1, x2, y2))

        return faces

    def _detect_haar(
        self, frame: np.ndarray
    ) -> list[tuple[int, int, int, int]]:
        """Detect faces using Haar cascade (fallback)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rects = self._haar_cascade.detectMultiScale(
            gray,
            scaleFactor=self.HAAR_SCALE_FACTOR,
            minNeighbors=self.HAAR_MIN_NEIGHBORS,
            minSize=self.HAAR_MIN_SIZE,
        )

        faces = []
        for x, y, w, h in rects:
            faces.append((x, y, x + w, y + h))
        return faces

    @staticmethod
    def _is_excluded(
        face: tuple[int, int, int, int],
        exclude_regions: list[tuple[float, float, float, float]],
    ) -> bool:
        """Check if a face bbox is inside any exclusion region."""
        fx1, fy1, fx2, fy2 = face
        face_cx = (fx1 + fx2) / 2
        face_cy = (fy1 + fy2) / 2
        for ex1, ey1, ex2, ey2 in exclude_regions:
            if ex1 <= face_cx <= ex2 and ey1 <= face_cy <= ey2:
                return True
        return False
