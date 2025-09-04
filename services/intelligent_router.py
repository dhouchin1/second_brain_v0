"""
Intelligent Router Service

Handles smart content routing, integration orchestration, and context-aware
processing decisions for Second Brain. Works with the workflow engine to
provide intelligent automation and content management.
"""

from __future__ import annotations
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from fastapi import HTTPException
import sqlite3
from pydantic import BaseModel

from config import settings
from services.workflow_engine import WorkflowEngine, TriggerType, ContentClassifier


class RoutingPriority(str, Enum):
    """Content routing priority levels"""
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal" 
    LOW = "low"
    BACKGROUND = "background"


class ProcessingMode(str, Enum):
    """Content processing modes"""
    IMMEDIATE = "immediate"      # Process immediately
    BATCH = "batch"             # Add to batch processing queue
    SCHEDULED = "scheduled"     # Schedule for later processing
    CONDITIONAL = "conditional" # Process based on conditions


class IntegrationType(str, Enum):
    """Types of integrations for routing"""
    OBSIDIAN = "obsidian"
    DISCORD = "discord"
    EMAIL = "email"
    WEBHOOK = "webhook"
    BROWSER = "browser"
    APPLE_SHORTCUTS = "apple_shortcuts"
    FILE_SYSTEM = "file_system"


@dataclass
class RoutingRule:
    """Defines intelligent routing logic"""
    id: str
    name: str
    description: str
    conditions: Dict[str, Any]
    routing_targets: List[Dict[str, Any]]
    priority: RoutingPriority
    processing_mode: ProcessingMode
    enabled: bool = True
    created_at: Optional[datetime] = None
    match_count: int = 0


@dataclass
class RoutingDecision:
    """Result of routing analysis"""
    content_id: str
    matched_rules: List[str]
    routing_targets: List[Dict[str, Any]]
    priority: RoutingPriority
    processing_mode: ProcessingMode
    confidence: float
    reasoning: List[str]
    metadata: Dict[str, Any]


