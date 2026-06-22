"""
YOLOv8 detection wrapper for ATVED.

Wraps the Ultralytics YOLO model with production-grade error handling,
coordinate remapping, Prometheus metrics, and structured logging.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import structlog
import torch
from prometheus_client import Histogram
from ultralytics import YOLO

from atved.config import get_settings
from atved.detection import DetectionResult

if TYPE_CHECKING:
    from ultralytics.engine.results import Results

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

DETECTION_INFERENCE_SECONDS = Histogram(
    "atved_detection_inference_seconds",
    "Time spent on YOLOv8 inference per batch (seconds).",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

DETECTIONS_PER_FRAME = Histogram(
    "atved_detections_per_frame",
    "Number of detections returned per frame after confidence and NMS filtering.",
    buckets=(0, 1, 2, 5, 10, 25, 50, 100, 200),
)


class Detector:
    """YOLOv8 object-detection wrapper.

    Loads an Ultralytics YOLO model, runs inference on single frames or
    batches, and maps raw model outputs back to original-image coordinates.

    Parameters
    ----------
    weights_path:
        Override path to ``.pt`` weights file.  Defaults to config value.
    device:
        PyTorch device string (e.g. ``"cuda:0"``).  Defaults to config.
    confidence_threshold:
        Minimum confidence to keep a detection.  Defaults to config.
    nms_threshold:
        IoU threshold for non-maximum suppression.  Defaults to config.
    input_size:
        ``(width, height)`` to which images are resized for inference.
    """

    # ------------------------------------------------------------------
    # Construction & lifecycle
    # ------------------------------------------------------------------

    def __init__(
        self,
        *,
        weights_path: str | Path | None = None,
        device: str | None = None,
        confidence_threshold: float | None = None,
        nms_threshold: float | None = None,
        input_size: tuple[int, int] | None = None,
    ) -> None:
        cfg = get_settings()
        det_cfg = cfg.inference.detection

        self._device = device or cfg.inference.device
        self._conf_thresh = confidence_threshold or det_cfg.confidence_threshold
        self._nms_thresh = nms_threshold or det_cfg.nms_threshold
        self._input_size = input_size or tuple(det_cfg.input_size)
        self._class_names: list[str] = list(det_cfg.classes)

        resolved_weights = str(weights_path or det_cfg.weights_path)

        logger.info(
            "detector.loading_model",
            weights=resolved_weights,
            device=self._device,
            confidence_threshold=self._conf_thresh,
            nms_threshold=self._nms_thresh,
            input_size=self._input_size,
        )

        try:
            self._model = YOLO(resolved_weights)
            self._model.to(self._device)
        except FileNotFoundError:
            logger.error(
                "detector.weights_not_found",
                weights_path=resolved_weights,
            )
            raise
        except Exception:
            logger.exception(
                "detector.model_load_failed",
                weights_path=resolved_weights,
                device=self._device,
            )
            raise

        logger.info("detector.model_loaded", device=self._device)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def warmup(self, *, runs: int = 2) -> None:
        """Run dummy inference to warm up the GPU and JIT compilation.

        Parameters
        ----------
        runs:
            Number of dummy forward passes.
        """
        h, w = self._input_size[1], self._input_size[0]
        dummy = np.zeros((h, w, 3), dtype=np.uint8)

        logger.info("detector.warmup_start", runs=runs, input_size=self._input_size)
        for i in range(runs):
            try:
                self._model.predict(
                    dummy,
                    imgsz=list(self._input_size),
                    conf=self._conf_thresh,
                    iou=self._nms_thresh,
                    verbose=False,
                )
            except RuntimeError as exc:
                logger.warning(
                    "detector.warmup_run_failed",
                    run=i,
                    error=str(exc),
                )
        logger.info("detector.warmup_complete")

    def detect(self, frame: np.ndarray) -> list[DetectionResult]:
        """Run detection on a single frame.

        Parameters
        ----------
        frame:
            BGR image as ``(H, W, 3)`` uint8 numpy array.

        Returns
        -------
        list[DetectionResult]
            Detections with bounding boxes in original-image coordinates.
        """
        batch_results = self.detect_batch([frame])
        return batch_results[0]

    def detect_batch(
        self,
        frames: list[np.ndarray],
    ) -> list[list[DetectionResult]]:
        """Run batched detection on multiple frames.

        Parameters
        ----------
        frames:
            List of BGR images, each ``(H, W, 3)`` uint8 numpy array.
            Frames may have different spatial dimensions — the YOLO model
            handles per-image letterbox resizing internally.

        Returns
        -------
        list[list[DetectionResult]]
            One detection list per input frame, in corresponding order.
        """
        if not frames:
            return []

        t0 = time.perf_counter()
        try:
            results: list[Results] = self._model.predict(
                frames,
                imgsz=list(self._input_size),
                conf=self._conf_thresh,
                iou=self._nms_thresh,
                verbose=False,
            )
        except torch.cuda.OutOfMemoryError:
            logger.error(
                "detector.cuda_oom",
                batch_size=len(frames),
                device=self._device,
            )
            # Attempt recovery: clear cache and fall back to sequential
            torch.cuda.empty_cache()
            return self._detect_sequential_fallback(frames)
        except Exception:
            logger.exception("detector.inference_failed", batch_size=len(frames))
            raise

        elapsed = time.perf_counter() - t0
        DETECTION_INFERENCE_SECONDS.observe(elapsed)

        all_detections: list[list[DetectionResult]] = []
        for result in results:
            frame_dets = self._parse_result(result)
            DETECTIONS_PER_FRAME.observe(len(frame_dets))
            all_detections.append(frame_dets)

        logger.debug(
            "detector.batch_complete",
            batch_size=len(frames),
            total_detections=sum(len(d) for d in all_detections),
            elapsed_ms=round(elapsed * 1000, 2),
        )
        return all_detections

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def class_names(self) -> list[str]:
        """Return the ordered list of class names the model detects."""
        return list(self._class_names)

    @property
    def device(self) -> str:
        """Return the device the model is currently on."""
        return self._device

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_result(self, result: Results) -> list[DetectionResult]:
        """Convert a single Ultralytics Results object into DetectionResults.

        The YOLO model internally letterbox-resizes images and returns
        bounding boxes in the *original* image coordinate space, so no
        manual coordinate remapping is required.
        """
        detections: list[DetectionResult] = []

        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return detections

        # boxes.xyxy  → (N, 4)  float32 in original coords
        # boxes.conf  → (N,)    float32
        # boxes.cls   → (N,)    float32 → int
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        cls_ids = boxes.cls.cpu().numpy().astype(int)

        for bbox_row, conf, cls_id in zip(xyxy, confs, cls_ids):
            # Map model class ID → ATVED class name
            class_name = self._resolve_class_name(int(cls_id))
            if class_name is None:
                # Model produced a class we don't care about — skip
                continue

            detections.append(
                DetectionResult(
                    bbox=(
                        float(bbox_row[0]),
                        float(bbox_row[1]),
                        float(bbox_row[2]),
                        float(bbox_row[3]),
                    ),
                    class_name=class_name,
                    class_id=int(cls_id),
                    confidence=float(conf),
                )
            )

        return detections

    def _resolve_class_name(self, model_cls_id: int) -> str | None:
        """Map a model-output class index to an ATVED class name.

        The Ultralytics model stores its own label map in
        ``self._model.names``.  We first look up the label in the model's
        map, then check whether that label is in our configured class list.

        Returns ``None`` if the class should be ignored (not in config).
        """
        model_names: dict[int, str] = self._model.names  # type: ignore[assignment]
        model_label = model_names.get(model_cls_id, "")
        model_label_lower = model_label.lower().strip()

        # Direct match against ATVED configured classes
        for idx, atved_name in enumerate(self._class_names):
            if atved_name.lower() == model_label_lower:
                return atved_name

        # COCO → ATVED alias mapping (common label remappings)
        _COCO_ALIASES: dict[str, str] = {
            "person": "pedestrian",
            "bicycle": "bicycle",
            "motorbike": "motorcycle",
            "bus": "bus",
            "truck": "truck",
            "car": "car",
        }
        alias = _COCO_ALIASES.get(model_label_lower)
        if alias and alias in self._class_names:
            return alias

        return None

    def _detect_sequential_fallback(
        self,
        frames: list[np.ndarray],
    ) -> list[list[DetectionResult]]:
        """OOM fallback: process frames one-by-one after clearing CUDA cache."""
        logger.warning(
            "detector.sequential_fallback",
            frame_count=len(frames),
        )
        all_detections: list[list[DetectionResult]] = []
        for frame in frames:
            try:
                results: list[Results] = self._model.predict(
                    frame,
                    imgsz=list(self._input_size),
                    conf=self._conf_thresh,
                    iou=self._nms_thresh,
                    verbose=False,
                )
                dets = self._parse_result(results[0])
            except Exception:
                logger.exception("detector.sequential_frame_failed")
                dets = []
            all_detections.append(dets)

        return all_detections
