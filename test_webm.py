#!/usr/bin/env python3
"""
Test WebM audio file processing
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from file_processor import FileProcessor
import json

def create_fake_webm():
    """Create a fake WebM file for testing"""
    # WebM files start with specific bytes, but for testing we'll just use a small file
    fake_webm = b'\x1a\x45\xdf\xa3' + b'\x00' * 100  # Basic WebM header + padding
    return fake_webm

def test_webm_processing():
    print("🎵 Testing WebM audio processing...")
    
    # Create fake WebM data
    webm_data = create_fake_webm()
    print(f"📁 WebM size: {len(webm_data)} bytes")
    
    # Test file processor
    processor = FileProcessor()
    
    # First test file type detection directly
    mime_type, category = processor.detect_file_type(webm_data, 'test_recording.webm')
    print(f"🔍 File type detection:")
    print(f"   MIME type: {mime_type}")
    print(f"   Category: {category}")
    
    # Test file validation
    is_valid, error, file_info = processor.validate_file(webm_data, 'test_recording.webm')
    print(f"📋 File validation:")
    print(f"   Valid: {is_valid}")
    print(f"   Error: {error}")
    print(f"   File info: {file_info}")
    
    if not is_valid:
        print("❌ File validation failed, can't proceed with processing")
        return False
    
    try:
        result = processor.process_file(webm_data, 'test_recording.webm')
        
        print(f"🏷️  Processing result:")
        print(f"   Success: {result['success']}")
        if result['success']:
            print(f"   File type: {result['processing_type']}")
            print(f"   Stored filename: {result.get('stored_filename', 'None')}")
            print(f"   File info: {result.get('file_info', {})}")
            print(f"   Metadata: {result.get('metadata', {})}")
            
            # Test JSON serialization of metadata
            try:
                json_str = json.dumps(result.get('metadata', {}), default=str)
                print(f"✅ JSON serialization successful: {len(json_str)} chars")
            except Exception as json_err:
                print(f"❌ JSON serialization failed: {json_err}")
            
        else:
            print(f"❌ Processing failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Exception during processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_webm_processing()