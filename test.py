import cv2
import pytesseract
import numpy as np
from PIL import Image

# Set Tesseract path
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def preprocess_image(image_path):
    # Read image with OpenCV
    img = cv2.imread(image_path)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Apply adaptive thresholding
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY_INV, 11, 2)
    
    # Remove noise
    kernel = np.ones((1, 1), np.uint8)
    processed = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    
    return processed

def extract_text(image_path):
    try:
        # Preprocess image
        processed_img = preprocess_image(image_path)
        
        # Configure Tesseract parameters
        custom_config = r'--oem 3 --psm 6 -l eng'
        
        # Perform OCR
        text = pytesseract.image_to_string(processed_img, config=custom_config)
        
        return text.strip()
    
    except Exception as e:
        return f"Error: {str(e)}"

# Usage
image_path = r'C:\Users\valen\Desktop\SocialHub\image3.png'
extracted_text = extract_text(image_path)

print("Original Output:")
print(extracted_text)

# Post-processing to clean common OCR errors
clean_text = extracted_text.replace('|', 'I').replace(']', 'J').replace('[', '')
print("\nCleaned Output:")
print(clean_text)