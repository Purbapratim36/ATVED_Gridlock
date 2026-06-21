from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from atved.db.models import ViolationType, Driver, RegisteredPlate

logger = structlog.get_logger(__name__)

# Deduction Matrix
PENALTY_MATRIX = {
    ViolationType.RED_LIGHT: -50,
    ViolationType.WRONG_SIDE: -60,
    ViolationType.SPEEDING: -40,
    ViolationType.TRIPLE_RIDING: -30,
    ViolationType.SEATBELT: -20,
    ViolationType.HELMET: -20,
    ViolationType.ILLEGAL_PARKING: -15,
    ViolationType.STOP_LINE: -10,
}

async def process_violation_for_driver(
    db: AsyncSession,
    plate_text: str,
    violation_type: ViolationType
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
        # Plate is not registered to anyone; system still logs violation normally
        # but no score deduction happens.
        return None
        
    penalty = PENALTY_MATRIX.get(violation_type, 0)
    
    if penalty < 0:
        old_score = driver.traffic_score
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
