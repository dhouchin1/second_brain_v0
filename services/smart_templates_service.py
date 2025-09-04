"""
Smart Templates Service

AI-powered context-aware note templates that adapt based on:
- Content analysis and intent detection
- Time of day and calendar context
- User patterns and preferences
- Location and device context
- Previous note history and tags
"""

import json
import re
from datetime import datetime, time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import sqlite3

from services.auth_service import User


class TemplateType(str, Enum):
    """Types of smart templates"""
    MEETING = "meeting"
    DAILY_STANDUP = "daily_standup"
    PROJECT_PLANNING = "project_planning"
    LEARNING_NOTES = "learning_notes"
    DECISION_LOG = "decision_log"
    RETROSPECTIVE = "retrospective"
    IDEA_CAPTURE = "idea_capture"
    RESEARCH_NOTES = "research_notes"
    TRAVEL_LOG = "travel_log"
    BOOK_NOTES = "book_notes"
    WORKOUT_LOG = "workout_log"
    MEAL_PLANNING = "meal_planning"
    GOAL_SETTING = "goal_setting"
    WEEKLY_REVIEW = "weekly_review"
    QUICK_TODO = "quick_todo"
    PHONE_CALL = "phone_call"
    INTERVIEW_NOTES = "interview_notes"
    BRAINSTORM = "brainstorm"
    BUDGET_TRACKING = "budget_tracking"
    HEALTH_LOG = "health_log"


class ContextTrigger(str, Enum):
    """Context triggers for template suggestions"""
    TIME_OF_DAY = "time_of_day"
    CALENDAR_EVENT = "calendar_event"
    KEYWORD_MATCH = "keyword_match"
    RECURRING_PATTERN = "recurring_pattern"
    LOCATION_CONTEXT = "location_context"
    DEVICE_CONTEXT = "device_context"
    CONTENT_ANALYSIS = "content_analysis"
    USER_PREFERENCE = "user_preference"


@dataclass
class SmartTemplate:
    """Smart template definition with AI context"""
    id: str
    name: str
    type: TemplateType
    template_content: str
    description: str
    triggers: List[ContextTrigger]
    keywords: List[str]
    time_contexts: List[str]  # ["morning", "afternoon", "evening", "weekend"]
    confidence_score: float
    usage_count: int = 0
    last_used: Optional[datetime] = None
    user_customizations: Dict[str, Any] = None
    ai_generated: bool = False


