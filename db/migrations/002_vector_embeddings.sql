-- Vector embeddings storage for semantic search
-- Migration: 002_vector_embeddings.sql

-- Table to store vector embeddings for notes
CREATE TABLE IF NOT EXISTS note_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL,
    embedding_model TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    embedding BLOB NOT NULL,  -- Serialized numpy array or list of floats
    embedding_dim INTEGER NOT NULL DEFAULT 384,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE
);

-- Index for fast lookups by note_id
CREATE INDEX IF NOT EXISTS idx_embeddings_note_id ON note_embeddings(note_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_model ON note_embeddings(embedding_model);
CREATE INDEX IF NOT EXISTS idx_embeddings_updated ON note_embeddings(updated_at);

-- Table to track embedding generation jobs and status
CREATE TABLE IF NOT EXISTS embedding_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending|processing|completed|failed
    model_name TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    error_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_embedding_jobs_status ON embedding_jobs(status);
CREATE INDEX IF NOT EXISTS idx_embedding_jobs_note_id ON embedding_jobs(note_id);

-- Table to store semantic search analytics
CREATE TABLE IF NOT EXISTS semantic_search_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    query TEXT NOT NULL,
    query_embedding BLOB,  -- Store query embedding for future optimization
    results_count INTEGER DEFAULT 0,
    search_type TEXT DEFAULT 'semantic', -- semantic|hybrid|fts
    similarity_threshold REAL DEFAULT 0.1,
    execution_time_ms INTEGER,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_semantic_analytics_user ON semantic_search_analytics(user_id);
CREATE INDEX IF NOT EXISTS idx_semantic_analytics_type ON semantic_search_analytics(search_type);
CREATE INDEX IF NOT EXISTS idx_semantic_analytics_time ON semantic_search_analytics(timestamp);

-- Trigger to update embedding timestamps
CREATE TRIGGER IF NOT EXISTS note_embeddings_touch 
AFTER UPDATE ON note_embeddings BEGIN
    UPDATE note_embeddings SET updated_at = datetime('now') WHERE id = new.id;
END;

-- Trigger to update embedding job timestamps  
CREATE TRIGGER IF NOT EXISTS embedding_jobs_touch 
AFTER UPDATE ON embedding_jobs BEGIN
    UPDATE embedding_jobs SET updated_at = datetime('now') WHERE id = new.id;
END;

-- Trigger to create embedding jobs when notes are created/updated
CREATE TRIGGER IF NOT EXISTS notes_embedding_job_insert 
AFTER INSERT ON notes BEGIN
    INSERT INTO embedding_jobs (note_id, model_name)
    VALUES (new.id, 'all-MiniLM-L6-v2');
END;

CREATE TRIGGER IF NOT EXISTS notes_embedding_job_update 
AFTER UPDATE OF content, title, summary ON notes BEGIN
    INSERT INTO embedding_jobs (note_id, model_name)
    VALUES (new.id, 'all-MiniLM-L6-v2');
END;

-- View for easy access to notes with their embeddings
CREATE VIEW IF NOT EXISTS notes_with_embeddings AS
SELECT 
    n.*,
    ne.embedding_model,
    ne.embedding_dim,
    ne.created_at as embedding_created_at,
    ne.updated_at as embedding_updated_at,
    CASE 
        WHEN ne.id IS NOT NULL THEN 1 
        ELSE 0 
    END as has_embedding
FROM notes n
LEFT JOIN note_embeddings ne ON n.id = ne.note_id
WHERE ne.id = (
    SELECT MAX(id) FROM note_embeddings ne2 
    WHERE ne2.note_id = n.id
);

-- View for embedding job status
CREATE VIEW IF NOT EXISTS embedding_status AS
SELECT 
    n.id as note_id,
    n.title,
    n.updated_at as note_updated_at,
    ej.status as embedding_status,
    ej.attempts,
    ej.error_message,
    ej.created_at as job_created_at,
    ej.completed_at as job_completed_at,
    CASE 
        WHEN ne.id IS NOT NULL THEN 1 
        ELSE 0 
    END as has_current_embedding
FROM notes n
LEFT JOIN embedding_jobs ej ON n.id = ej.note_id
    AND ej.id = (SELECT MAX(id) FROM embedding_jobs ej2 WHERE ej2.note_id = n.id)
LEFT JOIN note_embeddings ne ON n.id = ne.note_id;