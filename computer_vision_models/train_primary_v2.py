import os
from ultralytics import YOLO
import sys

def main():
    print("============================================================")
    print("  ATVED - Primary Detector Retraining (FLAW 1 & FLAW 2) ")
    print("============================================================")
    
    # Check GPU VRAM to decide model size (FLAW 1)
    import torch
    model_size = 'yolov8n.yaml'
    img_size = 640
    
    if torch.cuda.is_available():
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        print(f"Detected GPU VRAM: {vram_gb:.2f} GB")
        if vram_gb >= 4.0:
            print("VRAM >= 4GB. Upgrading primary detector to YOLOv8s (Small).")
            model_size = 'yolov8s.pt'
            img_size = 640
        else:
            print("VRAM < 4GB. Keeping YOLOv8n but increasing resolution to 1280px.")
            model_size = 'yolov8n.pt'
            img_size = 1280
    else:
        print("No CUDA detected. Running on CPU with YOLOv8n (Testing mode).")
        model_size = 'yolov8n.pt'
        img_size = 640
        
    print(f"\nInitializing model: {model_size} | Input Size: {img_size}px")
    
    # User must pass their dataset yaml here
    dataset_yaml = sys.argv[1] if len(sys.argv) > 1 else 'coco8.yaml'
    
    print(f"Target Dataset: {dataset_yaml}")
    print("Expected Classes: car, motorcycle, truck, bus, person, three_wheeler, bicycle, lcv, tractor")
    
    model = YOLO(model_size)
    
    # Time-boxed training parameters
    try:
        results = model.train(
            data=dataset_yaml,
            epochs=50,
            imgsz=img_size,
            batch=16,
            device=0 if torch.cuda.is_available() else 'cpu',
            patience=10,
            project='atved_training',
            name='primary_v2',
            exist_ok=True
        )
        print("\nTraining Complete! Weights saved to atved_training/primary_v2/weights/best.pt")
        
    except Exception as e:
        print(f"Training Failed: {e}")

if __name__ == "__main__":
    main()
