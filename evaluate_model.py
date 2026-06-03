from ultralytics import YOLO
from atis_inference import find_model_path

model_path = find_model_path()
if model_path is None:
    raise SystemExit("Model weights not found. Train the classifier first or set ATIS_MODEL_PATH.")

model = YOLO(str(model_path))
metrics = model.val()  # It will automatically evaluate using ATIS_Dataset/val
print(f"Top-1 Accuracy: {metrics.top1 * 100:.2f}%")
