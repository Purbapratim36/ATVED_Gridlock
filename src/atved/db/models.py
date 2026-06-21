from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    JSON,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CameraStatus(str, enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    TAMPERED = "TAMPERED"

class ViolationType(str, enum.Enum):
    HELMET = "HELMET"
    SEATBELT = "SEATBELT"
    TRIPLE_RIDING = "TRIPLE_RIDING"
    WRONG_SIDE = "WRONG_SIDE"
    STOP_LINE = "STOP_LINE"
    RED_LIGHT = "RED_LIGHT"
    ILLEGAL_PARKING = "ILLEGAL_PARKING"
    SPEEDING = "SPEEDING"

class ViolationStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    UNDER_REVIEW = "UNDER_REVIEW"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"
    APPEALED = "APPEALED"
    APPEAL_RESOLVED = "APPEAL_RESOLVED"
    PROCESSING_RESTRICTED = "PROCESSING_RESTRICTED"

class AuditAction(str, enum.Enum):
    CREATED = "CREATED"
    VIEWED = "VIEWED"
    MODIFIED = "MODIFIED"
    REVIEWED = "REVIEWED"
    APPEALED = "APPEALED"
    EXPORTED = "EXPORTED"
    DELETED = "DELETED"

class ActorType(str, enum.Enum):
    SYSTEM = "SYSTEM"
    STAFF = "STAFF"

class StaffRole(str, enum.Enum):
    CAMERA_OPERATOR = "CAMERA_OPERATOR"
    REVIEWER = "REVIEWER"
    SENIOR_REVIEWER = "SENIOR_REVIEWER"
    ANALYST = "ANALYST"
    DATA_ENGINEER = "DATA_ENGINEER"
    ADMIN = "ADMIN"
    AUDITOR = "AUDITOR"

class AppealStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    UPHELD = "UPHELD"
    OVERTURNED = "OVERTURNED"

class PIIAccessType(str, enum.Enum):
    READ = "READ"
    EXPORT = "EXPORT"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Base for all SQLAlchemy models."""
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=True)
    is_registered: Mapped[bool] = mapped_column(default=False)
    traffic_score: Mapped[int] = mapped_column(Integer, default=1000)

    # Aadhaar & Phone (for login + OTP)
    aadhaar_number: Mapped[str] = mapped_column(String(14), unique=True, index=True, nullable=True)  # Format: XXXX XXXX XXXX
    phone: Mapped[str] = mapped_column(String(15), nullable=True)

    # Bank Details (simulated for demo)
    bank_account_masked: Mapped[str] = mapped_column(String(20), nullable=True)  # e.g. XXXX-XXXX-1234
    bank_name: Mapped[str] = mapped_column(String(100), nullable=True)
    bank_balance: Mapped[float] = mapped_column(Float, default=50000.0, nullable=True)

    # Vehicle Info
    vehicle_make: Mapped[str] = mapped_column(String(50), nullable=True)
    vehicle_model: Mapped[str] = mapped_column(String(50), nullable=True)
    vehicle_color: Mapped[str] = mapped_column(String(30), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    registered_plates = relationship("RegisteredPlate", back_populates="driver")
    fine_transactions = relationship("FineTransaction", back_populates="driver")


class RegisteredPlate(Base):
    __tablename__ = "registered_plates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"), index=True)
    plate_text: Mapped[str] = mapped_column(String(20), unique=True, index=True) # Stored in plaintext for demo simplicity, but could be encrypted
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    driver = relationship("Driver", back_populates="registered_plates")


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[StaffRole] = mapped_column(Enum(StaffRole, name="staff_role_enum"))
    is_active: Mapped[bool] = mapped_column(default=True)
    mfa_enabled: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    reviews = relationship("ViolationRecord", back_populates="reviewer")
    appeals_reviewed = relationship("Appeal", back_populates="reviewer")


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    location_name: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    status: Mapped[CameraStatus] = mapped_column(Enum(CameraStatus, name="camera_status_enum"), default=CameraStatus.OFFLINE)
    stream_url: Mapped[str] = mapped_column(String(1024))
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    installed_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    violations = relationship("ViolationRecord", back_populates="camera")


class ViolationRecord(Base):
    __tablename__ = "violation_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), index=True)
    violation_type: Mapped[ViolationType] = mapped_column(Enum(ViolationType, name="violation_type_enum"), index=True)
    status: Mapped[ViolationStatus] = mapped_column(Enum(ViolationStatus, name="violation_status_enum"), default=ViolationStatus.PENDING_REVIEW, index=True)
    
    confidence_score: Mapped[float] = mapped_column(Float)
    calibrated_confidence: Mapped[float] = mapped_column(Float)
    
    vehicle_type: Mapped[str] = mapped_column(String(50))
    vehicle_color: Mapped[str] = mapped_column(String(50), nullable=True)
    
    # PII Field Level Encryption
    plate_text_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=True, index=True)
    plate_confidence: Mapped[float] = mapped_column(Float, nullable=True)
    
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff.id"), nullable=True)
    reviewed_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_notes: Mapped[str] = mapped_column(Text, nullable=True)
    
    detected_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "(status = 'PENDING_REVIEW') OR (reviewer_id IS NOT NULL)",
            name="check_human_in_loop"
        ),
    )

    # Relationships
    camera = relationship("Camera", back_populates="violations")
    reviewer = relationship("Staff", back_populates="reviews")
    evidence = relationship("Evidence", back_populates="violation_record", uselist=False)
    appeals = relationship("Appeal", back_populates="violation_record")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    violation_record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("violation_records.id"), unique=True)
    
    sha256_hash: Mapped[str] = mapped_column(String(64), unique=True)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    
    evidence_frames_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    annotations_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    sealed_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    violation_record = relationship("ViolationRecord", back_populates="evidence")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction, name="audit_action_enum"))
    actor_type: Mapped[ActorType] = mapped_column(Enum(ActorType, name="actor_type_enum"))
    actor_id: Mapped[str] = mapped_column(String(255))
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=True)
    hash_at_action: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Appeal(Base):
    __tablename__ = "appeals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    violation_record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("violation_records.id"))
    
    appellant_identifier: Mapped[bytes] = mapped_column(LargeBinary) # Encrypted
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[AppealStatus] = mapped_column(Enum(AppealStatus, name="appeal_status_enum"), default=AppealStatus.SUBMITTED)
    
    submitted_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff.id"), nullable=True)
    reviewed_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    violation_record = relationship("ViolationRecord", back_populates="appeals")
    reviewer = relationship("Staff", back_populates="appeals_reviewed")


class PIIAccessLog(Base):
    __tablename__ = "pii_access_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    accessor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff.id"))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    access_type: Mapped[PIIAccessType] = mapped_column(Enum(PIIAccessType, name="pii_access_type_enum"))
    justification: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    accessor = relationship("Staff")


class FineTransaction(Base):
    """Records each fine with score-based dynamic pricing."""
    __tablename__ = "fine_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"), index=True)
    violation_record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("violation_records.id"), index=True)

    base_fine: Mapped[float] = mapped_column(Float)
    multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    final_amount: Mapped[float] = mapped_column(Float)
    score_at_time: Mapped[int] = mapped_column(Integer)
    score_category: Mapped[str] = mapped_column(String(20))  # Excellent/Good/Average/Poor/Critical

    bank_deducted: Mapped[bool] = mapped_column(default=False)
    sms_sent: Mapped[bool] = mapped_column(default=False)
    receipt_number: Mapped[str] = mapped_column(String(30), unique=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    driver = relationship("Driver", back_populates="fine_transactions")
    violation_record = relationship("ViolationRecord")


class OTPSession(Base):
    """Temporary OTP sessions for Aadhaar-based login."""
    __tablename__ = "otp_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aadhaar_number: Mapped[str] = mapped_column(String(14), index=True)
    otp_code: Mapped[str] = mapped_column(String(6))
    phone: Mapped[str] = mapped_column(String(15))
    is_verified: Mapped[bool] = mapped_column(default=False)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
