#!/usr/bin/env python3
"""
Simple test for file processing capabilities
"""

from pathlib import Path

# Test PIL availability
try:
    from PIL import Image
    print("✅ PIL/Pillow available")
    PIL_AVAILABLE = True
except ImportError:
    print("❌ PIL/Pillow not available")
    PIL_AVAILABLE = False

# Test pytesseract availability  
try:
    import pytesseract
    print("✅ pytesseract available")
    TESSERACT_AVAILABLE = True
except ImportError:
    print("❌ pytesseract not available")
    TESSERACT_AVAILABLE = False

# Test PyPDF2 availability
try:
    import PyPDF2
    print("✅ PyPDF2 available")
    PDF_AVAILABLE = True
except ImportError:
    print("❌ PyPDF2 not available") 
    PDF_AVAILABLE = False

# Test python-magic availability
try:
    import magic
    print("✅ python-magic available")
    MAGIC_AVAILABLE = True
except ImportError:
    print("❌ python-magic not available (will use filename fallback)")
    MAGIC_AVAILABLE = False

print("\n📋 Summary:")
print(f"Image processing (PIL): {'✅' if PIL_AVAILABLE else '❌'}")
print(f"OCR (pytesseract): {'✅' if TESSERACT_AVAILABLE else '❌'}")
print(f"PDF processing (PyPDF2): {'✅' if PDF_AVAILABLE else '❌'}")
print(f"File type detection (magic): {'✅' if MAGIC_AVAILABLE else '⚠️  (fallback available)'}")

# Test file type detection fallback
def test_file_type_detection():
    print("\n🔍 Testing file type detection fallback:")
    
    test_files = [
        ("test.jpg", "image/jpeg", "image"),
        ("test.png", "image/png", "image"), 
        ("test.pdf", "application/pdf", "document"),
        ("test.mp3", "audio/mpeg", "audio"),
        ("test.wav", "audio/wav", "audio"),
        ("test.unknown", "application/octet-stream", "unknown")
    ]
    
    for filename, expected_mime, expected_category in test_files:
        ext = Path(filename).suffix.lower()
        if ext in ['.jpg', '.jpeg']:
            mime_type = 'image/jpeg'
        elif ext == '.png':
            mime_type = 'image/png' 
        elif ext == '.pdf':
            mime_type = 'application/pdf'
        elif ext == '.mp3':
            mime_type = 'audio/mpeg'
        elif ext == '.wav':
            mime_type = 'audio/wav'
        else:
            mime_type = 'application/octet-stream'
            
        category = 'image' if mime_type.startswith('image/') else \
                   'audio' if mime_type.startswith('audio/') else \
                   'document' if mime_type == 'application/pdf' else 'unknown'
        
        status = "✅" if mime_type == expected_mime and category == expected_category else "❌"
        print(f"   {filename} -> {mime_type} ({category}) {status}")

test_file_type_detection()

print(f"\n🚀 Ready for file processing implementation!")