class SmartTemplatesService:
    """Service for intelligent, context-aware note templates"""
    
    def __init__(self, get_conn_func):
        self.get_conn = get_conn_func
        self._initialize_default_templates()
        self._load_ai_models()
    
    def _load_ai_models(self):
        """Load AI models for content analysis"""
        # Placeholder for future ML model integration
        self.content_classifier = None
        self.intent_detector = None
    
    def _initialize_default_templates(self):
        """Initialize the smart template library"""
        self.templates = {
            # Meeting Templates
            "meeting_general": SmartTemplate(
                id="meeting_general",
                name="📅 General Meeting",
                type=TemplateType.MEETING,
                template_content="""# {meeting_title} - {date}

## 👥 Attendees
- {attendees}

## 🎯 Agenda
1. 
2. 
3. 

## 📝 Discussion Notes


## ✅ Action Items
- [ ] {action_item_1} - @{assignee} - Due: {due_date}
- [ ] 

## 🔗 Resources & Links


## 📋 Next Steps


---
*Meeting Type: {meeting_type}*
*Duration: {duration}*
*Location: {location}*""",
                description="Comprehensive meeting notes with action items",
                triggers=[ContextTrigger.CALENDAR_EVENT, ContextTrigger.KEYWORD_MATCH],
                keywords=["meeting", "call", "zoom", "conference", "discussion", "sync"],
                time_contexts=["morning", "afternoon"],
                confidence_score=0.9
            ),
            
            "daily_standup": SmartTemplate(
                id="daily_standup",
                name="🏃‍♂️ Daily Standup",
                type=TemplateType.DAILY_STANDUP,
                template_content="""# Daily Standup - {date}

## ✅ What I Did Yesterday
- 

## 🎯 What I'm Doing Today
- 

## 🚧 Blockers & Challenges
- 

## 💡 Key Insights


## 📊 Progress Update
**Sprint Goal Progress:** {progress}%
**Priority Tasks:** {priority_tasks}

---
*Team: {team_name}*
*Sprint: {sprint_name}*""",
                description="Daily standup meeting template with progress tracking",
                triggers=[ContextTrigger.TIME_OF_DAY, ContextTrigger.RECURRING_PATTERN],
                keywords=["standup", "daily", "scrum", "team update"],
                time_contexts=["morning"],
                confidence_score=0.85
            ),
            
            # Learning & Research Templates
            "learning_notes": SmartTemplate(
                id="learning_notes",
                name="📚 Learning Notes",
                type=TemplateType.LEARNING_NOTES,
                template_content="""# {topic} - Learning Notes

## 🎯 Learning Objectives
- 
- 
- 

## 📖 Key Concepts
### {concept_1}


### {concept_2}


## 💡 Insights & Connections


## 🔧 Practical Applications


## ❓ Questions & Follow-ups
- [ ] 
- [ ] 

## 📚 Resources
- [{resource_title}]({resource_url})
- 

## 📝 Summary
*What I learned:*


*How I'll apply it:*


---
*Source: {source}*
*Learning Method: {method}*
*Time Invested: {time_spent}*""",
                description="Structured learning and study notes",
                triggers=[ContextTrigger.KEYWORD_MATCH, ContextTrigger.CONTENT_ANALYSIS],
                keywords=["learn", "study", "course", "tutorial", "education", "training"],
                time_contexts=["evening", "weekend"],
                confidence_score=0.8
            ),
            
            # Project & Planning Templates
            "project_planning": SmartTemplate(
                id="project_planning",
                name="🚀 Project Planning",
                type=TemplateType.PROJECT_PLANNING,
                template_content="""# {project_name} - Project Plan

## 🎯 Project Overview
**Goal:** {project_goal}
**Timeline:** {start_date} - {end_date}
**Budget:** {budget}
**Priority:** {priority_level}

## 📋 Project Scope
### In Scope
- 
- 

### Out of Scope
- 
- 

## 🏗️ Deliverables
1. **{deliverable_1}** - Due: {due_date_1}
2. 
3. 

## 👥 Team & Stakeholders
**Project Lead:** {project_lead}
**Team Members:**
- {team_member_1} - {role_1}
- 

**Stakeholders:**
- {stakeholder_1} - {role_1}

## 📊 Milestones & Timeline
- [ ] **{milestone_1}** - {date_1}
- [ ] **{milestone_2}** - {date_2}
- [ ] 

## ⚠️ Risks & Mitigation
| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| {risk_1} | {impact_1} | {probability_1} | {mitigation_1} |

## 📈 Success Metrics
- {metric_1}: {target_1}
- {metric_2}: {target_2}

## 📝 Next Actions
- [ ] {action_1}
- [ ] {action_2}

---
*Project Type: {project_type}*
*Last Updated: {date}*""",
                description="Comprehensive project planning template",
                triggers=[ContextTrigger.KEYWORD_MATCH, ContextTrigger.CONTENT_ANALYSIS],
                keywords=["project", "plan", "timeline", "deliverable", "milestone"],
                time_contexts=["morning", "afternoon"],
                confidence_score=0.9
            ),
            
            # Quick Capture Templates
            "idea_capture": SmartTemplate(
                id="idea_capture",
                name="💡 Idea Capture",
                type=TemplateType.IDEA_CAPTURE,
                template_content="""# 💡 {idea_title}

## 🎯 Core Concept
{core_idea}

## 🧠 Why This Matters
{value_proposition}

## 🔧 How It Could Work
1. 
2. 
3. 

## 📊 Potential Impact
**Who benefits:** {target_audience}
**Potential value:** {potential_value}
**Effort required:** {effort_level}

## 🚧 Challenges & Considerations
- 
- 

## 📝 Next Steps
- [ ] {next_step_1}
- [ ] Research: {research_item}
- [ ] Validate with: {validation_target}

## 🔗 Related Ideas
- [{related_idea_1}]({link_1})
- 

---
*Idea Type: {idea_category}*
*Captured: {date}*
*Status: {status}*""",
                description="Quick idea capture with structured thinking",
                triggers=[ContextTrigger.KEYWORD_MATCH, ContextTrigger.CONTENT_ANALYSIS],
                keywords=["idea", "concept", "innovation", "brainstorm", "thought"],
                time_contexts=["morning", "afternoon", "evening"],
                confidence_score=0.7
            ),
            
            # Personal Development Templates  
            "weekly_review": SmartTemplate(
                id="weekly_review",
                name="📊 Weekly Review",
                type=TemplateType.WEEKLY_REVIEW,
                template_content="""# Week of {week_start} - {week_end}

## 🎯 Goals Review
### ✅ Accomplished
- 
- 

### 🚧 In Progress
- 
- 

### ❌ Missed/Delayed
- 
- 

## 📈 Key Metrics
**Productivity Score:** {productivity_score}/10
**Energy Level:** {energy_level}/10
**Satisfaction:** {satisfaction_score}/10

## 💡 Insights & Learnings
### What Went Well
- 

### What Could Improve
- 

### Key Lessons
- 

## 📅 Next Week Planning
### 🎯 Top 3 Priorities
1. 
2. 
3. 

### 📋 Focus Areas
- **Health & Wellness:** 
- **Work & Career:** 
- **Personal & Relationships:** 

## 🎉 Celebrations & Wins
- 

## 📝 Action Items
- [ ] {action_1}
- [ ] {action_2}

---
*Week: {week_number} of {year}*
*Review Date: {review_date}*""",
                description="Weekly reflection and planning template",
                triggers=[ContextTrigger.TIME_OF_DAY, ContextTrigger.RECURRING_PATTERN],
                keywords=["weekly", "review", "reflection", "planning"],
                time_contexts=["weekend", "evening"],
                confidence_score=0.85
            ),
            
            # Health & Wellness Templates
            "workout_log": SmartTemplate(
                id="workout_log", 
                name="💪 Workout Log",
                type=TemplateType.WORKOUT_LOG,
                template_content="""# Workout - {date}

## 🏋️ Workout Details
**Type:** {workout_type}
**Duration:** {duration} minutes
**Location:** {location}
**Energy Level (Pre):** {pre_energy}/10
**Energy Level (Post):** {post_energy}/10

## 📋 Exercises
### {exercise_1}
- Sets: {sets_1}
- Reps: {reps_1}
- Weight: {weight_1}
- Notes: {notes_1}

### {exercise_2}
- Sets: {sets_2}
- Reps: {reps_2}
- Weight: {weight_2}
- Notes: {notes_2}

## 📊 Performance Notes
**PRs/Improvements:** 
- 

**Form Focus:** 
- 

**Recovery Notes:**
- 

## 📈 Next Workout Plan
- 
- 

---
*Workout #{workout_number}*
*Week: {week_number}*""",
                description="Detailed workout tracking and progression",
                triggers=[ContextTrigger.KEYWORD_MATCH, ContextTrigger.TIME_OF_DAY],
                keywords=["workout", "exercise", "gym", "fitness", "training"],
                time_contexts=["morning", "afternoon"],
                confidence_score=0.75
            )
        }
    
    async def suggest_templates(self, content: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Suggest relevant templates based on content and context"""
        suggestions = []
        
        # Analyze content for template hints
        content_lower = content.lower() if content else ""
        
        # Check each template for relevance
        for template_id, template in self.templates.items():
            relevance_score = self._calculate_relevance_score(
                template, content_lower, context
            )
            
            if relevance_score > 0.3:  # Threshold for suggestions
                suggestions.append({
                    "template_id": template_id,
                    "name": template.name,
                    "type": template.type,
                    "description": template.description,
                    "relevance_score": relevance_score,
                    "confidence": template.confidence_score,
                    "suggested_variables": self._extract_template_variables(template, content, context)
                })
        
        # Sort by relevance score
        suggestions.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        # Limit to top 5 suggestions
        return suggestions[:5]
    
    def _calculate_relevance_score(self, template: SmartTemplate, content: str, context: Dict[str, Any]) -> float:
        """Calculate how relevant a template is based on content and context"""
        score = 0.0
        
        # Keyword matching (40% weight)
        keyword_matches = sum(1 for keyword in template.keywords if keyword in content)
        if template.keywords:
            keyword_score = keyword_matches / len(template.keywords)
            score += keyword_score * 0.4
        
        # Time context matching (20% weight)
        current_hour = datetime.now().hour
        time_context = self._get_time_context(current_hour)
        
        if time_context in template.time_contexts:
            score += 0.2
        
        # Calendar context (20% weight)
        if context.get("has_calendar_event") and ContextTrigger.CALENDAR_EVENT in template.triggers:
            score += 0.2
        
        # Usage patterns (10% weight) 
        if template.usage_count > 0:
            # Boost score for frequently used templates
            usage_boost = min(template.usage_count / 10, 0.1)
            score += usage_boost
        
        # Content analysis (10% weight)
        content_score = self._analyze_content_intent(content, template)
        score += content_score * 0.1
        
        return min(score, 1.0)  # Cap at 1.0
    
    def _get_time_context(self, hour: int) -> str:
        """Get time context from hour"""
        if 6 <= hour < 12:
            return "morning"
        elif 12 <= hour < 18:
            return "afternoon"
        elif 18 <= hour < 22:
            return "evening"
        else:
            return "night"
    
    def _analyze_content_intent(self, content: str, template: SmartTemplate) -> float:
        """Analyze content intent to match with template purpose"""
        intent_signals = {
            TemplateType.MEETING: ["discuss", "agenda", "attendees", "action items"],
            TemplateType.LEARNING_NOTES: ["learn", "understand", "concepts", "study"],
            TemplateType.PROJECT_PLANNING: ["project", "timeline", "deliverable", "plan"],
            TemplateType.IDEA_CAPTURE: ["idea", "concept", "what if", "could we"],
            TemplateType.WEEKLY_REVIEW: ["review", "reflect", "goals", "progress"],
            TemplateType.WORKOUT_LOG: ["workout", "exercise", "reps", "sets"]
        }
        
        signals = intent_signals.get(template.type, [])
        matches = sum(1 for signal in signals if signal in content)
        
        return matches / len(signals) if signals else 0.0
    
    def _extract_template_variables(self, template: SmartTemplate, content: str, context: Dict[str, Any]) -> Dict[str, str]:
        """Extract and suggest values for template variables"""
        variables = {}
        
        # Find all template variables (format: {variable_name})
        var_pattern = r'\{([^}]+)\}'
        template_vars = re.findall(var_pattern, template.template_content)
        
        # Smart variable extraction based on context and content
        for var in template_vars:
            var_lower = var.lower()
            
            # Date/time variables
            if 'date' in var_lower:
                if 'start' in var_lower:
                    variables[var] = (datetime.now()).strftime("%Y-%m-%d")
                else:
                    variables[var] = datetime.now().strftime("%Y-%m-%d")
            
            elif 'time' in var_lower:
                variables[var] = datetime.now().strftime("%H:%M")
            
            # Context-based variables
            elif var_lower == 'meeting_title' and context.get('calendar_event'):
                variables[var] = context['calendar_event'].get('title', 'Team Meeting')
            
            elif var_lower == 'attendees' and context.get('calendar_event'):
                attendees = context['calendar_event'].get('attendees', [])
                variables[var] = '\n- '.join(attendees) if attendees else '- '
            
            # Smart content extraction
            elif var_lower in ['topic', 'title', 'subject']:
                # Try to extract title from content
                lines = content.split('\n')
                first_meaningful_line = next((line.strip() for line in lines if line.strip()), '')
                variables[var] = first_meaningful_line[:50] if first_meaningful_line else f"New {template.type.replace('_', ' ').title()}"
            
            # Default suggestions
            else:
                variables[var] = self._get_default_variable_value(var_lower, context)
        
        return variables
    
    def _get_default_variable_value(self, var_name: str, context: Dict[str, Any]) -> str:
        """Get default values for common template variables"""
        defaults = {
            'priority_level': 'Medium',
            'status': 'In Progress',
            'energy_level': '7',
            'productivity_score': '7',
            'satisfaction_score': '7',
            'duration': '30',
            'location': 'Office',
            'workout_type': 'Strength Training',
            'team_name': 'Development Team',
            'project_type': 'Development'
        }
        
        return defaults.get(var_name, f'[{var_name.replace("_", " ").title()}]')
    
    async def get_template(self, template_id: str, variables: Dict[str, str] = None) -> Dict[str, Any]:
        """Get a template with optional variable substitution"""
        if template_id not in self.templates:
            raise ValueError(f"Template {template_id} not found")
        
        template = self.templates[template_id]
        content = template.template_content
        
        # Apply variable substitution
        if variables:
            for var, value in variables.items():
                content = content.replace(f'{{{var}}}', value)
        
        # Update usage statistics
        template.usage_count += 1
        template.last_used = datetime.now()
        
        # Store usage data in database
        await self._record_template_usage(template_id, variables)
        
        return {
            "id": template_id,
            "name": template.name,
            "type": template.type,
            "content": content,
            "description": template.description,
            "variables_applied": variables or {},
            "usage_count": template.usage_count
        }
    
    async def _record_template_usage(self, template_id: str, variables: Dict[str, str] = None):
        """Record template usage for learning user patterns"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            # Create table if not exists
            c.execute("""
                CREATE TABLE IF NOT EXISTS template_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id TEXT NOT NULL,
                    user_id INTEGER,
                    variables TEXT,
                    timestamp TEXT,
                    context TEXT
                )
            """)
            
            # Record usage
            c.execute("""
                INSERT INTO template_usage (template_id, variables, timestamp)
                VALUES (?, ?, ?)
            """, (
                template_id,
                json.dumps(variables, default=str) if variables else None,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            
            conn.commit()
        finally:
            conn.close()
    
    async def create_custom_template(self, user_id: int, template_data: Dict[str, Any]) -> str:
        """Create a custom template based on user input"""
        template_id = f"custom_{user_id}_{len(self.templates)}"
        
        # AI-powered template generation could go here
        # For now, use the provided template structure
        
        custom_template = SmartTemplate(
            id=template_id,
            name=template_data.get('name', 'Custom Template'),
            type=TemplateType(template_data.get('type', 'idea_capture')),
            template_content=template_data.get('content', '# {title}\n\n{content}'),
            description=template_data.get('description', 'User-created custom template'),
            triggers=[ContextTrigger.USER_PREFERENCE],
            keywords=template_data.get('keywords', []),
            time_contexts=template_data.get('time_contexts', ['morning', 'afternoon', 'evening']),
            confidence_score=0.6,
            ai_generated=template_data.get('ai_generated', False)
        )
        
        self.templates[template_id] = custom_template
        
        # Store in database
        await self._store_custom_template(user_id, custom_template)
        
        return template_id
    
    async def _store_custom_template(self, user_id: int, template: SmartTemplate):
        """Store custom template in database"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            # Create table if not exists
            c.execute("""
                CREATE TABLE IF NOT EXISTS custom_templates (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    description TEXT,
                    keywords TEXT,
                    time_contexts TEXT,
                    created_at TEXT,
                    usage_count INTEGER DEFAULT 0
                )
            """)
            
            # Store template
            c.execute("""
                INSERT OR REPLACE INTO custom_templates 
                (id, user_id, name, type, content, description, keywords, time_contexts, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                template.id,
                user_id,
                template.name,
                template.type,
                template.template_content,
                template.description,
                json.dumps(template.keywords),
                json.dumps(template.time_contexts),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            
            conn.commit()
        finally:
            conn.close()
    
    async def get_template_analytics(self, user_id: int = None) -> Dict[str, Any]:
        """Get analytics on template usage patterns"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            # Overall usage statistics
            query = """
                SELECT template_id, COUNT(*) as usage_count, MAX(timestamp) as last_used
                FROM template_usage
                {} 
                GROUP BY template_id
                ORDER BY usage_count DESC
            """
            
            user_filter = "WHERE user_id = ?" if user_id else ""
            params = (user_id,) if user_id else ()
            
            rows = c.execute(query.format(user_filter), params).fetchall()
            
            template_stats = {}
            for row in rows:
                template_id = row[0]
                if template_id in self.templates:
                    template_stats[template_id] = {
                        "name": self.templates[template_id].name,
                        "usage_count": row[1],
                        "last_used": row[2],
                        "type": self.templates[template_id].type
                    }
            
            # Time-based usage patterns
            time_query = """
                SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
                FROM template_usage
                {}
                GROUP BY hour
                ORDER BY hour
            """
            
            time_rows = c.execute(time_query.format(user_filter), params).fetchall()
            time_patterns = {row[0]: row[1] for row in time_rows}
            
            return {
                "total_templates": len(self.templates),
                "custom_templates": len([t for t in self.templates.values() if t.ai_generated or 'custom' in t.id]),
                "most_used_templates": template_stats,
                "usage_by_hour": time_patterns,
                "total_usages": sum(stats["usage_count"] for stats in template_stats.values())
            }
            
        finally:
            conn.close()
    
    def get_template_library(self) -> Dict[str, Any]:
        """Get the complete template library"""
        return {
            "templates": {
                template_id: {
                    "name": template.name,
                    "type": template.type,
                    "description": template.description,
                    "keywords": template.keywords,
                    "time_contexts": template.time_contexts,
                    "usage_count": template.usage_count,
                    "confidence": template.confidence_score
                }
                for template_id, template in self.templates.items()
            },
            "template_types": [t.value for t in TemplateType],
            "context_triggers": [t.value for t in ContextTrigger],
            "total_templates": len(self.templates)
        }