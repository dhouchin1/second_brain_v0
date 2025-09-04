"""
Auto-Seeding Service for Second Brain

Automatically seeds new Second Brain instances with starter content to improve
search algorithm performance and provide immediate user value.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from services.vault_seeding_service import get_seeding_service, SeedingOptions
from config import settings

log = logging.getLogger(__name__)

@dataclass
class AutoSeedingConfig:
    """Configuration for auto-seeding behavior."""
    enabled: bool = True
    namespace: str = ".starter_content"
    include_embeddings: bool = True
    embed_model: str = "nomic-embed-text"
    ollama_url: str = "http://localhost:11434"
    skip_if_content_exists: bool = True
    min_notes_threshold: int = 5  # Don't auto-seed if user already has content

class AutoSeedingService:
    """Service for automatically seeding new Second Brain instances."""
    
    def __init__(self, get_conn_func):
        """Initialize with database connection function."""
        self.get_conn = get_conn_func
        self.config = self._load_config()
    
    def _load_config(self) -> AutoSeedingConfig:
        """Load auto-seeding configuration from environment/settings."""
        return AutoSeedingConfig(
            enabled=getattr(settings, 'auto_seeding_enabled', True),
            namespace=getattr(settings, 'auto_seeding_namespace', '.starter_content'),
            include_embeddings=getattr(settings, 'auto_seeding_embeddings', True),
            embed_model=getattr(settings, 'auto_seeding_embed_model', 'nomic-embed-text'),
            ollama_url=getattr(settings, 'ollama_api_url', 'http://localhost:11434').replace('/api/generate', ''),
            skip_if_content_exists=getattr(settings, 'auto_seeding_skip_if_content', True),
            min_notes_threshold=getattr(settings, 'auto_seeding_min_notes', 5)
        )
    
    def should_auto_seed(self, user_id: int) -> Dict[str, Any]:
        """Determine if auto-seeding should be performed for a user."""
        if not self.config.enabled:
            return {
                "should_seed": False,
                "reason": "Auto-seeding disabled in configuration"
            }
        
        conn = self.get_conn()
        try:
            # Check if user already has content
            cursor = conn.execute("""
                SELECT COUNT(*) as note_count
                FROM notes 
                WHERE user_id = ? AND status != 'failed'
            """, (user_id,))
            
            note_count = cursor.fetchone()[0]
            
            # Check if already auto-seeded
            cursor = conn.execute("""
                SELECT COUNT(*) as seed_count
                FROM notes 
                WHERE user_id = ? 
                AND (title LIKE '%Weekly Review%' 
                     OR title LIKE '%SQLite Performance%' 
                     OR content LIKE '%seed-%')
            """, (user_id,))
            
            seed_count = cursor.fetchone()[0]
            
            # Decision logic
            if seed_count > 0:
                return {
                    "should_seed": False,
                    "reason": f"Already has {seed_count} seed items",
                    "note_count": note_count,
                    "seed_count": seed_count
                }
            
            if self.config.skip_if_content_exists and note_count >= self.config.min_notes_threshold:
                return {
                    "should_seed": False,
                    "reason": f"User already has {note_count} notes (threshold: {self.config.min_notes_threshold})",
                    "note_count": note_count,
                    "seed_count": seed_count
                }
            
            return {
                "should_seed": True,
                "reason": f"New user with {note_count} notes, auto-seeding enabled",
                "note_count": note_count,
                "seed_count": seed_count
            }
            
        except Exception as e:
            log.error("Error checking auto-seed conditions: %s", e)
            return {
                "should_seed": False,
                "reason": f"Error checking conditions: {str(e)}"
            }
        finally:
            conn.close()
    
    def perform_auto_seeding(self, user_id: int, force: bool = False) -> Dict[str, Any]:
        """Perform auto-seeding for a user if conditions are met."""
        try:
            # Check if we should auto-seed
            should_seed_result = self.should_auto_seed(user_id)
            if not force and not should_seed_result["should_seed"]:
                return {
                    "success": True,
                    "action": "skipped",
                    "reason": should_seed_result["reason"],
                    "details": should_seed_result
                }
            
            # Get seeding service and perform seeding
            seeding_service = get_seeding_service(self.get_conn)
            
            options = SeedingOptions(
                namespace=self.config.namespace,
                force_overwrite=False,
                include_embeddings=self.config.include_embeddings,
                embed_model=self.config.embed_model,
                ollama_url=self.config.ollama_url
            )
            
            log.info("Auto-seeding vault for user %s with namespace %s", user_id, self.config.namespace)
            result = seeding_service.seed_vault(user_id, options)
            
            if result.success:
                # Record auto-seeding completion
                self._record_auto_seeding(user_id, True, result.message)
                
                return {
                    "success": True,
                    "action": "seeded",
                    "message": f"Auto-seeded vault: {result.message}",
                    "details": {
                        "notes_created": result.notes_created,
                        "embeddings_created": result.embeddings_created,
                        "files_written": result.files_written,
                        "namespace": self.config.namespace
                    }
                }
            else:
                # Record auto-seeding failure
                self._record_auto_seeding(user_id, False, result.error or result.message)
                
                return {
                    "success": False,
                    "action": "failed",
                    "message": f"Auto-seeding failed: {result.message}",
                    "error": result.error
                }
                
        except Exception as e:
            log.error("Auto-seeding failed for user %s: %s", user_id, e)
            self._record_auto_seeding(user_id, False, str(e))
            
            return {
                "success": False,
                "action": "error",
                "message": "Auto-seeding encountered an error",
                "error": str(e)
            }
    
    def _record_auto_seeding(self, user_id: int, success: bool, message: str) -> None:
        """Record auto-seeding attempt in database for tracking."""
        conn = self.get_conn()
        try:
            # Create auto_seeding_log table if it doesn't exist
            conn.execute("""
                CREATE TABLE IF NOT EXISTS auto_seeding_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    success BOOLEAN NOT NULL,
                    message TEXT,
                    namespace TEXT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    config TEXT
                )
            """)
            
            # Insert log entry
            conn.execute("""
                INSERT INTO auto_seeding_log (user_id, success, message, namespace, config)
                VALUES (?, ?, ?, ?, ?)
            """, (
                user_id,
                success,
                message,
                self.config.namespace,
                str(self.config.__dict__)
            ))
            
            conn.commit()
            
        except Exception as e:
            log.error("Failed to record auto-seeding log: %s", e)
        finally:
            conn.close()
    
    def get_auto_seeding_history(self, user_id: int) -> List[Dict[str, Any]]:
        """Get auto-seeding history for a user."""
        conn = self.get_conn()
        try:
            cursor = conn.execute("""
                SELECT id, success, message, namespace, timestamp, config
                FROM auto_seeding_log 
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT 10
            """, (user_id,))
            
            return [
                {
                    "id": row[0],
                    "success": bool(row[1]),
                    "message": row[2],
                    "namespace": row[3],
                    "timestamp": row[4],
                    "config": row[5]
                }
                for row in cursor.fetchall()
            ]
            
        except Exception as e:
            log.error("Error getting auto-seeding history: %s", e)
            return []
        finally:
            conn.close()
    
    def check_auto_seeding_status(self) -> Dict[str, Any]:
        """Get overall auto-seeding system status."""
        conn = self.get_conn()
        try:
            # Get recent auto-seeding activity
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_attempts,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed
                FROM auto_seeding_log 
                WHERE timestamp > datetime('now', '-7 days')
            """)
            
            stats = cursor.fetchone()
            total_attempts = stats[0] if stats else 0
            successful = stats[1] if stats else 0
            failed = stats[2] if stats else 0
            
            return {
                "enabled": self.config.enabled,
                "config": self.config.__dict__,
                "recent_stats": {
                    "total_attempts": total_attempts,
                    "successful": successful,
                    "failed": failed,
                    "success_rate": (successful / total_attempts * 100) if total_attempts > 0 else 0
                }
            }
            
        except Exception as e:
            log.error("Error checking auto-seeding status: %s", e)
            return {
                "enabled": self.config.enabled,
                "config": self.config.__dict__,
                "error": str(e)
            }
        finally:
            conn.close()


# Global instance
_auto_seeding_service = None

def get_auto_seeding_service(get_conn_func):
    """Get global auto-seeding service instance."""
    global _auto_seeding_service
    if _auto_seeding_service is None:
        _auto_seeding_service = AutoSeedingService(get_conn_func)
    return _auto_seeding_service

# Export the service class and functions
__all__ = ["AutoSeedingService", "AutoSeedingConfig", "get_auto_seeding_service"]