#!/usr/bin/env python3
"""
Test the file processor functionality
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from file_processor import FileProcessor

def test_file_processor():
    """Test basic file processor functionality"""
    print("Testing FileProcessor...")
    
    try:
        processor = FileProcessor()
        print(f"✅ FileProcessor initialized")
        print(f"   Uploads dir: {processor.uploads_dir}")
        print(f"   Audio dir: {processor.audio_dir}")
        print(f"   Max size: {processor.max_size / (1024*1024):.1f} MB")
        
        # Test supported types
        print(f"   Supported image types: {list(processor.SUPPORTED_IMAGE_TYPES.keys())}")
        print(f"   Supported document types: {list(processor.SUPPORTED_DOCUMENT_TYPES.keys())}")
        print(f"   Supported audio types: {list(processor.SUPPORTED_AUDIO_TYPES.keys())}")
        
        # Test file type detection (with dummy data)
        test_data = b"fake image data"
        mime_type, category = processor.detect_file_type(test_data, "test.jpg")
        print(f"   Test file detection: {mime_type} -> {category}")
        
        print("✅ FileProcessor tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ FileProcessor test failed: {e}")
        return False

if __name__ == "__main__":
    test_file_processor()