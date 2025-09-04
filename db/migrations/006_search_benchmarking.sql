-- Search Benchmarking Migration
-- Tables for storing benchmark results, baselines, and analytics

-- Benchmark suites table - stores overall benchmark run information
CREATE TABLE IF NOT EXISTS benchmark_suites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suite_id TEXT UNIQUE NOT NULL,
    timestamp TEXT NOT NULL,
    total_queries INTEGER NOT NULL,
    successful_queries INTEGER NOT NULL,
    failed_queries INTEGER NOT NULL,
    avg_execution_time REAL NOT NULL,
    total_execution_time REAL NOT NULL,
    quality_summary TEXT NOT NULL,  -- JSON with quality metrics summary
    category_performance TEXT NOT NULL,  -- JSON with per-category performance
    regression_alerts TEXT NOT NULL,  -- JSON with regression alerts
    baseline_comparison TEXT,  -- JSON with baseline comparison (optional)
    notes TEXT,  -- Optional notes about this benchmark run
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Individual benchmark results table - detailed results for each query
CREATE TABLE IF NOT EXISTS benchmark_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suite_id TEXT NOT NULL,
    query_id TEXT NOT NULL,
    query TEXT NOT NULL,
    search_mode TEXT NOT NULL,
    result_limit INTEGER NOT NULL,
    execution_time REAL NOT NULL,
    result_count INTEGER NOT NULL,
    results TEXT NOT NULL,  -- JSON with full search results
    quality_scores TEXT NOT NULL,  -- JSON with calculated quality metrics
    expected_vs_actual TEXT NOT NULL,  -- JSON with expectation analysis
    status TEXT NOT NULL,  -- running, completed, failed, timeout
    error_message TEXT,
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(suite_id) REFERENCES benchmark_suites(suite_id)
);

-- Performance baselines table - established performance baselines for queries
CREATE TABLE IF NOT EXISTS benchmark_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id TEXT NOT NULL,
    search_mode TEXT NOT NULL,
    baseline_execution_time REAL NOT NULL,
    baseline_quality_score REAL NOT NULL,
    baseline_result_count INTEGER NOT NULL,
    established_at TEXT NOT NULL,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(query_id, search_mode)
);

-- Search analytics table - tracks search performance over time
CREATE TABLE IF NOT EXISTS search_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    search_mode TEXT NOT NULL,
    query_hash TEXT NOT NULL,  -- Hash of query for privacy
    execution_time REAL NOT NULL,
    result_count INTEGER NOT NULL,
    user_id INTEGER,
    quality_score REAL,
    cache_hit BOOLEAN DEFAULT FALSE,
    error_occurred BOOLEAN DEFAULT FALSE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Query performance trends - aggregated performance data
CREATE TABLE IF NOT EXISTS query_performance_trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,  -- YYYY-MM-DD format
    search_mode TEXT NOT NULL,
    total_queries INTEGER NOT NULL,
    avg_execution_time REAL NOT NULL,
    avg_result_count REAL NOT NULL,
    avg_quality_score REAL,
    error_rate REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, search_mode)
);

-- A/B testing experiments table
CREATE TABLE IF NOT EXISTS ab_test_experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    control_config TEXT NOT NULL,  -- JSON with control configuration
    variant_config TEXT NOT NULL,  -- JSON with variant configuration
    start_date TEXT NOT NULL,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',  -- active, completed, cancelled
    sample_size INTEGER,
    significance_level REAL DEFAULT 0.05,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- A/B test results table
CREATE TABLE IF NOT EXISTS ab_test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL,
    variant TEXT NOT NULL,  -- 'control' or 'variant'
    query_id TEXT NOT NULL,
    execution_time REAL NOT NULL,
    quality_score REAL,
    result_count INTEGER NOT NULL,
    user_satisfaction REAL,  -- Optional user satisfaction score
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(experiment_id) REFERENCES ab_test_experiments(experiment_id)
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_benchmark_suites_timestamp ON benchmark_suites(timestamp);
CREATE INDEX IF NOT EXISTS idx_benchmark_results_suite_id ON benchmark_results(suite_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_results_query_id ON benchmark_results(query_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_results_timestamp ON benchmark_results(timestamp);
CREATE INDEX IF NOT EXISTS idx_benchmark_baselines_query_mode ON benchmark_baselines(query_id, search_mode);
CREATE INDEX IF NOT EXISTS idx_search_analytics_timestamp ON search_analytics(timestamp);
CREATE INDEX IF NOT EXISTS idx_search_analytics_mode ON search_analytics(search_mode);
CREATE INDEX IF NOT EXISTS idx_query_performance_trends_date ON query_performance_trends(date);
CREATE INDEX IF NOT EXISTS idx_ab_test_results_experiment ON ab_test_results(experiment_id);
CREATE INDEX IF NOT EXISTS idx_ab_test_results_timestamp ON ab_test_results(timestamp);

-- Views for common queries
CREATE VIEW IF NOT EXISTS benchmark_summary AS
SELECT 
    suite_id,
    timestamp,
    total_queries,
    successful_queries,
    failed_queries,
    ROUND(avg_execution_time * 1000, 2) as avg_execution_time_ms,
    ROUND(total_execution_time, 2) as total_execution_time_s,
    ROUND((successful_queries * 100.0) / total_queries, 1) as success_rate_percent,
    json_extract(quality_summary, '$.relevance_score_avg') as avg_relevance_score,
    json_array_length(regression_alerts) as regression_count
FROM benchmark_suites
ORDER BY timestamp DESC;

CREATE VIEW IF NOT EXISTS recent_search_performance AS
SELECT 
    date,
    search_mode,
    total_queries,
    ROUND(avg_execution_time * 1000, 2) as avg_execution_time_ms,
    ROUND(avg_result_count, 1) as avg_result_count,
    ROUND(avg_quality_score, 3) as avg_quality_score,
    ROUND(error_rate * 100, 1) as error_rate_percent
FROM query_performance_trends 
WHERE date >= date('now', '-30 days')
ORDER BY date DESC, search_mode;

-- Trigger to automatically update performance trends
CREATE TRIGGER IF NOT EXISTS update_performance_trends 
AFTER INSERT ON search_analytics
BEGIN
    INSERT OR REPLACE INTO query_performance_trends (
        date, search_mode, total_queries, avg_execution_time, 
        avg_result_count, avg_quality_score, error_rate
    )
    SELECT 
        date(NEW.timestamp) as date,
        NEW.search_mode,
        COUNT(*) as total_queries,
        AVG(execution_time) as avg_execution_time,
        AVG(result_count) as avg_result_count,
        AVG(quality_score) as avg_quality_score,
        AVG(CASE WHEN error_occurred THEN 1.0 ELSE 0.0 END) as error_rate
    FROM search_analytics
    WHERE date(timestamp) = date(NEW.timestamp) 
    AND search_mode = NEW.search_mode;
END;