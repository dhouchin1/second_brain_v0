"""
Interactive Seeding Router

FastAPI router for interactive seeding endpoints, providing user-guided
content collection and progress tracking.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from services.interactive_seeding_service import InteractiveSeedingService, SeedingPrompt

# Global service instances (initialized by app.py)
seeding_service: Optional[InteractiveSeedingService] = None
get_conn = None

# Request/Response Models
class ProgressResponse(BaseModel):
    """Response model for user progress"""
    user_id: int
    level: int
    total_points: int
    completed_prompts: List[str]
    achievements: List[str]
    next_level_points: int
    progress_percentage: float

class PromptCompletionRequest(BaseModel):
    """Request model for completing a text prompt"""
    prompt_id: str
    response_text: str
    user_id: int = Field(default=1)

class LeaderboardResponse(BaseModel):
    """Response model for leaderboard"""
    user_id: int
    username: str
    level: int
    total_points: int
    rank: int

def init_interactive_seeding_router(get_conn_func):
    """Initialize Interactive Seeding router with dependencies"""
    global seeding_service, get_conn
    get_conn = get_conn_func
    seeding_service = InteractiveSeedingService(get_conn_func)

# Create router
router = APIRouter(prefix="/api/interactive-seeding", tags=["Interactive Seeding"])

@router.get("/prompts")
async def get_seeding_prompts(user_id: int = 1):
    """Get available seeding prompts with completion status"""
    try:
        prompts = seeding_service.get_seeding_prompts()
        progress = seeding_service.get_user_progress(user_id)
        completed_prompts = set(progress.completed_prompts or [])
        
        prompts_with_status = []
        for prompt in prompts:
            prompt_dict = {
                "id": prompt.id,
                "type": prompt.type,
                "title": prompt.title,
                "description": prompt.description,
                "target_count": prompt.target_count,
                "points": prompt.points,
                "required": prompt.required,
                "examples": prompt.examples or [],
                "completed": prompt.id in completed_prompts
            }
            prompts_with_status.append(prompt_dict)
        
        return {"prompts": prompts_with_status}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get prompts: {str(e)}")

@router.get("/progress", response_model=ProgressResponse)
async def get_user_progress(user_id: int = 1):
    """Get user's seeding progress and achievements"""
    try:
        progress = seeding_service.get_user_progress(user_id)
        next_level_points = seeding_service._calculate_next_level_points(progress.level)
        progress_percentage = (progress.total_points / next_level_points) * 100
        
        return ProgressResponse(
            user_id=progress.user_id,
            level=progress.level,
            total_points=progress.total_points,
            completed_prompts=progress.completed_prompts or [],
            achievements=progress.achievements or [],
            next_level_points=next_level_points,
            progress_percentage=min(progress_percentage, 100)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get progress: {str(e)}")

@router.post("/upload-pdf")
async def upload_pdf_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: int = Form(1),
    prompt_id: str = Form("pdf_personal_docs")
):
    """Upload and process a PDF document"""
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="File must be a PDF")
        
        # Save uploaded file temporarily
        temp_path = f"/tmp/{file.filename}"
        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Process in background
        background_tasks.add_task(
            seeding_service.process_pdf_document,
            temp_path,
            file.filename,
            user_id,
            prompt_id
        )
        
        return {
            "status": "uploaded",
            "filename": file.filename,
            "message": "PDF uploaded and processing started"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload PDF: {str(e)}")

@router.post("/upload-audio")
async def upload_audio_recording(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: int = Form(1),
    prompt_id: str = Form("audio_recordings")
):
    """Upload and process an audio recording"""
    try:
        allowed_formats = ['.mp3', '.wav', '.m4a', '.ogg', '.webm']
        file_ext = '.' + file.filename.split('.')[-1].lower()
        
        if file_ext not in allowed_formats:
            raise HTTPException(
                status_code=400, 
                detail=f"Audio format not supported. Use: {', '.join(allowed_formats)}"
            )
        
        # Save uploaded file temporarily
        temp_path = f"/tmp/{file.filename}"
        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Process in background
        background_tasks.add_task(
            seeding_service.process_audio_recording,
            temp_path,
            file.filename,
            user_id,
            prompt_id
        )
        
        return {
            "status": "uploaded",
            "filename": file.filename,
            "message": "Audio uploaded and processing started"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload audio: {str(e)}")

@router.post("/submit-text-response")
async def submit_text_response(request: PromptCompletionRequest):
    """Submit a text response to a prompt"""
    try:
        result = seeding_service.process_text_response(
            request.prompt_id,
            request.response_text,
            request.user_id
        )
        
        return {
            "status": "success",
            "points_earned": result.get("points_earned", 0),
            "message": "Text response saved successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit response: {str(e)}")

@router.post("/add-bookmark")
async def add_web_bookmark(
    url: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    user_id: int = Form(1),
    prompt_id: str = Form("web_bookmarks")
):
    """Add a web bookmark"""
    try:
        result = seeding_service.process_web_bookmark(
            url, title, description, user_id, prompt_id
        )
        
        return {
            "status": "success",
            "points_earned": result.get("points_earned", 0),
            "message": "Bookmark added successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add bookmark: {str(e)}")

@router.get("/achievements")
async def get_user_achievements(user_id: int = 1):
    """Get user's achievements and badges"""
    try:
        achievements = seeding_service.get_user_achievements(user_id)
        return {"achievements": achievements}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get achievements: {str(e)}")

@router.get("/leaderboard", response_model=List[LeaderboardResponse])
async def get_leaderboard(limit: int = 10):
    """Get seeding progress leaderboard"""
    try:
        leaderboard = seeding_service.get_leaderboard(limit)
        
        return [
            LeaderboardResponse(
                user_id=entry["user_id"],
                username=entry.get("username", f"User {entry['user_id']}"),
                level=entry["level"],
                total_points=entry["total_points"],
                rank=entry["rank"]
            )
            for entry in leaderboard
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get leaderboard: {str(e)}")

@router.get("/statistics")
async def get_seeding_statistics():
    """Get overall seeding statistics"""
    try:
        stats = seeding_service.get_seeding_statistics()
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")

# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check for interactive seeding service"""
    return {
        "status": "healthy",
        "service": "interactive_seeding",
        "timestamp": datetime.now().isoformat()
    }

print("[Interactive Seeding Router] Loaded successfully")