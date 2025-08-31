#!/usr/bin/env python3
"""
Test capture endpoint directly to verify web link ingestion
"""
import sqlite3
import asyncio
import sys
import os

# Add the current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from url_utils import extract_main_urls
from web_extractor import extract_web_content_sync

def test_url_processing():
    """Test the URL processing logic from the capture endpoint"""
    
    test_content = "Check out this interesting article: https://example.com"
    
    print("🔗 Testing URL Detection in Capture Content:")
    print(f"Content: {test_content}")
    
    # Extract URLs
    urls = extract_main_urls(test_content)
    print(f"URLs detected: {urls}")
    
    if urls:
        url = urls[0]
        print(f"Processing URL: {url}")
        
        # Extract web content
        print("🌐 Extracting web content...")
        web_result = extract_web_content_sync(url)
        
        print(f"Success: {web_result.success}")
        if web_result.success:
            print(f"Title: {web_result.title}")
            print(f"Content length: {len(web_result.content) if web_result.content else 0}")
            print(f"Screenshot: {web_result.screenshot_path}")
            print(f"Extraction time: {web_result.extraction_time:.2f}s")
            
            # Simulate database insertion (as done in capture endpoint)
            import hashlib
            content_hash = hashlib.sha256(web_result.content.encode()).hexdigest()[:16]
            
            print("\n📝 Simulating database insertion:")
            print(f"note_type: web_content")
            print(f"source_url: {url}")
            print(f"screenshot_path: {web_result.screenshot_path}")
            print(f"content_hash: {content_hash}")
            print(f"extracted_text length: {len(web_result.content) if web_result.content else 0}")
            
            # Check if screenshot file exists
            if web_result.screenshot_path and os.path.exists(web_result.screenshot_path):
                file_size = os.path.getsize(web_result.screenshot_path)
                print(f"Screenshot file size: {file_size} bytes")
            
        else:
            print(f"Error: {web_result.error_message}")
    else:
        print("No URLs found in content")

def test_database_schema():
    """Verify the database has the required web content columns"""
    print("\n🗄️ Checking database schema:")
    
    conn = sqlite3.connect('notes.db')
    cursor = conn.cursor()
    
    # Check if web columns exist
    cursor.execute("PRAGMA table_info(notes)")
    columns = cursor.fetchall()
    
    required_columns = ['source_url', 'web_metadata', 'screenshot_path', 'content_hash']
    existing_columns = [col[1] for col in columns]
    
    for col in required_columns:
        if col in existing_columns:
            print(f"✅ {col} column exists")
        else:
            print(f"❌ {col} column missing")
    
    conn.close()

if __name__ == "__main__":
    print("🧪 Testing Direct Web Link Ingestion Logic")
    print("=" * 50)
    
    test_url_processing()
    test_database_schema()
    
    print("\n" + "=" * 50)
    print("✅ Direct testing complete!")