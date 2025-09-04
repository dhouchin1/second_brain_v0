"""
Apple Shortcuts Integration Service

Provides enhanced endpoints and functionality for Apple Shortcuts integration,
including mobile-optimized workflows and Siri integration.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from fastapi import HTTPException

from services.auth_service import User


class ShortcutRequest(BaseModel):
    """Base model for Apple Shortcuts requests"""
    content: str
    source: str = "apple_shortcuts"
    device: Optional[str] = None
    timestamp: Optional[str] = None
    tags: Optional[str] = None


class QuickNoteRequest(ShortcutRequest):
    """Quick note capture from Shortcuts"""
    pass


class VoiceNoteRequest(ShortcutRequest):
    """Voice note with transcription"""
    audio_duration: Optional[float] = None
    language: Optional[str] = "en-US"
    audio_file: Optional[str] = None  # Base64 encoded audio file
    use_whisper: Optional[bool] = True  # Use Whisper.cpp instead of Apple transcription


class WebClipRequest(ShortcutRequest):
    """Web page clip from Safari/browser"""
    url: str
    title: Optional[str] = None
    webpage_content: Optional[str] = None


class MeetingPrepRequest(ShortcutRequest):
    """Meeting preparation notes"""
    meeting_title: str
    meeting_date: Optional[str] = None
    attendees: Optional[List[str]] = None


class DailyCaptureRequest(ShortcutRequest):
    """Daily reflection and capture"""
    mood: Optional[str] = None
    energy_level: Optional[int] = None


class PhotoTextRequest(ShortcutRequest):
    """Photo with OCR text extraction"""
    extracted_text: str
    photo_location: Optional[Dict[str, Any]] = None


class CalendarEventRequest(ShortcutRequest):
    """Calendar event capture"""
    event_title: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    location: Optional[str] = None
    attendees: Optional[List[str]] = None


class ContactRequest(ShortcutRequest):
    """Contact information capture"""
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None


class ReminderRequest(ShortcutRequest):
    """Reminder/task capture"""
    reminder_title: str
    due_date: Optional[str] = None
    priority: Optional[str] = "normal"
    notes: Optional[str] = None


class AppleShortcutsService:
    """Service for handling Apple Shortcuts integration"""
    
    def __init__(self, get_conn_func):
        self.get_conn = get_conn_func
    
    async def process_quick_note(self, request: QuickNoteRequest, user_id: int) -> Dict[str, Any]:
        """Process a quick note from Apple Shortcuts"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            # Generate title from content
            title = self._generate_title(request.content)
            
            # Create note
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO notes (
                    title, content, tags, type, timestamp, status, user_id,
                    source_url, web_metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title,
                request.content,
                request.tags or "shortcuts,quick",
                "text",
                now,
                "complete",
                user_id,
                None,
                json.dumps({
                    "source": request.source,
                    "device": request.device,
                    "shortcut_timestamp": request.timestamp
                }, default=str)
            ))
            
            note_id = c.lastrowid
            
            # Add to FTS
            c.execute("""
                INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (note_id, title, "", request.tags or "", "", request.content, request.content))
            
            conn.commit()
            
            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "message": "Quick note saved successfully",
                "shortcuts_response": {
                    "notification_title": "✅ Note Saved",
                    "notification_body": f"Saved: {title[:50]}..."
                }
            }
            
        finally:
            conn.close()
    
    async def process_voice_note(self, request: VoiceNoteRequest, user_id: int, fastapi_request = None) -> Dict[str, Any]:
        """Process a voice note with transcription from Apple Shortcuts"""
        
        # Extend session if we have a FastAPI request and this is a Whisper recording
        if fastapi_request and request.audio_file and request.use_whisper:
            try:
                # Import here to avoid circular imports
                import requests
                # Call our session extension endpoint
                session_response = requests.post(
                    "http://localhost:8082/api/auth/recording-session",
                    cookies=fastapi_request.cookies,
                    timeout=5
                )
                if session_response.status_code == 200:
                    print("✅ Session extended for voice recording")
                else:
                    print("⚠️ Failed to extend session for voice recording")
            except Exception as e:
                print(f"⚠️ Session extension error: {e}")
        
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            # Handle audio file processing with Whisper.cpp if provided
            transcription_source = "apple_dictation"
            final_content = request.content
            processing_status = "complete"
            
            if request.audio_file and request.use_whisper:
                # Save audio file and queue for Whisper.cpp processing
                audio_result = await self._process_audio_file(request.audio_file, user_id)
                if audio_result:
                    transcription_source = "whisper_cpp"
                    processing_status = "processing"  # Will be updated when Whisper completes
                    final_content = request.content or "[Audio file received - transcription in progress...]"
            
            # Generate title
            title = self._generate_title(final_content, prefix="🎤 Voice: ")
            
            # Create note with voice metadata
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO notes (
                    title, content, tags, type, timestamp, status, user_id,
                    source_url, web_metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title,
                final_content,
                request.tags or "shortcuts,voice,transcription",
                "audio",  # Mark as audio type even though it's transcribed
                now,
                processing_status,
                user_id,
                None,
                json.dumps({
                    "source": request.source,
                    "device": request.device,
                    "audio_duration": request.audio_duration,
                    "language": request.language,
                    "transcription_source": transcription_source,
                    "has_audio_file": request.audio_file is not None,
                    "use_whisper": request.use_whisper,
                    "shortcut_timestamp": request.timestamp
                }, default=str)
            ))
            
            note_id = c.lastrowid
            
            # Add to FTS (will be updated when transcription completes)
            c.execute("""
                INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (note_id, title, "", request.tags or "", "", final_content, final_content))
            
            # If we have an audio file, queue it for Whisper processing
            if request.audio_file and request.use_whisper and audio_result:
                from services.audio_queue import AudioProcessingQueue
                queue = AudioProcessingQueue()
                await queue.add_to_queue(note_id, user_id, priority=1)  # High priority for Shortcuts
            
            conn.commit()
            
            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "transcription": final_content,
                "duration": request.audio_duration,
                "processing_status": processing_status,
                "message": "Voice note saved" + (" - transcription in progress" if processing_status == "processing" else " and transcribed"),
                "shortcuts_response": {
                    "notification_title": "🎤 Voice Note Saved",
                    "notification_body": f"{'Transcribing' if processing_status == 'processing' else 'Transcribed'}: {final_content[:50]}..."
                }
            }
            
        finally:
            conn.close()
    
    async def process_web_clip(self, request: WebClipRequest, user_id: int) -> Dict[str, Any]:
        """Process a web page clip from Safari/browser"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            # Use provided title or generate one
            title = request.title or self._generate_title(request.content, prefix="🔗 ")
            
            # Create enhanced content with URL and clipped content
            enhanced_content = f"""# {title}

