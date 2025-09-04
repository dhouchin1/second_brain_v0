"""
FIFO Audio Processing Queue Service

Ensures audio files are processed in First In, First Out order
to prevent newer uploads from jumping ahead of older ones.
"""

import sqlite3
import asyncio
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from pathlib import Path
import logging
from config import settings

logger = logging.getLogger(__name__)

class AudioProcessingQueue:
    """FIFO queue for audio processing with database persistence"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(settings.db_path)
        self._processing_lock = threading.Lock()
        self._current_processing_id: Optional[int] = None
        self._batch_timer: Optional[threading.Timer] = None
        self._init_queue_table()
    
    def _init_queue_table(self):
        """Create queue table if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audio_processing_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id INTEGER UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                queued_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                status TEXT DEFAULT 'queued',
                priority INTEGER DEFAULT 0,
                FOREIGN KEY (note_id) REFERENCES notes (id)
            )
        """)
        
        # Create index for efficient FIFO ordering
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_queue_fifo 
            ON audio_processing_queue (status, priority DESC, queued_at ASC)
        """)
        conn.commit()
        conn.close()
    
    def add_to_queue(self, note_id: int, user_id: int, priority: int = 0) -> bool:
        """Add note to processing queue with FIFO ordering"""
        try:
            conn = sqlite3.connect(self.db_path)
            now = datetime.now().isoformat()
            
            conn.execute("""
                INSERT OR REPLACE INTO audio_processing_queue 
                (note_id, user_id, queued_at, status, priority)
                VALUES (?, ?, ?, 'queued', ?)
            """, (note_id, user_id, now, priority))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Added note {note_id} to audio processing queue")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add note {note_id} to queue: {e}")
            return False
    
    def get_next_for_processing(self) -> Optional[Tuple[int, int]]:
        """Get the next note ID and user ID for processing (FIFO order based on note creation time)"""
        with self._processing_lock:
            if self._current_processing_id:
                # Already processing something
                return None
            
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Get oldest queued item by note timestamp (true FIFO)
                cursor.execute("""
                    SELECT q.note_id, q.user_id 
                    FROM audio_processing_queue q
                    JOIN notes n ON q.note_id = n.id
                    WHERE q.status = 'queued'
                    ORDER BY q.priority DESC, n.timestamp ASC
                    LIMIT 1
                """)
                
                result = cursor.fetchone()
                if result:
                    note_id, user_id = result
                    
                    # Mark as processing
                    now = datetime.now().isoformat()
                    cursor.execute("""
                        UPDATE audio_processing_queue
                        SET status = 'processing', started_at = ?
                        WHERE note_id = ?
                    """, (now, note_id))
                    
                    conn.commit()
                    self._current_processing_id = note_id
                    
                    logger.info(f"Started processing note {note_id} from queue")
                    
                conn.close()
                return result
                
            except Exception as e:
                logger.error(f"Error getting next item from queue: {e}")
                return None
    
    def mark_completed(self, note_id: int, success: bool = True):
        """Mark note as completed in queue"""
        with self._processing_lock:
            try:
                conn = sqlite3.connect(self.db_path)
                now = datetime.now().isoformat()
                status = 'completed' if success else 'failed'
                
                conn.execute("""
                    UPDATE audio_processing_queue
                    SET status = ?, completed_at = ?
                    WHERE note_id = ?
                """, (status, now, note_id))
                
                conn.commit()
                conn.close()
                
                if self._current_processing_id == note_id:
                    self._current_processing_id = None
                
                logger.info(f"Marked note {note_id} as {status} in queue")
                
            except Exception as e:
                logger.error(f"Error marking note {note_id} as completed: {e}")
    
    def get_queue_status(self, user_id: int = None) -> dict:
        """Get current queue status"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Count by status
            if user_id:
                cursor.execute("""
                    SELECT status, COUNT(*) FROM audio_processing_queue
                    WHERE user_id = ?
                    GROUP BY status
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT status, COUNT(*) FROM audio_processing_queue
                    GROUP BY status
                """)
            
            status_counts = dict(cursor.fetchall())
            
            # Get current position for user's queued items (based on note timestamp)
            position_info = []
            if user_id:
                cursor.execute("""
                    SELECT q1.note_id, 
                           (SELECT COUNT(*) FROM audio_processing_queue q2 
                            JOIN notes n2 ON q2.note_id = n2.id
                            JOIN notes n1 ON q1.note_id = n1.id
                            WHERE q2.status = 'queued' 
                            AND (q2.priority > q1.priority 
                                 OR (q2.priority = q1.priority AND n2.timestamp < n1.timestamp))
                           ) + 1 as position
                    FROM audio_processing_queue q1
                    JOIN notes n1 ON q1.note_id = n1.id
                    WHERE q1.user_id = ? AND q1.status = 'queued'
                    ORDER BY q1.priority DESC, n1.timestamp ASC
                """, (user_id,))
                
                position_info = [{"note_id": row[0], "position": row[1]} for row in cursor.fetchall()]
            
            conn.close()
            
            return {
                "status_counts": status_counts,
                "user_queue_positions": position_info,
                "currently_processing": self._current_processing_id
            }
            
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {"error": str(e)}
    
    def cleanup_old_completed(self, days: int = 7):
        """Clean up old completed/failed queue entries"""
        try:
            conn = sqlite3.connect(self.db_path)
            cutoff = (datetime.now() - datetime.timedelta(days=days)).isoformat()
            
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM audio_processing_queue
                WHERE status IN ('completed', 'failed')
                AND completed_at < ?
            """, (cutoff,))
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old queue entries")
                
        except Exception as e:
            logger.error(f"Error cleaning up queue: {e}")
    
    def should_enable_batch_processing(self) -> bool:
        """Check if batch processing should be enabled based on queue size"""
        if not settings.batch_mode_enabled:
            return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Count queued items
            cursor.execute("SELECT COUNT(*) FROM audio_processing_queue WHERE status = 'queued'")
            queued_count = cursor.fetchone()[0]
            
            conn.close()
            
            return queued_count >= settings.batch_size_threshold
            
        except Exception as e:
            logger.error(f"Error checking batch processing status: {e}")
            return False
    
    def start_batch_timer(self):
        """Start or restart the batch processing timer"""
        if self._batch_timer:
            self._batch_timer.cancel()
        
        if settings.batch_mode_enabled and settings.batch_timeout_seconds > 0:
            self._batch_timer = threading.Timer(
                settings.batch_timeout_seconds, 
                self._process_batch_timeout
            )
            self._batch_timer.start()
            logger.info(f"Started batch timer for {settings.batch_timeout_seconds} seconds")
    
    def _process_batch_timeout(self):
        """Handle batch timeout - process all queued items"""
        logger.info("Batch timeout reached - processing all queued items")
        
        # Signal that batch processing should happen
        # The actual processing will be handled by the worker
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Count queued items
            cursor.execute("SELECT COUNT(*) FROM audio_processing_queue WHERE status = 'queued'")
            queued_count = cursor.fetchone()[0]
            
            if queued_count > 0:
                logger.info(f"Batch timeout: {queued_count} items ready for processing")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Error during batch timeout processing: {e}")
        finally:
            # Cancel the timer since timeout has been reached
            self.cancel_batch_timer()
    
    def cancel_batch_timer(self):
        """Cancel the batch processing timer"""
        if self._batch_timer:
            self._batch_timer.cancel()
            self._batch_timer = None
    
    def get_batch_status(self) -> dict:
        """Get batch processing status"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM audio_processing_queue WHERE status = 'queued'")
            queued = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "batch_mode_enabled": settings.batch_mode_enabled,
                "batch_threshold": settings.batch_size_threshold,
                "batch_timeout": settings.batch_timeout_seconds,
                "current_queue_size": queued,
                "should_process_batch": self.should_enable_batch_processing(),
                "timer_active": self._batch_timer is not None and self._batch_timer.is_alive() if self._batch_timer else False
            }
            
        except Exception as e:
            logger.error(f"Error getting batch status: {e}")
            return {"error": str(e)}

# Global queue instance
audio_queue = AudioProcessingQueue()