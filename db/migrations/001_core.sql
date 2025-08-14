# ──────────────────────────────────────────────────────────────────────────────
# File: db/migrations/001_core.sql
# ──────────────────────────────────────────────────────────────────────────────
-- Core schema for local-first search + jobs (FTS5 required)
PRAGMA foreign_keys=ON;

-- Notes (simplified)
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  body  TEXT NOT NULL DEFAULT '',
  tags  TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at);
CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at);

-- FTS5 virtual table referencing notes
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
  title, body, tags,
  content='notes', content_rowid='id',
  tokenize='unicode61 remove_diacritics 2 stemmer porter'
);

-- Triggers to keep FTS5 in sync with notes
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
  INSERT INTO notes_fts(rowid, title, body, tags)
  VALUES (new.id, new.title, new.body, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, title, body, tags)
  VALUES('delete', old.id, old.title, old.body, old.tags);
  INSERT INTO notes_fts(rowid, title, body, tags)
  VALUES (new.id, new.title, new.body, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, title, body, tags)
  VALUES('delete', old.id, old.title, old.body, old.tags);
END;

-- Jobs & Rules (embedded automation)
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', -- pending|running|done|failed
  not_before TEXT,                         -- schedule time (UTC)
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  payload TEXT NOT NULL DEFAULT '{}',      -- JSON
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  taken_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_time ON jobs(status, not_before);

CREATE TABLE IF NOT EXISTS job_logs (
  id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL,
  ts TEXT NOT NULL DEFAULT (datetime('now')),
  level TEXT NOT NULL DEFAULT 'info',
  message TEXT NOT NULL,
  FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

-- Optional: simple rules registry for future expansion
CREATE TABLE IF NOT EXISTS rules (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  definition TEXT NOT NULL DEFAULT '{}' -- JSON (conditions, actions)
);

-- housekeeping trigger
CREATE TRIGGER IF NOT EXISTS jobs_touch AFTER UPDATE ON jobs BEGIN
  UPDATE jobs SET updated_at = datetime('now') WHERE id = new.id;
END;

# ──────────────────────────────────────────────────────────────────────────────
# File: db/migrations/001_core.sql
# ──────────────────────────────────────────────────────────────────────────────
-- Core schema for local-first search + jobs (FTS5 required)
PRAGMA foreign_keys=ON;

-- Notes (simplified)
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  body  TEXT NOT NULL DEFAULT '',
  tags  TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at);
CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at);

-- FTS5 virtual table referencing notes
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
  title, body, tags,
  content='notes', content_rowid='id',
  tokenize='unicode61 remove_diacritics 2 stemmer porter'
);

-- Triggers to keep FTS5 in sync with notes
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
  INSERT INTO notes_fts(rowid, title, body, tags)
  VALUES (new.id, new.title, new.body, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, title, body, tags)
  VALUES('delete', old.id, old.title, old.body, old.tags);
  INSERT INTO notes_fts(rowid, title, body, tags)
  VALUES (new.id, new.title, new.body, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, title, body, tags)
  VALUES('delete', old.id, old.title, old.body, old.tags);
END;

-- Jobs & Rules (embedded automation)
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', -- pending|running|done|failed
  not_before TEXT,                         -- schedule time (UTC)
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  payload TEXT NOT NULL DEFAULT '{}',      -- JSON
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  taken_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_time ON jobs(status, not_before);

CREATE TABLE IF NOT EXISTS job_logs (
  id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL,
  ts TEXT NOT NULL DEFAULT (datetime('now')),
  level TEXT NOT NULL DEFAULT 'info',
  message TEXT NOT NULL,
  FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

-- Optional: simple rules registry for future expansion
CREATE TABLE IF NOT EXISTS rules (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  definition TEXT NOT NULL DEFAULT '{}' -- JSON (conditions, actions)
);

-- housekeeping trigger
CREATE TRIGGER IF NOT EXISTS jobs_touch AFTER UPDATE ON jobs BEGIN
  UPDATE jobs SET updated_at = datetime('now') WHERE id = new.id;
END;
