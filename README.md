# ATVED (Automated Traffic Violation Enforcement Dashboard)

ATVED is an advanced, end-to-end computer vision and web dashboard system designed to automatically detect traffic violations using traffic camera feeds, generate electronic citations (E-Challans), and provide real-time monitoring for both Police Authorities and Citizens.

> **Note on Testing & Validation:** Due to hardware limitations in processing multiple heavy deep learning models simultaneously in real-time, we are using pre-recorded high-resolution videos for validating the model's accuracy and performance during demonstrations.
## 🌟 Key Features

### 1. Dual AI Vision Engine
The core engine (`demo_live_end_to_end.py`) processes video feeds in real-time using a cascade of customized YOLO models and Optical Character Recognition (OCR):
- **Vehicle Tracking:** Uses ByteTrack to assign unique IDs to vehicles across frames, preventing duplicate citations.
- **Speed Detection:** Calculates real-world speed via pixel displacement analysis.
- **Helmet & Seatbelt Detection:** Specialized secondary models check for safety equipment compliance.
- **Red Light Violations:** Virtual stop-line crossing detection.
- **ALPR (Automatic License Plate Recognition):** Extracts the text from license plates of violating vehicles using EasyOCR.

### 2. Live API Backend
A lightweight, lightning-fast asynchronous backend powered by FastAPI (`api_server.py`) acts as the brain of the operation:
- **Real-Time Data Ingestion:** Receives violations directly from the Vision Engine.
- **Dynamic Scoring System:** Automatically deducts points from a driver's traffic score based on the severity of the violation.
- **E-Challan Generation:** Automatically generates official PDF receipts/challans dynamically for every violation.

### 3. Dual Web Dashboards
Beautifully designed, responsive, and data-driven portals for both stakeholders:
- **Authority Portal (Police Control Room):** Features a live-updating feed of AI-detected violations, a dynamic map of active traffic cameras, and real-time Key Performance Indicators (KPIs) showing total fines collected and system health.
- **Citizen Portal:** Allows users to log in and view their personal traffic score, past violations, and securely download PDF copies of their E-Challans.

---

## 🛠️ Technology Stack
- **Computer Vision:** PyTorch, Ultralytics YOLOv8, OpenCV, EasyOCR, ByteTrack
- **Backend Server:** Python, FastAPI, Uvicorn, FPDF
- **Database:** SQLite (Async via SQLAlchemy & aiosqlite)
- **Frontend Dashboards:** HTML5, Vanilla JavaScript, CSS3 (Glassmorphism UI), Leaflet.js (Maps)

---

## 🚀 How to Run the Project Locally

### Prerequisites
Make sure you have Python 3.10+ installed along with the required packages:
```bash
pip install fastapi uvicorn sqlalchemy aiosqlite fpdf ultralytics opencv-python easyocr requests
```

### Step 1: Start the API Server & Dashboards
Open a terminal in the root directory of the project and start the backend server:
```bash
python api_server.py
```
This will automatically initialize the database and host your web dashboards at:
- **Authority Dashboard:** http://localhost:8000/authority
- **Citizen Dashboard:** http://localhost:8000/user

### Step 2: Start the AI Vision Engine
Open a **second** terminal window and run the live camera engine against a test video:
```bash
python computer_vision_models/demo_live_end_to_end.py traffic.mp4
```
*(Note: If you want to test with a live webcam, replace `traffic.mp4` with `0`)*

The AI engine will begin processing the video, drawing bounding boxes, and pushing live violations to your backend. You can watch the dashboards update in real-time as cars break the rules!

---

## 📁 Project Structure

```text
ATVED_Gridlock/
├── api_server.py                  # Main FastAPI backend & database logic
├── computer_vision_models/        # AI logic and model weights
│   ├── demo_live_end_to_end.py    # The main inference engine loop
│   ├── yolov8n.pt                 # YOLOv8 weights
│   └── ... 
├── dashboard/                     # Web Frontends
│   ├── index.html                 # Citizen Portal UI
│   ├── authority.html             # Police Authority UI
│   ├── js/                        # API fetching logic
│   └── css/                       # Styling
├── evidence/                      # Auto-generated
│   └── challans/                  # PDF Receipts are saved here
└── src/                           # Internal Python modules and schemas
```

## ⚠️ Notes for Evaluators
- This project utilizes **GPU acceleration** (CUDA via PyTorch) for optimal performance. If run on a CPU, the video processing framerate will be significantly lower.
- The system is designed to simulate a connection to an RTO (Regional Transport Office) database. If an unregistered license plate is detected, it will automatically register a mock profile in the database to demonstrate the flow.
