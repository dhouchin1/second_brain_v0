-- Migration 006: Auto-seeding tracking
-- Track auto-seeding attempts and status for new instances

CREATE TABLE IF NOT EXISTS auto_seeding_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    success BOOLEAN NOT NULL,
    message TEXT,
    namespace TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    config TEXT,
    notes_created INTEGER DEFAULT 0,
    files_created INTEGER DEFAULT 0,
    embeddings_created INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_auto_seeding_user_timestamp 
ON auto_seeding_log(user_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_auto_seeding_timestamp 
ON auto_seeding_log(timestamp);

-- Add auto-seeding configuration to system settings if we had such a table
-- For now, configuration will be handled via environment variables