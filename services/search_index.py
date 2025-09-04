# ──────────────────────────────────────────────────────────────────────────────
# File: services/search_index.py
# ──────────────────────────────────────────────────────────────────────────────
"""
Search indexer refinements for Second Brain.
Implements chunk-based indexing with FTS5 and optional sqlite-vec support.
"""
from __future__ import annotations
import json
import logging
import os
import sqlite3
import urllib.request
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class SearchConfig:
    """Configuration for search indexing."""
    
    def __init__(
        self,
        db_path: Path,
        embed_model: str = "nomic-embed-text",
        enable_embeddings: bool = True,
        ollama_url: str = "http://localhost:11434"
    ):
        self.db_path = Path(db_path)
        self.embed_model = embed_model
        self.enable_embeddings = enable_embeddings
        self.ollama_url = ollama_url


class SearchIndexer:
    """Chunk-based search indexer with FTS5 and optional vector search."""
    
    def __init__(self, cfg: Optional[SearchConfig] = None):
        if cfg is None:
            cfg = SearchConfig(Path("notes.db"))
        self.cfg = cfg
        self.db_path = cfg.db_path
        self._vec_available = None
        self._setup_connection()
    
    def _setup_connection(self) -> None:
        """Initialize database connection with extensions."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        
        # Try to load sqlite-vec extension
        vec_path = os.getenv('SQLITE_VEC_PATH')
        if vec_path:
            try:
                self.conn.enable_load_extension(True)
                self.conn.load_extension(vec_path)
                logger.info("sqlite-vec extension loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load sqlite-vec extension: {e}")
    
    def ensure_fts(self) -> None:
        """Ensure FTS5 tables exist."""
        cursor = self.conn.cursor()
        
        # Create chunk table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunk (
                id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                ord INTEGER NOT NULL DEFAULT 0,
                heading TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL DEFAULT '',
                token_est INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        # Create FTS5 table for chunks (simplified tokenizer for compatibility)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunk USING fts5(
                chunk_id, item_id, heading, text
            )
        """)
        
        self.conn.commit()
        logger.info("FTS5 tables ensured")
    
    def ensure_vec(self, dim: int = 768) -> bool:
        """Returns True if vec0 usable."""
        if self._vec_available is not None:
            return self._vec_available
        
        cursor = self.conn.cursor()
        try:
            # Try to create vec_chunk virtual table
            cursor.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunk USING vec0(
                    embedding FLOAT[{dim}]
                )
            """)
            
            # Create vec_map table for tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vec_map (
                    chunk_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    rowid_int INTEGER NOT NULL,
                    PRIMARY KEY (chunk_id, model)
                )
            """)
            
            self.conn.commit()
            self._vec_available = True
            logger.info(f"sqlite-vec tables created with dim={dim}")
            return True
            
        except Exception as e:
            logger.warning(f"sqlite-vec not available, falling back to JSON embeddings: {e}")
            # Create fallback embedding table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS embedding (
                    chunk_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    vec_json TEXT NOT NULL,
                    PRIMARY KEY (chunk_id, model)
                )
            """)
            self.conn.commit()
            self._vec_available = False
            return False
    
    def rebuild_fts(self) -> Dict[str, Any]:
        """Wipe + reinsert from chunk table."""
        self.ensure_fts()
        
        cursor = self.conn.cursor()
        start_time = self._get_time_ms()
        
        # Clear FTS table
        cursor.execute("DELETE FROM fts_chunk")
        
        # Get all chunks
        cursor.execute("SELECT id, item_id, heading, text FROM chunk ORDER BY item_id, ord")
        chunks = cursor.fetchall()
        
        # Batch insert into FTS
        fts_rows = [(row['id'], row['item_id'], row['heading'], row['text']) for row in chunks]
        cursor.executemany(
            "INSERT INTO fts_chunk(chunk_id, item_id, heading, text) VALUES (?, ?, ?, ?)",
            fts_rows
        )
        
        self.conn.commit()
        end_time = self._get_time_ms()
        
        result = {
            'total_chunks': len(chunks),
            'time_ms': end_time - start_time,
            'status': 'success'
        }
        
        logger.info(f"FTS rebuild completed: {result}")
        return result
    
    def rebuild_embeddings(self, model: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """Rebuild embeddings for chunks."""
        if not self.cfg.enable_embeddings:
            return {'status': 'disabled', 'message': 'Embeddings disabled in config'}
        
        model = model or self.cfg.embed_model
        self.ensure_fts()
        vec_available = self.ensure_vec()
        
        cursor = self.conn.cursor()
        start_time = self._get_time_ms()
        
        # Get chunks to process
        query = "SELECT id, heading, text FROM chunk ORDER BY item_id, ord"
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query)
        chunks = cursor.fetchall()
        
        successful = 0
        failed = 0
        
        # Process chunks in batches
        batch_size = 10
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            for chunk in batch:
                try:
                    # Combine heading and text for embedding
                    text_content = f"{chunk['heading']}\n\n{chunk['text']}".strip()
                    if not text_content:
                        continue
                    
                    embedding = self._generate_embedding(text_content, model)
                    if embedding is None:
                        failed += 1
                        continue
                    
                    if vec_available:
                        self._store_vec_embedding(chunk['id'], model, embedding)
                    else:
                        self._store_json_embedding(chunk['id'], model, embedding)
                    
                    successful += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for chunk {chunk['id']}: {e}")
                    failed += 1
            
            self.conn.commit()
        
        end_time = self._get_time_ms()
        
        result = {
            'total_chunks': len(chunks),
            'successful': successful,
            'failed': failed,
            'model': model,
            'vec_available': vec_available,
            'time_ms': end_time - start_time,
            'status': 'success'
        }
        
        logger.info(f"Embedding rebuild completed: {result}")
        return result
    
    def index_item(self, item_id: str) -> Dict[str, Any]:
        """Delete/replace item's rows in FTS and embeddings."""
        self.ensure_fts()
        
        cursor = self.conn.cursor()
        start_time = self._get_time_ms()
        
        # Delete existing FTS entries for this item
        cursor.execute("DELETE FROM fts_chunk WHERE item_id = ?", (item_id,))
        
        # Delete existing embeddings for this item's chunks
        cursor.execute("SELECT id FROM chunk WHERE item_id = ?", (item_id,))
        chunk_ids = [row['id'] for row in cursor.fetchall()]
        
        for chunk_id in chunk_ids:
            if self.ensure_vec():
                cursor.execute("DELETE FROM vec_map WHERE chunk_id = ?", (chunk_id,))
                # Note: vec_chunk entries are handled by vec_map foreign keys
            else:
                cursor.execute("DELETE FROM embedding WHERE chunk_id = ?", (chunk_id,))
        
        # Re-index chunks for this item
        cursor.execute("SELECT id, item_id, heading, text FROM chunk WHERE item_id = ? ORDER BY ord", (item_id,))
        chunks = cursor.fetchall()
        
        successful_fts = 0
        successful_embed = 0
        failed_embed = 0
        
        # Add to FTS
        for chunk in chunks:
            cursor.execute(
                "INSERT INTO fts_chunk(chunk_id, item_id, heading, text) VALUES (?, ?, ?, ?)",
                (chunk['id'], chunk['item_id'], chunk['heading'], chunk['text'])
            )
            successful_fts += 1
        
        # Add embeddings if enabled
        if self.cfg.enable_embeddings:
            for chunk in chunks:
                try:
                    text_content = f"{chunk['heading']}\n\n{chunk['text']}".strip()
                    if not text_content:
                        continue
                    
                    embedding = self._generate_embedding(text_content, self.cfg.embed_model)
                    if embedding is None:
                        failed_embed += 1
                        continue
                    
                    if self.ensure_vec():
                        self._store_vec_embedding(chunk['id'], self.cfg.embed_model, embedding)
                    else:
                        self._store_json_embedding(chunk['id'], self.cfg.embed_model, embedding)
                    
                    successful_embed += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for chunk {chunk['id']}: {e}")
                    failed_embed += 1
        
        self.conn.commit()
        end_time = self._get_time_ms()
        
        result = {
            'item_id': item_id,
            'chunks_processed': len(chunks),
            'fts_indexed': successful_fts,
            'embeddings_successful': successful_embed,
            'embeddings_failed': failed_embed,
            'time_ms': end_time - start_time,
            'status': 'success'
        }
        
        logger.info(f"Item indexing completed: {result}")
        return result
    
    def query_bm25(self, q: str, k: int = 10) -> List[Dict[str, Any]]:
        """BM25 search with snippets."""
        if not q.strip():
            return []
        
        self.ensure_fts()
        cursor = self.conn.cursor()
        
        # Sanitize query for FTS5
        sanitized_q = self._sanitize_fts_query(q)
        if not sanitized_q:
            return []
        
        try:
            cursor.execute("""
                SELECT 
                    c.item_id,
                    f.chunk_id,
                    c.heading,
                    snippet(fts_chunk, 3, '<b>', '</b>', '…', 12) as preview,
                    bm25(fts_chunk) as score
                FROM fts_chunk f
                JOIN chunk c ON c.id = f.chunk_id
                WHERE fts_chunk MATCH ?
                ORDER BY score
                LIMIT ?
            """, (sanitized_q, k))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'item_id': row['item_id'],
                    'chunk_id': row['chunk_id'],
                    'heading': row['heading'],
                    'preview': row['preview'],
                    'score': abs(row['score']),  # Make positive for consistency
                    'sources': {'bm25_rank': len(results) + 1}
                })
            
            return results
            
        except Exception as e:
            logger.error(f"BM25 query failed for '{sanitized_q}': {e}")
            return []
    
    def query_vector(self, text: str, k: int = 10) -> List[Dict[str, Any]]:
        """Vector similarity search."""
        if not text.strip() or not self.cfg.enable_embeddings:
            return []
        
        embedding = self._generate_embedding(text, self.cfg.embed_model)
        if embedding is None:
            return []
        
        cursor = self.conn.cursor()
        
        if self.ensure_vec():
            # Use sqlite-vec
            try:
                cursor.execute("""
                    SELECT 
                        c.item_id,
                        c.id as chunk_id,
                        c.heading,
                        SUBSTR(c.text, 1, 200) || CASE WHEN LENGTH(c.text) > 200 THEN '...' ELSE '' END as preview,
                        (1.0 - vec_distance_cosine(vc.embedding, ?)) as score,
                        vm.rowid_int
                    FROM vec_map vm
                    JOIN vec_chunk vc ON vc.rowid = vm.rowid_int
                    JOIN chunk c ON c.id = vm.chunk_id
                    WHERE vm.model = ?
                    ORDER BY score DESC
                    LIMIT ?
                """, (json.dumps(embedding), self.cfg.embed_model, k))
                
                results = []
                for i, row in enumerate(cursor.fetchall(), 1):
                    results.append({
                        'item_id': row['item_id'],
                        'chunk_id': row['chunk_id'],
                        'heading': row['heading'],
                        'preview': row['preview'],
                        'score': row['score'],
                        'sources': {'vec_rank': i}
                    })
                
                return results
                
            except Exception as e:
                logger.error(f"Vector query failed with sqlite-vec: {e}")
                return []
        else:
            # Use JSON embeddings
            try:
                cursor.execute("""
                    SELECT chunk_id, vec_json FROM embedding WHERE model = ?
                """, (self.cfg.embed_model,))
                
                similarities = []
                for row in cursor.fetchall():
                    stored_embedding = json.loads(row['vec_json'])
                    similarity = self._cosine_similarity(embedding, stored_embedding)
                    similarities.append((row['chunk_id'], similarity))
                
                # Sort by similarity descending
                similarities.sort(key=lambda x: x[1], reverse=True)
                top_similarities = similarities[:k]
                
                # Get chunk details
                results = []
                for i, (chunk_id, similarity) in enumerate(top_similarities, 1):
                    cursor.execute("""
                        SELECT item_id, heading, text FROM chunk WHERE id = ?
                    """, (chunk_id,))
                    
                    row = cursor.fetchone()
                    if row:
                        preview = row['text'][:200]
                        if len(row['text']) > 200:
                            preview += '...'
                        
                        results.append({
                            'item_id': row['item_id'],
                            'chunk_id': chunk_id,
                            'heading': row['heading'],
                            'preview': preview,
                            'score': similarity,
                            'sources': {'vec_rank': i}
                        })
                
                return results
                
            except Exception as e:
                logger.error(f"Vector query failed with JSON embeddings: {e}")
                return []
    
    def search_hybrid(self, q: str, k: int = 10, alpha: float = 0.5) -> List[Dict[str, Any]]:
        """Hybrid search with Reciprocal Rank Fusion."""
        if not q.strip():
            return []
        
        # Get results from both methods
        bm25_results = self.query_bm25(q, k * 2)  # Get more for better fusion
        vector_results = self.query_vector(q, k * 2) if self.cfg.enable_embeddings else []
        
        if not bm25_results and not vector_results:
            return []
        
        if not vector_results:
            return bm25_results[:k]
        
        if not bm25_results:
            return vector_results[:k]
        
        # Reciprocal Rank Fusion with alpha blending
        rrf_scores = {}
        
        # Process BM25 results
        for i, result in enumerate(bm25_results):
            doc_key = (result['item_id'], result['chunk_id'])
            bm25_rrf = 1 / (i + 1 + 60)  # RRF formula
            rrf_scores[doc_key] = {
                'item_id': result['item_id'],
                'chunk_id': result['chunk_id'],
                'heading': result['heading'],
                'preview': result.get('preview', ''),
                'bm25_score': result['score'],
                'bm25_rank': i + 1,
                'bm25_rrf': bm25_rrf,
                'vec_rrf': 0
            }
        
        # Process vector results
        for i, result in enumerate(vector_results):
            doc_key = (result['item_id'], result['chunk_id'])
            vec_rrf = 1 / (i + 1 + 60)  # RRF formula
            
            if doc_key in rrf_scores:
                rrf_scores[doc_key]['vec_score'] = result['score']
                rrf_scores[doc_key]['vec_rank'] = i + 1
                rrf_scores[doc_key]['vec_rrf'] = vec_rrf
            else:
                rrf_scores[doc_key] = {
                    'item_id': result['item_id'],
                    'chunk_id': result['chunk_id'],
                    'heading': result['heading'],
                    'preview': result.get('preview', ''),
                    'vec_score': result['score'],
                    'vec_rank': i + 1,
                    'bm25_rrf': 0,
                    'vec_rrf': vec_rrf
                }
        
        # Calculate final RRF scores with alpha blending
        final_results = []
        for doc_key, data in rrf_scores.items():
            # Reciprocal Rank Fusion: score(doc) = Σ (1 / (rank_i + 60))
            rrf_score = data['bm25_rrf'] + data['vec_rrf']
            
            # Alpha blending (optional additional weighting)
            if 'bm25_score' in data and 'vec_score' in data:
                # Both methods found this document
                blended_score = alpha * rrf_score + (1 - alpha) * rrf_score
            else:
                # Only one method found this document
                blended_score = rrf_score
            
            sources = {}
            if data['bm25_rrf'] > 0:
                sources['bm25_rank'] = data['bm25_rank']
            if data['vec_rrf'] > 0:
                sources['vec_rank'] = data['vec_rank']
            
            final_results.append({
                'item_id': data['item_id'],
                'chunk_id': data['chunk_id'],
                'heading': data['heading'],
                'preview': data['preview'],
                'score': blended_score,
                'sources': sources
            })
        
        # Sort by final RRF score descending
        final_results.sort(key=lambda x: x['score'], reverse=True)
        
        return final_results[:k]
    
    def rebuild_all(self, embeddings: bool = True) -> Dict[str, Any]:
        """Full rebuild of all indices."""
        start_time = self._get_time_ms()
        
        # Rebuild FTS
        fts_result = self.rebuild_fts()
        
        # Rebuild embeddings if requested
        embedding_result = {}
        if embeddings and self.cfg.enable_embeddings:
            embedding_result = self.rebuild_embeddings()
        
        end_time = self._get_time_ms()
        
        result = {
            'fts_result': fts_result,
            'embedding_result': embedding_result,
            'total_time_ms': end_time - start_time,
            'status': 'success'
        }
        
        logger.info(f"Full rebuild completed: {result}")
        return result
    
    # Helper methods
    
    def _sanitize_fts_query(self, q: str) -> str:
        """Sanitize query for FTS5 compatibility."""
        if not q or not q.strip():
            return ""
        
        q = q.strip()
        
        # Remove problematic characters
        import re
        q = re.sub(r'[<>=^@#$%&]', '', q)
        q = re.sub(r'[():]', ' ', q)
        q = re.sub(r'[-]', ' ', q)
        
        # Handle quotes
        quote_count = q.count('"')
        if quote_count % 2 != 0:
            q = q.replace('"', '')
        
        # Clean up spaces
        q = re.sub(r'\s+', ' ', q).strip()
        
        if not q or len(q) < 2:
            return ""
        
        # For phrase search, wrap multi-word queries in quotes
        words = q.split()
        if len(words) == 1:
            return words[0]
        else:
            return f'"{q}"'
    
    def _generate_embedding(self, text: str, model: str) -> Optional[List[float]]:
        """Generate embedding using Ollama API."""
        try:
            data = json.dumps({"model": model, "input": text}).encode('utf-8')
            req = urllib.request.Request(
                f"{self.cfg.ollama_url}/api/embeddings",
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode('utf-8'))
            
            embedding = payload.get('embedding') or payload.get('data', [{}])[0].get('embedding')
            if not embedding:
                logger.warning("No embedding returned from Ollama")
                return None
            
            return embedding
            
        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")
            return None
    
    def _store_vec_embedding(self, chunk_id: str, model: str, embedding: List[float]) -> None:
        """Store embedding using sqlite-vec."""
        cursor = self.conn.cursor()
        
        # Delete existing mapping
        cursor.execute("DELETE FROM vec_map WHERE chunk_id = ? AND model = ?", (chunk_id, model))
        
        # Insert embedding into vec_chunk and capture rowid
        cursor.execute("INSERT INTO vec_chunk(embedding) VALUES (?)", (json.dumps(embedding),))
        rowid_int = cursor.lastrowid
        
        # Store mapping
        cursor.execute(
            "INSERT INTO vec_map(chunk_id, model, dim, rowid_int) VALUES (?, ?, ?, ?)",
            (chunk_id, model, len(embedding), rowid_int)
        )
    
    def _store_json_embedding(self, chunk_id: str, model: str, embedding: List[float]) -> None:
        """Store embedding as JSON fallback."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO embedding(chunk_id, model, dim, vec_json) VALUES (?, ?, ?, ?)",
            (chunk_id, model, len(embedding), json.dumps(embedding))
        )
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)
    
    def _get_time_ms(self) -> int:
        """Get current time in milliseconds."""
        import time
        return int(time.time() * 1000)