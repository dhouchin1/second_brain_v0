"""
Vault Seeding Service for Second Brain

This service provides programmatic access to vault seeding functionality,
allowing the web application to initialize vaults with starter content.
"""

import logging
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

# Import the seeding script functionality
import sys
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

try:
    from seed_starter_vault import (
        seed_active_vault, SeedCfg, SEED_NOTES, SEED_BOOKMARKS,
        try_ollama_embed, ensure_embeddings_schema, db_conn
    )
except ImportError as e:
    logging.warning("Could not import seeding functionality: %s", e)
    seed_active_vault = None

from config import settings

log = logging.getLogger(__name__)

@dataclass
class SeedingResult:
    """Result of a seeding operation."""
    success: bool
    message: str
    notes_created: int = 0
    embeddings_created: int = 0
    files_written: int = 0
    error: Optional[str] = None

@dataclass
class SeedingOptions:
    """Configuration options for vault seeding."""
    namespace: str = ".seed_samples"
    force_overwrite: bool = False
    include_embeddings: bool = True
    embed_model: str = "nomic-embed-text"
    ollama_url: str = "http://localhost:11434"

class VaultSeedingService:
    """Service for seeding vaults with starter content."""
    
    def __init__(self, get_conn_func):
        """Initialize with database connection function."""
        self.get_conn = get_conn_func
        self._validate_dependencies()
    
    def _validate_dependencies(self) -> bool:
        """Check if all seeding dependencies are available."""
        if seed_active_vault is None:
            log.error("Seeding script not available")
            return False
        
        # Check if vault path exists
        vault_path = Path(settings.vault_path)
        if not vault_path.exists():
            log.warning("Vault path does not exist: %s", vault_path)
            vault_path.mkdir(parents=True, exist_ok=True)
        
        return True
    
    def get_seeding_status(self, user_id: int) -> Dict[str, Any]:
        """Check if vault has been seeded and get status."""
        conn = self.get_conn()
        try:
            # Check for seed notes in database
            cursor = conn.execute("""
                SELECT COUNT(*) as seed_count
                FROM notes 
                WHERE title LIKE 'seed-%' OR content LIKE '%seed-%'
                AND user_id = ?
            """, (user_id,))
            
            seed_count = cursor.fetchone()[0]
            
            # Check for seed files in vault
            vault_path = Path(settings.vault_path)
            seed_namespace = vault_path / ".seed_samples"
            files_exist = seed_namespace.exists() and any(seed_namespace.rglob("*.md"))
            
            return {
                "is_seeded": seed_count > 0 or files_exist,
                "seed_notes_count": seed_count,
                "seed_files_exist": files_exist,
                "vault_path": str(vault_path),
                "seed_namespace": str(seed_namespace) if seed_namespace.exists() else None
            }
            
        except Exception as e:
            log.error("Error checking seeding status: %s", e)
            return {
                "is_seeded": False,
                "error": str(e)
            }
        finally:
            conn.close()
    
    def get_available_seed_content(self) -> Dict[str, Any]:
        """Get information about available seed content."""
        return {
            "notes": [
                {
                    "id": note["id"],
                    "title": note["title"],
                    "type": note["type"],
                    "tags": note["tags"].split(", "),
                    "summary": note["summary"]
                }
                for note in SEED_NOTES
            ],
            "bookmarks": [
                {
                    "id": bookmark["id"],
                    "title": bookmark["title"],
                    "url": bookmark["url"],
                    "tags": bookmark["tags"].split(", "),
                    "summary": bookmark["summary"]
                }
                for bookmark in SEED_BOOKMARKS
            ],
            "total_items": len(SEED_NOTES) + len(SEED_BOOKMARKS)
        }
    
    def seed_vault(self, user_id: int, options: SeedingOptions) -> SeedingResult:
        """Seed the vault with starter content."""
        if not self._validate_dependencies():
            return SeedingResult(
                success=False,
                message="Seeding dependencies not available",
                error="Missing seeding script or configuration"
            )
        
        try:
            # Create seeding configuration
            cfg = SeedCfg(
                db_path=Path(settings.db_path),
                vault_path=Path(settings.vault_path),
                namespace=options.namespace,
                force=options.force_overwrite,
                no_embed=not options.include_embeddings,
                embed_model=options.embed_model,
                ollama_url=options.ollama_url
            )
            
            # Count existing content before seeding
            initial_status = self.get_seeding_status(user_id)
            initial_count = initial_status.get("seed_notes_count", 0)
            
            # Perform the seeding
            seed_active_vault(cfg)
            
            # Count content after seeding
            final_status = self.get_seeding_status(user_id)
            final_count = final_status.get("seed_notes_count", 0)
            
            notes_created = final_count - initial_count
            
            # Count files written
            seed_path = Path(settings.vault_path) / options.namespace
            files_written = len(list(seed_path.rglob("*.md"))) if seed_path.exists() else 0
            
            return SeedingResult(
                success=True,
                message=f"Successfully seeded vault with {notes_created} notes and {files_written} files",
                notes_created=notes_created,
                files_written=files_written,
                embeddings_created=notes_created if options.include_embeddings else 0
            )
            
        except Exception as e:
            log.error("Vault seeding failed: %s", e)
            return SeedingResult(
                success=False,
                message="Vault seeding failed",
                error=str(e)
            )
    
    def clear_seed_content(self, user_id: int, namespace: str = ".seed_samples") -> SeedingResult:
        """Remove seed content from vault and database."""
        try:
            # Remove from database
            conn = self.get_conn()
            try:
                cursor = conn.execute("""
                    DELETE FROM notes 
                    WHERE (title LIKE 'seed-%' OR content LIKE '%seed-%')
                    AND user_id = ?
                """, (user_id,))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
            finally:
                conn.close()
            
            # Remove files
            seed_path = Path(settings.vault_path) / namespace
            files_removed = 0
            if seed_path.exists():
                for file_path in seed_path.rglob("*.md"):
                    file_path.unlink()
                    files_removed += 1
                
                # Remove empty directories
                try:
                    seed_path.rmdir()
                except OSError:
                    pass  # Directory not empty, leave it
            
            return SeedingResult(
                success=True,
                message=f"Removed {deleted_count} seed notes and {files_removed} files",
                notes_created=-deleted_count,  # Negative indicates removal
                files_written=-files_removed
            )
            
        except Exception as e:
            log.error("Failed to clear seed content: %s", e)
            return SeedingResult(
                success=False,
                message="Failed to clear seed content",
                error=str(e)
            )
    
    def test_ollama_connection(self, url: str = "http://localhost:11434") -> Dict[str, Any]:
        """Test connection to Ollama for embeddings."""
        try:
            test_result = try_ollama_embed(["test"], url=url)
            return {
                "available": test_result is not None,
                "url": url,
                "message": "Ollama connection successful" if test_result else "Ollama connection failed"
            }
        except Exception as e:
            return {
                "available": False,
                "url": url,
                "message": f"Ollama connection error: {str(e)}"
            }
    
    def preview_seeding_impact(self, user_id: int) -> Dict[str, Any]:
        """Preview what would happen if seeding is performed."""
        current_status = self.get_seeding_status(user_id)
        available_content = self.get_available_seed_content()
        ollama_status = self.test_ollama_connection()
        
        return {
            "current_status": current_status,
            "available_content": available_content,
            "ollama_status": ollama_status,
            "estimated_notes": available_content["total_items"],
            "estimated_files": available_content["total_items"],
            "estimated_embeddings": available_content["total_items"] if ollama_status["available"] else 0,
            "will_overwrite": current_status["is_seeded"]
        }

# Global instance - initialized when first imported
_seeding_service = None

def get_seeding_service(get_conn_func):
    """Get global seeding service instance."""
    global _seeding_service
    if _seeding_service is None:
        _seeding_service = VaultSeedingService(get_conn_func)
    return _seeding_service

# Export the service class and functions
__all__ = ["VaultSeedingService", "SeedingResult", "SeedingOptions", "get_seeding_service"]