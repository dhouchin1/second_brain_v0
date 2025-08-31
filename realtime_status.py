"""
Real-time status updates using Server-Sent Events (SSE)
"""
import json
import asyncio
import sqlite3
from datetime import datetime
from typing import Dict, Set, Optional, AsyncGenerator
from fastapi import Request
from fastapi.responses import StreamingResponse
from config import settings
# Avoid importing app-level symbols at module import time to prevent circular imports.
import logging

logger = logging.getLogger(__name__)


class StatusManager:
    """Manages real-time status updates for note processing"""
    
    def __init__(self):
        # Store active connections for each note_id
        self.connections: Dict[int, Set[asyncio.Queue]] = {}
        
    def get_conn(self):
        return sqlite3.connect(str(settings.db_path))
    
    async def subscribe_to_note(self, note_id: int) -> asyncio.Queue:
        """Subscribe to status updates for a specific note"""
        if note_id not in self.connections:
            self.connections[note_id] = set()
        
        queue = asyncio.Queue()
        self.connections[note_id].add(queue)
        return queue
    
    async def unsubscribe_from_note(self, note_id: int, queue: asyncio.Queue):
        """Unsubscribe from status updates"""
        if note_id in self.connections:
            self.connections[note_id].discard(queue)
            if not self.connections[note_id]:
                del self.connections[note_id]
    
    async def broadcast_status(self, note_id: int, status_data: dict):
        """Broadcast status update to all subscribers of a note"""
        if note_id not in self.connections:
            return
        
        # Remove closed connections
        active_queues = set()
        for queue in self.connections[note_id]:
            try:
                queue.put_nowait(status_data)
                active_queues.add(queue)
            except asyncio.QueueFull:
                # Skip full queues
                pass
        
        self.connections[note_id] = active_queues
    
    async def emit_progress(self, note_id: int, stage: str, progress: int, message: str = ""):
        """Emit a progress update"""
        status_data = {
            "note_id": note_id,
            "stage": stage,
            "progress": progress,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        
        # Update database
        conn = self.get_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE notes SET status = ? WHERE id = ?",
            (f"{stage}:{progress}", note_id)
        )
        conn.commit()
        conn.close()
        
        # Broadcast to subscribers
        await self.broadcast_status(note_id, status_data)
    
    async def emit_completion(self, note_id: int, success: bool = True, error_message: str = ""):
        """Emit completion status"""
        status_data = {
            "note_id": note_id,
            "stage": "complete" if success else "error",
            "progress": 100 if success else -1,
            "message": error_message if not success else "Processing complete",
            "timestamp": datetime.now().isoformat(),
            "completed": True,
            "success": success
        }
        
        # Update database
        conn = self.get_conn()
        c = conn.cursor()
        status_value = "complete" if success else f"error:{error_message}"
        c.execute(
            "UPDATE notes SET status = ? WHERE id = ?",
            (status_value, note_id)
        )
        conn.commit()
        conn.close()
        
        # Broadcast to subscribers
        await self.broadcast_status(note_id, status_data)
    
    async def get_note_status(self, note_id: int) -> Optional[dict]:
        """Get current status of a note"""
        conn = self.get_conn()
        c = conn.cursor()
        
        row = c.execute(
            "SELECT id, title, status, timestamp, type, user_id FROM notes WHERE id = ?",
            (note_id,)
        ).fetchone()
        
        conn.close()
        
        if not row:
            return None
        
        status = row[2] or "unknown"
        
        # Parse status
        if ":" in status:
            stage, progress_str = status.split(":", 1)
            try:
                progress = int(progress_str)
            except ValueError:
                progress = 0
        else:
            stage = status
            progress = 100 if status == "complete" else 0
        
        return {
            "note_id": row[0],
            "title": row[1],
            "stage": stage,
            "progress": progress,
            "timestamp": row[3],
            "type": row[4],
            "user_id": row[5],
            "completed": status == "complete"
        }


# Global status manager instance
status_manager = StatusManager()


async def create_sse_stream(note_id: int, user_id: int) -> AsyncGenerator[str, None]:
    """Create SSE stream for note status updates"""
    
    # Send initial status
    initial_status = await status_manager.get_note_status(note_id)
    if not initial_status:
        yield f"data: {json.dumps({'error': 'Note not found'})}\n\n"
        return
    
    # Check user permission
    if initial_status['user_id'] != user_id:
        yield f"data: {json.dumps({'error': 'Permission denied'})}\n\n"
        return
    
    # Send initial status
    yield f"data: {json.dumps(initial_status)}\n\n"
    
    # If already complete, close stream
    if initial_status.get('completed'):
        return
    
    # Subscribe to updates
    queue = await status_manager.subscribe_to_note(note_id)
    
    try:
        while True:
            try:
                # Wait for status update with timeout
                status_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(status_data)}\n\n"
                
                # Close stream if processing is complete
                if status_data.get('completed'):
                    break
                    
            except asyncio.TimeoutError:
                # Send keepalive
                yield f"data: {json.dumps({'keepalive': True})}\n\n"
                
    except asyncio.CancelledError:
        # Client disconnected
        pass
    finally:
        await status_manager.unsubscribe_from_note(note_id, queue)


