"""
ATVED Lightweight API Server for the Dashboard Demo.

This is a standalone FastAPI server that connects directly to the Docker Compose
PostgreSQL and serves both the Authority and User dashboards.

Run with:  python api_server.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from contextlib import asynccontextmanager
from fpdf import FPDF

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, desc, func

from atved.db.models import (
    Base, Driver, RegisteredPlate, ViolationRecord,
    ViolationType, ViolationStatus, Camera, Appeal, AppealStatus,
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = "postgresql+asyncpg://atved:atved_password@localhost:5432/atved_db"
engine = create_async_engine(DATABASE_URL, connect_args={"ssl": False})
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Scoring penalty matrix
PENALTY_MATRIX = {
    ViolationType.RED_LIGHT:      -50,
    ViolationType.WRONG_SIDE:     -60,
    ViolationType.SPEEDING:       -40,
    ViolationType.TRIPLE_RIDING:  -30,
    ViolationType.SEATBELT:       -20,
    ViolationType.HELMET:         -20,
    ViolationType.ILLEGAL_PARKING:-15,
    ViolationType.STOP_LINE:      -10,
}

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="ATVED Dashboard API", version="0.6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class ViolationIngest(BaseModel):
    camera_external_id: str = "DEMO-CAM-01"
    violation_type: str
    confidence_score: float
    vehicle_type: str = "unknown"
    plate_text: str | None = None
    plate_confidence: float | None = None
    detected_at: datetime | None = None

class DriverResponse(BaseModel):
    id: str
    name: str
    email: Optional[str]
    traffic_score: int
    registered_plates: List[str]

class AppealSubmit(BaseModel):
    violation_id: str
    reason: str

class AppealResolve(BaseModel):
    action: str  # "ACCEPT" or "REJECT"
    notes: str

# ---------------------------------------------------------------------------
# INGESTION endpoints (used by AI pipeline)
# ---------------------------------------------------------------------------
@app.post("/api/v1/ingest")
async def ingest_violation(req: ViolationIngest):
    async with SessionLocal() as db:
        # Resolve camera
        cam = (await db.execute(
            select(Camera).where(Camera.external_id == req.camera_external_id)
        )).scalar_one_or_none()

        if cam is None:
            cam = Camera(
                external_id=req.camera_external_id,
                location_name="Demo Camera",
                stream_url="demo",
            )
            db.add(cam)
            await db.commit()
            await db.refresh(cam)

        vtype = ViolationType(req.violation_type)
        detected = req.detected_at or datetime.now(timezone.utc)

        # Encrypt plate (simple demo: store as UTF-8 bytes)
        enc_plate = req.plate_text.encode("utf-8") if req.plate_text else None

        record = ViolationRecord(
            camera_id=cam.id,
            violation_type=vtype,
            status=ViolationStatus.PENDING_REVIEW,
            confidence_score=req.confidence_score,
            calibrated_confidence=req.confidence_score,
            vehicle_type=req.vehicle_type,
            plate_text_encrypted=enc_plate,
            plate_confidence=req.plate_confidence,
            detected_at=detected,
        )
        db.add(record)

        # Score deduction for registered drivers, and RTO fetch for unregistered
        driver_hit = None
        new_driver_created = False
        if req.plate_text:
            driver_q = select(Driver).join(RegisteredPlate).where(
                RegisteredPlate.plate_text == req.plate_text
            )
            driver_hit = (await db.execute(driver_q)).scalar_one_or_none()
            
            if not driver_hit:
                # Simulate RTO (DMV) lookup for unregistered plate
                # In a real system, this would call an external API
                print(f"[RTO Mock] Fetching details for unregistered plate: {req.plate_text}")
                mock_owner_name = f"Owner of {req.plate_text}"
                
                # Auto-create an unregistered driver profile
                driver_hit = Driver(
                    name=mock_owner_name,
                    email=None,
                    password_hash=None,
                    is_registered=False,
                    traffic_score=1000
                )
                db.add(driver_hit)
                await db.flush() # get driver_hit.id
                
                # Link plate
                new_plate = RegisteredPlate(driver_id=driver_hit.id, plate_text=req.plate_text)
                db.add(new_plate)
                new_driver_created = True
                
            # Apply penalty
            penalty = PENALTY_MATRIX.get(vtype, 0)
            driver_hit.traffic_score = max(0, driver_hit.traffic_score + penalty)

        await db.commit()
        await db.refresh(record)

        # Generate E-Challan PDF
        try:
            pdf_path = generate_echallan_pdf(record, driver_hit, req, penalty if driver_hit else PENALTY_MATRIX.get(vtype, 0))
            print(f"[PDF] E-Challan generated: {pdf_path}")
        except Exception as e:
            print(f"[PDF Error] Failed to generate PDF: {e}")

        return {
            "id": str(record.id),
            "status": "ingested",
            "driver_score_updated": driver_hit is not None,
            "new_driver_created_from_rto": new_driver_created,
            "new_score": driver_hit.traffic_score if driver_hit else None,
        }

# E-Challan PDF Generator
# ---------------------------------------------------------------------------
def generate_echallan_pdf(record, driver, req, penalty):
    os.makedirs("evidence/challans", exist_ok=True)
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font("helvetica", "B", 24)
    pdf.cell(0, 10, "ATVED TRAFFIC POLICE", ln=True, align="C")
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "OFFICIAL E-CHALLAN", ln=True, align="C")
    pdf.ln(10)
    
    # Details
    pdf.set_font("helvetica", "", 12)
    pdf.cell(50, 10, f"Challan No:", border=1); pdf.cell(0, 10, f" {record.id}", border=1, ln=True)
    pdf.cell(50, 10, f"Date & Time:", border=1); pdf.cell(0, 10, f" {record.detected_at.strftime('%Y-%m-%d %H:%M:%S UTC')}", border=1, ln=True)
    pdf.cell(50, 10, f"Location ID:", border=1); pdf.cell(0, 10, f" {req.camera_external_id}", border=1, ln=True)
    pdf.cell(50, 10, f"Vehicle Plate:", border=1); pdf.cell(0, 10, f" {req.plate_text or 'UNKNOWN'}", border=1, ln=True)
    pdf.cell(50, 10, f"Owner Name:", border=1); pdf.cell(0, 10, f" {driver.name if driver else 'UNREGISTERED'}", border=1, ln=True)
    pdf.ln(5)
    
    # Violation Info
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(200, 0, 0)
    pdf.cell(0, 10, f"VIOLATION: {req.violation_type}", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 10, f"Confidence Score: {req.confidence_score*100:.1f}%", ln=True)
    pdf.cell(0, 10, f"Traffic Score Penalty: -{penalty} Points", ln=True)
    
    pdf.ln(20)
    pdf.set_font("helvetica", "I", 10)
    pdf.cell(0, 10, "This is a computer-generated document by the ATVED system.", ln=True, align="C")
    
    file_path = f"evidence/challans/{record.id}.pdf"
    pdf.output(file_path)
    return file_path


# ---------------------------------------------------------------------------
# DRIVER / USER endpoints
# ---------------------------------------------------------------------------
@app.get("/api/v1/drivers/profile")
async def get_driver_profile(email: str):
    async with SessionLocal() as db:
        driver = (await db.execute(
            select(Driver).where(Driver.email == email)
        )).scalar_one_or_none()
        if not driver:
            raise HTTPException(404, "Driver not found")

        plates = [
            p.plate_text
            for p in (await db.execute(
                select(RegisteredPlate).where(RegisteredPlate.driver_id == driver.id)
            )).scalars().all()
        ]

        return {
            "id": str(driver.id),
            "name": driver.name,
            "email": driver.email,
            "traffic_score": driver.traffic_score,
            "registered_plates": plates,
        }


@app.get("/api/v1/drivers/violations")
async def get_driver_violations(email: str):
    async with SessionLocal() as db:
        driver = (await db.execute(
            select(Driver).where(Driver.email == email)
        )).scalar_one_or_none()
        if not driver:
            raise HTTPException(404, "Driver not found")

        plates = [
            p.plate_text
            for p in (await db.execute(
                select(RegisteredPlate).where(RegisteredPlate.driver_id == driver.id)
            )).scalars().all()
        ]
        plate_bytes = [p.encode("utf-8") for p in plates]

        all_v = (await db.execute(
            select(ViolationRecord)
            .where(ViolationRecord.plate_text_encrypted.in_(plate_bytes))
            .order_by(desc(ViolationRecord.detected_at))
        )).scalars().all()

        return [
            {
                "id": str(v.id),
                "type": v.violation_type.value,
                "status": v.status.value,
                "detected_at": v.detected_at.isoformat() if v.detected_at else None,
                "plate": v.plate_text_encrypted.decode("utf-8") if v.plate_text_encrypted else "",
                "confidence": v.confidence_score,
            }
            for v in all_v
        ]


# ---------------------------------------------------------------------------
# AUTHORITY endpoints
# ---------------------------------------------------------------------------
@app.get("/api/v1/violations")
async def list_all_violations():
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(ViolationRecord).order_by(desc(ViolationRecord.detected_at)).limit(200)
        )).scalars().all()

        return [
            {
                "id": str(v.id),
                "type": v.violation_type.value,
                "status": v.status.value,
                "detected_at": v.detected_at.isoformat() if v.detected_at else None,
                "vehicle_type": v.vehicle_type,
                "confidence": v.confidence_score,
                "plate": v.plate_text_encrypted.decode("utf-8") if v.plate_text_encrypted else "N/A",
            }
            for v in rows
        ]


@app.get("/api/v1/stats")
async def get_stats():
    async with SessionLocal() as db:
        total = (await db.execute(select(func.count(ViolationRecord.id)))).scalar() or 0
        pending = (await db.execute(
            select(func.count(ViolationRecord.id))
            .where(ViolationRecord.status == ViolationStatus.PENDING_REVIEW)
        )).scalar() or 0
        drivers = (await db.execute(select(func.count(Driver.id)))).scalar() or 0

        # Breakdown by type
        breakdown = {}
        for vtype in ViolationType:
            count = (await db.execute(
                select(func.count(ViolationRecord.id))
                .where(ViolationRecord.violation_type == vtype)
            )).scalar() or 0
            if count > 0:
                breakdown[vtype.value] = count

        return {
            "total_violations": total,
            "pending_review": pending,
            "registered_drivers": drivers,
            "by_type": breakdown,
        }


# ---------------------------------------------------------------------------
# APPEALS endpoints
# ---------------------------------------------------------------------------

@app.post("/api/v1/appeals")
async def submit_appeal(req: AppealSubmit):
    async with SessionLocal() as db:
        v_record = (await db.execute(select(ViolationRecord).where(ViolationRecord.id == req.violation_id))).scalar_one_or_none()
        if not v_record:
            raise HTTPException(status_code=404, detail="Violation not found")
            
        appeal = Appeal(
            violation_record_id=v_record.id,
            appellant_identifier=b"dummy_encrypted_user",
            reason=req.reason,
            status=AppealStatus.SUBMITTED
        )
        db.add(appeal)
        
        v_record.status = ViolationStatus.PENDING_REVIEW
        await db.commit()
        return {"status": "appeal_submitted", "appeal_id": str(appeal.id)}

@app.get("/api/v1/appeals")
async def list_appeals():
    async with SessionLocal() as db:
        appeals = (await db.execute(select(Appeal).order_by(Appeal.submitted_at.desc()))).scalars().all()
        result = []
        for a in appeals:
            result.append({
                "id": str(a.id),
                "violation_id": str(a.violation_record_id),
                "reason": a.reason,
                "status": a.status.value,
                "submitted_at": a.submitted_at
            })
        return result

@app.post("/api/v1/appeals/{appeal_id}/resolve")
async def resolve_appeal(appeal_id: str, req: AppealResolve):
    async with SessionLocal() as db:
        appeal = (await db.execute(select(Appeal).where(Appeal.id == appeal_id))).scalar_one_or_none()
        if not appeal:
            raise HTTPException(status_code=404, detail="Appeal not found")
            
        v_record = (await db.execute(select(ViolationRecord).where(ViolationRecord.id == appeal.violation_record_id))).scalar_one_or_none()
        
        if req.action.upper() == "ACCEPT":
            appeal.status = AppealStatus.ACCEPTED
            if v_record:
                v_record.status = ViolationStatus.DISMISSED
                
                # Restore points
                if v_record.plate_text_encrypted:
                    plate_text = v_record.plate_text_encrypted.decode('utf-8')
                    driver_q = select(Driver).join(RegisteredPlate).where(RegisteredPlate.plate_text == plate_text)
                    driver = (await db.execute(driver_q)).scalar_one_or_none()
                    if driver:
                        penalty = PENALTY_MATRIX.get(v_record.violation_type, 0)
                        # Penalty is negative, so subtracting it ADDS the points back
                        driver.traffic_score = min(1000, driver.traffic_score - penalty)
                        
        elif req.action.upper() == "REJECT":
            appeal.status = AppealStatus.REJECTED
            if v_record:
                v_record.status = ViolationStatus.CONFIRMED
            
        appeal.resolution_notes = req.notes
        appeal.reviewed_at = datetime.now(timezone.utc)
        
        await db.commit()
        return {"status": "resolved", "appeal_status": appeal.status.value}

# ---------------------------------------------------------------------------
# Static file serving for dashboards
# ---------------------------------------------------------------------------
dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard")
if os.path.isdir(os.path.join(dashboard_dir, "user")):
    app.mount("/user", StaticFiles(directory=os.path.join(dashboard_dir, "user"), html=True), name="user-dashboard")
if os.path.isdir(os.path.join(dashboard_dir, "authority")):
    app.mount("/authority", StaticFiles(directory=os.path.join(dashboard_dir, "authority"), html=True), name="authority-dashboard")


if __name__ == "__main__":
    print("=" * 60)
    print("  ATVED Dashboard API Server")
    print("  User Dashboard:      http://localhost:8000/user")
    print("  Authority Dashboard: http://localhost:8000/authority")
    print("  API Docs:            http://localhost:8000/docs")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
