#!/usr/bin/env python3
"""
Test OCR functionality with the test image
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from file_processor import FileProcessor

def test_ocr():
    print("🔍 Testing OCR functionality...")
    
    # Read the test image
    with open('test_image.png', 'rb') as f:
        image_data = f.read()
    
    print(f"📁 Image size: {len(image_data)} bytes")
    
    # Test file processor
    processor = FileProcessor()
    result = processor.process_file(image_data, 'test_image.png')
    
    print(f"🏷️  Processing result:")
    print(f"   Success: {result['success']}")
    print(f"   File type: {result['processing_type']}")
    
    if result['success']:
        print(f"   Stored filename: {result['stored_filename']}")
        print(f"   Extracted text length: {len(result['extracted_text'])}")
        print(f"📝 Extracted text:")
        print(f"   '{result['extracted_text'][:200]}{'...' if len(result['extracted_text']) > 200 else ''}'")
        
        metadata = result['metadata']
        if 'width' in metadata:
            print(f"🖼️  Image metadata:")
            print(f"   Dimensions: {metadata['width']}x{metadata['height']}")
            print(f"   Format: {metadata.get('format', 'Unknown')}")
            print(f"   OCR Success: {metadata.get('ocr_success', False)}")
        
        return True
    else:
        print(f"❌ Processing failed: {result['error']}")
        return False

if __name__ == "__main__":
    test_ocr()