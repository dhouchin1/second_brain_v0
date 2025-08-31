#!/usr/bin/env python3
"""
Test PDF processing functionality
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from file_processor import FileProcessor

def test_pdf():
    print("📄 Testing PDF processing...")
    
    # Read the test PDF
    with open('test_document.pdf', 'rb') as f:
        pdf_data = f.read()
    
    print(f"📁 PDF size: {len(pdf_data)} bytes")
    
    # Test file processor
    processor = FileProcessor()
    result = processor.process_file(pdf_data, 'test_document.pdf')
    
    print(f"🏷️  Processing result:")
    print(f"   Success: {result['success']}")
    print(f"   File type: {result['processing_type']}")
    
    if result['success']:
        print(f"   Stored filename: {result['stored_filename']}")
        print(f"   Extracted text length: {len(result['extracted_text'])}")
        print(f"📝 Extracted text:")
        print(f"   '{result['extracted_text'][:300]}{'...' if len(result['extracted_text']) > 300 else ''}'")
        
        metadata = result['metadata']
        if 'pages' in metadata:
            print(f"📄 PDF metadata:")
            print(f"   Pages: {metadata['pages']}")
            print(f"   Extraction method: {metadata.get('extraction_method', 'Unknown')}")
            print(f"   Text length: {metadata.get('text_length', 0)}")
        
        return True
    else:
        print(f"❌ Processing failed: {result['error']}")
        return False

if __name__ == "__main__":
    test_pdf()