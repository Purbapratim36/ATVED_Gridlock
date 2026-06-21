"""
ATVED Score-Based Dynamic Fine System.

Traffic score ranges from 0 to 1000. More violations → lower score → higher fines.
This creates a deterrent effect: repeat offenders pay exponentially more.
"""

from __future__ import annotations

import uuid
import random
import string
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from atved.db.models import ViolationType, Driver, RegisteredPlate, FineTransaction

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Score Deduction Matrix (points lost per violation)
# ---------------------------------------------------------------------------
PENALTY_MATRIX = {
    ViolationType.RED_LIGHT:       -50,
    ViolationType.WRONG_SIDE:      -60,
    ViolationType.SPEEDING:        -40,
    ViolationType.TRIPLE_RIDING:   -30,
    ViolationType.SEATBELT:        -20,
    ViolationType.HELMET:          -20,
    ViolationType.ILLEGAL_PARKING: -15,
    ViolationType.STOP_LINE:       -10,
}

# ---------------------------------------------------------------------------
# Base Fine Matrix (₹ INR, based on MV Act 2019 rates)
# ---------------------------------------------------------------------------
BASE_FINE_MATRIX = {
    ViolationType.RED_LIGHT:       1000,
    ViolationType.WRONG_SIDE:      1500,
    ViolationType.SPEEDING:        2000,
    ViolationType.TRIPLE_RIDING:   1000,
    ViolationType.SEATBELT:        1000,
    ViolationType.HELMET:          1000,
    ViolationType.ILLEGAL_PARKING: 500,
    ViolationType.STOP_LINE:       500,
}


def get_score_category(score: int) -> tuple[str, float]:
    """
    Returns (category_name, fine_multiplier) based on the driver's traffic score.

    Higher score = better driver = lower fine.
    Lower score = repeat offender = higher fine (deterrent).
    """
    if score >= 800:
        return "Excellent", 1.0
    elif score >= 600:
        return "Good", 1.25
    elif score >= 400:
        return "Average", 1.5
    elif score >= 200:
        return "Poor", 2.0
    else:
        return "Critical", 3.0


def calculate_fine(violation_type: ViolationType, driver_score: int) -> dict:
    """
    Calculate the fine amount based on violation type and driver's current score.

    Returns dict with base_fine, multiplier, final_amount, score_category.
    """
    base_fine = BASE_FINE_MATRIX.get(violation_type, 500)
    category, multiplier = get_score_category(driver_score)
    final_amount = base_fine * multiplier

    return {
        "base_fine": base_fine,
        "multiplier": multiplier,
        "final_amount": final_amount,
        "score_category": category,
    }


def generate_receipt_number() -> str:
    """Generate a unique receipt number like ATVED-2026-A7X3K2."""
    year = datetime.now().year
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ATVED-{year}-{suffix}"


async def process_violation_for_driver(
    db: AsyncSession,
    plate_text: str,
    violation_type: ViolationType,
) -> Driver | None:
    """
    Looks up if a license plate belongs to a registered driver.
    If it does, deduct points from their traffic score based on the penalty matrix.
    Returns the Driver object if one was found and updated, else None.
    """
    # Find the driver who owns this plate
    query = select(Driver).join(RegisteredPlate).where(RegisteredPlate.plate_text == plate_text)
    result = await db.execute(query)
    driver = result.scalar_one_or_none()
    
    if not driver:
        return None
        
    penalty = PENALTY_MATRIX.get(violation_type, 0)
    
    if penalty < 0:
        driver.traffic_score += penalty
        
        # Ensure score doesn't drop below 0
        if driver.traffic_score < 0:
            driver.traffic_score = 0
            
        logger.info(
            "traffic_score.deducted",
            driver_id=str(driver.id),
            driver_name=driver.name,
            plate=plate_text,
            violation=violation_type.value,
            penalty=penalty,
            new_score=driver.traffic_score
        )
        
        await db.commit()
        await db.refresh(driver)
        
    return driver


async def process_full_violation_flow(
    db: AsyncSession,
    plate_text: str,
    violation_type: ViolationType,
    violation_record_id: uuid.UUID,
) -> dict | None:
    """
    Complete violation processing flow:
    1. Look up driver by plate
    2. Deduct score points
    3. Calculate score-based fine
    4. Simulate bank deduction
    5. Create FineTransaction record
    6. Simulate SMS notification

    Returns a dict with all transaction details, or None if plate not found.
    """
    # Find driver
    query = select(Driver).join(RegisteredPlate).where(RegisteredPlate.plate_text == plate_text)
    result = await db.execute(query)
    driver = result.scalar_one_or_none()

    if not driver:
        return None

    # Step 1: Calculate fine BEFORE deducting score (fine is based on current score)
    fine_info = calculate_fine(violation_type, driver.traffic_score)

    # Step 2: Deduct score points
    penalty = PENALTY_MATRIX.get(violation_type, 0)
    old_score = driver.traffic_score
    driver.traffic_score = max(0, driver.traffic_score + penalty)

    # Step 3: Simulate bank deduction
    bank_deducted = False
    if driver.bank_balance and driver.bank_balance >= fine_info["final_amount"]:
        driver.bank_balance -= fine_info["final_amount"]
        bank_deducted = True

    # Step 4: Create FineTransaction
    receipt = generate_receipt_number()
    txn = FineTransaction(
        driver_id=driver.id,
        violation_record_id=violation_record_id,
        base_fine=fine_info["base_fine"],
        multiplier=fine_info["multiplier"],
        final_amount=fine_info["final_amount"],
        score_at_time=old_score,
        score_category=fine_info["score_category"],
        bank_deducted=bank_deducted,
        sms_sent=True,  # Simulated
        receipt_number=receipt,
    )
    db.add(txn)

    await db.commit()
    await db.refresh(driver)
    await db.refresh(txn)

    # Step 5: Log SMS (simulated)
    sms_msg = (
        f"ATVED Traffic Alert: Fine of Rs.{fine_info['final_amount']:.0f} "
        f"deducted from A/C {driver.bank_account_masked or 'N/A'} "
        f"for {violation_type.value} violation. "
        f"Receipt: {receipt}. Score: {driver.traffic_score}/1000. "
        f"Appeal at atved.gov.in"
    )
    logger.info("sms.sent", phone=driver.phone, message=sms_msg)
    print(f"\n📱 SMS to {driver.phone}: {sms_msg}\n")

    return {
        "driver_id": str(driver.id),
        "driver_name": driver.name,
        "phone": driver.phone,
        "old_score": old_score,
        "new_score": driver.traffic_score,
        "penalty_points": abs(penalty),
        "fine": fine_info,
        "receipt_number": receipt,
        "bank_deducted": bank_deducted,
        "bank_balance_remaining": driver.bank_balance,
        "sms_message": sms_msg,
    }
