# ATVED GridLock - Hackathon Demo Guide

This guide contains everything you need to run the live end-to-end demo for the Flickar GridLock Road Safety Hackathon. 

## 1. Setup Environment
First, ensure you are on the `kunal` branch and have installed the required dependencies.

```bash
# Checkout the final branch
git fetch origin
git checkout kunal

# Install dependencies (FastAPI, SQLAlchemy, Ultralytics, OpenCV)
pip install -r requirements.txt
```

## 2. Start the Backend API Server
The backend handles the traffic score calculations, mock bank deductions, and E-Challan PDF generation. Open a new terminal and run:

```bash
# 1. Reset and seed the mock database (Aadhaar records, plates, etc.)
python setup_db.py

# 2. Start the FastAPI Server on port 8000
python api_server.py
```
*(Leave this terminal running in the background)*

## 3. Start the Premium UI Dashboard
We built a custom HTML/CSS/JS web application. Open a **second terminal** and run a local web server to serve the files:

```bash
# Serve the dashboard folder on port 8080
python -m http.server 8080 -d dashboard
```

Now, open your browser and go to: **[http://localhost:8080](http://localhost:8080)**

**Demo Login Credentials:**
- **Aadhaar:** `4832 7651 9023` (Kunaljit Kashyap)
- *The backend will auto-generate a secure 6-digit OTP and display it on the UI for you to type in.*

*(Leave this terminal running in the background)*

## 4. Run the Live Computer Vision Demo
To prove the AI actually detects violations and triggers the whole system, open a **third terminal** and run the YOLO end-to-end script on a video file.

```bash
# Run the model on your demo video (replace 'your_traffic_video.mp4' with an actual video file)
python computer_vision_models/demo_live_end_to_end.py your_traffic_video.mp4
```

### What happens when you run this?
1. A video window will pop up showing real-time YOLO bounding boxes.
2. The script has an **"Override Trick"** built-in. Even though the video shows a random car, the script will automatically intercept the OCR and map it to Kunaljit's license plate (`AS 01 KK 4521`).
3. It sends the violation to the API. 
4. Switch immediately to the Browser (`http://localhost:8080`).
5. **The Magic:** You will instantly see Kunaljit's Traffic Score drop, and his mock Bank Balance decrease automatically on the UI!

### Evidence
Check the `evidence/challans/` folder. The system will have generated a beautifully formatted E-Challan PDF receipt showing the specific violation and the dynamically multiplied fine amount!
