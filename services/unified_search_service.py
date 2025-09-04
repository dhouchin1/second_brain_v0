"""
Unified Search Service

Combines traditional note search with Smart Templates suggestions to provide
a comprehensive search experience that includes both existing content and
intelligent template recommendations.
"""

import json
import time
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from services.search_adapter import SearchService
from services.smart_templates_service import SmartTemplatesService


class UnifiedResultType(str, Enum):
    """Types of unified search results"""
    NOTE = "note"
    TEMPLATE = "template"
    SUGGESTION = "suggestion"
    QUICK_ACTION = "quick_action"


class SearchIntent(str, Enum):
    """Search intent categories for enhanced results"""
    FIND_EXISTING = "find_existing"
    CREATE_NEW = "create_new"
    EXPLORE = "explore"
    REFERENCE = "reference"


@dataclass
class UnifiedSearchResult:
    """Unified search result combining notes and templates"""
    id: str
    type: UnifiedResultType
    title: str
    content: str
    description: str
    relevance_score: float
    source: str
    metadata: Dict[str, Any]
    quick_actions: List[Dict[str, str]] = None
    template_variables: Dict[str, str] = None


class UnifiedSearchService:
    """
    Service that provides unified search across notes and templates
    """
    
    def __init__(self, get_conn_func, db_path: str = None, vec_ext_path: str = None):
        self.get_conn = get_conn_func
        
        # Initialize search services
        self.search_service = SearchService(db_path=db_path, vec_ext_path=vec_ext_path)
        self.templates_service = SmartTemplatesService(get_conn_func)
        
        # Cache for recent searches and suggestions
        self._suggestion_cache = {}
        self._cache_timestamps = {}
        self._cache_ttl = 300  # 5 minutes
    
    async def unified_search(
        self, 
        query: str, 
        user_id: int,
        search_mode: str = "hybrid",
        limit: int = 20,
        include_templates: bool = True,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Perform unified search combining notes and template suggestions
        
        Args:
            query: Search query string
            user_id: User ID for personalized results
            search_mode: Search mode (hybrid, semantic, keyword)
            limit: Maximum number of results
            include_templates: Whether to include template suggestions
            context: Additional context for search enhancement
            
        Returns:
            Unified search results with notes, templates, and suggestions
        """
        start_time = time.time()
        context = context or {}
        context["user_id"] = user_id
        
        # Detect search intent
        intent = self._detect_search_intent(query)
        
        # Perform note search
        notes_results = await self._search_notes(query, search_mode, limit)
        
        # Get template suggestions if enabled
        template_suggestions = []
        if include_templates:
            template_suggestions = await self._get_template_suggestions(
                query, context, intent
            )
        
        # Generate quick actions based on intent
        quick_actions = await self._generate_quick_actions(query, intent, context)
        
        # Combine and rank results
        unified_results = self._combine_and_rank_results(
            notes_results, template_suggestions, quick_actions, query
        )
        
        # Apply final limit
        final_results = unified_results[:limit]
        
        # Generate search analytics
        analytics = {
            "search_time": time.time() - start_time,
            "notes_found": len(notes_results),
            "templates_suggested": len(template_suggestions),
            "quick_actions": len(quick_actions),
            "total_results": len(final_results),
            "search_intent": intent.value,
            "search_mode": search_mode
        }
        
        # Store search history for learning
        await self._record_search_history(user_id, query, intent, analytics)
        
        return {
            "results": [self._result_to_dict(r) for r in final_results],
            "analytics": analytics,
            "intent": intent.value,
            "suggestions": await self._get_search_suggestions(query, user_id),
            "query_enhancements": await self._get_query_enhancements(query, context),
            "total": len(final_results),
            "has_more": len(unified_results) > limit
        }
    
    async def _search_notes(self, query: str, mode: str, limit: int) -> List[UnifiedSearchResult]:
        """Search existing notes using the search adapter"""
        try:
            # Use existing search service
            search_results = self.search_service.search(query, mode=mode, k=limit)
            
            unified_results = []
            for result in search_results:
                # Convert search result to unified format
                unified_result = UnifiedSearchResult(
                    id=f"note_{result.get('id', 'unknown')}",
                    type=UnifiedResultType.NOTE,
                    title=result.get('title', 'Untitled Note'),
                    content=result.get('content', '')[:300] + "..." if result.get('content', '') else '',
                    description=result.get('summary', '')[:150] + "..." if result.get('summary', '') else '',
                    relevance_score=result.get('score', 0.0),
                    source="notes",
                    metadata={
                        "note_id": result.get('id'),
                        "created_at": result.get('created_at'),
                        "modified_at": result.get('modified_at'),
                        "tags": result.get('tags', '').split(',') if result.get('tags') else [],
                        "type": result.get('type', 'text'),
                        "file_path": result.get('file_path')
                    },
                    quick_actions=[
                        {"action": "open", "label": "Open Note", "icon": "📖"},
                        {"action": "edit", "label": "Edit", "icon": "✏️"},
                        {"action": "share", "label": "Share", "icon": "🔗"}
                    ]
                )
                unified_results.append(unified_result)
            
            return unified_results
            
        except Exception as e:
            print(f"Error searching notes: {e}")
            return []
    
    async def _get_template_suggestions(
        self, 
        query: str, 
        context: Dict[str, Any], 
        intent: SearchIntent
    ) -> List[UnifiedSearchResult]:
        """Get relevant template suggestions"""
        try:
            # Enhance context with intent
            enhanced_context = context.copy()
            enhanced_context["search_intent"] = intent.value
            enhanced_context["current_time"] = datetime.now().isoformat()
            
            # Get template suggestions from smart templates service
            template_suggestions = await self.templates_service.suggest_templates(
                query, enhanced_context
            )
            
            unified_results = []
            for suggestion in template_suggestions:
                template_id = suggestion["template_id"]
                
                unified_result = UnifiedSearchResult(
                    id=f"template_{template_id}",
                    type=UnifiedResultType.TEMPLATE,
                    title=suggestion["name"],
                    content=suggestion["description"],
                    description=f"Smart template for {suggestion['type']} - {suggestion['description']}",
                    relevance_score=suggestion["relevance_score"],
                    source="smart_templates",
                    metadata={
                        "template_id": template_id,
                        "template_type": suggestion["type"],
                        "confidence": suggestion["confidence"],
                        "suggested_variables": suggestion.get("suggested_variables", {})
                    },
                    template_variables=suggestion.get("suggested_variables", {}),
                    quick_actions=[
                        {"action": "apply_template", "label": "Use Template", "icon": "✨"},
                        {"action": "preview_template", "label": "Preview", "icon": "👁️"},
                        {"action": "customize_template", "label": "Customize", "icon": "⚙️"}
                    ]
                )
                unified_results.append(unified_result)
            
            return unified_results
            
        except Exception as e:
            print(f"Error getting template suggestions: {e}")
            return []
    
    async def _generate_quick_actions(
        self, 
        query: str, 
        intent: SearchIntent, 
        context: Dict[str, Any]
    ) -> List[UnifiedSearchResult]:
        """Generate contextual quick actions based on search intent"""
        quick_actions = []
        
        try:
            # Create new note action
            if intent in [SearchIntent.CREATE_NEW, SearchIntent.FIND_EXISTING]:
                quick_actions.append(UnifiedSearchResult(
                    id="action_create_note",
                    type=UnifiedResultType.QUICK_ACTION,
                    title=f'Create Note: "{query}"',
                    content=f"Start a new note with the title '{query}'",
                    description="Quickly create a new note with your search term as the title",
                    relevance_score=0.8,
                    source="quick_actions",
                    metadata={"action_type": "create_note", "suggested_title": query},
                    quick_actions=[
                        {"action": "create_note", "label": "Create Now", "icon": "➕"}
                    ]
                ))
            
            # Search web action
            if intent in [SearchIntent.EXPLORE, SearchIntent.REFERENCE]:
                quick_actions.append(UnifiedSearchResult(
                    id="action_web_search",
                    type=UnifiedResultType.QUICK_ACTION,
                    title=f'Search Web: "{query}"',
                    content=f"Search the web for '{query}' and capture results",
                    description="Search online and optionally save findings to your knowledge base",
                    relevance_score=0.7,
                    source="quick_actions",
                    metadata={"action_type": "web_search", "search_query": query},
                    quick_actions=[
                        {"action": "web_search", "label": "Search Web", "icon": "🌐"}
                    ]
                ))
            
            # AI assistance action
            if len(query) > 10:  # Only for substantial queries
                quick_actions.append(UnifiedSearchResult(
                    id="action_ai_assist",
                    type=UnifiedResultType.QUICK_ACTION,
                    title=f'Ask AI: "{query}"',
                    content=f"Get AI assistance or insights about '{query}'",
                    description="Use AI to analyze, summarize, or provide insights on your query",
                    relevance_score=0.6,
                    source="quick_actions",
                    metadata={"action_type": "ai_assist", "prompt": query},
                    quick_actions=[
                        {"action": "ai_assist", "label": "Ask AI", "icon": "🤖"}
                    ]
                ))
            
        except Exception as e:
            print(f"Error generating quick actions: {e}")
        
        return quick_actions
    
    def _detect_search_intent(self, query: str) -> SearchIntent:
        """Detect user intent from search query"""
        query_lower = query.lower().strip()
        
        # Keywords that suggest creating new content
        create_keywords = ["new", "create", "start", "begin", "make", "write", "draft"]
        if any(keyword in query_lower for keyword in create_keywords):
            return SearchIntent.CREATE_NEW
        
        # Keywords that suggest exploration
        explore_keywords = ["explore", "learn about", "understand", "research", "study"]
        if any(keyword in query_lower for keyword in explore_keywords):
            return SearchIntent.EXPLORE
        
        # Keywords that suggest finding references
        reference_keywords = ["reference", "documentation", "guide", "example", "template"]
        if any(keyword in query_lower for keyword in reference_keywords):
            return SearchIntent.REFERENCE
        
        # Default to finding existing content
        return SearchIntent.FIND_EXISTING
    
    def _combine_and_rank_results(
        self,
        notes: List[UnifiedSearchResult],
        templates: List[UnifiedSearchResult],
        actions: List[UnifiedSearchResult],
        query: str
    ) -> List[UnifiedSearchResult]:
        """Combine and intelligently rank all results"""
        all_results = []
        
        # Add all results with source-specific boosts
        for result in notes:
            # Boost highly relevant notes
            if result.relevance_score > 0.8:
                result.relevance_score *= 1.2
            all_results.append(result)
        
        for result in templates:
            # Templates get moderate boost for creation intent
            result.relevance_score *= 1.1
            all_results.append(result)
        
        for result in actions:
            # Actions get positioned based on intent appropriateness
            all_results.append(result)
        
        # Sort by relevance score (descending)
        all_results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # Ensure diversity in top results
        return self._ensure_result_diversity(all_results)
    
    def _ensure_result_diversity(
        self, 
        results: List[UnifiedSearchResult]
    ) -> List[UnifiedSearchResult]:
        """Ensure diverse result types in top positions"""
        if len(results) <= 5:
            return results
        
        # Group by type
        by_type = {}
        for result in results:
            if result.type not in by_type:
                by_type[result.type] = []
            by_type[result.type].append(result)
        
        # Interleave results to ensure diversity
        diverse_results = []
        max_length = max(len(group) for group in by_type.values())
        
        for i in range(max_length):
            for result_type in [UnifiedResultType.NOTE, UnifiedResultType.TEMPLATE, 
                              UnifiedResultType.QUICK_ACTION, UnifiedResultType.SUGGESTION]:
                if result_type in by_type and i < len(by_type[result_type]):
                    diverse_results.append(by_type[result_type][i])
        
        return diverse_results
    
    def _result_to_dict(self, result: UnifiedSearchResult) -> Dict[str, Any]:
        """Convert UnifiedSearchResult to dictionary for JSON serialization"""
        return {
            "id": result.id,
            "type": result.type.value,
            "title": result.title,
            "content": result.content,
            "description": result.description,
            "relevance_score": result.relevance_score,
            "source": result.source,
            "metadata": result.metadata,
            "quick_actions": result.quick_actions or [],
            "template_variables": result.template_variables or {}
        }
    
    async def _get_search_suggestions(self, query: str, user_id: int) -> List[Dict[str, Any]]:
        """Get real-time search suggestions"""
        cache_key = f"suggestions_{user_id}_{query.lower()}"
        
        # Check cache
        if (cache_key in self._suggestion_cache and 
            time.time() - self._cache_timestamps.get(cache_key, 0) < self._cache_ttl):
            return self._suggestion_cache[cache_key]
        
        suggestions = []
        
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            # Recent similar searches
            similar_searches = c.execute(
                """SELECT DISTINCT query FROM search_history 
                   WHERE user_id = ? AND query LIKE ? 
                   ORDER BY created_at DESC LIMIT 3""",
                (user_id, f"%{query}%")
            ).fetchall()
            
            suggestions.extend([
                {"text": row["query"], "type": "recent", "icon": "🕐"} 
                for row in similar_searches
            ])
            
            # Template-based suggestions
            template_keywords = [
                "meeting", "standup", "project", "learning", "idea", 
                "weekly review", "workout", "decision"
            ]
            
            for keyword in template_keywords:
                if keyword in query.lower():
                    suggestions.append({
                        "text": f"Create {keyword} template",
                        "type": "template_action",
                        "icon": "✨"
                    })
            
            conn.close()
            
        except Exception as e:
            print(f"Error getting suggestions: {e}")
        
        # Cache results
        self._suggestion_cache[cache_key] = suggestions
        self._cache_timestamps[cache_key] = time.time()
        
        return suggestions[:8]  # Limit to 8 suggestions
    
    async def _get_query_enhancements(
        self, 
        query: str, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get query enhancement suggestions"""
        enhancements = {
            "alternative_queries": [],
            "suggested_filters": [],
            "expansion_terms": []
        }
        
        try:
            # Basic query analysis
            words = query.split()
            if len(words) > 1:
                # Suggest individual word searches
                enhancements["alternative_queries"] = [
                    f'"{word}"' for word in words if len(word) > 3
                ][:3]
            
            # Suggest common filters based on query content
            if any(word in query.lower() for word in ["meeting", "call", "discussion"]):
                enhancements["suggested_filters"].append("type:meeting")
            
            if any(word in query.lower() for word in ["project", "plan", "task"]):
                enhancements["suggested_filters"].append("type:project")
            
            # Expansion terms
            enhancements["expansion_terms"] = words[:3]
            
        except Exception as e:
            print(f"Error getting query enhancements: {e}")
        
        return enhancements
    
    async def _record_search_history(
        self, 
        user_id: int, 
        query: str, 
        intent: SearchIntent, 
        analytics: Dict[str, Any]
    ):
        """Record search for analytics and learning"""
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            # Create table if not exists
            c.execute("""
                CREATE TABLE IF NOT EXISTS unified_search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    query TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    search_mode TEXT,
                    results_count INTEGER,
                    search_time REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert search record
            c.execute("""
                INSERT INTO unified_search_history 
                (user_id, query, intent, search_mode, results_count, search_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                query,
                intent.value,
                analytics.get("search_mode", "hybrid"),
                analytics.get("total_results", 0),
                analytics.get("search_time", 0)
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error recording search history: {e}")
    
    async def get_search_analytics(self, user_id: int = None) -> Dict[str, Any]:
        """Get search analytics and usage patterns"""
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            # Overall statistics
            if user_id:
                stats = c.execute("""
                    SELECT 
                        COUNT(*) as total_searches,
                        AVG(search_time) as avg_search_time,
                        AVG(results_count) as avg_results,
                        COUNT(DISTINCT query) as unique_queries
                    FROM unified_search_history 
                    WHERE user_id = ?
                """, (user_id,)).fetchone()
            else:
                stats = c.execute("""
                    SELECT 
                        COUNT(*) as total_searches,
                        AVG(search_time) as avg_search_time,
                        AVG(results_count) as avg_results,
                        COUNT(DISTINCT query) as unique_queries
                    FROM unified_search_history
                """).fetchone()
            
            # Intent distribution
            intent_query = """
                SELECT intent, COUNT(*) as count 
                FROM unified_search_history {}
                GROUP BY intent
                ORDER BY count DESC
            """
            user_filter = "WHERE user_id = ?" if user_id else ""
            params = (user_id,) if user_id else ()
            
            intent_stats = c.execute(intent_query.format(user_filter), params).fetchall()
            
            conn.close()
            
            return {
                "total_searches": stats["total_searches"] if stats else 0,
                "avg_search_time": round(stats["avg_search_time"] or 0, 3),
                "avg_results": round(stats["avg_results"] or 0, 1),
                "unique_queries": stats["unique_queries"] if stats else 0,
                "intent_distribution": {
                    row["intent"]: row["count"] for row in intent_stats
                }
            }
            
        except Exception as e:
            print(f"Error getting search analytics: {e}")
            return {}


print("[Unified Search Service] Loaded successfully")