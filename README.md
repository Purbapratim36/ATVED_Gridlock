# ATVED: AI Traffic Enforcement Platform

Production-grade CV system for automated traffic violation detection.

## Key Features
- **Human-in-the-Loop:** Strict workflow requiring manual review prior to citation.
- **Privacy First:** Automatic PII redaction and AES-256 field encryption.
- **Evidentiary Integrity:** Hash-sealed chain of custody for all violation records.
- **Multi-Camera Scale:** Asynchronous Kafka-backed pipeline running batched YOLOv8 inference.

## Quickstart (Development)

```bash
docker-compose up -d db redis kafka
uvicorn src.atved.api.main:create_app --reload
```

## Documentation
- [Architecture Details](docs/architecture.md)
- [Operational Runbook](docs/runbook.md)
