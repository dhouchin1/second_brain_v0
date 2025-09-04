"""
Apple Shortcuts FastAPI Router

Provides REST API endpoints for Apple Shortcuts integration with enhanced 
mobile workflows and Siri support.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse

from services.apple_shortcuts_service import (
    AppleShortcutsService,
    QuickNoteRequest,
    VoiceNoteRequest, 
    WebClipRequest,
    MeetingPrepRequest,
    DailyCaptureRequest,
    PhotoTextRequest,
    CalendarEventRequest,
    ContactRequest,
    ReminderRequest
)
from services.auth_service import User

# Global service instances and functions (initialized by app.py)
shortcuts_service: Optional[AppleShortcutsService] = None
get_conn = None
get_current_user = None

# FastAPI router
router = APIRouter(prefix="/api/shortcuts", tags=["apple-shortcuts"])


def init_apple_shortcuts_router(get_conn_func, get_current_user_func):
    """Initialize Apple Shortcuts router with dependencies"""
    global shortcuts_service, get_conn, get_current_user
    get_conn = get_conn_func
    get_current_user = get_current_user_func
    shortcuts_service = AppleShortcutsService(get_conn_func)


# ─── Core Shortcuts Endpoints ───

@router.post("/quick-note")
async def capture_quick_note(
    request_data: QuickNoteRequest,
    fastapi_request: Request
):
    """Capture a quick note from Apple Shortcuts"""
    if not shortcuts_service:
        raise HTTPException(status_code=500, detail="Shortcuts service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await shortcuts_service.process_quick_note(request_data, current_user.id)
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process quick note: {str(e)}")


@router.post("/voice-note")
async def capture_voice_note(
    request_data: VoiceNoteRequest,
    fastapi_request: Request
):
    """Capture a voice note with transcription from Apple Shortcuts"""
    if not shortcuts_service:
        raise HTTPException(status_code=500, detail="Shortcuts service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await shortcuts_service.process_voice_note(request_data, current_user.id, fastapi_request)
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process voice note: {str(e)}")


@router.post("/web-clip")
async def capture_web_clip(
    request_data: WebClipRequest,
    fastapi_request: Request,
    background_tasks: BackgroundTasks
):
    """Capture a web page clip from Safari/browser"""
    if not shortcuts_service:
        raise HTTPException(status_code=500, detail="Shortcuts service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await shortcuts_service.process_web_clip(request_data, current_user.id)
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process web clip: {str(e)}")


@router.post("/meeting-prep")
async def prepare_meeting(
    request_data: MeetingPrepRequest,
    fastapi_request: Request
):
    """Create meeting preparation notes"""
    if not shortcuts_service:
        raise HTTPException(status_code=500, detail="Shortcuts service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await shortcuts_service.process_meeting_prep(request_data, current_user.id)
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process meeting prep: {str(e)}")


@router.post("/daily-capture")
async def capture_daily_reflection(
    request_data: DailyCaptureRequest,
    fastapi_request: Request
):
    """Capture daily reflection and thoughts"""
    if not shortcuts_service:
        raise HTTPException(status_code=500, detail="Shortcuts service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await shortcuts_service.process_daily_capture(request_data, current_user.id)
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process daily capture: {str(e)}")


@router.post("/photo-text")
async def capture_photo_text(
    request_data: PhotoTextRequest,
    fastapi_request: Request
):
    """Capture photo with OCR text extraction"""
    if not shortcuts_service:
        raise HTTPException(status_code=500, detail="Shortcuts service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await shortcuts_service.process_photo_text(request_data, current_user.id)
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process photo text: {str(e)}")


@router.post("/calendar-event")
async def capture_calendar_event(
    request_data: CalendarEventRequest,
    fastapi_request: Request
):
    """Capture calendar event"""
    if not shortcuts_service:
        raise HTTPException(status_code=500, detail="Shortcuts service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await shortcuts_service.process_calendar_event(request_data, current_user.id)
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process calendar event: {str(e)}")


@router.post("/contact")
async def capture_contact(
    request_data: ContactRequest,
    fastapi_request: Request
):
    """Capture contact information"""
    if not shortcuts_service:
        raise HTTPException(status_code=500, detail="Shortcuts service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await shortcuts_service.process_contact(request_data, current_user.id)
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process contact: {str(e)}")


@router.post("/reminder")
async def capture_reminder(
    request_data: ReminderRequest,
    fastapi_request: Request
):
    """Capture reminder/task"""
    if not shortcuts_service:
        raise HTTPException(status_code=500, detail="Shortcuts service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        result = await shortcuts_service.process_reminder(request_data, current_user.id)
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process reminder: {str(e)}")


# ─── Setup and Configuration Endpoints ───

@router.get("/status")
async def shortcuts_status():
    """Get Apple Shortcuts integration status"""
    if not shortcuts_service:
        return JSONResponse(
            content={"status": "unavailable", "error": "Service not initialized"},
            status_code=503
        )
    
    return JSONResponse(content=shortcuts_service.get_shortcut_status())


@router.get("/setup")
async def shortcuts_setup():
    """Serve the interactive setup page for Apple Shortcuts"""
    with open("templates/shortcuts_setup.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)


@router.get("/setup/json")
async def shortcuts_setup_json(fastapi_request: Request):
    """Get setup configuration data in JSON format"""
    if not shortcuts_service:
        raise HTTPException(status_code=500, detail="Shortcuts service not initialized")
    
    # Get current user for personalized setup
    current_user = await get_current_user(fastapi_request)
    
    base_url = str(fastapi_request.base_url).rstrip("/")
    
    setup_info = {
        "title": "Second Brain - Apple Shortcuts Setup",
        "description": "Configure Apple Shortcuts for seamless note capture",
        "base_url": base_url,
        "endpoints": {
            "quick_note": f"{base_url}/api/shortcuts/quick-note",
            "voice_note": f"{base_url}/api/shortcuts/voice-note",
            "web_clip": f"{base_url}/api/shortcuts/web-clip",
            "meeting_prep": f"{base_url}/api/shortcuts/meeting-prep",
            "daily_capture": f"{base_url}/api/shortcuts/daily-capture",
            "photo_text": f"{base_url}/api/shortcuts/photo-text",
            "calendar_event": f"{base_url}/api/shortcuts/calendar-event",
            "contact": f"{base_url}/api/shortcuts/contact",
            "reminder": f"{base_url}/api/shortcuts/reminder"
        },
        "authentication": {
            "method": "session_cookie",
            "note": "Authenticate via web interface first, then shortcuts will inherit session"
        },
        "mobile_capture_url": f"{base_url}/capture/mobile",
        "shortcuts_config": f"{base_url}/api/shortcuts/config",
        "instructions": [
            "1. Open the Shortcuts app on your iOS device",
            "2. Download our pre-configured shortcuts from the config endpoint",
            "3. Update the URLs to point to your Second Brain instance",
            "4. Test each shortcut with sample content",
            "5. Add shortcuts to your home screen for quick access",
            "6. Configure Siri phrases for voice activation"
        ],
        "siri_phrases": [
            "Quick note to Second Brain",
            "Save a voice note", 
            "Capture this page",
            "Prepare for meeting",
            "Daily reflection time"
        ],
        "features": [
            "📝 Quick text notes with auto-tagging",
            "🎤 Voice notes with Whisper.cpp transcription",
            "🔗 Web page clipping from Safari",
            "📅 Meeting preparation workflows",
            "🌅 Daily reflection prompts",
            "📸 Photo OCR text extraction",
            "📅 Calendar event capture",
            "👤 Contact information saving",
            "🔔 Reminder and task creation",
            "🔄 Smart Automation integration",
            "📱 Mobile-optimized interface"
        ]
    }
    
    return JSONResponse(content=setup_info)


@router.get("/config")
async def shortcuts_config():
    """Download legacy quick note shortcut configuration"""
    try:
        return FileResponse(
            path="apple_shortcuts/Quick_Note_Shortcut.json",
            filename="SecondBrain_QuickNote.json",
            media_type="application/json"
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Configuration file not found")


# Individual shortcut download endpoints
@router.get("/shortcuts/photo-text.json")
async def download_photo_text_shortcut():
    """Download Photo Text OCR shortcut"""
    try:
        return FileResponse(
            path="apple_shortcuts/Photo_Text_Shortcut.json",
            filename="SecondBrain_PhotoText.json",
            media_type="application/json"
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Photo text shortcut not found")


@router.get("/shortcuts/voice-whisper.json")
async def download_voice_whisper_shortcut():
    """Download Voice Whisper shortcut"""
    try:
        return FileResponse(
            path="apple_shortcuts/Voice_Whisper_Shortcut.json",
            filename="SecondBrain_VoiceWhisper.json",
            media_type="application/json"
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Voice whisper shortcut not found")


@router.get("/shortcuts/calendar-event.json")
async def download_calendar_event_shortcut():
    """Download Calendar Event shortcut"""
    try:
        return FileResponse(
            path="apple_shortcuts/Calendar_Event_Shortcut.json",
            filename="SecondBrain_CalendarEvent.json",
            media_type="application/json"
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Calendar event shortcut not found")


@router.get("/shortcuts/contact.json")
async def download_contact_shortcut():
    """Download Contact shortcut"""
    try:
        return FileResponse(
            path="apple_shortcuts/Contact_Shortcut.json",
            filename="SecondBrain_Contact.json",
            media_type="application/json"
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Contact shortcut not found")


@router.get("/shortcuts/reminder.json")
async def download_reminder_shortcut():
    """Download Quick Reminder shortcut"""
    try:
        return FileResponse(
            path="apple_shortcuts/Quick_Reminder_Shortcut.json",
            filename="SecondBrain_QuickReminder.json",
            media_type="application/json"
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Quick reminder shortcut not found")


# ─── Utility Endpoints ───

@router.post("/test")
async def test_shortcuts_integration(fastapi_request: Request):
    """Test endpoint for Apple Shortcuts integration"""
    if not shortcuts_service:
        raise HTTPException(status_code=500, detail="Shortcuts service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Create a test note
    test_request = QuickNoteRequest(
        content="Test note from Apple Shortcuts integration ✅",
        source="apple_shortcuts_test",
        device="Test Device",
        tags="test,shortcuts"
    )
    
    try:
        result = await shortcuts_service.process_quick_note(test_request, current_user.id)
        result["test"] = True
        result["message"] = "Apple Shortcuts integration test successful!"
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")


@router.get("/health")
async def shortcuts_health():
    """Health check for Apple Shortcuts service"""
    return JSONResponse(content={
        "status": "healthy" if shortcuts_service else "unavailable",
        "service": "Apple Shortcuts Integration",
        "endpoints_active": shortcuts_service is not None,
        "features": {
            "quick_notes": True,
            "voice_notes": True,
            "voice_transcription_whisper": True,
            "web_clipping": True,
            "meeting_prep": True,
            "daily_capture": True,
            "photo_ocr": True,
            "calendar_events": True,
            "contacts": True,
            "reminders": True,
            "siri_integration": True,
            "smart_automation": True
        }
    })


# ─── Legacy Compatibility ───

@router.post("/capture")
async def legacy_shortcuts_capture(
    content: str,
    tags: str = "",
    source: str = "apple_shortcuts_legacy",
    fastapi_request: Request = None
):
    """Legacy compatibility endpoint for older shortcuts"""
    if not shortcuts_service:
        raise HTTPException(status_code=500, detail="Shortcuts service not initialized")
    
    # Get current user
    current_user = await get_current_user(fastapi_request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Convert to new format
    request_data = QuickNoteRequest(
        content=content,
        tags=tags,
        source=source
    )
    
    try:
        result = await shortcuts_service.process_quick_note(request_data, current_user.id)
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process legacy capture: {str(e)}")


print("[Apple Shortcuts Router] Loaded successfully")