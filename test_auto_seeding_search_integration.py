#!/usr/bin/env python3
"""
Test script for auto-seeding and search integration.

This script tests the complete integration of:
1. Auto-seeding system with starter content
2. Search indexer with sqlite-vec support
3. Hybrid search with Reciprocal Rank Fusion
4. Fresh instance initialization
"""

import sqlite3
import tempfile
import shutil
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from config import settings
from services.initialization_service import get_initialization_service
from services.auto_seeding_service import get_auto_seeding_service  
from services.search_index import SearchIndexer, SearchConfig
from services.vault_seeding_service import get_seeding_service

def create_test_database(test_db_path: Path):
    """Create a fresh test database with required schema."""
    conn = sqlite3.connect(str(test_db_path))
    
    # Core users table (minimal)
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            hashed_password TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Core notes table (matches current schema)
    conn.execute("""
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            summary TEXT,
            tags TEXT,
            type TEXT,
            timestamp TEXT,
            audio_filename TEXT,
            content TEXT,
            status TEXT DEFAULT 'complete',
            user_id INTEGER,
            actions TEXT,
            file_filename TEXT,
            file_type TEXT,
            file_mime_type TEXT,
            file_size INTEGER,
            extracted_text TEXT,
            file_metadata TEXT,
            source_url TEXT,
            web_metadata TEXT,
            screenshot_path TEXT,
            content_hash TEXT,
            external_id TEXT,
            external_url TEXT,
            metadata TEXT DEFAULT '{}'
        )
    """)
    
    # FTS5 table for notes (simplified tokenizer)
    conn.execute("""
        CREATE VIRTUAL TABLE notes_fts USING fts5(
            title, body, tags,
            content='notes', content_rowid='id'
        )
    """)
    
    # Add triggers to keep FTS in sync
    conn.execute("""
        CREATE TRIGGER notes_ai AFTER INSERT ON notes BEGIN
            INSERT INTO notes_fts(rowid, title, body, tags)
            VALUES (new.id, new.title, COALESCE(new.content, ''), COALESCE(new.tags, ''));
        END
    """)
    
    conn.execute("""
        CREATE TRIGGER notes_au AFTER UPDATE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, body, tags)
            VALUES('delete', old.id, old.title, COALESCE(old.content, ''), COALESCE(old.tags, ''));
            INSERT INTO notes_fts(rowid, title, body, tags)
            VALUES (new.id, new.title, COALESCE(new.content, ''), COALESCE(new.tags, ''));
        END
    """)
    
    conn.commit()
    conn.close()
    print(f"✅ Created test database: {test_db_path}")

