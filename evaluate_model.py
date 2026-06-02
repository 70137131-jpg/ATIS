from ultralytics import YOLO

model = YOLO(r"runs\classify\ATIS_Project\tyre_safety_model\weights\best.pt")
metrics = model.val()  # It will automatically evaluate using ATIS_Dataset/val
print(f"Top-1 Accuracy: {metrics.top1 * 100:.2f}%")