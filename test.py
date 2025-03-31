import pytesseract
from PIL import Image
import os

# Set the path to tesseract.exe
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Path to your image
image_path = r'C:\Users\valen\Desktop\SocialHub\image3.png'

# Verify the image exists
if not os.path.exists(image_path):
    print(f"Error: Image not found at {image_path}")
else:
    try:
        # Open the image
        img = Image.open(image_path)
        
        # Perform OCR
        text = pytesseract.image_to_string(img)
        
        # Print extracted text
        print("Extracted Text:")
        print(text)
        
        # (Optional) Save to a text file
        with open('extracted_text.txt', 'w', encoding='utf-8') as f:
            f.write(text)
        print("Text saved to extracted_text.txt")
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")