def create_status_endpoint(app):
    """Add status streaming endpoints to FastAPI app"""
    
    @app.get("/api/status/stream/{note_id}")
    async def stream_note_status(note_id: int, request: Request, token: str | None = None):
        """Stream real-time status updates for a note - simplified auth"""
        
        # SIMPLE FIX: Check if note is complete first, no auth needed for completed notes
        conn = status_manager.get_conn()
        c = conn.cursor()
        row = c.execute("SELECT status FROM notes WHERE id = ?", (note_id,)).fetchone()
        conn.close()
        
        if row and row[0] == 'complete':
            # Note is complete - return completion status and close stream immediately
            async def _complete_stream():
                yield f"data: {json.dumps({'note_id': note_id, 'stage': 'complete', 'progress': 100, 'completed': True})}\n\n"
            return StreamingResponse(
                _complete_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )
        
        # For non-complete notes, try authentication
        user_id: int | None = None
        try:
            current_user = __import__('app').get_current_user_silent(request)
            user_id = getattr(current_user, 'id', None) if current_user else None
        except Exception:
            user_id = None
            
        if not user_id:
            # No auth - return error and close
            async def _unauth_stream():
                yield f"data: {json.dumps({'error': 'unauthorized'})}\n\n"
            return StreamingResponse(
                _unauth_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )

        # Dynamic CORS for credentialed SSE if cross-origin
        origin = request.headers.get('origin')
        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        if origin:
            headers.update({
                "Access-Control-Allow-Origin": origin,
                "Vary": "Origin",
                "Access-Control-Allow-Credentials": "true",
            })

        logger.debug(f"SSE stream authorized for note {note_id}, uid={user_id}")
        return StreamingResponse(
            create_sse_stream(note_id, user_id),
            media_type="text/event-stream",
            headers=headers,
        )
    
    @app.get("/api/status/queue")
    async def get_processing_queue(request: Request, token: str | None = None):
        """Get current processing queue status (supports token auth)."""
        # Resolve user_id via cookie/session or signed token
        user_id = None
        try:
            current_user = __import__('app').get_current_user_silent(request)
            user_id = getattr(current_user, 'id', None) if current_user else None
        except Exception:
            user_id = None
        if not user_id and token:
            try:
                from jose import jwt
                app_mod = __import__('app')
                payload = jwt.decode(token, app_mod.SECRET_KEY, algorithms=[app_mod.ALGORITHM])
                uid = payload.get('uid')
                sub = payload.get('sub')
                if uid is not None:
                    user_id = int(uid)
                elif sub:
                    user = app_mod.get_user(sub)
                    user_id = user.id if user else None
            except Exception:
                user_id = None
        if not user_id:
            logger.debug("Queue status auth failed: no cookie user and no valid token")
            # Return empty queue with 200 to avoid noisy 401s
            origin = request.headers.get('origin')
            payload = {"queue": [], "total_pending": 0}
            if origin:
                return JSONResponse(payload, headers={
                    "Access-Control-Allow-Origin": origin,
                    "Vary": "Origin",
                    "Access-Control-Allow-Credentials": "true",
                })
            return payload

        conn = status_manager.get_conn()
        c = conn.cursor()
        
        # Get pending notes
        pending_notes = c.execute(
            """SELECT id, title, status, timestamp, type 
               FROM notes 
               WHERE user_id = ? AND (status = 'pending' OR status LIKE '%:%')
               ORDER BY timestamp DESC""",
            (user_id,)
        ).fetchall()
        
        queue_items = []
        for note in pending_notes:
            status = note[2] or "pending"
            if ":" in status:
                stage, progress_str = status.split(":", 1)
                try:
                    progress = int(progress_str)
                except ValueError:
                    progress = 0
            else:
                stage = status
                progress = 0
                
            queue_items.append({
                "id": note[0],
                "title": note[1],
                "stage": stage,
                "progress": progress,
                "timestamp": note[3],
                "type": note[4]
            })
        
        conn.close()
        
        result = {
            "queue": queue_items,
            "total_pending": len(queue_items)
        }
        # Dynamic CORS if used cross-origin
        origin = request.headers.get('origin')
        if origin:
            from fastapi.responses import JSONResponse
            return JSONResponse(result, headers={
                "Access-Control-Allow-Origin": origin,
                "Vary": "Origin",
                "Access-Control-Allow-Credentials": "true",
            })
        return result

    @app.get("/api/status/note/{note_id}")
    async def get_note_status_api(note_id: int, request: Request, token: str | None = None):
        """Polling endpoint for a single note's status (supports token auth)."""
        # Resolve user id
        user_id = None
        try:
            current_user = __import__('app').get_current_user_silent(request)
            user_id = getattr(current_user, 'id', None) if current_user else None
        except Exception:
            user_id = None
        if not user_id and token:
            try:
                from jose import jwt
                app_mod = __import__('app')
                payload = jwt.decode(token, app_mod.SECRET_KEY, algorithms=[app_mod.ALGORITHM])
                uid = payload.get('uid')
                sub = payload.get('sub')
                if uid is not None:
                    user_id = int(uid)
                elif sub:
                    user = app_mod.get_user(sub)
                    user_id = user.id if user else None
            except Exception:
                user_id = None
        if not user_id:
            logger.debug(f"Note status auth failed for note {note_id}: no cookie user and no valid token")
            payload = {"error": "unauthorized"}
            origin = request.headers.get('origin')
            if origin:
                return JSONResponse(payload, headers={
                    "Access-Control-Allow-Origin": origin,
                    "Vary": "Origin",
                    "Access-Control-Allow-Credentials": "true",
                })
            return payload

        status = await status_manager.get_note_status(note_id)
        if not status:
            payload = {"error": "not_found"}
        elif status.get('user_id') != user_id:
            payload = {"error": "forbidden"}
        else:
            payload = status

        origin = request.headers.get('origin')
        if origin:
            from fastapi.responses import JSONResponse
            return JSONResponse(payload, headers={
                "Access-Control-Allow-Origin": origin,
                "Vary": "Origin",
                "Access-Control-Allow-Credentials": "true",
            })
        return payload


# Export for use in other modules
__all__ = ["status_manager", "create_status_endpoint"]
