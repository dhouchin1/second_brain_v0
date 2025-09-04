"""
Bulk Operations FastAPI Router

Provides REST API endpoints for bulk note management operations including:
- Bulk delete, update, tag, move operations
- Import/export functionality
- Bulk statistics and management
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from services.bulk_operations_service import BulkOperationsService, BulkOperationResult
from services.auth_service import User

# Global service instances and functions (initialized by app.py)
bulk_operations_service: Optional[BulkOperationsService] = None
get_conn = None
get_current_user = None

# FastAPI router
router = APIRouter(prefix="/api/bulk", tags=["bulk-operations"])

def init_bulk_operations_router(get_conn_func, get_current_user_func):
    """Initialize Bulk Operations router with dependencies"""
    global bulk_operations_service, get_conn, get_current_user
    get_conn = get_conn_func
    get_current_user = get_current_user_func
    bulk_operations_service = BulkOperationsService(get_conn_func)

# ─── Pydantic Models ───

class BulkDeleteRequest(BaseModel):
    """Request model for bulk delete operations"""
    note_ids: Optional[List[int]] = None
    filter: Optional[Dict[str, Any]] = None

class BulkUpdateRequest(BaseModel):
    """Request model for bulk update operations"""
    note_ids: List[int]
    updates: Dict[str, Any]

class BulkTagRequest(BaseModel):
    """Request model for bulk tag operations"""
    note_ids: List[int]
    tags: str
    tag_operation: str = "add"  # add, remove, replace

class BulkMoveRequest(BaseModel):
    """Request model for bulk move operations"""
    note_ids: List[int]
    target_status: str = "active"

class BulkExportRequest(BaseModel):
    """Request model for bulk export operations"""
    note_ids: List[int]
    format: str = "json"  # json, csv, markdown, zip

class BulkDuplicateRequest(BaseModel):
    """Request model for bulk duplicate operations"""
    note_ids: List[int]
    suffix: str = " (Copy)"

class BulkOperationsRequest(BaseModel):
    """Request model for multiple bulk operations"""
    operations: List[Dict[str, Any]]

# ─── Core Bulk Operations Endpoints ───

@router.post("/operations")
async def execute_bulk_operations(
    request_data: BulkOperationsRequest,
    current_user: User = Depends(get_current_user)
):
    """Execute multiple bulk operations in sequence"""
    if not bulk_operations_service:
        raise HTTPException(status_code=500, detail="Bulk operations service not initialized")
    
    try:
        results = bulk_operations_service.execute_bulk_operations(
            current_user.id, request_data.operations
        )
        
        # Convert results to serializable format
        serialized_results = []
        for result in results:
            serialized_results.append({
                "operation": result.operation,
                "note_id": result.note_id,
                "status": result.status,
                "message": result.message,
                "error": result.error
            })
        
        success_count = sum(1 for r in results if r.status == "success")
        error_count = sum(1 for r in results if r.status == "error")
        
        return JSONResponse(content={
            "success": True,
            "total_operations": len(results),
            "successful": success_count,
            "failed": error_count,
            "results": serialized_results,
            "user_id": current_user.id
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute bulk operations: {str(e)}")

@router.delete("/notes")
async def bulk_delete_notes(
    request_data: BulkDeleteRequest,
    current_user: User = Depends(get_current_user)
):
    """Delete multiple notes at once"""
    if not bulk_operations_service:
        raise HTTPException(status_code=500, detail="Bulk operations service not initialized")
    
    try:
        operation = {"action": "delete"}
        if request_data.note_ids:
            operation["note_ids"] = request_data.note_ids
        if request_data.filter:
            operation["filter"] = request_data.filter
        
        results = bulk_operations_service.execute_bulk_operations(current_user.id, [operation])
        
        success_count = sum(1 for r in results if r.status == "success")
        
        return JSONResponse(content={
            "success": True,
            "deleted_count": success_count,
            "results": [
                {
                    "note_id": r.note_id,
                    "status": r.status,
                    "message": r.message,
                    "error": r.error
                }
                for r in results
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete notes: {str(e)}")

@router.put("/notes")
async def bulk_update_notes(
    request_data: BulkUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """Update multiple notes at once"""
    if not bulk_operations_service:
        raise HTTPException(status_code=500, detail="Bulk operations service not initialized")
    
    try:
        operation = {
            "action": "update",
            "note_ids": request_data.note_ids,
            "updates": request_data.updates
        }
        
        results = bulk_operations_service.execute_bulk_operations(current_user.id, [operation])
        
        success_count = sum(1 for r in results if r.status == "success")
        
        return JSONResponse(content={
            "success": True,
            "updated_count": success_count,
            "results": [
                {
                    "note_id": r.note_id,
                    "status": r.status,
                    "message": r.message,
                    "error": r.error
                }
                for r in results
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update notes: {str(e)}")

@router.post("/notes/tags")
async def bulk_tag_notes(
    request_data: BulkTagRequest,
    current_user: User = Depends(get_current_user)
):
    """Add, remove, or replace tags on multiple notes"""
    if not bulk_operations_service:
        raise HTTPException(status_code=500, detail="Bulk operations service not initialized")
    
    try:
        operation = {
            "action": "tag",
            "note_ids": request_data.note_ids,
            "tags": request_data.tags,
            "tag_operation": request_data.tag_operation
        }
        
        results = bulk_operations_service.execute_bulk_operations(current_user.id, [operation])
        
        success_count = sum(1 for r in results if r.status == "success")
        
        return JSONResponse(content={
            "success": True,
            "tagged_count": success_count,
            "operation": request_data.tag_operation,
            "tags": request_data.tags,
            "results": [
                {
                    "note_id": r.note_id,
                    "status": r.status,
                    "message": r.message,
                    "error": r.error
                }
                for r in results
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to tag notes: {str(e)}")

@router.post("/notes/move")
async def bulk_move_notes(
    request_data: BulkMoveRequest,
    current_user: User = Depends(get_current_user)
):
    """Move multiple notes to a different status"""
    if not bulk_operations_service:
        raise HTTPException(status_code=500, detail="Bulk operations service not initialized")
    
    try:
        operation = {
            "action": "move",
            "note_ids": request_data.note_ids,
            "target_status": request_data.target_status
        }
        
        results = bulk_operations_service.execute_bulk_operations(current_user.id, [operation])
        
        success_count = sum(1 for r in results if r.status == "success")
        
        return JSONResponse(content={
            "success": True,
            "moved_count": success_count,
            "target_status": request_data.target_status,
            "results": [
                {
                    "note_id": r.note_id,
                    "status": r.status,
                    "message": r.message,
                    "error": r.error
                }
                for r in results
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to move notes: {str(e)}")

@router.post("/notes/duplicate")
async def bulk_duplicate_notes(
    request_data: BulkDuplicateRequest,
    current_user: User = Depends(get_current_user)
):
    """Duplicate multiple notes"""
    if not bulk_operations_service:
        raise HTTPException(status_code=500, detail="Bulk operations service not initialized")
    
    try:
        operation = {
            "action": "duplicate",
            "note_ids": request_data.note_ids,
            "suffix": request_data.suffix
        }
        
        results = bulk_operations_service.execute_bulk_operations(current_user.id, [operation])
        
        success_count = sum(1 for r in results if r.status == "success")
        
        return JSONResponse(content={
            "success": True,
            "duplicated_count": success_count,
            "suffix": request_data.suffix,
            "results": [
                {
                    "original_note_id": r.note_id,
                    "status": r.status,
                    "message": r.message,
                    "error": r.error
                }
                for r in results
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to duplicate notes: {str(e)}")

# ─── Export/Import Endpoints ───

@router.post("/export")
async def bulk_export_notes(
    request_data: BulkExportRequest,
    current_user: User = Depends(get_current_user)
):
    """Export multiple notes to various formats"""
    if not bulk_operations_service:
        raise HTTPException(status_code=500, detail="Bulk operations service not initialized")
    
    try:
        operation = {
            "action": "export",
            "note_ids": request_data.note_ids,
            "format": request_data.format
        }
        
        results = bulk_operations_service.execute_bulk_operations(current_user.id, [operation])
        
        if results and results[0].status == "success":
            # Extract file path from message
            message = results[0].message
            if "to " in message:
                file_path = message.split("to ")[1]
                
                # Return file path for download
                return JSONResponse(content={
                    "success": True,
                    "export_format": request_data.format,
                    "exported_count": len(request_data.note_ids),
                    "file_path": file_path,
                    "message": message
                })
        
        # If export failed
        return JSONResponse(content={
            "success": False,
            "error": results[0].error if results else "Export failed",
            "export_format": request_data.format
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export notes: {str(e)}")

@router.post("/import")
async def bulk_import_notes(
    file: UploadFile = File(...),
    format: str = "json",
    current_user: User = Depends(get_current_user)
):
    """Import notes from uploaded file"""
    if not bulk_operations_service:
        raise HTTPException(status_code=500, detail="Bulk operations service not initialized")
    
    try:
        # Read file content
        file_content = await file.read()
        
        # Import notes
        results = bulk_operations_service.import_notes(current_user.id, file_content, format)
        
        success_count = sum(1 for r in results if r.status == "success")
        error_count = sum(1 for r in results if r.status == "error")
        
        return JSONResponse(content={
            "success": True,
            "import_format": format,
            "imported_count": success_count,
            "failed_count": error_count,
            "total_processed": len(results),
            "results": [
                {
                    "note_id": r.note_id,
                    "status": r.status,
                    "message": r.message,
                    "error": r.error
                }
                for r in results[:50]  # Limit results for large imports
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import notes: {str(e)}")

# ─── Statistics and Management Endpoints ───

@router.get("/stats")
async def get_bulk_operations_stats(
    current_user: User = Depends(get_current_user)
):
    """Get statistics for bulk operations"""
    if not bulk_operations_service:
        raise HTTPException(status_code=500, detail="Bulk operations service not initialized")
    
    try:
        stats = bulk_operations_service.get_bulk_operation_stats(current_user.id)
        
        return JSONResponse(content={
            "success": True,
            "user_id": current_user.id,
            **stats
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

@router.get("/health")
async def bulk_operations_health():
    """Health check for bulk operations service"""
    return JSONResponse(content={
        "status": "healthy" if bulk_operations_service else "unavailable",
        "service": "Bulk Operations",
        "operations_available": [
            "delete", "update", "tag", "move", "export", "duplicate", "import"
        ],
        "features": {
            "bulk_delete": True,
            "bulk_update": True,
            "bulk_tagging": True,
            "bulk_move": True,
            "export_formats": ["json", "csv", "markdown", "zip"],
            "import_formats": ["json", "csv"],
            "filter_operations": True,
            "batch_processing": True
        },
        "version": "1.0.0"
    })

# ─── Utility Endpoints ───

@router.get("/operations/help")
async def get_operations_help():
    """Get help information about available bulk operations"""
    return JSONResponse(content={
        "operations": {
            "delete": {
                "description": "Delete multiple notes by IDs or filter criteria",
                "parameters": ["note_ids", "filter"],
                "example": {
                    "action": "delete",
                    "note_ids": [1, 2, 3]
                }
            },
            "update": {
                "description": "Update fields on multiple notes",
                "parameters": ["note_ids", "updates"],
                "example": {
                    "action": "update",
                    "note_ids": [1, 2, 3],
                    "updates": {"status": "archived", "tags": "bulk-updated"}
                }
            },
            "tag": {
                "description": "Add, remove, or replace tags on multiple notes",
                "parameters": ["note_ids", "tags", "tag_operation"],
                "example": {
                    "action": "tag",
                    "note_ids": [1, 2, 3],
                    "tags": "important,urgent",
                    "tag_operation": "add"
                }
            },
            "move": {
                "description": "Move multiple notes to a different status",
                "parameters": ["note_ids", "target_status"],
                "example": {
                    "action": "move",
                    "note_ids": [1, 2, 3],
                    "target_status": "archived"
                }
            },
            "export": {
                "description": "Export multiple notes to file",
                "parameters": ["note_ids", "format"],
                "example": {
                    "action": "export",
                    "note_ids": [1, 2, 3],
                    "format": "json"
                }
            },
            "duplicate": {
                "description": "Create copies of multiple notes",
                "parameters": ["note_ids", "suffix"],
                "example": {
                    "action": "duplicate",
                    "note_ids": [1, 2, 3],
                    "suffix": " (Copy)"
                }
            }
        },
        "filters": {
            "tags": "Filter by tags containing text",
            "date_range": {
                "start": "Start date (YYYY-MM-DD)",
                "end": "End date (YYYY-MM-DD)"
            },
            "status": "Filter by note status",
            "file_type": "Filter by file type"
        },
        "formats": {
            "export": ["json", "csv", "markdown", "zip"],
            "import": ["json", "csv"]
        }
    })

print("[Bulk Operations Router] Loaded successfully")