**URL:** {request.url}

**Clipped Content:**
{request.content}

---
*Captured via Apple Shortcuts on {request.timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
"""
            
            if request.webpage_content:
                enhanced_content += f"\n\n**Full Page Content:**\n{request.webpage_content[:2000]}..."
            
            # Create note
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO notes (
                    title, content, tags, type, timestamp, status, user_id,
                    source_url, web_metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title,
                enhanced_content,
                request.tags or "shortcuts,web,clip",
                "web_content",
                now,
                "complete",
                user_id,
                request.url,
                json.dumps({
                    "source": request.source,
                    "device": request.device,
                    "original_url": request.url,
                    "clip_method": "apple_shortcuts",
                    "shortcut_timestamp": request.timestamp
                }, default=str)
            ))
            
            note_id = c.lastrowid
            
            # Add to FTS
            c.execute("""
                INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (note_id, title, "", request.tags or "", "", enhanced_content, request.content))
            
            conn.commit()
            
            # Trigger Smart Automation for URL processing
            try:
                from services.workflow_engine import WorkflowEngine, TriggerType
                workflow_engine = WorkflowEngine(self.get_conn)
                
                trigger_data = {
                    "note_id": note_id,
                    "user_id": user_id,
                    "title": title,
                    "content": enhanced_content,
                    "tags": request.tags or "",
                    "note_type": "web_content"
                }
                
                await workflow_engine.trigger_workflow(TriggerType.CONTENT_CREATED, trigger_data)
            except Exception as e:
                print(f"Smart Automation trigger failed for web clip: {e}")
            
            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "url": request.url,
                "message": "Web clip saved successfully",
                "shortcuts_response": {
                    "notification_title": "🔗 Web Clip Saved",
                    "notification_body": f"Saved: {title[:50]}..."
                }
            }
            
        finally:
            conn.close()
    
    async def process_meeting_prep(self, request: MeetingPrepRequest, user_id: int) -> Dict[str, Any]:
        """Process meeting preparation notes"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            title = f"📅 Meeting Prep: {request.meeting_title}"
            
            # Create structured meeting content
            meeting_content = f"""# {request.meeting_title}

