"""EXPERIMENTAL/LEGACY PROTOTYPE — Not used by current app.

Kept for reference and experiments. The live application uses
`services/search_adapter.py` via app.py endpoints.
"""
# search_engine.py - Enhanced search with FTS5 + sqlite-vec

import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer
import json
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import re
from config import settings

@dataclass
class SearchResult:
    note_id: int
    title: str
    content: str
    summary: str
    tags: List[str]
    timestamp: str
    score: float
    snippet: str
    match_type: str  # 'fts', 'semantic', 'hybrid'

class EnhancedSearchEngine:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.embedding_model = None
        self._init_database()
        
    def _init_database(self):
        """Initialize database with FTS5 and vector extensions"""
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        
        try:
            # Load sqlite-vec extension (requires compilation)
            conn.load_extension("./extensions/vec0")
        except:
            print("Warning: sqlite-vec extension not available. Semantic search disabled.")
            
        # Create enhanced FTS5 table
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts5 USING fts5(
                title, content, summary, tags, actions,
                content='notes', content_rowid='id',
                tokenize='porter unicode61'
            )
        """)
        
        # Create vector table for embeddings
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS note_embeddings USING vec0(
                note_id INTEGER PRIMARY KEY,
                embedding FLOAT[384]
            )
        """)
        
        # Create search analytics
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query TEXT,
                results_count INTEGER,
                clicked_result_id INTEGER,
                search_type TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.close()
    
    def _get_embedding_model(self):
        """Lazy load embedding model"""
        if self.embedding_model is None:
            # Use lightweight model for local processing
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        return self.embedding_model
    
    def index_note(self, note_id: int, title: str, content: str, 
                   summary: str, tags: str, actions: str):
        """Index a note for both FTS and vector search"""
        conn = sqlite3.connect(self.db_path)
        
        # Update FTS5 index
        conn.execute("""
            INSERT OR REPLACE INTO notes_fts5(rowid, title, content, summary, tags, actions)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (note_id, title, content, summary, tags, actions))
        
        # Generate and store embedding
        try:
            model = self._get_embedding_model()
            text_to_embed = f"{title} {summary} {content}"[:500]  # Limit length
            embedding = model.encode(text_to_embed)
            
            # Store in vector table
            conn.execute("""
                INSERT OR REPLACE INTO note_embeddings(note_id, embedding)
                VALUES (?, ?)
            """, (note_id, embedding.tobytes()))
            
        except Exception as e:
            print(f"Warning: Could not generate embedding for note {note_id}: {e}")
        
        conn.commit()
        conn.close()
    
    def search(self, query: str, user_id: int, limit: int = 20, 
               search_type: str = 'hybrid') -> List[SearchResult]:
        """Enhanced search with multiple strategies"""
        
        if search_type == 'fts':
            return self._fts_search(query, user_id, limit)
        elif search_type == 'semantic':
            return self._semantic_search(query, user_id, limit)
        else:
            return self._hybrid_search(query, user_id, limit)
    
    def _fts_search(self, query: str, user_id: int, limit: int) -> List[SearchResult]:
        """Full-text search using FTS5"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        # Enhanced FTS query with ranking
        fts_query = self._prepare_fts_query(query)
        
        rows = conn.execute("""
            SELECT n.*, 
                   bm25(notes_fts5) as fts_score,
                   snippet(notes_fts5, 1, '<mark>', '</mark>', '...', 32) as snippet
            FROM notes_fts5 
            JOIN notes n ON n.id = notes_fts5.rowid
            WHERE notes_fts5 MATCH ? AND n.user_id = ?
            ORDER BY bm25(notes_fts5)
            LIMIT ?
        """, (fts_query, user_id, limit)).fetchall()
        
        conn.close()
        
        results = []
        for row in rows:
            results.append(SearchResult(
                note_id=row['id'],
                title=row['title'],
                content=row['content'],
                summary=row['summary'],
                tags=row['tags'].split(',') if row['tags'] else [],
                timestamp=row['timestamp'],
                score=abs(row['fts_score']),  # BM25 returns negative scores
                snippet=row['snippet'],
                match_type='fts'
            ))
        
        return results
    
    def _semantic_search(self, query: str, user_id: int, limit: int) -> List[SearchResult]:
        """Semantic search using embeddings"""
        try:
            model = self._get_embedding_model()
            query_embedding = model.encode(query)
            
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            # Vector similarity search
            rows = conn.execute("""
                SELECT n.*, 
                       vec_distance_cosine(ne.embedding, ?) as similarity
                FROM note_embeddings ne
                JOIN notes n ON n.id = ne.note_id
                WHERE n.user_id = ?
                ORDER BY similarity
                LIMIT ?
            """, (query_embedding.tobytes(), user_id, limit)).fetchall()
            
            conn.close()
            
            results = []
            for row in rows:
                # Create snippet from content
                snippet = self._create_snippet(row['content'], query)
                
                results.append(SearchResult(
                    note_id=row['id'],
                    title=row['title'],
                    content=row['content'],
                    summary=row['summary'],
                    tags=row['tags'].split(',') if row['tags'] else [],
                    timestamp=row['timestamp'],
                    score=1 - row['similarity'],  # Convert distance to similarity
                    snippet=snippet,
                    match_type='semantic'
                ))
            
            return results
            
        except Exception as e:
            print(f"Semantic search failed: {e}")
            return []
    
    def _hybrid_search(self, query: str, user_id: int, limit: int) -> List[SearchResult]:
        """Combine FTS and semantic search results"""
        
        # Get results from both methods
        fts_results = self._fts_search(query, user_id, limit)
        semantic_results = self._semantic_search(query, user_id, limit // 2)
        
        # Combine and deduplicate
        combined = {}
        
        # Add FTS results with higher weight
        for result in fts_results:
            combined[result.note_id] = result
            combined[result.note_id].score *= 1.2  # Boost FTS scores
        
        # Add semantic results
        for result in semantic_results:
            if result.note_id in combined:
                # Average the scores if found in both
                existing = combined[result.note_id]
                existing.score = (existing.score + result.score) / 2
                existing.match_type = 'hybrid'
            else:
                combined[result.note_id] = result
        
        # Sort by combined score
        results = list(combined.values())
        results.sort(key=lambda x: x.score, reverse=True)
        
        return results[:limit]
    
    def _prepare_fts_query(self, query: str) -> str:
        """Prepare FTS5 query with proper escaping and enhancement"""
        # Handle special characters
        query = re.sub(r'[^\w\s#-]', ' ', query)
        
        # Split into terms
        terms = query.strip().split()
        
        if not terms:
            return '""'
        
        # Build FTS query with phrase and proximity
        fts_terms = []
        for term in terms:
            if term.startswith('#'):
                # Tag search
                fts_terms.append(f'tags:"{term[1:]}"')
            else:
                # Regular term with prefix matching
                fts_terms.append(f'"{term}"*')
        
        return ' '.join(fts_terms)
    
    def _create_snippet(self, content: str, query: str, max_length: int = 150) -> str:
        """Create a snippet highlighting query terms"""
        words = content.split()
        query_words = query.lower().split()
        
        # Find best match position
        best_pos = 0
        best_score = 0
        
        for i in range(len(words)):
            score = 0
            for j in range(min(20, len(words) - i)):  # Check next 20 words
                word = words[i + j].lower()
                if any(qw in word for qw in query_words):
                    score += 1
            if score > best_score:
                best_score = score
                best_pos = i
        
        # Extract snippet around best position
        start = max(0, best_pos - 10)
        end = min(len(words), best_pos + 15)
        snippet_words = words[start:end]
        
        # Highlight query terms
        highlighted = []
        for word in snippet_words:
            if any(qw in word.lower() for qw in query_words):
                highlighted.append(f"<mark>{word}</mark>")
            else:
                highlighted.append(word)
        
        snippet = ' '.join(highlighted)
        if len(snippet) > max_length:
            snippet = snippet[:max_length] + '...'
        
        return snippet
    
    def log_search(self, user_id: int, query: str, results_count: int, search_type: str):
        """Log search for analytics"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO search_analytics (user_id, query, results_count, search_type)
            VALUES (?, ?, ?, ?)
        """, (user_id, query, results_count, search_type))
        conn.commit()
        conn.close()
    
    def get_popular_searches(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get popular search terms for user"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        rows = conn.execute("""
            SELECT query, COUNT(*) as count, MAX(timestamp) as last_used
            FROM search_analytics 
            WHERE user_id = ? AND query != ''
            GROUP BY query
            ORDER BY count DESC, last_used DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
        
        conn.close()
        
        return [dict(row) for row in rows]


# Enhanced search API endpoints
from fastapi import Query
from typing import Optional

@app.get("/api/search/enhanced")
async def enhanced_search(
    q: str = Query(..., description="Search query"),
    type: str = Query("hybrid", description="Search type: fts, semantic, or hybrid"),
    limit: int = Query(20, description="Number of results"),
    user_id: int = Depends(get_current_user_id)
):
    """Enhanced search endpoint"""
    
    search_engine = EnhancedSearchEngine(str(settings.db_path))
    results = search_engine.search(q, user_id, limit, type)
    
    # Log the search
    search_engine.log_search(user_id, q, len(results), type)
    
    return {
        "query": q,
        "results": [
            {
                "id": r.note_id,
                "title": r.title,
                "summary": r.summary,
                "tags": r.tags,
                "timestamp": r.timestamp,
                "score": r.score,
                "snippet": r.snippet,
                "match_type": r.match_type
            } for r in results
        ],
        "total": len(results),
        "search_type": type
    }

@app.get("/api/search/suggestions")
async def search_suggestions(
    q: str = Query(..., description="Partial query"),
    user_id: int = Depends(get_current_user_id)
):
    """Get search suggestions based on popular searches and content"""
    
    search_engine = EnhancedSearchEngine(str(settings.db_path))
    popular = search_engine.get_popular_searches(user_id, 5)
    
    # Get tag suggestions
    conn = sqlite3.connect(str(settings.db_path))
    tag_matches = conn.execute("""
        SELECT DISTINCT tags FROM notes 
        WHERE user_id = ? AND tags LIKE ?
        LIMIT 5
    """, (user_id, f"%{q}%")).fetchall()
    conn.close()
    
    suggestions = []
    
    # Add popular searches that match
    for search in popular:
        if q.lower() in search['query'].lower():
            suggestions.append({
                "text": search['query'],
                "type": "recent",
                "count": search['count']
            })
    
    # Add tag suggestions
    for tag_row in tag_matches:
        tags = tag_row[0].split(',')
        for tag in tags:
            tag = tag.strip()
            if q.lower() in tag.lower() and tag not in [s['text'] for s in suggestions]:
                suggestions.append({
                    "text": f"#{tag}",
                    "type": "tag",
                    "count": 0
                })
    
    return {"suggestions": suggestions[:10]}

# Background task to reindex embeddings
@app.post("/api/search/reindex")
async def reindex_embeddings(
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id)
):
    """Reindex all embeddings for better search"""
    
    def reindex_user_notes(user_id: int):
        search_engine = EnhancedSearchEngine(str(settings.db_path))
        conn = sqlite3.connect(str(settings.db_path))
        
        notes = conn.execute("""
            SELECT id, title, content, summary, tags, actions 
            FROM notes WHERE user_id = ?
        """, (user_id,)).fetchall()
        
        for note in notes:
            search_engine.index_note(
                note[0], note[1], note[2], 
                note[3], note[4] or '', note[5] or ''
            )
        
        conn.close()
    
    background_tasks.add_task(reindex_user_notes, user_id)
    return {"status": "reindexing started"}