class ContentAnalyzer:
    """Advanced content analysis for routing decisions"""
    
    URGENCY_KEYWORDS = [
        "urgent", "emergency", "asap", "critical", "important", "deadline",
        "meeting in", "due today", "expires", "urgent", "priority"
    ]
    
    MEETING_INDICATORS = [
        "meeting", "call", "standup", "review", "demo", "interview",
        "presentation", "conference", "workshop", "sync"
    ]
    
    TASK_INDICATORS = [
        "todo", "task", "action", "assignment", "deliverable",
        "complete", "finish", "implement", "fix", "build"
    ]
    
    def __init__(self):
        self.classifier = ContentClassifier()
    
    def analyze_content(self, title: str, content: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Comprehensive content analysis for routing"""
        text = f"{title} {content}".lower()
        metadata = metadata or {}
        
        analysis = {
            "urgency_score": self._calculate_urgency(text),
            "content_type": self._detect_content_type(text),
            "complexity_score": self._calculate_complexity(content),
            "processing_time_estimate": self._estimate_processing_time(content, metadata),
            "integration_hints": self._detect_integration_hints(text, metadata),
            "temporal_context": self._analyze_temporal_context(text),
            "classification": self.classifier.classify_content(title, content)
        }
        
        return analysis
    
    def _calculate_urgency(self, text: str) -> float:
        """Calculate urgency score based on content analysis"""
        urgency_count = sum(1 for keyword in self.URGENCY_KEYWORDS if keyword in text)
        
        # Check for time-sensitive patterns
        time_patterns = [
            r"\b(?:today|tomorrow|this week|deadline|due)\b",
            r"\b(?:urgent|asap|emergency|critical)\b",
            r"\b(?:meeting in|call in|due in) \d+\s*(?:minutes?|hours?|days?)\b"
        ]
        
        import re
        pattern_matches = sum(1 for pattern in time_patterns if re.search(pattern, text))
        
        # Normalize to 0-1 scale
        urgency_score = min((urgency_count * 0.3 + pattern_matches * 0.5), 1.0)
        return urgency_score
    
    def _detect_content_type(self, text: str) -> str:
        """Detect the primary content type"""
        type_scores = {}
        
        # Meeting detection
        meeting_count = sum(1 for indicator in self.MEETING_INDICATORS if indicator in text)
        if meeting_count > 0:
            type_scores["meeting"] = meeting_count
        
        # Task detection  
        task_count = sum(1 for indicator in self.TASK_INDICATORS if indicator in text)
        if task_count > 0:
            type_scores["task"] = task_count
        
        # Note patterns
        if any(word in text for word in ["note", "remember", "idea", "thought"]):
            type_scores["note"] = 1
        
        # Research patterns
        if any(word in text for word in ["research", "analysis", "study", "findings"]):
            type_scores["research"] = 1
        
        return max(type_scores, key=type_scores.get) if type_scores else "general"
    
    def _calculate_complexity(self, content: str) -> float:
        """Calculate content complexity for processing estimation"""
        factors = {
            "length": len(content) / 1000.0,  # Normalize by 1000 chars
            "sentences": content.count('.') / 10.0,  # Normalize by 10 sentences
            "technical_terms": self._count_technical_terms(content) / 5.0,
            "structure_complexity": self._analyze_structure_complexity(content)
        }
        
        # Weighted average
        complexity = (
            factors["length"] * 0.3 +
            factors["sentences"] * 0.2 +
            factors["technical_terms"] * 0.3 +
            factors["structure_complexity"] * 0.2
        )
        
        return min(complexity, 1.0)
    
    def _count_technical_terms(self, content: str) -> int:
        """Count technical terminology that might require special processing"""
        technical_patterns = [
            r'\b(?:API|HTTP|REST|JSON|SQL|HTML|CSS|JavaScript|Python|React)\b',
            r'\b(?:database|server|client|endpoint|authentication|authorization)\b',
            r'\b(?:function|method|class|object|variable|parameter)\b'
        ]
        
        import re
        count = 0
        for pattern in technical_patterns:
            count += len(re.findall(pattern, content, re.IGNORECASE))
        
        return count
    
    def _analyze_structure_complexity(self, content: str) -> float:
        """Analyze structural complexity (lists, headers, etc.)"""
        structure_score = 0
        
        # Check for markdown/structured elements
        if '##' in content or '###' in content:
            structure_score += 0.3
        if '- ' in content or '* ' in content:
            structure_score += 0.2
        if '1. ' in content or '2. ' in content:
            structure_score += 0.2
        if '```' in content:
            structure_score += 0.3
        
        return min(structure_score, 1.0)
    
    def _estimate_processing_time(self, content: str, metadata: Dict[str, Any]) -> int:
        """Estimate processing time in seconds"""
        base_time = 2  # Base processing time
        
        # Factor in content length
        length_factor = len(content) / 500.0  # 500 chars = 1 second
        
        # Factor in complexity
        complexity = self._calculate_complexity(content)
        complexity_factor = complexity * 3
        
        # Factor in media files
        media_factor = 0
        if metadata.get("has_audio"):
            media_factor += 15  # Audio transcription time
        if metadata.get("has_images"):
            media_factor += 5   # Image processing time
        
        total_time = base_time + length_factor + complexity_factor + media_factor
        return int(min(total_time, 300))  # Cap at 5 minutes
    
    def _detect_integration_hints(self, text: str, metadata: Dict[str, Any]) -> List[str]:
        """Detect which integrations might be relevant"""
        hints = []
        
        # Obsidian hints
        if any(word in text for word in ["note", "vault", "markdown", "link"]):
            hints.append(IntegrationType.OBSIDIAN)
        
        # Discord hints
        if any(word in text for word in ["discord", "channel", "mention", "@"]):
            hints.append(IntegrationType.DISCORD)
        
        # Email hints
        if any(word in text for word in ["email", "send", "recipient", "@"]):
            hints.append(IntegrationType.EMAIL)
        
        # File system hints
        if metadata.get("source_type") == "file" or "file" in text:
            hints.append(IntegrationType.FILE_SYSTEM)
        
        return hints
    
    def _analyze_temporal_context(self, text: str) -> Dict[str, Any]:
        """Analyze temporal context for scheduling"""
        import re
        
        temporal_info = {
            "has_deadline": bool(re.search(r"\b(?:deadline|due|expires?)\b", text)),
            "has_meeting_time": bool(re.search(r"\b(?:meeting|call).*(?:at|@)\s*\d", text)),
            "time_sensitive": bool(re.search(r"\b(?:today|tomorrow|urgent|asap)\b", text)),
            "future_oriented": bool(re.search(r"\b(?:plan|will|going to|next week|next month)\b", text))
        }
        
        return temporal_info


class IntelligentRouter:
    """Core intelligent routing service"""
    
    def __init__(self, get_conn_func: Callable[[], sqlite3.Connection]):
        self.get_conn = get_conn_func
        self.analyzer = ContentAnalyzer()
        self.routing_rules: Dict[str, RoutingRule] = {}
        self._initialize_default_rules()
    
    def _initialize_default_rules(self):
        """Set up default routing rules"""
        default_rules = [
            RoutingRule(
                id="urgent_content_immediate",
                name="Urgent Content - Immediate Processing",
                description="Route urgent content for immediate processing",
                conditions={
                    "urgency_score": {"min": 0.7},
                    "content_types": ["meeting", "task"]
                },
                routing_targets=[
                    {
                        "type": "workflow",
                        "target": "urgent_content_notification",
                        "params": {"priority": "high"}
                    },
                    {
                        "type": "integration",
                        "target": IntegrationType.DISCORD,
                        "params": {"channel": "urgent-notifications"}
                    }
                ],
                priority=RoutingPriority.URGENT,
                processing_mode=ProcessingMode.IMMEDIATE
            ),
            
            RoutingRule(
                id="meeting_notes_special",
                name="Meeting Notes - Special Processing",
                description="Special handling for meeting-related content",
                conditions={
                    "content_types": ["meeting"],
                    "keywords": ["meeting", "call", "standup"]
                },
                routing_targets=[
                    {
                        "type": "workflow",
                        "target": "meeting_note_processing",
                        "params": {}
                    },
                    {
                        "type": "integration",
                        "target": IntegrationType.OBSIDIAN,
                        "params": {"folder": "Meetings", "template": "meeting"}
                    }
                ],
                priority=RoutingPriority.HIGH,
                processing_mode=ProcessingMode.IMMEDIATE
            ),
            
            RoutingRule(
                id="complex_content_batch",
                name="Complex Content - Batch Processing",
                description="Route complex content to batch processing for efficiency",
                conditions={
                    "complexity_score": {"min": 0.6},
                    "processing_time": {"min": 30}
                },
                routing_targets=[
                    {
                        "type": "queue",
                        "target": "batch_processing",
                        "params": {"batch_size": 10}
                    }
                ],
                priority=RoutingPriority.NORMAL,
                processing_mode=ProcessingMode.BATCH
            ),
            
            RoutingRule(
                id="research_content_enhanced",
                name="Research Content - Enhanced Processing",
                description="Enhanced processing for research and technical content",
                conditions={
                    "content_types": ["research", "technical"],
                    "complexity_score": {"min": 0.4}
                },
                routing_targets=[
                    {
                        "type": "workflow",
                        "target": "research_enhancement",
                        "params": {"include_references": True}
                    },
                    {
                        "type": "integration", 
                        "target": IntegrationType.OBSIDIAN,
                        "params": {"folder": "Research", "link_references": True}
                    }
                ],
                priority=RoutingPriority.HIGH,
                processing_mode=ProcessingMode.IMMEDIATE
            ),
            
            RoutingRule(
                id="simple_content_fast",
                name="Simple Content - Fast Track",
                description="Fast processing for simple content",
                conditions={
                    "complexity_score": {"max": 0.3},
                    "processing_time": {"max": 10}
                },
                routing_targets=[
                    {
                        "type": "workflow",
                        "target": "simple_processing",
                        "params": {"skip_ai_analysis": True}
                    }
                ],
                priority=RoutingPriority.NORMAL,
                processing_mode=ProcessingMode.IMMEDIATE
            )
        ]
        
        for rule in default_rules:
            self.routing_rules[rule.id] = rule
    
    async def route_content(self, content_data: Dict[str, Any]) -> RoutingDecision:
        """Main routing decision function"""
        content_id = content_data.get("id", "unknown")
        title = content_data.get("title", "")
        content = content_data.get("content", "")
        metadata = content_data.get("metadata", {})
        
        # Analyze content
        analysis = self.analyzer.analyze_content(title, content, metadata)
        
        # Find matching rules
        matched_rules = []
        routing_targets = []
        reasoning = []
        
        for rule_id, rule in self.routing_rules.items():
            if not rule.enabled:
                continue
            
            if self._evaluate_rule_conditions(rule.conditions, analysis, content_data):
                matched_rules.append(rule_id)
                routing_targets.extend(rule.routing_targets)
                reasoning.append(f"Matched rule '{rule.name}': {rule.description}")
                rule.match_count += 1
        
        # Determine overall priority and processing mode
        priority = self._determine_priority(matched_rules, analysis)
        processing_mode = self._determine_processing_mode(matched_rules, analysis)
        
        # Calculate confidence
        confidence = self._calculate_confidence(matched_rules, analysis)
        
        # Add analysis-based reasoning
        if analysis["urgency_score"] > 0.5:
            reasoning.append(f"High urgency detected (score: {analysis['urgency_score']:.2f})")
        if analysis["complexity_score"] > 0.7:
            reasoning.append(f"High complexity content (score: {analysis['complexity_score']:.2f})")
        
        decision = RoutingDecision(
            content_id=content_id,
            matched_rules=matched_rules,
            routing_targets=routing_targets,
            priority=priority,
            processing_mode=processing_mode,
            confidence=confidence,
            reasoning=reasoning,
            metadata={
                "analysis": analysis,
                "processing_time_estimate": analysis["processing_time_estimate"]
            }
        )
        
        return decision
    
    def _evaluate_rule_conditions(self, conditions: Dict[str, Any], analysis: Dict[str, Any], content_data: Dict[str, Any]) -> bool:
        """Evaluate if rule conditions are met"""
        for condition_key, condition_value in conditions.items():
            
            if condition_key == "urgency_score":
                urgency = analysis.get("urgency_score", 0)
                if "min" in condition_value and urgency < condition_value["min"]:
                    return False
                if "max" in condition_value and urgency > condition_value["max"]:
                    return False
            
            elif condition_key == "complexity_score":
                complexity = analysis.get("complexity_score", 0)
                if "min" in condition_value and complexity < condition_value["min"]:
                    return False
                if "max" in condition_value and complexity > condition_value["max"]:
                    return False
            
            elif condition_key == "processing_time":
                proc_time = analysis.get("processing_time_estimate", 0)
                if "min" in condition_value and proc_time < condition_value["min"]:
                    return False
                if "max" in condition_value and proc_time > condition_value["max"]:
                    return False
            
            elif condition_key == "content_types":
                content_type = analysis.get("content_type", "general")
                if content_type not in condition_value:
                    return False
            
            elif condition_key == "keywords":
                text = f"{content_data.get('title', '')} {content_data.get('content', '')}".lower()
                if not any(keyword.lower() in text for keyword in condition_value):
                    return False
            
            elif condition_key in analysis:
                if analysis[condition_key] != condition_value:
                    return False
        
        return True
    
    def _determine_priority(self, matched_rules: List[str], analysis: Dict[str, Any]) -> RoutingPriority:
        """Determine overall routing priority"""
        if not matched_rules:
            return RoutingPriority.NORMAL
        
        # Get highest priority from matched rules
        priorities = []
        for rule_id in matched_rules:
            rule = self.routing_rules[rule_id]
            priorities.append(rule.priority)
        
        # Priority order: URGENT > HIGH > NORMAL > LOW > BACKGROUND
        priority_order = [
            RoutingPriority.URGENT,
            RoutingPriority.HIGH,
            RoutingPriority.NORMAL,
            RoutingPriority.LOW,
            RoutingPriority.BACKGROUND
        ]
        
        for priority in priority_order:
            if priority in priorities:
                return priority
        
        return RoutingPriority.NORMAL
    
    def _determine_processing_mode(self, matched_rules: List[str], analysis: Dict[str, Any]) -> ProcessingMode:
        """Determine processing mode"""
        if not matched_rules:
            return ProcessingMode.IMMEDIATE
        
        # Check for immediate processing requirements
        for rule_id in matched_rules:
            rule = self.routing_rules[rule_id]
            if rule.processing_mode == ProcessingMode.IMMEDIATE:
                return ProcessingMode.IMMEDIATE
        
        # Check complexity and urgency for batch processing
        if (analysis.get("complexity_score", 0) > 0.6 and 
            analysis.get("urgency_score", 0) < 0.3):
            return ProcessingMode.BATCH
        
        return ProcessingMode.IMMEDIATE
    
    def _calculate_confidence(self, matched_rules: List[str], analysis: Dict[str, Any]) -> float:
        """Calculate confidence in routing decision"""
        if not matched_rules:
            return 0.3  # Low confidence for no matches
        
        # Base confidence from number of matched rules
        rule_confidence = min(len(matched_rules) * 0.3, 0.9)
        
        # Adjust based on analysis certainty
        classification_confidence = analysis.get("classification", {}).get("confidence", 0.5)
        
        # Combined confidence
        total_confidence = (rule_confidence * 0.7 + classification_confidence * 0.3)
        
        return min(total_confidence, 1.0)
    
    # --- Integration Execution ---
    
    async def execute_routing_decision(self, decision: RoutingDecision, content_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the routing decision"""
        results = []
        
        for target in decision.routing_targets:
            try:
                result = await self._execute_routing_target(target, content_data, decision)
                results.append({
                    "target": target,
                    "result": result,
                    "status": "success"
                })
            except Exception as e:
                results.append({
                    "target": target,
                    "error": str(e),
                    "status": "error"
                })
        
        return {
            "decision_id": decision.content_id,
            "execution_results": results,
            "total_targets": len(decision.routing_targets),
            "successful_targets": len([r for r in results if r["status"] == "success"]),
            "execution_time": datetime.now().isoformat()
        }
    
    async def _execute_routing_target(self, target: Dict[str, Any], content_data: Dict[str, Any], decision: RoutingDecision) -> Any:
        """Execute a specific routing target"""
        target_type = target.get("type")
        target_name = target.get("target")
        params = target.get("params", {})
        
        if target_type == "workflow":
            # Execute workflow (would integrate with WorkflowEngine)
            return {"workflow_triggered": target_name, "params": params}
        
        elif target_type == "integration":
            # Route to integration (Discord, Obsidian, etc.)
            return await self._route_to_integration(target_name, content_data, params)
        
        elif target_type == "queue":
            # Add to processing queue
            return {"queued": target_name, "priority": decision.priority}
        
        else:
            raise ValueError(f"Unknown routing target type: {target_type}")
    
    async def _route_to_integration(self, integration: str, content_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Route content to specific integration"""
        if integration == IntegrationType.OBSIDIAN:
            # Obsidian integration logic
            return {
                "integration": "obsidian",
                "folder": params.get("folder", "Inbox"),
                "template": params.get("template"),
                "note_created": True
            }
        
        elif integration == IntegrationType.DISCORD:
            # Discord integration logic  
            return {
                "integration": "discord",
                "channel": params.get("channel", "general"),
                "message_sent": True
            }
        
        else:
            return {"integration": integration, "status": "not_implemented"}
    
    # --- Management Methods ---
    
    def add_routing_rule(self, rule: RoutingRule) -> None:
        """Add a new routing rule"""
        self.routing_rules[rule.id] = rule
    
    def remove_routing_rule(self, rule_id: str) -> bool:
        """Remove a routing rule"""
        return self.routing_rules.pop(rule_id, None) is not None
    
    def get_routing_rule(self, rule_id: str) -> Optional[RoutingRule]:
        """Get routing rule by ID"""
        return self.routing_rules.get(rule_id)
    
    def list_routing_rules(self) -> List[RoutingRule]:
        """List all routing rules"""
        return list(self.routing_rules.values())
    
    def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing statistics"""
        return {
            "total_rules": len(self.routing_rules),
            "active_rules": len([r for r in self.routing_rules.values() if r.enabled]),
            "total_matches": sum(r.match_count for r in self.routing_rules.values()),
            "rules": [
                {
                    "id": r.id,
                    "name": r.name,
                    "enabled": r.enabled,
                    "match_count": r.match_count,
                    "priority": r.priority,
                    "processing_mode": r.processing_mode
                }
                for r in self.routing_rules.values()
            ]
        }


# --- API Models for FastAPI Integration ---

class RoutingRuleCreate(BaseModel):
    name: str
    description: str
    conditions: Dict[str, Any]
    routing_targets: List[Dict[str, Any]]
    priority: RoutingPriority
    processing_mode: ProcessingMode


class RoutingRuleResponse(BaseModel):
    id: str
    name: str
    description: str
    conditions: Dict[str, Any]
    routing_targets: List[Dict[str, Any]]
    priority: RoutingPriority
    processing_mode: ProcessingMode
    enabled: bool
    match_count: int


class RoutingDecisionResponse(BaseModel):
    content_id: str
    matched_rules: List[str]
    routing_targets: List[Dict[str, Any]]
    priority: RoutingPriority
    processing_mode: ProcessingMode
    confidence: float
    reasoning: List[str]
    metadata: Dict[str, Any]


class RoutingStatsResponse(BaseModel):
    total_rules: int
    active_rules: int
    total_matches: int
    rules: List[Dict[str, Any]]


class ContentAnalysisResponse(BaseModel):
    urgency_score: float
    content_type: str
    complexity_score: float
    processing_time_estimate: int
    integration_hints: List[str]
    temporal_context: Dict[str, Any]
    classification: Dict[str, Any]