#!/usr/bin/env python3
"""
Create a test image with text for OCR testing
"""

from PIL import Image, ImageDraw, ImageFont
import io
import sys

def create_test_image():
    # Create a simple image with text
    width, height = 400, 200
    image = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(image)
    
    # Add some text
    text = "Second Brain OCR Test\nThis text should be extracted!"
    
    try:
        # Try to use a better font if available
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 20)
    except:
        # Fall back to default font
        font = ImageFont.load_default()
    
    # Draw text
    draw.text((20, 50), text, fill='black', font=font)
    
    # Draw a simple rectangle
    draw.rectangle([20, 120, 200, 160], outline='blue', width=2)
    draw.text((30, 130), "Test Rectangle", fill='blue', font=font)
    
    # Save the image
    image.save('test_image.png')
    print("✅ Created test_image.png")
    
    # Also create a bytes version for testing
    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return img_bytes.getvalue()

if __name__ == "__main__":
    create_test_image()