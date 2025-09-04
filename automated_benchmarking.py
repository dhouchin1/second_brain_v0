#!/usr/bin/env python3
"""
Automated Search Benchmarking Integration

This script provides automated benchmarking capabilities that can be run
on schedule or triggered by code changes to ensure search performance
and quality remain consistent.
"""

import asyncio
import json
import sys
import time
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

# Add the project root to the path for imports
sys.path.append(str(Path(__file__).parent))

from services.search_benchmarking_service import SearchBenchmarkingService, BenchmarkStatus
from config import get_connection


class AutomatedBenchmarking:
    """
    Automated benchmarking system for continuous quality monitoring
    """
    
    def __init__(self, config_file: Optional[str] = None):
        self.config = self._load_config(config_file)
        self.service = SearchBenchmarkingService(get_connection)
        self.results_history = []
        
    def _load_config(self, config_file: Optional[str]) -> Dict[str, Any]:
        """Load automation configuration"""
        default_config = {
            "schedule": {
                "run_on_startup": True,
                "daily_benchmark": True,
                "weekly_full_benchmark": True,
                "run_on_code_changes": False
            },
            "alerts": {
                "regression_threshold": 0.15,
                "performance_threshold": 0.20,
                "email_notifications": False,
                "webhook_url": None
            },
            "benchmarking": {
                "default_categories": ["keyword_search", "semantic_search", "hybrid_search"],
                "quick_categories": ["keyword_search"],
                "search_modes": ["hybrid", "keyword", "semantic"],
                "establish_baseline_after_major_changes": True
            },
            "ci_integration": {
                "fail_on_regressions": True,
                "max_execution_time_increase": 0.25,
                "min_quality_score": 0.6
            }
        }
        
        if config_file and Path(config_file).exists():
            try:
                with open(config_file, 'r') as f:
                    user_config = json.load(f)
                # Merge user config with defaults
                default_config.update(user_config)
            except Exception as e:
                print(f"Warning: Could not load config file {config_file}: {e}")
        
        return default_config
    
    async def run_automated_benchmark(
        self, 
        benchmark_type: str = "daily",
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Run automated benchmark based on type
        
        Args:
            benchmark_type: Type of benchmark (daily, weekly, quick, ci)
            force: Force run even if not scheduled
            
        Returns:
            Benchmark results and status
        """
        print(f"Starting automated benchmark: {benchmark_type}")
        start_time = time.time()
        
        try:
            # Determine benchmark parameters based on type
            if benchmark_type == "quick":
                categories = self.config["benchmarking"]["quick_categories"]
                search_modes = ["hybrid"]
                suite_id = f"auto_quick_{int(time.time())}"
            elif benchmark_type == "daily":
                categories = self.config["benchmarking"]["default_categories"]
                search_modes = self.config["benchmarking"]["search_modes"]
                suite_id = f"auto_daily_{datetime.now().strftime('%Y%m%d')}"
            elif benchmark_type == "weekly":
                categories = None  # All categories
                search_modes = self.config["benchmarking"]["search_modes"]
                suite_id = f"auto_weekly_{datetime.now().strftime('%Y%W')}"
            elif benchmark_type == "ci":
                categories = self.config["benchmarking"]["quick_categories"]
                search_modes = ["hybrid"]
                suite_id = f"auto_ci_{int(time.time())}"
            else:
                raise ValueError(f"Unknown benchmark type: {benchmark_type}")
            
            # Run the benchmark
            suite = await self.service.run_full_benchmark_suite(
                suite_id=suite_id,
                categories=categories,
                search_modes=search_modes,
                save_results=True
            )
            
            # Analyze results
            analysis = await self._analyze_benchmark_results(suite, benchmark_type)
            
            # Handle alerts and notifications
            if analysis["has_regressions"] or analysis["performance_issues"]:
                await self._handle_alerts(suite, analysis, benchmark_type)
            
            # Update baseline if needed
            if (benchmark_type in ["weekly", "daily"] and 
                analysis["quality_score"] >= self.config["ci_integration"]["min_quality_score"]):
                
                if self.config["benchmarking"]["establish_baseline_after_major_changes"]:
                    await self.service.establish_baseline(
                        suite.suite_id, 
                        f"Automated baseline from {benchmark_type} benchmark"
                    )
            
            total_time = time.time() - start_time
            
            result = {
                "status": "completed",
                "benchmark_type": benchmark_type,
                "suite_id": suite.suite_id,
                "execution_time": total_time,
                "summary": {
                    "total_queries": suite.total_queries,
                    "successful_queries": suite.successful_queries,
                    "failed_queries": suite.failed_queries,
                    "success_rate": suite.successful_queries / suite.total_queries if suite.total_queries > 0 else 0,
                    "avg_execution_time": suite.avg_execution_time,
                    "regression_count": len(suite.regression_alerts)
                },
                "analysis": analysis,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Store in history
            self.results_history.append(result)
            
            print(f"Automated benchmark completed: {suite.successful_queries}/{suite.total_queries} queries successful")
            return result
            
        except Exception as e:
            error_result = {
                "status": "failed",
                "benchmark_type": benchmark_type,
                "error": str(e),
                "execution_time": time.time() - start_time,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.results_history.append(error_result)
            print(f"Automated benchmark failed: {e}")
            return error_result
    
    async def _analyze_benchmark_results(
        self, 
        suite, 
        benchmark_type: str
    ) -> Dict[str, Any]:
        """Analyze benchmark results for issues and insights"""
        analysis = {
            "has_regressions": len(suite.regression_alerts) > 0,
            "performance_issues": False,
            "quality_issues": False,
            "quality_score": 0.0,
            "performance_score": 0.0,
            "insights": [],
            "recommendations": []
        }
        
        # Calculate overall quality score
        if suite.quality_summary:
            relevance_avg = suite.quality_summary.get("relevance_score_avg", 0)
            recall_avg = suite.quality_summary.get("recall_avg", 0)
            precision_avg = suite.quality_summary.get("precision_avg", 0)
            
            # Weighted quality score
            analysis["quality_score"] = (
                relevance_avg * 0.4 + 
                recall_avg * 0.3 + 
                precision_avg * 0.3
            )
        
        # Calculate performance score (inverse of execution time, normalized)
        if suite.avg_execution_time > 0:
            # Good performance is < 500ms, poor is > 2s
            normalized_time = min(2.0, max(0.1, suite.avg_execution_time))
            analysis["performance_score"] = max(0, 1.0 - (normalized_time - 0.1) / 1.9)
        
        # Check for performance issues
        perf_threshold = self.config["alerts"]["performance_threshold"]
        if suite.avg_execution_time > 1.0:  # Over 1 second average
            analysis["performance_issues"] = True
            analysis["insights"].append(f"Average query time ({suite.avg_execution_time:.2f}s) exceeds 1 second")
        
        # Check for quality issues
        quality_threshold = self.config["ci_integration"]["min_quality_score"]
        if analysis["quality_score"] < quality_threshold:
            analysis["quality_issues"] = True
            analysis["insights"].append(f"Quality score ({analysis['quality_score']:.2f}) below threshold ({quality_threshold})")
        
        # Success rate analysis
        success_rate = suite.successful_queries / suite.total_queries if suite.total_queries > 0 else 0
        if success_rate < 0.9:
            analysis["insights"].append(f"Success rate ({success_rate:.1%}) is below 90%")
        
        # Category performance analysis
        if suite.category_performance:
            worst_category = None
            worst_success_rate = 1.0
            
            for category, perf in suite.category_performance.items():
                cat_success_rate = perf.get("success_rate", 0)
                if cat_success_rate < worst_success_rate:
                    worst_success_rate = cat_success_rate
                    worst_category = category
            
            if worst_category and worst_success_rate < 0.8:
                analysis["insights"].append(f"Category '{worst_category}' has low success rate ({worst_success_rate:.1%})")
        
        # Generate recommendations
        if analysis["performance_issues"]:
            analysis["recommendations"].append("Consider optimizing search algorithms or adding caching")
        
        if analysis["quality_issues"]:
            analysis["recommendations"].append("Review golden queries and expected results for accuracy")
        
        if len(suite.regression_alerts) > 0:
            analysis["recommendations"].append("Investigate code changes that may have caused regressions")
        
        return analysis
    
    async def _handle_alerts(
        self, 
        suite, 
        analysis: Dict[str, Any], 
        benchmark_type: str
    ):
        """Handle alerts and notifications for benchmark issues"""
        alert_data = {
            "suite_id": suite.suite_id,
            "benchmark_type": benchmark_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "regressions": suite.regression_alerts,
            "analysis": analysis
        }
        
        print(f"ALERT: Benchmark {suite.suite_id} has issues:")
        
        if analysis["has_regressions"]:
            print(f"  - {len(suite.regression_alerts)} regressions detected")
            for alert in suite.regression_alerts:
                print(f"    * {alert['type']}: {alert['query_id']} ({alert.get('degradation', 0):.1%} degradation)")
        
        if analysis["performance_issues"]:
            print(f"  - Performance issues: avg time {suite.avg_execution_time:.2f}s")
        
        if analysis["quality_issues"]:
            print(f"  - Quality issues: score {analysis['quality_score']:.2f}")
        
        # Save alert to file
        alert_file = Path("benchmark_alerts.json")
        alerts = []
        if alert_file.exists():
            try:
                alerts = json.loads(alert_file.read_text())
            except:
                alerts = []
        
        alerts.append(alert_data)
        alert_file.write_text(json.dumps(alerts, indent=2))
        
        # TODO: Implement email/webhook notifications based on config
        webhook_url = self.config["alerts"].get("webhook_url")
        if webhook_url:
            # Would send webhook notification here
            pass
    
    async def run_ci_benchmark(self) -> bool:
        """
        Run CI/CD benchmark and return success status
        
        Returns:
            True if benchmark passes CI criteria, False otherwise
        """
        print("Running CI benchmark...")
        
        result = await self.run_automated_benchmark("ci")
        
        if result["status"] != "completed":
            print("CI benchmark failed to complete")
            return False
        
        # Check CI criteria
        ci_config = self.config["ci_integration"]
        analysis = result["analysis"]
        summary = result["summary"]
        
        # Fail if regressions detected and configured to fail
        if ci_config["fail_on_regressions"] and analysis["has_regressions"]:
            print("CI benchmark failed: regressions detected")
            return False
        
        # Fail if quality below minimum
        if analysis["quality_score"] < ci_config["min_quality_score"]:
            print(f"CI benchmark failed: quality score {analysis['quality_score']:.2f} < {ci_config['min_quality_score']}")
            return False
        
        # Fail if performance degraded too much
        max_time_increase = ci_config["max_execution_time_increase"]
        if summary["avg_execution_time"] > 1.0 * (1 + max_time_increase):
            print(f"CI benchmark failed: execution time {summary['avg_execution_time']:.2f}s exceeds threshold")
            return False
        
        print("CI benchmark passed all criteria")
        return True
    
    async def generate_daily_report(self) -> Dict[str, Any]:
        """Generate daily benchmarking report"""
        report = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "recent_benchmarks": self.results_history[-7:] if len(self.results_history) >= 7 else self.results_history,
            "summary": {
                "total_runs": len(self.results_history),
                "successful_runs": len([r for r in self.results_history if r["status"] == "completed"]),
                "total_alerts": sum(len(r.get("analysis", {}).get("regressions", [])) for r in self.results_history)
            },
            "trends": await self._analyze_trends(),
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Save report
        report_file = Path(f"benchmark_report_{datetime.now().strftime('%Y%m%d')}.json")
        report_file.write_text(json.dumps(report, indent=2))
        
        return report
    
    async def _analyze_trends(self) -> Dict[str, Any]:
        """Analyze performance trends from recent benchmarks"""
        if len(self.results_history) < 2:
            return {"insufficient_data": True}
        
        recent_results = [r for r in self.results_history[-10:] if r["status"] == "completed"]
        
        if len(recent_results) < 2:
            return {"insufficient_data": True}
        
        # Calculate trends
        execution_times = [r["summary"]["avg_execution_time"] for r in recent_results]
        success_rates = [r["summary"]["success_rate"] for r in recent_results]
        quality_scores = [r["analysis"]["quality_score"] for r in recent_results if "analysis" in r]
        
        trends = {}
        
        if len(execution_times) >= 2:
            time_trend = (execution_times[-1] - execution_times[0]) / execution_times[0]
            trends["execution_time"] = {
                "trend": "improving" if time_trend < -0.05 else "degrading" if time_trend > 0.05 else "stable",
                "change": time_trend
            }
        
        if len(success_rates) >= 2:
            success_trend = success_rates[-1] - success_rates[0]
            trends["success_rate"] = {
                "trend": "improving" if success_trend > 0.05 else "degrading" if success_trend < -0.05 else "stable",
                "change": success_trend
            }
        
        if len(quality_scores) >= 2:
            quality_trend = quality_scores[-1] - quality_scores[0]
            trends["quality_score"] = {
                "trend": "improving" if quality_trend > 0.05 else "degrading" if quality_trend < -0.05 else "stable",
                "change": quality_trend
            }
        
        return trends


async def main():
    """Main CLI interface for automated benchmarking"""
    parser = argparse.ArgumentParser(description="Automated Search Benchmarking")
    parser.add_argument("command", choices=["daily", "weekly", "quick", "ci", "report"], 
                       help="Benchmark command to run")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--force", action="store_true", help="Force run even if not scheduled")
    parser.add_argument("--output", help="Output file for results")
    
    args = parser.parse_args()
    
    # Initialize automated benchmarking
    automation = AutomatedBenchmarking(args.config)
    
    try:
        if args.command == "report":
            # Generate daily report
            report = await automation.generate_daily_report()
            print(f"Daily report generated: {len(report['recent_benchmarks'])} recent benchmarks")
            
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(report, f, indent=2)
            else:
                print(json.dumps(report, indent=2))
        
        elif args.command == "ci":
            # Run CI benchmark and exit with appropriate code
            success = await automation.run_ci_benchmark()
            if not success:
                sys.exit(1)
        
        else:
            # Run specified benchmark type
            result = await automation.run_automated_benchmark(args.command, args.force)
            
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(result, f, indent=2)
            else:
                print(json.dumps(result, indent=2))
            
            # Exit with error code if benchmark failed
            if result["status"] != "completed":
                sys.exit(1)
    
    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Benchmark failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())