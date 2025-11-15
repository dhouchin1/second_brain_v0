"""
Advanced Search Router for Second Brain
Provides enhanced search capabilities with Boolean operators, filters, and saved searches
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import sqlite3
import json
from pathlib import Path
from datetime import datetime

from services.advanced_search_parser import AdvancedSearchParser, SearchQuery

router = APIRouter(prefix="/api/search/advanced", tags=["search"])


# ============================================
# Models
# ============================================

class SearchRequest(BaseModel):
    """Advanced search request"""
    query: str = Field(..., description="Search query with optional operators and filters")
    mode: str = Field(default="hybrid", description="Search mode: fts, semantic, or hybrid")
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    min_score: float = Field(default=0.1, ge=0.0, le=1.0)


class SearchResult(BaseModel):
    """Search result item"""
    id: int
    title: str
    content: str
    score: float
    created_at: str
    updated_at: Optional[str] = None
    tags: Optional[List[str]] = None
    type: Optional[str] = None
    source: Optional[str] = None


class SearchResponse(BaseModel):
    """Search response"""
    success: bool
    query: str
    total_results: int
    results: List[SearchResult]
    execution_time_ms: float
    filters_applied: Dict[str, List[str]]


class SavedSearch(BaseModel):
    """Saved search query"""
    id: Optional[int] = None
    name: str
    query: str
    filters: Optional[Dict[str, List[str]]] = None
    created_at: Optional[str] = None
    user_id: int = 1


class SearchHistoryEntry(BaseModel):
    """Search history entry"""
    id: Optional[int] = None
    query: str
    results_count: int
    timestamp: str
    user_id: int = 1


# ============================================
# Database Helpers
# ============================================

def get_db_connection():
    """Get database connection"""
    db_path = Path(__file__).parent.parent / "second_brain.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_search_tables():
    """Initialize search-related tables"""
    conn = get_db_connection()
    try:
        # Saved searches table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL,
                query TEXT NOT NULL,
                filters TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Search history table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                query TEXT NOT NULL,
                results_count INTEGER DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Create index on timestamp for faster queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_history_timestamp
            ON search_history(timestamp DESC)
        """)

        conn.commit()
    finally:
        conn.close()


# Initialize tables on module import
try:
    init_search_tables()
except Exception as e:
    print(f"Warning: Could not initialize search tables: {e}")


# ============================================
# Search Endpoints
# ============================================

@router.post("/query", response_model=SearchResponse)
async def advanced_search(request: SearchRequest):
    """
    Perform advanced search with Boolean operators and filters

    Supports:
    - Boolean operators: AND, OR, NOT
    - Field-specific search: title:python, tag:work
    - Date ranges: created:2024-01-01..2024-12-31
    - Quoted phrases: "machine learning"
    - Wildcards: pyth*
    """
    start_time = datetime.now()

    # Parse query
    parser = AdvancedSearchParser()
    parsed_query = parser.parse(request.query)

    # Build SQL query
    where_clause, parameters = parser.to_sql_conditions()

    conn = get_db_connection()
    try:
        # Construct full SQL query
        sql = f"""
            SELECT
                id,
                title,
                content,
                created_at,
                updated_at,
                tags,
                type,
                source,
                1.0 as score
            FROM notes
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """

        parameters['limit'] = request.limit
        parameters['offset'] = request.offset

        # Execute query
        cursor = conn.execute(sql, parameters)
        rows = cursor.fetchall()

        # Build results
        results = []
        for row in rows:
            tags = json.loads(row['tags']) if row['tags'] else []
            results.append(SearchResult(
                id=row['id'],
                title=row['title'] or "Untitled",
                content=row['content'][:500] if row['content'] else "",
                score=row['score'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                tags=tags,
                type=row.get('type'),
                source=row.get('source')
            ))

        # Get total count
        count_sql = f"SELECT COUNT(*) as total FROM notes WHERE {where_clause}"
        total_count = conn.execute(count_sql, {k: v for k, v in parameters.items() if k not in ['limit', 'offset']}).fetchone()['total']

        # Calculate execution time
        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        # Record in search history
        record_search_history(request.query, len(results))

        return SearchResponse(
            success=True,
            query=request.query,
            total_results=total_count,
            results=results,
            execution_time_ms=round(execution_time, 2),
            filters_applied=parsed_query.filters
        )

    finally:
        conn.close()


@router.get("/suggestions")
async def get_search_suggestions(q: str = Query(..., min_length=1)):
    """
    Get search suggestions based on partial query

    Returns: List of suggested search terms
    """
    conn = get_db_connection()
    try:
        # Get title suggestions
        cursor = conn.execute("""
            SELECT DISTINCT title
            FROM notes
            WHERE title LIKE ?
            ORDER BY created_at DESC
            LIMIT 10
        """, (f"%{q}%",))

        suggestions = [row['title'] for row in cursor.fetchall() if row['title']]

        # Get tag suggestions
        cursor = conn.execute("""
            SELECT DISTINCT tags
            FROM notes
            WHERE tags IS NOT NULL AND tags != '[]'
            LIMIT 100
        """)

        all_tags = set()
        for row in cursor.fetchall():
            if row['tags']:
                try:
                    tags = json.loads(row['tags'])
                    all_tags.update(tags)
                except:
                    pass

        # Filter tags that match query
        matching_tags = [f"tag:{tag}" for tag in all_tags if q.lower() in tag.lower()][:5]
        suggestions.extend(matching_tags)

        return {
            "success": True,
            "query": q,
            "suggestions": suggestions[:10]
        }

    finally:
        conn.close()


# ============================================
# Saved Searches
# ============================================

@router.post("/saved", response_model=SavedSearch)
async def save_search(search: SavedSearch):
    """Save a search query for later use"""
    conn = get_db_connection()
    try:
        filters_json = json.dumps(search.filters) if search.filters else None

        cursor = conn.execute("""
            INSERT INTO saved_searches (user_id, name, query, filters)
            VALUES (?, ?, ?, ?)
        """, (search.user_id, search.name, search.query, filters_json))

        conn.commit()
        search_id = cursor.lastrowid

        return SavedSearch(
            id=search_id,
            name=search.name,
            query=search.query,
            filters=search.filters,
            user_id=search.user_id,
            created_at=datetime.now().isoformat()
        )

    finally:
        conn.close()


@router.get("/saved", response_model=List[SavedSearch])
async def get_saved_searches(user_id: int = 1):
    """Get all saved searches for a user"""
    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            SELECT id, user_id, name, query, filters, created_at
            FROM saved_searches
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))

        searches = []
        for row in cursor.fetchall():
            filters = json.loads(row['filters']) if row['filters'] else None
            searches.append(SavedSearch(
                id=row['id'],
                name=row['name'],
                query=row['query'],
                filters=filters,
                user_id=row['user_id'],
                created_at=row['created_at']
            ))

        return searches

    finally:
        conn.close()


