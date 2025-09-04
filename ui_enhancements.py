#!/usr/bin/env python3
"""
UI Enhancement Functions for Automated Relationship Discovery
Adds similar notes and cluster suggestions to templates
"""

import sqlite3
from typing import Dict, List, Any
import logging
import json

logger = logging.getLogger(__name__)

class UIRelationshipEnhancer:
    """Enhances UI with automated relationship suggestions"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._relationship_engine = None
    
    def _get_relationship_engine(self):
        """Lazy load relationship engine"""
        if self._relationship_engine is None:
            try:
                from note_relationships import NoteRelationshipEngine
                self._relationship_engine = NoteRelationshipEngine(self.db_path)
            except ImportError:
                logger.warning("Relationship engine not available for UI")
                return None
        return self._relationship_engine
    
    def get_similar_notes_widget(self, note_id: int, user_id: int, 
                                limit: int = 3) -> Dict[str, Any]:
        """Get similar notes widget data for UI"""
        relationship_engine = self._get_relationship_engine()
        if not relationship_engine:
            return {"enabled": False, "notes": []}
        
        try:
            similar_notes = relationship_engine.find_similar_notes(
                note_id, user_id, limit=limit, min_similarity=0.25
            )
            
            # Convert to UI format
            notes_data = []
            for note in similar_notes:
                notes_data.append({
                    "id": note.note_id,
                    "title": note.title,
                    "snippet": note.snippet,
                    "similarity": f"{note.similarity_score:.1%}",
                    "relationship_type": note.relationship_type,
                    "tags": note.tags[:3],  # Show only first 3 tags
                    "timestamp": note.timestamp[:10] if note.timestamp else ""  # YYYY-MM-DD
                })
            
            return {
                "enabled": True,
                "notes": notes_data,
                "total_found": len(similar_notes)
            }
            
        except Exception as e:
            logger.error(f"Failed to get similar notes widget: {e}")
            return {"enabled": False, "notes": [], "error": str(e)}
    
    def get_cluster_suggestions_widget(self, user_id: int, 
                                     limit: int = 3) -> Dict[str, Any]:
        """Get cluster suggestions widget for dashboard"""
        relationship_engine = self._get_relationship_engine()
        if not relationship_engine:
            return {"enabled": False, "clusters": []}
        
        try:
            clusters = relationship_engine.get_note_clusters(user_id)
            
            # Sort by avg similarity and take top clusters
            clusters.sort(key=lambda x: x.get('avg_similarity', 0), reverse=True)
            top_clusters = clusters[:limit]
            
            # Format for UI
            clusters_data = []
            for cluster in top_clusters:
                clusters_data.append({
                    "id": cluster['cluster_id'],
                    "theme": cluster['theme'],
                    "note_count": cluster['note_count'],
                    "similarity": f"{cluster.get('avg_similarity', 0):.1%}",
                    "representative_note_id": cluster.get('representative_note_id'),
                    "preview_note_ids": cluster.get('note_ids', [])[:4]  # Show first 4 notes
                })
            
            return {
                "enabled": True,
                "clusters": clusters_data,
                "total_clusters": len(clusters)
            }
            
        except Exception as e:
            logger.error(f"Failed to get cluster suggestions: {e}")
            return {"enabled": False, "clusters": [], "error": str(e)}
    
    def get_relationship_stats_widget(self, user_id: int) -> Dict[str, Any]:
        """Get relationship statistics for dashboard"""
        relationship_engine = self._get_relationship_engine()
        if not relationship_engine:
            return {"enabled": False}
        
        try:
            stats = relationship_engine.get_relationship_stats(user_id)
            
            return {
                "enabled": True,
                "stats": {
                    "total_notes": stats.get('total_notes', 0),
                    "connected_notes": stats.get('notes_with_relationships', 0),
                    "coverage_percent": stats.get('relationship_coverage', 0),
                    "cluster_count": stats.get('cluster_count', 0)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get relationship stats: {e}")
            return {"enabled": False, "error": str(e)}
    
    def get_automation_status_widget(self, user_id: int) -> Dict[str, Any]:
        """Get automation status for user dashboard"""
        try:
            from automated_relationships import get_automation_engine
            automation_engine = get_automation_engine(self.db_path)
            status = automation_engine.get_automation_status(user_id)
            
            # Format for UI display
            return {
                "enabled": True,
                "automation_active": status.get("automation_enabled", False),
                "recent_jobs": {
                    "completed": status.get("recent_jobs", {}).get("completed", 0),
                    "pending": status.get("recent_jobs", {}).get("pending", 0),
                    "failed": status.get("recent_jobs", {}).get("failed", 0)
                },
                "metrics": status.get("metrics", {}),
                "adaptive_threshold": f"{status.get('adaptive_threshold', 0.3):.2f}"
            }
            
        except ImportError:
            return {"enabled": False, "message": "Automation not available"}
        except Exception as e:
            logger.error(f"Failed to get automation status: {e}")
            return {"enabled": False, "error": str(e)}
    
    def inject_similar_notes_into_detail(self, note_data: Dict, user_id: int) -> Dict:
        """Inject similar notes data into note detail view"""
        note_id = note_data.get('id')
        if not note_id:
            return note_data
        
        similar_widget = self.get_similar_notes_widget(note_id, user_id, limit=5)
        note_data['similar_notes'] = similar_widget
        
        return note_data
    
    def inject_dashboard_widgets(self, dashboard_data: Dict, user_id: int) -> Dict:
        """Inject relationship widgets into dashboard data"""
        
        # Add cluster suggestions
        dashboard_data['cluster_suggestions'] = self.get_cluster_suggestions_widget(user_id)
        
        # Add relationship stats
        dashboard_data['relationship_stats'] = self.get_relationship_stats_widget(user_id)
        
        # Add automation status
        dashboard_data['automation_status'] = self.get_automation_status_widget(user_id)
        
        return dashboard_data
    
    def get_smart_tags_suggestions(self, user_id: int, current_content: str = "", 
                                 limit: int = 5) -> List[str]:
        """Get smart tag suggestions based on similar notes"""
        if not current_content:
            return []
        
        try:
            # Use semantic search to find similar content
            from services.search_adapter import SearchService
            search_engine = SearchService()
            
            # Search for similar content
            results = search_engine.semantic_search(
                current_content[:500], user_id, limit=10, similarity_threshold=0.2
            )
            
            # Collect tags from similar notes
            tag_counts = {}
            for result in results:
                for tag in result.tags:
                    if tag.strip():
                        tag_counts[tag.strip()] = tag_counts.get(tag.strip(), 0) + 1
            
            # Sort by frequency and return top suggestions
            suggested_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
            return [tag for tag, count in suggested_tags[:limit] if count >= 2]
            
        except Exception as e:
            logger.error(f"Failed to get smart tag suggestions: {e}")
            return []


def create_template_filters(db_path: str):
    """Create Jinja2 template filters for UI enhancements"""
    enhancer = UIRelationshipEnhancer(db_path)
    
    def similar_notes_filter(note_data, user_id, limit=3):
        """Jinja2 filter to get similar notes"""
        if isinstance(note_data, dict) and 'id' in note_data:
            return enhancer.get_similar_notes_widget(note_data['id'], user_id, limit)
        return {"enabled": False, "notes": []}
    
    def cluster_suggestions_filter(user_id, limit=3):
        """Jinja2 filter to get cluster suggestions"""
        return enhancer.get_cluster_suggestions_widget(user_id, limit)
    
    def relationship_stats_filter(user_id):
        """Jinja2 filter to get relationship stats"""
        return enhancer.get_relationship_stats_widget(user_id)
    
    def smart_tags_filter(user_id, content="", limit=5):
        """Jinja2 filter to get smart tag suggestions"""
        return enhancer.get_smart_tags_suggestions(user_id, content, limit)
    
    return {
        'similar_notes': similar_notes_filter,
        'cluster_suggestions': cluster_suggestions_filter,
        'relationship_stats': relationship_stats_filter,
        'smart_tags': smart_tags_filter
    }


# Template enhancement functions for direct injection
def enhance_detail_template_context(note_data: Dict, user_id: int, db_path: str) -> Dict:
    """Enhance detail template context with relationship data"""
    enhancer = UIRelationshipEnhancer(db_path)
    return enhancer.inject_similar_notes_into_detail(note_data, user_id)

def enhance_dashboard_template_context(dashboard_data: Dict, user_id: int, db_path: str) -> Dict:
    """Enhance dashboard template context with relationship widgets"""
    enhancer = UIRelationshipEnhancer(db_path)
    return enhancer.inject_dashboard_widgets(dashboard_data, user_id)

def get_ui_enhancer(db_path: str) -> UIRelationshipEnhancer:
    """Get UI enhancer instance"""
    return UIRelationshipEnhancer(db_path)
