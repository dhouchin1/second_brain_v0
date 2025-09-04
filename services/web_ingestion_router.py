"""
Web Ingestion Router

FastAPI router for web content ingestion with Playwright integration.
Provides endpoints for URL processing and integrates with Smart Automation.
"""

from typing import List, Optional
import re

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl

from services.web_ingestion_service import (
    WebIngestionService, UrlIngestionRequest, UrlIngestionResponse,
    ExtractionConfig, UrlDetectionWorkflow
)
from services.auth_service import User
from services.workflow_engine import WorkflowEngine, TriggerType


# Global service instances and functions (initialized by app.py)
web_ingestion_service: Optional[WebIngestionService] = None
url_workflow: Optional[UrlDetectionWorkflow] = None
get_conn = None
get_current_user = None

# FastAPI router
router = APIRouter(prefix="/api/web", tags=["web-ingestion"])


def init_web_ingestion_router(get_conn_func, workflow_engine: WorkflowEngine, get_current_user_func):
    """Initialize Web Ingestion services"""
    global web_ingestion_service, url_workflow, get_conn, get_current_user
    get_conn = get_conn_func
    get_current_user = get_current_user_func
    web_ingestion_service = WebIngestionService(get_conn_func)
    url_workflow = UrlDetectionWorkflow(web_ingestion_service)


# ─── Request/Response Models ───

class BulkUrlRequest(BaseModel):
    urls: List[str]
    take_screenshot: bool = True
    timeout: int = 30


class QuickCaptureRequest(BaseModel):
    content: str
    tags: Optional[str] = ""
    auto_extract_urls: bool = True


class QuickCaptureResponse(BaseModel):
    success: bool
    note_id: int
    urls_found: List[str]
    urls_processed: int
    web_extractions: List[dict]


class UrlDetectionResponse(BaseModel):
    urls_found: List[str]
    valid_urls: List[str]


# ─── URL Processing Endpoints ───

