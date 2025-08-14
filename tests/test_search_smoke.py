# ──────────────────────────────────────────────────────────────────────────────
# File: tests/test_search_smoke.py
# ──────────────────────────────────────────────────────────────────────────────
import os
import sqlite3
import pytest
from services.search_adapter import SearchService

@pytest.fixture()
def svc(tmp_path):
    db = tmp_path / 'test.db'
    # No sqlite-vec in CI: run keyword-only
    os.environ.pop('SQLITE_VEC_PATH', None)
    s = SearchService(db_path=str(db))
    s.upsert_note(None, 'Hello World', 'This is a hello note about FastAPI and search.', '#hello')
    s.upsert_note(None, 'Grocery List', 'eggs\nmilk\nbananas', '#list')
    return s

@pytest.mark.parametrize('mode',["keyword","hybrid"]) 
def test_search_basic(svc, mode):
    res = svc.search('hello', mode=mode, k=5)
    assert any('Hello World' in r['title'] for r in res)