"""
ATVED GridLock — Complete API Server

Features:
- Aadhaar + OTP login for citizen portal
- Violation ingestion with automatic fine calculation
- Score-based dynamic fine system
- Simulated bank deduction & SMS notification
- Authority & User dashboard API endpoints
- Camera location data for map integration

Run with:  python api_server.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import json
import uuid
import random
import string
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import List, Optional
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, desc, func, and_

from atved.db.models import (
    Base, Driver, RegisteredPlate, ViolationRecord,
    ViolationType, ViolationStatus, Camera, CameraStatus,
    Appeal, AppealStatus, FineTransaction, OTPSession,
)
from atved.scoring import (
    PENALTY_MATRIX, BASE_FINE_MATRIX,
    calculate_fine, generate_receipt_number, get_score_category,
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = "sqlite+aiosqlite:///atved.db"
engine = create_async_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


import asyncio

# Queue for DB Writes
ingest_queue = asyncio.Queue()

async def ingest_worker():
    while True:
        req = await ingest_queue.get()
        try:
            await process_ingest(req)
        except Exception as e:
            print(f"[DB Write Worker] Error processing ingest: {e}")
        finally:
            ingest_queue.task_done()

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Auto-reset bank balances and traffic scores on server restart for clean demo state
        from sqlalchemy import text
        await conn.execute(text("UPDATE drivers SET bank_balance = 75000.0, traffic_score = 1000"))
    
    worker_task = asyncio.create_task(ingest_worker())
    yield
    worker_task.cancel()
    await engine.dispose()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="ATVED GridLock API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# WebSocket Connection Manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class ViolationIngest(BaseModel):
    camera_external_id: str = "CAM-GHY-001"
    violation_type: str
    confidence_score: float
    vehicle_type: str = "unknown"
    plate_text: str | None = None
    plate_confidence: float | None = None
    detected_at: datetime | None = None
    evidence_image_path: str | None = None


class AadhaarLoginRequest(BaseModel):
    aadhaar_number: str  # e.g. "4832 7651 9023"


class OTPVerifyRequest(BaseModel):
    aadhaar_number: str
    otp: str


class AppealSubmit(BaseModel):
    violation_id: str
    reason: str


class AppealResolve(BaseModel):
    action: str  # "ACCEPT" or "REJECT"
    notes: str


# ===========================================================================
# AUTH ENDPOINTS — Aadhaar + OTP Login
# ===========================================================================

@app.post("/api/v1/auth/aadhaar-login")
async def aadhaar_login(req: AadhaarLoginRequest):
    """
    Step 1: User enters Aadhaar number.
    System looks up the driver, generates OTP, and simulates sending to phone.
    """
    async with SessionLocal() as db:
        driver = (await db.execute(
            select(Driver).where(
                (Driver.aadhaar_number == req.aadhaar_number) | (Driver.phone == req.aadhaar_number)
            )
        )).scalar_one_or_none()

        if not driver:
            raise HTTPException(404, "Aadhaar or Mobile number not found in our system")

        # Generate 6-digit OTP
        otp_code = ''.join(random.choices(string.digits, k=6))
        expires = datetime.now(timezone.utc) + timedelta(minutes=5)

        # Store OTP session
        otp_session = OTPSession(
            aadhaar_number=req.aadhaar_number,
            otp_code=otp_code,
            phone=driver.phone,
            is_verified=False,
            expires_at=expires,
        )
        db.add(otp_session)
        await db.commit()

        # Simulate SMS sending
        masked_phone = f"XXXX-XXX-{driver.phone[-3:]}" if driver.phone else "N/A"
        print(f"\n📱 OTP SMS to {driver.phone}: Your ATVED login OTP is {otp_code}. Valid for 5 minutes.\n")

        return {
            "status": "otp_sent",
            "masked_phone": masked_phone,
            "message": f"OTP sent to {masked_phone}",
            # For demo convenience, include OTP in response (remove in production!)
            "demo_otp": otp_code,
        }


@app.post("/api/v1/auth/verify-otp")
async def verify_otp(req: OTPVerifyRequest):
    """
    Step 2: User enters OTP received on phone.
    If correct, returns driver profile as login session.
    """
    async with SessionLocal() as db:
        # Find latest unexpired OTP for this Aadhaar
        otp_session = (await db.execute(
            select(OTPSession)
            .where(
                OTPSession.aadhaar_number == req.aadhaar_number,
                OTPSession.is_verified == False,
                OTPSession.expires_at > datetime.now(timezone.utc),
            )
            .order_by(desc(OTPSession.created_at))
        )).scalars().first()

        if not otp_session:
            raise HTTPException(400, "No valid OTP session found. Please request a new OTP.")

        if otp_session.otp_code != req.otp:
            raise HTTPException(401, "Invalid OTP. Please try again.")

        # Mark as verified
        otp_session.is_verified = True

        # Get driver profile
        driver = (await db.execute(
            select(Driver).where(
                (Driver.aadhaar_number == req.aadhaar_number) | (Driver.phone == req.aadhaar_number)
            )
        )).scalar_one_or_none()

        plates = [
            p.plate_text
            for p in (await db.execute(
                select(RegisteredPlate).where(RegisteredPlate.driver_id == driver.id)
            )).scalars().all()
        ]

        await db.commit()

        category, _ = get_score_category(driver.traffic_score)

        return {
            "status": "login_success",
            "driver": {
                "id": str(driver.id),
                "name": driver.name,
                "email": driver.email,
                "phone": driver.phone,
                "aadhaar_masked": f"XXXX XXXX {req.aadhaar_number[-4:]}",
                "traffic_score": driver.traffic_score,
                "score_category": category,
                "registered_plates": plates,
                "bank_name": driver.bank_name,
                "bank_account_masked": driver.bank_account_masked,
                "bank_balance": driver.bank_balance,
                "vehicle_make": driver.vehicle_make,
                "vehicle_model": driver.vehicle_model,
                "vehicle_color": driver.vehicle_color,
            }
        }


# ===========================================================================
# INGESTION — Violation from AI Pipeline
# ===========================================================================

@app.post("/api/v1/ingest")
async def ingest_violation(req: ViolationIngest):
    """
    Ingest a violation from the AI detection pipeline.
    Put into the queue so the vision pipeline doesn't block on DB writes.
    """
    await ingest_queue.put(req)
    return {"status": "queued"}

async def process_ingest(req: ViolationIngest):
    """
    Background worker function that handles DB writes.
    """
    async with SessionLocal() as db:
        # Resolve camera
        cam = (await db.execute(
            select(Camera).where(Camera.external_id == req.camera_external_id)
        )).scalar_one_or_none()

        if cam is None:
            cam = Camera(
                external_id=req.camera_external_id,
                location_name="Auto-registered Camera",
                stream_url="auto",
            )
            db.add(cam)
            await db.commit()
            await db.refresh(cam)

        v_type_str = req.violation_type.upper()
        if v_type_str == "NO_HELMET":
            v_type_str = "HELMET"
        
        try:
            vtype = ViolationType(v_type_str)
        except ValueError:
            vtype = ViolationType.SPEEDING # Default fallback if weird string comes in
            
        detected = req.detected_at or datetime.now(timezone.utc)

        # Store plate (simple demo encoding)
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
        await db.flush()

        # ── Tiered Evidence Protocol ──
        evidence_tier = 3 # Tier 3: Visual Only (No plate)
        is_valid_plate = False
        
        if req.plate_text:
            try:
                import sys
                import os
                sys.path.append(os.path.join(os.path.dirname(__file__), 'computer_vision_models'))
                from ocr_preprocessing import is_valid_indian_plate
                is_valid_plate = is_valid_indian_plate(req.plate_text)
            except Exception:
                is_valid_plate = False

            if is_valid_plate and (req.plate_confidence is not None and req.plate_confidence >= 0.70):
                evidence_tier = 1 # Tier 1: Full
            else:
                evidence_tier = 2 # Tier 2: Partial (Unconfirmed)

        # ── Full Fine Processing Flow ──
        fine_result = None
        driver_hit = None
        new_driver_created = False

        if evidence_tier in [1, 2] and req.plate_text:
            # Look up driver (ignoring spaces in the database plate)
            driver_q = select(Driver).join(RegisteredPlate).where(
                func.replace(RegisteredPlate.plate_text, ' ', '') == req.plate_text.replace(' ', '')
            )
            driver_hit = (await db.execute(driver_q)).scalar_one_or_none()

            if not driver_hit:
                import random
                # Pick a random demo user but use the REAL detected plate
                demo_users = [
                    {"name": "Kunaljit Kashyap", "phone": "9678620969", "email": "kunaljit@gridlock.demo"},
                    {"name": "Purba Pratim Mahanta", "phone": "6000605406", "email": "purba@gridlock.demo"},
                    {"name": "Mayur", "phone": "7002870742", "email": "mayur@gridlock.demo"},
                ]
                chosen = random.choice(demo_users)
                print(f"[RTO] Plate '{req.plate_text}' not in DB. Assigning to: {chosen['name']} ({chosen['phone']})")

                # Try to find this demo user in the DB
                driver_hit = (await db.execute(
                    select(Driver).where(Driver.name == chosen["name"])
                )).scalar_one_or_none()

                if not driver_hit:
                    # Demo user doesn't exist yet — create them with phone
                    driver_hit = Driver(
                        name=chosen["name"],
                        email=chosen["email"],
                        phone=chosen["phone"],
                        is_registered=True,
                        traffic_score=1000,
                        bank_balance=50000,
                    )
                    db.add(driver_hit)
                    await db.flush()

                # Register the REAL detected plate to this driver
                new_plate = RegisteredPlate(driver_id=driver_hit.id, plate_text=req.plate_text)
                db.add(new_plate)
                new_driver_created = True

            # Calculate score-based fine
            fine_result = None
            fine_info = calculate_fine(vtype, driver_hit.traffic_score)

            # Deduct score
            penalty = PENALTY_MATRIX.get(vtype, 0)
            old_score = driver_hit.traffic_score
            driver_hit.traffic_score = max(0, driver_hit.traffic_score + penalty)

            # --- Rule 1: Good Samaritan Mitigation Loop ---
            if driver_hit.eligible_for_mitigation:
                fine_info["final_amount"] = fine_info["final_amount"] * 0.90
                driver_hit.eligible_for_mitigation = False
            
            # Simulate bank deduction - Disabled to enforce manual payment workflow
            bank_deducted = False
            # if driver_hit.bank_balance and driver_hit.bank_balance >= fine_info["final_amount"]:
            #     driver_hit.bank_balance -= fine_info["final_amount"]
            #     bank_deducted = True

            # Create fine transaction
            receipt = generate_receipt_number()
            txn = FineTransaction(
                driver_id=driver_hit.id,
                violation_record_id=record.id,
                base_fine=fine_info["base_fine"],
                multiplier=fine_info["multiplier"],
                final_amount=fine_info["final_amount"],
                score_at_time=old_score,
                score_category=fine_info["score_category"],
                bank_deducted=bank_deducted,
                sms_sent=driver_hit.phone is not None,
                receipt_number=receipt,
            )
            db.add(txn)

            fine_result = {
                "base_fine": fine_info["base_fine"],
                "multiplier": fine_info["multiplier"],
                "final_amount": fine_info["final_amount"],
                "score_category": fine_info["score_category"],
                "receipt_number": receipt,
                "bank_deducted": bank_deducted,
                "old_score": old_score,
                "new_score": driver_hit.traffic_score,
            }

        await db.commit()
        await db.refresh(record)

        # Generate E-Challan PDF FIRST (so we can embed the link in the SMS)
        pdf_url = None
        try:
            from fpdf import FPDF
            pdf_path = generate_echallan_pdf(record, driver_hit, req, fine_result)
            pdf_url = f"http://localhost:8000/pdf/{record.id}.pdf"
            print(f"[PDF] E-Challan generated: {pdf_path}")
        except Exception as e:
            print(f"[PDF Error] {e}")

        # --- Rule 2: High-Confidence Automated Dispatch ---
        # Send SMS notification with embedded E-Challan link
        if driver_hit and driver_hit.phone and req.confidence_score >= 0.85:
            challan_link = pdf_url or "https://atved.gov.in/challan"
            sms_body = (
                f"-----------------------------------\n"
                f"  [SMS NOTIFICATION SENT]\n"
                f"-----------------------------------\n"
                f"  To: {driver_hit.phone} ({driver_hit.name})\n"
                f"-----------------------------------\n"
                f"  ATVED Traffic Violation Alert\n"
                f"  \n"
                f"  Dear {driver_hit.name},\n"
                f"  \n"
                f"  A {vtype.value.replace('_',' ').title()} violation has been\n"
                f"  detected on your vehicle ({req.plate_text}).\n"
                f"  \n"
                f"  Fine Amount : Rs. {fine_info['final_amount']:.0f}\n"
                f"  Receipt No  : {receipt}\n"
                f"  Your Score  : {driver_hit.traffic_score}/1000\n"
                f"  Bank Deducted: {'[YES]' if bank_deducted else '[NO]'}\n"
                f"  \n"
                f"  [LINK] View E-Challan: {challan_link}\n"
                f"  \n"
                f"  Pay within 30 days to avoid penalty.\n"
                f"  - ATVED GridLock Authority\n"
                f"-----------------------------------\n"
            )
            try:
                print(f"\n{sms_body}")
            except Exception:
                pass
        elif driver_hit and req.confidence_score < 0.85:
            print(f"[DISPATCH SILENT] Confidence {req.confidence_score:.2f} < 0.85. Suppressed SMS dispatch.")

        # -----------------------------------------------------------------------
        # Broadcast the new violation via WebSocket
        # -----------------------------------------------------------------------
        is_auto = bool(driver_hit and req.confidence_score >= 0.85)
        ws_payload = {
            "time": record.detected_at.strftime("%I:%M %p") if record.detected_at else "Just now",
            "driver": driver_hit.name if driver_hit else f"Owner of {req.plate_text}",
            "score": str(driver_hit.traffic_score) if driver_hit else "N/A",
            "type": vtype.value.upper(),
            "isAuto": is_auto,
        }
        await manager.broadcast(json.dumps(ws_payload))

        return {
            "id": str(record.id),
            "status": "ingested",
            "driver_found": driver_hit is not None,
            "new_driver_created": new_driver_created,
            "fine": fine_result,
        }

# ===========================================================================
# WEBSOCKET ENDPOINTS
# ===========================================================================
@app.websocket("/ws/authority")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


def generate_echallan_pdf(record, driver, req, fine_result):
    """Generate enhanced E-Challan PDF with fine breakdown."""
    import os
    from fpdf import FPDF
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
    pdf.cell(50, 10, "Challan No:", border=1)
    pdf.cell(0, 10, f" {record.id}", border=1, ln=True)
    pdf.cell(50, 10, "Date & Time:", border=1)
    pdf.cell(0, 10, f" {record.detected_at.strftime('%Y-%m-%d %H:%M:%S UTC')}", border=1, ln=True)
    pdf.cell(50, 10, "Location ID:", border=1)
    pdf.cell(0, 10, f" {req.camera_external_id}", border=1, ln=True)
    pdf.cell(50, 10, "Vehicle Plate:", border=1)
    
    # Tiered presentation for plate
    plate_display = req.plate_text if req.plate_text else "NOT DETECTED"
    if req.plate_text:
        try:
            import sys, os
            sys.path.append(os.path.join(os.path.dirname(__file__), 'computer_vision_models'))
            from ocr_preprocessing import is_valid_indian_plate
            if not is_valid_indian_plate(req.plate_text) or (req.plate_confidence and req.plate_confidence < 0.7):
                plate_display += " (UNCONFIRMED)"
        except:
            pass
            
    pdf.cell(0, 10, f" {plate_display}", border=1, ln=True)
    pdf.cell(50, 10, "Owner Name:", border=1)
    pdf.cell(0, 10, f" {driver.name if driver else 'UNREGISTERED'}", border=1, ln=True)

    if driver and driver.phone:
        pdf.cell(50, 10, "Phone:", border=1)
        pdf.cell(0, 10, f" {driver.phone}", border=1, ln=True)

    pdf.ln(5)

    # Violation Info
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(200, 0, 0)
    pdf.cell(0, 10, f"VIOLATION: {req.violation_type}", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 10, f"Confidence Score: {req.confidence_score*100:.1f}%", ln=True)

    # Fine breakdown
    if fine_result:
        pdf.ln(5)
        pdf.set_font("helvetica", "B", 14)
        pdf.cell(0, 10, "FINE BREAKDOWN", ln=True)
        pdf.set_font("helvetica", "", 12)
        pdf.cell(60, 10, "Base Fine:", border=1)
        pdf.cell(0, 10, f" Rs. {fine_result['base_fine']:.0f}", border=1, ln=True)
        pdf.cell(60, 10, "Score Category:", border=1)
        pdf.cell(0, 10, f" {fine_result['score_category']} ({fine_result['multiplier']}x)", border=1, ln=True)
        pdf.cell(60, 10, "Final Amount:", border=1)
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 10, f" Rs. {fine_result['final_amount']:.0f}", border=1, ln=True)
        pdf.set_font("helvetica", "", 12)
        pdf.cell(60, 10, "Receipt:", border=1)
        pdf.cell(0, 10, f" {fine_result['receipt_number']}", border=1, ln=True)
        pdf.cell(60, 10, "Bank Deducted:", border=1)
        pdf.cell(0, 10, f" {'Yes' if fine_result['bank_deducted'] else 'Pending'}", border=1, ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "I", 10)
    pdf.cell(0, 10, "This is a computer-generated document by the ATVED system.", ln=True, align="C")

    # --- ADD IMAGE EVIDENCE HERE ---
    if req.evidence_image_path and os.path.exists(req.evidence_image_path):
        pdf.add_page()
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(0, 10, "VIOLATION EVIDENCE", ln=True, align="C")
        pdf.ln(10)
        # Embed image (max width 190 to fit page)
        pdf.image(req.evidence_image_path, x=10, w=190)

    file_path = f"evidence/challans/{record.id}.pdf"
    pdf.output(file_path)
    return file_path


# ===========================================================================
# DRIVER / USER ENDPOINTS
# ===========================================================================

@app.get("/api/v1/drivers/profile")
async def get_driver_profile(email: str = None, aadhaar: str = None):
    """Get driver profile by email, Aadhaar number, or Phone."""
    async with SessionLocal() as db:
        if aadhaar:
            driver = (await db.execute(
                select(Driver).where(
                    (Driver.aadhaar_number == aadhaar) | (Driver.phone == aadhaar)
                )
            )).scalar_one_or_none()
        elif email:
            driver = (await db.execute(
                select(Driver).where(Driver.email == email)
            )).scalar_one_or_none()
        else:
            raise HTTPException(400, "Provide email or aadhaar parameter")

        if not driver:
            raise HTTPException(404, "Driver not found")

        plates = [
            p.plate_text
            for p in (await db.execute(
                select(RegisteredPlate).where(RegisteredPlate.driver_id == driver.id)
            )).scalars().all()
        ]

        # Get total fines paid
        total_fines = (await db.execute(
            select(func.sum(FineTransaction.final_amount))
            .where(FineTransaction.driver_id == driver.id, FineTransaction.bank_deducted == True)
        )).scalar() or 0

        total_violations = (await db.execute(
            select(func.count(FineTransaction.id))
            .where(FineTransaction.driver_id == driver.id)
        )).scalar() or 0

        category, multiplier = get_score_category(driver.traffic_score)

        return {
            "id": str(driver.id),
            "name": driver.name,
            "email": driver.email,
            "phone": driver.phone,
            "aadhaar_masked": f"XXXX XXXX {driver.aadhaar_number[-4:]}" if driver.aadhaar_number else None,
            "traffic_score": driver.traffic_score,
            "score_category": category,
            "current_multiplier": multiplier,
            "registered_plates": plates,
            "bank_name": driver.bank_name,
            "bank_account_masked": driver.bank_account_masked,
            "bank_balance": driver.bank_balance,
            "vehicle_make": driver.vehicle_make,
            "vehicle_model": driver.vehicle_model,
            "vehicle_color": driver.vehicle_color,
            "total_fines_paid": total_fines,
            "total_violations": total_violations,
        }


@app.get("/api/v1/drivers/violations")
async def get_driver_violations(email: str = None, aadhaar: str = None):
    """Get all violations for a driver."""
    async with SessionLocal() as db:
        if aadhaar:
            driver = (await db.execute(
                select(Driver).where(
                    (Driver.aadhaar_number == aadhaar) | (Driver.phone == aadhaar)
                )
            )).scalar_one_or_none()
        elif email:
            driver = (await db.execute(
                select(Driver).where(Driver.email == email)
            )).scalar_one_or_none()
        else:
            raise HTTPException(400, "Provide email or aadhaar parameter")

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


@app.get("/api/v1/drivers/transactions")
async def get_driver_transactions(email: str = None, aadhaar: str = None):
    """Get fine transaction history for a driver."""
    async with SessionLocal() as db:
        if aadhaar:
            driver = (await db.execute(
                select(Driver).where(
                    (Driver.aadhaar_number == aadhaar) | (Driver.phone == aadhaar)
                )
            )).scalar_one_or_none()
        elif email:
            driver = (await db.execute(
                select(Driver).where(Driver.email == email)
            )).scalar_one_or_none()
        else:
            raise HTTPException(400, "Provide email or aadhaar parameter")

        if not driver:
            raise HTTPException(404, "Driver not found")

        txns = (await db.execute(
            select(FineTransaction)
            .where(FineTransaction.driver_id == driver.id)
            .order_by(desc(FineTransaction.created_at))
        )).scalars().all()

        result = []
        for t in txns:
            # Get the violation type
            v_record = (await db.execute(
                select(ViolationRecord).where(ViolationRecord.id == t.violation_record_id)
            )).scalar_one_or_none()

            result.append({
                "id": str(t.id),
                "receipt_number": t.receipt_number,
                "violation_type": v_record.violation_type.value if v_record else "UNKNOWN",
                "base_fine": t.base_fine,
                "multiplier": t.multiplier,
                "final_amount": t.final_amount,
                "score_at_time": t.score_at_time,
                "score_category": t.score_category,
                "bank_deducted": t.bank_deducted,
                "sms_sent": t.sms_sent,
                "violation_record_id": str(uuid.UUID(str(t.violation_record_id))),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

        return result


# ===========================================================================
# AUTHORITY ENDPOINTS
# ===========================================================================

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

        # Fine revenue stats
        total_revenue = (await db.execute(
            select(func.sum(FineTransaction.final_amount))
            .where(FineTransaction.bank_deducted == True)
        )).scalar() or 0

        total_fines_issued = (await db.execute(
            select(func.count(FineTransaction.id))
        )).scalar() or 0

        pending_collection = (await db.execute(
            select(func.sum(FineTransaction.final_amount))
            .where(FineTransaction.bank_deducted == False)
        )).scalar() or 0

        return {
            "total_violations": total,
            "pending_review": pending,
            "registered_drivers": drivers,
            "by_type": breakdown,
            "total_revenue": total_revenue,
            "total_fines_issued": total_fines_issued,
            "pending_collection": pending_collection or 0,
        }


@app.get("/api/v1/cameras/locations")
async def get_camera_locations():
    """Get all camera locations for map display."""
    async with SessionLocal() as db:
        cameras = (await db.execute(select(Camera))).scalars().all()
        return [
            {
                "id": str(c.id),
                "external_id": c.external_id,
                "location_name": c.location_name,
                "latitude": c.latitude,
                "longitude": c.longitude,
                "status": c.status.value if c.status else "UNKNOWN",
            }
            for c in cameras
            if c.latitude and c.longitude
        ]


@app.get("/api/v1/drivers/all")
async def list_all_drivers():
    """Get all drivers with scores (for authority dashboard)."""
    async with SessionLocal() as db:
        drivers = (await db.execute(
            select(Driver).where(Driver.is_registered == True).order_by(Driver.traffic_score)
        )).scalars().all()

        result = []
        for d in drivers:
            plates = [
                p.plate_text
                for p in (await db.execute(
                    select(RegisteredPlate).where(RegisteredPlate.driver_id == d.id)
                )).scalars().all()
            ]
            category, _ = get_score_category(d.traffic_score)
            result.append({
                "id": str(d.id),
                "name": d.name,
                "phone": d.phone,
                "traffic_score": d.traffic_score,
                "score_category": category,
                "plates": plates,
                "vehicle": f"{d.vehicle_make} {d.vehicle_model}" if d.vehicle_make else "N/A",
            })

        return result


@app.get("/api/v1/transactions/recent")
async def get_recent_transactions():
    """Get recent fine transactions (for authority dashboard)."""
    async with SessionLocal() as db:
        txns = (await db.execute(
            select(FineTransaction).order_by(desc(FineTransaction.created_at)).limit(50)
        )).scalars().all()

        result = []
        for t in txns:
            driver = (await db.execute(
                select(Driver).where(Driver.id == t.driver_id)
            )).scalar_one_or_none()

            v_record = (await db.execute(
                select(ViolationRecord).where(ViolationRecord.id == t.violation_record_id)
            )).scalar_one_or_none()

            result.append({
                "id": str(t.id),
                "receipt": t.receipt_number,
                "driver_name": driver.name if driver else "Unknown",
                "phone": driver.phone if driver else None,
                "violation_type": v_record.violation_type.value if v_record else "UNKNOWN",
                "base_fine": t.base_fine,
                "multiplier": t.multiplier,
                "final_amount": t.final_amount,
                "score_category": t.score_category,
                "bank_deducted": t.bank_deducted,
                "sms_sent": t.sms_sent,
                "violation_record_id": str(t.violation_record_id),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

        return result


@app.get("/api/v1/fines")
async def list_fines():
    """Get all fines with driver and violation details for the authority dashboard."""
    async with SessionLocal() as db:
        txns = (await db.execute(
            select(FineTransaction).order_by(desc(FineTransaction.created_at)).limit(50)
        )).scalars().all()

        result = []
        for t in txns:
            driver = (await db.execute(
                select(Driver).where(Driver.id == t.driver_id)
            )).scalar_one_or_none()

            v_record = (await db.execute(
                select(ViolationRecord).where(ViolationRecord.id == t.violation_record_id)
            )).scalar_one_or_none()

            result.append({
                "id": str(t.id),
                "receipt_number": t.receipt_number,
                "violation_record_id": str(uuid.UUID(str(t.violation_record_id))),
                "driver": {
                    "name": driver.name if driver else "Unknown",
                    "traffic_score": driver.traffic_score if driver else 0,
                } if driver else None,
                "violation": {
                    "violation_type": v_record.violation_type.value if v_record else "UNKNOWN",
                } if v_record else None,
                "base_fine": t.base_fine,
                "multiplier": t.multiplier,
                "final_amount": t.final_amount,
                "score_category": t.score_category,
                "bank_deducted": t.bank_deducted,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

        return result


@app.post("/api/v1/fines/{transaction_id}/pay")
async def pay_fine(transaction_id: str):
    """Manually pay a fine to boost the traffic score."""
    import uuid
    try:
        txn_uuid = uuid.UUID(transaction_id)
    except ValueError:
        raise HTTPException(400, "Invalid transaction ID format")

    async with SessionLocal() as db:
        txn = (await db.execute(
            select(FineTransaction).where(FineTransaction.id == txn_uuid)
        )).scalar_one_or_none()
        
        if not txn:
            raise HTTPException(404, "Transaction not found")
        if txn.bank_deducted:
            raise HTTPException(400, "Fine is already paid")
            
        driver = (await db.execute(
            select(Driver).where(Driver.id == txn.driver_id)
        )).scalar_one_or_none()
        
        if not driver:
            raise HTTPException(404, "Driver not found")
            
        if driver.bank_balance < txn.final_amount:
            raise HTTPException(400, "Insufficient bank balance")
            
        # Deduct balance
        driver.bank_balance -= txn.final_amount
        txn.bank_deducted = True
        
        # Boost Score Workflow: Paying a fine recovers 150 score points
        driver.traffic_score = min(1000, driver.traffic_score + 150)
        
        await db.commit()
        return {"status": "success", "new_score": driver.traffic_score, "balance": driver.bank_balance}


# ===========================================================================
# APPEALS ENDPOINTS
# ===========================================================================

@app.post("/api/v1/appeals")
async def submit_appeal(req: AppealSubmit):
    async with SessionLocal() as db:
        v_record = (await db.execute(
            select(ViolationRecord).where(ViolationRecord.id == req.violation_id)
        )).scalar_one_or_none()
        if not v_record:
            raise HTTPException(404, "Violation not found")

        appeal = Appeal(
            violation_record_id=v_record.id,
            appellant_identifier=b"demo_user",
            reason=req.reason,
            status=AppealStatus.SUBMITTED,
        )
        db.add(appeal)
        v_record.status = ViolationStatus.PENDING_REVIEW
        await db.commit()
        return {"status": "appeal_submitted", "appeal_id": str(appeal.id)}


@app.get("/api/v1/appeals")
async def list_appeals():
    async with SessionLocal() as db:
        appeals = (await db.execute(
            select(Appeal).order_by(Appeal.submitted_at.desc())
        )).scalars().all()
        return [
            {
                "id": str(a.id),
                "violation_id": str(a.violation_record_id),
                "reason": a.reason,
                "status": a.status.value,
                "submitted_at": a.submitted_at,
            }
            for a in appeals
        ]


@app.post("/api/v1/appeals/{appeal_id}/resolve")
async def resolve_appeal(appeal_id: str, req: AppealResolve):
    async with SessionLocal() as db:
        appeal = (await db.execute(
            select(Appeal).where(Appeal.id == appeal_id)
        )).scalar_one_or_none()
        if not appeal:
            raise HTTPException(404, "Appeal not found")

        v_record = (await db.execute(
            select(ViolationRecord).where(ViolationRecord.id == appeal.violation_record_id)
        )).scalar_one_or_none()

        if req.action.upper() == "ACCEPT":
            appeal.status = AppealStatus.OVERTURNED
            if v_record:
                v_record.status = ViolationStatus.DISMISSED

                # Restore fine + points
                if v_record.plate_text_encrypted:
                    plate_text = v_record.plate_text_encrypted.decode('utf-8')
                    driver_q = select(Driver).join(RegisteredPlate).where(
                        RegisteredPlate.plate_text == plate_text
                    )
                    driver = (await db.execute(driver_q)).scalar_one_or_none()
                    if driver:
                        # Restore score
                        penalty = PENALTY_MATRIX.get(v_record.violation_type, 0)
                        driver.traffic_score = min(1000, driver.traffic_score - penalty)

                        # Refund fine
                        txn = (await db.execute(
                            select(FineTransaction).where(
                                FineTransaction.violation_record_id == v_record.id
                            )
                        )).scalar_one_or_none()
                        if txn and txn.bank_deducted:
                            driver.bank_balance += txn.final_amount
                            print(f"💰 Refund of Rs.{txn.final_amount:.0f} to {driver.name}")

        elif req.action.upper() == "REJECT":
            appeal.status = AppealStatus.UPHELD
            if v_record:
                v_record.status = ViolationStatus.CONFIRMED

        appeal.resolution_notes = req.notes
        appeal.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "resolved", "appeal_status": appeal.status.value}


# ===========================================================================
# Static file serving for dashboards
# ===========================================================================

@app.get("/api/v1/cameras")
async def get_cameras():
    """Alias for camera locations for older dashboard compatibility."""
    async with SessionLocal() as db:
        cameras = (await db.execute(select(Camera))).scalars().all()
        return [
            {
                "id": str(c.id),
                "external_id": c.external_id,
                "location_name": c.location_name,
                "latitude": c.latitude,
                "longitude": c.longitude,
                "status": c.status.value if c.status else "UNKNOWN",
            }
            for c in cameras
            if c.latitude and c.longitude
        ]

@app.get("/api/v1/fines")
async def list_fines():
    """Get all fines with driver and violation details for the authority dashboard."""
    async with SessionLocal() as db:
        txns = (await db.execute(
            select(FineTransaction).order_by(desc(FineTransaction.created_at)).limit(50)
        )).scalars().all()

        result = []
        for t in txns:
            driver = (await db.execute(
                select(Driver).where(Driver.id == t.driver_id)
            )).scalar_one_or_none()

            v_record = (await db.execute(
                select(ViolationRecord).where(ViolationRecord.id == t.violation_record_id)
            )).scalar_one_or_none()

            result.append({
                "id": str(t.id),
                "receipt_number": t.receipt_number,
                "violation_record_id": str(t.violation_record_id),
                "driver": {
                    "name": driver.name if driver else "Unknown",
                    "traffic_score": driver.traffic_score if driver else 0,
                } if driver else None,
                "violation": {
                    "violation_type": v_record.violation_type.value if v_record else "UNKNOWN",
                } if v_record else None,
                "base_fine": t.base_fine,
                "multiplier": t.multiplier,
                "final_amount": t.final_amount,
                "score_category": t.score_category,
                "bank_deducted": t.bank_deducted,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

        return result


dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard")

@app.get("/user")
async def serve_user_dashboard():
    return FileResponse(os.path.join(dashboard_dir, "index.html"))

@app.get("/authority")
async def serve_authority_dashboard():
    return FileResponse(os.path.join(dashboard_dir, "authority.html"))

app.mount("/css", StaticFiles(directory=os.path.join(dashboard_dir, "css")), name="dashboard-css")
app.mount("/js", StaticFiles(directory=os.path.join(dashboard_dir, "js")), name="dashboard-js")

# Mount the evidence directory to serve generated PDFs
os.makedirs("evidence/challans", exist_ok=True)
app.mount("/pdf", StaticFiles(directory="evidence/challans"), name="challans-pdf")

if __name__ == "__main__":
    print("=" * 60)
    print("  ATVED GridLock — API Server v1.0")
    print("  User Dashboard:      http://localhost:8000/user")
    print("  Authority Dashboard: http://localhost:8000/authority")
    print("  API Docs:            http://localhost:8000/docs")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)