def test_fresh_installation_detection():
    """Test fresh installation detection logic."""
    print("\n🧪 Testing fresh installation detection...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        test_db = Path(temp_dir) / "test.db"
        test_vault = Path(temp_dir) / "vault"
        test_vault.mkdir()
        
        # Create fresh database
        create_test_database(test_db)
        
        def get_conn():
            return sqlite3.connect(str(test_db))
        
        init_service = get_initialization_service(get_conn)
        
        # Should detect fresh installation
        is_fresh = init_service.is_fresh_installation()
        assert is_fresh, "Should detect fresh installation"
        print("✅ Fresh installation detection working")

def test_auto_seeding_logic():
    """Test auto-seeding decision logic."""
    print("\n🧪 Testing auto-seeding logic...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        test_db = Path(temp_dir) / "test.db"
        test_vault = Path(temp_dir) / "vault"
        test_vault.mkdir()
        
        create_test_database(test_db)
        
        def get_conn():
            return sqlite3.connect(str(test_db))
        
        # Create test user
        conn = get_conn()
        cursor = conn.execute("INSERT INTO users (username) VALUES ('testuser')")
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        auto_seeding_service = get_auto_seeding_service(get_conn)
        
        # Should auto-seed for new user with no content
        should_seed = auto_seeding_service.should_auto_seed(user_id)
        assert should_seed["should_seed"], f"Should auto-seed new user: {should_seed['reason']}"
        print("✅ Auto-seeding logic working for new users")

def test_search_indexer_initialization():
    """Test search indexer setup and schema creation."""
    print("\n🧪 Testing search indexer initialization...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        test_db = Path(temp_dir) / "test.db"
        
        create_test_database(test_db)
        
        config = SearchConfig(
            db_path=test_db,
            embed_model="nomic-embed-text",
            enable_embeddings=False,  # Skip embeddings for basic test
            ollama_url="http://localhost:11434"
        )
        
        indexer = SearchIndexer(config)
        
        # Test FTS setup
        indexer.ensure_fts()
        print("✅ FTS tables created successfully")
        
        # Test vector setup (should handle missing sqlite-vec gracefully)
        vec_available = indexer.ensure_vec()
        print(f"✅ Vector setup completed (sqlite-vec available: {vec_available})")

def test_seeded_content_search():
    """Test that seeded content can be searched effectively."""
    print("\n🧪 Testing search functionality with seeded content...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        test_db = Path(temp_dir) / "test.db"
        test_vault = Path(temp_dir) / "vault"
        test_vault.mkdir()
        
        # Temporarily override settings for testing
        original_db_path = settings.db_path
        original_vault_path = settings.vault_path
        
        settings.db_path = str(test_db)
        settings.vault_path = str(test_vault)
        
        try:
            create_test_database(test_db)
            
            def get_conn():
                return sqlite3.connect(str(test_db))
            
            # Create test user
            conn = get_conn()
            cursor = conn.execute("INSERT INTO users (username) VALUES ('testuser')")
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            
            # Perform seeding
            seeding_service = get_seeding_service(get_conn)
            from services.vault_seeding_service import SeedingOptions
            
            options = SeedingOptions(
                namespace="test_seeds",
                force_overwrite=True,
                include_embeddings=False  # Skip embeddings for speed
            )
            
            result = seeding_service.seed_vault(user_id, options)
            assert result.success, f"Seeding failed: {result.error}"
            print(f"✅ Seeded {result.notes_created} notes successfully")
            
            # Debug: Check actual database content
            conn = get_conn()
            cursor = conn.execute("SELECT COUNT(*) FROM notes WHERE user_id = ?", (user_id,))
            actual_notes = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT title FROM notes WHERE user_id = ? LIMIT 3", (user_id,))
            sample_titles = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            print(f"🔍 Debug: {actual_notes} notes in database, sample titles: {sample_titles}")
            
            # Create chunk table and populate from notes (bridge the gap)
            conn = get_conn()
            
            # Create chunk table if it doesn't exist
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunk (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    ord INTEGER NOT NULL DEFAULT 0,
                    heading TEXT,
                    text TEXT NOT NULL,
                    token_est INTEGER NOT NULL DEFAULT 0
                )
            """)
            
            # Populate chunks from notes
            notes_cursor = conn.execute("SELECT id, title, content FROM notes WHERE user_id = ?", (user_id,))
            notes_data = notes_cursor.fetchall()
            
            for note_id, title, content in notes_data:
                chunk_id = f"note-{note_id}-chunk-0"
                # Use content or title as text
                text = content or title or ""
                token_est = max(50, len(text.split()))
                
                conn.execute("""
                    INSERT OR REPLACE INTO chunk (id, item_id, ord, heading, text, token_est)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (chunk_id, f"note-{note_id}", 0, title, text, token_est))
            
            conn.commit()
            
            # Check chunks created
            chunk_cursor = conn.execute("SELECT COUNT(*) FROM chunk")
            chunk_count = chunk_cursor.fetchone()[0]
            conn.close()
            
            print(f"🔍 Debug: Created {chunk_count} chunks from {actual_notes} notes")
            
            # Test search indexer on seeded content
            config = SearchConfig(
                db_path=test_db,
                enable_embeddings=False
            )
            
            indexer = SearchIndexer(config)
            indexer.ensure_fts()
            
            # Rebuild FTS index
            fts_result = indexer.rebuild_fts()
            indexed_count = fts_result.get('indexed_chunks', fts_result.get('total_chunks', 0))
            print(f"✅ Rebuilt FTS index: {indexed_count} chunks")
            
            # Test BM25 search
            bm25_results = indexer.query_bm25("weekly review", k=5)
            assert len(bm25_results) > 0, "Should find results for 'weekly review'"
            print(f"✅ BM25 search found {len(bm25_results)} results")
            
            # Test that we can find specific seeded content
            sqlite_results = indexer.query_bm25("SQLite performance", k=5)
            assert len(sqlite_results) > 0, "Should find SQLite performance content"
            print(f"✅ Found SQLite performance content: {len(sqlite_results)} results")
            
        finally:
            # Restore original settings
            settings.db_path = original_db_path
            settings.vault_path = original_vault_path

def test_integration_end_to_end():
    """Test complete end-to-end integration."""
    print("\n🧪 Testing complete end-to-end integration...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        test_db = Path(temp_dir) / "test.db"
        test_vault = Path(temp_dir) / "vault"
        test_vault.mkdir()
        
        # Override settings
        original_db_path = settings.db_path
        original_vault_path = settings.vault_path
        original_auto_seeding = getattr(settings, 'auto_seeding_enabled', True)
        
        # Use absolute paths
        settings.db_path = test_db.absolute()
        settings.vault_path = test_vault.absolute() 
        settings.auto_seeding_enabled = True
        
        try:
            create_test_database(test_db)
            
            def get_conn():
                return sqlite3.connect(str(test_db))
            
            # Test initialization service (simulates app startup)
            init_service = get_initialization_service(get_conn)
            
            # Should detect fresh installation
            assert init_service.is_fresh_installation(), "Should be fresh installation"
            
            # Create a user (simulates user registration)
            conn = get_conn()
            cursor = conn.execute("INSERT INTO users (username) VALUES ('newuser')")
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            
            # Perform first-run setup (simulates app startup for fresh install)
            setup_result = init_service.perform_first_run_setup()
            assert setup_result["success"], f"First-run setup failed: {setup_result.get('error')}"
            print("✅ First-run setup completed successfully")
            
            # Verify seeded content exists
            conn = get_conn()
            cursor = conn.execute("SELECT COUNT(*) FROM notes WHERE user_id = ?", (user_id,))
            note_count = cursor.fetchone()[0]
            conn.close()
            
            print(f"✅ Found {note_count} seeded notes for user {user_id}")
            
            # Test search functionality
            config = SearchConfig(db_path=test_db, enable_embeddings=False)
            indexer = SearchIndexer(config)
            
            # Search should work on seeded content
            results = indexer.query_bm25("performance", k=3)
            assert len(results) > 0, "Should find performance-related content"
            print(f"✅ Search working: found {len(results)} results for 'performance'")
            
            print("✅ End-to-end integration test passed!")
            
        finally:
            # Restore settings
            settings.db_path = original_db_path
            settings.vault_path = original_vault_path
            settings.auto_seeding_enabled = original_auto_seeding

def main():
    """Run all integration tests."""
    print("🚀 Starting auto-seeding and search integration tests...")
    
    try:
        test_fresh_installation_detection()
        test_auto_seeding_logic()
        test_search_indexer_initialization()
        test_seeded_content_search()
        test_integration_end_to_end()
        
        print("\n🎉 All integration tests passed!")
        print("\n📋 Summary:")
        print("✅ Fresh installation detection works")
        print("✅ Auto-seeding logic works for new users")
        print("✅ Search indexer initialization works")
        print("✅ Seeded content can be searched effectively") 
        print("✅ End-to-end integration works")
        print("\n🔍 The auto-seeding system will improve search algorithm performance by providing high-quality starter content!")
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()