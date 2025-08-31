#!/usr/bin/env python3
"""
BM25 Sparse Search Engine for Second Brain
Implements BM25 keyword search for better exact term matching
"""

import logging
import sqlite3
import time
from typing import List, Dict
from dataclasses import dataclass
import re

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False

from config import settings

logger = logging.getLogger(__name__)

@dataclass
class SparseSearchResult:
    """Result from BM25 sparse search"""
    note_id: int
    title: str
    content: str
    summary: str
    tags: List[str]
    timestamp: str
    bm25_score: float
    snippet: str
    match_type: str = 'sparse'
    matched_terms: List[str] = None

class BM25SparseSearchEngine:
    """BM25-based sparse search for keyword matching"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.bm25_index = None
        self.document_metadata = {}  # Maps doc_idx to note metadata
        self.last_update = None
        
        # BM25 parameters (can be tuned)
        self.k1 = 1.2  # Term frequency saturation parameter
        self.b = 0.75  # Length normalization parameter
        
        if BM25_AVAILABLE:
            self._init_index()
        else:
            logger.warning("BM25 not available - install rank-bm25")
    
    def _init_index(self):
        """Initialize BM25 index from database"""
        try:
            logger.info("Initializing BM25 sparse search index...")
            
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            # Get all notes for indexing
            rows = conn.execute("""
                SELECT id, title, content, summary, tags, timestamp
                FROM notes
                ORDER BY id
            """).fetchall()
            
            if not rows:
                logger.warning("No notes found for BM25 indexing")
                return
            
            # Prepare documents for BM25
            documents = []
            self.document_metadata = {}
            
            for i, row in enumerate(rows):
                # Combine text fields for indexing
                doc_text = self._prepare_document_for_indexing(dict(row))
                
                # Tokenize document  
                tokenized_doc = self._tokenize_text(doc_text)
                documents.append(tokenized_doc)
                
                # Store metadata mapping
                self.document_metadata[i] = {
                    'note_id': row['id'],
                    'title': row['title'] or '',
                    'content': row['content'] or '',
                    'summary': row['summary'] or '',
                    'tags': row['tags'].split(',') if row['tags'] else [],
                    'timestamp': row['timestamp'] or '',
                    'original_text': doc_text
                }
            
            # Build BM25 index
            self.bm25_index = BM25Okapi(documents, k1=self.k1, b=self.b)
            self.last_update = time.time()
            
            logger.info(f"✅ BM25 index built with {len(documents)} documents")
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to initialize BM25 index: {e}")
            self.bm25_index = None
    
    def _prepare_document_for_indexing(self, note: Dict) -> str:
        """Prepare note content for BM25 indexing"""
        parts = []
        
        # Add title with higher weight (repeat 2x for importance)
        if note.get('title'):
            title_text = note['title']
            parts.extend([title_text, title_text])  # Double weight for title
        
        # Add summary
        if note.get('summary'):
            parts.append(note['summary'])
        
        # Add main content
        if note.get('content'):
            content = note['content']
            # Clean content but preserve important keywords
            content = re.sub(r'\s+', ' ', content).strip()
            if len(content) > 2000:  # Limit very long content
                content = content[:2000] + "..."
            parts.append(content)
        
        # Add tags (repeat for importance in keyword matching)
        if note.get('tags'):
            tags = note['tags'] if isinstance(note['tags'], list) else note['tags'].split(',')
            tags_text = ' '.join(tag.strip() for tag in tags if tag.strip())
            if tags_text:
                parts.extend([tags_text, tags_text])  # Double weight for tags
        
        return ' '.join(parts)
    
    def _tokenize_text(self, text: str) -> List[str]:
        """Tokenize text for BM25 (preserving important technical terms)"""
        if not text:
            return []
        
        # Convert to lowercase but preserve some patterns
        text = text.lower()
        
        # Split on whitespace and punctuation but keep some technical terms
        # This regex preserves:
        # - Alphanumeric words
        # - Technical terms with underscores (e.g., machine_learning)
        # - Hyphenated terms (e.g., cross-validation)
        # - File extensions (e.g., .py, .json)
        tokens = re.findall(r'\b\w+(?:[._-]\w+)*\b|\w+', text)
        
        # Filter out very short tokens and stopwords (basic list)
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 
            'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might', 'must',
            'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
        }
        
        filtered_tokens = [
            token for token in tokens 
            if len(token) > 1 and token not in stopwords
        ]
        
        return filtered_tokens
    
    def _generate_snippet_with_highlights(self, text: str, matched_terms: List[str], max_length: int = 200) -> str:
        """Generate snippet with matched terms highlighted"""
        if not text or not matched_terms:
            return text[:max_length] + "..." if len(text) > max_length else text
        
        text_lower = text.lower()
        
        # Find best position that contains the most matched terms
        best_pos = 0
        max_matches = 0
        
        for i in range(0, max(1, len(text) - max_length), 20):
            snippet_text = text_lower[i:i + max_length]
            matches = sum(1 for term in matched_terms if term.lower() in snippet_text)
            if matches > max_matches:
                max_matches = matches
                best_pos = i
        
        # Extract snippet
        snippet = text[best_pos:best_pos + max_length]
        
        # Add ellipsis if needed
        if best_pos > 0:
            snippet = "..." + snippet
        if best_pos + max_length < len(text):
            snippet = snippet + "..."
        
        return snippet.strip()
    
    def search(self, query: str, user_id: int, limit: int = 20, 
               min_score: float = 0.1) -> List[SparseSearchResult]:
        """Perform BM25 sparse search"""
        if not self.bm25_index or not BM25_AVAILABLE:
            logger.warning("BM25 search not available")
            return []
        
        if not query.strip():
            return []
        
        start_time = time.time()
        
        try:
            # Tokenize query
            query_tokens = self._tokenize_text(query)
            if not query_tokens:
                return []
            
            logger.debug(f"BM25 query tokens: {query_tokens}")
            
            # Get BM25 scores for all documents
            doc_scores = self.bm25_index.get_scores(query_tokens)
            
            # Create results with scores and metadata
            results = []
            for doc_idx, score in enumerate(doc_scores):
                if score < min_score:
                    continue
                
                if doc_idx not in self.document_metadata:
                    continue
                
                metadata = self.document_metadata[doc_idx]
                
                # Check user access (simple approach - in production you'd want proper DB filtering)
                conn = sqlite3.connect(self.db_path)
                user_check = conn.execute(
                    "SELECT 1 FROM notes WHERE id = ? AND user_id = ?",
                    (metadata['note_id'], user_id)
                ).fetchone()
                conn.close()
                
                if not user_check:
                    continue
                
                # Find which query terms matched
                original_text_lower = metadata['original_text'].lower()
                matched_terms = [token for token in query_tokens if token in original_text_lower]
                
                # Generate snippet with highlighting context
                snippet = self._generate_snippet_with_highlights(
                    metadata['content'] or metadata['summary'] or metadata['title'],
                    matched_terms
                )
                
                result = SparseSearchResult(
                    note_id=metadata['note_id'],
                    title=metadata['title'],
                    content=metadata['content'],
                    summary=metadata['summary'], 
                    tags=metadata['tags'],
                    timestamp=metadata['timestamp'],
                    bm25_score=float(score),
                    snippet=snippet,
                    match_type='sparse',
                    matched_terms=matched_terms
                )
                
                results.append(result)
            
            # Sort by BM25 score (descending)
            results.sort(key=lambda x: x.bm25_score, reverse=True)
            
            # Apply limit
            results = results[:limit]
            
            execution_time = time.time() - start_time
            logger.info(f"BM25 search completed: {len(results)} results in {execution_time:.3f}s")
            
            return results
            
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []
    
    def get_top_documents(self, query: str, k: int = 10) -> List[Tuple[int, float]]:
        """Get top-k document indices and scores for a query"""
        if not self.bm25_index:
            return []
        
        try:
            query_tokens = self._tokenize_text(query)
            if not query_tokens:
                return []
            
            # Get top-k documents
            doc_scores = self.bm25_index.get_scores(query_tokens)
            
            # Get top-k indices and scores
            top_indices = []
            for doc_idx, score in enumerate(doc_scores):
                top_indices.append((doc_idx, float(score)))
            
            # Sort by score and get top-k
            top_indices.sort(key=lambda x: x[1], reverse=True)
            return top_indices[:k]
            
        except Exception as e:
            logger.error(f"Failed to get top documents: {e}")
            return []
    
    def update_index(self, force_rebuild: bool = False):
        """Update the BM25 index (checks if needed unless forced)"""
        if not BM25_AVAILABLE:
            return False
        
        try:
            # Check if update needed
            if not force_rebuild and self.bm25_index and self.last_update:
                # Simple check - could be improved with change tracking
                conn = sqlite3.connect(self.db_path)
                latest_timestamp = conn.execute(
                    "SELECT MAX(timestamp) FROM notes"
                ).fetchone()[0]
                conn.close()
                
                if latest_timestamp and self.last_update:
                    # Parse timestamp to compare (basic approach)
                    # In production, you'd want proper timestamp comparison
                    pass
            
            # Rebuild index
            self._init_index()
            return True
            
        except Exception as e:
            logger.error(f"Failed to update BM25 index: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get BM25 search statistics"""
        stats = {
            'bm25_available': BM25_AVAILABLE,
            'index_built': self.bm25_index is not None,
            'total_documents': len(self.document_metadata) if self.document_metadata else 0,
            'last_update': self.last_update,
            'parameters': {
                'k1': self.k1,
                'b': self.b
            }
        }
        
        return stats

# Global sparse search instance
_sparse_search_engine = None

def get_sparse_search_engine() -> BM25SparseSearchEngine:
    """Get global sparse search engine instance"""
    global _sparse_search_engine
    if _sparse_search_engine is None:
        _sparse_search_engine = BM25SparseSearchEngine(str(settings.db_path))
    return _sparse_search_engine
