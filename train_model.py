from ultralytics import YOLO

def train_atis_classifier():
    """
    Trains a YOLOv11 classification model for the Automated Tyre Inspection System.
    """
    # Load the YOLOv11 nano classification model (weights download automatically)
    model = YOLO("yolo11n-cls.pt")
    
    # Define the path to the root of the reformatted dataset
    dataset_path = "ATIS_Dataset"
    
    print("Starting YOLOv11 Classification Training...")
    
    # Train the model
    results = model.train(
        data=dataset_path,
        epochs=50,          # Adjust based on how quickly the model converges
        imgsz=224,          # Standard classification input size
        batch=32,           # Optimized batch size for 8GB VRAM
        device=0,           # Force CUDA usage (RTX 2070 Super)
        project="ATIS_Project",
        name="tyre_safety_model",
        exist_ok=True
    )
    
    print("Training complete. Weights saved in ATIS_Project/tyre_safety_model/weights/")

if __name__ == "__main__":
    train_atis_classifier()