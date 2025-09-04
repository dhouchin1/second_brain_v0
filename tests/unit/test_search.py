import pytest
<<<<<<< HEAD
import tempfile
from pathlib import Path
import sqlite3
from services.search_adapter import SearchService

class TestSearchService:
=======
from unittest.mock import patch
import tempfile
from pathlib import Path
import sqlite3
from search_engine import EnhancedSearchEngine

class TestEnhancedSearchEngine:
>>>>>>> origin/main
    
    @pytest.fixture
    def search_engine(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
<<<<<<< HEAD
            svc = SearchService(db_path=tmp.name)
            yield svc
            Path(tmp.name).unlink()
    
    def test_fts_search(self, search_engine: SearchService):
        """Test FTS search functionality"""
        # Add test data (service schema: notes(title, body, tags, ...), FTS triggers maintain notes_fts)
        conn = search_engine.conn
        conn.execute("INSERT INTO notes (id, title, body, tags) VALUES (1, 'Test Note', 'Meeting content', '#test')")
        conn.commit()
        
        results = search_engine.search("meeting", mode='keyword', k=10)
        assert len(results) > 0
        assert results[0]["id"] == 1
=======
            engine = EnhancedSearchEngine(tmp.name)
            yield engine
            Path(tmp.name).unlink()
    
    def test_fts_search(self, search_engine):
        """Test FTS search functionality"""
        # Add test data
        conn = sqlite3.connect(search_engine.db_path)
        conn.execute("INSERT INTO notes (id, title, content, user_id) VALUES (1, 'Test Note', 'Meeting content', 1)")
        conn.execute("INSERT INTO notes_fts5 (rowid, title, content) VALUES (1, 'Test Note', 'Meeting content')")
        conn.commit()
        conn.close()
        
        results = search_engine.search("meeting", 1, 10)
        assert len(results) > 0
        assert results[0].note_id == 1
>>>>>>> origin/main