@router.delete("/saved/{search_id}")
async def delete_saved_search(search_id: int, user_id: int = 1):
    """Delete a saved search"""
    conn = get_db_connection()
    try:
        conn.execute("""
            DELETE FROM saved_searches
            WHERE id = ? AND user_id = ?
        """, (search_id, user_id))

        conn.commit()

        return {
            "success": True,
            "message": f"Saved search {search_id} deleted"
        }

    finally:
        conn.close()


# ============================================
# Search History
# ============================================

def record_search_history(query: str, results_count: int, user_id: int = 1):
    """Record a search in history"""
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO search_history (user_id, query, results_count)
            VALUES (?, ?, ?)
        """, (user_id, query, results_count))

        conn.commit()

        # Keep only last 100 entries per user
        conn.execute("""
            DELETE FROM search_history
            WHERE id IN (
                SELECT id FROM search_history
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT -1 OFFSET 100
            )
        """, (user_id,))

        conn.commit()

    except Exception as e:
        print(f"Failed to record search history: {e}")
    finally:
        conn.close()


@router.get("/history", response_model=List[SearchHistoryEntry])
async def get_search_history(user_id: int = 1, limit: int = 20):
    """Get search history for a user"""
    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            SELECT id, query, results_count, timestamp
            FROM search_history
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (user_id, limit))

        history = []
        for row in cursor.fetchall():
            history.append(SearchHistoryEntry(
                id=row['id'],
                query=row['query'],
                results_count=row['results_count'],
                timestamp=row['timestamp'],
                user_id=user_id
            ))

        return history

    finally:
        conn.close()


@router.delete("/history")
async def clear_search_history(user_id: int = 1):
    """Clear search history for a user"""
    conn = get_db_connection()
    try:
        conn.execute("""
            DELETE FROM search_history
            WHERE user_id = ?
        """, (user_id,))

        conn.commit()

        return {
            "success": True,
            "message": "Search history cleared"
        }

    finally:
        conn.close()


# ============================================
# Search Analytics
# ============================================

@router.get("/analytics")
async def get_search_analytics(user_id: int = 1):
    """Get search analytics"""
    conn = get_db_connection()
    try:
        # Total searches
        total_searches = conn.execute("""
            SELECT COUNT(*) as count
            FROM search_history
            WHERE user_id = ?
        """, (user_id,)).fetchone()['count']

        # Popular searches
        popular = conn.execute("""
            SELECT query, COUNT(*) as count
            FROM search_history
            WHERE user_id = ?
            GROUP BY query
            ORDER BY count DESC
            LIMIT 10
        """, (user_id,)).fetchall()

        # Recent searches
        recent = conn.execute("""
            SELECT query, timestamp
            FROM search_history
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT 10
        """, (user_id,)).fetchall()

        return {
            "success": True,
            "total_searches": total_searches,
            "popular_searches": [{"query": row['query'], "count": row['count']} for row in popular],
            "recent_searches": [{"query": row['query'], "timestamp": row['timestamp']} for row in recent]
        }

    finally:
        conn.close()


# ============================================
# Health Check
# ============================================

@router.get("/health")
async def health_check():
    """Advanced search service health check"""
    return {
        "status": "healthy",
        "service": "advanced_search",
        "features": [
            "boolean_operators",
            "field_specific_search",
            "date_ranges",
            "saved_searches",
            "search_history",
            "suggestions"
        ]
    }
