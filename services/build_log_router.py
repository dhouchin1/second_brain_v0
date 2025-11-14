"""
Build Log Router

FastAPI router for build log web interface and API endpoints.

Provides:
- Web UI for viewing sessions
- API endpoints for CRUD operations
- Search and analytics
- Screenshot capture
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
from pathlib import Path

from services.build_log_service import get_build_log_service

# Router setup
router = APIRouter(prefix="/build-logs", tags=["build-logs"])

# Templates
templates = Jinja2Templates(directory="templates")

# Database connection (will be injected)
_db_connection = None


def init_build_log_router(db_connection):
    """Initialize router with database connection"""
    global _db_connection
    _db_connection = db_connection


def get_service():
    """Get build log service instance"""
    if _db_connection is None:
        raise HTTPException(status_code=500, detail="Router not initialized")
    return get_build_log_service(_db_connection)


# ============================================================================
# Pydantic Models
# ============================================================================

class CreateSessionRequest(BaseModel):
    """Request model for creating a build log session"""
    task_description: str
    conversation_log: str
    files_changed: Optional[List[str]] = None
    commands_executed: Optional[List[str]] = None
    duration_minutes: Optional[int] = None
    outcomes: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None


class UpdateSessionRequest(BaseModel):
    """Request model for updating a build log session"""
    title: Optional[str] = None
    body: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ============================================================================
# Web UI Routes
# ============================================================================

@router.get("/", response_class=HTMLResponse)
async def build_logs_index(request: Request, page: int = Query(1, ge=1)):
    """
    Build logs dashboard - list all sessions with pagination.
    """
    service = get_service()

    # Pagination
    per_page = 20
    offset = (page - 1) * per_page

    # Get sessions
    sessions = service.list_sessions(limit=per_page, offset=offset)
    total = service.count_sessions()
    total_pages = (total + per_page - 1) // per_page

    # Process sessions for display
    for session in sessions:
        metadata = session.get('metadata', {})
        session['session_id'] = metadata.get('session_id', 'N/A')
        session['task'] = metadata.get('task_description', session.get('title', 'Untitled'))
        session['duration'] = metadata.get('duration_minutes')

        # Technical context
        tech_context = metadata.get('technical_context', {})
        session['files_count'] = len(tech_context.get('files_changed', []))
        session['commands_count'] = len(tech_context.get('commands_executed', []))

        # Outcomes
        outcomes = metadata.get('outcomes', {})
        session['success'] = outcomes.get('success')
        session['deliverables_count'] = len(outcomes.get('deliverables', []))

        # Format date
        try:
            created = datetime.fromisoformat(session['created_at'])
            session['created_display'] = created.strftime('%Y-%m-%d %H:%M')
            session['created_relative'] = format_relative_time(created)
        except:
            session['created_display'] = session.get('created_at', 'Unknown')
            session['created_relative'] = ''

    return templates.TemplateResponse("build_logs/index.html", {
        "request": request,
        "sessions": sessions,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "has_prev": page > 1,
        "has_next": page < total_pages
    })


@router.get("/{note_id}", response_class=HTMLResponse)
async def view_session(request: Request, note_id: int):
    """
    View detailed build log session.
    """
    service = get_service()
    session = service.get_session_by_id(note_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Process session for display
    metadata = session.get('metadata', {})

    # Format dates
    try:
        created = datetime.fromisoformat(session['created_at'])
        session['created_display'] = created.strftime('%B %d, %Y at %H:%M')
        session['created_relative'] = format_relative_time(created)
    except:
        session['created_display'] = session.get('created_at', 'Unknown')
        session['created_relative'] = ''

    # Extract structured data
    session['session_id'] = metadata.get('session_id', 'N/A')
    session['task'] = metadata.get('task_description', session.get('title', 'Untitled'))
    session['duration'] = metadata.get('duration_minutes')

    # Technical context
    tech_context = metadata.get('technical_context', {})
    session['files_changed'] = tech_context.get('files_changed', [])
    session['commands_executed'] = tech_context.get('commands_executed', [])

    # Outcomes
    outcomes = metadata.get('outcomes', {})
    session['success'] = outcomes.get('success')
    session['deliverables'] = outcomes.get('deliverables', [])
    session['next_steps'] = outcomes.get('next_steps', [])
    session['key_learnings'] = outcomes.get('key_learnings', [])

    # Parse tags
    tags = session.get('tags', '').split(',')
    session['tags_list'] = [t.strip() for t in tags if t.strip()]

    return templates.TemplateResponse("build_logs/detail.html", {
        "request": request,
        "session": session
    })


@router.get("/new", response_class=HTMLResponse)
async def new_session_form(request: Request):
    """
    Form to create a new build log session.
    """
    return templates.TemplateResponse("build_logs/new.html", {
        "request": request
    })


@router.post("/create", response_class=HTMLResponse)
async def create_session_form(
    request: Request,
    task_description: str = Form(...),
    conversation_log: str = Form(...),
    files_changed: str = Form(""),
    commands_executed: str = Form(""),
    duration_minutes: Optional[int] = Form(None),
    success: bool = Form(False),
    deliverables: str = Form(""),
    next_steps: str = Form("")
):
    """
    Create a new build log session from web form.
    """
    service = get_service()

    # Parse multi-line fields
    files_list = [f.strip() for f in files_changed.split('\n') if f.strip()]
    commands_list = [c.strip() for c in commands_executed.split('\n') if c.strip()]
    deliverables_list = [d.strip() for d in deliverables.split('\n') if d.strip()]
    next_steps_list = [n.strip() for n in next_steps.split('\n') if n.strip()]

    # Build outcomes
    outcomes = {
        "success": success,
        "deliverables": deliverables_list,
        "next_steps": next_steps_list
    }

    # Create session
    result = service.create_session(
        task_description=task_description,
        conversation_log=conversation_log,
        files_changed=files_list,
        commands_executed=commands_list,
        duration_minutes=duration_minutes,
        outcomes=outcomes
    )

    # Redirect to view page
    return RedirectResponse(
        url=f"/build-logs/{result['note_id']}",
        status_code=303
    )


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_dashboard(request: Request):
    """
    Analytics dashboard for build logs.
    """
    service = get_service()
    analytics = service.get_analytics()

    return templates.TemplateResponse("build_logs/analytics.html", {
        "request": request,
        "analytics": analytics
    })


@router.get("/search", response_class=HTMLResponse)
async def search_sessions(request: Request, q: str = Query("")):
    """
    Search build log sessions.
    """
    service = get_service()

    sessions = []
    if q:
        sessions = service.search_sessions(q, limit=50)

        # Process for display
        for session in sessions:
            metadata = session.get('metadata', {})
            session['session_id'] = metadata.get('session_id', 'N/A')
            session['task'] = metadata.get('task_description', session.get('title', 'Untitled'))

            try:
                created = datetime.fromisoformat(session['created_at'])
                session['created_display'] = created.strftime('%Y-%m-%d %H:%M')
            except:
                session['created_display'] = session.get('created_at', 'Unknown')

    return templates.TemplateResponse("build_logs/search.html", {
        "request": request,
        "query": q,
        "sessions": sessions,
        "count": len(sessions)
    })


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/api/sessions", response_class=JSONResponse)
async def create_session_api(req: CreateSessionRequest):
    """
    API endpoint to create a new build log session.
    """
    service = get_service()

    result = service.create_session(
        task_description=req.task_description,
        conversation_log=req.conversation_log,
        files_changed=req.files_changed,
        commands_executed=req.commands_executed,
        duration_minutes=req.duration_minutes,
        outcomes=req.outcomes,
        session_id=req.session_id
    )

    return JSONResponse(content=result, status_code=201)


@router.get("/api/sessions", response_class=JSONResponse)
async def list_sessions_api(
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0)
):
    """
    API endpoint to list build log sessions.
    """
    service = get_service()
    sessions = service.list_sessions(limit=limit, offset=offset)
    total = service.count_sessions()

    return JSONResponse(content={
        "sessions": sessions,
        "total": total,
        "limit": limit,
        "offset": offset
    })


@router.get("/api/sessions/{note_id}", response_class=JSONResponse)
async def get_session_api(note_id: int):
    """
    API endpoint to get a specific build log session.
    """
    service = get_service()
    session = service.get_session_by_id(note_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return JSONResponse(content=session)


@router.put("/api/sessions/{note_id}", response_class=JSONResponse)
async def update_session_api(note_id: int, req: UpdateSessionRequest):
    """
    API endpoint to update a build log session.
    """
    service = get_service()

    success = service.update_session(
        note_id=note_id,
        title=req.title,
        body=req.body,
        metadata=req.metadata
    )

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return JSONResponse(content={"success": True})


@router.delete("/api/sessions/{note_id}", response_class=JSONResponse)
async def delete_session_api(note_id: int):
    """
    API endpoint to delete a build log session.
    """
    service = get_service()

    success = service.delete_session(note_id)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return JSONResponse(content={"success": True})


@router.get("/api/analytics", response_class=JSONResponse)
async def analytics_api():
    """
    API endpoint to get build log analytics.
    """
    service = get_service()
    analytics = service.get_analytics()

    return JSONResponse(content=analytics)


@router.get("/api/search", response_class=JSONResponse)
async def search_api(q: str = Query(...)):
    """
    API endpoint to search build log sessions.
    """
    service = get_service()
    sessions = service.search_sessions(q, limit=50)

    return JSONResponse(content={
        "query": q,
        "sessions": sessions,
        "count": len(sessions)
    })


# ============================================================================
# Helper Functions
# ============================================================================

def format_relative_time(dt: datetime) -> str:
    """Format datetime as relative time (e.g., '2 hours ago')"""
    now = datetime.now()
    diff = now - dt

    seconds = diff.total_seconds()

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"
    elif seconds < 2592000:
        weeks = int(seconds / 604800)
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    elif seconds < 31536000:
        months = int(seconds / 2592000)
        return f"{months} month{'s' if months != 1 else ''} ago"
    else:
        years = int(seconds / 31536000)
        return f"{years} year{'s' if years != 1 else ''} ago"
