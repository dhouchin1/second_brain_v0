"""
Mobile Capture Router - FastAPI endpoints for all mobile capture methods
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import json
from datetime import datetime

# Import service (will be initialized in main app)
mobile_service = None
get_conn = None
get_current_user = None

# === Pydantic Models ===

class ShortcutsCaptureRequest(BaseModel):
    type: str = Field(..., description="Type of shortcut capture", example="web_clip")
    content: str = Field(..., description="Main content")
    title: Optional[str] = Field(None, description="Content title")
    url: Optional[str] = Field(None, description="Source URL for web clips")
    source_app: Optional[str] = Field("iOS Shortcuts", description="Source application")
    location: Optional[Dict[str, Any]] = Field(None, description="Location data")
    device_info: Optional[Dict[str, Any]] = Field(None, description="Device information")
    extracted_text: Optional[str] = Field(None, description="OCR extracted text from photos")
    transcription: Optional[str] = Field(None, description="Voice transcription")
    duration: Optional[int] = Field(None, description="Audio duration in seconds")
    
    # Calendar/Contact specific fields
    event_title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    attendees: Optional[List[str]] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None
    
    # Task/Reminder fields
    due_date: Optional[str] = None
    priority: Optional[str] = "normal"

class EmailCaptureRequest(BaseModel):
    subject: str = Field(..., description="Email subject")
    sender: str = Field(..., description="Sender email address", alias="from")
    body: str = Field(..., description="Email body text")
    html_body: Optional[str] = Field(None, description="HTML email body")
    attachments: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Email attachments")
    received_date: Optional[str] = Field(None, description="Email received date")

class SMSCaptureRequest(BaseModel):
    body: str = Field(..., description="SMS message body")
    sender: str = Field(..., description="Sender phone number or name")
    timestamp: Optional[str] = Field(None, description="Message timestamp")

class VoiceCaptureRequest(BaseModel):
    transcription: Optional[str] = Field(None, description="Voice transcription")
    audio_file: Optional[str] = Field(None, description="Base64 encoded audio file")
    duration: Optional[int] = Field(0, description="Audio duration in seconds")
    source: Optional[str] = Field("voice_recorder", description="Voice recording source")
    confidence: Optional[float] = Field(0.0, description="Transcription confidence score")

# === Router Setup ===

router = APIRouter(prefix="/api/mobile", tags=["Mobile Capture"])

def init_mobile_capture_router(get_conn_func, get_current_user_func):
    """Initialize the mobile capture router with database connection and auth"""
    global mobile_service, get_conn, get_current_user
    from services.mobile_capture_service import MobileCaptureService
    
    get_conn = get_conn_func
    get_current_user = get_current_user_func
    mobile_service = MobileCaptureService(get_conn_func)

# === iOS Shortcuts Integration ===
# Note: iOS Shortcuts endpoints are handled by services/apple_shortcuts_router.py
# This router focuses on email, SMS, and voice capture methods

# === Email Forwarding Endpoints ===

@router.post("/email/forward")
async def forward_email_to_brain(
    request_data: EmailCaptureRequest,
    current_user = Depends(lambda: get_current_user())
):
    """
    Process emails forwarded to Second Brain
    
    Set up email forwarding to capture important emails directly into your knowledge base.
    Supports both plain text and HTML emails with attachment handling.
    """
    try:
        result = mobile_service.process_email_capture(
            user_id=current_user.id,
            email_data=request_data.dict()
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email capture failed: {str(e)}")

@router.post("/email/setup")
async def setup_email_forwarding(
    provider: str = "gmail",
    current_user = Depends(lambda: get_current_user())
):
    """
    Set up email forwarding for the current user
    
    Generates a unique forwarding address and provides setup instructions
    for the specified email provider (gmail, outlook, apple, etc.)
    """
    try:
        from services.email_forwarding_service import EmailForwardingService
        forwarding_service = EmailForwardingService(get_conn)
        
        result = forwarding_service.setup_email_forwarding(
            user_id=current_user.id,
            email_config={'provider': provider}
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email setup failed: {str(e)}")

@router.get("/email/config")
async def get_email_config(
    current_user = Depends(lambda: get_current_user())
):
    """Get user's current email forwarding configuration"""
    try:
        from services.email_forwarding_service import EmailForwardingService
        forwarding_service = EmailForwardingService(get_conn)
        
        config = forwarding_service.get_user_forwarding_config(current_user.id)
        if config:
            return config
        else:
            return {"message": "No email forwarding configured"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get config: {str(e)}")

@router.get("/email/stats")
async def get_email_stats(
    days: int = 30,
    current_user = Depends(lambda: get_current_user())
):
    """Get email processing statistics"""
    try:
        from services.email_forwarding_service import EmailForwardingService
        forwarding_service = EmailForwardingService(get_conn)
        
        stats = forwarding_service.get_email_processing_stats(current_user.id, days)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

@router.post("/email/webhook")
async def email_webhook_handler(request: Request):
    """
    Webhook endpoint for email service providers (SendGrid, Mailgun, etc.)
    
    Configure your email provider to forward emails to this endpoint.
    The email content will be parsed and saved to the appropriate user's Second Brain.
    """
    try:
        payload = await request.json()
        
        # Determine webhook provider from headers or payload structure
        provider = _detect_webhook_provider(request.headers, payload)
        
        from services.email_forwarding_service import EmailWebhookProcessor
        processor = EmailWebhookProcessor(get_conn)
        
        if provider == 'sendgrid':
            result = processor.process_sendgrid_webhook(payload)
        elif provider == 'mailgun':
            result = processor.process_mailgun_webhook(payload)
        else:
            # Generic email processing
            email_data = _parse_email_webhook(payload)
            forwarding_address = payload.get('to', payload.get('recipient', ''))
            result = processor._process_webhook_email(email_data, forwarding_address)
        
        return {"success": True, "processed": result.get("success", False)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email webhook failed: {str(e)}")

# === SMS/Text Endpoints ===

@router.post("/sms/capture")
async def capture_sms_message(
    request_data: SMSCaptureRequest,
    current_user = Depends(lambda: get_current_user())
):
    """
    Capture SMS/text messages sent to Second Brain
    
    Supports special commands:
    - #task [content] - Creates a task
    - #reminder [content] - Creates a reminder  
    - #note [content] - Creates a note
    - #idea [content] - Captures an idea
    - #quote [content] - Saves a quote
    """
    try:
        result = mobile_service.process_sms_capture(
            user_id=current_user.id,
            sms_data=request_data.dict()
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SMS capture failed: {str(e)}")

@router.post("/sms/webhook")
async def sms_webhook_handler(request: Request):
    """
    Webhook endpoint for SMS service providers (Twilio, etc.)
    
    Configure your SMS provider to forward messages to this endpoint.
    """
    try:
        payload = await request.json()
        
        # Parse SMS webhook payload
        sms_data = _parse_sms_webhook(payload)
        
        # Determine user based on phone number mapping
        user_id = _determine_user_from_sms(sms_data)
        
        if not user_id:
            raise HTTPException(status_code=400, detail="Could not determine target user")
        
        result = mobile_service.process_sms_capture(user_id, sms_data)
        return {"success": True, "note_id": result["note_id"]}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SMS webhook failed: {str(e)}")

# === Voice Note Endpoints ===

@router.post("/voice/capture")
async def capture_voice_note(
    request_data: VoiceCaptureRequest,
    background_tasks: BackgroundTasks,
    current_user = Depends(lambda: get_current_user())
):
    """
    Process voice notes with automatic transcription
    
    Can accept either:
    - Pre-transcribed text
    - Raw audio file for transcription
    - Both for verification
    """
    try:
        # If audio file provided but no transcription, queue for background processing
        if request_data.audio_file and not request_data.transcription:
            background_tasks.add_task(
                _process_voice_transcription,
                current_user.id,
                request_data.dict()
            )
            return {
                "success": True,
                "message": "Voice note queued for transcription",
                "status": "processing"
            }
        
        result = mobile_service.process_voice_capture(
            user_id=current_user.id,
            voice_data=request_data.dict()
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice capture failed: {str(e)}")

@router.get("/voice/status/{note_id}")
async def get_voice_processing_status(
    note_id: int,
    current_user = Depends(lambda: get_current_user())
):
    """Check the processing status of a voice note"""
    # Implementation would check processing queue/status
    return {
        "note_id": note_id,
        "status": "completed",  # or "processing", "failed"
        "transcription_ready": True
    }

# === Statistics and Management ===

@router.get("/stats")
async def get_mobile_capture_stats(
    days: int = 30,
    current_user = Depends(lambda: get_current_user())
):
    """Get mobile capture usage statistics"""
    try:
        stats = mobile_service.get_capture_stats(current_user.id, days)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

@router.get("/methods")
async def get_available_capture_methods():
    """Get list of all available mobile capture methods with setup instructions"""
    return {
        "methods": {
            "ios_shortcuts": {
                "name": "iOS Shortcuts",
                "description": "Capture content directly from iOS using the Shortcuts app",
                "endpoint": "/api/mobile/shortcuts/capture",
                "setup_url": "/setup/shortcuts"
            },
            "email_forwarding": {
                "name": "Email Forwarding", 
                "description": "Forward important emails directly to your Second Brain",
                "endpoint": "/api/mobile/email/forward",
                "setup_url": "/setup/email"
            },
            "sms_capture": {
                "name": "SMS Capture",
                "description": "Send text messages to save notes and tasks",
                "endpoint": "/api/mobile/sms/capture", 
                "setup_url": "/setup/sms"
            },
            "voice_notes": {
                "name": "Voice Notes",
                "description": "Record voice memos with automatic transcription",
                "endpoint": "/api/mobile/voice/capture",
                "setup_url": "/setup/voice"
            }
        }
    }

# === Utility Functions ===

def _parse_email_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Parse email webhook payload from various providers"""
    # This would be customized based on your email provider
    # Example for generic webhook format:
    return {
        "subject": payload.get("subject", ""),
        "from": payload.get("from", ""),
        "body": payload.get("text", ""),
        "html_body": payload.get("html", ""),
        "attachments": payload.get("attachments", [])
    }

def _parse_sms_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Parse SMS webhook payload"""
    # Example for Twilio format:
    return {
        "body": payload.get("Body", ""),
        "sender": payload.get("From", ""),
        "timestamp": payload.get("DateSent", datetime.utcnow().isoformat())
    }

def _determine_user_from_email(email_data: Dict[str, Any]) -> Optional[int]:
    """Determine which user an email should be saved to"""
    # Implementation would look up user by email address, API key, etc.
    # For now, return None to indicate user lookup needed
    return None

def _detect_webhook_provider(headers, payload: Dict[str, Any]) -> str:
    """Detect which email webhook provider sent the request"""
    user_agent = headers.get('user-agent', '').lower()
    
    if 'sendgrid' in user_agent or 'sendgrid' in str(payload):
        return 'sendgrid'
    elif 'mailgun' in user_agent or 'mailgun-api' in headers:
        return 'mailgun'
    else:
        return 'generic'

def _determine_user_from_email(email_data: Dict[str, Any]) -> Optional[int]:
    """Determine which user an email should be saved to"""
    # Extract forwarding address from recipient field
    recipient = email_data.get('to', email_data.get('recipient', ''))
    if not recipient:
        return None
    
    # Look up user by forwarding address
    from services.email_forwarding_service import EmailForwardingService
    forwarding_service = EmailForwardingService(get_conn)
    return forwarding_service._get_user_from_forwarding_address(recipient)

def _determine_user_from_sms(sms_data: Dict[str, Any]) -> Optional[int]:
    """Determine which user an SMS should be saved to"""
    # Implementation would look up user by phone number mapping
    # For now, this would require a phone_number_mapping table
    return None

async def _process_voice_transcription(user_id: int, voice_data: Dict[str, Any]):
    """Background task for voice transcription processing"""
    try:
        # This would call actual transcription service like Whisper, OpenAI, etc.
        # For now, just simulate processing
        result = mobile_service.process_voice_capture(user_id, voice_data)
        # Could send notification to user when complete
        print(f"Voice transcription completed for user {user_id}")
    except Exception as e:
        # Log error and possibly notify user
        print(f"Voice transcription failed: {e}")