**Date:** {request.meeting_date or datetime.now().strftime("%Y-%m-%d")}
**Prepared:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

{request.content}

---
*Prepared via Apple Shortcuts*
"""
            
            # Create note
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO notes (
                    title, content, tags, type, timestamp, status, user_id,
                    source_url, web_metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title,
                meeting_content,
                request.tags or "shortcuts,meeting,preparation",
                "text",
                now,
                "complete",
                user_id,
                None,
                json.dumps({
                    "source": request.source,
                    "device": request.device,
                    "meeting_title": request.meeting_title,
                    "meeting_date": request.meeting_date,
                    "attendees": request.attendees,
                    "shortcut_timestamp": request.timestamp
                }, default=str)
            ))
            
            note_id = c.lastrowid
            
            # Add to FTS
            c.execute("""
                INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (note_id, title, "", request.tags or "", "", meeting_content, meeting_content))
            
            conn.commit()
            
            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "meeting_title": request.meeting_title,
                "meeting_date": request.meeting_date,
                "message": "Meeting prep notes saved",
                "shortcuts_response": {
                    "notification_title": "📅 Meeting Prep Ready",
                    "notification_body": f"Prepared for: {request.meeting_title}"
                }
            }
            
        finally:
            conn.close()
    
    async def process_daily_capture(self, request: DailyCaptureRequest, user_id: int) -> Dict[str, Any]:
        """Process daily reflection and capture"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            date_str = datetime.now().strftime("%Y-%m-%d")
            title = f"🌅 Daily Reflection - {date_str}"
            
            # Create structured daily content
            daily_content = f"""# Daily Reflection - {date_str}

{request.content}

