-- GitHub/GitLab Integration Migration
-- Adds support for external content tracking and metadata

-- Add external tracking columns to notes table
ALTER TABLE notes ADD COLUMN external_id TEXT;
ALTER TABLE notes ADD COLUMN external_url TEXT;
ALTER TABLE notes ADD COLUMN metadata TEXT DEFAULT '{}';

-- Create indexes for external content lookup
CREATE INDEX IF NOT EXISTS idx_notes_external_id ON notes(external_id);
CREATE INDEX IF NOT EXISTS idx_notes_external_url ON notes(external_url);

-- Create integration sync tracking table
CREATE TABLE IF NOT EXISTS integration_sync (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    platform TEXT NOT NULL, -- github, gitlab
    sync_type TEXT NOT NULL, -- repository, user_repos, starred, gists
    target TEXT NOT NULL, -- repository URL, username, etc.
    last_sync_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    next_sync_at TIMESTAMP,
    sync_status TEXT DEFAULT 'pending', -- pending, success, error
    error_message TEXT,
    items_synced INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Create integration configuration table
CREATE TABLE IF NOT EXISTS integration_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    platform TEXT NOT NULL, -- github, gitlab
    config_key TEXT NOT NULL, -- token, instance_url
    config_value TEXT NOT NULL, -- encrypted values in production
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, platform, config_key)
);

-- Create indexes for integration tables
CREATE INDEX IF NOT EXISTS idx_integration_sync_user_platform ON integration_sync(user_id, platform);
CREATE INDEX IF NOT EXISTS idx_integration_sync_status ON integration_sync(sync_status, next_sync_at);
CREATE INDEX IF NOT EXISTS idx_integration_config_user ON integration_config(user_id, platform);

-- Create trigger to update integration_config timestamp
CREATE TRIGGER IF NOT EXISTS update_integration_config_timestamp 
    AFTER UPDATE ON integration_config
BEGIN
    UPDATE integration_config 
    SET updated_at = CURRENT_TIMESTAMP 
    WHERE id = NEW.id;
END;