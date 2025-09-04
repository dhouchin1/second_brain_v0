"""
Upload Service

Handles file upload operations including chunked/resumable uploads.
Extracted from app.py to provide clean separation of upload concerns.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from services.auth_service import User
from config import settings
from file_processor import FileProcessor
from obsidian_sync import ObsidianSync


class UploadService:
    """Service for handling file upload operations."""
    
    def __init__(self, get_conn_func, auth_service, audio_queue):
        """Initialize upload service with dependencies."""
        self.get_conn = get_conn_func
        self.auth_service = auth_service
        self.audio_queue = audio_queue
    
    # --- Helper Methods ---
    
    def _get_incoming_dir(self) -> Path:
        """Get incoming directory for temporary files."""
        incoming_dir = settings.base_dir / "incoming"
        incoming_dir.mkdir(exist_ok=True)
        return incoming_dir
    
    def _get_manifest_path(self, upload_id: str) -> Path:
        """Get path for upload manifest file."""
        return self._get_incoming_dir() / f"{upload_id}.json"
    
    def _get_part_path(self, upload_id: str) -> Path:
        """Get path for upload part file."""
        return self._get_incoming_dir() / f"{upload_id}.part"
    
    def _load_manifest(self, upload_id: str) -> Optional[dict]:
        """Load upload manifest from disk."""
        p = self._get_manifest_path(upload_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    
    def _save_manifest(self, upload_id: str, data: dict) -> None:
        """Save upload manifest to disk."""
        p = self._get_manifest_path(upload_id)
        p.write_text(json.dumps(data))
    
    # --- Upload Operations ---
    
    async def init_upload(self, request: Request, data: dict, current_user: User) -> dict:
        """Initialize a resumable upload."""
        # Validate CSRF token
        csrf_header = request.headers.get("X-CSRF-Token")
        if not self.auth_service.validate_csrf(request, csrf_header):
            raise HTTPException(status_code=400, detail="Invalid CSRF token")

        filename = (data or {}).get("filename")
        total_size = (data or {}).get("total_size")
        mime_type = (data or {}).get("mime_type")
        if not filename:
            raise HTTPException(status_code=400, detail="filename required")

        upload_id = uuid.uuid4().hex
        manifest = {
            "upload_id": upload_id,
            "filename": filename,
            "total_size": int(total_size) if total_size is not None else None,
            "mime_type": mime_type,
            "created_by": current_user.id,
            "created_at": datetime.utcnow().isoformat(),
            "status": "active",
        }
        self._save_manifest(upload_id, manifest)
        # Ensure empty part file
        self._get_part_path(upload_id).write_bytes(b"")
        return {"upload_id": upload_id, "offset": 0}
    
    async def get_upload_status(self, upload_id: str, current_user: User) -> dict:
        """Get status of an upload."""
        manifest = self._load_manifest(upload_id)
        if not manifest or manifest.get("created_by") != current_user.id:
            raise HTTPException(status_code=404, detail="Upload not found")
        part_path = self._get_part_path(upload_id)
        size = part_path.stat().st_size if part_path.exists() else 0
        return {
            "upload_id": upload_id,
            "offset": size,
            "status": manifest.get("status", "active"),
            "filename": manifest.get("filename"),
            "total_size": manifest.get("total_size"),
        }
    
    async def upload_chunk(self, request: Request, upload_id: str, offset: int, current_user: User) -> dict:
        """Append a chunk to an active upload."""
        # Validate CSRF token
        csrf_header = request.headers.get("X-CSRF-Token")
        if not self.auth_service.validate_csrf(request, csrf_header):
            raise HTTPException(status_code=400, detail="Invalid CSRF token")

        manifest = self._load_manifest(upload_id)
        if not manifest or manifest.get("created_by") != current_user.id:
            raise HTTPException(status_code=404, detail="Upload not found")
        if manifest.get("status") != "active":
            raise HTTPException(status_code=400, detail="Upload not active")

        part_path = self._get_part_path(upload_id)
        part_path.parent.mkdir(parents=True, exist_ok=True)
        current_size = part_path.stat().st_size if part_path.exists() else 0
        if current_size != int(offset):
            # Client should resume from server-reported offset
            return JSONResponse({"expected_offset": current_size}, status_code=409)

        # Read raw body in chunks and append
        max_size = settings.max_file_size
        total_after = current_size
        try:
            with open(part_path, "ab") as out:
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    total_after += len(chunk)
                    if total_after > max_size:
                        raise HTTPException(status_code=400, detail=f"File too large (>{max_size} bytes)")
                    out.write(chunk)
            return {"upload_id": upload_id, "offset": total_after}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Chunk append failed: {e}")
    
    async def finalize_upload(
        self, 
        request: Request, 
        background_tasks: BackgroundTasks, 
        upload_id: str, 
        note: str, 
        tags: str, 
        current_user: User
    ) -> dict:
        """Finalize an upload and create a note."""
        # Validate CSRF token
        csrf_header = request.headers.get("X-CSRF-Token")
        if not self.auth_service.validate_csrf(request, csrf_header):
            raise HTTPException(status_code=400, detail="Invalid CSRF token")

        manifest = self._load_manifest(upload_id)
        if not manifest or manifest.get("created_by") != current_user.id:
            raise HTTPException(status_code=404, detail="Upload not found")
        if manifest.get("status") != "active":
            raise HTTPException(status_code=400, detail="Upload not active")

        part_path = self._get_part_path(upload_id)
        if not part_path.exists():
            raise HTTPException(status_code=400, detail="No data uploaded")

        # Process the saved file
        processor = FileProcessor()
        result = processor.process_saved_file(part_path, manifest.get("filename") or "uploaded.bin")
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=f"File processing failed: {result.get('error')}")

        manifest["status"] = "finalized"
        self._save_manifest(upload_id, manifest)

        file_info = result['file_info']
        note_type = file_info['category']
        stored_filename = result['stored_filename']
        extracted_text = result.get('extracted_text', "")
        file_metadata = {
            'original_filename': file_info['original_filename'],
            'mime_type': file_info['mime_type'],
            'size_bytes': file_info['size_bytes'],
            'processing_type': result['processing_type'],
            'metadata': result.get('metadata'),
        }
        processing_status = "pending" if note_type == 'audio' else "complete"
        content = (note or "").strip()
        if processing_status == "complete" and not content and extracted_text:
            content = extracted_text[:1000]

        title = content[:60] if content else (f"File: {file_info['original_filename']}" if file_info['original_filename'] else "New Note")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Save to database
        conn = self.get_conn()
        c = conn.cursor()
        try:
            c.execute(
                """
                INSERT INTO notes (
                    title, content, summary, tags, actions, type, timestamp,
                    audio_filename, file_filename, file_type, file_mime_type,
                    file_size, extracted_text, file_metadata, status, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    content,
                    "",
                    tags,
                    "",
                    note_type,
                    now,
                    stored_filename if note_type == 'audio' else None,
                    stored_filename,
                    note_type,
                    file_metadata.get('mime_type'),
                    file_metadata.get('size_bytes'),
                    extracted_text,
                    json.dumps(file_metadata, default=str) if file_metadata else None,
                    processing_status,
                    current_user.id,
                ),
            )
            note_id = c.lastrowid
            c.execute(
                """
                INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (note_id, title, "", tags, "", content, extracted_text),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Database error: {e}")
        finally:
            conn.close()

        # After note is created, export an Obsidian markdown file in background
        try:
            sync = ObsidianSync()
            background_tasks.add_task(sync.export_note_to_obsidian, note_id)
        except Exception:
            pass

        # Queue background processing for audio using FIFO queue
        if processing_status == "pending":
            # Add to FIFO queue for ordered processing
            self.audio_queue.add_to_queue(note_id, current_user.id)
            
            # Start queue worker as background task
            from tasks import process_audio_queue
            background_tasks.add_task(process_audio_queue)
            return {
                "success": True,
                "id": note_id,
                "status": processing_status,
                "file_type": note_type,
                "message": "Upload finalized and queued for processing",
            }

        return {"success": True, "id": note_id, "status": processing_status, "file_type": note_type, "message": "Upload finalized"}