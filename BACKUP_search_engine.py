# Enhanced Search Engine with FTS5
import sqlite3
import re
from typing import List, Dict, Optional
from dataclasses import dataclass
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
    match_type: str

class EnhancedSearchEngine:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_database()
        
    def _init_database(self):
        """Initialize database with FTS5"""
        conn = sqlite3.connect(self.db_path)
        
        # Create enhanced FTS5 table
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts5 USING fts5(
                title, content, summary, tags, actions,
                content='notes', content_rowid='id',
                tokenize='porter unicode61'
            )
        """)
        
        # Create search analytics
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query TEXT,
                results_count INTEGER,
                search_type TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.close()
    
    def search(self, query: str, user_id: int, limit: int = 20) -> List[SearchResult]:
        """Enhanced FTS search"""
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
                title=row['title'] or '',
                content=row['content'] or '',
                summary=row['summary'] or '',
                tags=row['tags'].split(',') if row['tags'] else [],
                timestamp=row['timestamp'] or '',
                score=abs(row['fts_score']),
                snippet=row['snippet'] or '',
                match_type='fts'
            ))
        
        return results
    
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
    
    def log_search(self, user_id: int, query: str, results_count: int, search_type: str = 'fts'):
        """Log search for analytics"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO search_analytics (user_id, query, results_count, search_type)
            VALUES (?, ?, ?, ?)
        """, (user_id, query, results_count, search_type))
        conn.commit()
        conn.close()
