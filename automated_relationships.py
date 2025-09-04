#!/usr/bin/env python3
"""
Automated Note Relationship Discovery System
Runs background processes to discover relationships and clusters automatically
"""

import sqlite3
import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import time
import json
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class AutomationConfig:
    """Configuration for automated relationship discovery"""
    min_notes_for_clustering: int = 10
    similarity_threshold_base: float = 0.3
    similarity_threshold_adaptive: bool = True
    cluster_min_size: int = 3
    relationship_refresh_hours: int = 24
    embedding_batch_size: int = 20
    max_similar_notes: int = 5
    auto_cluster_frequency_hours: int = 6
    enable_real_time_updates: bool = True

class AutomatedRelationshipEngine:
    """Manages automated relationship discovery and maintenance"""
    
    def __init__(self, db_path: str, config: AutomationConfig = None):
        self.db_path = db_path
        self.config = config or AutomationConfig()
        self._running = False
        self._background_task = None
        self._last_cluster_update = {}  # user_id -> timestamp
        self._adaptive_thresholds = {}  # user_id -> threshold
        
        # Initialize components
        self._relationship_engine = None
        self._embedding_manager = None
        self._semantic_search = None
        
        self._init_database()
    
    def _get_relationship_engine(self):
        """Lazy load relationship engine"""
        if self._relationship_engine is None:
            try:
                from note_relationships import NoteRelationshipEngine
                self._relationship_engine = NoteRelationshipEngine(self.db_path)
            except ImportError:
                logger.warning("Relationship engine not available")
                return None
        return self._relationship_engine
    
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
    
    def _get_semantic_search(self):
        """Lazy load semantic search"""
        if self._semantic_search is None:
            try:
                from services.search_adapter import SearchService
                self._semantic_search = SearchService(self.db_path)
            except ImportError:
                logger.warning("Semantic search not available")
                return None
        return self._semantic_search
    
    def _init_database(self):
        """Initialize automation tracking tables"""
        conn = sqlite3.connect(self.db_path)
        
        # Automation jobs queue
        conn.execute("""
            CREATE TABLE IF NOT EXISTS automation_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                target_id INTEGER,
                user_id INTEGER,
                priority INTEGER DEFAULT 5,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT,
                metadata TEXT
            )
        """)
        
        # Automation settings per user
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_automation_settings (
                user_id INTEGER PRIMARY KEY,
                enable_auto_relationships BOOLEAN DEFAULT 1,
                enable_auto_clustering BOOLEAN DEFAULT 1,
                enable_similar_suggestions BOOLEAN DEFAULT 1,
                similarity_threshold REAL DEFAULT 0.3,
                cluster_frequency_hours INTEGER DEFAULT 6,
                last_full_update TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        
        # Performance metrics
        conn.execute("""
            CREATE TABLE IF NOT EXISTS automation_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                metric_type TEXT NOT NULL,
                metric_value REAL NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_automation_jobs_status ON automation_jobs(status, priority)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_automation_jobs_user ON automation_jobs(user_id)")
        
        conn.commit()
        conn.close()
    
    async def start_automation(self):
        """Start the automated relationship discovery system"""
        if self._running:
            logger.info("Automation already running")
            return
        
        self._running = True
        logger.info("🤖 Starting automated relationship discovery system")
        
        # Start background processing task
        self._background_task = asyncio.create_task(self._automation_loop())
        
        # Initialize user settings
        await self._initialize_user_settings()
        
        # Queue initial discovery jobs for all users
        await self._queue_initial_jobs()
    
    async def stop_automation(self):
        """Stop the automated system"""
        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Automation system stopped")
    
    async def _automation_loop(self):
        """Main automation processing loop"""
        while self._running:
            try:
                # Process pending jobs
                await self._process_automation_jobs()
                
                # Check for users needing periodic updates
                await self._schedule_periodic_updates()
                
                # Adapt thresholds based on performance
                await self._adapt_similarity_thresholds()
                
                # Sleep before next iteration
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in automation loop: {e}")
                await asyncio.sleep(60)  # Wait longer if there's an error
    
    async def _initialize_user_settings(self):
        """Initialize automation settings for all users"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get all users who don't have automation settings
            users_without_settings = conn.execute("""
                SELECT DISTINCT u.id FROM users u
                LEFT JOIN user_automation_settings uas ON u.id = uas.user_id
                WHERE uas.user_id IS NULL
            """).fetchall()
            
            for (user_id,) in users_without_settings:
                conn.execute("""
                    INSERT OR IGNORE INTO user_automation_settings (user_id)
                    VALUES (?)
                """, (user_id,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to initialize user settings: {e}")
    
    async def _queue_initial_jobs(self):
        """Queue initial discovery jobs for all users"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            users = conn.execute("""
                SELECT id FROM users WHERE EXISTS (
                    SELECT 1 FROM notes WHERE user_id = users.id
                )
            """).fetchall()
            
            for (user_id,) in users:
                # Queue embedding update job
                await self._queue_job("update_embeddings", user_id=user_id, priority=3)
                
                # Queue clustering job
                await self._queue_job("discover_clusters", user_id=user_id, priority=4)
            
            conn.close()
            logger.info(f"Queued initial jobs for {len(users)} users")
            
        except Exception as e:
            logger.error(f"Failed to queue initial jobs: {e}")
    
    async def _queue_job(self, job_type: str, target_id: int = None, 
                        user_id: int = None, priority: int = 5, 
                        metadata: Dict = None):
        """Queue an automation job"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            conn.execute("""
                INSERT INTO automation_jobs 
                (job_type, target_id, user_id, priority, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (job_type, target_id, user_id, priority, metadata_json))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to queue job: {e}")
    
    async def _process_automation_jobs(self):
        """Process pending automation jobs"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            # Get highest priority pending jobs
            jobs = conn.execute("""
                SELECT * FROM automation_jobs 
                WHERE status = 'pending'
                ORDER BY priority ASC, created_at ASC
                LIMIT 5
            """).fetchall()
            
            conn.close()
            
            for job in jobs:
                await self._process_single_job(job)
                
        except Exception as e:
            logger.error(f"Failed to process automation jobs: {e}")
    
    async def _process_single_job(self, job):
        """Process a single automation job"""
        job_id = job['id']
        job_type = job['job_type']
        target_id = job['target_id']
        user_id = job['user_id']
        metadata = json.loads(job['metadata']) if job['metadata'] else {}
        
        try:
            # Update job status to running
            self._update_job_status(job_id, 'running', datetime.now().isoformat())
            
            if job_type == 'update_embeddings':
                await self._job_update_embeddings(user_id, metadata)
            elif job_type == 'discover_clusters':
                await self._job_discover_clusters(user_id, metadata)
            elif job_type == 'find_similar':
                await self._job_find_similar(target_id, user_id, metadata)
            elif job_type == 'refresh_relationships':
                await self._job_refresh_relationships(user_id, metadata)
            else:
                logger.warning(f"Unknown job type: {job_type}")
                self._update_job_status(job_id, 'failed', error_message="Unknown job type")
                return
            
            # Mark job as completed
            self._update_job_status(job_id, 'completed', completed_at=datetime.now().isoformat())
            
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            self._update_job_status(job_id, 'failed', error_message=str(e))
    
    def _update_job_status(self, job_id: int, status: str, 
                          started_at: str = None, completed_at: str = None,
                          error_message: str = None):
        """Update job status in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            if started_at:
                conn.execute("""
                    UPDATE automation_jobs 
                    SET status = ?, started_at = ?
                    WHERE id = ?
                """, (status, started_at, job_id))
            elif completed_at:
                conn.execute("""
                    UPDATE automation_jobs 
                    SET status = ?, completed_at = ?
                    WHERE id = ?
                """, (status, completed_at, job_id))
            elif error_message:
                conn.execute("""
                    UPDATE automation_jobs 
                    SET status = ?, error_message = ?
                    WHERE id = ?
                """, (status, error_message, job_id))
            else:
                conn.execute("""
                    UPDATE automation_jobs 
                    SET status = ?
                    WHERE id = ?
                """, (status, job_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
    
    async def _job_update_embeddings(self, user_id: int, metadata: Dict):
        """Job: Update embeddings for user's notes"""
        embedding_manager = self._get_embedding_manager()
        if not embedding_manager:
            raise Exception("Embedding manager not available")
        
        # Process embeddings in batches
        processed = await embedding_manager.process_pending_jobs(
            batch_size=self.config.embedding_batch_size
        )
        
        # Create embedding jobs for notes without embeddings
        if processed == 0:  # No pending jobs, create new ones
            embedding_manager.rebuild_embeddings(force=False)
            processed = await embedding_manager.process_pending_jobs(
                batch_size=self.config.embedding_batch_size
            )
        
        # Log metrics
        await self._log_metric(user_id, "embeddings_processed", processed)
        
        logger.info(f"Updated {processed} embeddings for user {user_id}")
    
    async def _job_discover_clusters(self, user_id: int, metadata: Dict):
        """Job: Discover note clusters for user"""
        relationship_engine = self._get_relationship_engine()
        if not relationship_engine:
            raise Exception("Relationship engine not available")
        
        # Get adaptive threshold
        threshold = await self._get_adaptive_threshold(user_id)
        
        # Discover clusters
        clusters = relationship_engine.discover_note_clusters(
            user_id, 
            min_cluster_size=self.config.cluster_min_size,
            similarity_threshold=threshold
        )
        
        # Update last cluster time
        self._last_cluster_update[user_id] = datetime.now()
        
        # Log metrics
        await self._log_metric(user_id, "clusters_discovered", len(clusters))
        
        logger.info(f"Discovered {len(clusters)} clusters for user {user_id}")
    
    async def _job_find_similar(self, note_id: int, user_id: int, metadata: Dict):
        """Job: Find similar notes for a specific note"""
        relationship_engine = self._get_relationship_engine()
        if not relationship_engine:
            raise Exception("Relationship engine not available")
        
        # Get adaptive threshold
        threshold = await self._get_adaptive_threshold(user_id)
        
        similar_notes = relationship_engine.find_similar_notes(
            note_id, user_id,
            limit=self.config.max_similar_notes,
            min_similarity=threshold
        )
        
        # Log metrics
        await self._log_metric(user_id, "similar_notes_found", len(similar_notes))
        
        logger.debug(f"Found {len(similar_notes)} similar notes for note {note_id}")
    
    async def _job_refresh_relationships(self, user_id: int, metadata: Dict):
        """Job: Refresh all relationships for user"""
        # Get all user's notes
        conn = sqlite3.connect(self.db_path)
        note_ids = [row[0] for row in conn.execute("""
            SELECT id FROM notes WHERE user_id = ?
        """, (user_id,)).fetchall()]
        conn.close()
        
        # Queue similar note discovery for each note
        for note_id in note_ids[:50]:  # Limit to prevent overwhelming
            await self._queue_job("find_similar", target_id=note_id, user_id=user_id, priority=6)
    
    async def _schedule_periodic_updates(self):
        """Schedule periodic updates for users"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Find users needing cluster updates
            cutoff_time = datetime.now() - timedelta(hours=self.config.auto_cluster_frequency_hours)
            
            users_needing_clusters = conn.execute("""
                SELECT user_id FROM user_automation_settings
                WHERE enable_auto_clustering = 1 
                AND (last_full_update IS NULL OR last_full_update < ?)
            """, (cutoff_time.isoformat(),)).fetchall()
            
            for (user_id,) in users_needing_clusters:
                if user_id not in self._last_cluster_update or \
                   self._last_cluster_update[user_id] < cutoff_time:
                    
                    await self._queue_job("discover_clusters", user_id=user_id, priority=7)
                    
                    # Update timestamp
                    conn.execute("""
                        UPDATE user_automation_settings
                        SET last_full_update = ?
                        WHERE user_id = ?
                    """, (datetime.now().isoformat(), user_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to schedule periodic updates: {e}")
    
    async def _adapt_similarity_thresholds(self):
        """Adapt similarity thresholds based on performance metrics"""
        if not self.config.similarity_threshold_adaptive:
            return
        
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get users and their recent metrics
            users = conn.execute("""
                SELECT user_id FROM user_automation_settings
                WHERE enable_auto_relationships = 1
            """).fetchall()
            
            for (user_id,) in users:
                # Get recent cluster and similarity metrics
                recent_clusters = conn.execute("""
                    SELECT metric_value FROM automation_metrics
                    WHERE user_id = ? AND metric_type = 'clusters_discovered'
                    AND timestamp > datetime('now', '-7 days')
                    ORDER BY timestamp DESC LIMIT 5
                """, (user_id,)).fetchall()
                
                if recent_clusters:
                    avg_clusters = sum(row[0] for row in recent_clusters) / len(recent_clusters)
                    
                    # Adapt threshold based on cluster count
                    current_threshold = self._adaptive_thresholds.get(user_id, self.config.similarity_threshold_base)
                    
                    if avg_clusters < 2:  # Too few clusters, lower threshold
                        new_threshold = max(0.2, current_threshold - 0.05)
                    elif avg_clusters > 8:  # Too many clusters, raise threshold
                        new_threshold = min(0.6, current_threshold + 0.05)
                    else:
                        new_threshold = current_threshold
                    
                    if abs(new_threshold - current_threshold) > 0.01:
                        self._adaptive_thresholds[user_id] = new_threshold
                        
                        # Update in database
                        conn.execute("""
                            UPDATE user_automation_settings
                            SET similarity_threshold = ?
                            WHERE user_id = ?
                        """, (new_threshold, user_id))
                        
                        logger.info(f"Adapted threshold for user {user_id}: {current_threshold:.3f} -> {new_threshold:.3f}")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to adapt thresholds: {e}")
    
    async def _get_adaptive_threshold(self, user_id: int) -> float:
        """Get the current adaptive threshold for a user"""
        if user_id in self._adaptive_thresholds:
            return self._adaptive_thresholds[user_id]
        
        try:
            conn = sqlite3.connect(self.db_path)
            result = conn.execute("""
                SELECT similarity_threshold FROM user_automation_settings
                WHERE user_id = ?
            """, (user_id,)).fetchone()
            conn.close()
            
            if result:
                threshold = result[0]
                self._adaptive_thresholds[user_id] = threshold
                return threshold
        except Exception as e:
            logger.error(f"Failed to get adaptive threshold: {e}")
        
        return self.config.similarity_threshold_base
    
    async def _log_metric(self, user_id: int, metric_type: str, metric_value: float, 
                         metadata: Dict = None):
        """Log automation metrics"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            conn.execute("""
                INSERT INTO automation_metrics (user_id, metric_type, metric_value, metadata)
                VALUES (?, ?, ?, ?)
            """, (user_id, metric_type, metric_value, metadata_json))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to log metric: {e}")
    
    async def on_note_created(self, note_id: int, user_id: int):
        """Trigger automation when a new note is created"""
        if not self.config.enable_real_time_updates:
            return
        
        # Queue embedding generation for the new note
        embedding_manager = self._get_embedding_manager()
        if embedding_manager:
            embedding_manager.create_embedding_job(note_id)
        
        # Queue similarity discovery
        await self._queue_job("find_similar", target_id=note_id, user_id=user_id, priority=2)
        
        # If user has enough notes, queue clustering update
        conn = sqlite3.connect(self.db_path)
        note_count = conn.execute("""
            SELECT COUNT(*) FROM notes WHERE user_id = ?
        """, (user_id,)).fetchone()[0]
        conn.close()
        
        if note_count >= self.config.min_notes_for_clustering:
            await self._queue_job("discover_clusters", user_id=user_id, priority=8)
    
    async def on_note_updated(self, note_id: int, user_id: int):
        """Trigger automation when a note is updated"""
        if not self.config.enable_real_time_updates:
            return
        
        # Queue embedding update
        embedding_manager = self._get_embedding_manager()
        if embedding_manager:
            embedding_manager.create_embedding_job(note_id)
        
        # Queue similarity update
        await self._queue_job("find_similar", target_id=note_id, user_id=user_id, priority=3)
    
    def get_automation_status(self, user_id: int) -> Dict:
        """Get automation status for a user"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            # Get user settings
            settings = conn.execute("""
                SELECT * FROM user_automation_settings WHERE user_id = ?
            """, (user_id,)).fetchone()
            
            # Get recent job counts
            recent_jobs = dict(conn.execute("""
                SELECT status, COUNT(*) FROM automation_jobs
                WHERE user_id = ? AND created_at > datetime('now', '-24 hours')
                GROUP BY status
            """, (user_id,)).fetchall())
            
            # Get recent metrics
            recent_metrics = conn.execute("""
                SELECT metric_type, AVG(metric_value) as avg_value
                FROM automation_metrics
                WHERE user_id = ? AND timestamp > datetime('now', '-7 days')
                GROUP BY metric_type
            """, (user_id,)).fetchall()
            
            conn.close()
            
            return {
                "automation_enabled": self._running,
                "settings": dict(settings) if settings else {},
                "recent_jobs": recent_jobs,
                "metrics": {row[0]: row[1] for row in recent_metrics},
                "adaptive_threshold": self._adaptive_thresholds.get(user_id, self.config.similarity_threshold_base)
            }
            
        except Exception as e:
            logger.error(f"Failed to get automation status: {e}")
            return {"error": str(e)}


# Global automation engine instance
_automation_engine = None

def get_automation_engine(db_path: str) -> AutomatedRelationshipEngine:
    """Get global automation engine instance"""
    global _automation_engine
    if _automation_engine is None:
        _automation_engine = AutomatedRelationshipEngine(db_path)
    return _automation_engine


async def main():
    """CLI interface for automated relationship system"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Automated Relationship Discovery")
    parser.add_argument("--db", default="notes.db", help="Database path")
    parser.add_argument("--start", action="store_true", help="Start automation system")
    parser.add_argument("--status", action="store_true", help="Show automation status")
    parser.add_argument("--user-id", type=int, default=1, help="User ID for status")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    engine = AutomatedRelationshipEngine(args.db)
    
    if args.status:
        status = engine.get_automation_status(args.user_id)
        print("\n🤖 Automation Status")
        print("=" * 30)
        for key, value in status.items():
            print(f"{key}: {value}")
    
    if args.start:
        print("🚀 Starting automated relationship discovery system...")
        await engine.start_automation()
        
        # Run for demonstration
        try:
            await asyncio.sleep(300)  # Run for 5 minutes
        except KeyboardInterrupt:
            print("\n⏹️  Stopping automation...")
        finally:
            await engine.stop_automation()


if __name__ == "__main__":
    asyncio.run(main())
