"""
Workflow Engine Service

Handles automated workflows, rule-based content processing, and intelligent automation
for Second Brain. Provides the foundation for smart content routing and processing.
"""

from __future__ import annotations
import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

from fastapi import HTTPException
import sqlite3
from pydantic import BaseModel

from config import settings
from llm_utils import ollama_summarize, ollama_generate_title


class TriggerType(str, Enum):
    """Types of workflow triggers"""
    CONTENT_CREATED = "content_created"
    CONTENT_UPDATED = "content_updated"
    TAG_ADDED = "tag_added"
    FILE_UPLOADED = "file_uploaded"
    KEYWORD_MATCHED = "keyword_matched"
    SCHEDULE = "schedule"
    WEBHOOK = "webhook"
    USER_ACTION = "user_action"


class ActionType(str, Enum):
    """Types of workflow actions"""
    AUTO_TAG = "auto_tag"
    AUTO_SUMMARIZE = "auto_summarize"
    SEND_NOTIFICATION = "send_notification"
    ROUTE_TO_SERVICE = "route_to_service"
    CREATE_OBSIDIAN_NOTE = "create_obsidian_note"
    EXTRACT_ACTION_ITEMS = "extract_action_items"
    GENERATE_TITLE = "generate_title"
    CLASSIFY_CONTENT = "classify_content"
    ARCHIVE_CONTENT = "archive_content"
    WEBHOOK_CALL = "webhook_call"
    DETECT_URLS = "detect_urls"
    INGEST_WEB_CONTENT = "ingest_web_content"


class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class WorkflowRule:
    """Defines a workflow automation rule"""
    id: str
    name: str
    description: str
    trigger_type: TriggerType
    trigger_conditions: Dict[str, Any]
    actions: List[Dict[str, Any]]
    status: WorkflowStatus = WorkflowStatus.ACTIVE
    user_id: Optional[int] = None
    tenant_id: Optional[str] = None
    created_at: Optional[datetime] = None
    last_run: Optional[datetime] = None
    run_count: int = 0
    priority: int = 5  # 1=highest, 10=lowest


@dataclass
class WorkflowExecution:
    """Records workflow execution details"""
    id: str
    rule_id: str
    trigger_data: Dict[str, Any]
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    actions_completed: List[str] = None
    result_data: Optional[Dict[str, Any]] = None


class ContentClassifier:
    """AI-powered content classification for intelligent routing"""
    
    CONTENT_CATEGORIES = {
        "meeting": ["meeting", "call", "discussion", "standup", "review"],
        "task": ["todo", "action", "task", "assignment", "deadline"],
        "research": ["research", "study", "analysis", "findings", "paper"],
        "personal": ["personal", "diary", "journal", "reflection", "thought"],
        "technical": ["code", "bug", "feature", "implementation", "api"],
        "business": ["strategy", "plan", "revenue", "market", "customer"],
        "idea": ["idea", "concept", "brainstorm", "innovation", "creative"]
    }
    
    def __init__(self):
        self.keyword_patterns = self._compile_keyword_patterns()
    
    def _compile_keyword_patterns(self) -> Dict[str, re.Pattern]:
        """Compile regex patterns for efficient keyword matching"""
        patterns = {}
        for category, keywords in self.CONTENT_CATEGORIES.items():
            pattern = r'\b(' + '|'.join(re.escape(kw) for kw in keywords) + r')\b'
            patterns[category] = re.compile(pattern, re.IGNORECASE)
        return patterns
    
    def classify_content(self, title: str, content: str, existing_tags: List[str] = None) -> Dict[str, Any]:
        """Classify content and suggest categories and tags"""
        text = f"{title} {content}".lower()
        existing_tags = existing_tags or []
        
        # Keyword-based classification
        category_scores = {}
        matched_keywords = {}
        
        for category, pattern in self.keyword_patterns.items():
            matches = pattern.findall(text)
            if matches:
                category_scores[category] = len(matches)
                matched_keywords[category] = list(set(matches))
        
        # Determine primary category
        primary_category = max(category_scores.keys(), key=category_scores.get) if category_scores else "general"
        
        # Generate suggested tags
        suggested_tags = []
        if primary_category != "general":
            suggested_tags.append(primary_category)
        
        # Add specific keywords as tags
        for category, keywords in matched_keywords.items():
            suggested_tags.extend(keywords[:2])  # Limit to 2 keywords per category
        
        # Remove duplicates and existing tags
        suggested_tags = [tag for tag in set(suggested_tags) if tag not in existing_tags]
        
        return {
            "primary_category": primary_category,
            "category_scores": category_scores,
            "suggested_tags": suggested_tags[:5],  # Limit to 5 suggestions
            "matched_keywords": matched_keywords,
            "confidence": max(category_scores.values()) / len(text.split()) if category_scores else 0.0
        }


