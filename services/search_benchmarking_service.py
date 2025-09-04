"""
Search Benchmarking Service

Provides comprehensive benchmarking capabilities for the Second Brain search system,
including golden query testing, performance monitoring, and regression detection.
"""

import json
import time
import statistics
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum

from services.search_adapter import SearchService
from services.unified_search_service import UnifiedSearchService


class BenchmarkStatus(str, Enum):
    """Status of benchmark runs"""
    RUNNING = "running"
    COMPLETED = "completed" 
    FAILED = "failed"
    TIMEOUT = "timeout"


class QualityMetric(str, Enum):
    """Quality metrics for search evaluation"""
    RELEVANCE_SCORE = "relevance_score"
    RESULT_COUNT = "result_count"
    SEARCH_TIME = "search_time"
    RESULT_DIVERSITY = "result_diversity"
    INTENT_ACCURACY = "intent_accuracy"
    RECALL = "recall"
    PRECISION = "precision"


@dataclass
class BenchmarkResult:
    """Individual benchmark query result"""
    query_id: str
    query: str
    search_mode: str
    result_limit: int
    execution_time: float
    result_count: int
    results: List[Dict[str, Any]]
    quality_scores: Dict[str, float]
    expected_vs_actual: Dict[str, Any]
    status: BenchmarkStatus
    error_message: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class BenchmarkSuite:
    """Complete benchmark suite results"""
    suite_id: str
    timestamp: str
    total_queries: int
    successful_queries: int
    failed_queries: int
    avg_execution_time: float
    total_execution_time: float
    quality_summary: Dict[str, float]
    category_performance: Dict[str, Dict[str, float]]
    regression_alerts: List[Dict[str, Any]]
    results: List[BenchmarkResult]
    baseline_comparison: Optional[Dict[str, Any]] = None


