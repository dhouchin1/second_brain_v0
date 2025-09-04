-- Search History & Saved Searches Migration
-- Enhances search functionality with user search tracking and saved searches

-- Search history table
CREATE TABLE IF NOT EXISTS search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    query TEXT NOT NULL,
    search_mode TEXT DEFAULT 'hybrid' CHECK (search_mode IN ('keyword', 'semantic', 'hybrid')),
    results_count INTEGER DEFAULT 0,
    response_time_ms INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Saved searches table  
CREATE TABLE IF NOT EXISTS saved_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    query TEXT NOT NULL,
    search_mode TEXT DEFAULT 'hybrid' CHECK (search_mode IN ('keyword', 'semantic', 'hybrid')),
    filters TEXT DEFAULT '{}', -- JSON for additional filters
    is_favorite BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, name)
);

-- Search analytics table for insights
CREATE TABLE IF NOT EXISTS search_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date DATE NOT NULL,
    total_searches INTEGER DEFAULT 0,
    avg_response_time_ms INTEGER DEFAULT 0,
    most_common_query TEXT,
    search_mode_breakdown TEXT DEFAULT '{}', -- JSON: {"keyword": 5, "semantic": 3, "hybrid": 10}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, date)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_search_history_user_created ON search_history(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_search_history_query ON search_history(query);
CREATE INDEX IF NOT EXISTS idx_saved_searches_user ON saved_searches(user_id, is_favorite DESC, last_used_at DESC);
CREATE INDEX IF NOT EXISTS idx_search_analytics_user_date ON search_analytics(user_id, date DESC);

-- Triggers to auto-update timestamps
CREATE TRIGGER IF NOT EXISTS update_saved_searches_timestamp 
    AFTER UPDATE ON saved_searches
BEGIN
    UPDATE saved_searches 
    SET updated_at = CURRENT_TIMESTAMP 
    WHERE id = NEW.id;
END;