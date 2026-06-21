import cv2
import sys
import os
from ultralytics import YOLO

# load both models
try:
    m1 = YOLO("yolov8n.pt")
    print("Model 1 loaded")
    m2 = YOLO("atved_seatbelt_best.pt")
    print("Model 2 loaded")
except Exception as e:
    print("Error loading models:", e)
    sys.exit(1)

# try a predict
try:
    img = cv2.imread(r"C:\Users\mahan\OneDrive\Documents\Desktop\Projects\Gridlock_sunny\confusion_matrix.png")
    r1 = m1.predict(img)
    print("M1 predicted")
    r2 = m2.predict(img)
    print("M2 predicted")
except Exception as e:
    print("Predict error:", e)