class WorkflowEngine:
    """Core workflow automation engine"""
    
    def __init__(self, get_conn_func: Callable[[], sqlite3.Connection]):
        self.get_conn = get_conn_func
        self.classifier = ContentClassifier()
        self.active_workflows: Dict[str, WorkflowRule] = {}
        self.execution_queue: asyncio.Queue = asyncio.Queue()
        self._initialize_default_workflows()
    
    def _initialize_default_workflows(self):
        """Set up default automation workflows"""
        default_workflows = [
            WorkflowRule(
                id="auto_tag_content",
                name="Auto-Tag Content",
                description="Automatically tag new content based on AI analysis",
                trigger_type=TriggerType.CONTENT_CREATED,
                trigger_conditions={"min_content_length": 50},
                actions=[
                    {"type": ActionType.AUTO_TAG, "params": {"max_tags": 3}},
                    {"type": ActionType.CLASSIFY_CONTENT, "params": {}}
                ]
            ),
            WorkflowRule(
                id="summarize_long_content",
                name="Auto-Summarize Long Content",
                description="Automatically summarize content longer than 1000 characters",
                trigger_type=TriggerType.CONTENT_CREATED,
                trigger_conditions={"min_content_length": 1000},
                actions=[
                    {"type": ActionType.AUTO_SUMMARIZE, "params": {"max_length": 200}}
                ]
            ),
            WorkflowRule(
                id="meeting_note_processing",
                name="Meeting Note Processing",
                description="Special processing for meeting notes with action item extraction",
                trigger_type=TriggerType.TAG_ADDED,
                trigger_conditions={"tags": ["meeting", "call"]},
                actions=[
                    {"type": ActionType.EXTRACT_ACTION_ITEMS, "params": {}},
                    {"type": ActionType.CREATE_OBSIDIAN_NOTE, "params": {"template": "meeting"}}
                ]
            ),
            WorkflowRule(
                id="urgent_content_notification",
                name="Urgent Content Notification",
                description="Send notifications for urgent or high-priority content",
                trigger_type=TriggerType.KEYWORD_MATCHED,
                trigger_conditions={"keywords": ["urgent", "asap", "emergency", "critical"]},
                actions=[
                    {"type": ActionType.SEND_NOTIFICATION, "params": {"channel": "discord"}}
                ]
            ),
            WorkflowRule(
                id="auto_url_ingestion",
                name="Auto URL Ingestion",
                description="Automatically detect and ingest URLs found in content",
                trigger_type=TriggerType.CONTENT_CREATED,
                trigger_conditions={"contains_url": True},
                actions=[
                    {"type": ActionType.DETECT_URLS, "params": {}},
                    {"type": ActionType.INGEST_WEB_CONTENT, "params": {"max_urls": 3}},
                    {"type": ActionType.AUTO_TAG, "params": {"max_tags": 2, "include_web_tags": True}}
                ]
            )
        ]
        
        for workflow in default_workflows:
            self.active_workflows[workflow.id] = workflow
    
    async def trigger_workflow(self, trigger_type: TriggerType, trigger_data: Dict[str, Any]) -> List[str]:
        """Trigger workflows based on events"""
        triggered_workflows = []
        
        for workflow_id, workflow in self.active_workflows.items():
            if workflow.status != WorkflowStatus.ACTIVE:
                continue
            
            if workflow.trigger_type != trigger_type:
                continue
            
            if self._evaluate_trigger_conditions(workflow.trigger_conditions, trigger_data):
                execution_id = await self._execute_workflow(workflow, trigger_data)
                triggered_workflows.append(execution_id)
        
        return triggered_workflows
    
    def _evaluate_trigger_conditions(self, conditions: Dict[str, Any], trigger_data: Dict[str, Any]) -> bool:
        """Evaluate if trigger conditions are met"""
        for key, expected_value in conditions.items():
            if key == "min_content_length":
                content = trigger_data.get("content", "")
                if len(content) < expected_value:
                    return False
            
            elif key == "tags":
                note_tags = set(trigger_data.get("tags", "").split(","))
                required_tags = set(expected_value)
                if not required_tags.intersection(note_tags):
                    return False
            
            elif key == "keywords":
                content = f"{trigger_data.get('title', '')} {trigger_data.get('content', '')}".lower()
                if not any(keyword.lower() in content for keyword in expected_value):
                    return False
            
            elif key == "contains_url":
                content = trigger_data.get("content", "")
                import re
                url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
                has_urls = bool(re.search(url_pattern, content))
                if has_urls != expected_value:
                    return False
            
            elif key in trigger_data:
                if trigger_data[key] != expected_value:
                    return False
        
        return True
    
    async def _execute_workflow(self, workflow: WorkflowRule, trigger_data: Dict[str, Any]) -> str:
        """Execute a workflow with its actions"""
        execution_id = f"exec_{workflow.id}_{datetime.now().timestamp()}"
        execution = WorkflowExecution(
            id=execution_id,
            rule_id=workflow.id,
            trigger_data=trigger_data,
            status="running",
            started_at=datetime.now(),
            actions_completed=[]
        )
        
        try:
            result_data = {}
            
            for action_config in workflow.actions:
                action_type = ActionType(action_config["type"])
                params = action_config.get("params", {})
                
                action_result = await self._execute_action(action_type, trigger_data, params)
                result_data[action_type.value] = action_result
                execution.actions_completed.append(action_type.value)
            
            execution.status = "completed"
            execution.completed_at = datetime.now()
            execution.result_data = result_data
            
            # Update workflow run statistics
            workflow.last_run = datetime.now()
            workflow.run_count += 1
            
        except Exception as e:
            execution.status = "error"
            execution.error_message = str(e)
            execution.completed_at = datetime.now()
        
        # Store execution record
        await self._store_execution_record(execution)
        return execution_id
    
    async def _execute_action(self, action_type: ActionType, trigger_data: Dict[str, Any], params: Dict[str, Any]) -> Any:
        """Execute a specific workflow action"""
        note_id = trigger_data.get("note_id")
        
        if action_type == ActionType.AUTO_TAG:
            return await self._action_auto_tag(trigger_data, params)
        
        elif action_type == ActionType.CLASSIFY_CONTENT:
            return await self._action_classify_content(trigger_data, params)
        
        elif action_type == ActionType.AUTO_SUMMARIZE:
            return await self._action_auto_summarize(trigger_data, params)
        
        elif action_type == ActionType.EXTRACT_ACTION_ITEMS:
            return await self._action_extract_action_items(trigger_data, params)
        
        elif action_type == ActionType.GENERATE_TITLE:
            return await self._action_generate_title(trigger_data, params)
        
        elif action_type == ActionType.SEND_NOTIFICATION:
            return await self._action_send_notification(trigger_data, params)
        
        elif action_type == ActionType.CREATE_OBSIDIAN_NOTE:
            return await self._action_create_obsidian_note(trigger_data, params)
        
        elif action_type == ActionType.DETECT_URLS:
            return await self._action_detect_urls(trigger_data, params)
        
        elif action_type == ActionType.INGEST_WEB_CONTENT:
            return await self._action_ingest_web_content(trigger_data, params)
        
        else:
            raise ValueError(f"Unknown action type: {action_type}")
    
    async def _action_auto_tag(self, trigger_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-tag content based on AI analysis"""
        title = trigger_data.get("title", "")
        content = trigger_data.get("content", "")
        existing_tags = trigger_data.get("tags", "").split(",") if trigger_data.get("tags") else []
        
        classification = self.classifier.classify_content(title, content, existing_tags)
        suggested_tags = classification["suggested_tags"][:params.get("max_tags", 3)]
        
        if suggested_tags and trigger_data.get("note_id"):
            # Update note with new tags
            conn = self.get_conn()
            try:
                current_tags = set(existing_tags)
                current_tags.update(suggested_tags)
                new_tags = ",".join(filter(None, current_tags))
                
                c = conn.cursor()
                c.execute("UPDATE notes SET tags = ? WHERE id = ?", (new_tags, trigger_data["note_id"]))
                conn.commit()
            finally:
                conn.close()
        
        return {
            "suggested_tags": suggested_tags,
            "classification": classification,
            "tags_added": suggested_tags
        }
    
    async def _action_classify_content(self, trigger_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Classify content and store classification metadata"""
        title = trigger_data.get("title", "")
        content = trigger_data.get("content", "")
        existing_tags = trigger_data.get("tags", "").split(",") if trigger_data.get("tags") else []
        
        classification = self.classifier.classify_content(title, content, existing_tags)
        
        if trigger_data.get("note_id"):
            # Store classification in note metadata
            conn = self.get_conn()
            try:
                c = conn.cursor()
                c.execute(
                    "UPDATE notes SET type = ? WHERE id = ?",
                    (classification["primary_category"], trigger_data["note_id"])
                )
                conn.commit()
            finally:
                conn.close()
        
        return classification
    
    async def _action_auto_summarize(self, trigger_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate AI summary for content"""
        content = trigger_data.get("content", "")
        max_length = params.get("max_length", 200)
        
        try:
            summary_result = ollama_summarize(content)
            summary = summary_result.get("summary", "")
            
            if summary and trigger_data.get("note_id"):
                # Update note with summary
                conn = self.get_conn()
                try:
                    c = conn.cursor()
                    c.execute("UPDATE notes SET summary = ? WHERE id = ?", (summary, trigger_data["note_id"]))
                    conn.commit()
                finally:
                    conn.close()
            
            return {"summary": summary, "length": len(summary)}
        
        except Exception as e:
            return {"error": str(e), "summary": ""}
    
    async def _action_extract_action_items(self, trigger_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Extract action items from content"""
        content = trigger_data.get("content", "")
        
        # Simple regex-based action item extraction
        action_patterns = [
            r'(?:TODO|todo|To-do|Action|Task):\s*(.+?)(?:\n|$)',
            r'\[[ ]?\]\s*(.+?)(?:\n|$)',
            r'(?:Need to|Must|Should|Will):\s*(.+?)(?:\n|$)'
        ]
        
        action_items = []
        for pattern in action_patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            action_items.extend([match.strip() for match in matches])
        
        # Remove duplicates and empty items
        action_items = list(set(filter(None, action_items)))
        
        if action_items and trigger_data.get("note_id"):
            # Update note with action items
            actions_text = "\n".join(f"- [ ] {item}" for item in action_items)
            conn = self.get_conn()
            try:
                c = conn.cursor()
                c.execute("UPDATE notes SET actions = ? WHERE id = ?", (actions_text, trigger_data["note_id"]))
                conn.commit()
            finally:
                conn.close()
        
        return {"action_items": action_items, "count": len(action_items)}
    
    async def _action_generate_title(self, trigger_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate AI title for content"""
        content = trigger_data.get("content", "")
        
        try:
            title_result = ollama_generate_title(content)
            title = title_result.get("title", "")
            
            if title and trigger_data.get("note_id"):
                # Update note with generated title
                conn = self.get_conn()
                try:
                    c = conn.cursor()
                    c.execute("UPDATE notes SET title = ? WHERE id = ?", (title, trigger_data["note_id"]))
                    conn.commit()
                finally:
                    conn.close()
            
            return {"title": title, "original_length": len(content)}
        
        except Exception as e:
            return {"error": str(e), "title": ""}
    
    async def _action_send_notification(self, trigger_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Send notification for urgent content"""
        channel = params.get("channel", "discord")
        
        # For now, just log the notification
        # This can be extended to integrate with Discord bot, email, etc.
        notification_data = {
            "channel": channel,
            "message": f"Urgent content detected: {trigger_data.get('title', 'Untitled')}",
            "content_preview": trigger_data.get("content", "")[:100],
            "timestamp": datetime.now().isoformat()
        }
        
        # Log notification (extend to actual delivery later)
        print(f"[WORKFLOW NOTIFICATION] {notification_data}")
        
        return notification_data
    
    async def _action_create_obsidian_note(self, trigger_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update Obsidian note with special formatting"""
        template = params.get("template", "default")
        
        # This would integrate with the ObsidianSync service
        # For now, return metadata about the note creation
        return {
            "template": template,
            "note_id": trigger_data.get("note_id"),
            "obsidian_path": f"{trigger_data.get('title', 'note')}.md"
        }
    
    async def _action_detect_urls(self, trigger_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Detect URLs in content"""
        content = trigger_data.get("content", "")
        
        import re
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, content)
        
        # Store detected URLs in the trigger data for subsequent actions
        trigger_data["detected_urls"] = urls
        
        return {
            "urls_found": urls,
            "url_count": len(urls),
            "note_id": trigger_data.get("note_id")
        }
    
    async def _action_ingest_web_content(self, trigger_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Ingest web content from detected URLs"""
        urls = trigger_data.get("detected_urls", [])
        max_urls = params.get("max_urls", 3)
        user_id = trigger_data.get("user_id", 1)
        
        if not urls:
            return {"ingested": 0, "results": []}
        
        # Limit URLs to process
        urls_to_process = urls[:max_urls]
        results = []
        
        try:
            # Import web ingestion service
            from services.web_ingestion_service import WebIngestionService, ExtractionConfig
            
            web_service = WebIngestionService(self.get_conn)
            config = ExtractionConfig(
                take_screenshot=True,
                extract_images=False,
                timeout=30
            )
            
            for url in urls_to_process:
                try:
                    result = await web_service.ingest_url(url, user_id, config=config)
                    results.append({
                        "url": url,
                        "success": True,
                        "note_id": result.get("note_id"),
                        "title": result.get("title"),
                        "summary": result.get("summary")
                    })
                except Exception as e:
                    results.append({
                        "url": url,
                        "success": False,
                        "error": str(e)
                    })
            
            return {
                "ingested": sum(1 for r in results if r["success"]),
                "total_urls": len(urls_to_process),
                "results": results
            }
            
        except ImportError:
            return {
                "ingested": 0,
                "error": "Web ingestion service not available",
                "results": []
            }
    
    async def _store_execution_record(self, execution: WorkflowExecution):
        """Store workflow execution record for auditing"""
        # Store in a workflow_executions table (would need migration)
        # For now, just log the execution
        print(f"[WORKFLOW EXECUTION] {execution.id}: {execution.status}")
    
    # --- Management Methods ---
    
    def add_workflow(self, workflow: WorkflowRule) -> None:
        """Add a new workflow rule"""
        self.active_workflows[workflow.id] = workflow
    
    def remove_workflow(self, workflow_id: str) -> bool:
        """Remove a workflow rule"""
        return self.active_workflows.pop(workflow_id, None) is not None
    
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowRule]:
        """Get workflow by ID"""
        return self.active_workflows.get(workflow_id)
    
    def list_workflows(self) -> List[WorkflowRule]:
        """List all active workflows"""
        return list(self.active_workflows.values())
    
    def get_workflow_stats(self) -> Dict[str, Any]:
        """Get workflow execution statistics"""
        return {
            "total_workflows": len(self.active_workflows),
            "active_workflows": len([w for w in self.active_workflows.values() if w.status == WorkflowStatus.ACTIVE]),
            "total_executions": sum(w.run_count for w in self.active_workflows.values()),
            "workflows": [
                {
                    "id": w.id,
                    "name": w.name,
                    "status": w.status,
                    "run_count": w.run_count,
                    "last_run": w.last_run.isoformat() if w.last_run else None
                }
                for w in self.active_workflows.values()
            ]
        }


# --- API Models for FastAPI Integration ---

class WorkflowRuleCreate(BaseModel):
    name: str
    description: str
    trigger_type: TriggerType
    trigger_conditions: Dict[str, Any]
    actions: List[Dict[str, Any]]
    priority: int = 5


class WorkflowRuleResponse(BaseModel):
    id: str
    name: str
    description: str
    trigger_type: TriggerType
    trigger_conditions: Dict[str, Any]
    actions: List[Dict[str, Any]]
    status: WorkflowStatus
    created_at: Optional[str] = None
    last_run: Optional[str] = None
    run_count: int = 0
    priority: int = 5


class WorkflowStatsResponse(BaseModel):
    total_workflows: int
    active_workflows: int
    total_executions: int
    workflows: List[Dict[str, Any]]


class ContentClassificationResponse(BaseModel):
    primary_category: str
    category_scores: Dict[str, int]
    suggested_tags: List[str]
    matched_keywords: Dict[str, List[str]]
    confidence: float