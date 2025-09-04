#!/usr/bin/env python3
"""
Test script for the search benchmarking system

This script validates that the benchmarking system works correctly
and can be used to test the golden queries and benchmarking service.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the project root to the path
sys.path.append(str(Path(__file__).parent))

from services.search_benchmarking_service import SearchBenchmarkingService
from automated_benchmarking import AutomatedBenchmarking
from config import get_connection


async def test_golden_queries_loading():
    """Test that golden queries can be loaded correctly"""
    print("Testing golden queries loading...")
    
    try:
        service = SearchBenchmarkingService(get_connection)
        queries = service.golden_queries
        
        if not queries:
            print("❌ No golden queries loaded")
            return False
        
        scenarios = queries.get("scenarios", [])
        if not scenarios:
            print("❌ No scenarios found in golden queries")
            return False
        
        total_queries = sum(len(scenario.get("queries", [])) for scenario in scenarios)
        print(f"✅ Loaded {len(scenarios)} scenarios with {total_queries} total queries")
        
        # Validate query structure
        for scenario in scenarios:
            category = scenario.get("category", "unknown")
            queries_list = scenario.get("queries", [])
            
            for query in queries_list:
                required_fields = ["id", "query", "expected_result_types", "min_results", "quality_threshold"]
                missing_fields = [field for field in required_fields if field not in query]
                
                if missing_fields:
                    print(f"❌ Query {query.get('id', 'unknown')} in category {category} missing fields: {missing_fields}")
                    return False
        
        print("✅ All golden queries have valid structure")
        return True
        
    except Exception as e:
        print(f"❌ Error loading golden queries: {e}")
        return False


async def test_single_benchmark():
    """Test running a single benchmark query"""
    print("\nTesting single benchmark execution...")
    
    try:
        service = SearchBenchmarkingService(get_connection)
        
        # Create a simple test query
        test_query = {
            "id": "test_001",
            "query": "test query",
            "expected_result_types": ["note"],
            "min_results": 0,
            "quality_threshold": 0.5,
            "context": {"user_id": 1}
        }
        
        result = await service._run_single_benchmark(
            test_query, "hybrid", 10, 5000
        )
        
        if result.status.value not in ["completed", "failed"]:
            print(f"❌ Unexpected benchmark status: {result.status.value}")
            return False
        
        print(f"✅ Single benchmark completed with status: {result.status.value}")
        print(f"   Execution time: {result.execution_time:.3f}s")
        print(f"   Result count: {result.result_count}")
        print(f"   Quality scores: {result.quality_scores}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error running single benchmark: {e}")
        return False


async def test_quick_benchmark_suite():
    """Test running a quick benchmark suite"""
    print("\nTesting quick benchmark suite...")
    
    try:
        service = SearchBenchmarkingService(get_connection)
        
        # Run a quick benchmark with just one category
        suite = await service.run_full_benchmark_suite(
            suite_id="test_quick",
            categories=["keyword_search"],
            search_modes=["hybrid"],
            save_results=False
        )
        
        if suite.total_queries == 0:
            print("❌ No queries were executed in benchmark suite")
            return False
        
        print(f"✅ Quick benchmark suite completed")
        print(f"   Suite ID: {suite.suite_id}")
        print(f"   Total queries: {suite.total_queries}")
        print(f"   Successful: {suite.successful_queries}")
        print(f"   Failed: {suite.failed_queries}")
        print(f"   Average execution time: {suite.avg_execution_time:.3f}s")
        print(f"   Regressions: {len(suite.regression_alerts)}")
        
        # Test quality summary
        if suite.quality_summary:
            print(f"   Quality summary keys: {list(suite.quality_summary.keys())}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error running benchmark suite: {e}")
        return False


async def test_database_operations():
    """Test database operations for benchmarking"""
    print("\nTesting database operations...")
    
    try:
        service = SearchBenchmarkingService(get_connection)
        
        # Test suite saving (create a minimal suite)
        from services.search_benchmarking_service import BenchmarkSuite, BenchmarkResult, BenchmarkStatus
        from datetime import datetime, timezone
        
        test_result = BenchmarkResult(
            query_id="test_db_001",
            query="test database query",
            search_mode="hybrid",
            result_limit=10,
            execution_time=0.123,
            result_count=5,
            results=[{"id": "1", "title": "test", "score": 0.8}],
            quality_scores={"relevance_score": 0.75},
            expected_vs_actual={"expected_min_results": 0, "actual_result_count": 5},
            status=BenchmarkStatus.COMPLETED
        )
        
        test_suite = BenchmarkSuite(
            suite_id="test_db_suite",
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_queries=1,
            successful_queries=1,
            failed_queries=0,
            avg_execution_time=0.123,
            total_execution_time=0.123,
            quality_summary={"relevance_score_avg": 0.75},
            category_performance={"test_category": {"success_rate": 1.0}},
            regression_alerts=[],
            results=[test_result]
        )
        
        # Save to database
        await service._save_benchmark_suite(test_suite)
        print("✅ Benchmark suite saved to database")
        
        # Test retrieval
        history = await service.get_benchmark_history(limit=1)
        if not history:
            print("❌ Could not retrieve benchmark history")
            return False
        
        print(f"✅ Retrieved {len(history)} benchmark records")
        
        # Test baseline establishment
        success = await service.establish_baseline("test_db_suite", "Test baseline")
        if not success:
            print("❌ Failed to establish baseline")
            return False
        
        print("✅ Baseline established successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Database operations failed: {e}")
        return False


async def test_automated_benchmarking():
    """Test the automated benchmarking system"""
    print("\nTesting automated benchmarking...")
    
    try:
        automation = AutomatedBenchmarking()
        
        # Test configuration loading
        if not automation.config:
            print("❌ Configuration not loaded")
            return False
        
        print("✅ Configuration loaded successfully")
        print(f"   Schedule config: {automation.config.get('schedule', {})}")
        print(f"   Benchmarking config: {automation.config.get('benchmarking', {})}")
        
        # Test quick automated benchmark
        result = await automation.run_automated_benchmark("quick")
        
        if result["status"] != "completed":
            print(f"❌ Automated benchmark failed: {result.get('error', 'Unknown error')}")
            return False
        
        print("✅ Automated benchmark completed")
        print(f"   Suite ID: {result['suite_id']}")
        print(f"   Summary: {result['summary']}")
        print(f"   Analysis: {result['analysis']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Automated benchmarking failed: {e}")
        return False


async def test_performance_measurement():
    """Test that performance measurements are accurate"""
    print("\nTesting performance measurement accuracy...")
    
    try:
        service = SearchBenchmarkingService(get_connection)
        
        # Test with a known slow operation (sleep)
        import time
        
        test_query = {
            "id": "perf_test_001",
            "query": "performance test",
            "expected_result_types": ["note"],
            "min_results": 0,
            "quality_threshold": 0.5,
            "context": {"user_id": 1}
        }
        
        start_time = time.time()
        result = await service._run_single_benchmark(
            test_query, "hybrid", 5, 5000
        )
        actual_time = time.time() - start_time
        
        # The measured time should be close to actual time (within 50ms)
        time_diff = abs(result.execution_time - actual_time)
        
        if time_diff > 0.05:  # 50ms tolerance
            print(f"❌ Performance measurement inaccurate: measured={result.execution_time:.3f}s, actual={actual_time:.3f}s, diff={time_diff:.3f}s")
            return False
        
        print(f"✅ Performance measurement accurate: {result.execution_time:.3f}s (diff: {time_diff:.3f}s)")
        return True
        
    except Exception as e:
        print(f"❌ Performance measurement test failed: {e}")
        return False


async def run_all_tests():
    """Run all benchmark tests"""
    print("🧪 Starting benchmarking system tests...\n")
    
    tests = [
        ("Golden Queries Loading", test_golden_queries_loading),
        ("Single Benchmark", test_single_benchmark),
        ("Quick Benchmark Suite", test_quick_benchmark_suite),
        ("Database Operations", test_database_operations),
        ("Automated Benchmarking", test_automated_benchmarking),
        ("Performance Measurement", test_performance_measurement)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = await test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status:8} {test_name}")
    
    print("-"*60)
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All tests passed! Benchmarking system is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return False


async def main():
    """Main test function"""
    success = await run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())