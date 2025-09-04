"""
Search Analytics Service

Comprehensive analytics tracking for search performance, query effectiveness,
click-through rates, and search method comparisons (BM25 vs semantic vs hybrid).
Designed to measure and improve search algorithm performance with detailed metrics.
"""

import json
import sqlite3
import time
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass
from collections import defaultdict

@dataclass
class SearchQueryMetrics:
    """Metrics for a specific search query execution"""
    id: int
    user_id: int
    query: str
    search_mode: str
    results_count: int
    response_time_ms: int
    click_through_rate: float
    avg_relevance_score: float
    result_quality_score: float
    auto_seeded_content_hits: int
    created_at: datetime

@dataclass
class ClickThroughEvent:
    """Click-through event tracking"""
    id: int
    search_query_id: int
    result_position: int
    note_id: int
    time_to_click_ms: int
    session_duration_ms: Optional[int]
    created_at: datetime

@dataclass
class SearchPerformanceMetrics:
    """Aggregated performance metrics"""
    total_searches: int
    avg_response_time: float
    avg_click_through_rate: float
    avg_result_quality: float
    search_mode_performance: Dict[str, Dict[str, float]]
    top_performing_queries: List[Dict[str, Any]]
    improvement_opportunities: List[str]

class SearchAnalyticsService:
    def __init__(self, get_conn: Callable[[], sqlite3.Connection]):
        self.get_conn = get_conn
        self._ensure_analytics_tables()
        
    def _ensure_analytics_tables(self):
        """Ensure all analytics tables exist with proper schema"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # Detailed query metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_query_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                search_mode TEXT NOT NULL CHECK (search_mode IN ('keyword', 'semantic', 'hybrid')),
                results_count INTEGER DEFAULT 0,
                response_time_ms INTEGER DEFAULT 0,
                click_through_rate REAL DEFAULT 0.0,
                avg_relevance_score REAL DEFAULT 0.0,
                result_quality_score REAL DEFAULT 0.0,
                auto_seeded_content_hits INTEGER DEFAULT 0,
                search_session_id TEXT,
                user_agent TEXT,
                search_context TEXT DEFAULT '{}', -- JSON for additional context
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Click-through tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS click_through_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_query_id INTEGER NOT NULL,
                result_position INTEGER NOT NULL,
                note_id INTEGER NOT NULL,
                time_to_click_ms INTEGER DEFAULT 0,
                session_duration_ms INTEGER,
                interaction_type TEXT DEFAULT 'view' CHECK (interaction_type IN ('view', 'edit', 'share', 'bookmark')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (search_query_id) REFERENCES search_query_metrics(id) ON DELETE CASCADE,
                FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
            )
        """)
        
        # Search result quality scores table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_result_quality (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_query_id INTEGER NOT NULL,
                note_id INTEGER NOT NULL,
                result_position INTEGER NOT NULL,
                relevance_score REAL DEFAULT 0.0,
                semantic_score REAL DEFAULT 0.0,
                keyword_score REAL DEFAULT 0.0,
                combined_score REAL DEFAULT 0.0,
                is_auto_seeded_content BOOLEAN DEFAULT FALSE,
                user_feedback_score INTEGER, -- 1-5 rating if provided
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (search_query_id) REFERENCES search_query_metrics(id) ON DELETE CASCADE,
                FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
            )
        """)
        
        # Performance benchmarks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_performance_benchmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                search_mode TEXT NOT NULL,
                avg_response_time_ms REAL DEFAULT 0.0,
                avg_click_through_rate REAL DEFAULT 0.0,
                avg_result_quality REAL DEFAULT 0.0,
                total_searches INTEGER DEFAULT 0,
                successful_searches INTEGER DEFAULT 0, -- searches that got clicks
                auto_seeded_effectiveness REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, search_mode)
            )
        """)
        
        # Create performance indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_query_metrics_user_date ON search_query_metrics(user_id, created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_query_metrics_mode_date ON search_query_metrics(search_mode, created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_click_through_search_id ON click_through_events(search_query_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_result_quality_query ON search_result_quality(search_query_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_performance_benchmarks_date ON search_performance_benchmarks(date DESC)")
        
        conn.commit()
    
    def track_search_query(self, user_id: int, query: str, search_mode: str, 
                          results: List[Dict[str, Any]], response_time_ms: int,
                          search_context: Dict[str, Any] = None,
                          search_session_id: str = None,
                          user_agent: str = None) -> int:
        """Track a search query with detailed metrics"""
        
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # Calculate result quality metrics
        result_quality_score = self._calculate_result_quality(results)
        avg_relevance_score = self._calculate_avg_relevance(results)
        auto_seeded_hits = self._count_auto_seeded_content(results)
        
        # Insert query metrics
        cursor.execute("""
            INSERT INTO search_query_metrics 
            (user_id, query, search_mode, results_count, response_time_ms, 
             avg_relevance_score, result_quality_score, auto_seeded_content_hits,
             search_session_id, user_agent, search_context)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, query, search_mode, len(results), response_time_ms,
              avg_relevance_score, result_quality_score, auto_seeded_hits,
              search_session_id, user_agent, json.dumps(search_context or {})))
        
        search_query_id = cursor.lastrowid
        
        # Track individual result quality scores
        for position, result in enumerate(results):
            self._track_result_quality(cursor, search_query_id, result, position)
        
        conn.commit()
        
        # Update daily benchmarks
        self._update_performance_benchmarks(search_mode, response_time_ms, result_quality_score)
        
        return search_query_id
    
    def track_click_through(self, search_query_id: int, result_position: int, 
                          note_id: int, time_to_click_ms: int = 0,
                          interaction_type: str = 'view',
                          session_duration_ms: Optional[int] = None) -> int:
        """Track click-through events for CTR calculation"""
        
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO click_through_events 
            (search_query_id, result_position, note_id, time_to_click_ms, 
             session_duration_ms, interaction_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (search_query_id, result_position, note_id, time_to_click_ms,
              session_duration_ms, interaction_type))
        
        click_event_id = cursor.lastrowid
        conn.commit()
        
        # Update CTR for the search query
        self._update_search_ctr(search_query_id)
        
        return click_event_id
    
    def get_dashboard_analytics(self, user_id: Optional[int] = None, 
                              days: int = 30) -> Dict[str, Any]:
        """Get comprehensive dashboard analytics"""
        
        conn = self.get_conn()
        cursor = conn.cursor()
        
        date_filter = "AND created_at >= datetime('now', '-{} days')".format(days)
        user_filter = "AND user_id = ?" if user_id else ""
        params = [user_id] if user_id else []
        
        # Overall search volume and performance
        cursor.execute(f"""
            SELECT 
                COUNT(*) as total_searches,
                AVG(response_time_ms) as avg_response_time,
                AVG(click_through_rate) as avg_ctr,
                AVG(result_quality_score) as avg_quality,
                AVG(auto_seeded_content_hits) as avg_auto_seeded_hits
            FROM search_query_metrics 
            WHERE 1=1 {date_filter} {user_filter}
        """, params)
        
        overall_stats = cursor.fetchone()
        
        # Search mode effectiveness comparison
        cursor.execute(f"""
            SELECT 
                search_mode,
                COUNT(*) as search_count,
                AVG(response_time_ms) as avg_response_time,
                AVG(click_through_rate) as avg_ctr,
                AVG(result_quality_score) as avg_quality,
                AVG(results_count) as avg_results_count
            FROM search_query_metrics 
            WHERE 1=1 {date_filter} {user_filter}
            GROUP BY search_mode
        """, params)
        
        mode_effectiveness = {}
        for row in cursor.fetchall():
            mode_effectiveness[row[0]] = {
                'search_count': row[1],
                'avg_response_time': float(row[2] or 0),
                'avg_ctr': float(row[3] or 0),
                'avg_quality': float(row[4] or 0),
                'avg_results_count': float(row[5] or 0)
            }
        
        # Daily search volume trends
        cursor.execute(f"""
            SELECT 
                DATE(created_at) as search_date,
                COUNT(*) as daily_searches,
                AVG(response_time_ms) as daily_avg_response_time,
                AVG(click_through_rate) as daily_avg_ctr
            FROM search_query_metrics 
            WHERE 1=1 {date_filter} {user_filter}
            GROUP BY DATE(created_at)
            ORDER BY search_date DESC
        """, params)
        
        daily_trends = []
        for row in cursor.fetchall():
            daily_trends.append({
                'date': row[0],
                'searches': row[1],
                'avg_response_time': float(row[2] or 0),
                'avg_ctr': float(row[3] or 0)
            })
        
        # Top performing queries
        cursor.execute(f"""
            SELECT 
                query,
                search_mode,
                COUNT(*) as frequency,
                AVG(click_through_rate) as avg_ctr,
                AVG(result_quality_score) as avg_quality,
                AVG(response_time_ms) as avg_response_time
            FROM search_query_metrics 
            WHERE 1=1 {date_filter} {user_filter}
            GROUP BY query, search_mode
            HAVING frequency > 1
            ORDER BY avg_ctr DESC, avg_quality DESC
            LIMIT 10
        """, params)
        
        top_queries = []
        for row in cursor.fetchall():
            top_queries.append({
                'query': row[0],
                'search_mode': row[1], 
                'frequency': row[2],
                'avg_ctr': float(row[3] or 0),
                'avg_quality': float(row[4] or 0),
                'avg_response_time': float(row[5] or 0)
            })
        
        # Auto-seeded content effectiveness
        cursor.execute(f"""
            SELECT 
                AVG(CASE WHEN auto_seeded_content_hits > 0 THEN click_through_rate ELSE 0 END) as auto_seeded_ctr,
                AVG(CASE WHEN auto_seeded_content_hits = 0 THEN click_through_rate ELSE 0 END) as regular_content_ctr,
                COUNT(CASE WHEN auto_seeded_content_hits > 0 THEN 1 END) as searches_with_auto_seeded,
                COUNT(*) as total_searches
            FROM search_query_metrics 
            WHERE 1=1 {date_filter} {user_filter}
        """, params)
        
        auto_seeded_stats = cursor.fetchone()
        
        return {
            'period_days': days,
            'total_searches': overall_stats[0] or 0,
            'avg_response_time_ms': float(overall_stats[1] or 0),
            'avg_click_through_rate': float(overall_stats[2] or 0),
            'avg_result_quality': float(overall_stats[3] or 0),
            'avg_auto_seeded_hits': float(overall_stats[4] or 0),
            'search_mode_effectiveness': mode_effectiveness,
            'daily_trends': daily_trends,
            'top_performing_queries': top_queries,
            'auto_seeded_effectiveness': {
                'auto_seeded_ctr': float(auto_seeded_stats[0] or 0),
                'regular_content_ctr': float(auto_seeded_stats[1] or 0),
                'searches_with_auto_seeded': auto_seeded_stats[2] or 0,
                'auto_seeded_improvement': float(auto_seeded_stats[0] or 0) - float(auto_seeded_stats[1] or 0)
            }
        }
    
    def get_performance_metrics(self, user_id: Optional[int] = None,
                              search_mode: Optional[str] = None,
                              days: int = 30) -> SearchPerformanceMetrics:
        """Get detailed performance metrics for analysis"""
        
        conn = self.get_conn()
        cursor = conn.cursor()
        
        date_filter = "AND sqm.created_at >= datetime('now', '-{} days')".format(days)
        user_filter = "AND sqm.user_id = ?" if user_id else ""
        mode_filter = "AND sqm.search_mode = ?" if search_mode else ""
        
        params = []
        if user_id:
            params.append(user_id)
        if search_mode:
            params.append(search_mode)
        
        # Basic performance metrics
        cursor.execute(f"""
            SELECT 
                COUNT(*) as total_searches,
                AVG(sqm.response_time_ms) as avg_response_time,
                AVG(sqm.click_through_rate) as avg_ctr,
                AVG(sqm.result_quality_score) as avg_quality
            FROM search_query_metrics sqm
            WHERE 1=1 {date_filter} {user_filter} {mode_filter}
        """, params)
        
        basic_metrics = cursor.fetchone()
        
        # Performance by search mode
        cursor.execute(f"""
            SELECT 
                sqm.search_mode,
                COUNT(*) as search_count,
                AVG(sqm.response_time_ms) as avg_response_time,
                AVG(sqm.click_through_rate) as avg_ctr,
                AVG(sqm.result_quality_score) as avg_quality,
                AVG(sqm.results_count) as avg_results
            FROM search_query_metrics sqm
            WHERE 1=1 {date_filter} {user_filter}
            GROUP BY sqm.search_mode
        """, params[:1] if user_id and not search_mode else [])
        
        mode_performance = {}
        for row in cursor.fetchall():
            mode_performance[row[0]] = {
                'search_count': row[1],
                'avg_response_time': float(row[2] or 0),
                'avg_ctr': float(row[3] or 0),
                'avg_quality': float(row[4] or 0),
                'avg_results': float(row[5] or 0)
            }
        
        # Top performing queries with detailed metrics
        cursor.execute(f"""
            SELECT 
                sqm.query,
                sqm.search_mode,
                COUNT(*) as frequency,
                AVG(sqm.click_through_rate) as avg_ctr,
                AVG(sqm.result_quality_score) as avg_quality,
                AVG(sqm.response_time_ms) as avg_response_time,
                AVG(sqm.results_count) as avg_results,
                MAX(sqm.created_at) as last_used
            FROM search_query_metrics sqm
            WHERE 1=1 {date_filter} {user_filter} {mode_filter}
            GROUP BY sqm.query, sqm.search_mode
            HAVING frequency > 1
            ORDER BY avg_ctr DESC, avg_quality DESC, frequency DESC
            LIMIT 15
        """, params)
        
        top_queries = []
        for row in cursor.fetchall():
            top_queries.append({
                'query': row[0],
                'search_mode': row[1],
                'frequency': row[2],
                'avg_ctr': float(row[3] or 0),
                'avg_quality': float(row[4] or 0),
                'avg_response_time': float(row[5] or 0),
                'avg_results': float(row[6] or 0),
                'last_used': row[7]
            })
        
        # Identify improvement opportunities
        improvement_opportunities = self._identify_improvement_opportunities(
            basic_metrics, mode_performance, top_queries
        )
        
        return SearchPerformanceMetrics(
            total_searches=basic_metrics[0] or 0,
            avg_response_time=float(basic_metrics[1] or 0),
            avg_click_through_rate=float(basic_metrics[2] or 0),
            avg_result_quality=float(basic_metrics[3] or 0),
            search_mode_performance=mode_performance,
            top_performing_queries=top_queries,
            improvement_opportunities=improvement_opportunities
        )
    
    def _calculate_result_quality(self, results: List[Dict[str, Any]]) -> float:
        """Calculate overall result quality score based on various factors"""
        if not results:
            return 0.0
        
        total_score = 0.0
        for i, result in enumerate(results[:10]):  # Consider top 10 results
            # Position-based relevance (higher positions get lower weight)
            position_weight = 1.0 / (1.0 + i * 0.1)
            
            # Content quality indicators
            content_score = 0.0
            
            # Has meaningful title
            title = result.get('title', '')
            if title and len(title.strip()) > 5:
                content_score += 0.2
            
            # Has content/summary
            content = result.get('content', '') or result.get('summary', '')
            if content and len(content.strip()) > 20:
                content_score += 0.3
            
            # Has tags (indicates organized content)
            tags = result.get('tags', '')
            if tags and tags.strip():
                content_score += 0.2
            
            # Recent content (more likely to be relevant)
            if result.get('created_at'):
                try:
                    created_date = datetime.fromisoformat(result['created_at'].replace('Z', '+00:00'))
                    days_old = (datetime.now() - created_date).days
                    if days_old <= 30:
                        content_score += 0.2
                    elif days_old <= 90:
                        content_score += 0.1
                except:
                    pass
            
            # Search-specific score if available
            search_score = result.get('score', 0.5)
            if isinstance(search_score, (int, float)):
                content_score += min(search_score, 1.0) * 0.1
            
            total_score += content_score * position_weight
        
        return min(total_score / len(results), 1.0)
    
    def _calculate_avg_relevance(self, results: List[Dict[str, Any]]) -> float:
        """Calculate average relevance score from search results"""
        if not results:
            return 0.0
        
        total_relevance = 0.0
        count = 0
        
        for result in results:
            # Try to get various score fields
            score = (result.get('score') or 
                    result.get('fts_score') or
                    result.get('semantic_score') or
                    result.get('combined_score') or
                    0.5)
            
            if isinstance(score, (int, float)):
                total_relevance += float(score)
                count += 1
        
        return total_relevance / count if count > 0 else 0.5
    
    def _count_auto_seeded_content(self, results: List[Dict[str, Any]]) -> int:
        """Count how many results are from auto-seeded content"""
        count = 0
        
        for result in results:
            # Check various indicators of auto-seeded content
            tags = result.get('tags', '').lower()
            title = result.get('title', '').lower()
            content_type = result.get('type', '').lower()
            
            # Look for auto-seeding indicators
            if ('auto-seeded' in tags or 
                'web-ingestion' in tags or
                'smart-automation' in tags or
                'web-content' in content_type or
                'automated' in title):
                count += 1
        
        return count
    
    def _track_result_quality(self, cursor: sqlite3.Cursor, search_query_id: int, 
                            result: Dict[str, Any], position: int):
        """Track individual result quality metrics"""
        
        relevance_score = result.get('score', 0.5)
        semantic_score = result.get('semantic_score', 0.0)
        keyword_score = result.get('fts_score', 0.0)
        combined_score = result.get('combined_score', relevance_score)
        
        # Check if this is auto-seeded content
        is_auto_seeded = self._is_auto_seeded_content(result)
        
        note_id = result.get('id', 0)
        
        cursor.execute("""
            INSERT INTO search_result_quality 
            (search_query_id, note_id, result_position, relevance_score,
             semantic_score, keyword_score, combined_score, is_auto_seeded_content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (search_query_id, note_id, position, float(relevance_score or 0),
              float(semantic_score or 0), float(keyword_score or 0), 
              float(combined_score or 0), is_auto_seeded))
    
    def _is_auto_seeded_content(self, result: Dict[str, Any]) -> bool:
        """Determine if a result is from auto-seeded content"""
        tags = result.get('tags', '').lower()
        content_type = result.get('type', '').lower()
        
        return ('auto-seeded' in tags or 
                'web-ingestion' in tags or
                'smart-automation' in tags or
                'web-content' in content_type)
    
    def _update_search_ctr(self, search_query_id: int):
        """Update click-through rate for a search query"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # Calculate CTR based on click events
        cursor.execute("""
            SELECT COUNT(DISTINCT result_position) as clicked_results
            FROM click_through_events 
            WHERE search_query_id = ?
        """, (search_query_id,))
        
        clicked_results = cursor.fetchone()[0] or 0
        
        # Get total results for this search
        cursor.execute("""
            SELECT results_count 
            FROM search_query_metrics 
            WHERE id = ?
        """, (search_query_id,))
        
        total_results = cursor.fetchone()[0] or 0
        
        # Calculate CTR
        ctr = clicked_results / max(total_results, 1)
        
        # Update the search query metrics
        cursor.execute("""
            UPDATE search_query_metrics 
            SET click_through_rate = ?
            WHERE id = ?
        """, (ctr, search_query_id))
        
        conn.commit()
    
    def _update_performance_benchmarks(self, search_mode: str, response_time_ms: int, 
                                     result_quality_score: float):
        """Update daily performance benchmarks"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        today = date.today().isoformat()
        
        cursor.execute("""
            INSERT INTO search_performance_benchmarks 
            (date, search_mode, avg_response_time_ms, avg_result_quality, total_searches)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(date, search_mode) DO UPDATE SET
                avg_response_time_ms = (avg_response_time_ms * total_searches + ?) / (total_searches + 1),
                avg_result_quality = (avg_result_quality * total_searches + ?) / (total_searches + 1),
                total_searches = total_searches + 1
        """, (today, search_mode, response_time_ms, result_quality_score,
              response_time_ms, result_quality_score))
        
        conn.commit()
    
    def _identify_improvement_opportunities(self, basic_metrics: tuple, 
                                         mode_performance: Dict[str, Dict], 
                                         top_queries: List[Dict]) -> List[str]:
        """Identify areas for search performance improvement"""
        opportunities = []
        
        avg_response_time = basic_metrics[1] or 0
        avg_ctr = basic_metrics[2] or 0
        avg_quality = basic_metrics[3] or 0
        
        # Response time opportunities
        if avg_response_time > 1000:
            opportunities.append("High response times detected (>1s). Consider optimizing search indexes or query complexity.")
        elif avg_response_time > 500:
            opportunities.append("Moderate response times (>500ms). Monitor for performance degradation.")
        
        # CTR opportunities
        if avg_ctr < 0.3:
            opportunities.append("Low click-through rate (<30%). Consider improving result relevance or ranking algorithm.")
        elif avg_ctr < 0.5:
            opportunities.append("Moderate CTR. Test different ranking strategies to improve user engagement.")
        
        # Quality opportunities
        if avg_quality < 0.6:
            opportunities.append("Low result quality scores. Review content indexing and similarity algorithms.")
        
        # Mode comparison opportunities
        if len(mode_performance) > 1:
            best_mode = max(mode_performance.items(), 
                          key=lambda x: x[1]['avg_ctr'] * x[1]['avg_quality'])
            worst_mode = min(mode_performance.items(),
                           key=lambda x: x[1]['avg_ctr'] * x[1]['avg_quality'])
            
            if best_mode[1]['avg_ctr'] - worst_mode[1]['avg_ctr'] > 0.2:
                opportunities.append(f"'{best_mode[0]}' search significantly outperforms '{worst_mode[0]}'. Consider promoting the better-performing mode.")
        
        # Query-specific opportunities
        low_performing_queries = [q for q in top_queries if q['avg_ctr'] < 0.2 and q['frequency'] > 2]
        if low_performing_queries:
            opportunities.append(f"Found {len(low_performing_queries)} frequently-used queries with low CTR. Consider query expansion or result re-ranking.")
        
        return opportunities[:5]  # Limit to top 5 most important opportunities
    
    def get_user_search_patterns(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Analyze user-specific search patterns and preferences"""
        
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # User's preferred search modes
        cursor.execute("""
            SELECT 
                search_mode,
                COUNT(*) as usage_count,
                AVG(click_through_rate) as avg_success_rate
            FROM search_query_metrics 
            WHERE user_id = ? AND created_at >= datetime('now', '-{} days')
            GROUP BY search_mode
            ORDER BY usage_count DESC
        """.format(days), (user_id,))
        
        mode_preferences = []
        for row in cursor.fetchall():
            mode_preferences.append({
                'mode': row[0],
                'usage_count': row[1],
                'success_rate': float(row[2] or 0)
            })
        
        # Common query patterns
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN LENGTH(query) <= 10 THEN 'short'
                    WHEN LENGTH(query) <= 30 THEN 'medium'
                    ELSE 'long'
                END as query_length,
                COUNT(*) as count,
                AVG(click_through_rate) as avg_ctr
            FROM search_query_metrics 
            WHERE user_id = ? AND created_at >= datetime('now', '-{} days')
            GROUP BY query_length
        """.format(days), (user_id,))
        
        query_patterns = []
        for row in cursor.fetchall():
            query_patterns.append({
                'pattern': row[0],
                'count': row[1],
                'avg_ctr': float(row[2] or 0)
            })
        
        # Peak search times
        cursor.execute("""
            SELECT 
                strftime('%H', created_at) as hour,
                COUNT(*) as search_count
            FROM search_query_metrics 
            WHERE user_id = ? AND created_at >= datetime('now', '-{} days')
            GROUP BY hour
            ORDER BY search_count DESC
            LIMIT 5
        """.format(days), (user_id,))
        
        peak_hours = [{'hour': int(row[0]), 'searches': row[1]} for row in cursor.fetchall()]
        
        return {
            'mode_preferences': mode_preferences,
            'query_patterns': query_patterns,
            'peak_search_hours': peak_hours,
            'analysis_period_days': days
        }

print("[Search Analytics Service] Loaded successfully")