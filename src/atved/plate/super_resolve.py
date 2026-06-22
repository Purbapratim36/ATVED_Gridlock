"""
Super-resolution upscaling for low-resolution plate crops.

Uses Real-ESRGAN x2 model when available, falls back to bicubic
interpolation. Only applied when the plate crop width is below
the configured minimum threshold.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class SuperResolver:
    """
    Upscales low-resolution plate crops to improve OCR accuracy.

    The Real-ESRGAN x2 model produces sharper results than bicubic
    interpolation, especially for text. However, it requires an ONNX
    runtime and the model weights. When unavailable, we fall back to
    cv2.INTER_CUBIC which still helps OCR on tiny plates.
    """

    def __init__(
        self,
        min_width_px: int = 64,
        model_path: str | None = None,
        enabled: bool = True,
    ) -> None:
        self._min_width = min_width_px
        self._enabled = enabled
        self._onnx_session = None

        if enabled and model_path and Path(model_path).exists():
            try:
                import onnxruntime as ort

                self._onnx_session = ort.InferenceSession(
                    model_path,
                    providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
                )
                logger.info(
                    "super_resolve.model_loaded",
                    model_path=model_path,
                    provider=self._onnx_session.get_providers()[0],
                )
            except Exception:
                logger.warning("super_resolve.onnx_load_failed", model_path=model_path)

    def upscale(self, plate_crop: np.ndarray) -> np.ndarray:
        """
        Upscale a plate crop if it's below the minimum width.

        Parameters
        ----------
        plate_crop:
            BGR uint8 image of the cropped license plate.

        Returns
        -------
        Upscaled image (or original if already large enough / disabled).
        """
        if not self._enabled:
            return plate_crop

        h, w = plate_crop.shape[:2]
        if w >= self._min_width:
            return plate_crop

        scale = max(2, int(np.ceil(self._min_width / w)))

        if self._onnx_session is not None:
            try:
                return self._upscale_onnx(plate_crop, scale)
            except Exception:
                logger.warning("super_resolve.onnx_inference_failed_fallback_bicubic")

        return self._upscale_bicubic(plate_crop, scale)

    def _upscale_onnx(self, image: np.ndarray, scale: int) -> np.ndarray:
        """Upscale using the ONNX Real-ESRGAN model."""
        # Prepare input: BGR→RGB, HWC→CHW, float32, normalise to [0,1]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        input_tensor = rgb.astype(np.float32) / 255.0
        input_tensor = np.transpose(input_tensor, (2, 0, 1))
        input_tensor = np.expand_dims(input_tensor, 0)

        input_name = self._onnx_session.get_inputs()[0].name
        output = self._onnx_session.run(None, {input_name: input_tensor})[0]

        # Output: (1, C, H*scale, W*scale) → HWC uint8 BGR
        output = np.squeeze(output, 0)
        output = np.transpose(output, (1, 2, 0))
        output = np.clip(output * 255.0, 0, 255).astype(np.uint8)
        result = cv2.cvtColor(output, cv2.COLOR_RGB2BGR)

        # If model output isn't the right scale, resize to target
        target_h = image.shape[0] * scale
        target_w = image.shape[1] * scale
        if result.shape[0] != target_h or result.shape[1] != target_w:
            result = cv2.resize(result, (target_w, target_h), interpolation=cv2.INTER_CUBIC)

        return result

    def _upscale_bicubic(self, image: np.ndarray, scale: int) -> np.ndarray:
        """Fallback: bicubic interpolation with mild sharpening."""
        h, w = image.shape[:2]
        upscaled = cv2.resize(
            image, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC
        )
        # Light unsharp mask to recover edges
        blurred = cv2.GaussianBlur(upscaled, (0, 0), 3)
        sharpened = cv2.addWeighted(upscaled, 1.5, blurred, -0.5, 0)
        return sharpened
