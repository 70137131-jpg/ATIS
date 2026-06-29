import os

from atis_inference import classify_tyre_image, find_model_path

def test_tyre_safety(image_path):
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
    
    # Confidence threshold — below this, result is treated as unreliable
    CONFIDENCE_THRESHOLD = 65.0
    
    # Run prediction (verbose=False keeps the console clean)
    results = model(image_path, verbose=False)
    
    # Extract and display the prediction data
    for result in results:
        top_class_id = result.probs.top1
        confidence = result.probs.top1conf.item()
        confidence_pct = confidence * 100
        predicted_class = result.names[top_class_id]
        
        print("\n=== ATIS DIAGNOSTIC REPORT ===")
        # DEBUGGING CRITICAL INFO: This reveals how the folders were mapped by Ultralytics
        print(f"DEBUG - Full Model Class Mapping : {result.names}")
        print(f"DEBUG - Predicted Class ID        : {top_class_id}")
        print("-" * 46)
        print(f"Detected Condition                : {predicted_class.upper()}")
        print(f"Confidence Score                  : {confidence_pct:.2f}%")
        print(f"Confidence Threshold              : {CONFIDENCE_THRESHOLD:.2f}%")
        print("-" * 46)

        # --- Low Confidence Override (checked first) ---
        if confidence_pct < CONFIDENCE_THRESHOLD:
            print("VERDICT: NOT A GOOD TYRE (LOW CONFIDENCE).")
            print(f"Status : Orange - Model confidence ({confidence_pct:.2f}%) is below the")
            print(f"         required threshold of {CONFIDENCE_THRESHOLD:.0f}%. Result is unreliable.")
            print("         Please inspect the tyre manually or re-submit a clearer image.")

        # --- Normal confidence: apply standard FYP Decision Logic ---
        elif str(predicted_class).strip().lower() == 'normal':
            print("VERDICT: ELIGIBLE FOR HIGHWAY TRAVEL.")
            print("Status : Green - The tire texture shows no critical surface defects.")
        elif str(predicted_class).strip().lower() == 'cracked':
            print("VERDICT: NOT ELIGIBLE FOR HIGHWAY TRAVEL.")
            print("Status : Red - Structural cracking or dangerous degradation detected.")
        else:
            print("VERDICT: UNKNOWN CLASS DETECTED.")
            print(f"Status : Orange - Unexpected folder class output: {predicted_class}")
            
        print("=============================================\n")

if __name__ == "__main__":
    # Target your sample image directly in the ATIS folder.
    SAMPLE_IMAGE = "tyre4.jpg" 
    
    # Convert to absolute path to prevent any root folder ambiguity
    abs_image_path = os.path.abspath(SAMPLE_IMAGE)
    
    if os.path.exists(abs_image_path):
        test_tyre_safety(abs_image_path)
    else:
        print(f"Error: Could not find '{SAMPLE_IMAGE}' at location: {abs_image_path}")
        print("Please check the folder to make sure the file name and extension are exactly matching.")
