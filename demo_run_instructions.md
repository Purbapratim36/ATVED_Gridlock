# ATVED Gridlock - Distributed Architecture Demo

To run the full production-style 5-terminal distributed architecture (including the background worker and dashboard), I have restored the Celery routing code. 

Open 5 separate PowerShell windows, navigate all of them to `C:\Users\mahan\OneDrive\Documents\Desktop\Projects\ATVED_Gridlock`, and run the following commands in order:

## Terminal 1: Database (Redis Message Broker)
Starts the local Redis server needed to queue background tasks.
```powershell
.\redis\redis-server.exe
```

## Terminal 2: Core API Server
Starts the central API hub that receives detections and routes them.
```powershell
python api_server.py
```

## Terminal 3: Background Worker (Celery)
Starts the asynchronous worker that listens for Redis messages and physically generates the official PDF Challan documents.
```powershell
python -m celery -A src.atved.tasks.challan_tasks worker --loglevel=info --pool=solo
```

## Terminal 4: Authority Dashboard (Streamlit)
Boots up the interactive web application used by the traffic authority to review fines.
```powershell
python -m streamlit run streamlit_app.py
```

## Terminal 5: Live Video AI Engine
Finally, start the heavy AI engine that runs the YOLO and ONNX OCR models on your GPU, analyzes the video frame-by-frame, and pumps violations to the API.
```powershell
python computer_vision_models/demo_live_end_to_end.py test1.mp4
```

> **To test Red Light Violations:** Press the `r` key on your keyboard while the video is playing in Terminal 5 to toggle the virtual traffic light from GREEN to RED.
