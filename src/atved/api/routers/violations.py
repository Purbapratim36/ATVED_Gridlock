"""
API Router for violation ingestion.
Validates confidence gates, routes to Celery tasks or manual review.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel
# FILE: src/atved/api/routers/violations.py
# DEBUG-FIX: Pydantic schema and route_violation lacked compound routing for readable plates below the primary gate.
import structlog
from typing import Optional

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["violations"])

CONFIDENCE_GATES = {
    "NO_HELMET": {"auto": 0.88, "review": 0.72},
    "TRIPLE_RIDING": {"auto": 0.82, "review": 0.65},
    "SPEEDING": {"auto": 0.90, "review": 0.75},
    "RED_LIGHT": {"auto": 0.93, "review": 0.80}
}

class ViolationIngestRequest(BaseModel):
    camera_external_id: str
    violation_type:     str
    plate_text:         str
    confidence_score:   float
    vehicle_type:       str
    plate_confidence:   float
    ocr_source:         str = "primary"
    evidence_image_path: Optional[str] = None
    ocr_confidence:     float = 0.0   # safe default
    buffer_complete:    bool  = False  # safe default

def route_violation(
    vtype:            str,
    conf_score:       float,
    ocr_source:       str,
    ocr_confidence:   float = 0.0,
    buffer_complete:  bool  = False
) -> str:
    if vtype == "HELMET":
        vtype = "NO_HELMET"  # DEBUG-FIX: Map payload type to CONFIDENCE_GATES key
    elif vtype == "SEATBELT":
        vtype = "NO_SEATBELT"

    # Use .get() with fallback to prevent 500 KeyError if an unknown type is sent
    gate = CONFIDENCE_GATES.get(vtype, {"auto": 0.90, "review": 0.75})

    # PRIMARY PATH — unchanged
    if conf_score >= gate["auto"] and ocr_source == "primary":
        return "AUTO_FINE"

    # COMPOUND PATH — temporal buffer + readable plate compensates
    # for review-zone detection confidence.
    # All three conditions must be simultaneously true:
    #   (a) detection is plausible (above review gate)
    #   (b) temporal buffer fully satisfied (not a single-frame fluke)
    #   (c) plate is clearly readable (high OCR confidence)
    # ocr_source check relaxed for demo video conditions where
    # PaddleOCR may fall back to EasyOCR on motion-blurred frames.
    compound_eligible = (
        conf_score >= gate["review"] and     # (a)
        buffer_complete and                   # (b)
        ocr_confidence >= 0.88               # (c)
    )
    if compound_eligible:
        print(
            f"[COMPOUND AUTO-FINE] {vtype} | "
            f"det={conf_score:.2f} (below auto gate) | "
            f"ocr={ocr_confidence:.2f} | ocr_src={ocr_source} | "
            f"buffer=COMPLETE — compound evidence sufficient"
        )
        return "AUTO_FINE"  # DEBUG-FIX: was routing to HUMAN_REVIEW

    if conf_score >= gate["review"]:
        return "HUMAN_REVIEW"

    return "DISCARD"

@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_violation(request: ViolationIngestRequest, background_tasks: BackgroundTasks):
    """
    Ingest a new violation from the edge pipeline.
    Uses confidence gating to determine routing.
    """
    routing_decision = route_violation(
        request.violation_type.upper().replace(" ", "_"), 
        request.confidence_score, 
        request.ocr_source,
        request.ocr_confidence,
        request.buffer_complete
    )
    
    logger.info(
        "api.ingest.routed", 
        camera=request.camera_external_id, 
        vtype=request.violation_type, 
        decision=routing_decision,
        conf=request.confidence_score,
        ocr_source=request.ocr_source
    )
    
    print(f"[DIAG-2] ROUTE ASSIGNED: plate={request.plate_text} | "
          f"route={routing_decision} | vtype={request.violation_type}")
          
    if routing_decision == "DISCARD":
        return {"status": "discarded", "reason": "Confidence below review threshold"}
        
    elif routing_decision == "HUMAN_REVIEW":
        # Save to DB for review (mock implementation for demo)
        return {"status": "queued_for_review", "reason": "Requires human confirmation"}
        
    elif routing_decision == "AUTO_FINE":
        # Dispatch Celery task
        try:
            from atved.tasks.challan_tasks import generate_and_dispatch_challan
            import uuid
            import random
            import string
            
            # Generate custom ID: ATVED12345A1h
            random_digits = ''.join(random.choices(string.digits, k=5))
            random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=3))
            challan_id = f"ATVED{random_digits}{random_suffix}"
            
            print(f"[DIAG-3] CELERY DISPATCH CALLED: challan_id={challan_id}")
            generate_and_dispatch_challan.delay(
                challan_id=challan_id,
                plate_text=request.plate_text,
                violation_type=request.violation_type,
                evidence_path=request.evidence_image_path
            )
            return {"status": "auto_fined", "reason": "High confidence, dispatched challan task"}
        except ImportError:
            logger.warning("api.ingest.no_celery_task_found")
            return {"status": "auto_fined_mock", "reason": "Celery not configured"}
            
    raise HTTPException(status_code=500, detail="Invalid routing state")
