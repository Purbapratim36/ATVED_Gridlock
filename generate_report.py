from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from datetime import datetime

def generate_report():
    doc = Document()
    
    # Title Page
    doc.add_heading('Automated Traffic Violation Evidence & Detection (ATVED)', 0)
    
    subtitle = doc.add_paragraph('Comprehensive System Architecture & Development Report\n')
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].font.size = Pt(14)
    subtitle.runs[0].font.bold = True
    
    date_para = doc.add_paragraph(f'Date Generated: {datetime.now().strftime("%Y-%m-%d")}')
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_page_break()
    
    # 1. Abstract
    doc.add_heading('1. Abstract', level=1)
    doc.add_paragraph(
        "Traffic rule violations, such as riding without helmets or overspeeding, contribute significantly "
        "to road accidents. Traditional manual enforcement is inefficient and prone to human error. "
        "The Automated Traffic Violation Evidence & Detection (ATVED) system aims to solve this by "
        "deploying an end-to-end AI pipeline. The system processes live camera feeds using Computer Vision "
        "to detect violations in real-time, automatically generate E-Challans (PDF tickets), deduct "
        "traffic compliance scores, and provide a comprehensive web dashboard for both citizens and authorities."
    )
    
    # 2. Technologies & Libraries
    doc.add_heading('2. Technologies & Frameworks', level=1)
    tech_details = [
        ("Computer Vision", "Ultralytics YOLOv8 (Custom trained for helmet detection), ByteTrack (Object Tracking), OpenCV (Video processing)."),
        ("Backend Server", "FastAPI (High-performance API framework), Uvicorn (ASGI Server), Pydantic (Data validation)."),
        ("Database", "PostgreSQL (Relational DB), SQLAlchemy (Async ORM), GeoAlchemy2 (Spatial data)."),
        ("Evidence & Reporting", "FPDF2 (PDF Generation for E-Challans)."),
        ("Deployment & DevOps", "Docker & Docker Compose (Containerization of the database and API server)."),
        ("Frontend Dashboards", "HTML5, CSS3 (Glassmorphism design), Vanilla JS, Chart.js (Analytics visualization).")
    ]
    for tech, desc in tech_details:
        p = doc.add_paragraph()
        p.add_run(f"{tech}: ").bold = True
        p.add_run(desc)

    # 3. System Architecture & Workflow
    doc.add_heading('3. System Architecture & Workflow', level=1)
    doc.add_paragraph("The ATVED system operates in a streamlined, multi-stage pipeline:")
    
    workflow = [
        ("1. Video Ingestion", "The system connects to IP Webcams or static video files using OpenCV."),
        ("2. Object Detection", "YOLOv8 scans each frame to locate motorcycles, riders, and helmets."),
        ("3. Tracking", "ByteTrack assigns unique IDs to detected objects across frames to prevent duplicate counting."),
        ("4. Rule Evaluation", "Custom Python logic evaluates spatial relationships (e.g., rider overlapping a motorcycle) to confirm violations (e.g., no helmet for 5 consecutive frames)."),
        ("5. API Ingestion", "Detected violations are sent via POST request to the FastAPI backend."),
        ("6. Evidence Generation", "The backend automatically generates a PDF E-Challan containing violation details."),
        ("7. Profile Scoring", "The driver's Traffic Score is deducted. If the plate is unregistered, a mock RTO lookup creates a new temporary profile."),
        ("8. Dashboard Review", "The user can view their challans and click 'Dispute'. Authorities can review the dispute queue and accept/reject appeals.")
    ]
    for step, desc in workflow:
        p = doc.add_paragraph(style='List Bullet')
        p.add_run(f"{step}: ").bold = True
        p.add_run(desc)

    doc.add_paragraph("Below is the visual workflow diagram demonstrating the end-to-end pipeline:")
    doc.add_picture('workflow.png', width=Inches(6.0))

    # 4. Model Accuracy & Evaluation
    doc.add_page_break()
    doc.add_heading('4. Model Accuracy & Evaluation', level=1)
    doc.add_paragraph(
        "The object detection engine relies on a custom-trained YOLOv8 model specialized for traffic environments. "
        "The model achieves high accuracy across all critical classes. Below is the normalized confusion matrix "
        "demonstrating the model's performance on the validation dataset:"
    )
    doc.add_picture('confusion_matrix.png', width=Inches(5.5))
    doc.add_paragraph()

    # 5. File functioning
    doc.add_heading('5. Core Files & Modules', level=1)
    
    files = [
        ("api_server.py", "Central FastAPI application. Hosts all REST endpoints, manages SQLAlchemy database sessions, integrates the mock RTO system, generates PDF E-Challans via FPDF2, and serves the static HTML dashboards."),
        ("demo_live_end_to_end.py", "The primary inference script. It opens the camera stream, initializes the YOLO model and ByteTrack, runs the frame-by-frame analysis, and pushes violation data to the API server."),
        ("src/atved/violations/helmet.py", "Contains the mathematical logic for detecting helmet violations by calculating bounding box overlaps (IoU) between motorcycles and riders, and checking the upper 35% of the rider's region for a helmet class."),
        ("src/atved/violations/speed.py", "Contains the mathematical logic for speed estimation using perspective transformation, tracking centroid displacement across frames based on a pixels-per-meter calibration."),
        ("src/atved/db/models.py", "Defines the PostgreSQL database schemas including Driver, Camera, ViolationRecord, Evidence, and Appeal tables."),
        ("docker-compose.yml", "Orchestrates the PostgreSQL database and FastAPI server into isolated, interconnected Docker containers for easy standalone deployment."),
        ("dashboard/user/ & dashboard/authority/", "Frontend directories containing the HTML, CSS, and JS for the Citizen Portal and Analytics Dashboard. Features include Chart.js gauges, dynamic tables, and modal-based dispute workflows.")
    ]
    for filename, desc in files:
        p = doc.add_paragraph()
        p.add_run(f"{filename}").bold = True
        p.add_run(f" - {desc}")
        
    # 5. Conclusion
    doc.add_heading('5. Conclusion & Future Scope', level=1)
    doc.add_paragraph(
        "The ATVED prototype successfully demonstrates a fully automated, standalone pipeline for traffic enforcement. "
        "By combining state-of-the-art Computer Vision with a robust, asynchronous backend API, the system eliminates "
        "the need for manual traffic monitoring. Future scope includes integrating ANPR (Automatic Number Plate Recognition) "
        "models directly into the pipeline, deploying the AI inference workers inside GPU-accelerated Docker containers, "
        "and building a mobile application for traffic police on the ground."
    )
    
    # Save the document
    output_path = 'ATVED_Project_Report_v2.docx'
    doc.save(output_path)
    print(f"Report successfully generated at: {output_path}")

if __name__ == "__main__":
    generate_report()