class SearchBenchmarkingService:
    """
    Service for comprehensive search system benchmarking
    """
    
    def __init__(self, get_conn_func, db_path: str = None, vec_ext_path: str = None):
        from config import settings
        self.get_conn = get_conn_func
        
        # Use settings defaults if not provided
        if not db_path:
            db_path = str(settings.db_path)
        if not vec_ext_path:
            # Try to get from environment or use None if not available
            import os
            vec_ext_path = os.environ.get('SQLITE_VEC_PATH')
        
        self.search_service = SearchService(db_path=db_path, vec_ext_path=vec_ext_path)
        self.unified_search_service = UnifiedSearchService(get_conn_func, db_path, vec_ext_path)
        
        # Load golden queries
        self.golden_queries_path = Path("golden_queries.json")
        self.golden_queries = self._load_golden_queries()
        
        # Benchmark history for comparison
        self._benchmark_history = []
        self._setup_benchmark_tables()
    
    def _load_golden_queries(self) -> Dict[str, Any]:
        """Load golden queries from JSON file"""
        try:
            if self.golden_queries_path.exists():
                return json.loads(self.golden_queries_path.read_text())
            else:
                print(f"Warning: Golden queries file not found at {self.golden_queries_path}")
                return {"scenarios": [], "benchmarking_config": {}}
        except Exception as e:
            print(f"Error loading golden queries: {e}")
            return {"scenarios": [], "benchmarking_config": {}}
    
    def _setup_benchmark_tables(self):
        """Setup database tables for benchmark storage"""
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            # Benchmark suites table
            c.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_suites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    suite_id TEXT UNIQUE NOT NULL,
                    timestamp TEXT NOT NULL,
                    total_queries INTEGER NOT NULL,
                    successful_queries INTEGER NOT NULL,
                    failed_queries INTEGER NOT NULL,
                    avg_execution_time REAL NOT NULL,
                    total_execution_time REAL NOT NULL,
                    quality_summary TEXT NOT NULL,  -- JSON
                    category_performance TEXT NOT NULL,  -- JSON
                    regression_alerts TEXT NOT NULL,  -- JSON
                    baseline_comparison TEXT,  -- JSON
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Individual benchmark results table
            c.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    suite_id TEXT NOT NULL,
                    query_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    search_mode TEXT NOT NULL,
                    result_limit INTEGER NOT NULL,
                    execution_time REAL NOT NULL,
                    result_count INTEGER NOT NULL,
                    results TEXT NOT NULL,  -- JSON
                    quality_scores TEXT NOT NULL,  -- JSON
                    expected_vs_actual TEXT NOT NULL,  -- JSON
                    status TEXT NOT NULL,
                    error_message TEXT,
                    timestamp TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(suite_id) REFERENCES benchmark_suites(suite_id)
                )
            """)
            
            # Performance baselines table
            c.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_baselines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id TEXT NOT NULL,
                    search_mode TEXT NOT NULL,
                    baseline_execution_time REAL NOT NULL,
                    baseline_quality_score REAL NOT NULL,
                    baseline_result_count INTEGER NOT NULL,
                    established_at TEXT NOT NULL,
                    notes TEXT,
                    UNIQUE(query_id, search_mode)
                )
            """)
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error setting up benchmark tables: {e}")
    
    async def run_full_benchmark_suite(
        self, 
        suite_id: Optional[str] = None,
        categories: Optional[List[str]] = None,
        search_modes: Optional[List[str]] = None,
        save_results: bool = True
    ) -> BenchmarkSuite:
        """
        Run complete benchmark suite against golden queries
        
        Args:
            suite_id: Unique identifier for this benchmark run
            categories: Specific categories to test (None for all)
            search_modes: Search modes to test (None for all configured)
            save_results: Whether to save results to database
            
        Returns:
            Complete benchmark suite results
        """
        if suite_id is None:
            suite_id = f"bench_{int(time.time())}"
            
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Get configuration
        config = self.golden_queries.get("benchmarking_config", {})
        test_search_modes = search_modes or config.get("search_modes", ["hybrid"])
        result_limits = config.get("result_limits", [20])
        timeout_ms = config.get("timeout_ms", 5000)
        
        # Collect all queries to test
        all_queries = []
        scenarios = self.golden_queries.get("scenarios", [])
        
        for scenario in scenarios:
            if categories and scenario.get("category") not in categories:
                continue
                
            for query_spec in scenario.get("queries", []):
                all_queries.append((scenario.get("category"), query_spec))
        
        print(f"Running benchmark suite '{suite_id}' with {len(all_queries)} queries")
        
        # Run all benchmark combinations
        all_results = []
        total_start_time = time.time()
        
        for category, query_spec in all_queries:
            for search_mode in test_search_modes:
                for result_limit in result_limits:
                    try:
                        result = await self._run_single_benchmark(
                            query_spec, search_mode, result_limit, timeout_ms
                        )
                        all_results.append(result)
                        
                    except Exception as e:
                        # Create failed result
                        failed_result = BenchmarkResult(
                            query_id=query_spec.get("id", "unknown"),
                            query=query_spec.get("query", ""),
                            search_mode=search_mode,
                            result_limit=result_limit,
                            execution_time=0.0,
                            result_count=0,
                            results=[],
                            quality_scores={},
                            expected_vs_actual={},
                            status=BenchmarkStatus.FAILED,
                            error_message=str(e)
                        )
                        all_results.append(failed_result)
        
        total_execution_time = time.time() - total_start_time
        
        # Analyze results
        successful_results = [r for r in all_results if r.status == BenchmarkStatus.COMPLETED]
        failed_results = [r for r in all_results if r.status != BenchmarkStatus.COMPLETED]
        
        avg_execution_time = (
            statistics.mean([r.execution_time for r in successful_results])
            if successful_results else 0.0
        )
        
        # Calculate quality metrics
        quality_summary = await self._calculate_quality_summary(successful_results)
        
        # Group results by category
        category_performance = await self._calculate_category_performance(
            all_results, scenarios
        )
        
        # Check for regressions
        regression_alerts = await self._check_for_regressions(all_results)
        
        # Create benchmark suite
        suite = BenchmarkSuite(
            suite_id=suite_id,
            timestamp=timestamp,
            total_queries=len(all_results),
            successful_queries=len(successful_results),
            failed_queries=len(failed_results),
            avg_execution_time=avg_execution_time,
            total_execution_time=total_execution_time,
            quality_summary=quality_summary,
            category_performance=category_performance,
            regression_alerts=regression_alerts,
            results=all_results
        )
        
        # Add baseline comparison if available
        suite.baseline_comparison = await self._compare_with_baseline(suite)
        
        # Save results if requested
        if save_results:
            await self._save_benchmark_suite(suite)
        
        print(f"Benchmark suite completed: {len(successful_results)}/{len(all_results)} queries successful")
        
        return suite
    
    async def _run_single_benchmark(
        self, 
        query_spec: Dict[str, Any], 
        search_mode: str, 
        result_limit: int,
        timeout_ms: int
    ) -> BenchmarkResult:
        """Run a single benchmark query"""
        query_id = query_spec.get("id", "unknown")
        query_text = query_spec.get("query", "")
        context = query_spec.get("context", {})
        
        start_time = time.time()
        
        try:
            # Run the search with timeout
            if context.get("use_unified_search", True):
                search_results = await self.unified_search_service.unified_search(
                    query=query_text,
                    user_id=context.get("user_id", 1),
                    search_mode=search_mode,
                    limit=result_limit,
                    include_templates=True,
                    context=context
                )
                results = search_results.get("results", [])
                execution_time = search_results.get("analytics", {}).get("search_time", 0)
            else:
                # Use basic search service
                raw_results = self.search_service.search(query_text, mode=search_mode, k=result_limit)
                results = [dict(row) for row in raw_results]
                execution_time = time.time() - start_time
            
            # Check timeout
            if execution_time * 1000 > timeout_ms:
                return BenchmarkResult(
                    query_id=query_id,
                    query=query_text,
                    search_mode=search_mode,
                    result_limit=result_limit,
                    execution_time=execution_time,
                    result_count=len(results),
                    results=results,
                    quality_scores={},
                    expected_vs_actual={},
                    status=BenchmarkStatus.TIMEOUT
                )
            
            # Calculate quality scores
            quality_scores = await self._calculate_quality_scores(
                query_spec, results, execution_time
            )
            
            # Compare expected vs actual
            expected_vs_actual = await self._compare_expected_vs_actual(
                query_spec, results
            )
            
            return BenchmarkResult(
                query_id=query_id,
                query=query_text,
                search_mode=search_mode,
                result_limit=result_limit,
                execution_time=execution_time,
                result_count=len(results),
                results=results,
                quality_scores=quality_scores,
                expected_vs_actual=expected_vs_actual,
                status=BenchmarkStatus.COMPLETED
            )
            
        except Exception as e:
            return BenchmarkResult(
                query_id=query_id,
                query=query_text,
                search_mode=search_mode,
                result_limit=result_limit,
                execution_time=time.time() - start_time,
                result_count=0,
                results=[],
                quality_scores={},
                expected_vs_actual={},
                status=BenchmarkStatus.FAILED,
                error_message=str(e)
            )
    
    async def _calculate_quality_scores(
        self, 
        query_spec: Dict[str, Any], 
        results: List[Dict[str, Any]], 
        execution_time: float
    ) -> Dict[str, float]:
        """Calculate quality scores for a benchmark result"""
        scores = {}
        
        # Basic metrics
        scores[QualityMetric.RESULT_COUNT] = len(results)
        scores[QualityMetric.SEARCH_TIME] = execution_time
        
        # Relevance score (average of result scores)
        if results and any("relevance_score" in r for r in results):
            relevance_scores = [
                r.get("relevance_score", 0) for r in results 
                if "relevance_score" in r
            ]
            scores[QualityMetric.RELEVANCE_SCORE] = (
                statistics.mean(relevance_scores) if relevance_scores else 0.0
            )
        
        # Result diversity (count of unique result types)
        result_types = set(r.get("type", "unknown") for r in results)
        scores[QualityMetric.RESULT_DIVERSITY] = len(result_types)
        
        # Intent accuracy (match between expected and actual result types)
        expected_types = set(query_spec.get("expected_result_types", []))
        actual_types = set(r.get("type", "note") for r in results)
        
        if expected_types:
            intent_match = len(expected_types.intersection(actual_types)) / len(expected_types)
            scores[QualityMetric.INTENT_ACCURACY] = intent_match
        
        # Recall estimation (based on minimum expected results)
        min_results = query_spec.get("min_results", 0)
        if min_results > 0:
            scores[QualityMetric.RECALL] = min(1.0, len(results) / min_results)
        
        # Quality threshold check
        quality_threshold = query_spec.get("quality_threshold", 0.5)
        avg_quality = scores.get(QualityMetric.RELEVANCE_SCORE, 0)
        scores[QualityMetric.PRECISION] = 1.0 if avg_quality >= quality_threshold else avg_quality
        
        return scores
    
    async def _compare_expected_vs_actual(
        self, 
        query_spec: Dict[str, Any], 
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Compare expected query outcomes with actual results"""
        comparison = {
            "expected_min_results": query_spec.get("min_results", 0),
            "actual_result_count": len(results),
            "expected_result_types": query_spec.get("expected_result_types", []),
            "actual_result_types": list(set(r.get("type", "note") for r in results)),
            "quality_threshold": query_spec.get("quality_threshold", 0.5),
            "meets_quality_threshold": False,
            "performance_target_met": False
        }
        
        # Check quality threshold
        if results:
            avg_score = statistics.mean([
                r.get("relevance_score", 0) for r in results
                if "relevance_score" in r
            ]) if any("relevance_score" in r for r in results) else 0
            comparison["actual_avg_quality"] = avg_score
            comparison["meets_quality_threshold"] = avg_score >= comparison["quality_threshold"]
        
        # Check performance target
        perf_target = query_spec.get("performance_target", {})
        if perf_target:
            max_time_ms = perf_target.get("max_time_ms", float('inf'))
            # This would need execution time from calling context
            comparison["performance_target"] = perf_target
        
        return comparison
    
    async def _calculate_quality_summary(
        self, 
        results: List[BenchmarkResult]
    ) -> Dict[str, float]:
        """Calculate overall quality summary across all results"""
        if not results:
            return {}
        
        summary = {}
        
        # Aggregate metrics across all results
        for metric in QualityMetric:
            metric_values = []
            for result in results:
                if metric.value in result.quality_scores:
                    metric_values.append(result.quality_scores[metric.value])
            
            if metric_values:
                summary[f"{metric.value}_avg"] = statistics.mean(metric_values)
                summary[f"{metric.value}_min"] = min(metric_values)
                summary[f"{metric.value}_max"] = max(metric_values)
                summary[f"{metric.value}_std"] = statistics.stdev(metric_values) if len(metric_values) > 1 else 0
        
        # Success rate
        total_queries = len(results)
        successful_queries = len([r for r in results if r.status == BenchmarkStatus.COMPLETED])
        summary["success_rate"] = successful_queries / total_queries if total_queries > 0 else 0
        
        return summary
    
    async def _calculate_category_performance(
        self, 
        results: List[BenchmarkResult], 
        scenarios: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, float]]:
        """Calculate performance metrics by query category"""
        category_perf = {}
        
        # Map query IDs to categories
        query_to_category = {}
        for scenario in scenarios:
            category = scenario.get("category", "unknown")
            for query in scenario.get("queries", []):
                query_to_category[query.get("id")] = category
        
        # Group results by category
        by_category = {}
        for result in results:
            category = query_to_category.get(result.query_id, "unknown")
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(result)
        
        # Calculate metrics for each category
        for category, cat_results in by_category.items():
            successful_results = [r for r in cat_results if r.status == BenchmarkStatus.COMPLETED]
            
            if successful_results:
                category_perf[category] = {
                    "total_queries": len(cat_results),
                    "successful_queries": len(successful_results),
                    "success_rate": len(successful_results) / len(cat_results),
                    "avg_execution_time": statistics.mean([r.execution_time for r in successful_results]),
                    "avg_result_count": statistics.mean([r.result_count for r in successful_results])
                }
                
                # Add quality metrics if available
                if successful_results[0].quality_scores:
                    for metric, values in {}.items():
                        metric_values = [r.quality_scores.get(metric, 0) for r in successful_results]
                        if metric_values:
                            category_perf[category][f"avg_{metric}"] = statistics.mean(metric_values)
        
        return category_perf
    
    async def _check_for_regressions(
        self, 
        results: List[BenchmarkResult]
    ) -> List[Dict[str, Any]]:
        """Check for performance or quality regressions"""
        alerts = []
        
        config = self.golden_queries.get("benchmarking_config", {})
        thresholds = config.get("regression_thresholds", {})
        
        # Get baseline data from database
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            for result in results:
                if result.status != BenchmarkStatus.COMPLETED:
                    continue
                
                # Look up baseline for this query/mode combination
                baseline = c.execute(
                    """SELECT * FROM benchmark_baselines 
                       WHERE query_id = ? AND search_mode = ?""",
                    (result.query_id, result.search_mode)
                ).fetchone()
                
                if not baseline:
                    continue
                
                # Check for performance regression
                perf_threshold = thresholds.get("performance_degradation", 0.2)
                if result.execution_time > baseline["baseline_execution_time"] * (1 + perf_threshold):
                    alerts.append({
                        "type": "performance_regression",
                        "query_id": result.query_id,
                        "search_mode": result.search_mode,
                        "baseline_time": baseline["baseline_execution_time"],
                        "current_time": result.execution_time,
                        "degradation": (result.execution_time / baseline["baseline_execution_time"]) - 1,
                        "threshold": perf_threshold
                    })
                
                # Check for quality regression
                current_quality = result.quality_scores.get(QualityMetric.RELEVANCE_SCORE, 0)
                quality_threshold = thresholds.get("quality_degradation", 0.15)
                
                if current_quality < baseline["baseline_quality_score"] * (1 - quality_threshold):
                    alerts.append({
                        "type": "quality_regression",
                        "query_id": result.query_id,
                        "search_mode": result.search_mode,
                        "baseline_quality": baseline["baseline_quality_score"],
                        "current_quality": current_quality,
                        "degradation": 1 - (current_quality / baseline["baseline_quality_score"]),
                        "threshold": quality_threshold
                    })
            
            conn.close()
            
        except Exception as e:
            print(f"Error checking for regressions: {e}")
        
        return alerts
    
    async def _compare_with_baseline(
        self, 
        suite: BenchmarkSuite
    ) -> Optional[Dict[str, Any]]:
        """Compare current suite with established baseline"""
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            # Get most recent successful benchmark suite
            baseline_suite = c.execute(
                """SELECT * FROM benchmark_suites 
                   WHERE successful_queries > 0 
                   ORDER BY created_at DESC 
                   LIMIT 1 OFFSET 1"""  # Skip current suite
            ).fetchone()
            
            if not baseline_suite:
                return None
            
            baseline_quality = json.loads(baseline_suite["quality_summary"])
            current_quality = suite.quality_summary
            
            comparison = {
                "baseline_suite_id": baseline_suite["suite_id"],
                "baseline_timestamp": baseline_suite["timestamp"],
                "performance_delta": {},
                "quality_delta": {},
                "overall_change": "improved"  # improved, degraded, similar
            }
            
            # Compare key metrics
            perf_delta = (suite.avg_execution_time - baseline_suite["avg_execution_time"]) / baseline_suite["avg_execution_time"]
            comparison["performance_delta"] = {
                "execution_time_change": perf_delta,
                "baseline_avg_time": baseline_suite["avg_execution_time"],
                "current_avg_time": suite.avg_execution_time
            }
            
            # Compare quality metrics
            for metric in [QualityMetric.RELEVANCE_SCORE, QualityMetric.RECALL, QualityMetric.PRECISION]:
                baseline_key = f"{metric.value}_avg"
                if baseline_key in baseline_quality and baseline_key in current_quality:
                    delta = (current_quality[baseline_key] - baseline_quality[baseline_key]) / baseline_quality[baseline_key]
                    comparison["quality_delta"][metric.value] = {
                        "change": delta,
                        "baseline": baseline_quality[baseline_key],
                        "current": current_quality[baseline_key]
                    }
            
            # Determine overall change
            if len(suite.regression_alerts) > 0:
                comparison["overall_change"] = "degraded"
            elif perf_delta < -0.05 or any(
                q.get("change", 0) > 0.05 for q in comparison["quality_delta"].values()
            ):
                comparison["overall_change"] = "improved"
            else:
                comparison["overall_change"] = "similar"
            
            conn.close()
            return comparison
            
        except Exception as e:
            print(f"Error comparing with baseline: {e}")
            return None
    
    async def _save_benchmark_suite(self, suite: BenchmarkSuite):
        """Save benchmark suite to database"""
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            # Save suite summary
            c.execute("""
                INSERT OR REPLACE INTO benchmark_suites
                (suite_id, timestamp, total_queries, successful_queries, failed_queries,
                 avg_execution_time, total_execution_time, quality_summary, category_performance,
                 regression_alerts, baseline_comparison)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                suite.suite_id,
                suite.timestamp,
                suite.total_queries,
                suite.successful_queries,
                suite.failed_queries,
                suite.avg_execution_time,
                suite.total_execution_time,
                json.dumps(suite.quality_summary),
                json.dumps(suite.category_performance),
                json.dumps(suite.regression_alerts),
                json.dumps(suite.baseline_comparison) if suite.baseline_comparison else None
            ))
            
            # Save individual results
            for result in suite.results:
                c.execute("""
                    INSERT INTO benchmark_results
                    (suite_id, query_id, query, search_mode, result_limit, execution_time,
                     result_count, results, quality_scores, expected_vs_actual, status,
                     error_message, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    suite.suite_id,
                    result.query_id,
                    result.query,
                    result.search_mode,
                    result.result_limit,
                    result.execution_time,
                    result.result_count,
                    json.dumps(result.results),
                    json.dumps(result.quality_scores),
                    json.dumps(result.expected_vs_actual),
                    result.status.value,
                    result.error_message,
                    result.timestamp
                ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error saving benchmark suite: {e}")
    
    async def establish_baseline(
        self, 
        suite_id: str,
        notes: str = "Automated baseline establishment"
    ) -> bool:
        """Establish performance baselines from a benchmark suite"""
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            # Get results from the specified suite
            results = c.execute(
                """SELECT * FROM benchmark_results WHERE suite_id = ? AND status = ?""",
                (suite_id, BenchmarkStatus.COMPLETED.value)
            ).fetchall()
            
            for result in results:
                quality_scores = json.loads(result["quality_scores"])
                
                # Calculate baseline quality score (use relevance score as primary metric)
                baseline_quality = quality_scores.get(QualityMetric.RELEVANCE_SCORE, 0)
                
                # Insert or update baseline
                c.execute("""
                    INSERT OR REPLACE INTO benchmark_baselines
                    (query_id, search_mode, baseline_execution_time, baseline_quality_score,
                     baseline_result_count, established_at, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    result["query_id"],
                    result["search_mode"],
                    result["execution_time"],
                    baseline_quality,
                    result["result_count"],
                    datetime.now(timezone.utc).isoformat(),
                    notes
                ))
            
            conn.commit()
            conn.close()
            
            print(f"Established baselines for {len(results)} benchmark results from suite {suite_id}")
            return True
            
        except Exception as e:
            print(f"Error establishing baseline: {e}")
            return False
    
    async def get_benchmark_history(
        self, 
        limit: int = 10,
        query_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get benchmark suite history"""
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            if query_id:
                # Get history for specific query
                history = c.execute("""
                    SELECT br.*, bs.suite_id, bs.timestamp as suite_timestamp
                    FROM benchmark_results br
                    JOIN benchmark_suites bs ON br.suite_id = bs.suite_id
                    WHERE br.query_id = ?
                    ORDER BY bs.created_at DESC
                    LIMIT ?
                """, (query_id, limit)).fetchall()
            else:
                # Get suite history
                history = c.execute("""
                    SELECT * FROM benchmark_suites
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,)).fetchall()
            
            conn.close()
            return [dict(row) for row in history]
            
        except Exception as e:
            print(f"Error getting benchmark history: {e}")
            return []
    
    async def generate_benchmark_report(
        self, 
        suite_id: str,
        format: str = "json"
    ) -> Dict[str, Any]:
        """Generate comprehensive benchmark report"""
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            # Get suite information
            suite = c.execute(
                "SELECT * FROM benchmark_suites WHERE suite_id = ?",
                (suite_id,)
            ).fetchone()
            
            if not suite:
                return {"error": f"Suite {suite_id} not found"}
            
            # Get detailed results
            results = c.execute(
                "SELECT * FROM benchmark_results WHERE suite_id = ?",
                (suite_id,)
            ).fetchall()
            
            conn.close()
            
            report = {
                "suite_summary": dict(suite),
                "detailed_results": [dict(result) for result in results],
                "analysis": {
                    "top_performing_queries": [],
                    "slowest_queries": [],
                    "failing_queries": [],
                    "category_breakdown": json.loads(suite["category_performance"]),
                    "regression_summary": json.loads(suite["regression_alerts"]),
                    "recommendations": []
                },
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Analyze results
            successful_results = [r for r in results if r["status"] == BenchmarkStatus.COMPLETED.value]
            
            if successful_results:
                # Top performing queries (by quality score)
                sorted_by_quality = sorted(
                    successful_results, 
                    key=lambda r: json.loads(r["quality_scores"]).get("relevance_score", 0),
                    reverse=True
                )
                report["analysis"]["top_performing_queries"] = sorted_by_quality[:5]
                
                # Slowest queries
                sorted_by_time = sorted(successful_results, key=lambda r: r["execution_time"], reverse=True)
                report["analysis"]["slowest_queries"] = sorted_by_time[:5]
            
            # Failing queries
            failing_results = [r for r in results if r["status"] != BenchmarkStatus.COMPLETED.value]
            report["analysis"]["failing_queries"] = failing_results
            
            # Generate recommendations
            recommendations = []
            if len(failing_results) > 0:
                recommendations.append(f"Investigate {len(failing_results)} failing queries")
            
            if suite["avg_execution_time"] > 1.0:
                recommendations.append("Consider performance optimization - average query time exceeds 1 second")
            
            if len(json.loads(suite["regression_alerts"])) > 0:
                recommendations.append("Address performance or quality regressions")
            
            report["analysis"]["recommendations"] = recommendations
            
            return report
            
        except Exception as e:
            return {"error": f"Error generating report: {e}"}


print("[Search Benchmarking Service] Loaded successfully")