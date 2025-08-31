"""Alternate semantic search engine (legacy path).

Kept for reference and experiments. The live app uses the unified
`services/SearchService` for keyword/semantic/hybrid search.
"""

import numpy as np
import sqlite3
import json
import pickle
from typing import List, Dict, Tuple, Optional, Union
from dataclasses import dataclass
from pathlib import Path
import logging
from datetime import datetime
import time
import re

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.feature_extraction.text import TfidfVectorizer
    SEMANTIC_SEARCH_AVAILABLE = True
except ImportError:
    SEMANTIC_SEARCH_AVAILABLE = False
    print("⚠️  Semantic search dependencies not available. Install: pip install sentence-transformers scikit-learn")

from config import settings

# Import re-ranker (optional dependency)
try:
    from reranker import get_reranker, RerankResult
    RERANKER_AVAILABLE = True
except ImportError:
    RERANKER_AVAILABLE = False
    RerankResult = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SemanticSearchResult:
    note_id: int
    title: str
    content: str
    summary: str
    tags: List[str]
    timestamp: str
    semantic_score: float
    fts_score: float
    combined_score: float
    snippet: str
    match_type: str  # 'semantic', 'fts', 'hybrid'
    embedding_similarity: float = 0.0

class SemanticSearchEngine:
    """Advanced search engine with semantic similarity and hybrid ranking"""
    
    def __init__(self, db_path: str, model_name: str = "all-MiniLM-L6-v2"):
        self.db_path = db_path
        self.model_name = model_name
        self.model = None
        self.embeddings_cache_path = Path(settings.base_dir) / "embeddings_cache.pkl"
        self.model_path = Path(settings.base_dir) / "sentence_transformer_model"
        
        if SEMANTIC_SEARCH_AVAILABLE:
            self._init_model()
        
        self._init_database()
    
    def _init_model(self):
        """Initialize the sentence transformer model"""
        try:
            logger.info(f"Loading sentence transformer model: {self.model_name}")
            
            # Try to load from cache first
            if self.model_path.exists():
                logger.info(f"Loading cached model from {self.model_path}")
                self.model = SentenceTransformer(str(self.model_path))
            else:
                logger.info(f"Downloading model {self.model_name} (first time only)")
                self.model = SentenceTransformer(self.model_name)
                # Cache the model locally
                self.model_path.mkdir(exist_ok=True)
                self.model.save(str(self.model_path))
                logger.info(f"Model cached to {self.model_path}")
            
            logger.info("✅ Semantic search model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load semantic search model: {e}")
            self.model = None
    
    def _init_database(self):
        """Initialize database tables for semantic search"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Create embeddings table (compatible with existing schema)
        c.execute("""
            CREATE TABLE IF NOT EXISTS note_embeddings (
                note_id INTEGER PRIMARY KEY,
                embedding BLOB NOT NULL,
                content_hash TEXT,
                model_version TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE
            )
        """)
        
        # Create search performance table
        c.execute("""
            CREATE TABLE IF NOT EXISTS search_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                search_type TEXT NOT NULL,
                results_count INTEGER,
                execution_time REAL,
                user_id INTEGER,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index for faster lookups
        c.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_hash ON note_embeddings(content_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_updated ON note_embeddings(updated_at)")
        
        conn.commit()
        conn.close()
    
    def _generate_content_hash(self, content: str) -> str:
        """Generate hash of content for caching embeddings"""
        import hashlib
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _get_note_content_for_embedding(self, note: Dict) -> str:
        """Extract and format content for embedding generation"""
        parts = []
        
        # Add title with more weight
        if note.get('title'):
            parts.append(f"Title: {note['title']}")
        
        # Add summary if available
        if note.get('summary'):
            parts.append(f"Summary: {note['summary']}")
        
        # Add main content
        if note.get('content'):
            content = note['content']
            # Clean up content - remove excessive whitespace
            content = re.sub(r'\s+', ' ', content).strip()
            # Truncate very long content to avoid token limits
            if len(content) > 1000:
                content = content[:1000] + "..."
            parts.append(f"Content: {content}")
        
        # Add extracted text from files (OCR, PDF text) with higher weight
        if note.get('extracted_text'):
            extracted = note['extracted_text']
            # Clean and truncate extracted text
            extracted = re.sub(r'\s+', ' ', extracted).strip()
            if len(extracted) > 800:  # Slightly smaller to leave room for other content
                extracted = extracted[:800] + "..."
            parts.append(f"File Content: {extracted}")
        
        # Add file type context for better semantic understanding
        if note.get('file_type'):
            file_type = note['file_type']
            file_mime = note.get('file_mime_type', '')
            if file_type == 'image' or file_mime.startswith('image/'):
                parts.append("Content Type: Image with text content")
            elif file_type == 'document' or file_mime == 'application/pdf':
                parts.append("Content Type: Document with text content")
            elif file_type == 'audio':
                parts.append("Content Type: Audio transcription")
        
        # Add tags
        if note.get('tags'):
            parts.append(f"Tags: {note['tags']}")
        
        # Add actions if available
        if note.get('actions'):
            parts.append(f"Actions: {note['actions']}")
        
        return " | ".join(parts)
    
    def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for given text"""
        if not self.model or not SEMANTIC_SEARCH_AVAILABLE:
            return None
        
        try:
            # Generate embedding
            embedding = self.model.encode([text], convert_to_tensor=False)[0]
            return embedding.astype(np.float32)  # Reduce memory usage
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None
    
    def update_note_embedding(self, note_id: int, force_update: bool = False) -> bool:
        """Update embedding for a specific note"""
        if not self.model:
            return False
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            # Get note data including file-related fields
            note = c.execute("""
                SELECT id, title, content, summary, tags, actions, 
                       extracted_text, file_type, file_mime_type
                FROM notes WHERE id = ?
            """, (note_id,)).fetchone()
            
            if not note:
                logger.warning(f"Note {note_id} not found")
                return False
            
            # Convert to dict
            note_dict = {
                'id': note[0], 'title': note[1], 'content': note[2],
                'summary': note[3], 'tags': note[4], 'actions': note[5],
                'extracted_text': note[6], 'file_type': note[7], 'file_mime_type': note[8]
            }
            
            # Generate content for embedding
            content_for_embedding = self._get_note_content_for_embedding(note_dict)
            content_hash = self._generate_content_hash(content_for_embedding)
            
            # Check if embedding already exists and is current
            if not force_update:
                existing = c.execute("""
                    SELECT content_hash FROM note_embeddings 
                    WHERE note_id = ? AND (content_hash = ? OR content_hash IS NULL) AND (model_version = ? OR model_version IS NULL)
                """, (note_id, content_hash, self.model_name)).fetchone()
                
                if existing and existing[0] == content_hash:
                    logger.debug(f"Embedding for note {note_id} is up to date")
                    return True
            
            # Generate new embedding
            embedding = self.generate_embedding(content_for_embedding)
            if embedding is None:
                return False
            
            # Store embedding in database
            embedding_blob = pickle.dumps(embedding)
            
            # Use INSERT OR REPLACE with proper column handling
            c.execute("""
                INSERT OR REPLACE INTO note_embeddings 
                (note_id, embedding_model, embedding, embedding_dim, content_hash, model_version, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (note_id, self.model_name, embedding_blob, len(embedding), content_hash, self.model_name))
            
            conn.commit()
            logger.debug(f"✅ Updated embedding for note {note_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update embedding for note {note_id}: {e}")
            return False
        finally:
            conn.close()
    
    def batch_update_embeddings(self, limit: int = 100, force_update: bool = False) -> Dict[str, int]:
        """Update embeddings for multiple notes in batch"""
        if not self.model:
            return {"error": "Model not available", "updated": 0, "failed": 0}
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            # Get notes that need embedding updates
            if force_update:
                notes_query = "SELECT id FROM notes ORDER BY timestamp DESC LIMIT ?"
                notes = c.execute(notes_query, (limit,)).fetchall()
            else:
                # Get notes without embeddings or with outdated embeddings
                notes_query = """
                    SELECT n.id FROM notes n
                    LEFT JOIN note_embeddings e ON n.id = e.note_id
                    WHERE e.note_id IS NULL 
                       OR e.model_version != ?
                    ORDER BY n.timestamp DESC 
                    LIMIT ?
                """
                notes = c.execute(notes_query, (self.model_name, limit)).fetchall()
            
            updated = 0
            failed = 0
            
            logger.info(f"Updating embeddings for {len(notes)} notes...")
            
            for (note_id,) in notes:
                if self.update_note_embedding(note_id, force_update):
                    updated += 1
                else:
                    failed += 1
                
                # Log progress every 10 notes
                if (updated + failed) % 10 == 0:
                    logger.info(f"Progress: {updated} updated, {failed} failed")
            
            logger.info(f"✅ Batch embedding update complete: {updated} updated, {failed} failed")
            return {"updated": updated, "failed": failed, "total": len(notes)}
            
        except Exception as e:
            logger.error(f"Batch embedding update failed: {e}")
            return {"error": str(e), "updated": 0, "failed": 0}
        finally:
            conn.close()
    
    def semantic_search(self, query: str, user_id: int, limit: int = 20, 
                       similarity_threshold: float = 0.3) -> List[SemanticSearchResult]:
        """Perform semantic similarity search"""
        if not self.model:
            logger.warning("Semantic search not available - model not loaded")
            return []
        
        start_time = time.time()
        
        try:
            # Generate query embedding
            query_embedding = self.generate_embedding(query)
            if query_embedding is None:
                return []
            
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Get all notes with embeddings for this user
            notes_with_embeddings = c.execute("""
                SELECT n.id, n.title, n.content, n.summary, n.tags, n.timestamp,
                       e.embedding
                FROM notes n
                JOIN note_embeddings e ON n.id = e.note_id
                WHERE n.user_id = ?
                ORDER BY n.timestamp DESC
            """, (user_id,)).fetchall()
            
            if not notes_with_embeddings:
                logger.info("No notes with embeddings found")
                return []
            
            results = []
            
            # Calculate similarities
            for note_data in notes_with_embeddings:
                note_id, title, content, summary, tags, timestamp, embedding_blob = note_data
                
                try:
                    # Deserialize embedding
                    note_embedding = pickle.loads(embedding_blob)
                    
                    # Calculate cosine similarity
                    similarity = cosine_similarity(
                        query_embedding.reshape(1, -1),
                        note_embedding.reshape(1, -1)
                    )[0][0]
                    
                    # Apply threshold
                    if similarity < similarity_threshold:
                        continue
                    
                    # Generate snippet
                    snippet = self._generate_snippet(content or summary or title, query)
                    
                    # Create result
                    result = SemanticSearchResult(
                        note_id=note_id,
                        title=title or "",
                        content=content or "",
                        summary=summary or "",
                        tags=tags.split(",") if tags else [],
                        timestamp=timestamp or "",
                        semantic_score=float(similarity),
                        fts_score=0.0,
                        combined_score=float(similarity),
                        snippet=snippet,
                        match_type='semantic',
                        embedding_similarity=float(similarity)
                    )
                    
                    results.append(result)
                    
                except Exception as e:
                    logger.error(f"Error processing note {note_id}: {e}")
                    continue
            
            # Sort by similarity score
            results.sort(key=lambda x: x.semantic_score, reverse=True)
            
            # Apply limit
            results = results[:limit]
            
            # Log search performance
            execution_time = time.time() - start_time
            c.execute("""
                INSERT INTO search_performance 
                (query, search_type, results_count, execution_time, user_id)
                VALUES (?, ?, ?, ?, ?)
            """, (query, 'semantic', len(results), execution_time, user_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Semantic search completed: {len(results)} results in {execution_time:.2f}s")
            return results
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    def _generate_snippet(self, text: str, query: str, max_length: int = 200) -> str:
        """Generate a snippet highlighting relevant parts"""
        if not text:
            return ""
        
        # Simple snippet generation - find query terms in text
        query_terms = query.lower().split()
        text_lower = text.lower()
        
        # Find best position to extract snippet
        best_pos = 0
        max_matches = 0
        
        # Search for position with most query term matches
        for i in range(0, len(text) - max_length, 20):
            snippet_text = text_lower[i:i + max_length]
            matches = sum(1 for term in query_terms if term in snippet_text)
            if matches > max_matches:
                max_matches = matches
                best_pos = i
        
        # Extract snippet
        snippet = text[best_pos:best_pos + max_length]
        
        # Add ellipsis if truncated
        if best_pos > 0:
            snippet = "..." + snippet
        if best_pos + max_length < len(text):
            snippet = snippet + "..."
        
        return snippet.strip()
    
    def reranked_search(self, query: str, user_id: int, limit: int = 8, 
                       use_reranking: bool = True) -> List[SemanticSearchResult]:
        """
        Enhanced search with cross-encoder re-ranking (Priority 1 - Highest ROI)
        
        This method provides the best search quality by:
        1. Getting initial results from hybrid search (FTS + semantic)
        2. Re-ranking top results using cross-encoder for better precision
        3. Returning the most relevant results
        
        Args:
            query: Search query
            user_id: User ID for scoped search
            limit: Final number of results to return
            use_reranking: Whether to use cross-encoder re-ranking
        
        Returns:
            List of re-ranked search results
        """
        if not use_reranking or not RERANKER_AVAILABLE:
            logger.info("Re-ranking disabled or not available, falling back to hybrid search")
            return self.hybrid_search(query, user_id, limit)
        
        start_time = time.time()
        
        try:
            # Get more initial results for better re-ranking
            initial_limit = max(20, limit * 3)  # Get 3x more results for re-ranking
            
            # Get initial results from hybrid search
            initial_results = self.hybrid_search(query, user_id, initial_limit)
            
            if not initial_results:
                logger.info("No initial results found for re-ranking")
                return []
            
            logger.info(f"Got {len(initial_results)} initial results for re-ranking")
            
            # Convert to dict format for re-ranker
            results_for_reranking = []
            for result in initial_results:
                result_dict = {
                    'note_id': result.note_id,
                    'title': result.title,
                    'content': result.content,
                    'summary': result.summary,
                    'tags': result.tags,
                    'timestamp': result.timestamp,
                    'snippet': result.snippet,
                    'combined_score': result.combined_score,
                    'semantic_score': result.semantic_score,
                    'fts_score': result.fts_score,
                    'match_type': result.match_type
                }
                results_for_reranking.append(result_dict)
            
            # Apply cross-encoder re-ranking
            reranker = get_reranker()
            reranked_results = reranker.rerank_results(query, results_for_reranking, limit)
            
            # Convert back to SemanticSearchResult format
            final_results = []
            for rerank_result in reranked_results:
                semantic_result = SemanticSearchResult(
                    note_id=rerank_result.note_id,
                    title=rerank_result.title,
                    content=rerank_result.content,
                    summary=rerank_result.summary,
                    tags=rerank_result.tags,
                    timestamp=rerank_result.timestamp,
                    semantic_score=0.0,  # Original semantic score lost in conversion
                    fts_score=0.0,       # Original FTS score lost in conversion  
                    combined_score=rerank_result.combined_score,  # Use re-ranked score
                    snippet=rerank_result.snippet,
                    match_type='reranked_hybrid',
                    embedding_similarity=rerank_result.rerank_score
                )
                final_results.append(semantic_result)
            
            # Log performance
            execution_time = time.time() - start_time
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                INSERT INTO search_performance 
                (query, search_type, results_count, execution_time, user_id)
                VALUES (?, ?, ?, ?, ?)
            """, (query, 'reranked_hybrid', len(final_results), execution_time, user_id))
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Re-ranked search completed: {len(final_results)} results in {execution_time:.3f}s")
            return final_results
            
        except Exception as e:
            logger.error(f"Re-ranked search failed, falling back to hybrid search: {e}")
            return self.hybrid_search(query, user_id, limit)

    def hybrid_search(self, query: str, user_id: int, limit: int = 20,
                     semantic_weight: float = 0.6, fts_weight: float = 0.4) -> List[SemanticSearchResult]:
        """Perform hybrid search combining FTS and semantic similarity"""
        if not self.model:
            # Fall back to FTS only
            return self._fts_search_fallback(query, user_id, limit)
        
        start_time = time.time()
        
        try:
            # Get FTS results
            fts_results = self._get_fts_results(query, user_id, limit * 2)  # Get more for better mixing
            
            # Get semantic results
            semantic_results = self.semantic_search(query, user_id, limit * 2)
            
            # Combine and rank results
            combined_results = self._combine_search_results(
                fts_results, semantic_results, semantic_weight, fts_weight
            )
            
            # Log performance
            execution_time = time.time() - start_time
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                INSERT INTO search_performance 
                (query, search_type, results_count, execution_time, user_id)
                VALUES (?, ?, ?, ?, ?)
            """, (query, 'hybrid', len(combined_results[:limit]), execution_time, user_id))
            conn.commit()
            conn.close()
            
            logger.info(f"Hybrid search completed: {len(combined_results[:limit])} results in {execution_time:.2f}s")
            return combined_results[:limit]
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return self._fts_search_fallback(query, user_id, limit)
    
    def _get_fts_results(self, query: str, user_id: int, limit: int) -> List[SemanticSearchResult]:
        """Get FTS search results"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            # Clean query for FTS
            fts_query = self._prepare_fts_query(query)
            
            results = c.execute("""
                SELECT n.id, n.title, n.content, n.summary, n.tags, n.timestamp,
                       bm25(notes_fts) as fts_score,
                       snippet(notes_fts, 1, '<mark>', '</mark>', '...', 32) as snippet
                FROM notes_fts fts
                JOIN notes n ON n.id = fts.rowid
                WHERE notes_fts MATCH ? AND n.user_id = ?
                ORDER BY bm25(notes_fts)
                LIMIT ?
            """, (fts_query, user_id, limit)).fetchall()
            
            fts_results = []
            for row in results:
                result = SemanticSearchResult(
                    note_id=row[0],
                    title=row[1] or "",
                    content=row[2] or "",
                    summary=row[3] or "",
                    tags=row[4].split(",") if row[4] else [],
                    timestamp=row[5] or "",
                    semantic_score=0.0,
                    fts_score=abs(row[6]) if row[6] else 0.0,
                    combined_score=abs(row[6]) if row[6] else 0.0,
                    snippet=row[7] or "",
                    match_type='fts'
                )
                fts_results.append(result)
            
            return fts_results
            
        except Exception as e:
            logger.error(f"FTS search failed: {e}")
            return []
        finally:
            conn.close()
    
    def _prepare_fts_query(self, query: str) -> str:
        """Prepare query for FTS5"""
        # Clean query
        query = re.sub(r'[^\w\s#-]', ' ', query)
        terms = query.strip().split()
        
        if not terms:
            return '""'
        
        # Build FTS5 query
        fts_terms = []
        for term in terms:
            if term.startswith('#'):
                fts_terms.append(f'tags:"{term[1:]}"')
            else:
                fts_terms.append(f'"{term}"*')
        
        return ' '.join(fts_terms)
    
    def _combine_search_results(self, fts_results: List[SemanticSearchResult], 
                               semantic_results: List[SemanticSearchResult],
                               semantic_weight: float, fts_weight: float) -> List[SemanticSearchResult]:
        """Combine FTS and semantic results with weighted scoring"""
        
        # Create lookup for faster merging
        fts_lookup = {r.note_id: r for r in fts_results}
        semantic_lookup = {r.note_id: r for r in semantic_results}
        
        # Get all unique note IDs
        all_note_ids = set(fts_lookup.keys()) | set(semantic_lookup.keys())
        
        combined_results = []
        
        for note_id in all_note_ids:
            fts_result = fts_lookup.get(note_id)
            semantic_result = semantic_lookup.get(note_id)
            
            # Normalize scores (0-1 range)
            fts_score = fts_result.fts_score if fts_result else 0.0
            semantic_score = semantic_result.semantic_score if semantic_result else 0.0
            
            # Calculate combined score
            combined_score = (semantic_score * semantic_weight) + (fts_score * fts_weight)
            
            # Use the result with more complete data
            base_result = semantic_result or fts_result
            
            # Create combined result
            result = SemanticSearchResult(
                note_id=base_result.note_id,
                title=base_result.title,
                content=base_result.content,
                summary=base_result.summary,
                tags=base_result.tags,
                timestamp=base_result.timestamp,
                semantic_score=semantic_score,
                fts_score=fts_score,
                combined_score=combined_score,
                snippet=base_result.snippet,
                match_type='hybrid',
                embedding_similarity=semantic_score
            )
            
            combined_results.append(result)
        
        # Sort by combined score
        combined_results.sort(key=lambda x: x.combined_score, reverse=True)
        return combined_results
    
    def _fts_search_fallback(self, query: str, user_id: int, limit: int) -> List[SemanticSearchResult]:
        """Fallback to FTS-only search when semantic search is unavailable"""
        logger.info("Using FTS fallback search")
        return self._get_fts_results(query, user_id, limit)
    
    def get_search_stats(self) -> Dict:
        """Get search performance statistics"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            stats = {}
            
            # Total embeddings
            total_embeddings = c.execute("SELECT COUNT(*) FROM note_embeddings").fetchone()[0]
            stats['total_embeddings'] = total_embeddings
            
            # Model info
            stats['model_name'] = self.model_name
            stats['semantic_available'] = self.model is not None
            
            # Recent search performance
            recent_searches = c.execute("""
                SELECT search_type, AVG(execution_time) as avg_time, COUNT(*) as count
                FROM search_performance 
                WHERE timestamp > datetime('now', '-7 days')
                GROUP BY search_type
            """).fetchall()
            
            stats['recent_performance'] = {
                row[0]: {'avg_time': round(row[1], 3), 'count': row[2]}
                for row in recent_searches
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get search stats: {e}")
            return {"error": str(e)}
        finally:
            conn.close()


# Global search engine instance
_search_engine = None

def get_search_engine() -> SemanticSearchEngine:
    """Get global search engine instance"""
    global _search_engine
    if _search_engine is None:
        _search_engine = SemanticSearchEngine(str(settings.db_path))
    return _search_engine
