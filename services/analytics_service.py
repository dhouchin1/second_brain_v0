"""
Analytics Service

Handles analytics and reporting functionality.
Extracted from app.py to provide clean separation of analytics concerns.
"""

from typing import Dict, List
from services.auth_service import User


class AnalyticsService:
    """Service for handling analytics operations."""
    
    def __init__(self, get_conn_func):
        """Initialize analytics service with database connection function."""
        self.get_conn = get_conn_func
    
    def get_user_analytics(self, current_user: User) -> Dict:
        """Get user analytics and insights."""
        conn = self.get_conn()
        c = conn.cursor()
        
        # Basic stats
        total_notes = c.execute(
            "SELECT COUNT(*) as count FROM notes WHERE user_id = ?",
            (current_user.id,)
        ).fetchone()["count"]
        
        # This week
        this_week = c.execute(
            "SELECT COUNT(*) as count FROM notes WHERE user_id = ? AND date(timestamp) >= date('now', '-7 days')",
            (current_user.id,)
        ).fetchone()["count"]
        
        # By type
        by_type = c.execute(
            "SELECT type, COUNT(*) as count FROM notes WHERE user_id = ? GROUP BY type",
            (current_user.id,)
        ).fetchall()
        
        # Popular tags
        tag_counts = {}
        tag_rows = c.execute(
            "SELECT tags FROM notes WHERE user_id = ? AND tags IS NOT NULL",
            (current_user.id,)
        ).fetchall()
        
        for row in tag_rows:
            tags = row["tags"].split(",")
            for tag in tags:
                tag = tag.strip()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        popular_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        conn.close()
        
        return {
            "total_notes": total_notes,
            "this_week": this_week,
            "by_type": [{"type": row["type"], "count": row["count"]} for row in by_type],
            "popular_tags": [{"name": tag, "count": count} for tag, count in popular_tags]
        }