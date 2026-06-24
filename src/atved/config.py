"""
Configuration management for ATVED.

Loads YAML configuration with environment-specific overrides and env var substitution.
Uses a layered approach: base.yaml → {environment}.yaml → environment variables.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# Helpers

def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base*, returning a new dict."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning empty dict if it doesn't exist."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# Pydantic sub-models (typed config sections)

class AppConfig(BaseModel):
    name: str = "ATVED"
    version: str = "0.1.0"
    description: str = ""
    debug: bool = False
    log_level: str = "INFO"
    timezone: str = "UTC"


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    cors_origins: list[str] = Field(default_factory=list)


class DatabaseConfig(BaseModel):
    host: str = "localhost"
    port: int = 5432
    name: str = "atved"
    user: str = "atved"
    password: str = ""
    pool_size: int = 20
    max_overflow: int = 10
    echo: bool = False
    ssl_mode: str = "prefer"

    @property
    def async_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @property
    def sync_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class RedisConfig(BaseModel):
    url: str = "redis://localhost:6379/0"
    max_connections: int = 50


class KafkaTopicsConfig(BaseModel):
    frames: str = "camera-frames"
    violations: str = "violation-events"
    evidence: str = "evidence-records"
    alerts: str = "system-alerts"


class KafkaConfig(BaseModel):
    bootstrap_servers: str = "localhost:9092"
    topics: KafkaTopicsConfig = Field(default_factory=KafkaTopicsConfig)
    consumer_group: str = "inference-workers"
    max_poll_records: int = 50
    session_timeout_ms: int = 30000
    heartbeat_interval_ms: int = 10000


class StorageEncryptionConfig(BaseModel):
    enabled: bool = True
    algorithm: str = "AES-256-GCM"


class StorageBucketsConfig(BaseModel):
    evidence: str = "atved-evidence"
    raw_frames: str = "atved-raw-frames"
    models: str = "atved-models"


class StorageConfig(BaseModel):
    backend: str = "s3"
    endpoint: str = "http://localhost:9000"
    access_key: str = ""
    secret_key: str = ""
    region: str = "us-east-1"
    buckets: StorageBucketsConfig = Field(default_factory=StorageBucketsConfig)
    encryption: StorageEncryptionConfig = Field(default_factory=StorageEncryptionConfig)


class DetectionConfig(BaseModel):
    model: str = "yolov8l"
    weights_path: str = "models/detection/yolov8l.pt"
    confidence_threshold: float = 0.5
    nms_threshold: float = 0.45
    input_size: list[int] = Field(default_factory=lambda: [640, 640])
    classes: list[str] = Field(default_factory=lambda: [
        "car", "motorcycle", "bus", "truck", "van",
        "auto_rickshaw", "bicycle", "pedestrian", "rider", "driver",
    ])


class TrackingConfig(BaseModel):
    algorithm: str = "bytetrack"
    track_thresh: float = 0.5
    track_buffer: int = 30
    match_thresh: float = 0.8
    frame_rate: int = 5


class InferenceConfig(BaseModel):
    device: str = "cuda:0"
    batch_size: int = 16
    num_workers: int = 4
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)


class ViolationModuleConfig(BaseModel):
    enabled: bool = True
    min_confidence: float = 0.75
    min_consecutive_frames: int = 3
    min_visibility_score: float | None = None
    max_riders_threshold: int | None = None
    direction_deviation_degrees: float | None = None
    min_duration_seconds: float | None = None
    grace_period_ms: int | None = None
    signal_confirm_frames: int | None = None
    right_turn_on_red_allowed: bool | None = None
    violation_threshold_seconds: int | None = None
    congestion_filter: bool | None = None


class ViolationsConfig(BaseModel):
    helmet: ViolationModuleConfig = Field(default_factory=ViolationModuleConfig)
    seatbelt: ViolationModuleConfig = Field(default_factory=ViolationModuleConfig)
    triple_riding: ViolationModuleConfig = Field(default_factory=ViolationModuleConfig)
    wrong_side: ViolationModuleConfig = Field(default_factory=ViolationModuleConfig)
    stop_line: ViolationModuleConfig = Field(default_factory=ViolationModuleConfig)
    red_light: ViolationModuleConfig = Field(default_factory=ViolationModuleConfig)
    illegal_parking: ViolationModuleConfig = Field(default_factory=ViolationModuleConfig)
    speed: ViolationModuleConfig = Field(default_factory=ViolationModuleConfig)


class PlateDetectorConfig(BaseModel):
    weights_path: str = "models/plate_ocr/plate_detector.pt"
    confidence_threshold: float = 0.6


class PlateOCRConfig(BaseModel):
    engine: str = "paddleocr"
    lang: str = "en"
    use_gpu: bool = True


class PlateSuperResConfig(BaseModel):
    enabled: bool = True
    min_plate_width_px: int = 64
    model: str = "real_esrgan_x2"


class PlateFormatConfig(BaseModel):
    patterns: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class PlatePostCorrectionConfig(BaseModel):
    jurisdiction: str = "IN"
    plate_formats: dict[str, PlateFormatConfig] = Field(default_factory=dict)


class PlateRecognitionConfig(BaseModel):
    detector: PlateDetectorConfig = Field(default_factory=PlateDetectorConfig)
    ocr: PlateOCRConfig = Field(default_factory=PlateOCRConfig)
    super_resolution: PlateSuperResConfig = Field(default_factory=PlateSuperResConfig)
    post_correction: PlatePostCorrectionConfig = Field(default_factory=PlatePostCorrectionConfig)


class TamperDetectionConfig(BaseModel):
    enabled: bool = True
    check_every_nth_frame: int = 10
    tamper_threshold: float = 0.8
    consecutive_checks_for_alert: int = 3


class CameraHealthConfig(BaseModel):
    timeout_seconds: int = 30
    degraded_decode_error_rate: float = 0.10
    degraded_frame_drop_rate: float = 0.20


class CameraConfig(BaseModel):
    max_concurrent: int = 200
    frame_rate_target: int = 5
    max_buffer_frames: int = 30
    health_check_interval_seconds: int = 10
    tamper_detection: TamperDetectionConfig = Field(default_factory=TamperDetectionConfig)
    heartbeat: CameraHealthConfig = Field(default_factory=CameraHealthConfig)


class ConfidenceTriageConfig(BaseModel):
    auto_queue_threshold: float = 0.95
    standard_threshold: float = 0.80
    low_priority_threshold: float = 0.60
    discard_threshold: float = 0.60


class EvidenceConfig(BaseModel):
    hash_algorithm: str = "sha256"
    seal_type: str = "append_only_log"
    confidence_triage: ConfidenceTriageConfig = Field(default_factory=ConfidenceTriageConfig)


class ComplianceConfig(BaseModel):
    legal_basis: str = "legitimate_interest"
    jurisdiction: str = "IN"


class RetentionConfig(BaseModel):
    violation_evidence_days: int = 365
    non_violation_hours: int = 72
    raw_buffer_hours: int = 24
    audit_log_years: int = 7
    pii_access_log_years: int = 7
    cleanup_interval_minutes: int = 60


class AppealsConfig(BaseModel):
    window_days: int = 30
    max_escalation_levels: int = 2


class AuthConfig(BaseModel):
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60
    password_hash_scheme: str = "bcrypt"
    mfa_required_for_admin: bool = True


class MetricsConfig(BaseModel):
    enabled: bool = True
    port: int = 9090


class TracingConfig(BaseModel):
    enabled: bool = True
    endpoint: str = "http://localhost:4317"
    sample_rate: float = 0.1


class LoggingConfig(BaseModel):
    format: str = "json"
    correlation_id: bool = True


class ObservabilityConfig(BaseModel):
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


# Root settings

class Settings(BaseSettings):
    """
    Root configuration object.

    Loads from: base.yaml → {env}.yaml → environment variables (prefix ATVED_).
    """

    app: AppConfig = Field(default_factory=AppConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    kafka: KafkaConfig = Field(default_factory=KafkaConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    violations: ViolationsConfig = Field(default_factory=ViolationsConfig)
    plate_recognition: PlateRecognitionConfig = Field(default_factory=PlateRecognitionConfig)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    evidence: EvidenceConfig = Field(default_factory=EvidenceConfig)
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    appeals: AppealsConfig = Field(default_factory=AppealsConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    model_config = {"env_prefix": "ATVED_", "env_nested_delimiter": "__"}


# Loader

def load_settings(
    config_dir: str | Path | None = None,
    env: str | None = None,
) -> Settings:
    """
    Build a Settings instance from YAML + env overrides.

    Parameters
    ----------
    config_dir:
        Directory containing base.yaml and environment overlays.
        Defaults to ``<project_root>/config``.
    env:
        Environment name (development / staging / production).
        Defaults to ``ATVED_ENV`` env var, then ``development``.
    """
    if config_dir is None:
        # Walk up from this file to find the config dir at project root
        project_root = Path(__file__).resolve().parent.parent.parent
        config_dir = project_root / "config"
    else:
        config_dir = Path(config_dir)

    if env is None:
        env = os.getenv("ATVED_ENV", "development")

    # Layer 1: base config
    base = _load_yaml(config_dir / "base.yaml")

    # Layer 2: environment overlay
    env_overlay = _load_yaml(config_dir / f"{env}.yaml")
    merged = _deep_merge(base, env_overlay)

    # Layer 3: environment variable overrides are handled by pydantic-settings
    # We pass the YAML dict as initial values
    return Settings(**merged)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton accessor for Settings. Call this from dependency injection."""
    return load_settings()
