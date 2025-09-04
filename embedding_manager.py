#!/usr/bin/env python3
"""
Vector Embedding Manager for Second Brain
Handles embedding generation, storage, and retrieval for semantic search
"""

import sqlite3
import numpy as np
import pickle
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
import asyncio
import logging
from datetime import datetime
import time
import json

logger = logging.getLogger(__name__)

@dataclass
class EmbeddingJob:
    """Represents an embedding generation job"""
    id: int
    note_id: int
    status: str
    model_name: str
    error_message: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None

@dataclass
class NoteEmbedding:
    """Represents a stored note embedding"""
    id: int
    note_id: int
    embedding_model: str
    embedding: np.ndarray
    embedding_dim: int
    created_at: str
    updated_at: str

class EmbeddingManager:
    """Manages vector embeddings for semantic search"""
    
    def __init__(self, db_path: str, default_model: str = "all-MiniLM-L6-v2"):
        self.db_path = db_path
        self.default_model = default_model
        self._semantic_search = None  # Will be lazily loaded
        
    def _get_semantic_search(self):
        """Lazy load semantic search to avoid import errors"""
        if self._semantic_search is None:
            try:
                from services.search_adapter import SearchService
                self._semantic_search = SearchService(self.db_path)
            except ImportError as e:
                logger.warning(f"Semantic search not available: {e}")
                return None
        return self._semantic_search
    
    def _serialize_embedding(self, embedding: np.ndarray) -> bytes:
        """Serialize numpy array to bytes for database storage"""
        return pickle.dumps(embedding.astype(np.float32))
    
    def _deserialize_embedding(self, data: bytes) -> np.ndarray:
        """Deserialize bytes back to numpy array"""
        return pickle.loads(data)
    
    def store_embedding(self, note_id: int, embedding: np.ndarray, 
                       model_name: str = None) -> bool:
        """Store an embedding for a note"""
        if model_name is None:
            model_name = self.default_model
            
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Serialize embedding
            embedding_data = self._serialize_embedding(embedding)
            embedding_dim = len(embedding)
            
            # Check if embedding already exists for this note and model
            existing = conn.execute("""
                SELECT id FROM note_embeddings 
                WHERE note_id = ? AND embedding_model = ?
            """, (note_id, model_name)).fetchone()
            
            if existing:
                # Update existing embedding
                conn.execute("""
                    UPDATE note_embeddings 
                    SET embedding = ?, embedding_dim = ?, updated_at = datetime('now')
                    WHERE note_id = ? AND embedding_model = ?
                """, (embedding_data, embedding_dim, note_id, model_name))
                logger.debug(f"Updated embedding for note {note_id}")
            else:
                # Insert new embedding
                conn.execute("""
                    INSERT INTO note_embeddings 
                    (note_id, embedding_model, embedding, embedding_dim)
                    VALUES (?, ?, ?, ?)
                """, (note_id, model_name, embedding_data, embedding_dim))
                logger.debug(f"Stored new embedding for note {note_id}")
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to store embedding for note {note_id}: {e}")
            return False
    
    def get_embedding(self, note_id: int, model_name: str = None) -> Optional[np.ndarray]:
        """Retrieve embedding for a note"""
        if model_name is None:
            model_name = self.default_model
            
        try:
            conn = sqlite3.connect(self.db_path)
            
            result = conn.execute("""
                SELECT embedding FROM note_embeddings 
                WHERE note_id = ? AND embedding_model = ?
                ORDER BY updated_at DESC LIMIT 1
            """, (note_id, model_name)).fetchone()
            
            conn.close()
            
            if result:
                return self._deserialize_embedding(result[0])
            return None
            
        except Exception as e:
            logger.error(f"Failed to retrieve embedding for note {note_id}: {e}")
            return None
    
    def get_all_embeddings(self, model_name: str = None) -> List[Tuple[int, np.ndarray]]:
        """Get all embeddings for similarity search"""
        if model_name is None:
            model_name = self.default_model
            
        try:
            conn = sqlite3.connect(self.db_path)
            
            results = conn.execute("""
                SELECT note_id, embedding FROM note_embeddings 
                WHERE embedding_model = ?
                ORDER BY note_id
            """, (model_name,)).fetchall()
            
            conn.close()
            
            embeddings = []
            for note_id, embedding_data in results:
                try:
                    embedding = self._deserialize_embedding(embedding_data)
                    embeddings.append((note_id, embedding))
                except Exception as e:
                    logger.warning(f"Failed to deserialize embedding for note {note_id}: {e}")
                    continue
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to retrieve all embeddings: {e}")
            return []
    
    def create_embedding_job(self, note_id: int, model_name: str = None) -> bool:
        """Create a new embedding generation job"""
        if model_name is None:
            model_name = self.default_model
            
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Check if there's already a pending job for this note
            existing = conn.execute("""
                SELECT id FROM embedding_jobs 
                WHERE note_id = ? AND status = 'pending'
            """, (note_id,)).fetchone()
            
            if existing:
                logger.debug(f"Embedding job already exists for note {note_id}")
                conn.close()
                return True
            
            # Create new job
            conn.execute("""
                INSERT INTO embedding_jobs (note_id, model_name)
                VALUES (?, ?)
            """, (note_id, model_name))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Created embedding job for note {note_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create embedding job for note {note_id}: {e}")
            return False
    
    def get_pending_jobs(self, limit: int = 10) -> List[EmbeddingJob]:
        """Get pending embedding jobs"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            rows = conn.execute("""
                SELECT * FROM embedding_jobs 
                WHERE status = 'pending' AND attempts < max_attempts
                ORDER BY created_at ASC
                LIMIT ?
            """, (limit,)).fetchall()
            
            conn.close()
            
            jobs = []
            for row in rows:
                jobs.append(EmbeddingJob(
                    id=row['id'],
                    note_id=row['note_id'],
                    status=row['status'],
                    model_name=row['model_name'],
                    error_message=row['error_message'],
                    attempts=row['attempts'],
                    max_attempts=row['max_attempts'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    completed_at=row['completed_at']
                ))
            
            return jobs
            
        except Exception as e:
            logger.error(f"Failed to get pending jobs: {e}")
            return []
    
    def update_job_status(self, job_id: int, status: str, 
                         error_message: str = None) -> bool:
        """Update the status of an embedding job"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            if status == 'completed':
                conn.execute("""
                    UPDATE embedding_jobs 
                    SET status = ?, completed_at = datetime('now'), error_message = ?
                    WHERE id = ?
                """, (status, error_message, job_id))
            elif status == 'failed':
                conn.execute("""
                    UPDATE embedding_jobs 
                    SET status = ?, attempts = attempts + 1, error_message = ?
                    WHERE id = ?
                """, (status, error_message, job_id))
            else:
                conn.execute("""
                    UPDATE embedding_jobs 
                    SET status = ?, error_message = ?
                    WHERE id = ?
                """, (status, error_message, job_id))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
            return False
    
    def process_embedding_job(self, job: EmbeddingJob) -> bool:
        """Process a single embedding job"""
        semantic_search = self._get_semantic_search()
        if not semantic_search:
            logger.warning("Semantic search not available, skipping embedding job")
            return False
        
        try:
            # Update job status to processing
            self.update_job_status(job.id, 'processing')
            
            # Get note content
            conn = sqlite3.connect(self.db_path)
            note_data = conn.execute("""
                SELECT title, content, summary FROM notes WHERE id = ?
            """, (job.note_id,)).fetchone()
            conn.close()
            
            if not note_data:
                self.update_job_status(job.id, 'failed', 'Note not found')
                return False
            
            title, content, summary = note_data
            
            # Combine text for embedding
            text_parts = []
            if title:
                text_parts.append(title)
            if summary:
                text_parts.append(summary)
            if content:
                text_parts.append(content)
            
            combined_text = ' '.join(text_parts).strip()
            
            if not combined_text:
                self.update_job_status(job.id, 'failed', 'No text content to embed')
                return False
            
            # Generate embedding
            embedding = semantic_search.generate_embedding(combined_text)
            if embedding is None:
                self.update_job_status(job.id, 'failed', 'Failed to generate embedding')
                return False
            
            # Store embedding
            if self.store_embedding(job.note_id, embedding, job.model_name):
                self.update_job_status(job.id, 'completed')
                logger.info(f"✅ Processed embedding job {job.id} for note {job.note_id}")
                return True
            else:
                self.update_job_status(job.id, 'failed', 'Failed to store embedding')
                return False
            
        except Exception as e:
            error_msg = f"Exception processing job: {str(e)}"
            self.update_job_status(job.id, 'failed', error_msg)
            logger.error(f"Failed to process embedding job {job.id}: {e}")
            return False
    
    async def process_pending_jobs(self, batch_size: int = 5) -> int:
        """Process pending embedding jobs in batches"""
        processed_count = 0
        
        while True:
            jobs = self.get_pending_jobs(batch_size)
            if not jobs:
                break
            
            logger.info(f"Processing {len(jobs)} embedding jobs...")
            
            for job in jobs:
                if self.process_embedding_job(job):
                    processed_count += 1
                
                # Small delay between jobs to prevent overwhelming the system
                await asyncio.sleep(0.1)
            
            # If we got fewer jobs than requested, we're done
            if len(jobs) < batch_size:
                break
        
        if processed_count > 0:
            logger.info(f"✅ Processed {processed_count} embedding jobs")
        
        return processed_count
    
    def get_embedding_stats(self) -> Dict[str, Any]:
        """Get statistics about embeddings and jobs"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Count embeddings by model
            embeddings_by_model = dict(conn.execute("""
                SELECT embedding_model, COUNT(*) 
                FROM note_embeddings 
                GROUP BY embedding_model
            """).fetchall())
            
            # Count notes with/without embeddings
            total_notes = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            notes_with_embeddings = conn.execute("""
                SELECT COUNT(DISTINCT note_id) FROM note_embeddings
            """).fetchone()[0]
            
            # Job statistics
            job_stats = dict(conn.execute("""
                SELECT status, COUNT(*) FROM embedding_jobs GROUP BY status
            """).fetchall())
            
            conn.close()
            
            return {
                'total_notes': total_notes,
                'notes_with_embeddings': notes_with_embeddings,
                'notes_without_embeddings': total_notes - notes_with_embeddings,
                'embeddings_by_model': embeddings_by_model,
                'job_statistics': job_stats,
                'coverage_percentage': round((notes_with_embeddings / total_notes) * 100, 1) if total_notes > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get embedding stats: {e}")
            return {}
    
    def rebuild_embeddings(self, model_name: str = None, force: bool = False) -> bool:
        """Rebuild all embeddings, optionally forcing regeneration"""
        if model_name is None:
            model_name = self.default_model
        
        try:
            conn = sqlite3.connect(self.db_path)
            
            if force:
                # Delete existing embeddings for this model
                conn.execute("""
                    DELETE FROM note_embeddings WHERE embedding_model = ?
                """, (model_name,))
                
                # Delete existing jobs
                conn.execute("""
                    DELETE FROM embedding_jobs WHERE model_name = ?
                """, (model_name,))
            
            # Create jobs for all notes that don't have embeddings
            if force:
                # Create jobs for all notes
                conn.execute("""
                    INSERT INTO embedding_jobs (note_id, model_name)
                    SELECT id, ? FROM notes
                """, (model_name,))
            else:
                # Create jobs only for notes without embeddings
                conn.execute("""
                    INSERT INTO embedding_jobs (note_id, model_name)
                    SELECT n.id, ?
                    FROM notes n
                    LEFT JOIN note_embeddings ne ON n.id = ne.note_id AND ne.embedding_model = ?
                    WHERE ne.id IS NULL
                """, (model_name, model_name))
            
            conn.commit()
            jobs_created = conn.execute("""
                SELECT COUNT(*) FROM embedding_jobs WHERE status = 'pending'
            """).fetchone()[0]
            conn.close()
            
            logger.info(f"Created {jobs_created} embedding jobs for model {model_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rebuild embeddings: {e}")
            return False


async def main():
    """CLI interface for embedding manager"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Manage vector embeddings")
    parser.add_argument("--db", default="notes.db", help="Database path")
    parser.add_argument("--model", default="all-MiniLM-L6-v2", help="Embedding model")
    parser.add_argument("--stats", action="store_true", help="Show embedding statistics")
    parser.add_argument("--process", action="store_true", help="Process pending jobs")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild all embeddings")
    parser.add_argument("--force", action="store_true", help="Force rebuild (delete existing)")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for processing")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    manager = EmbeddingManager(args.db, args.model)
    
    if args.stats:
        stats = manager.get_embedding_stats()
        print("\n📊 Embedding Statistics")
        print("=" * 30)
        for key, value in stats.items():
            print(f"{key}: {value}")
    
    if args.rebuild:
        print(f"🔄 Rebuilding embeddings (force: {args.force})...")
        manager.rebuild_embeddings(args.model, args.force)
    
    if args.process:
        print("⚡ Processing pending embedding jobs...")
        processed = await manager.process_pending_jobs(args.batch_size)
        print(f"✅ Processed {processed} jobs")


if __name__ == "__main__":
    asyncio.run(main())