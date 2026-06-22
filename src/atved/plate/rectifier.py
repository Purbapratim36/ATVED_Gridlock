"""
Perspective rectification for license-plate crops.

Attempts contour-based corner detection, falls back to Hough-line
intersection, and ultimately returns the original crop unchanged
if no reliable quadrilateral can be found.
"""

from __future__ import annotations

import cv2
import numpy as np
import structlog

log = structlog.get_logger(__name__)

# Target aspect ratio for a standard rectangular plate.
_TARGET_ASPECT = 4.5
_TARGET_HEIGHT = 80
_TARGET_WIDTH = int(_TARGET_HEIGHT * _TARGET_ASPECT)


class PlateRectifier:
    """Rectify a skewed plate crop into a front-facing rectangle."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rectify(self, plate_crop: np.ndarray) -> np.ndarray:
        """Return a perspective-corrected plate image.

        Falls back gracefully to the original *plate_crop* when corner
        detection is unreliable.
        """
        corners = self._detect_corners_contour(plate_crop)
        if corners is None:
            corners = self._detect_corners_hough(plate_crop)
        if corners is None:
            log.debug("rectifier.fallback", reason="no_corners_found")
            return plate_crop

        return self._warp(plate_crop, corners)

    # ------------------------------------------------------------------
    # Corner detection strategies
    # ------------------------------------------------------------------

    def _detect_corners_contour(self, image: np.ndarray) -> np.ndarray | None:
        """Find the plate quadrilateral via contour approximation."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)

        # Dilate to close small gaps in the edge map.
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=1)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        # Pick the largest contour by area.
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for cnt in contours[:5]:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
            if len(approx) == 4:
                area = cv2.contourArea(approx)
                frame_area = image.shape[0] * image.shape[1]
                # Reject tiny or frame-filling quads.
                if 0.1 * frame_area < area < 0.98 * frame_area:
                    return self._order_points(approx.reshape(4, 2).astype(np.float32))

        return None

    def _detect_corners_hough(self, image: np.ndarray) -> np.ndarray | None:
        """Derive corners from intersecting Hough lines."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=60)

        if lines is None or len(lines) < 4:
            return None

        # Separate roughly horizontal and vertical lines.
        horizontal: list[tuple[float, float]] = []
        vertical: list[tuple[float, float]] = []

        for rho, theta in lines[:, 0]:
            angle_deg = np.degrees(theta)
            if angle_deg < 30 or angle_deg > 150:
                vertical.append((rho, theta))
            elif 60 < angle_deg < 120:
                horizontal.append((rho, theta))

        if len(horizontal) < 2 or len(vertical) < 2:
            return None

        # Take the extreme lines in each orientation.
        horizontal.sort(key=lambda lt: lt[0])
        vertical.sort(key=lambda lt: lt[0])
        h_lines = [horizontal[0], horizontal[-1]]
        v_lines = [vertical[0], vertical[-1]]

        # Compute intersections.
        corners: list[tuple[float, float]] = []
        for h_rho, h_theta in h_lines:
            for v_rho, v_theta in v_lines:
                pt = self._line_intersection(h_rho, h_theta, v_rho, v_theta)
                if pt is not None:
                    corners.append(pt)

        if len(corners) != 4:
            return None

        pts = np.array(corners, dtype=np.float32)
        h, w = image.shape[:2]
        # Reject if any corner is far outside the image.
        if np.any(pts < -w * 0.2) or np.any(pts[:, 0] > w * 1.2) or np.any(pts[:, 1] > h * 1.2):
            return None

        return self._order_points(pts)

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _line_intersection(
        rho1: float, theta1: float, rho2: float, theta2: float,
    ) -> tuple[float, float] | None:
        """Intersection of two Hough lines in (rho, theta) form."""
        ct1, st1 = np.cos(theta1), np.sin(theta1)
        ct2, st2 = np.cos(theta2), np.sin(theta2)
        det = ct1 * st2 - ct2 * st1
        if abs(det) < 1e-6:
            return None
        x = (st2 * rho1 - st1 * rho2) / det
        y = (ct1 * rho2 - ct2 * rho1) / det
        return (x, y)

    @staticmethod
    def _order_points(pts: np.ndarray) -> np.ndarray:
        """Order four points as: top-left, top-right, bottom-right, bottom-left."""
        ordered = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        d = np.diff(pts, axis=1).ravel()
        ordered[0] = pts[np.argmin(s)]   # top-left
        ordered[2] = pts[np.argmax(s)]   # bottom-right
        ordered[1] = pts[np.argmin(d)]   # top-right
        ordered[3] = pts[np.argmax(d)]   # bottom-left
        return ordered

    @staticmethod
    def _warp(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
        """Perspective-warp *image* so that *corners* map to a rectangle."""
        dst = np.array(
            [[0, 0], [_TARGET_WIDTH, 0], [_TARGET_WIDTH, _TARGET_HEIGHT], [0, _TARGET_HEIGHT]],
            dtype=np.float32,
        )
        matrix = cv2.getPerspectiveTransform(corners, dst)
        warped = cv2.warpPerspective(image, matrix, (_TARGET_WIDTH, _TARGET_HEIGHT))
        log.debug("rectifier.warped", width=_TARGET_WIDTH, height=_TARGET_HEIGHT)
        return warped
