"""
Web Content Ingestion Service

Intelligent web content extraction using Playwright with AI-powered processing.
Integrates with Smart Automation system for seamless URL-to-knowledge conversion.
"""

from __future__ import annotations
import asyncio
import json
import re
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urljoin
import base64

try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[web_ingestion] Playwright not available. Install with: pip install playwright")

import sqlite3
from pydantic import BaseModel

from config import settings
from llm_utils import ollama_summarize, ollama_generate_title


@dataclass
class WebContent:
    """Extracted web content data"""
    url: str
    title: str
    content: str
    summary: str
    metadata: Dict[str, Any]
    screenshot_path: Optional[str] = None
    extracted_at: datetime = None
    content_hash: Optional[str] = None


@dataclass
class ExtractionConfig:
    """Configuration for web content extraction"""
    take_screenshot: bool = True
    extract_images: bool = False
    follow_redirects: bool = True
    timeout: int = 30
    viewport_width: int = 1920
    viewport_height: int = 1080
    user_agent: str = "Second Brain Web Ingestion Bot 1.0"
    block_ads: bool = True
    extract_links: bool = True
    max_content_length: int = 50000


class WebContentExtractor:
    """Playwright-based web content extraction"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not available")
            
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-images' if not True else '',  # Can be configured
            ]
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def extract_content(self, url: str, config: ExtractionConfig = None) -> WebContent:
        """Extract content from a web page"""
        config = config or ExtractionConfig()
        
        page = await self.browser.new_page(
            viewport={'width': config.viewport_width, 'height': config.viewport_height},
            user_agent=config.user_agent
        )
        
        try:
            # Block ads and trackers if requested
            if config.block_ads:
                await page.route("**/*", self._block_ads_handler)
            
            # Navigate to page
            response = await page.goto(
                url, 
                wait_until='networkidle',
                timeout=config.timeout * 1000
            )
            
            if not response or response.status >= 400:
                raise Exception(f"Failed to load page: HTTP {response.status if response else 'No response'}")
            
            # Get final URL after redirects
            final_url = page.url
            
            # Extract basic metadata
            title = await page.title() or ""
            
            # Try to get meta description
            description_element = await page.query_selector('meta[name="description"]')
            description = ""
            if description_element:
                description = await description_element.get_attribute('content') or ""
            
            # Extract main content using multiple strategies
            content = await self._extract_main_content(page)
            
            # Extract additional metadata
            metadata = await self._extract_metadata(page, final_url)
            
            # Take screenshot if requested
            screenshot_path = None
            if config.take_screenshot:
                screenshot_path = await self._take_screenshot(page, final_url)
            
            # Generate content hash
            content_hash = hashlib.sha256((title + content).encode()).hexdigest()[:16]
            
            return WebContent(
                url=final_url,
                title=title,
                content=content,
                summary=description,
                metadata=metadata,
                screenshot_path=screenshot_path,
                extracted_at=datetime.now(),
                content_hash=content_hash
            )
            
        finally:
            await page.close()
    
    async def _block_ads_handler(self, route):
        """Block ads and tracking requests"""
        url = route.request.url
        
        # Block known ad/tracking domains and resources
        blocked_patterns = [
            'googletagmanager.com',
            'google-analytics.com',
            'googlesyndication.com',
            'doubleclick.net',
            'facebook.com/tr',
            'twitter.com/i/adsct',
            'ads',
            'analytics',
            'tracking',
            '.gif',
            'pixel'
        ]
        
        if any(pattern in url.lower() for pattern in blocked_patterns):
            await route.abort()
        else:
            await route.continue_()
    
    async def _extract_main_content(self, page: Page) -> str:
        """Extract main content using multiple strategies"""
        content_selectors = [
            'article',
            '[role="main"]',
            'main',
            '.content',
            '.post-content',
            '.entry-content',
            '.article-content',
            '.story-body',
            '.post-body',
            '#content',
            '.container .row .col'
        ]
        
        # Try structured content extraction first
        for selector in content_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    content = await element.inner_text()
                    if len(content.strip()) > 200:  # Minimum content length
                        return self._clean_content(content)
            except:
                continue
        
        # Fallback: extract from body but try to avoid navigation/sidebar content
        try:
            # Remove navigation, sidebar, and footer elements
            await page.evaluate("""
                () => {
                    const selectorsToRemove = [
                        'nav', 'header', 'footer', '.nav', '.navigation', 
                        '.sidebar', '.menu', '.ads', '.advertisement',
                        '.social', '.comments', '.related', '.recommendations'
                    ];
                    selectorsToRemove.forEach(selector => {
                        document.querySelectorAll(selector).forEach(el => el.remove());
                    });
                }
            """)
            
            # Get remaining body content
            body_content = await page.evaluate("document.body.innerText")
            return self._clean_content(body_content)
            
        except:
            # Ultimate fallback
            return await page.inner_text('body') or ""
    
    def _clean_content(self, content: str) -> str:
        """Clean extracted content"""
        if not content:
            return ""
        
        # Remove excessive whitespace
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        content = re.sub(r' +', ' ', content)
        content = content.strip()
        
        # Remove common footer/header patterns
        patterns_to_remove = [
            r'Cookie[s]?\s+Policy.*',
            r'Privacy\s+Policy.*',
            r'Terms\s+of\s+Service.*',
            r'Subscribe\s+to.*',
            r'Follow\s+us.*',
            r'Share\s+this.*',
        ]
        
        for pattern in patterns_to_remove:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)
        
        return content
    
    async def _extract_metadata(self, page: Page, url: str) -> Dict[str, Any]:
        """Extract metadata from the page"""
        metadata = {
            'domain': urlparse(url).netloc,
            'extracted_at': datetime.now().isoformat(),
            'final_url': url
        }
        
        # Extract Open Graph metadata
        og_tags = await page.evaluate("""
            () => {
                const og = {};
                const ogTags = document.querySelectorAll('meta[property^="og:"]');
                ogTags.forEach(tag => {
                    const property = tag.getAttribute('property');
                    const content = tag.getAttribute('content');
                    if (property && content) {
                        og[property.replace('og:', '')] = content;
                    }
                });
                return og;
            }
        """)
        
        metadata['open_graph'] = og_tags
        
        # Extract other meta tags
        meta_tags = await page.evaluate("""
            () => {
                const meta = {};
                const metaTags = document.querySelectorAll('meta[name]');
                metaTags.forEach(tag => {
                    const name = tag.getAttribute('name');
                    const content = tag.getAttribute('content');
                    if (name && content) {
                        meta[name] = content;
                    }
                });
                return meta;
            }
        """)
        
        metadata['meta_tags'] = meta_tags
        
        # Extract author information
        author_selectors = [
            '.author',
            '.byline',
            '[rel="author"]',
            '.post-author',
            '.article-author'
        ]
        
        for selector in author_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    author = await element.inner_text()
                    if author:
                        metadata['author'] = author.strip()
                        break
            except:
                continue
        
        # Extract publish date
        date_selectors = [
            'time[datetime]',
            '.published',
            '.post-date',
            '.article-date',
            '.date'
        ]
        
        for selector in date_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    # Try datetime attribute first
                    date_attr = await element.get_attribute('datetime')
                    if date_attr:
                        metadata['published_date'] = date_attr
                        break
                    # Fallback to text content
                    date_text = await element.inner_text()
                    if date_text:
                        metadata['published_date'] = date_text.strip()
                        break
            except:
                continue
        
        return metadata
    
    async def _take_screenshot(self, page: Page, url: str) -> Optional[str]:
        """Take a screenshot of the page"""
        try:
            # Create screenshots directory
            screenshots_dir = Path(settings.base_dir) / "screenshots"
            screenshots_dir.mkdir(exist_ok=True)
            
            # Generate filename
            url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"web_{timestamp}_{url_hash}.png"
            
            screenshot_path = screenshots_dir / filename
            
            # Take screenshot
            await page.screenshot(
                path=str(screenshot_path),
                full_page=True,
                type='png'
            )
            
            return str(screenshot_path)
            
        except Exception as e:
            print(f"[web_ingestion] Screenshot failed: {e}")
            return None


class WebIngestionService:
    """Main web content ingestion service"""
    
    def __init__(self, get_conn_func: Callable[[], sqlite3.Connection]):
        self.get_conn = get_conn_func
        
    async def ingest_url(self, url: str, user_id: int, note_id: Optional[int] = None, 
                        config: ExtractionConfig = None) -> Dict[str, Any]:
        """Ingest content from a URL"""
        config = config or ExtractionConfig()
        
        if not PLAYWRIGHT_AVAILABLE:
            return {
                "success": False,
                "error": "Playwright not available. Install with: pip install playwright"
            }
        
        try:
            # Extract web content
            async with WebContentExtractor() as extractor:
                web_content = await extractor.extract_content(url, config)
            
            # Process with AI
            ai_results = await self._process_with_ai(web_content)
            
            # Store in database
            stored_note_id = await self._store_content(
                web_content, ai_results, user_id, note_id
            )
            
            return {
                "success": True,
                "note_id": stored_note_id,
                "title": web_content.title,
                "content_length": len(web_content.content),
                "summary": ai_results.get("summary", ""),
                "tags": ai_results.get("tags", []),
                "screenshot_path": web_content.screenshot_path,
                "metadata": web_content.metadata
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _process_with_ai(self, web_content: WebContent) -> Dict[str, Any]:
        """Process web content with local LLM"""
        try:
            # Create a comprehensive prompt for the LLM
            prompt_content = f"""
            Title: {web_content.title}
            URL: {web_content.url}
            Domain: {web_content.metadata.get('domain', '')}
            
            Content:
            {web_content.content[:10000]}  # Limit content for LLM
            """
            
            # Get AI summary and analysis
            ai_result = ollama_summarize(prompt_content)
            
            # Enhanced processing for web content
            enhanced_prompt = f"""
            Analyze this web content and provide:
            1. A concise summary (2-3 sentences)
            2. Key topics/themes
            3. Relevant tags (3-5 tags)
            4. Content type (article, blog, tutorial, news, etc.)
            5. Notable quotes or key points
            
            Content: {prompt_content}
            """
            
            # Get enhanced analysis
            try:
                enhanced_result = ollama_summarize(enhanced_prompt)
                
                return {
                    "summary": enhanced_result.get("summary", ai_result.get("summary", "")),
                    "tags": enhanced_result.get("tags", ai_result.get("tags", [])),
                    "content_type": enhanced_result.get("content_type", "web_content"),
                    "key_points": enhanced_result.get("key_points", []),
                    "ai_analysis": enhanced_result
                }
            except:
                # Fallback to basic AI result
                return {
                    "summary": ai_result.get("summary", ""),
                    "tags": ai_result.get("tags", []),
                    "content_type": "web_content",
                    "key_points": [],
                    "ai_analysis": ai_result
                }
                
        except Exception as e:
            print(f"[web_ingestion] AI processing failed: {e}")
            return {
                "summary": web_content.summary or "Web content extracted",
                "tags": [],
                "content_type": "web_content",
                "key_points": [],
                "ai_analysis": {}
            }
    
    async def _store_content(self, web_content: WebContent, ai_results: Dict[str, Any], 
                           user_id: int, note_id: Optional[int] = None) -> int:
        """Store web content in database"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            # Prepare data
            title = web_content.title or f"Web Content from {web_content.metadata.get('domain', 'Unknown')}"
            summary = ai_results.get("summary", "")
            tags = ",".join(ai_results.get("tags", []))
            content_type = ai_results.get("content_type", "web_content")
            
            # Prepare metadata
            file_metadata = {
                "source_url": web_content.url,
                "domain": web_content.metadata.get("domain"),
                "extracted_at": web_content.extracted_at.isoformat(),
                "content_hash": web_content.content_hash,
                "screenshot_path": web_content.screenshot_path,
                "metadata": web_content.metadata,
                "ai_analysis": ai_results.get("ai_analysis", {})
            }
            
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if note_id:
                # Update existing note
                c.execute("""
                    UPDATE notes SET
                        title = ?, content = ?, summary = ?, tags = ?, 
                        type = ?, file_metadata = ?, updated_at = datetime('now')
                    WHERE id = ? AND user_id = ?
                """, (
                    title, web_content.content, summary, tags,
                    content_type, json.dumps(file_metadata), note_id, user_id
                ))
                final_note_id = note_id
            else:
                # Create new note
                c.execute("""
                    INSERT INTO notes (
                        title, content, summary, tags, actions, type, timestamp,
                        file_metadata, status, user_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    title, web_content.content, summary, tags, "",
                    content_type, now, json.dumps(file_metadata),
                    "complete", user_id
                ))
                final_note_id = c.lastrowid
                
                # Add to FTS index
                c.execute("""
                    INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    final_note_id, title, summary, tags, "",
                    web_content.content, web_content.content
                ))
            
            conn.commit()
            return final_note_id
            
        finally:
            conn.close()
    
    def detect_urls(self, text: str) -> List[str]:
        """Detect URLs in text"""
        url_pattern = re.compile(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        )
        return url_pattern.findall(text)
    
    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and accessible"""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ['http', 'https'] and parsed.netloc
        except:
            return False


# Integration with Smart Automation System
class UrlDetectionWorkflow:
    """Workflow for automatic URL detection and processing"""
    
    def __init__(self, web_ingestion_service: WebIngestionService):
        self.web_service = web_ingestion_service
    
    async def process_content_for_urls(self, content_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process content and extract any URLs found"""
        content = content_data.get("content", "")
        user_id = content_data.get("user_id")
        note_id = content_data.get("note_id")
        
        if not content or not user_id:
            return {"urls_processed": 0, "results": []}
        
        # Detect URLs
        urls = self.web_service.detect_urls(content)
        valid_urls = [url for url in urls if self.web_service.is_valid_url(url)]
        
        if not valid_urls:
            return {"urls_processed": 0, "results": []}
        
        # Process URLs
        results = []
        for url in valid_urls[:3]:  # Limit to first 3 URLs to avoid overload
            try:
                result = await self.web_service.ingest_url(url, user_id)
                results.append({
                    "url": url,
                    "success": result["success"],
                    "note_id": result.get("note_id"),
                    "title": result.get("title", ""),
                    "error": result.get("error")
                })
            except Exception as e:
                results.append({
                    "url": url,
                    "success": False,
                    "error": str(e)
                })
        
        return {
            "urls_processed": len(results),
            "results": results
        }


# API Models
class UrlIngestionRequest(BaseModel):
    url: str
    take_screenshot: bool = True
    extract_images: bool = False
    timeout: int = 30


class UrlIngestionResponse(BaseModel):
    success: bool
    note_id: Optional[int] = None
    title: Optional[str] = None
    content_length: Optional[int] = None
    summary: Optional[str] = None
    tags: List[str] = []
    screenshot_path: Optional[str] = None
    error: Optional[str] = None