"""
Search Benchmarking Router

FastAPI router for search benchmarking endpoints, providing API access
to benchmark execution, results analysis, and performance monitoring.
"""

import json
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field

from services.search_benchmarking_service import SearchBenchmarkingService, BenchmarkStatus

# Global service instances and functions (initialized by app.py)
benchmarking_service: Optional[SearchBenchmarkingService] = None
get_conn = None

# Request/Response Models
class BenchmarkRequest(BaseModel):
    """Request model for benchmark execution"""
    suite_id: Optional[str] = Field(None, description="Custom suite ID")
    categories: Optional[List[str]] = Field(None, description="Specific categories to test")
    search_modes: Optional[List[str]] = Field(None, description="Search modes to test")
    save_results: bool = Field(True, description="Whether to save results to database")
    establish_baseline: bool = Field(False, description="Whether to establish baseline from results")


class QuickBenchmarkRequest(BaseModel):
    """Request model for quick benchmark of specific queries"""
    queries: List[str] = Field(..., description="List of queries to benchmark")
    search_mode: str = Field("hybrid", description="Search mode to use")
    result_limit: int = Field(10, description="Number of results to fetch")


class BaselineRequest(BaseModel):
    """Request model for establishing baselines"""
    suite_id: str = Field(..., description="Suite ID to use for baseline")
    notes: Optional[str] = Field("API baseline establishment", description="Notes about baseline")


class ABTestRequest(BaseModel):
    """Request model for A/B testing"""
    experiment_name: str = Field(..., description="Name of the experiment")
    description: Optional[str] = Field(None, description="Description of the experiment")
    control_config: Dict[str, Any] = Field(..., description="Control configuration")
    variant_config: Dict[str, Any] = Field(..., description="Variant configuration")
    sample_size: Optional[int] = Field(100, description="Target sample size")
    duration_days: int = Field(7, description="Experiment duration in days")


class BenchmarkSummaryResponse(BaseModel):
    """Response model for benchmark summary"""
    suite_id: str
    timestamp: str
    total_queries: int
    successful_queries: int
    failed_queries: int
    success_rate: float
    avg_execution_time_ms: float
    regression_count: int
    status: str


class PerformanceTrendResponse(BaseModel):
    """Response model for performance trends"""
    date: str
    search_mode: str
    total_queries: int
    avg_execution_time_ms: float
    avg_result_count: float
    avg_quality_score: Optional[float]
    error_rate_percent: float


def init_search_benchmarking_router(get_conn_func):
    """Initialize Search Benchmarking router with dependencies"""
    global benchmarking_service, get_conn
    get_conn = get_conn_func
    benchmarking_service = SearchBenchmarkingService(get_conn_func)


# Create router
router = APIRouter(prefix="/api/benchmarking", tags=["Search Benchmarking"])


