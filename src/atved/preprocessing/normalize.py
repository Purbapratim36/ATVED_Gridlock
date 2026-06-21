"""Frame normalisation and model-input preparation for the ATVED pipeline.

Handles the conversion from raw BGR uint8 camera frames to the format
expected by detection models:

1. **Letterbox resize** — resize the frame so its longest edge matches the
   target dimension, then pad the shorter edge with a neutral colour
   (114, 114, 114 — the YOLO / COCO convention) to reach a square target.
   A ``ResizeMetadata`` record is returned so that downstream code can
   remap bounding-box predictions back to original pixel coordinates.

2. **Normalise** — BGR → RGB, HWC → CHW, uint8 → float32 [0, 1].

3. **Batch** — stack *N* normalised frames into a single (N, C, H, W) array.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ResizeMetadata:
    """Records the geometry of a letterbox resize for coordinate remapping.

    To convert a detection (x, y) in model-input space back to the original
    frame::

        x_orig = (x_model - pad_x) / scale
        y_orig = (y_model - pad_y) / scale

    Attributes
    ----------
    original_size:
        (height, width) of the source frame before resizing.
    scale:
        Uniform scale factor applied during resize.
    pad_x:
        Horizontal (left) padding in pixels added *after* scaling.
    pad_y:
        Vertical (top) padding in pixels added *after* scaling.
    """

    original_size: tuple[int, int]
    scale: float
    pad_x: int
    pad_y: int


# ---------------------------------------------------------------------------
# Normaliser
# ---------------------------------------------------------------------------

class FrameNormalizer:
    """Resize, pad, and normalise frames for model inference.

    Parameters
    ----------
    target_size:
        ``(width, height)`` of the model input tensor.
    pad_color:
        BGR tuple used for letterbox padding.  The YOLO / COCO convention
        is (114, 114, 114).
    """

    def __init__(
        self,
        *,
        target_size: tuple[int, int] = (640, 640),
        pad_color: tuple[int, int, int] = (114, 114, 114),
    ) -> None:
        self._target_w, self._target_h = target_size
        self._pad_color = pad_color

    # ----- Letterbox resize ------------------------------------------------

    def resize_with_pad(
        self,
        frame: np.ndarray,
        target_size: tuple[int, int] | None = None,
    ) -> tuple[np.ndarray, ResizeMetadata]:
        """Resize *frame* with letterbox padding to *target_size*.

        The frame is scaled so that the longest edge fits within the target
        dimensions, then centred padding is added along the shorter edge.

        Parameters
        ----------
        frame:
            BGR uint8 HWC input.
        target_size:
            ``(width, height)`` override.  Uses the instance default when
            ``None``.

        Returns
        -------
        resized:
            Padded BGR uint8 HWC image of exactly ``target_size``.
        metadata:
            ``ResizeMetadata`` needed for coordinate remapping.
        """
        target_w, target_h = target_size or (self._target_w, self._target_h)
        src_h, src_w = frame.shape[:2]

        # Compute the uniform scale factor.
        scale = min(target_w / src_w, target_h / src_h)
        new_w = int(round(src_w * scale))
        new_h = int(round(src_h * scale))

        # Resize using area interpolation for downscaling (avoids aliasing),
        # linear for upscaling (smooth).
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        resized = cv2.resize(frame, (new_w, new_h), interpolation=interp)

        # Compute symmetric padding.
        pad_x = (target_w - new_w) // 2
        pad_y = (target_h - new_h) // 2

        padded = cv2.copyMakeBorder(
            resized,
            top=pad_y,
            bottom=target_h - new_h - pad_y,
            left=pad_x,
            right=target_w - new_w - pad_x,
            borderType=cv2.BORDER_CONSTANT,
            value=self._pad_color,
        )

        metadata = ResizeMetadata(
            original_size=(src_h, src_w),
            scale=scale,
            pad_x=pad_x,
            pad_y=pad_y,
        )

        return padded, metadata

    # ----- Pixel normalisation ---------------------------------------------

    @staticmethod
    def normalize(frame: np.ndarray) -> np.ndarray:
        """Convert a BGR uint8 HWC frame to an RGB float32 CHW array.

        Steps:
        1. BGR → RGB channel reorder.
        2. HWC → CHW transpose.
        3. uint8 [0, 255] → float32 [0.0, 1.0].

        Parameters
        ----------
        frame:
            BGR uint8 HWC input (typically after ``resize_with_pad``).

        Returns
        -------
        np.ndarray
            Float32 array of shape ``(3, H, W)`` with values in [0, 1].
        """
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        chw = np.transpose(rgb, (2, 0, 1))  # HWC → CHW
        return chw.astype(np.float32) / 255.0

    # ----- Batching --------------------------------------------------------

    @staticmethod
    def to_tensor_batch(frames: list[np.ndarray]) -> np.ndarray:
        """Stack normalised CHW frames into a single NCHW batch array.

        Parameters
        ----------
        frames:
            List of float32 CHW arrays (output of ``normalize``).

        Returns
        -------
        np.ndarray
            Float32 array of shape ``(N, C, H, W)``.

        Raises
        ------
        ValueError
            If *frames* is empty.
        """
        if not frames:
            raise ValueError("Cannot create a batch from an empty frame list.")
        return np.stack(frames, axis=0)
