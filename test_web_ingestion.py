#!/usr/bin/env python3
"""
Test web link ingestion functionality
"""

import asyncio
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_url_detection():
    """Test URL detection functionality"""
    from url_utils import extract_main_urls, is_url_extractable
    
    test_cases = [
        "Check out this article: https://example.com/article",
        "https://github.com/microsoft/playwright",
        "Visit www.python.org for more info",
        "Just some regular text without URLs",
        "Multiple links: https://docs.python.org and https://stackoverflow.com/questions/123"
    ]
    
    print("🔍 Testing URL Detection:")
    for i, text in enumerate(test_cases, 1):
        urls = extract_main_urls(text)
        print(f"{i}. Text: {text}")
        print(f"   URLs found: {urls}")
        for url in urls:
            extractable, reason = is_url_extractable(url)
            print(f"   - {url}: {'✅' if extractable else '❌'} {reason}")
        print()

def test_web_extractor():
    """Test web content extraction"""
    from web_extractor import extract_web_content_sync
    
    test_urls = [
        "https://httpbin.org/html",  # Simple HTML test page
        "https://example.com",       # Basic example page
    ]
    
    print("🌐 Testing Web Content Extraction:")
    for url in test_urls:
        print(f"Testing {url}...")
        try:
            result = extract_web_content_sync(url)
            print(f"  Success: {result.success}")
            if result.success:
                print(f"  Title: {result.title}")
                print(f"  Content length: {len(result.content) if result.content else 0} chars")
                print(f"  Screenshot: {'Yes' if result.screenshot_path else 'No'}")
                print(f"  Extraction time: {result.extraction_time:.2f}s")
            else:
                print(f"  Error: {result.error_message}")
        except Exception as e:
            print(f"  Exception: {e}")
        print()

async def test_async_extractor():
    """Test async web content extraction"""
    from web_extractor import extract_web_content
    
    print("⚡ Testing Async Web Content Extraction:")
    try:
        result = await extract_web_content("https://httpbin.org/html")
        print(f"  Success: {result.success}")
        if result.success:
            print(f"  Title: {result.title}")
            print(f"  Content preview: {result.text_content[:200]}...")
    except Exception as e:
        print(f"  Exception: {e}")

def main():
    print("🧪 Testing Web Link Ingestion System")
    print("=" * 50)
    
    # Test URL detection
    test_url_detection()
    
    # Test web content extraction  
    test_web_extractor()
    
    # Test async extraction
    print("Running async test...")
    try:
        asyncio.run(test_async_extractor())
    except Exception as e:
        print(f"Async test failed: {e}")
    
    print("=" * 50)
    print("✅ Web ingestion testing complete!")
    print("\n💡 To test end-to-end:")
    print("1. Start the server: uvicorn app:app --reload")
    print("2. Go to http://localhost:8000")
    print("3. Paste a URL in Quick Notes and submit")
    print("4. Check if web content is extracted automatically")

if __name__ == "__main__":
    main()