@router.post("/run-benchmark")
async def run_benchmark(
    request: BenchmarkRequest,
    background_tasks: BackgroundTasks
):
    """
    Run a full benchmark suite
    
    This endpoint runs benchmarks against golden queries and returns
    comprehensive performance and quality metrics.
    """
    try:
        # Run benchmark in background for long-running suites
        if not request.categories or len(request.categories) > 2:
            suite_id = request.suite_id or f"bench_api_{int(datetime.now().timestamp())}"
            
            # Start benchmark in background
            background_tasks.add_task(
                _run_benchmark_background,
                benchmarking_service,
                suite_id,
                request.categories,
                request.search_modes,
                request.save_results,
                request.establish_baseline
            )
            
            return {
                "status": "started",
                "suite_id": suite_id,
                "message": "Benchmark suite started in background",
                "estimated_completion": datetime.now() + timedelta(minutes=5)
            }
        else:
            # Run smaller benchmark synchronously
            suite = await benchmarking_service.run_full_benchmark_suite(
                suite_id=request.suite_id,
                categories=request.categories,
                search_modes=request.search_modes,
                save_results=request.save_results
            )
            
            # Establish baseline if requested
            if request.establish_baseline:
                await benchmarking_service.establish_baseline(suite.suite_id)
            
            return {
                "status": "completed",
                "suite": {
                    "suite_id": suite.suite_id,
                    "timestamp": suite.timestamp,
                    "total_queries": suite.total_queries,
                    "successful_queries": suite.successful_queries,
                    "failed_queries": suite.failed_queries,
                    "avg_execution_time": suite.avg_execution_time,
                    "quality_summary": suite.quality_summary,
                    "regression_alerts": suite.regression_alerts
                }
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Benchmark failed: {str(e)}")


@router.post("/quick-benchmark")
async def quick_benchmark(
    request: QuickBenchmarkRequest
):
    """
    Run a quick benchmark on specific queries
    
    Useful for testing individual queries or small sets during development.
    """
    try:
        results = []
        
        for query in request.queries:
            # Create a simple query spec
            query_spec = {
                "id": f"quick_{hash(query)}",
                "query": query,
                "min_results": 0,
                "quality_threshold": 0.5,
                "expected_result_types": ["note"],
                "context": {"use_unified_search": True, "user_id": 1}
            }
            
            result = await benchmarking_service._run_single_benchmark(
                query_spec, request.search_mode, request.result_limit, 5000
            )
            
            results.append({
                "query": query,
                "execution_time_ms": result.execution_time * 1000,
                "result_count": result.result_count,
                "quality_scores": result.quality_scores,
                "status": result.status.value
            })
        
        return {
            "results": results,
            "summary": {
                "total_queries": len(results),
                "avg_execution_time_ms": sum(r["execution_time_ms"] for r in results) / len(results),
                "avg_result_count": sum(r["result_count"] for r in results) / len(results)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quick benchmark failed: {str(e)}")


@router.get("/suites", response_model=List[BenchmarkSummaryResponse])
async def get_benchmark_suites(
    limit: int = Query(10, description="Number of suites to return"),
):
    """Get recent benchmark suites summary"""
    try:
        history = await benchmarking_service.get_benchmark_history(limit=limit)
        
        summaries = []
        for suite_data in history:
            quality_summary = json.loads(suite_data.get("quality_summary", "{}"))
            regression_alerts = json.loads(suite_data.get("regression_alerts", "[]"))
            
            summary = BenchmarkSummaryResponse(
                suite_id=suite_data["suite_id"],
                timestamp=suite_data["timestamp"],
                total_queries=suite_data["total_queries"],
                successful_queries=suite_data["successful_queries"],
                failed_queries=suite_data["failed_queries"],
                success_rate=suite_data["successful_queries"] / suite_data["total_queries"] if suite_data["total_queries"] > 0 else 0,
                avg_execution_time_ms=suite_data["avg_execution_time"] * 1000,
                regression_count=len(regression_alerts),
                status="completed" if suite_data["successful_queries"] > 0 else "failed"
            )
            summaries.append(summary)
        
        return summaries
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get suites: {str(e)}")


@router.get("/suite/{suite_id}")
async def get_benchmark_suite(
    suite_id: str,
):
    """Get detailed benchmark suite results"""
    try:
        report = await benchmarking_service.generate_benchmark_report(suite_id)
        
        if "error" in report:
            raise HTTPException(status_code=404, detail=report["error"])
        
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get suite: {str(e)}")


@router.get("/performance-trends", response_model=List[PerformanceTrendResponse])
async def get_performance_trends(
    days: int = Query(30, description="Number of days to include"),
    search_mode: Optional[str] = Query(None, description="Filter by search mode"),
):
    """Get search performance trends over time"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # Build query
        query = """
            SELECT date, search_mode, total_queries, 
                   ROUND(avg_execution_time * 1000, 2) as avg_execution_time_ms,
                   ROUND(avg_result_count, 1) as avg_result_count,
                   ROUND(avg_quality_score, 3) as avg_quality_score,
                   ROUND(error_rate * 100, 1) as error_rate_percent
            FROM query_performance_trends 
            WHERE date >= date('now', '-' || ? || ' days')
        """
        params = [days]
        
        if search_mode:
            query += " AND search_mode = ?"
            params.append(search_mode)
        
        query += " ORDER BY date DESC, search_mode"
        
        trends = c.execute(query, params).fetchall()
        conn.close()
        
        return [
            PerformanceTrendResponse(
                date=trend["date"],
                search_mode=trend["search_mode"],
                total_queries=trend["total_queries"],
                avg_execution_time_ms=trend["avg_execution_time_ms"],
                avg_result_count=trend["avg_result_count"],
                avg_quality_score=trend["avg_quality_score"],
                error_rate_percent=trend["error_rate_percent"]
            )
            for trend in trends
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trends: {str(e)}")


@router.post("/baseline")
async def establish_baseline(
    request: BaselineRequest,
):
    """Establish performance baseline from a benchmark suite"""
    try:
        success = await benchmarking_service.establish_baseline(request.suite_id, request.notes)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to establish baseline")
        
        return {
            "status": "success",
            "message": f"Baseline established from suite {request.suite_id}",
            "suite_id": request.suite_id,
            "notes": request.notes
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to establish baseline: {str(e)}")


@router.get("/baselines")
async def get_baselines(
):
    """Get current performance baselines"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        baselines = c.execute("""
            SELECT query_id, search_mode, baseline_execution_time,
                   baseline_quality_score, baseline_result_count,
                   established_at, notes
            FROM benchmark_baselines
            ORDER BY established_at DESC
        """).fetchall()
        
        conn.close()
        
        return {
            "baselines": [dict(baseline) for baseline in baselines],
            "total_count": len(baselines)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get baselines: {str(e)}")


@router.post("/ab-test")
async def create_ab_test(
    request: ABTestRequest,
):
    """Create a new A/B testing experiment"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        experiment_id = f"exp_{int(datetime.now().timestamp())}"
        end_date = datetime.now() + timedelta(days=request.duration_days)
        
        c.execute("""
            INSERT INTO ab_test_experiments
            (experiment_id, name, description, control_config, variant_config,
             start_date, end_date, sample_size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            experiment_id,
            request.experiment_name,
            request.description,
            json.dumps(request.control_config),
            json.dumps(request.variant_config),
            datetime.now().isoformat(),
            end_date.isoformat(),
            request.sample_size
        ))
        
        conn.commit()
        conn.close()
        
        return {
            "experiment_id": experiment_id,
            "status": "created",
            "start_date": datetime.now().isoformat(),
            "end_date": end_date.isoformat(),
            "message": "A/B test experiment created successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create A/B test: {str(e)}")


@router.get("/ab-tests")
async def get_ab_tests(
):
    """Get active A/B testing experiments"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        experiments = c.execute("""
            SELECT * FROM ab_test_experiments
            WHERE status = 'active'
            ORDER BY created_at DESC
        """).fetchall()
        
        conn.close()
        
        return {
            "experiments": [dict(exp) for exp in experiments],
            "total_count": len(experiments)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get A/B tests: {str(e)}")


@router.get("/analytics/dashboard")
async def get_analytics_dashboard(
):
    """Get comprehensive analytics dashboard data"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # Recent benchmark summary
        recent_benchmark = c.execute("""
            SELECT * FROM benchmark_summary LIMIT 1
        """).fetchone()
        
        # Performance trends (last 7 days)
        recent_trends = c.execute("""
            SELECT * FROM recent_search_performance
            WHERE date >= date('now', '-7 days')
            ORDER BY date DESC
        """).fetchall()
        
        # Active baselines count
        baseline_count = c.execute("""
            SELECT COUNT(*) as count FROM benchmark_baselines
        """).fetchone()
        
        # Recent regression alerts
        recent_regressions = c.execute("""
            SELECT suite_id, regression_alerts FROM benchmark_suites
            WHERE json_array_length(regression_alerts) > 0
            ORDER BY timestamp DESC
            LIMIT 5
        """).fetchall()
        
        conn.close()
        
        return {
            "recent_benchmark": dict(recent_benchmark) if recent_benchmark else None,
            "performance_trends": [dict(trend) for trend in recent_trends],
            "baseline_count": baseline_count["count"] if baseline_count else 0,
            "recent_regressions": [
                {
                    "suite_id": reg["suite_id"],
                    "alerts": json.loads(reg["regression_alerts"])
                }
                for reg in recent_regressions
            ],
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard: {str(e)}")


# Background task functions
async def _run_benchmark_background(
    service: SearchBenchmarkingService,
    suite_id: str,
    categories: Optional[List[str]],
    search_modes: Optional[List[str]],
    save_results: bool,
    establish_baseline: bool
):
    """Run benchmark suite in background"""
    try:
        suite = await service.run_full_benchmark_suite(
            suite_id=suite_id,
            categories=categories,
            search_modes=search_modes,
            save_results=save_results
        )
        
        if establish_baseline:
            await service.establish_baseline(suite.suite_id)
        
        print(f"Background benchmark {suite_id} completed successfully")
        
    except Exception as e:
        print(f"Background benchmark {suite_id} failed: {e}")


# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check for benchmarking service"""
    return {
        "status": "healthy",
        "service": "search_benchmarking",
        "timestamp": datetime.now().isoformat()
    }


print("[Search Benchmarking Router] Loaded successfully")