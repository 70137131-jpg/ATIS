import os
from ultralytics import YOLO

def train_atis_classifier():
    """
    Trains a YOLOv11 classification model for the Automated Tyre Inspection System.
    """
    model = YOLO("yolo11n-cls.pt")
    dataset_path = r"E:\ATIS\ATIS_Dataset"
    
    print("Starting YOLOv11 Classification Training...")
    
    results = model.train(
        data=dataset_path,
        epochs=50,
        imgsz=224,
        batch=16,
        workers=2,
        device=0,
        project="runs/classify/ATIS_Project",
        name="tyre_safety_model",
        exist_ok=True
    )
    
    print("Training complete. Weights saved under runs/classify/ATIS_Project/tyre_safety_model/weights/")

if __name__ == "__main__":
    train_atis_classifier()