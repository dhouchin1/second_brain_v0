# ──────────────────────────────────────────────────────────────────────────────
# File: scripts/dev_seed.py
# ──────────────────────────────────────────────────────────────────────────────
"""Seed a few notes for manual testing."""
import os
from services.search_adapter import SearchService

if __name__ == '__main__':
    svc = SearchService(db_path=os.getenv('SQLITE_DB','notes.db'), vec_ext_path=os.getenv('SQLITE_VEC_PATH'))
    svc.upsert_note(None, 'Second Brain setup', 'Finish Shortcuts + Bookmarklet today.', '#todo #setup')
    svc.upsert_note(None, 'ArchiveBox idea', 'Queue links nightly and snapshot with WARC.', '#archive #idea')
    svc.upsert_note(None, 'Daily Digest sketch', 'Outline jobs and rules for local runner.', '#digest #idea')
    print('Seeded!')