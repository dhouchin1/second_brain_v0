#!/usr/bin/env python3
"""Alternate hybrid search engine (legacy path).

Kept for reference and experiments. The live app uses the unified
`services/SearchService` for keyword/semantic/hybrid search.
"""

import sqlite3
import re
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class HybridSearchResult:
    """Enhanced search result with both FTS and semantic scores"""
    note_id: int
    title: str
    content: str
    summary: str
    tags: List[str]
    timestamp: str
    fts_score: float
    semantic_score: float
    combined_score: float
    snippet: str
    match_type: str  # 'fts', 'semantic', 'hybrid'
    ranking_factors: Dict[str, Any]

class HybridSearchEngine:
    """Advanced search engine combining FTS5 and semantic similarity"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._semantic_search = None
        self._embedding_manager = None
        self._init_database()
    
    def _get_semantic_search(self):
        """Lazy load semantic search"""
        if self._semantic_search is None:
            try:
                from semantic_search import EnhancedSemanticSearch
                self._semantic_search = EnhancedSemanticSearch(self.db_path)
            except ImportError:
                logger.warning("Semantic search not available")
                return None
        return self._semantic_search
    
    def _get_embedding_manager(self):
        """Lazy load embedding manager"""
        if self._embedding_manager is None:
            try:
                from embedding_manager import EmbeddingManager
                self._embedding_manager = EmbeddingManager(self.db_path)
            except ImportError:
                logger.warning("Embedding manager not available")
                return None
        return self._embedding_manager
    
    def _init_database(self):
        """Initialize database with hybrid search tables"""
        conn = sqlite3.connect(self.db_path)
        
        # Use existing notes_fts table that's maintained by app.py
        # notes_fts is already created and synchronized by the main application
        
        # Create hybrid search analytics
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hybrid_search_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query TEXT NOT NULL,
                search_type TEXT DEFAULT 'hybrid',
                fts_results_count INTEGER DEFAULT 0,
                semantic_results_count INTEGER DEFAULT 0,
                hybrid_results_count INTEGER DEFAULT 0,
                fts_weight REAL DEFAULT 0.5,
                semantic_weight REAL DEFAULT 0.5,
                execution_time_ms INTEGER,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def search(self, query: str, user_id: int, 
               search_type: str = 'hybrid',
               fts_weight: float = 0.4,
               semantic_weight: float = 0.6,
               limit: int = 20,
               min_fts_score: float = 0.1,
               min_semantic_score: float = 0.1) -> List[HybridSearchResult]:
        """
        Perform hybrid search combining FTS and semantic similarity
        
        Args:
            query: Search query string
            user_id: User ID for scoping results
            search_type: 'hybrid', 'fts', or 'semantic'
            fts_weight: Weight for FTS scores (0.0-1.0)
            semantic_weight: Weight for semantic scores (0.0-1.0)
            limit: Maximum number of results
            min_fts_score: Minimum FTS score threshold
            min_semantic_score: Minimum semantic similarity threshold
        """
        start_time = time.time()
        
        if search_type == 'fts':
            results = self._fts_search(query, user_id, limit)
        elif search_type == 'semantic':
            results = self._semantic_search_only(query, user_id, limit, min_semantic_score)
        else:
            results = self._hybrid_search(
                query, user_id, limit, fts_weight, semantic_weight,
                min_fts_score, min_semantic_score
            )
        
        execution_time = int((time.time() - start_time) * 1000)
        
        # Log search analytics
        self._log_search_analytics(
            user_id, query, search_type, len(results),
            fts_weight, semantic_weight, execution_time
        )
        
        return results
    
    def _fts_search(self, query: str, user_id: int, limit: int) -> List[HybridSearchResult]:
        """Perform FTS-only search"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            fts_query = self._prepare_fts_query(query)
            
            rows = conn.execute("""
                SELECT n.*, 
                       bm25(notes_fts) as fts_score,
                       snippet(notes_fts, 1, '<mark>', '</mark>', '...', 32) as snippet
                FROM notes_fts 
                JOIN notes n ON n.id = notes_fts.rowid
                WHERE notes_fts MATCH ? AND n.user_id = ?
                ORDER BY bm25(notes_fts)
                LIMIT ?
            """, (fts_query, user_id, limit)).fetchall()
            
            conn.close()
            
            results = []
            for row in rows:
                fts_score = abs(row['fts_score'])
                
                results.append(HybridSearchResult(
                    note_id=row['id'],
                    title=row['title'] or '',
                    content=row['content'] or '',
                    summary=row['summary'] or '',
                    tags=row['tags'].split(',') if row['tags'] else [],
                    timestamp=row['timestamp'] or '',
                    fts_score=fts_score,
                    semantic_score=0.0,
                    combined_score=fts_score,
                    snippet=row['snippet'] or '',
                    match_type='fts',
                    ranking_factors={'fts_only': True}
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"FTS search failed: {e}")
            return []
    
    def _semantic_search_only(self, query: str, user_id: int, limit: int,
                             min_score: float) -> List[HybridSearchResult]:
        """Perform semantic-only search"""
        semantic_search = self._get_semantic_search()
        if not semantic_search:
            return []
        
        try:
            # Get semantic results
            semantic_results = semantic_search.semantic_search(
                query, user_id, limit=limit, min_similarity=min_score
            )
            
            results = []
            for result in semantic_results:
                results.append(HybridSearchResult(
                    note_id=result.note_id,
                    title=result.title,
                    content=result.content,
                    summary=result.summary,
                    tags=result.tags,
                    timestamp=result.timestamp,
                    fts_score=0.0,
                    semantic_score=result.similarity_score,
                    combined_score=result.similarity_score,
                    snippet=result.snippet,
                    match_type='semantic',
                    ranking_factors={'semantic_only': True}
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    def _hybrid_search(self, query: str, user_id: int, limit: int,
                      fts_weight: float, semantic_weight: float,
                      min_fts_score: float, min_semantic_score: float) -> List[HybridSearchResult]:
        """Perform hybrid search combining FTS and semantic results"""
        
        # Get FTS results with higher limit for better coverage
        fts_results = self._fts_search(query, user_id, limit * 2)
        
        # Get semantic results
        semantic_search = self._get_semantic_search()
        semantic_results = {}
        if semantic_search:
            try:
                sem_results = semantic_search.semantic_search(
                    query, user_id, limit=limit * 2, min_similarity=min_semantic_score
                )
                semantic_results = {r.note_id: r for r in sem_results}
            except Exception as e:
                logger.error(f"Semantic component failed in hybrid search: {e}")
        
        # Combine results
        combined_results = {}
        
        # Process FTS results
        for fts_result in fts_results:
            if fts_result.fts_score < min_fts_score:
                continue
                
            note_id = fts_result.note_id
            semantic_score = 0.0
            
            # Check if we have semantic score for this note
            if note_id in semantic_results:
                semantic_score = semantic_results[note_id].similarity_score
            
            # Calculate combined score
            combined_score = (
                fts_weight * fts_result.fts_score +
                semantic_weight * semantic_score
            )
            
            combined_results[note_id] = HybridSearchResult(
                note_id=note_id,
                title=fts_result.title,
                content=fts_result.content,
                summary=fts_result.summary,
                tags=fts_result.tags,
                timestamp=fts_result.timestamp,
                fts_score=fts_result.fts_score,
                semantic_score=semantic_score,
                combined_score=combined_score,
                snippet=fts_result.snippet,
                match_type='hybrid',
                ranking_factors={
                    'fts_weight': fts_weight,
                    'semantic_weight': semantic_weight,
                    'has_both_scores': semantic_score > 0
                }
            )
        
        # Add semantic-only results that weren't in FTS
        for note_id, sem_result in getattr(semantic_results, 'items', lambda: [])():
            if note_id not in combined_results and sem_result.similarity_score >= min_semantic_score:
                combined_score = semantic_weight * sem_result.similarity_score
                
                combined_results[note_id] = HybridSearchResult(
                    note_id=note_id,
                    title=sem_result.title,
                    content=sem_result.content,
                    summary=sem_result.summary,
                    tags=sem_result.tags,
                    timestamp=sem_result.timestamp,
                    fts_score=0.0,
                    semantic_score=sem_result.similarity_score,
                    combined_score=combined_score,
                    snippet=sem_result.snippet,
                    match_type='semantic',
                    ranking_factors={
                        'semantic_weight': semantic_weight,
                        'semantic_only': True
                    }
                )
        
        # Sort by combined score and limit results
        sorted_results = sorted(
            combined_results.values(),
            key=lambda x: x.combined_score,
            reverse=True
        )
        
        return sorted_results[:limit]
    
    def _prepare_fts_query(self, query: str) -> str:
        """Prepare FTS5 query with proper escaping"""
        query = re.sub(r'[^\w\s#-]', ' ', query)
        terms = query.strip().split()
        
        if not terms:
            return '""'
        
        fts_terms = []
        for term in terms:
            if term.startswith('#'):
                fts_terms.append(f'tags:"{term[1:]}"')
            else:
                fts_terms.append(f'"{term}"*')
        
        return ' '.join(fts_terms)
    
    def _log_search_analytics(self, user_id: int, query: str, search_type: str,
                             results_count: int, fts_weight: float, 
                             semantic_weight: float, execution_time: int):
        """Log search analytics"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT INTO hybrid_search_analytics 
                (user_id, query, search_type, hybrid_results_count, 
                 fts_weight, semantic_weight, execution_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, query, search_type, results_count, 
                  fts_weight, semantic_weight, execution_time))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log search analytics: {e}")
    
    def get_search_suggestions(self, query: str, user_id: int, limit: int = 5) -> List[str]:
        """Get search suggestions based on query and user history"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get suggestions from search history
            suggestions = conn.execute("""
                SELECT DISTINCT query
                FROM hybrid_search_analytics
                WHERE user_id = ? AND query LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (user_id, f"{query}%", limit)).fetchall()
            
            conn.close()
            
            return [s[0] for s in suggestions]
            
        except Exception as e:
            logger.error(f"Failed to get search suggestions: {e}")
            return []
    
    def get_search_analytics(self, user_id: Optional[int] = None, 
                            days: int = 30) -> Dict[str, Any]:
        """Get search analytics for optimization"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            where_clause = "WHERE timestamp >= datetime('now', '-{} days')".format(days)
            if user_id:
                where_clause += f" AND user_id = {user_id}"
            
            # Search type distribution
            search_types = dict(conn.execute(f"""
                SELECT search_type, COUNT(*) 
                FROM hybrid_search_analytics 
                {where_clause}
                GROUP BY search_type
            """).fetchall())
            
            # Average execution times
            avg_times = dict(conn.execute(f"""
                SELECT search_type, AVG(execution_time_ms) 
                FROM hybrid_search_analytics 
                {where_clause}
                GROUP BY search_type
            """).fetchall())
            
            # Most common queries
            common_queries = conn.execute(f"""
                SELECT query, COUNT(*) as count
                FROM hybrid_search_analytics 
                {where_clause}
                GROUP BY query
                ORDER BY count DESC
                LIMIT 10
            """).fetchall()
            
            conn.close()
            
            return {
                'search_type_distribution': search_types,
                'average_execution_times_ms': avg_times,
                'common_queries': [{'query': q[0], 'count': q[1]} for q in common_queries],
                'period_days': days
            }
            
        except Exception as e:
            logger.error(f"Failed to get search analytics: {e}")
            return {}


async def main():
    """CLI interface for hybrid search"""
    import argparse
    import asyncio
    
    parser = argparse.ArgumentParser(description="Hybrid Search Engine")
    parser.add_argument("--db", default="notes.db", help="Database path")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--user-id", type=int, default=1, help="User ID")
    parser.add_argument("--type", choices=['hybrid', 'fts', 'semantic'], 
                       default='hybrid', help="Search type")
    parser.add_argument("--fts-weight", type=float, default=0.4, 
                       help="FTS weight (0.0-1.0)")
    parser.add_argument("--semantic-weight", type=float, default=0.6, 
                       help="Semantic weight (0.0-1.0)")
    parser.add_argument("--limit", type=int, default=10, help="Result limit")
    parser.add_argument("--analytics", action="store_true", 
                       help="Show search analytics")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    engine = HybridSearchEngine(args.db)
    
    if args.analytics:
        stats = engine.get_search_analytics()
        print("\n📊 Search Analytics")
        print("=" * 30)
        for key, value in stats.items():
            print(f"{key}: {value}")
        return
    
    # Perform search
    print(f"\n🔍 Searching for: '{args.query}' (type: {args.type})")
    print("=" * 50)
    
    results = engine.search(
        args.query, args.user_id, args.type,
        args.fts_weight, args.semantic_weight, args.limit
    )
    
    print(f"Found {len(results)} results:\n")
    
    for i, result in enumerate(results, 1):
        print(f"{i}. {result.title}")
        print(f"   ID: {result.note_id}")
        print(f"   FTS Score: {result.fts_score:.3f}")
        print(f"   Semantic Score: {result.semantic_score:.3f}")
        print(f"   Combined Score: {result.combined_score:.3f}")
        print(f"   Type: {result.match_type}")
        if result.snippet:
            print(f"   Snippet: {result.snippet}")
        print()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
