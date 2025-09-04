"""
Smart Automation Router

FastAPI router for Smart Automation services including workflow automation
and intelligent routing capabilities. Provides REST API endpoints for
managing and executing automated workflows.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import sqlite3

from services.workflow_engine import (
    WorkflowEngine, WorkflowRule, WorkflowRuleCreate, WorkflowRuleResponse,
    WorkflowStatsResponse, ContentClassificationResponse, TriggerType, ActionType
)
from services.intelligent_router import (
    IntelligentRouter, RoutingRule, RoutingRuleCreate, RoutingRuleResponse,
    RoutingDecisionResponse, RoutingStatsResponse, ContentAnalysisResponse,
    RoutingPriority, ProcessingMode
)
from services.auth_service import User


# Global service instances (will be initialized by app.py)
workflow_engine: Optional[WorkflowEngine] = None
intelligent_router: Optional[IntelligentRouter] = None

# FastAPI router
router = APIRouter(prefix="/api/automation", tags=["smart-automation"])


def init_smart_automation_router(get_conn_func):
    """Initialize Smart Automation services with database connection"""
    global workflow_engine, intelligent_router
    workflow_engine = WorkflowEngine(get_conn_func)
    intelligent_router = IntelligentRouter(get_conn_func)


# ─── Request/Response Models ───

class ContentProcessingRequest(BaseModel):
    """Request model for content processing"""
    content_id: Optional[str] = None
    title: str
    content: str
    tags: Optional[str] = ""
    type: Optional[str] = "text"
    metadata: Optional[Dict[str, Any]] = {}


class ContentProcessingResponse(BaseModel):
    """Response model for content processing"""
    content_id: str
    workflows_triggered: List[str]
    routing_decision: Dict[str, Any]
    processing_results: Dict[str, Any]
    execution_time: str


class WorkflowTriggerRequest(BaseModel):
    """Request model for manual workflow triggering"""
    trigger_type: TriggerType
    trigger_data: Dict[str, Any]


class WorkflowTriggerResponse(BaseModel):
    """Response model for workflow triggering"""
    triggered_workflows: List[str]
    execution_ids: List[str]
    message: str


# ─── Workflow Management Endpoints ───

@router.get("/workflows", response_model=List[WorkflowRuleResponse])
async def list_workflows():
    """List all workflow rules"""
    if not workflow_engine:
        raise HTTPException(status_code=500, detail="Workflow engine not initialized")
    
    workflows = workflow_engine.list_workflows()
    return [
        WorkflowRuleResponse(
            id=w.id,
            name=w.name,
            description=w.description,
            trigger_type=w.trigger_type,
            trigger_conditions=w.trigger_conditions,
            actions=w.actions,
            status=w.status,
            created_at=w.created_at.isoformat() if w.created_at else None,
            last_run=w.last_run.isoformat() if w.last_run else None,
            run_count=w.run_count,
            priority=w.priority
        )
        for w in workflows
    ]


@router.get("/workflows/{workflow_id}", response_model=WorkflowRuleResponse)
async def get_workflow(workflow_id: str):
    """Get a specific workflow rule"""
    if not workflow_engine:
        raise HTTPException(status_code=500, detail="Workflow engine not initialized")
    
    workflow = workflow_engine.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return WorkflowRuleResponse(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        trigger_type=workflow.trigger_type,
        trigger_conditions=workflow.trigger_conditions,
        actions=workflow.actions,
        status=workflow.status,
        created_at=workflow.created_at.isoformat() if workflow.created_at else None,
        last_run=workflow.last_run.isoformat() if workflow.last_run else None,
        run_count=workflow.run_count,
        priority=workflow.priority
    )


@router.post("/workflows", response_model=WorkflowRuleResponse)
async def create_workflow(workflow_data: WorkflowRuleCreate, current_user: User = Depends()):
    """Create a new workflow rule"""
    if not workflow_engine:
        raise HTTPException(status_code=500, detail="Workflow engine not initialized")
    
    # Generate unique workflow ID
    workflow_id = f"custom_{current_user.id}_{datetime.now().timestamp()}"
    
    workflow_rule = WorkflowRule(
        id=workflow_id,
        name=workflow_data.name,
        description=workflow_data.description,
        trigger_type=workflow_data.trigger_type,
        trigger_conditions=workflow_data.trigger_conditions,
        actions=workflow_data.actions,
        user_id=current_user.id,
        created_at=datetime.now(),
        priority=workflow_data.priority
    )
    
    workflow_engine.add_workflow(workflow_rule)
    
    return WorkflowRuleResponse(
        id=workflow_rule.id,
        name=workflow_rule.name,
        description=workflow_rule.description,
        trigger_type=workflow_rule.trigger_type,
        trigger_conditions=workflow_rule.trigger_conditions,
        actions=workflow_rule.actions,
        status=workflow_rule.status,
        created_at=workflow_rule.created_at.isoformat(),
        last_run=None,
        run_count=0,
        priority=workflow_rule.priority
    )


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str, current_user: User = Depends()):
    """Delete a workflow rule"""
    if not workflow_engine:
        raise HTTPException(status_code=500, detail="Workflow engine not initialized")
    
    workflow = workflow_engine.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Check ownership for custom workflows
    if workflow.user_id and workflow.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this workflow")
    
    success = workflow_engine.remove_workflow(workflow_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return {"message": "Workflow deleted successfully"}


@router.get("/workflows/stats", response_model=WorkflowStatsResponse)
async def get_workflow_stats():
    """Get workflow execution statistics"""
    if not workflow_engine:
        raise HTTPException(status_code=500, detail="Workflow engine not initialized")
    
    stats = workflow_engine.get_workflow_stats()
    return WorkflowStatsResponse(**stats)


@router.post("/workflows/trigger", response_model=WorkflowTriggerResponse)
async def trigger_workflows(request: WorkflowTriggerRequest, current_user: User = Depends()):
    """Manually trigger workflows based on trigger type and data"""
    if not workflow_engine:
        raise HTTPException(status_code=500, detail="Workflow engine not initialized")
    
    try:
        execution_ids = await workflow_engine.trigger_workflow(
            request.trigger_type,
            request.trigger_data
        )
        
        return WorkflowTriggerResponse(
            triggered_workflows=[],  # Would need to track which workflows matched
            execution_ids=execution_ids,
            message=f"Triggered {len(execution_ids)} workflow executions"
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger workflows: {str(e)}")


# ─── Intelligent Routing Endpoints ───

@router.get("/routing/rules", response_model=List[RoutingRuleResponse])
async def list_routing_rules():
    """List all routing rules"""
    if not intelligent_router:
        raise HTTPException(status_code=500, detail="Intelligent router not initialized")
    
    rules = intelligent_router.list_routing_rules()
    return [
        RoutingRuleResponse(
            id=r.id,
            name=r.name,
            description=r.description,
            conditions=r.conditions,
            routing_targets=r.routing_targets,
            priority=r.priority,
            processing_mode=r.processing_mode,
            enabled=r.enabled,
            match_count=r.match_count
        )
        for r in rules
    ]


@router.post("/routing/rules", response_model=RoutingRuleResponse)
async def create_routing_rule(rule_data: RoutingRuleCreate, current_user: User = Depends()):
    """Create a new routing rule"""
    if not intelligent_router:
        raise HTTPException(status_code=500, detail="Intelligent router not initialized")
    
    # Generate unique rule ID
    rule_id = f"custom_routing_{current_user.id}_{datetime.now().timestamp()}"
    
    routing_rule = RoutingRule(
        id=rule_id,
        name=rule_data.name,
        description=rule_data.description,
        conditions=rule_data.conditions,
        routing_targets=rule_data.routing_targets,
        priority=rule_data.priority,
        processing_mode=rule_data.processing_mode,
        created_at=datetime.now()
    )
    
    intelligent_router.add_routing_rule(routing_rule)
    
    return RoutingRuleResponse(
        id=routing_rule.id,
        name=routing_rule.name,
        description=routing_rule.description,
        conditions=routing_rule.conditions,
        routing_targets=routing_rule.routing_targets,
        priority=routing_rule.priority,
        processing_mode=routing_rule.processing_mode,
        enabled=routing_rule.enabled,
        match_count=0
    )


@router.get("/routing/stats", response_model=RoutingStatsResponse)
async def get_routing_stats():
    """Get routing statistics"""
    if not intelligent_router:
        raise HTTPException(status_code=500, detail="Intelligent router not initialized")
    
    stats = intelligent_router.get_routing_stats()
    return RoutingStatsResponse(**stats)


@router.post("/routing/analyze", response_model=ContentAnalysisResponse)
async def analyze_content(request: ContentProcessingRequest):
    """Analyze content for routing decisions"""
    if not intelligent_router:
        raise HTTPException(status_code=500, detail="Intelligent router not initialized")
    
    analysis = intelligent_router.analyzer.analyze_content(
        request.title,
        request.content,
        request.metadata
    )
    
    return ContentAnalysisResponse(**analysis)


@router.post("/routing/decide", response_model=RoutingDecisionResponse)
async def make_routing_decision(request: ContentProcessingRequest):
    """Make routing decision for content"""
    if not intelligent_router:
        raise HTTPException(status_code=500, detail="Intelligent router not initialized")
    
    content_data = {
        "id": request.content_id or f"temp_{datetime.now().timestamp()}",
        "title": request.title,
        "content": request.content,
        "tags": request.tags,
        "type": request.type,
        "metadata": request.metadata
    }
    
    decision = await intelligent_router.route_content(content_data)
    
    return RoutingDecisionResponse(
        content_id=decision.content_id,
        matched_rules=decision.matched_rules,
        routing_targets=decision.routing_targets,
        priority=decision.priority,
        processing_mode=decision.processing_mode,
        confidence=decision.confidence,
        reasoning=decision.reasoning,
        metadata=decision.metadata
    )


# ─── Content Processing Endpoints ───

@router.post("/process", response_model=ContentProcessingResponse)
async def process_content(
    request: ContentProcessingRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends()
):
    """Comprehensive content processing with workflows and routing"""
    if not workflow_engine or not intelligent_router:
        raise HTTPException(status_code=500, detail="Automation services not initialized")
    
    start_time = datetime.now()
    content_id = request.content_id or f"processed_{current_user.id}_{start_time.timestamp()}"
    
    # Prepare content data
    content_data = {
        "id": content_id,
        "note_id": request.content_id,  # If updating existing note
        "title": request.title,
        "content": request.content,
        "tags": request.tags,
        "type": request.type,
        "metadata": request.metadata,
        "user_id": current_user.id
    }
    
    # Make routing decision
    routing_decision = await intelligent_router.route_content(content_data)
    
    # Trigger workflows based on content
    workflow_executions = await workflow_engine.trigger_workflow(
        TriggerType.CONTENT_CREATED,
        content_data
    )
    
    # Execute routing decision in background
    routing_results = {}
    try:
        routing_results = await intelligent_router.execute_routing_decision(
            routing_decision,
            content_data
        )
    except Exception as e:
        # Log error but don't fail the entire request
        routing_results = {"error": str(e)}
    
    processing_results = {
        "routing_decision": {
            "matched_rules": routing_decision.matched_rules,
            "priority": routing_decision.priority.value,
            "processing_mode": routing_decision.processing_mode.value,
            "confidence": routing_decision.confidence,
            "reasoning": routing_decision.reasoning
        },
        "routing_execution": routing_results,
        "workflow_executions": workflow_executions
    }
    
    return ContentProcessingResponse(
        content_id=content_id,
        workflows_triggered=workflow_executions,
        routing_decision=routing_decision.__dict__,
        processing_results=processing_results,
        execution_time=datetime.now().isoformat()
    )


# ─── Content Classification Endpoints ───

@router.post("/classify", response_model=ContentClassificationResponse)
async def classify_content(request: ContentProcessingRequest):
    """Classify content using AI-powered analysis"""
    if not workflow_engine:
        raise HTTPException(status_code=500, detail="Workflow engine not initialized")
    
    existing_tags = request.tags.split(",") if request.tags else []
    classification = workflow_engine.classifier.classify_content(
        request.title,
        request.content,
        existing_tags
    )
    
    return ContentClassificationResponse(**classification)


# ─── System Management Endpoints ───

@router.get("/status")
async def get_automation_status():
    """Get overall automation system status"""
    return {
        "workflow_engine": {
            "initialized": workflow_engine is not None,
            "active_workflows": len(workflow_engine.active_workflows) if workflow_engine else 0
        },
        "intelligent_router": {
            "initialized": intelligent_router is not None,
            "routing_rules": len(intelligent_router.routing_rules) if intelligent_router else 0
        },
        "system_time": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@router.post("/test")
async def test_automation_system():
    """Test the automation system with sample content"""
    if not workflow_engine or not intelligent_router:
        raise HTTPException(status_code=500, detail="Automation services not initialized")
    
    test_content = {
        "id": f"test_{datetime.now().timestamp()}",
        "title": "Test Meeting Notes",
        "content": "Meeting with the team about the urgent project deadline. Action items: complete the API, test the integration, and deploy to production by tomorrow.",
        "tags": "meeting,urgent",
        "type": "text",
        "metadata": {"source": "test"}
    }
    
    # Test routing
    routing_decision = await intelligent_router.route_content(test_content)
    
    # Test workflow triggering
    workflow_executions = await workflow_engine.trigger_workflow(
        TriggerType.CONTENT_CREATED,
        test_content
    )
    
    return {
        "test_content": test_content,
        "routing_decision": {
            "matched_rules": routing_decision.matched_rules,
            "priority": routing_decision.priority.value,
            "confidence": routing_decision.confidence,
            "reasoning": routing_decision.reasoning
        },
        "workflow_executions": workflow_executions,
        "status": "success",
        "timestamp": datetime.now().isoformat()
    }


# ─── Health Check ───

@router.get("/health")
async def health_check():
    """Health check for Smart Automation services"""
    return {
        "status": "healthy",
        "services": {
            "workflow_engine": workflow_engine is not None,
            "intelligent_router": intelligent_router is not None
        },
        "timestamp": datetime.now().isoformat()
    }