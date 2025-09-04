"""
Initialization Service for Second Brain

Handles first-run setup, auto-seeding, and new user onboarding.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from services.auto_seeding_service import get_auto_seeding_service
from services.search_index import SearchIndexer, SearchConfig
from config import settings

log = logging.getLogger(__name__)

class InitializationService:
    """Service for handling new instance setup and user onboarding."""
    
    def __init__(self, get_conn_func):
        """Initialize with database connection function."""
        self.get_conn = get_conn_func
    
    def is_fresh_installation(self) -> bool:
        """Check if this is a fresh Second Brain installation."""
        conn = self.get_conn()
        try:
            # Check if any users exist (excluding potential admin/system users)
            cursor = conn.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            
            # Check if any notes exist
            cursor = conn.execute("SELECT COUNT(*) FROM notes")
            note_count = cursor.fetchone()[0]
            
            # Consider fresh if no users or very few notes
            return user_count == 0 or (user_count <= 1 and note_count < 5)
            
        except Exception as e:
            log.error("Error checking installation status: %s", e)
            # Assume not fresh on error to avoid unwanted auto-seeding
            return False
        finally:
            conn.close()
    
    def is_new_user(self, user_id: int) -> bool:
        """Check if user is newly created and needs onboarding."""
        conn = self.get_conn()
        try:
            # Check user creation time (if we have it)
            cursor = conn.execute("""
                SELECT created_at FROM users 
                WHERE id = ?
            """, (user_id,))
            
            result = cursor.fetchone()
            if not result:
                return False
                
            # If created within last hour, consider new
            # This is a simple heuristic - you might want more sophisticated logic
            created_at = result[0]  # Assuming ISO format
            
            # Check if user has any content
            cursor = conn.execute("""
                SELECT COUNT(*) FROM notes WHERE user_id = ?
            """, (user_id,))
            
            note_count = cursor.fetchone()[0]
            
            # New user if they have very few notes
            return note_count < 3
            
        except Exception as e:
            log.error("Error checking if user is new: %s", e)
            return False
        finally:
            conn.close()
    
    def perform_first_run_setup(self) -> Dict[str, Any]:
        """Perform first-run setup for fresh installation."""
        try:
            log.info("Performing first-run setup for fresh installation")
            
            # Ensure database schema is up to date
            self._ensure_auto_seeding_schema()
            
            # Create first user if none exists
            first_user_id = self._ensure_first_user()
            
            if first_user_id:
                # Initialize search indexer
                search_config = SearchConfig(
                    db_path=Path(settings.db_path),
                    embed_model=getattr(settings, 'auto_seeding_embed_model', 'nomic-embed-text'),
                    enable_embeddings=getattr(settings, 'auto_seeding_embeddings', True),
                    ollama_url=settings.ollama_api_url.replace('/api/generate', '')
                )
                
                search_indexer = SearchIndexer(search_config)
                
                # Ensure search infrastructure
                search_indexer.ensure_fts()
                vec_available = search_indexer.ensure_vec()
                
                log.info("Search indexer initialized (sqlite-vec available: %s)", vec_available)
                
                # Auto-seed for the first user
                auto_seeding_service = get_auto_seeding_service(self.get_conn)
                result = auto_seeding_service.perform_auto_seeding(first_user_id, force=True)
                
                # Rebuild search indexes with new content
                if result.get("success"):
                    try:
                        log.info("Rebuilding search indexes after auto-seeding...")
                        fts_result = search_indexer.rebuild_fts()
                        
                        if search_config.enable_embeddings:
                            embed_result = search_indexer.rebuild_embeddings()
                            log.info("Search indexes rebuilt: FTS=%s, Embeddings=%s", 
                                   fts_result.get("indexed_chunks", 0),
                                   embed_result.get("embedded_chunks", 0))
                        else:
                            log.info("Search indexes rebuilt: FTS=%s (embeddings disabled)", 
                                   fts_result.get("indexed_chunks", 0))
                            
                    except Exception as e:
                        log.warning("Search index rebuild failed after auto-seeding: %s", e)
                
                return {
                    "success": True,
                    "first_user_id": first_user_id,
                    "auto_seeding_result": result,
                    "search_indexer": {
                        "vec_available": vec_available,
                        "fts_enabled": True
                    },
                    "message": "First-run setup completed successfully"
                }
            else:
                return {
                    "success": True,
                    "message": "First-run setup completed, no auto-seeding needed"
                }
                
        except Exception as e:
            log.error("First-run setup failed: %s", e)
            return {
                "success": False,
                "error": str(e),
                "message": "First-run setup failed"
            }
    
    def perform_user_onboarding(self, user_id: int, retry_count: int = 0, max_retries: int = 2) -> Dict[str, Any]:
        """Perform onboarding for a new user with retry logic."""
        try:
            log.info("Performing user onboarding for user %s (attempt %d/%d)", user_id, retry_count + 1, max_retries + 1)
            
            # Check if auto-seeding should be performed
            auto_seeding_service = get_auto_seeding_service(self.get_conn)
            result = auto_seeding_service.perform_auto_seeding(user_id)
            
            # If auto-seeding failed and we have retries left, schedule a retry
            if not result.get("success", False) and result.get("action") == "error" and retry_count < max_retries:
                log.warning("Auto-seeding failed for user %s, will retry: %s", user_id, result.get("error", "Unknown error"))
                # Store failed attempt for tracking
                self._record_onboarding_retry(user_id, retry_count, result.get("error", "Unknown error"))
                # Return result indicating retry will be scheduled
                return {
                    "success": True,
                    "user_id": user_id,
                    "auto_seeding_result": result,
                    "message": f"User onboarding will retry (attempt {retry_count + 1}/{max_retries + 1})",
                    "retry_scheduled": True,
                    "retry_count": retry_count
                }
            
            return {
                "success": True,
                "user_id": user_id,
                "auto_seeding_result": result,
                "message": "User onboarding completed",
                "retry_count": retry_count
            }
            
        except Exception as e:
            log.error("User onboarding failed for user %s (attempt %d): %s", user_id, retry_count + 1, e)
            
            # If we have retries left, indicate retry should be scheduled
            if retry_count < max_retries:
                self._record_onboarding_retry(user_id, retry_count, str(e))
                return {
                    "success": True,  # Success means we can retry
                    "user_id": user_id,
                    "error": str(e),
                    "message": f"User onboarding will retry after error (attempt {retry_count + 1}/{max_retries + 1})",
                    "retry_scheduled": True,
                    "retry_count": retry_count
                }
            else:
                # No more retries, this is a final failure
                return {
                    "success": False,
                    "user_id": user_id,
                    "error": str(e),
                    "message": f"User onboarding failed after {max_retries + 1} attempts",
                    "retry_count": retry_count
                }
    
    def _ensure_auto_seeding_schema(self) -> None:
        """Ensure auto-seeding tables exist."""
        conn = self.get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS auto_seeding_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    success BOOLEAN NOT NULL,
                    message TEXT,
                    namespace TEXT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    config TEXT,
                    notes_created INTEGER DEFAULT 0,
                    files_created INTEGER DEFAULT 0,
                    embeddings_created INTEGER DEFAULT 0
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_auto_seeding_user_timestamp 
                ON auto_seeding_log(user_id, timestamp)
            """)
            
            conn.commit()
            
        except Exception as e:
            log.error("Failed to ensure auto-seeding schema: %s", e)
        finally:
            conn.close()
    
    def _ensure_first_user(self) -> Optional[int]:
        """Ensure a first user exists, creating one if necessary."""
        conn = self.get_conn()
        try:
            # Check if any users exist
            cursor = conn.execute("SELECT id FROM users LIMIT 1")
            result = cursor.fetchone()
            
            if result:
                return result[0]  # Return existing user ID
            
            # No users exist, this would typically be handled by the auth system
            # We don't create users here, just return None
            return None
            
        except Exception as e:
            log.error("Error ensuring first user: %s", e)
            return None
        finally:
            conn.close()
    
    def get_initialization_status(self) -> Dict[str, Any]:
        """Get overall initialization status."""
        try:
            conn = self.get_conn()
            
            # Get user and content counts
            cursor = conn.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM notes")
            note_count = cursor.fetchone()[0]
            
            # Get auto-seeding history
            cursor = conn.execute("""
                SELECT COUNT(*) as attempts,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful
                FROM auto_seeding_log
            """)
            
            seeding_stats = cursor.fetchone()
            seeding_attempts = seeding_stats[0] if seeding_stats else 0
            seeding_successful = seeding_stats[1] if seeding_stats else 0
            
            conn.close()
            
            is_fresh = self.is_fresh_installation()
            
            return {
                "is_fresh_installation": is_fresh,
                "user_count": user_count,
                "note_count": note_count,
                "auto_seeding": {
                    "enabled": settings.auto_seeding_enabled,
                    "attempts": seeding_attempts,
                    "successful": seeding_successful,
                    "namespace": settings.auto_seeding_namespace
                },
                "vault_path": str(settings.vault_path),
                "database_path": str(settings.db_path)
            }
            
        except Exception as e:
            log.error("Error getting initialization status: %s", e)
            return {
                "error": str(e),
                "is_fresh_installation": False
            }
    
    def _record_onboarding_retry(self, user_id: int, retry_count: int, error_message: str) -> None:
        """Record onboarding retry attempt for tracking."""
        conn = self.get_conn()
        try:
            # Create retry tracking table if it doesn't exist
            conn.execute("""
                CREATE TABLE IF NOT EXISTS onboarding_retry_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    retry_count INTEGER NOT NULL,
                    error_message TEXT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    status TEXT DEFAULT 'pending'
                )
            """)
            
            # Insert retry log entry
            conn.execute("""
                INSERT INTO onboarding_retry_log (user_id, retry_count, error_message)
                VALUES (?, ?, ?)
            """, (user_id, retry_count, error_message))
            
            conn.commit()
            log.info("Recorded onboarding retry for user %s (attempt %d): %s", user_id, retry_count, error_message)
            
        except Exception as e:
            log.error("Failed to record onboarding retry: %s", e)
        finally:
            conn.close()
    
    def get_failed_onboardings(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get list of users that need onboarding retry."""
        conn = self.get_conn()
        try:
            cursor = conn.execute("""
                SELECT DISTINCT r.user_id, u.username, 
                       COUNT(r.id) as retry_count,
                       MAX(r.timestamp) as last_attempt,
                       r.error_message
                FROM onboarding_retry_log r
                JOIN users u ON r.user_id = u.id
                WHERE r.status = 'pending'
                GROUP BY r.user_id
                HAVING COUNT(r.id) < 3  -- Only include users with less than 3 attempts
                ORDER BY last_attempt DESC
                LIMIT ?
            """, (limit,))
            
            return [
                {
                    "user_id": row[0],
                    "username": row[1],
                    "retry_count": row[2],
                    "last_attempt": row[3],
                    "error_message": row[4]
                }
                for row in cursor.fetchall()
            ]
            
        except Exception as e:
            log.error("Error getting failed onboardings: %s", e)
            return []
        finally:
            conn.close()


# Global instance
_initialization_service = None

def get_initialization_service(get_conn_func):
    """Get global initialization service instance."""
    global _initialization_service
    if _initialization_service is None:
        _initialization_service = InitializationService(get_conn_func)
    return _initialization_service

# Export the service class and functions
__all__ = ["InitializationService", "get_initialization_service"]