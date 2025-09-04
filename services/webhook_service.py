"""
Webhook Service

Handles webhook endpoints for Discord, Apple Shortcuts, and other external integrations.
Extracted from app.py to provide clean separation of webhook processing logic.
"""

import json
import secrets
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import HTTPException, BackgroundTasks, UploadFile
from pydantic import BaseModel

from config import settings
from file_processor import FileProcessor
from llm_utils import ollama_summarize


# --- Data Models ---

class DiscordWebhook(BaseModel):
    note: str
    tags: str = ""
    type: str = "discord"
    discord_user_id: Optional[int] = None
    timestamp: Optional[str] = None


class AppleReminderWebhook(BaseModel):
    title: str
    due_date: Optional[str] = None
    notes: str = ""
    tags: str = "reminder,apple"


class CalendarEvent(BaseModel):
    title: str
    start_date: str
    end_date: str
    description: str = ""
    attendees: List[str] = []


class WebhookService:
    """Service for handling webhook operations."""
    
    def __init__(self, get_conn_func, auth_service):
        """Initialize webhook service with database connection and auth service."""
        self.get_conn = get_conn_func
        self.auth_service = auth_service
    
    # --- Audio Webhook ---
    
    async def process_audio_webhook(
        self, 
        background_tasks: BackgroundTasks,
        file: UploadFile,
        tags: str = "",
        user_id: int = 2
    ) -> dict:
        """
        Fast audio webhook endpoint for Apple Shortcuts and external integrations.
        Quickly saves audio and queues for background processing without blocking.
        """
        # Validate audio file
        if not file.content_type or not file.content_type.startswith('audio/'):
            raise HTTPException(status_code=400, detail="File must be audio")
        
        try:
            # Process the file with existing processor
            processor = FileProcessor()
            file_content = await file.read()
            
            # Quick validation and get metadata
            is_valid, error_msg, file_info = processor.validate_file(
                file_content, file.filename or "webhook_audio.webm"
            )
            
            if not is_valid:
                raise HTTPException(status_code=400, detail=error_msg)
            
            # Save the file
            file_path, stored_filename = processor.save_file(file_content, file_info)
            
            # Create note in database quickly
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn = self.get_conn()
            c = conn.cursor()
            
            # Insert note with pending status for background processing
            c.execute(
                """
                INSERT INTO notes (
                    title, content, summary, tags, actions, type, timestamp,
                    audio_filename, file_filename, file_type, file_mime_type, 
                    file_size, extracted_text, file_metadata, status, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Incoming Audio",  # Will be updated after processing
                    "",  # Will be filled with transcript
                    "",
                    tags,
                    "",
                    "audio",
                    now,
                    stored_filename,
                    stored_filename,
                    "audio", 
                    file.content_type,
                    len(file_content),
                    "",
                    json.dumps(file_info, default=str) if file_info else None,
                    "pending",
                    user_id,
                ),
            )
            
            note_id = c.lastrowid
            
            # Add to FTS for immediate searchability (even before transcription)
            c.execute(
                """
                INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (note_id, "Incoming Audio", "", tags, "", "", ""),
            )
            
            conn.commit()
            conn.close()
            
            # Add to FIFO processing queue
            from services.audio_queue import audio_queue
            audio_queue.add_to_queue(note_id, user_id)
            
            # Start batch timer if batch mode is enabled
            if settings.batch_mode_enabled:
                audio_queue.start_batch_timer()
            
            # Start background processing 
            from tasks import process_audio_queue
            background_tasks.add_task(process_audio_queue)
            
            return {
                "success": True,
                "id": note_id,
                "status": "queued",
                "message": "Audio uploaded successfully and queued for processing",
                "filename": stored_filename,
                "queue_position": "pending"
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
    
    # --- Discord Webhooks ---
    
    async def process_discord_webhook_legacy(
        self, 
        data: DiscordWebhook,
        background_tasks: BackgroundTasks
    ) -> dict:
        """Enhanced Discord webhook with user mapping."""
        # Map Discord user to Second Brain user
        conn = self.get_conn()
        c = conn.cursor()
        
        # Check if Discord user is linked
        discord_link = c.execute(
            "SELECT user_id FROM discord_users WHERE discord_id = ?",
            (data.discord_user_id,)
        ).fetchone()
        
        if not discord_link:
            # Auto-register or return error
            raise HTTPException(
                status_code=401, 
                detail="Discord user not linked. Use !link command first."
            )
        
        user_id = discord_link[0]
        
        # Process note with AI
        result = ollama_summarize(data.note)
        summary = result.get("summary", "")
        ai_tags = result.get("tags", [])
        ai_actions = result.get("actions", [])
        
        # Combine tags
        tag_list = [t.strip() for t in data.tags.split(",") if t.strip()]
        tag_list.extend([t for t in ai_tags if t and t not in tag_list])
        tags = ",".join(tag_list)
        
        # Save note
        c.execute(
            "INSERT INTO notes (title, content, summary, tags, actions, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data.note[:60] + "..." if len(data.note) > 60 else data.note,
                data.note,
                summary,
                tags,
                "\n".join(ai_actions),
                data.type,
                data.timestamp,
                user_id
            ),
        )
        conn.commit()
        note_id = c.lastrowid
        
        # Update FTS
        c.execute(
            "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, data.note[:60], summary, tags, "\n".join(ai_actions), data.note),
        )
        conn.commit()
        conn.close()
        
        return {"status": "ok", "note_id": note_id}
    
    def process_discord_webhook(self, data: dict, user_id: int) -> dict:
        """Process Discord webhook with AI summarization."""
        note = data.get("note", "")
        tags = data.get("tags", "")
        note_type = data.get("type", "discord")
        
        # Process note with AI
        result = ollama_summarize(note)
        summary = result.get("summary", "")
        ai_tags = result.get("tags", [])
        ai_actions = result.get("actions", [])
        
        # Combine tags
        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        tag_list.extend([t for t in ai_tags if t and t not in tag_list])
        final_tags = ",".join(tag_list)
        actions = "\n".join(ai_actions)
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self.get_conn()
        c = conn.cursor()
        
        c.execute(
            "INSERT INTO notes (title, content, summary, tags, actions, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                note[:60] + "..." if len(note) > 60 else note,
                note,
                summary,
                final_tags,
                actions,
                note_type,
                now,
                user_id,
            ),
        )
        conn.commit()
        note_id = c.lastrowid
        
        c.execute(
            "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, note[:60] + "..." if len(note) > 60 else note, summary, final_tags, actions, note),
        )
        conn.commit()
        conn.close()
        
        return {"status": "ok", "note_id": note_id}
    
    async def process_discord_upload_webhook(
        self,
        file: UploadFile,
        note: str,
        tags: str,
        discord_user_id: str,
        note_type: str,
        background_tasks: BackgroundTasks
    ) -> dict:
        """Discord-specific file upload webhook that bypasses CSRF."""
        
        # Map Discord user to Second Brain user if needed
        conn = self.get_conn()
        c = conn.cursor()
        
        # Check if Discord user is linked to a Second Brain account
        c.execute("SELECT user_id, username FROM user_discord_links WHERE discord_user_id = ?", (discord_user_id,))
        link = c.fetchone()
        
        if link:
            # Use linked user
            user_id = link[0]
        else:
            # Create or get default Discord user
            username = f"discord_{discord_user_id}"
            c.execute("SELECT id FROM users WHERE username = ?", (username,))
            existing_user = c.fetchone()
            
            if existing_user:
                user_id = existing_user[0]
            else:
                # Create new user for this Discord user
                temp_password = secrets.token_urlsafe(16)
                hashed_password = self.auth_service.get_password_hash(temp_password)
                
                c.execute(
                    "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
                    (username, hashed_password, f"{username}@discord.local")
                )
                user_id = c.lastrowid
            
            # Create the Discord link
            c.execute(
                "INSERT OR REPLACE INTO user_discord_links (discord_user_id, user_id, username) VALUES (?, ?, ?)",
                (discord_user_id, user_id, username)
            )
            conn.commit()
        
        conn.close()
        
        # Use existing file upload logic but without CSRF requirements
        try:
            # Create temporary file to save the uploaded content
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or "").suffix) as tmp_file:
                # Read file content in chunks
                chunk_size = 1024 * 1024  # 1MB chunks
                total_size = 0
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > settings.max_file_size:
                        tmp_file.close()
                        Path(tmp_file.name).unlink(missing_ok=True)
                        raise HTTPException(status_code=400, detail=f"File too large ({total_size} bytes, max {settings.max_file_size})")
                    tmp_file.write(chunk)
                
                tmp_path = Path(tmp_file.name)
            
            # Process the uploaded file
            processor = FileProcessor()
            result = processor.process_saved_file(tmp_path, file.filename or "unknown")
            
            if not result['success']:
                raise HTTPException(status_code=400, detail=f"File processing failed: {result['error']}")
            
            # Create note entry
            file_info = result['file_info']
            file_note_type = file_info['category']  # audio, image, document
            stored_filename = result['stored_filename']
            extracted_text = result['extracted_text']
            
            # Combine note content with extracted text
            combined_content = []
            if note.strip():
                combined_content.append(note.strip())
            if extracted_text.strip():
                combined_content.append(f"[Extracted Content]\n{extracted_text.strip()}")
            
            final_content = "\n\n".join(combined_content) if combined_content else ""
            
            # Save to database
            conn = self.get_conn()
            c = conn.cursor()
            
            c.execute("""
                INSERT INTO notes (
                    user_id, title, content, tags, type, timestamp, 
                    file_filename, file_type, file_mime_type, file_size,
                    processing_status, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                file.filename or f"Discord Upload {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                final_content,
                tags,
                file_note_type,
                datetime.now().isoformat(),
                stored_filename,
                file_note_type,
                file_info['mime_type'],
                file_info['size_bytes'],
                "processing" if file_note_type in ["audio", "image", "document"] else "completed",
                "discord_upload"
            ))
            
            note_id = c.lastrowid
            
            # Queue background processing for audio files
            if file_note_type == "audio" and stored_filename:
                audio_path = settings.audio_dir / stored_filename
                if audio_path.exists():
                    c.execute(
                        "INSERT INTO processing_tasks (note_id, task_type, status, file_path, created_at) VALUES (?, ?, ?, ?, ?)",
                        (note_id, "transcription", "pending", str(audio_path), datetime.now().isoformat())
                    )
                    
                    # Add to audio queue for processing
                    from services.audio_queue import audio_queue
                    if audio_queue:
                        background_tasks.add_task(audio_queue.add_job, str(audio_path), note_id)
            
            conn.commit()
            conn.close()
            
            # Clean up temp file
            tmp_path.unlink(missing_ok=True)
            
            return {
                "success": True,
                "note_id": note_id,
                "extracted_text": extracted_text,
                "file_size": file_info['size_bytes'],
                "file_type": file_note_type,
                "message": "Discord file uploaded successfully"
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Discord upload failed: {e}")
    
    # --- Apple Shortcuts Webhooks ---
    
    def process_apple_reminder_webhook(self, data: AppleReminderWebhook, user_id: int) -> dict:
        """Create reminder from Apple Shortcuts."""
        conn = self.get_conn()
        c = conn.cursor()
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Create note
        c.execute(
            "INSERT INTO notes (title, content, summary, tags, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                data.title,
                data.notes,
                f"Reminder: {data.title}",
                data.tags,
                "reminder",
                now,
                user_id
            ),
        )
        note_id = c.lastrowid
        
        # Create reminder entry
        c.execute(
            "INSERT INTO reminders (note_id, user_id, due_date, completed) VALUES (?, ?, ?, ?)",
            (note_id, user_id, data.due_date, False)
        )
        
        conn.commit()
        conn.close()
        
        return {"status": "ok", "reminder_id": note_id}
    
    def process_apple_calendar_webhook(self, data: CalendarEvent, user_id: int) -> dict:
        """Create calendar event and meeting note."""
        conn = self.get_conn()
        c = conn.cursor()
        
        meeting_note = f"""
Meeting: {data.title}
Date: {data.start_date} - {data.end_date}
Attendees: {', '.join(data.attendees)}

{data.description}

--- Meeting Notes ---
(This will be filled during/after the meeting)
"""
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute(
            "INSERT INTO notes (title, content, summary, tags, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                f"Meeting: {data.title}",
                meeting_note,
                f"Scheduled meeting: {data.title}",
                "meeting,calendar,scheduled",
                "meeting",
                now,
                user_id
            ),
        )
        
        conn.commit()
        conn.close()
        
        return {"status": "ok", "event_created": True}
    
    def process_apple_webhook(self, data: dict, user_id: int) -> dict:
        """Process Apple Shortcuts webhook."""
        note = data.get("note", "")
        tags = data.get("tags", "")
        note_type = data.get("type", "apple")
        
        result = ollama_summarize(note)
        summary = result.get("summary", "")
        ai_tags = result.get("tags", [])
        ai_actions = result.get("actions", [])
        
        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        tag_list.extend([t for t in ai_tags if t and t not in tag_list])
        final_tags = ",".join(tag_list)
        actions = "\n".join(ai_actions)
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self.get_conn()
        c = conn.cursor()
        
        c.execute(
            "INSERT INTO notes (title, content, summary, tags, actions, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                note[:60] + "..." if len(note) > 60 else note,
                note,
                summary,
                final_tags,
                actions,
                note_type,
                now,
                user_id,
            ),
        )
        conn.commit()
        note_id = c.lastrowid
        
        c.execute(
            "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, note[:60] + "..." if len(note) > 60 else note, summary, final_tags, actions, note),
        )
        conn.commit()
        conn.close()
        
        return {"status": "ok", "note_id": note_id}
    
    # --- Browser Webhook ---
    
    def process_browser_webhook(self, data: dict, user_id: int) -> dict:
        """Process browser extension webhook."""
        # Similar to Apple webhook but for browser content
        url = data.get("url", "")
        title = data.get("title", "")
        content = data.get("content", "")
        tags = data.get("tags", "browser,web")
        
        # Create formatted content
        formatted_content = f"URL: {url}\n\n{content}" if url else content
        
        # Use AI to process if content is substantial
        if len(content) > 50:
            result = ollama_summarize(content)
            summary = result.get("summary", "")
            ai_tags = result.get("tags", [])
        else:
            summary = title or "Browser capture"
            ai_tags = []
        
        # Combine tags
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        tag_list.extend([t for t in ai_tags if t and t not in tag_list])
        final_tags = ",".join(tag_list)
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self.get_conn()
        c = conn.cursor()
        
        c.execute(
            "INSERT INTO notes (title, content, summary, tags, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                title or formatted_content[:60] + "..." if len(formatted_content) > 60 else formatted_content,
                formatted_content,
                summary,
                final_tags,
                "browser",
                now,
                user_id,
            ),
        )
        conn.commit()
        note_id = c.lastrowid
        
        c.execute(
            "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, title or formatted_content[:60], summary, final_tags, "", formatted_content),
        )
        conn.commit()
        conn.close()
        
        return {"status": "ok", "note_id": note_id}