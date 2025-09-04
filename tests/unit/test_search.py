import pytest
import tempfile
from pathlib import Path
import sqlite3
from services.search_adapter import SearchService

class TestSearchService:
    
    @pytest.fixture
    def search_engine(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
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
