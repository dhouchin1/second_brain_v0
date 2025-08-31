#!/usr/bin/env python3
"""
Enhanced Capture Endpoint for Multiple File Types
Supports images, PDFs, and documents in addition to audio
"""

import json
import asyncio
from datetime import datetime
from fastapi import UploadFile, Form, Request, BackgroundTasks, HTTPException
from fastapi.responses import RedirectResponse

from file_processor import FileProcessor
from tasks_enhanced import process_note_enhanced
from config import settings

# Import existing functions from app.py
def get_current_user_silent(request):
    """Import this from app.py"""
    pass

def validate_csrf(request, token):
    """Import this from app.py"""
    pass

def get_conn():
    """Import this from app.py"""
    pass

async def capture_enhanced(
    request: Request,
    background_tasks: BackgroundTasks,
    note: str = Form(""),
    tags: str = Form(""),
    file: UploadFile = File(None),
    csrf_token: str | None = Form(None),
):
    """Enhanced capture endpoint with multi-file support"""
    
    # Auth validation
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    
    # CSRF validation
    csrf_valid = validate_csrf(request, csrf_token)
    if not csrf_valid:
        header_token = request.headers.get("X-CSRF-Token")
        if header_token:
            csrf_valid = validate_csrf(request, header_token)
    
    if not csrf_valid:
        error_msg = "CSRF token validation failed"
        if "application/json" in request.headers.get("accept", ""):
            raise HTTPException(status_code=400, detail=error_msg)
        return RedirectResponse("/", status_code=302)
    
    # Process the submission
    content = note.strip()
    note_type = "text"  # Default type
    stored_filename = None
    extracted_text = ""
    file_metadata = {}
    processing_status = "complete"  # Text notes are complete immediately
    
    # Handle file upload if present
    if file and file.filename:
        try:
            # Read file content
            file_content = await file.read()
            
            # Process with FileProcessor
            processor = FileProcessor()
            result = processor.process_file(file_content, file.filename)
            
            if not result['success']:
                error_msg = f"File processing failed: {result['error']}"
                if "application/json" in request.headers.get("accept", ""):
                    raise HTTPException(status_code=400, detail=error_msg)
                return RedirectResponse("/?error=" + error_msg, status_code=302)
            
            # Update note details based on file processing
            file_info = result['file_info']
            note_type = file_info['category']
            stored_filename = result['stored_filename']
            extracted_text = result['extracted_text']
            file_metadata = {
                'original_filename': file_info['original_filename'],
                'mime_type': file_info['mime_type'],
                'size_bytes': file_info['size_bytes'],
                'processing_type': result['processing_type'],
                'metadata': result['metadata']
            }
            
            # Set processing status based on file type
            if note_type == 'audio':
                processing_status = "pending"  # Audio needs transcription
            else:
                processing_status = "complete"  # Images/PDFs are processed immediately
                # Use extracted text as content if no manual note provided
                if not content and extracted_text:
                    content = extracted_text
                    
        except Exception as e:
            error_msg = f"File upload failed: {str(e)}"
            if "application/json" in request.headers.get("accept", ""):
                raise HTTPException(status_code=400, detail=error_msg)
            return RedirectResponse("/?error=" + error_msg, status_code=302)
    
    # Generate title and prepare for database
    title = content[:60] if content else (
        f"File: {file.filename}" if file and file.filename else "New Note"
    )
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Save to database
    conn = get_conn()
    c = conn.cursor()
    
    try:
        # Insert main note record
        c.execute("""
            INSERT INTO notes (
                title, content, summary, tags, actions, type, timestamp, 
                audio_filename, file_filename, file_type, file_mime_type, 
                file_size, extracted_text, file_metadata, status, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            title,
            content,
            "",  # summary will be generated later
            tags,
            "",  # actions will be generated later
            note_type,
            now,
            stored_filename if note_type == 'audio' else None,  # legacy audio field
            stored_filename,  # new generic file field
            note_type,
            file_metadata.get('mime_type'),
            file_metadata.get('size_bytes'),
            extracted_text,
            json.dumps(file_metadata) if file_metadata else None,
            processing_status,
            current_user.id
        ))
        
        note_id = c.lastrowid
        
        # Insert into FTS
        c.execute("""
            INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (note_id, title, "", tags, "", content, extracted_text))
        
        conn.commit()
        
        # Queue background processing if needed
        if processing_status == "pending":
            background_tasks.add_task(
                process_note_enhanced,
                note_id,
                note_type,
                stored_filename,
                content
            )
        
        # Return success response
        if "application/json" in request.headers.get("accept", ""):
            return {
                "success": True, 
                "note_id": note_id,
                "status": processing_status,
                "file_type": note_type,
                "message": f"{'File uploaded and queued for processing' if processing_status == 'pending' else 'Note saved successfully'}"
            }
        else:
            success_msg = f"Note saved successfully"
            if processing_status == "pending":
                success_msg += " and queued for processing"
            return RedirectResponse(f"/?success={success_msg}", status_code=302)
            
    except Exception as e:
        conn.rollback()
        error_msg = f"Database error: {str(e)}"
        if "application/json" in request.headers.get("accept", ""):
            raise HTTPException(status_code=500, detail=error_msg)
        return RedirectResponse("/?error=" + error_msg, status_code=302)
    finally:
        conn.close()

# File serving endpoints
async def serve_file(filename: str, current_user):
    """Serve uploaded files (images, PDFs, etc.)"""
    from fastapi.responses import FileResponse
    import mimetypes
    
    # Check if file belongs to user
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT file_type, file_mime_type FROM notes WHERE file_filename = ? AND user_id = ?",
        (filename, current_user.id),
    ).fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_type, mime_type = row
    
    # Determine file path based on type
    if file_type == 'audio':
        file_path = settings.audio_dir / filename
    else:
        file_path = settings.uploads_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine content type
    content_type = mime_type or mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream'
    
    return FileResponse(
        str(file_path),
        media_type=content_type,
        filename=filename
    )