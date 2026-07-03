import os

from atis_inference import classify_tyre_image, find_model_path

def run_tyre_safety_check(image_path):
    """
    Runs inference using the trained ATIS classification model to predict tire safety.
    """
    weights_path = find_model_path()
    if weights_path is None:
        print("Error: Model weights (best.pt) not found anywhere in your runs directory.")
        print("Please verify your training finished successfully without errors.")
        return
    
    print(f"Analyzing tire image: {image_path}")
    print(f"Using model weights from: {weights_path}")
    print("-" * 50)
    
    prediction = classify_tyre_image(image_path, weights_path)
    predicted_class = prediction["predicted_class"]
    confidence = prediction["confidence"]
    
    print("\n=== ATIS DIAGNOSTIC REPORT ===")
    print(f"Detected Condition                : {predicted_class.upper()}")
    print(f"Confidence Score                  : {confidence:.2f}%")
    print("-" * 46)
    
    if prediction["status"] == "safe":
        print("VERDICT: ELIGIBLE FOR HIGHWAY TRAVEL.")
        print("Status : Green - The tire texture shows no critical surface defects.")
    elif prediction.get("low_confidence"):
        print("VERDICT: NOT ELIGIBLE - FLAGGED FOR MANUAL REVIEW.")
        print(
            f"Status : Amber - '{predicted_class}' predicted below the "
            f"{prediction.get('threshold', '?')}% confidence threshold."
        )
    else:
        print("VERDICT: NOT ELIGIBLE FOR HIGHWAY TRAVEL.")
        print("Status : Red - Structural cracking or dangerous degradation detected.")
        
    print("=============================================\n")

if __name__ == "__main__":
    # Target your sample image directly in the ATIS folder.
    SAMPLE_IMAGE = "tyre3.jpg" 
    
    # Convert to absolute path to prevent any root folder ambiguity
    abs_image_path = os.path.abspath(SAMPLE_IMAGE)
    
    if os.path.exists(abs_image_path):
        run_tyre_safety_check(abs_image_path)
    else:
        print(f"Error: Could not find '{SAMPLE_IMAGE}' at location: {abs_image_path}")
        print("Please check the folder to make sure the file name and extension are exactly matching.")
