"""
Inference worker daemon.

Consumes frames from the Kafka topic, runs the full detection and
violation pipeline, and stores results to the database and S3.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import numpy as np
import cv2
import structlog

# Assume aiokafka is installed
try:
    from aiokafka import AIOKafkaConsumer
except ImportError:
    AIOKafkaConsumer = None

from atved.config import settings
from atved.db.session import async_session_maker
from atved.detection.batch_engine import BatchInferenceEngine, FrameInput
from atved.violations.registry import ViolationRegistry
from atved.violations.classifier import UnifiedClassifier
from atved.plate.pipeline import PlateRecognitionPipeline
from atved.evidence.generator import EvidenceGenerator
from atved.evidence.storage import EvidenceStorage
from atved.services.violation_service import ViolationService

logger = structlog.get_logger(__name__)


class InferenceWorker:
    """
    Main background worker that processes camera frames.
    
    Architecture:
        1. Consume messages from Kafka `camera-frames` topic.
        2. Decode JPEGs into numpy arrays.
        3. Batch cross-camera frames for GPU efficiency.
        4. Run BatchInferenceEngine (detection + tracking).
        5. Pass tracked detections to ViolationRegistry.
        6. Triage candidates with UnifiedClassifier.
        7. Run PlateRecognitionPipeline on high-confidence candidates.
        8. Generate sealed evidence via EvidenceGenerator.
        9. Upload evidence to S3 and save metadata to Postgres.
    """
    
    def __init__(
        self,
        batch_engine: BatchInferenceEngine,
        violation_registry: ViolationRegistry,
        classifier: UnifiedClassifier,
        plate_pipeline: PlateRecognitionPipeline,
        evidence_generator: EvidenceGenerator,
        storage: EvidenceStorage,
    ):
        self.batch_engine = batch_engine
        self.registry = violation_registry
        self.classifier = classifier
        self.plate_pipeline = plate_pipeline
        self.evidence_generator = evidence_generator
        self.storage = storage
        self.violation_service = ViolationService()
        self.consumer = None

    async def start(self):
        """Start the worker loop."""
        if AIOKafkaConsumer is None:
            logger.error("inference_worker.missing_dependency", dep="aiokafka")
            return
            
        logger.info("inference_worker.starting")
        self.batch_engine.warmup()
        
        self.consumer = AIOKafkaConsumer(
            settings.kafka.topics.frames,
            bootstrap_servers=settings.kafka.bootstrap_servers,
            group_id=settings.kafka.consumer_group,
            auto_offset_reset="latest",
        )
        await self.consumer.start()
        
        try:
            await self._run_loop()
        finally:
            await self.consumer.stop()
            
    async def _run_loop(self):
        """Main batching loop."""
        batch = []
        # In a real implementation we would use a proper batching buffer with a timeout
        # For this prototype we process message by message (batch size 1 effectively if not buffering)
        # To truly batch, we'd use asyncio.wait_for on getmany()
        
        async for msg in self.consumer:
            # msg.value contains the JSON encoded FrameMessage
            # We would decode it here
            import json
            import base64
            
            try:
                data = json.loads(msg.value)
                camera_id = data["camera_id"]
                # Decode jpeg
                jpg_bytes = base64.b64decode(data["frame_bytes"])
                frame_arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
                frame = cv2.imdecode(frame_arr, cv2.IMREAD_COLOR)
                
                timestamp = datetime.fromisoformat(data["timestamp"])
                
                # We'll just run it as a batch of 1 for now for simplicity of this stub
                input_frame = FrameInput(camera_id=camera_id, timestamp=timestamp, frame=frame)
                
                # Run inference
                batch_result = self.batch_engine.process_batch([input_frame])
                
                # Check violations
                for fd in batch_result.frame_detections:
                    candidates = self.registry.analyze_all(fd, history=[]) # Note: history needs to be maintained per camera in a real worker
                    
                    if candidates:
                        triaged = self.classifier.classify(candidates)
                        
                        # Process high/standard priority violations
                        for result in triaged:
                            if result.priority in ("high", "standard"):
                                await self._process_violation(result, frame)
                                
            except Exception:
                logger.exception("inference_worker.process_error")

    async def _process_violation(self, triage_result, frame):
        """Process a confirmed violation candidate."""
        candidate = triage_result.candidate
        
        # 1. Try to read plate
        # For full pipeline we need the vehicle bbox. We find the vehicle in the detections.
        plate_text = None
        plate_conf = None
        plate_bbox = None
        
        vehicle_det = next((d for d in candidate.detections if d.class_name in {"car", "motorcycle", "bus", "truck"}), None)
        if vehicle_det:
            plate_result = self.plate_pipeline.recognize(frame, vehicle_det.bbox)
            if plate_result:
                plate_text = plate_result.corrected_text
                plate_conf = plate_result.confidence
                plate_bbox = plate_result.bbox_in_frame
                
        # 2. Database save
        async with async_session_maker() as session:
            record = await self.violation_service.ingest_violation(
                session, triage_result, plate_text, plate_conf
            )
            
            # 3. Generate evidence
            sealed = self.evidence_generator.generate(
                candidate=candidate,
                frames=[frame], # We'd want the history frames here too ideally
                plate_text=plate_text,
                plate_confidence=plate_conf,
                plate_bbox=plate_bbox,
                previous_hash=None # We'd query the DB for the previous hash to maintain chain
            )
            
            # 4. Upload to S3
            # In a real app we'd convert the frames_json to a byte array
            import json
            meta_bytes = json.dumps({
                "metadata": sealed.metadata_json,
                "annotations": sealed.annotations_json,
                "frames": sealed.evidence_frames_json
            }).encode()
            
            # Re-encode frame for upload (in practice EvidenceGenerator should return the byte blobs it created)
            _, jpg = cv2.imencode('.jpg', frame)
            await self.storage.upload_evidence(str(record.id), [jpg.tobytes()], meta_bytes)
            
            await session.commit()
            logger.info("inference_worker.violation_saved", violation_id=str(record.id))
