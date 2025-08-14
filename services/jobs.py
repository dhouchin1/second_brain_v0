# ──────────────────────────────────────────────────────────────────────────────
# File: services/jobs.py
# ──────────────────────────────────────────────────────────────────────────────
"""
Embedded job runner (SQLite-only) for digests, reindexing, etc.
Usage:
  from services.jobs import JobRunner
  runner = JobRunner(db_path)
  runner.start(app)  # FastAPI lifespan or on_startup event
"""
from __future__ import annotations
import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

UTC = timezone.utc

class JobRunner:
    def __init__(self, db_path: str = 'notes.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.handlers: Dict[str, Callable[[sqlite3.Row, sqlite3.Connection], None]] = {
            'digest': self._handle_digest,
            'reindex': self._handle_reindex,
        }
        self._stop = asyncio.Event()

    def start(self, app=None):
        loop = asyncio.get_event_loop()
        loop.create_task(self._worker())

    async def _worker(self):
        while not self._stop.is_set():
            job = self._take_job()
            if not job:
                await asyncio.sleep(1.0)
                continue
            try:
                self._update_job_status(job['id'], 'running')
                handler = self.handlers.get(job['type'])
                if not handler:
                    raise RuntimeError(f"No handler for job type {job['type']}")
                handler(job, self.conn)
                self._update_job_status(job['id'], 'done')
            except Exception as e:
                self._fail_job(job, e)

    def stop(self):
        self._stop.set()

    def enqueue(self, type_: str, payload: Optional[dict] = None, when: Optional[datetime] = None):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO jobs(type, not_before, payload) VALUES (?,?,?)",
            (type_, (when or datetime.now(tz=UTC)).isoformat(), json.dumps(payload or {}))
        )
        self.conn.commit()
        return cur.lastrowid

    def _take_job(self) -> Optional[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE jobs
            SET status='running', taken_by='local', updated_at=datetime('now')
            WHERE id = (
              SELECT id FROM jobs
              WHERE status='pending' AND (not_before IS NULL OR not_before <= datetime('now'))
              ORDER BY created_at
              LIMIT 1
            )
            RETURNING *;
            """
        )
        return cur.fetchone()

    def _update_job_status(self, job_id: int, status: str):
        self.conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
        self.conn.commit()

    def _fail_job(self, job: sqlite3.Row, e: Exception):
        attempts = job['attempts'] + 1
        if attempts < job['max_attempts']:
            # backoff 2^attempts minutes
            delay = 2 ** attempts
            self.conn.execute(
                "UPDATE jobs SET status='pending', attempts=?, last_error=?, not_before=datetime('now', ?) WHERE id=?",
                (attempts, str(e), f'+{delay} minutes', job['id'])
            )
        else:
            self.conn.execute(
                "UPDATE jobs SET status='failed', attempts=?, last_error=? WHERE id=?",
                (attempts, str(e), job['id'])
            )
        self.conn.commit()

    # ─── Handlers ────────────────────────────────────────────────────────────
    def _handle_digest(self, job: sqlite3.Row, conn: sqlite3.Connection):
        # Naive digest: gather recent notes and write a new summary note stub
        payload = json.loads(job['payload'] or '{}')
        cur = conn.cursor()
        cur.execute("SELECT id, title FROM notes WHERE created_at >= datetime('now','-1 day') ORDER BY created_at DESC")
        items = cur.fetchall()
        titles = '\n'.join(f"- {r['title']}" for r in items)
        title = payload.get('title') or f"Daily Digest — {datetime.now(tz=UTC).date()}"
        body = f"Auto-generated digest stub (local). Items:\n\n{titles}\n"
        cur.execute("INSERT INTO notes(title, body, tags) VALUES (?,?,?)", (title, body, '#digest'))
        conn.commit()

    def _handle_reindex(self, job: sqlite3.Row, conn: sqlite3.Connection):
        # Rebuild FTS from content
        cur = conn.cursor()
        cur.execute("INSERT INTO notes_fts(notes_fts) VALUES('rebuild')")
        conn.commit()