**Captured:** {datetime.now().strftime("%H:%M:%S")}
**Device:** {request.device or "iPhone/iPad"}
"""
            
            if request.mood:
                daily_content += f"\n**Mood:** {request.mood}"
            
            if request.energy_level:
                daily_content += f"\n**Energy Level:** {request.energy_level}/10"
            
            daily_content += "\n\n---\n*Captured via Apple Shortcuts*"
            
            # Create note
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO notes (
                    title, content, tags, type, timestamp, status, user_id,
                    source_url, web_metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title,
                daily_content,
                request.tags or "shortcuts,daily,reflection",
                "text",
                now,
                "complete",
                user_id,
                None,
                json.dumps({
                    "source": request.source,
                    "device": request.device,
                    "mood": request.mood,
                    "energy_level": request.energy_level,
                    "shortcut_timestamp": request.timestamp
                }, default=str)
            ))
            
            note_id = c.lastrowid
            
            # Add to FTS
            c.execute("""
                INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (note_id, title, "", request.tags or "", "", daily_content, daily_content))
            
            conn.commit()
            
            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "date": date_str,
                "message": "Daily reflection saved",
                "shortcuts_response": {
                    "notification_title": "🌅 Daily Reflection Saved",
                    "notification_body": "Great job reflecting on your day!"
                }
            }
            
        finally:
            conn.close()
    
    async def process_photo_text(self, request: PhotoTextRequest, user_id: int) -> Dict[str, Any]:
        """Process photo with OCR text extraction"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            title = "📸 Photo Text Capture"
            
            # Create enhanced content with location data
            content = f"# {title}\n\n"
            
            if request.photo_location:
                location_name = request.photo_location.get('name', 'Unknown')
                content += f"**Location**: {location_name}\n"
                if request.photo_location.get('coordinates'):
                    lat, lon = request.photo_location['coordinates']
                    content += f"**Coordinates**: [{lat}, {lon}](https://maps.apple.com/?q={lat},{lon})\n"
                content += "\n"
            
            content += f"**Extracted Text**:\n\n{request.extracted_text}\n\n"
            content += f"*Captured via Apple Shortcuts on {request.timestamp or datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
            
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO notes (
                    title, content, tags, type, timestamp, status, user_id,
                    source_url, web_metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title,
                content,
                request.tags or "shortcuts,photo,ocr,text-extraction",
                "photo_text",
                now,
                "complete",
                user_id,
                None,
                json.dumps({
                    "source": request.source,
                    "device": request.device,
                    "photo_location": request.photo_location,
                    "shortcut_timestamp": request.timestamp
                }, default=str)
            ))
            
            note_id = c.lastrowid
            
            c.execute("""
                INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (note_id, title, "", request.tags or "", "", content, request.extracted_text))
            
            conn.commit()
            
            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "extracted_text": request.extracted_text,
                "message": "Photo text captured successfully",
                "shortcuts_response": {
                    "notification_title": "📸 Photo Text Saved",
                    "notification_body": f"Extracted: {request.extracted_text[:50]}..."
                }
            }
            
        finally:
            conn.close()
    
    def _generate_title(self, content: str, prefix: str = "") -> str:
        """Generate a title from content"""
        if not content:
            return f"{prefix}Untitled Note"
        
        # Clean and truncate content for title
        clean_content = content.replace("\n", " ").strip()
        
        # Remove markdown headers
        if clean_content.startswith("#"):
            clean_content = clean_content.lstrip("#").strip()
        
        # Truncate to reasonable length
        max_length = 60 - len(prefix)
        if len(clean_content) > max_length:
            title = clean_content[:max_length].rsplit(" ", 1)[0] + "..."
        else:
            title = clean_content
        
        return f"{prefix}{title}" if title else f"{prefix}Quick Note"
    
    async def _process_audio_file(self, audio_base64: str, user_id: int) -> Optional[str]:
        """Process base64 encoded audio file from Shortcuts"""
        try:
            import base64
            from pathlib import Path
            import tempfile
            import os
            
            # Decode base64 audio
            audio_data = base64.b64decode(audio_base64)
            
            # Create temporary file with unique name
            audio_dir = Path("vault/audio")
            audio_dir.mkdir(exist_ok=True)
            
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_filename = f"shortcuts_audio_{user_id}_{timestamp}.m4a"  # Common iOS format
            audio_path = audio_dir / audio_filename
            
            # Write audio data to file
            with open(audio_path, 'wb') as f:
                f.write(audio_data)
            
            return str(audio_path)
            
        except Exception as e:
            print(f"Error processing audio file: {e}")
            return None
    
    def get_shortcut_status(self) -> Dict[str, Any]:
        """Get status information for Apple Shortcuts integration"""
        return {
            "service": "Apple Shortcuts Integration",
            "status": "active",
            "endpoints": {
                "quick_note": "/api/shortcuts/quick-note",
                "voice_note": "/api/shortcuts/voice-note", 
                "web_clip": "/api/shortcuts/web-clip",
                "meeting_prep": "/api/shortcuts/meeting-prep",
                "daily_capture": "/api/shortcuts/daily-capture"
            },
            "features": [
                "Quick text capture",
                "Voice transcription",
                "Web page clipping",
                "Meeting preparation",
                "Daily reflection",
                "Siri integration",
                "Smart Automation triggers"
            ],
            "setup_url": "/api/shortcuts/setup"
        }