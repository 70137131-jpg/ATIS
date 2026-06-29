from ultralytics import YOLO
from atis_inference import find_model_path

if __name__ == '__main__':
    model = YOLO(r"E:\ATIS\runs\classify\ATIS_Project\tyre_safety_model\weights\best.pt")
    
    metrics = model.val(
        data=r"E:\ATIS\ATIS_Dataset",
        workers=2
    )
    
    print(f"Top-1 Accuracy: {metrics.top1 * 100:.2f}%")
