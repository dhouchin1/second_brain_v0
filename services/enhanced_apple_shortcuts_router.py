# ──────────────────────────────────────────────────────────────────────────────
# File: services/enhanced_apple_shortcuts_router.py
# ──────────────────────────────────────────────────────────────────────────────
"""
Enhanced Apple Shortcuts API Router

Advanced REST endpoints for iOS/macOS Shortcuts integration including voice memos,
photo OCR, location-based notes, and deep iOS integration.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging

from services.enhanced_apple_shortcuts_service import get_enhanced_apple_shortcuts_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shortcuts", tags=["apple-shortcuts-enhanced"])

class VoiceMemoRequest(BaseModel):
    """Voice memo capture request."""
    audio_data: Optional[str] = None
    audio_url: Optional[str] = None  
    transcription: str
    location_data: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None

class PhotoOCRRequest(BaseModel):
    """Photo OCR processing request."""
    image_data: str
    location_data: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None

class QuickNoteRequest(BaseModel):
    """Quick note capture request."""
    text: str
    note_type: str = "thought"
    location_data: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    auto_tag: bool = True

class WebClipRequest(BaseModel):
    """Web clip capture request."""
    url: str
    selected_text: Optional[str] = None
    page_title: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

# Global service instance
_service = None

def init_enhanced_apple_shortcuts_router(get_conn_func):
    """Initialize the router with database connection."""
    global _service
    _service = get_enhanced_apple_shortcuts_service(get_conn_func)

@router.get("/templates")
async def get_shortcut_templates():
    """Get pre-built iOS Shortcuts templates and examples."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        templates = _service.get_shortcut_templates()
        
        return JSONResponse(content={
            "success": True,
            "templates": templates,
            "total": len(templates),
            "message": "Shortcut templates retrieved successfully"
        })
        
    except Exception as e:
        logger.error(f"Failed to get shortcut templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/voice-memo")
async def process_voice_memo(request: VoiceMemoRequest):
    """
    Process voice memo from iOS Shortcuts.
    
    Supports:
    - Pre-transcribed text from iOS
    - Audio data for server-side transcription
    - Location and context information
    - AI-powered summarization and tagging
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        result = await _service.process_voice_memo(
            audio_data=request.audio_data,
            audio_url=request.audio_url,
            transcription=request.transcription,
            location_data=request.location_data,
            context=request.context
        )
        
        if result["success"]:
            return JSONResponse(content={
                "success": True,
                "note_id": result["note_id"],
                "title": result["title"],
                "summary": result.get("summary"),
                "action_items": result.get("action_items", []),
                "tags": result["tags"],
                "message": result["message"]
            })
        else:
            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "error": result["error"]
                }
            )
            
    except Exception as e:
        logger.error(f"Voice memo processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/photo-ocr")
async def process_photo_ocr(request: PhotoOCRRequest):
    """
    Process photo with OCR from iOS Shortcuts.
    
    Features:
    - OCR text extraction from photos
    - Location tagging
    - Context preservation
    - AI-powered content processing
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        result = await _service.process_photo_ocr(
            image_data=request.image_data,
            location_data=request.location_data,
            context=request.context
        )
        
        if result["success"]:
            return JSONResponse(content={
                "success": True,
                "note_id": result["note_id"],
                "title": result["title"],
                "extracted_text": result["extracted_text"],
                "tags": result["tags"],
                "message": result["message"]
            })
        else:
            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "error": result["error"]
                }
            )
            
    except Exception as e:
        logger.error(f"Photo OCR processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/quick-note")