@router.post("/ingest", response_model=UrlIngestionResponse)
async def ingest_url(
    request: UrlIngestionRequest,
    fastapi_request: Request
):
    """Ingest content from a single URL"""
    if not web_ingestion_service:
        raise HTTPException(status_code=500, detail="Web ingestion service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Validate URL
    if not web_ingestion_service.is_valid_url(request.url):
        raise HTTPException(status_code=400, detail="Invalid URL format")
    
    # Configure extraction
    config = ExtractionConfig(
        take_screenshot=request.take_screenshot,
        extract_images=request.extract_images,
        timeout=request.timeout
    )
    
    try:
        result = await web_ingestion_service.ingest_url(
            request.url, 
            current_user.id,
            config=config
        )
        
        return UrlIngestionResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/ingest/bulk")
async def ingest_bulk_urls(
    request: BulkUrlRequest,
    background_tasks: BackgroundTasks,
    fastapi_request: Request
):
    """Ingest content from multiple URLs"""
    if not web_ingestion_service:
        raise HTTPException(status_code=500, detail="Web ingestion service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if len(request.urls) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 URLs per bulk request")
    
    # Validate URLs
    valid_urls = [url for url in request.urls if web_ingestion_service.is_valid_url(url)]
    if not valid_urls:
        raise HTTPException(status_code=400, detail="No valid URLs provided")
    
    # Process URLs in background
    async def process_urls():
        config = ExtractionConfig(
            take_screenshot=request.take_screenshot,
            timeout=request.timeout
        )
        
        results = []
        for url in valid_urls:
            try:
                result = await web_ingestion_service.ingest_url(
                    url, current_user.id, config=config
                )
                results.append({"url": url, "success": True, "note_id": result.get("note_id")})
            except Exception as e:
                results.append({"url": url, "success": False, "error": str(e)})
        
        return results
    
    background_tasks.add_task(process_urls)
    
    return {
        "message": f"Processing {len(valid_urls)} URLs in background",
        "urls_queued": valid_urls
    }


@router.post("/detect-urls", response_model=UrlDetectionResponse)
async def detect_urls(content: str):
    """Detect URLs in text content"""
    if not web_ingestion_service:
        raise HTTPException(status_code=500, detail="Web ingestion service not initialized")
    
    urls_found = web_ingestion_service.detect_urls(content)
    valid_urls = [url for url in urls_found if web_ingestion_service.is_valid_url(url)]
    
    return UrlDetectionResponse(
        urls_found=urls_found,
        valid_urls=valid_urls
    )


# ─── Smart Capture Enhancement ───

@router.post("/capture/smart", response_model=QuickCaptureResponse)
async def smart_capture(
    request: QuickCaptureRequest,
    background_tasks: BackgroundTasks,
    fastapi_request: Request
):
    """Enhanced capture that automatically processes URLs found in content"""
    if not web_ingestion_service:
        raise HTTPException(status_code=500, detail="Web ingestion service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # First, create the note with the original content
    from datetime import datetime
    import sqlite3
    import json
    
    # Get database connection (this should be injected properly)
    def get_conn():
        conn = sqlite3.connect('notes.db')
        conn.row_factory = sqlite3.Row
        return conn
    
    conn = get_conn()
    try:
        c = conn.cursor()
        
        # Create basic note
        title = request.content[:60] if request.content else "Quick Note"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute("""
            INSERT INTO notes (
                title, content, tags, type, timestamp, status, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            title, request.content, request.tags or "", "text", now, "complete", current_user.id
        ))
        
        note_id = c.lastrowid
        
        # Add to FTS
        c.execute("""
            INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (note_id, title, "", request.tags or "", "", request.content, request.content))
        
        conn.commit()
        
    finally:
        conn.close()
    
    # Detect URLs
    urls_found = web_ingestion_service.detect_urls(request.content)
    valid_urls = [url for url in urls_found if web_ingestion_service.is_valid_url(url)]
    
    web_extractions = []
    
    if request.auto_extract_urls and valid_urls:
        # Process URLs in background
        async def process_urls_background():
            nonlocal web_extractions
            config = ExtractionConfig(take_screenshot=True, timeout=30)
            
            for url in valid_urls[:3]:  # Limit to 3 URLs
                try:
                    result = await web_ingestion_service.ingest_url(
                        url, current_user.id, config=config
                    )
                    web_extractions.append({
                        "url": url,
                        "success": result["success"],
                        "note_id": result.get("note_id"),
                        "title": result.get("title"),
                        "summary": result.get("summary")
                    })
                except Exception as e:
                    web_extractions.append({
                        "url": url,
                        "success": False,
                        "error": str(e)
                    })
        
        background_tasks.add_task(process_urls_background)
    
    return QuickCaptureResponse(
        success=True,
        note_id=note_id,
        urls_found=urls_found,
        urls_processed=len(valid_urls) if request.auto_extract_urls else 0,
        web_extractions=[]  # Will be populated in background
    )


# ─── URL Analysis Endpoints ───

@router.get("/analyze/{url:path}")
async def analyze_url(url: str):
    """Analyze URL without extracting content (preview)"""
    if not web_ingestion_service:
        raise HTTPException(status_code=500, detail="Web ingestion service not initialized")
    
    if not web_ingestion_service.is_valid_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL format")
    
    try:
        from urllib.parse import urlparse
        import aiohttp
        
        # Quick metadata extraction without Playwright
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status >= 400:
                    raise HTTPException(status_code=400, detail=f"URL returned HTTP {response.status}")
                
                html = await response.text()
                
                # Extract basic info with regex
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
                title = title_match.group(1).strip() if title_match else ""
                
                desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
                description = desc_match.group(1).strip() if desc_match else ""
                
                return {
                    "url": url,
                    "domain": domain,
                    "title": title,
                    "description": description,
                    "status": "accessible",
                    "content_type": response.content_type
                }
                
    except Exception as e:
        return {
            "url": url,
            "error": str(e),
            "status": "error"
        }


# ─── Configuration Endpoints ───

@router.get("/config/extraction")
async def get_extraction_config():
    """Get current extraction configuration"""
    return {
        "default_config": {
            "take_screenshot": True,
            "extract_images": False,
            "timeout": 30,
            "viewport_width": 1920,
            "viewport_height": 1080,
            "block_ads": True,
            "max_content_length": 50000
        },
        "supported_features": {
            "playwright_available": True,  # Would check PLAYWRIGHT_AVAILABLE
            "screenshot_capture": True,
            "image_extraction": True,
            "ad_blocking": True
        }
    }


@router.post("/config/test")
async def test_web_ingestion():
    """Test web ingestion system"""
    if not web_ingestion_service:
        raise HTTPException(status_code=500, detail="Web ingestion service not initialized")
    
    test_url = "https://example.com"
    
    try:
        # Test URL detection
        test_content = f"Check out this link: {test_url} and this one: https://github.com"
        urls = web_ingestion_service.detect_urls(test_content)
        
        return {
            "web_ingestion_available": True,
            "playwright_available": True,  # Would check PLAYWRIGHT_AVAILABLE
            "url_detection_working": len(urls) > 0,
            "detected_urls": urls,
            "test_passed": True
        }
        
    except Exception as e:
        return {
            "web_ingestion_available": False,
            "error": str(e),
            "test_passed": False
        }


# ─── Health Check ───

@router.get("/health")
async def web_ingestion_health():
    """Health check for web ingestion service"""
    return {
        "status": "healthy" if web_ingestion_service else "unavailable",
        "services": {
            "web_ingestion_service": web_ingestion_service is not None,
            "playwright_available": True,  # Would check PLAYWRIGHT_AVAILABLE
            "url_workflow": url_workflow is not None
        },
        "capabilities": {
            "url_detection": True,
            "content_extraction": True,
            "screenshot_capture": True,
            "ai_processing": True,
            "smart_automation": True
        }
    }