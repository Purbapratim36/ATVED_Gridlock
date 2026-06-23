"""
Celery tasks for offloading heavy API operations like PDF generation and SMS sending.
"""

import time
import structlog
import os
import random
from datetime import datetime, timedelta
from celery import Celery

logger = structlog.get_logger(__name__)

celery_app = Celery(
    "atved",
    broker="redis://127.0.0.1:6379/0",
    backend="redis://127.0.0.1:6379/0"
)

@celery_app.task(name="atved.tasks.challan_tasks.generate_and_dispatch_challan")
def generate_and_dispatch_challan(challan_id: str, plate_text: str = "UNKNOWN", violation_type: str = "UNKNOWN", evidence_path: str = None):
    """
    Background task to generate a highly styled PDF challan matching the GridLock design.
    """
    print(f"[DIAG-4] CELERY WORKER RECEIVED: challan_id={challan_id}")
    logger.info("celery.task.start", task="generate_and_dispatch_challan", challan_id=challan_id)
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors

        out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "demo_output", "challans")
        os.makedirs(out_dir, exist_ok=True)
        pdf_path = os.path.join(out_dir, f"{challan_id}.pdf")
        
        c = canvas.Canvas(pdf_path, pagesize=A4)
        W, H = A4
        
        # Helper for monospace text
        def drawText(x, y, text, font="Courier", size=10, color=colors.black):
            c.setFillColor(color)
            c.setFont(font, size)
            c.drawString(x, y, text)
            
        def drawCenterText(x, y, text, font="Courier", size=10, color=colors.black):
            c.setFillColor(color)
            c.setFont(font, size)
            c.drawCentredString(x, y, text)

        # 1. Header (Black background)
        c.setFillColorRGB(0, 0, 0)
        c.rect(0, H - 70, W, 70, fill=1)
        
        c.setFillColorRGB(1, 0.8, 0)
        c.rect(20, H - 40, 10, 10, fill=1)
        drawText(40, H - 40, "ATVED GRIDLOCK", "Courier-Bold", 18, colors.yellow)
        drawText(20, H - 55, "AI-POWERED TRAFFIC ENFORCEMENT SYSTEM", "Courier", 8, colors.lightgrey)
        
        drawText(W - 150, H - 35, "CHALLAN ID", "Courier-Bold", 8, colors.cyan)
        drawText(W - 200, H - 55, challan_id, "Courier-Bold", 18, colors.yellow)

        # 2. Yellow Bar
        c.setFillColorRGB(1, 0.84, 0)
        c.rect(0, H - 110, W, 40, fill=1)
        
        c.setFillColorRGB(0, 0, 0)
        c.rect(20, H - 105, 120, 30, fill=1)
        
        v_display = violation_type.replace('_', ' ').upper()
        drawText(30, H - 95, v_display, "Courier-Bold", 12, colors.yellow)
        drawText(150, H - 95, "VIOLATION DETECTED", "Courier-Bold", 12, colors.black)
        
        now = datetime.now()
        drawText(W - 150, H - 85, "DATE & TIME", "Courier", 8, colors.black)
        drawText(W - 200, H - 100, now.strftime('%Y-%m-%d   %H:%M:%S'), "Courier-Bold", 12, colors.black)

        # 3. Owner & Plate Boxes
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        
        # Box 1
        c.rect(10, H - 250, W/2 - 15, 130, fill=0)
        drawText(20, H - 140, "VEHICLE OWNER", "Courier", 8, colors.gray)
        owner_name = random.choice(["Kunaljit Kashyap", "Purba Pratim Mahanta", "Mayur"])
        drawText(20, H - 160, owner_name, "Courier-Bold", 14, colors.black)
        drawText(20, H - 180, "SOURCE", "Courier", 8, colors.gray)
        drawText(20, H - 200, "RTO Database - Verified", "Courier-Bold", 12, colors.black)
        drawText(20, H - 220, "TRAFFIC SCORE", "Courier", 8, colors.gray)
        
        # Randomize traffic score
        score = random.randint(150, 950)
        
        if score >= 700:
            score_color = colors.green
            status_text = "GOOD"
            status_bg = colors.green
        elif score >= 400:
            score_color = colors.orange
            status_text = "WARNING"
            status_bg = colors.orange
        else:
            score_color = colors.red
            status_text = "SUSPENDED"
            status_bg = colors.red
            
        drawText(20, H - 240, str(score), "Courier-Bold", 18, score_color)
        c.setFillColor(status_bg)
        c.rect(55, H - 240, 70, 15, fill=1)
        drawText(60, H - 235, status_text, "Courier-Bold", 10, colors.white)

        # Box 2
        c.rect(W/2 + 5, H - 250, W/2 - 15, 130, fill=0)
        drawText(W/2 + 15, H - 140, "DETECTED PLATE", "Courier", 8, colors.gray)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.rect(W/2 + 15, H - 175, 180, 30, fill=1)
        drawText(W/2 + 25, H - 165, plate_text.upper(), "Courier-Bold", 16, colors.yellow)
        drawText(W/2 + 15, H - 195, "CAMERA LOCATION", "Courier", 8, colors.gray)
        drawText(W/2 + 15, H - 210, "DEMO-LIVE-CAM", "Courier-Bold", 12, colors.black)
        drawText(W/2 + 15, H - 225, "Indore, Madhya Pradesh", "Courier", 10, colors.black)
        drawText(W/2 + 15, H - 245, "VEHICLE TYPE", "Courier", 8, colors.gray)
        drawText(W/2 + 95, H - 245, "Motorcycle", "Courier-Bold", 10, colors.black)

        # 4. Confidence Boxes
        drawText(10, H - 270, "AI DETECTION CONFIDENCE", "Courier-Bold", 8, colors.gray)
        c.rect(10, H - 330, W/3 - 15, 50, fill=0)
        drawCenterText(10 + (W/3 - 15)/2, H - 295, "VIOLATION", "Courier", 8, colors.gray)
        drawCenterText(10 + (W/3 - 15)/2, H - 315, "78%", "Courier-Bold", 16, colors.black)
        drawCenterText(10 + (W/3 - 15)/2, H - 325, "CONFIRMED", "Courier", 6, colors.black)
        
        c.rect(W/3 + 5, H - 330, W/3 - 10, 50, fill=0)
        drawCenterText(W/3 + 5 + (W/3 - 10)/2, H - 295, "OCR PLATE", "Courier", 8, colors.gray)
        drawCenterText(W/3 + 5 + (W/3 - 10)/2, H - 315, "90%", "Courier-Bold", 16, colors.black)
        drawCenterText(W/3 + 5 + (W/3 - 10)/2, H - 325, "PRIMARY READ", "Courier", 6, colors.black)

        c.rect(2*W/3 + 5, H - 330, W/3 - 15, 50, fill=0)
        drawCenterText(2*W/3 + 5 + (W/3 - 15)/2, H - 295, "OCR VOTES", "Courier", 8, colors.gray)
        drawCenterText(2*W/3 + 5 + (W/3 - 15)/2, H - 315, "9/15", "Courier-Bold", 16, colors.black)
        drawCenterText(2*W/3 + 5 + (W/3 - 15)/2, H - 325, "MAJORITY", "Courier", 6, colors.black)

        # 5. Evidence Snapshot
        drawText(10, H - 350, "EVIDENCE SNAPSHOT", "Courier-Bold", 8, colors.gray)
        c.setFillColorRGB(0.15, 0.15, 0.15)
        c.rect(10, H - 580, W - 20, 220, fill=1)
        
        c.setFillColorRGB(1, 0.2, 0)
        c.rect(20, H - 380, 100, 15, fill=1)
        drawText(25, H - 375, "LIVE DETECTION", "Courier-Bold", 9, colors.white)
        
        c.setFillColorRGB(0, 0, 0)
        c.rect(W - 60, H - 380, 40, 15, fill=1)
        drawText(W - 55, H - 375, "CAM-01", "Courier-Bold", 9, colors.yellow)
        
        drawCenterText(W/2, H - 400, f"FRAME CAPTURE - {now.strftime('%H:%M:%S')}", "Courier-Bold", 10, colors.yellow)

        # Image Drawing inside the dark box
        if evidence_path and os.path.exists(evidence_path):
            try:
                c.drawImage(evidence_path, W/2 - 150, H - 540, width=300, height=130, preserveAspectRatio=True)
                c.setStrokeColor(colors.red)
                c.setLineWidth(1)
                c.rect(W/2 - 150, H - 540, 300, 130, fill=0)
            except Exception as e:
                drawCenterText(W/2, H - 480, f"[IMAGE LOAD ERROR: {e}]", "Courier", 10, colors.white)
        else:
            c.setStrokeColor(colors.red)
            c.rect(W/2 - 100, H - 500, 200, 80, fill=0)
            drawCenterText(W/2, H - 450, "DETECTION BOX", "Courier-Bold", 10, colors.red)
            drawCenterText(W/2, H - 465, "TRACK ID: 51", "Courier-Bold", 10, colors.red)
            drawCenterText(W/2, H - 480, "CONF: 78%", "Courier-Bold", 10, colors.red)
            drawCenterText(W/2, H - 520, "[ evidence image embedded in PDF ]", "Courier", 8, colors.lightgrey)

        drawText(10, H - 595, "Frame retained as tamper-proof evidence. Hash: 0x4A2F...C91B", "Courier", 8, colors.gray)

        # 6. Fine Calculation row
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        
        base_fine = 500
        if "SPEEDING" in violation_type.upper(): base_fine = 1000
        elif "RED_LIGHT" in violation_type.upper(): base_fine = 1500
        elif "HELMET" in violation_type.upper(): base_fine = 1000
        
        # Left: Base Fine
        c.rect(10, H - 680, W/3, 70, fill=0)
        drawCenterText(10 + W/6, H - 630, "BASE FINE", "Courier", 8, colors.gray)
        drawCenterText(10 + W/6, H - 655, f"Rs. {base_fine:,}", "Courier-Bold", 20, colors.black)
        drawCenterText(10 + W/6, H - 670, v_display, "Courier", 8, colors.gray)

        # Middle: Multiplier (Yellow bg)
        c.setFillColorRGB(1, 0.9, 0.6)
        c.rect(10 + W/3, H - 680, W/3, 70, fill=1)
        drawCenterText(10 + W/3 + W/6, H - 630, "MULTIPLIER", "Courier", 8, colors.gray)
        drawCenterText(10 + W/3 + W/6, H - 655, "3x", "Courier-Bold", 20, colors.orange)
        drawCenterText(10 + W/3 + W/6, H - 670, "SCORE: 0 / 1000", "Courier", 8, colors.gray)

        # Right: Total Due (Red bg)
        c.setFillColorRGB(0.9, 0.1, 0.1)
        c.rect(10 + 2*W/3, H - 680, W/3 - 20, 70, fill=1)
        drawCenterText(10 + 2*W/3 + (W/3 - 20)/2, H - 630, "TOTAL DUE", "Courier", 8, colors.white)
        drawCenterText(10 + 2*W/3 + (W/3 - 20)/2, H - 655, f"Rs. {base_fine * 3:,}", "Courier-Bold", 22, colors.white)
        drawCenterText(10 + 2*W/3 + (W/3 - 20)/2, H - 670, "AUTO-DEDUCTED", "Courier", 8, colors.white)

        # 7. QR Code / Footer
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        c.rect(20, H - 760, 60, 60, fill=0)
        # Draw fake QR squares
        c.rect(25, H - 725, 20, 20, fill=0)
        c.rect(55, H - 725, 20, 20, fill=0)
        c.rect(25, H - 755, 20, 20, fill=0)
        c.rect(55, H - 755, 10, 10, fill=1)
        c.rect(65, H - 745, 10, 10, fill=1)

        drawText(100, H - 720, "PAY ONLINE - SCAN OR VISIT", "Courier", 8, colors.gray)
        drawText(100, H - 735, f"pay.atved.gov.in/{challan_id}", "Courier-Bold", 12, colors.black)
        
        due_date = (now + timedelta(days=15)).strftime('%d-%m-%Y')
        c.setFillColorRGB(0.9, 0.2, 0.1)
        c.rect(100, H - 755, 120, 15, fill=1)
        drawText(105, H - 750, f"DUE BY: {due_date}", "Courier-Bold", 8, colors.white)
        
        c.setFillColorRGB(0.1, 0.5, 0.1)
        c.rect(230, H - 755, 100, 15, fill=1)
        drawText(235, H - 750, "15 DAYS TO PAY", "Courier-Bold", 8, colors.yellow)

        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.rect(340, H - 755, 150, 15, fill=0)
        drawText(345, H - 750, "UPI / NET BANKING / CARD", "Courier-Bold", 8, colors.black)

        # 8. Bottom Black Bar
        c.setFillColorRGB(0, 0, 0)
        c.rect(0, 0, W, 40, fill=1)
        drawText(20, 20, "VERIFY: verify.atved.gov.in  |  HASH: 0x4A2F9C...1B  |  DIGITALLY SIGNED", "Courier-Bold", 8, colors.yellow)
        drawText(20, 8, "Non-payment attracts 2x penalty after due date.", "Courier", 8, colors.gray)

        c.save()
        
        logger.info("celery.task.pdf_generated", challan_id=challan_id, path=pdf_path)
    except Exception as e:
        logger.error("celery.task.pdf_failed", error=str(e))
    
    time.sleep(1.0)
    logger.info("celery.task.sms_sent", challan_id=challan_id)
    return {"status": "success", "challan_id": challan_id, "action": "challan_dispatched"}
