#!/usr/bin/env python3
"""
Web Content Extractor using Playwright
Simple implementation for Second Brain web link ingestion
"""

import asyncio
import logging
import time
import hashlib
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    from bs4 import BeautifulSoup
    from readability import Document
    import html2text
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from config import settings

logger = logging.getLogger(__name__)

@dataclass
class WebContent:
    """Extracted web content data"""
    url: str
    title: str
    content: str
    html: str
    text_content: str
    metadata: Dict[str, Any]
    screenshot_path: Optional[str]
    extraction_time: float
    success: bool
    error_message: str = ""

class WebContentExtractor:
    """Simple Playwright-based web content extraction"""
    
    def __init__(self):
        self.timeout = 30000  # 30 seconds
        self.wait_for = 'networkidle'
        self.user_agent = (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/91.0.4472.124 Safari/537.36'
        )
        
        # Screenshot settings
        self.screenshots_dir = settings.base_dir / "screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)
        
        # HTML to text converter
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = False
        self.h2t.body_width = 0  # Don't wrap lines
    
    async def extract_content(self, url: str) -> WebContent:
        """Extract content from a single URL"""
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not available")
            return WebContent(
                url=url, title="", content="", html="", text_content="",
                metadata={}, screenshot_path=None, extraction_time=0.0,
                success=False, error_message="Playwright not installed"
            )
        
        start_time = time.time()
        
        try:
            async with async_playwright() as p:
                # Launch browser
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=self.user_agent,
                    viewport={'width': 1280, 'height': 800}
                )
                
                page = await context.new_page()
                
                # Navigate to page
                logger.info(f"Extracting content from: {url}")
                response = await page.goto(url, timeout=self.timeout, wait_until=self.wait_for)
                
                if not response or response.status >= 400:
                    await browser.close()
                    return WebContent(
                        url=url, title="", content="", html="", text_content="",
                        metadata={}, screenshot_path=None, 
                        extraction_time=time.time() - start_time,
                        success=False, error_message=f"HTTP {response.status if response else 'No response'}"
                    )
                
                # Wait for page to be ready
                try:
                    await page.wait_for_load_state('networkidle', timeout=10000)
                except PlaywrightTimeoutError:
                    logger.warning(f"Network idle timeout for {url}, continuing...")
                
                # Extract content
                title = await page.title()
                html = await page.content()
                
                # Take screenshot
                screenshot_path = await self._capture_screenshot(page, url)
                
                await browser.close()
                
                # Process HTML content
                processed = self._process_html(html, url, title)
                
                extraction_time = time.time() - start_time
                logger.info(f"Extracted content from {url} in {extraction_time:.2f}s")
                
                return WebContent(
                    url=url,
                    title=processed['title'],
                    content=processed['content'],
                    html=html,
                    text_content=processed['text_content'],
                    metadata=processed['metadata'],
                    screenshot_path=screenshot_path,
                    extraction_time=extraction_time,
                    success=True
                )
                
        except PlaywrightTimeoutError:
            logger.error(f"Timeout extracting content from {url}")
            return WebContent(
                url=url, title="", content="", html="", text_content="",
                metadata={}, screenshot_path=None,
                extraction_time=time.time() - start_time,
                success=False, error_message="Timeout"
            )
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            return WebContent(
                url=url, title="", content="", html="", text_content="",
                metadata={}, screenshot_path=None,
                extraction_time=time.time() - start_time,
                success=False, error_message=str(e)
            )
    
    async def _capture_screenshot(self, page, url: str) -> Optional[str]:
        """Capture screenshot of the page"""
        try:
            # Generate filename from URL
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            timestamp = int(time.time())
            filename = f"web_{timestamp}_{url_hash}.jpg"
            screenshot_path = self.screenshots_dir / filename
            
            # Capture screenshot
            await page.screenshot(
                path=str(screenshot_path),
                type='jpeg',
                quality=85,
                full_page=True
            )
            
            logger.info(f"Screenshot saved: {screenshot_path}")
            return str(screenshot_path)
            
        except Exception as e:
            logger.error(f"Failed to capture screenshot for {url}: {e}")
            return None
    
    def _process_html(self, html: str, url: str, page_title: str) -> Dict[str, Any]:
        """Process HTML content to extract structured data"""
        try:
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                element.decompose()
            
            # Extract using readability
            doc = Document(html)
            main_content = doc.summary()
            main_title = doc.title() or page_title
            
            # Convert to text
            text_content = self.h2t.handle(main_content)
            
            # Extract metadata
            metadata = self._extract_metadata(soup, url)
            
            # Clean up content
            cleaned_content = self._clean_content(main_content)
            
            return {
                'title': main_title,
                'content': cleaned_content,
                'text_content': text_content,
                'metadata': metadata
            }
            
        except Exception as e:
            logger.error(f"Error processing HTML: {e}")
            # Fallback to basic extraction
            soup = BeautifulSoup(html, 'html.parser')
            title = page_title or "Untitled"
            
            # Get text content as fallback
            text_content = soup.get_text()
            # Clean up whitespace
            text_content = ' '.join(text_content.split())
            
            return {
                'title': title,
                'content': text_content[:2000] + "..." if len(text_content) > 2000 else text_content,
                'text_content': text_content,
                'metadata': {'url': url, 'extraction_method': 'fallback'}
            }
    
    def _extract_metadata(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract metadata from HTML"""
        metadata = {'url': url}
        
        # Meta tags
        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property')
            content = meta.get('content')
            
            if name and content:
                if name in ['description', 'author', 'keywords']:
                    metadata[name] = content
                elif name.startswith('og:'):
                    metadata[name] = content
                elif name.startswith('twitter:'):
                    metadata[name] = content
        
        # Canonical URL
        canonical = soup.find('link', rel='canonical')
        if canonical and canonical.get('href'):
            metadata['canonical_url'] = canonical['href']
        
        # Published date (various formats)
        date_selectors = [
            'meta[property="article:published_time"]',
            'meta[name="publishdate"]',
            'time[datetime]',
            '.published',
            '.date'
        ]
        
        for selector in date_selectors:
            element = soup.select_one(selector)
            if element:
                date_value = element.get('content') or element.get('datetime') or element.get_text()
                if date_value:
                    metadata['publish_date'] = date_value.strip()
                    break
        
        return metadata
    
    def _clean_content(self, content: str) -> str:
        """Clean HTML content for storage"""
        if not content:
            return ""
        
        # Parse and clean
        soup = BeautifulSoup(content, 'html.parser')
        
        # Remove unwanted attributes
        for tag in soup.find_all():
            # Keep only essential attributes
            keep_attrs = ['href', 'src', 'alt', 'title']
            attrs_to_remove = [attr for attr in tag.attrs if attr not in keep_attrs]
            for attr in attrs_to_remove:
                del tag[attr]
        
        # Convert back to string
        cleaned = str(soup)
        
        # Limit length
        if len(cleaned) > 50000:  # 50KB limit
            cleaned = cleaned[:50000] + "...\n[Content truncated]"
        
        return cleaned

# Global extractor instance
_extractor = None

def get_extractor() -> WebContentExtractor:
    """Get global web content extractor"""
    global _extractor
    if _extractor is None:
        _extractor = WebContentExtractor()
    return _extractor

async def extract_web_content(url: str) -> WebContent:
    """Simple function to extract web content from a URL"""
    extractor = get_extractor()
    return await extractor.extract_content(url)

# Synchronous wrapper for use in non-async contexts
def extract_web_content_sync(url: str) -> WebContent:
    """Synchronous wrapper for web content extraction"""
    try:
        # Try to get existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're already in an async context, need to create task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, extract_web_content(url))
                return future.result(timeout=60)
        else:
            # No running loop, we can use asyncio.run
            return asyncio.run(extract_web_content(url))
    except:
        # Fallback: create new event loop in thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, extract_web_content(url))
            return future.result(timeout=60)
