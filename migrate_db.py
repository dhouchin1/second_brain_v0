#!/usr/bin/env python3
"""
Database migration runner for Second Brain
Applies migrations in order and tracks applied migrations
"""

import sqlite3
import os
import re
from pathlib import Path
from typing import List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MigrationRunner:
    def __init__(self, db_path: str, migrations_dir: str = "db/migrations"):
        self.db_path = db_path
        self.migrations_dir = Path(migrations_dir)
        self._ensure_migrations_table()
    
    def _ensure_migrations_table(self):
        """Create migrations tracking table if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL DEFAULT (datetime('now')),
                checksum TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def _get_applied_migrations(self) -> List[str]:
        """Get list of already applied migrations"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT migration_name FROM schema_migrations ORDER BY migration_name")
        applied = [row[0] for row in cursor.fetchall()]
        conn.close()
        return applied
    
    def _get_pending_migrations(self) -> List[Tuple[str, Path]]:
        """Get list of migration files that haven't been applied"""
        applied = set(self._get_applied_migrations())
        
        migration_files = []
        if self.migrations_dir.exists():
            for file_path in self.migrations_dir.glob("*.sql"):
                migration_name = file_path.stem
                if migration_name not in applied:
                    migration_files.append((migration_name, file_path))
        
        # Sort by migration name (should be numbered)
        migration_files.sort(key=lambda x: x[0])
        return migration_files
    
    def _calculate_checksum(self, content: str) -> str:
        """Calculate simple checksum for migration content"""
        import hashlib
        return hashlib.md5(content.encode()).hexdigest()
    
    def apply_migration(self, migration_name: str, file_path: Path) -> bool:
        """Apply a single migration file"""
        try:
            logger.info(f"Applying migration: {migration_name}")
            
            # Read migration file
            with open(file_path, 'r') as f:
                sql_content = f.read()
            
            checksum = self._calculate_checksum(sql_content)
            
            # Apply migration
            conn = sqlite3.connect(self.db_path)
            
            # Split on semicolons and execute each statement
            statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
            
            for statement in statements:
                if statement:
                    conn.execute(statement)
            
            # Record migration as applied
            conn.execute(
                "INSERT INTO schema_migrations (migration_name, checksum) VALUES (?, ?)",
                (migration_name, checksum)
            )
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Successfully applied: {migration_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to apply migration {migration_name}: {e}")
            return False
    
    def run_migrations(self) -> bool:
        """Run all pending migrations"""
        pending = self._get_pending_migrations()
        
        if not pending:
            logger.info("📄 No pending migrations")
            return True
        
        logger.info(f"📋 Found {len(pending)} pending migrations")
        
        success = True
        for migration_name, file_path in pending:
            if not self.apply_migration(migration_name, file_path):
                success = False
                break
        
        if success:
            logger.info("🎉 All migrations applied successfully!")
        else:
            logger.error("💥 Migration failed - stopping execution")
        
        return success
    
    def status(self):
        """Show migration status"""
        applied = self._get_applied_migrations()
        pending = self._get_pending_migrations()
        
        print(f"\n📊 Migration Status for: {self.db_path}")
        print("=" * 50)
        
        print(f"\n✅ Applied migrations ({len(applied)}):")
        for migration in applied:
            print(f"  - {migration}")
        
        print(f"\n⏳ Pending migrations ({len(pending)}):")
        for migration_name, file_path in pending:
            print(f"  - {migration_name} ({file_path})")
        
        if not pending:
            print("  (none)")
        
        print()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument("--db", default="notes.db", help="Database path")
    parser.add_argument("--migrations-dir", default="db/migrations", help="Migrations directory")
    parser.add_argument("--status", action="store_true", help="Show migration status")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    
    args = parser.parse_args()
    
    runner = MigrationRunner(args.db, args.migrations_dir)
    
    if args.status:
        runner.status()
    elif args.dry_run:
        pending = runner._get_pending_migrations()
        print(f"Would apply {len(pending)} migrations:")
        for name, path in pending:
            print(f"  - {name}")
    else:
        runner.run_migrations()


if __name__ == "__main__":
    main()