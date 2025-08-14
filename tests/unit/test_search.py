import pytest
from unittest.mock import patch
import tempfile
from pathlib import Path
import sqlite3
from search_engine import EnhancedSearchEngine

class TestEnhancedSearchEngine:
    
    @pytest.fixture
    def search_engine(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
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
