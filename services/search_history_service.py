"""
Search History & Saved Searches Service

Provides search tracking, history management, and saved search functionality
to enhance user search experience and provide analytics insights.
"""

import json
import sqlite3
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

@dataclass
class SearchHistoryEntry:
    id: int
    user_id: int
    query: str
    search_mode: str
    results_count: int
    response_time_ms: int
    created_at: datetime

@dataclass 
class SavedSearch:
    id: int
    user_id: int
    name: str
    query: str
    search_mode: str
    filters: Dict[str, Any]
    is_favorite: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime

class SearchHistoryService:
    def __init__(self, get_conn: Callable[[], sqlite3.Connection]):
        self.get_conn = get_conn
        
    def record_search(self, user_id: int, query: str, search_mode: str, 
                     results_count: int, response_time_ms: int) -> int:
        """Record a search in history for analytics and quick access"""
        if not query.strip():
            return 0
            
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO search_history (user_id, query, search_mode, results_count, response_time_ms)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, query.strip(), search_mode, results_count, response_time_ms))
        
        search_id = cursor.lastrowid
        conn.commit()
        
        # Update daily analytics
        self._update_daily_analytics(user_id, query, search_mode, response_time_ms)
        
        # Cleanup old history (keep last 1000 searches per user)
        self._cleanup_old_history(user_id)
        
        return search_id
    
    def get_search_history(self, user_id: int, limit: int = 20) -> List[SearchHistoryEntry]:
        """Get recent search history for a user"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, user_id, query, search_mode, results_count, response_time_ms, created_at
            FROM search_history 
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))
        
        rows = cursor.fetchall()
        return [
            SearchHistoryEntry(
                id=row[0],
                user_id=row[1], 
                query=row[2],
                search_mode=row[3],
                results_count=row[4],
                response_time_ms=row[5],
                created_at=datetime.fromisoformat(row[6])
            )
            for row in rows
        ]
    
    def get_popular_searches(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most frequently searched queries for quick access"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT query, search_mode, COUNT(*) as search_count,
                   AVG(results_count) as avg_results,
                   MAX(created_at) as last_searched
            FROM search_history 
            WHERE user_id = ?
              AND created_at >= datetime('now', '-30 days')
            GROUP BY query, search_mode
            HAVING search_count > 1
            ORDER BY search_count DESC, last_searched DESC
            LIMIT ?
        """, (user_id, limit))
        
        rows = cursor.fetchall()
        return [
            {
                "query": row[0],
                "search_mode": row[1], 
                "search_count": row[2],
                "avg_results": int(row[3]),
                "last_searched": row[4]
            }
            for row in rows
        ]
    
    def save_search(self, user_id: int, name: str, query: str, search_mode: str = 'hybrid',
                   filters: Dict[str, Any] = None, is_favorite: bool = False) -> int:
        """Save a search for quick access later"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        filters_json = json.dumps(filters or {})
        
        try:
            cursor.execute("""
                INSERT INTO saved_searches (user_id, name, query, search_mode, filters, is_favorite)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, name, query, search_mode, filters_json, is_favorite))
            
            saved_search_id = cursor.lastrowid
            conn.commit()
            return saved_search_id
            
        except sqlite3.IntegrityError:
            # Name already exists for this user
            raise ValueError(f"Saved search '{name}' already exists")
    
    def get_saved_searches(self, user_id: int) -> List[SavedSearch]:
        """Get all saved searches for a user"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, user_id, name, query, search_mode, filters, is_favorite,
                   created_at, updated_at, last_used_at
            FROM saved_searches
            WHERE user_id = ?
            ORDER BY is_favorite DESC, last_used_at DESC
        """, (user_id,))
        
        rows = cursor.fetchall()
        return [
            SavedSearch(
                id=row[0],
                user_id=row[1],
                name=row[2],
                query=row[3], 
                search_mode=row[4],
                filters=json.loads(row[5]),
                is_favorite=bool(row[6]),
                created_at=datetime.fromisoformat(row[7]),
                updated_at=datetime.fromisoformat(row[8]),
                last_used_at=datetime.fromisoformat(row[9])
            )
            for row in rows
        ]
    
    def use_saved_search(self, user_id: int, saved_search_id: int) -> Optional[SavedSearch]:
        """Mark a saved search as used and return its details"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # Update last_used_at
        cursor.execute("""
            UPDATE saved_searches 
            SET last_used_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        """, (saved_search_id, user_id))
        
        if cursor.rowcount == 0:
            return None
            
        conn.commit()
        
        # Return the saved search details
        cursor.execute("""
            SELECT id, user_id, name, query, search_mode, filters, is_favorite,
                   created_at, updated_at, last_used_at
            FROM saved_searches
            WHERE id = ? AND user_id = ?
        """, (saved_search_id, user_id))
        
        row = cursor.fetchone()
        if not row:
            return None
            
        return SavedSearch(
            id=row[0],
            user_id=row[1],
            name=row[2],
            query=row[3],
            search_mode=row[4], 
            filters=json.loads(row[5]),
            is_favorite=bool(row[6]),
            created_at=datetime.fromisoformat(row[7]),
            updated_at=datetime.fromisoformat(row[8]),
            last_used_at=datetime.fromisoformat(row[9])
        )
    
    def delete_saved_search(self, user_id: int, saved_search_id: int) -> bool:
        """Delete a saved search"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM saved_searches
            WHERE id = ? AND user_id = ?
        """, (saved_search_id, user_id))
        
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    
    def toggle_favorite(self, user_id: int, saved_search_id: int) -> bool:
        """Toggle favorite status of a saved search"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE saved_searches 
            SET is_favorite = NOT is_favorite
            WHERE id = ? AND user_id = ?
        """, (saved_search_id, user_id))
        
        updated = cursor.rowcount > 0
        conn.commit()
        return updated
    
    def get_search_analytics(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get search analytics for a user"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # Basic stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_searches,
                COUNT(DISTINCT query) as unique_queries,
                AVG(response_time_ms) as avg_response_time,
                AVG(results_count) as avg_results_count
            FROM search_history
            WHERE user_id = ? AND created_at >= datetime('now', '-{} days')
        """.format(days), (user_id,))
        
        basic_stats = cursor.fetchone()
        
        # Search mode breakdown
        cursor.execute("""
            SELECT search_mode, COUNT(*) as count
            FROM search_history
            WHERE user_id = ? AND created_at >= datetime('now', '-{} days')
            GROUP BY search_mode
        """.format(days), (user_id,))
        
        mode_breakdown = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Daily search volume
        cursor.execute("""
            SELECT DATE(created_at) as search_date, COUNT(*) as daily_searches
            FROM search_history
            WHERE user_id = ? AND created_at >= datetime('now', '-{} days')
            GROUP BY DATE(created_at)
            ORDER BY search_date DESC
        """.format(days), (user_id,))
        
        daily_volume = [{"date": row[0], "searches": row[1]} for row in cursor.fetchall()]
        
        return {
            "total_searches": basic_stats[0] or 0,
            "unique_queries": basic_stats[1] or 0,
            "avg_response_time_ms": int(basic_stats[2] or 0),
            "avg_results_count": int(basic_stats[3] or 0),
            "search_mode_breakdown": mode_breakdown,
            "daily_volume": daily_volume,
            "period_days": days
        }
    
    def _update_daily_analytics(self, user_id: int, query: str, search_mode: str, response_time_ms: int):
        """Update daily search analytics"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        today = date.today().isoformat()
        
        cursor.execute("""
            INSERT INTO search_analytics (user_id, date, total_searches, avg_response_time_ms, 
                                        most_common_query, search_mode_breakdown)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                total_searches = total_searches + 1,
                avg_response_time_ms = (avg_response_time_ms * (total_searches - 1) + ?) / total_searches,
                search_mode_breakdown = CASE
                    WHEN json_extract(search_mode_breakdown, '$.' || ?) IS NULL 
                    THEN json_set(search_mode_breakdown, '$.' || ?, 1)
                    ELSE json_set(search_mode_breakdown, '$.' || ?, json_extract(search_mode_breakdown, '$.' || ?) + 1)
                END
        """, (user_id, today, response_time_ms, query, json.dumps({search_mode: 1}), 
              response_time_ms, search_mode, search_mode, search_mode, search_mode))
        
        conn.commit()
    
    def _cleanup_old_history(self, user_id: int, keep_last: int = 1000):
        """Keep only the most recent search history entries"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM search_history 
            WHERE user_id = ? AND id NOT IN (
                SELECT id FROM search_history 
                WHERE user_id = ?
                ORDER BY created_at DESC 
                LIMIT ?
            )
        """, (user_id, user_id, keep_last))
        
        if cursor.rowcount > 0:
            conn.commit()

print("[Search History Service] Loaded successfully")