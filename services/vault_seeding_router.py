"""
Vault Seeding Router for Second Brain

Provides HTTP endpoints for vault seeding functionality including:
- Seeding vault with starter content
- Checking seeding status
- Managing seed content
- Testing dependencies
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from services.vault_seeding_service import (
    VaultSeedingService, SeedingOptions, SeedingResult, get_seeding_service
)
from services.auth_service import User

log = logging.getLogger(__name__)

# Global variables (initialized by parent app)
get_conn = None
get_current_user = None

# Request/Response models
class SeedVaultRequest(BaseModel):
    """Request model for vault seeding."""
    namespace: str = ".seed_samples"
    force_overwrite: bool = False
    include_embeddings: bool = True
    embed_model: str = "nomic-embed-text"
    ollama_url: str = "http://localhost:11434"

class SeedingStatusResponse(BaseModel):
    """Response model for seeding status."""
    is_seeded: bool
    seed_notes_count: int
    seed_files_exist: bool
    vault_path: str
    seed_namespace: Optional[str] = None
    error: Optional[str] = None

class SeedingResultResponse(BaseModel):
    """Response model for seeding operations."""
    success: bool
    message: str
    notes_created: int = 0
    embeddings_created: int = 0
    files_written: int = 0
    error: Optional[str] = None

class ClearSeedContentRequest(BaseModel):
    """Request model for clearing seed content."""
    namespace: str = ".seed_samples"

# Router setup
router = APIRouter(prefix="/api/vault/seeding", tags=["vault-seeding"])

def init_vault_seeding_router(get_conn_func, get_current_user_func):
    """Initialize vault seeding router with functions from app.py"""
    global get_conn, get_current_user
    get_conn = get_conn_func
    get_current_user = get_current_user_func

@router.get("/status")
async def get_seeding_status(current_user: User = Depends(get_current_user)):
    """Get current seeding status for the user's vault."""
    try:
        service = get_seeding_service(get_conn)
        status = service.get_seeding_status(current_user.id)
        
        return {
            "success": True,
            "data": status
        }
        
    except Exception as e:
        log.error("Error getting seeding status: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get seeding status: {str(e)}")

@router.get("/available-content")
async def get_available_seed_content(current_user: User = Depends(get_current_user)):
    """Get information about available seed content."""
    try:
        service = get_seeding_service(get_conn)
        content = service.get_available_seed_content()
        
        return {
            "success": True,
            "data": content
        }
        
    except Exception as e:
        log.error("Error getting available content: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get available content: {str(e)}")

@router.get("/preview")
async def preview_seeding_impact(current_user: User = Depends(get_current_user)):
    """Preview the impact of seeding the vault."""
    try:
        service = get_seeding_service(get_conn)
        preview = service.preview_seeding_impact(current_user.id)
        
        return {
            "success": True,
            "data": preview
        }
        
    except Exception as e:
        log.error("Error previewing seeding impact: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to preview seeding: {str(e)}")

@router.post("/seed")
async def seed_vault(
    request: SeedVaultRequest,
    current_user: User = Depends(get_current_user)
):
    """Seed the vault with starter content."""
    try:
        service = get_seeding_service(get_conn)
        
        # Convert request to options
        options = SeedingOptions(
            namespace=request.namespace,
            force_overwrite=request.force_overwrite,
            include_embeddings=request.include_embeddings,
            embed_model=request.embed_model,
            ollama_url=request.ollama_url
        )
        
        # Perform seeding
        result = service.seed_vault(current_user.id, options)
        
        if result.success:
            return {
                "success": True,
                "message": result.message,
                "data": {
                    "notes_created": result.notes_created,
                    "embeddings_created": result.embeddings_created,
                    "files_written": result.files_written
                }
            }
        else:
            return {
                "success": False,
                "message": result.message,
                "error": result.error
            }
            
    except Exception as e:
        log.error("Error seeding vault: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to seed vault: {str(e)}")

@router.post("/clear")
async def clear_seed_content(
    request: ClearSeedContentRequest,
    current_user: User = Depends(get_current_user)
):
    """Clear seed content from vault and database."""
    try:
        service = get_seeding_service(get_conn)
        result = service.clear_seed_content(current_user.id, request.namespace)
        
        if result.success:
            return {
                "success": True,
                "message": result.message,
                "data": {
                    "notes_removed": abs(result.notes_created),  # Convert negative back to positive
                    "files_removed": abs(result.files_written)
                }
            }
        else:
            return {
                "success": False,
                "message": result.message,
                "error": result.error
            }
            
    except Exception as e:
        log.error("Error clearing seed content: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to clear seed content: {str(e)}")

@router.get("/test-dependencies")
async def test_seeding_dependencies(current_user: User = Depends(get_current_user)):
    """Test that all seeding dependencies are available."""
    try:
        service = get_seeding_service(get_conn)
        
        # Test Ollama connection
        ollama_status = service.test_ollama_connection()
        
        # Check vault path
        from config import settings
        from pathlib import Path
        
        vault_path = Path(settings.vault_path)
        vault_exists = vault_path.exists()
        vault_writable = vault_path.is_dir() and vault_path.stat().st_mode & 0o200
        
        return {
            "success": True,
            "data": {
                "ollama": ollama_status,
                "vault": {
                    "path": str(vault_path),
                    "exists": vault_exists,
                    "writable": vault_writable
                },
                "overall_ready": ollama_status["available"] and vault_exists and vault_writable
            }
        }
        
    except Exception as e:
        log.error("Error testing dependencies: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to test dependencies: {str(e)}")

# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check endpoint for vault seeding service."""
    return {
        "service": "vault-seeding",
        "status": "healthy",
        "features": [
            "seed_vault",
            "clear_content", 
            "status_check",
            "dependency_test"
        ]
    }

print("[Vault Seeding Router] Loaded successfully")