async def process_quick_note(request: QuickNoteRequest):
    """
    Process quick note from iOS Shortcuts.
    
    Note types supported:
    - thought: Random thoughts and ideas
    - task: Action items and todos
    - meeting: Meeting-related notes
    - idea: Creative ideas and insights
    - reminder: Things to remember
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        result = await _service.process_quick_note(
            text=request.text,
            note_type=request.note_type,
            location_data=request.location_data,
            context=request.context,
            auto_tag=request.auto_tag
        )
        
        if result["success"]:
            return JSONResponse(content={
                "success": True,
                "note_id": result["note_id"],
                "title": result["title"],
                "tags": result["tags"],
                "message": result["message"]
            })
        else:
            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "error": result["error"]
                }
            )
            
    except Exception as e:
        logger.error(f"Quick note processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/web-clip")
async def process_web_clip(request: WebClipRequest):
    """
    Process web clip from iOS Safari Share Sheet.
    
    Features:
    - Full page content extraction
    - Selected text capture
    - Context preservation
    - AI-powered summarization
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        result = await _service.process_web_clip(
            url=request.url,
            selected_text=request.selected_text,
            page_title=request.page_title,
            context=request.context
        )
        
        if result["success"]:
            return JSONResponse(content={
                "success": True,
                "note_id": result["note_id"],
                "title": result["title"],
                "content_type": result["content_type"],
                "message": result["message"]
            })
        else:
            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "error": result["error"]
                }
            )
            
    except Exception as e:
        logger.error(f"Web clip processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_shortcuts_stats():
    """Get statistics about iOS Shortcuts usage."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        conn = _service.get_conn()
        cursor = conn.cursor()
        
        # Get shortcuts content statistics
        cursor.execute("""
            SELECT 
                json_extract(metadata, '$.source') as source,
                json_extract(metadata, '$.content_type') as content_type,
                COUNT(*) as count
            FROM notes 
            WHERE json_extract(metadata, '$.source') = 'ios_shortcuts'
            GROUP BY content_type
            ORDER BY count DESC
        """)
        
        content_types = {}
        for row in cursor.fetchall():
            content_types[row[1]] = row[2]
        
        # Get recent shortcuts captures
        cursor.execute("""
            SELECT title, created_at, json_extract(metadata, '$.content_type') as content_type
            FROM notes 
            WHERE json_extract(metadata, '$.source') = 'ios_shortcuts'
            ORDER BY created_at DESC
            LIMIT 10
        """)
        
        recent_captures = [
            {
                "title": row[0],
                "created_at": row[1],
                "content_type": row[2]
            }
            for row in cursor.fetchall()
        ]
        
        # Get usage by day (last 7 days)
        cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM notes 
            WHERE json_extract(metadata, '$.source') = 'ios_shortcuts'
            AND DATE(created_at) >= DATE('now', '-7 days')
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """)
        
        daily_usage = dict(cursor.fetchall())
        
        conn.close()
        
        return JSONResponse(content={
            "success": True,
            "data": {
                "content_types": content_types,
                "recent_captures": recent_captures,
                "daily_usage_7_days": daily_usage,
                "total_shortcuts_notes": sum(content_types.values())
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get shortcuts stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    """Health check for iOS Shortcuts integration."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return JSONResponse(content={
        "success": True,
        "service": "enhanced_apple_shortcuts",
        "status": "healthy",
        "features": {
            "voice_memos": True,
            "photo_ocr": True,
            "quick_notes": True,
            "web_clips": True,
            "location_support": True,
            "ai_processing": True
        }
    })

@router.post("/reading-list")
async def process_reading_list(request: Request):
    """Process reading list article from Safari."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        data = await request.json()
        result = await _service.process_reading_list(
            url=data.get("url"),
            title=data.get("title"),
            preview_text=data.get("preview_text"),
            added_date=data.get("added_date"),
            context=data.get("context")
        )

        if result["success"]:
            return JSONResponse(content=result)
        else:
            return JSONResponse(status_code=422, content=result)
    except Exception as e:
        logger.error(f"Reading list processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/contact-note")
async def process_contact_note(request: Request):
    """Create note about a contact/person."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        data = await request.json()
        result = await _service.process_contact_note(
            contact_name=data.get("contact_name"),
            contact_info=data.get("contact_info"),
            note_text=data.get("note_text", ""),
            meeting_context=data.get("meeting_context"),
            location_data=data.get("location_data")
        )

        if result["success"]:
            return JSONResponse(content=result)
        else:
            return JSONResponse(status_code=422, content=result)
    except Exception as e:
        logger.error(f"Contact note processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/media-note")
async def process_media_note(request: Request):
    """Create note about book, movie, podcast, etc."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        data = await request.json()
        result = await _service.process_media_note(
            media_type=data.get("media_type"),
            title=data.get("title"),
            creator=data.get("creator"),
            notes=data.get("notes", ""),
            rating=data.get("rating"),
            tags_custom=data.get("tags_custom"),
            metadata_extra=data.get("metadata_extra")
        )

        if result["success"]:
            return JSONResponse(content=result)
        else:
            return JSONResponse(status_code=422, content=result)
    except Exception as e:
        logger.error(f"Media note processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/recipe")
async def process_recipe(request: Request):
    """Save recipe with structured data."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        data = await request.json()
        result = await _service.process_recipe(
            recipe_name=data.get("recipe_name"),
            ingredients=data.get("ingredients", []),
            instructions=data.get("instructions", []),
            prep_time=data.get("prep_time"),
            cook_time=data.get("cook_time"),
            servings=data.get("servings"),
            source_url=data.get("source_url"),
            tags_custom=data.get("tags_custom"),
            image_data=data.get("image_data")
        )

        if result["success"]:
            return JSONResponse(content=result)
        else:
            return JSONResponse(status_code=422, content=result)
    except Exception as e:
        logger.error(f"Recipe processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dream-journal")
async def process_dream_journal(request: Request):
    """Log dream journal entry."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        data = await request.json()
        result = await _service.process_dream_journal(
            dream_text=data.get("dream_text"),
            emotions=data.get("emotions"),
            themes=data.get("themes"),
            lucid=data.get("lucid", False),
            sleep_quality=data.get("sleep_quality")
        )

        if result["success"]:
            return JSONResponse(content=result)
        else:
            return JSONResponse(status_code=422, content=result)
    except Exception as e:
        logger.error(f"Dream journal processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/quote")
async def process_quote(request: Request):
    """Save inspirational quote with attribution."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        data = await request.json()
        result = await _service.process_quote(
            quote_text=data.get("quote_text"),
            author=data.get("author"),
            source=data.get("source"),
            category=data.get("category"),
            reflection=data.get("reflection"),
            context=data.get("context")
        )

        if result["success"]:
            return JSONResponse(content=result)
        else:
            return JSONResponse(status_code=422, content=result)
    except Exception as e:
        logger.error(f"Quote processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/code-snippet")
async def process_code_snippet(request: Request):
    """Save code snippet with syntax highlighting."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        data = await request.json()
        result = await _service.process_code_snippet(
            code=data.get("code"),
            language=data.get("language"),
            description=data.get("description"),
            tags_custom=data.get("tags_custom"),
            source_url=data.get("source_url")
        )

        if result["success"]:
            return JSONResponse(content=result)
        else:
            return JSONResponse(status_code=422, content=result)
    except Exception as e:
        logger.error(f"Code snippet processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/travel-journal")
async def process_travel_journal(request: Request):
    """Create travel journal entry with rich location data."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        data = await request.json()
        result = await _service.process_travel_journal(
            entry_text=data.get("entry_text"),
            location_data=data.get("location_data"),
            photos=data.get("photos"),
            activity_type=data.get("activity_type"),
            companions=data.get("companions"),
            expenses=data.get("expenses")
        )

        if result["success"]:
            return JSONResponse(content=result)
        else:
            return JSONResponse(status_code=422, content=result)
    except Exception as e:
        logger.error(f"Travel journal processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/habit-log")
async def process_habit_log(request: Request):
    """Log habit completion/tracking."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        data = await request.json()
        result = await _service.process_habit_log(
            habit_name=data.get("habit_name"),
            completed=data.get("completed", False),
            notes=data.get("notes"),
            mood=data.get("mood"),
            difficulty=data.get("difficulty")
        )

        if result["success"]:
            return JSONResponse(content=result)
        else:
            return JSONResponse(status_code=422, content=result)
    except Exception as e:
        logger.error(f"Habit log processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/file-upload")
async def process_file_upload(request: Request):
    """Upload file from Files app."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        data = await request.json()
        result = await _service.process_file_upload(
            file_data=data.get("file_data"),
            file_name=data.get("file_name"),
            file_type=data.get("file_type"),
            description=data.get("description"),
            tags_custom=data.get("tags_custom")
        )

        if result["success"]:
            return JSONResponse(content=result)
        else:
            return JSONResponse(status_code=422, content=result)
    except Exception as e:
        logger.error(f"File upload processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch")
async def process_batch_shortcuts(requests: List[Dict[str, Any]]):
    """
    Process multiple shortcuts requests in batch.

    Useful for offline sync or bulk operations.
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        if len(requests) > 20:
            raise HTTPException(status_code=422, detail="Maximum 20 requests per batch")

        results = []

        for i, req_data in enumerate(requests):
            try:
                req_type = req_data.get("type")

                if req_type == "voice_memo":
                    result = await _service.process_voice_memo(**req_data.get("data", {}))
                elif req_type == "photo_ocr":
                    result = await _service.process_photo_ocr(**req_data.get("data", {}))
                elif req_type == "quick_note":
                    result = await _service.process_quick_note(**req_data.get("data", {}))
                elif req_type == "web_clip":
                    result = await _service.process_web_clip(**req_data.get("data", {}))
                elif req_type == "reading_list":
                    result = await _service.process_reading_list(**req_data.get("data", {}))
                elif req_type == "contact_note":
                    result = await _service.process_contact_note(**req_data.get("data", {}))
                elif req_type == "media_note":
                    result = await _service.process_media_note(**req_data.get("data", {}))
                elif req_type == "recipe":
                    result = await _service.process_recipe(**req_data.get("data", {}))
                elif req_type == "dream_journal":
                    result = await _service.process_dream_journal(**req_data.get("data", {}))
                elif req_type == "quote":
                    result = await _service.process_quote(**req_data.get("data", {}))
                elif req_type == "code_snippet":
                    result = await _service.process_code_snippet(**req_data.get("data", {}))
                elif req_type == "travel_journal":
                    result = await _service.process_travel_journal(**req_data.get("data", {}))
                elif req_type == "habit_log":
                    result = await _service.process_habit_log(**req_data.get("data", {}))
                elif req_type == "file_upload":
                    result = await _service.process_file_upload(**req_data.get("data", {}))
                else:
                    result = {"success": False, "error": f"Unknown request type: {req_type}"}

                results.append({
                    "index": i,
                    "type": req_type,
                    "success": result["success"],
                    "note_id": result.get("note_id"),
                    "error": result.get("error")
                })

            except Exception as e:
                results.append({
                    "index": i,
                    "success": False,
                    "error": str(e)
                })

        successful = sum(1 for r in results if r["success"])

        return JSONResponse(content={
            "success": True,
            "total_requests": len(requests),
            "successful": successful,
            "failed": len(requests) - successful,
            "results": results,
            "message": f"Batch processed: {successful}/{len(requests)} successful"
        })

    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))