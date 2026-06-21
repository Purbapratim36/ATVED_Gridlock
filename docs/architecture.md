# ATVED Architecture

## System Boundaries & Constraints
- No real-time tracking across un-flagged trips.
- No facial recognition; faces are blurred dynamically via DNN/Haar models.
- Immutable evidence artifacts stored in S3, metadata mapped in PostgreSQL.

## Pipeline Flow
1. **Ingestion:** Async multi-camera RTSP polling pushes frames into Kafka topic `camera-frames`.
2. **Batch Engine:** `InferenceWorker` consumes topic, batches numpy arrays across cameras to saturate T4 GPUs.
3. **Tracking & Detections:** YOLOv8 detects entities; ByteTrack assigns per-camera spatio-temporal IDs.
4. **Violations Engine:** `ViolationRegistry` feeds tracked history to logic modules (e.g., `helmet.py`, `seatbelt.py`).
5. **Triage:** `UnifiedClassifier` temperature-scales confidences for precision prioritization.
6. **ALPR:** For confirmed candidates, `PlateRecognitionPipeline` runs super-resolution and PaddleOCR.
7. **Storage:** `ViolationService` encrypts plate text; `EvidenceGenerator` links the SHA-256 chain and stores to object storage.
8. **Review:** API exposes `/violations/{id}/review` endpoint strictly to `REVIEWER` roles.
