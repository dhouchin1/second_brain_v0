#!/usr/bin/env python3
"""
Search Performance Testing Suite for Second Brain
Tests and optimizes FTS, semantic, and hybrid search performance
"""

import time
import sqlite3
import asyncio
import statistics
from typing import List, Dict, Any
import logging
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SearchPerformanceTester:
    """Comprehensive search performance testing and optimization"""
    
    def __init__(self, db_path: str = "notes.db"):
        self.db_path = db_path
        self.test_queries = [
            "machine learning algorithms",
            "productivity tips",
            "python programming",
            "#work project management",
            "data science visualization", 
            "ai artificial intelligence",
            "web development react",
            "database optimization",
            "health fitness exercise",
            "book recommendation science fiction"
        ]
        self.results = {}
        
    def setup_test_data(self):
        """Ensure we have sufficient test data"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Check current note count
        note_count = c.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        logger.info(f"Current note count: {note_count}")
        
        if note_count < 50:
            logger.info("Generating test data for performance testing...")
            self._generate_test_notes(conn, 100 - note_count)
        
        conn.close()
        
    def _generate_test_notes(self, conn, count: int):
        """Generate synthetic test notes for performance testing"""
        test_content = [
            ("Machine Learning Basics", "Introduction to machine learning algorithms including supervised, unsupervised, and reinforcement learning. Covers neural networks, decision trees, and ensemble methods.", "machine-learning,ai,algorithms"),
            ("Python Data Analysis", "Using pandas, numpy, and matplotlib for data analysis. Data cleaning, visualization, and statistical analysis techniques.", "python,data-science,pandas"),
            ("Web Development Guide", "Complete guide to modern web development using React, Node.js, and databases. Frontend and backend development practices.", "web-dev,react,nodejs"),
            ("Productivity Systems", "Getting Things Done methodology, time blocking, and digital productivity tools. Improving focus and task management.", "productivity,gtd,time-management"),
            ("Database Optimization", "SQL query optimization, indexing strategies, and database performance tuning. PostgreSQL and SQLite best practices.", "database,sql,performance"),
            ("Health and Fitness", "Exercise routines, nutrition basics, and wellness tracking. Building sustainable healthy habits.", "health,fitness,wellness"),
            ("Book Notes: Sci-Fi", "Notes from science fiction novels including themes of AI, space exploration, and future technology.", "books,sci-fi,reading"),
            ("Project Management", "Agile methodologies, sprint planning, and team collaboration tools. Effective project delivery strategies.", "project-management,agile,teamwork"),
            ("Data Visualization", "Creating effective charts and graphs using D3.js, Tableau, and Python plotting libraries.", "data-viz,charts,python"),
            ("AI Ethics Discussion", "Exploring ethical implications of artificial intelligence, bias in algorithms, and responsible AI development.", "ai,ethics,philosophy")
        ]
        
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for i in range(count):
            title, content, tags = test_content[i % len(test_content)]
            title = f"{title} - Test {i+1}"
            
            c.execute("""
                INSERT INTO notes (title, content, summary, tags, type, timestamp, user_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, content, content[:100] + "...", tags, "test", now, 1, "complete"))
        
        conn.commit()
        logger.info(f"Generated {count} test notes")
    
    def test_fts_performance(self, user_id: int = 1) -> Dict[str, Any]:
        """Test FTS search performance"""
        logger.info("Testing FTS search performance...")
        
        try:
            from services.search_adapter import SearchService
            svc = SearchService(self.db_path)
            times = []
            results_counts = []
            for query in self.test_queries:
                start_time = time.time()
                rows = svc.search(query, mode='keyword', k=20)
                execution_time = (time.time() - start_time) * 1000
                times.append(execution_time)
                results_counts.append(len(rows))
                logger.debug(f"FTS '{query}': {execution_time:.2f}ms, {len(rows)} results")
            return {
                "avg_time_ms": statistics.mean(times),
                "median_time_ms": statistics.median(times),
                "min_time_ms": min(times),
                "max_time_ms": max(times),
                "avg_results": statistics.mean(results_counts),
                "total_tests": len(times),
                "all_times": times
            }
        except Exception as e:
            logger.error(f"FTS performance test failed: {e}")
            return {"error": str(e)}
    
    async def test_semantic_performance(self, user_id: int = 1) -> Dict[str, Any]:
        """Test semantic search performance"""
        logger.info("Testing semantic search performance...")
        
        try:
            from semantic_search import EnhancedSemanticSearch
            engine = EnhancedSemanticSearch(self.db_path)
            
            # First ensure embeddings are generated
            logger.info("Ensuring embeddings are available...")
            await self._ensure_embeddings()
            
            times = []
            results_counts = []
            
            for query in self.test_queries:
                start_time = time.time()
                results = engine.semantic_search(query, user_id, limit=20, min_similarity=0.1)
                execution_time = (time.time() - start_time) * 1000
                
                times.append(execution_time)
                results_counts.append(len(results))
                
                logger.debug(f"Semantic '{query}': {execution_time:.2f}ms, {len(results)} results")
            
            return {
                "avg_time_ms": statistics.mean(times),
                "median_time_ms": statistics.median(times),
                "min_time_ms": min(times),
                "max_time_ms": max(times),
                "avg_results": statistics.mean(results_counts),
                "total_tests": len(times),
                "all_times": times
            }
            
        except ImportError:
            logger.warning("Semantic search not available - sentence-transformers not installed")
            return {"error": "Semantic search dependencies not available"}
        except Exception as e:
            logger.error(f"Semantic performance test failed: {e}")
            return {"error": str(e)}
    
    def test_hybrid_performance(self, user_id: int = 1) -> Dict[str, Any]:
        """Test hybrid search performance"""
        logger.info("Testing hybrid search performance...")
        
        try:
            from hybrid_search import HybridSearchEngine
            engine = HybridSearchEngine(self.db_path)
            
            times = []
            results_counts = []
            
            for query in self.test_queries:
                start_time = time.time()
                results = engine.search(
                    query, user_id, 
                    search_type='hybrid',
                    fts_weight=0.4,
                    semantic_weight=0.6,
                    limit=20
                )
                execution_time = (time.time() - start_time) * 1000
                
                times.append(execution_time)
                results_counts.append(len(results))
                
                logger.debug(f"Hybrid '{query}': {execution_time:.2f}ms, {len(results)} results")
            
            return {
                "avg_time_ms": statistics.mean(times),
                "median_time_ms": statistics.median(times),
                "min_time_ms": min(times),
                "max_time_ms": max(times),
                "avg_results": statistics.mean(results_counts),
                "total_tests": len(times),
                "all_times": times
            }
            
        except Exception as e:
            logger.error(f"Hybrid performance test failed: {e}")
            return {"error": str(e)}
    
    async def _ensure_embeddings(self):
        """Ensure embeddings are generated for test data"""
        try:
            from embedding_manager import EmbeddingManager
            
            manager = EmbeddingManager(self.db_path)
            stats = manager.get_embedding_stats()
            
            if stats.get('notes_without_embeddings', 0) > 0:
                logger.info("Generating missing embeddings...")
                manager.rebuild_embeddings(force=False)
                processed = await manager.process_pending_jobs(batch_size=10)
                logger.info(f"Generated {processed} embeddings")
            else:
                logger.info("All notes have embeddings")
                
        except ImportError:
            logger.warning("Embedding manager not available")
    
    def test_database_performance(self) -> Dict[str, Any]:
        """Test database query performance and optimization"""
        logger.info("Testing database performance...")
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Test various database queries
        tests = {
            "note_count": "SELECT COUNT(*) FROM notes",
            "fts_search": "SELECT COUNT(*) FROM notes_fts WHERE notes_fts MATCH 'machine'",
            "tag_search": "SELECT COUNT(*) FROM notes WHERE tags LIKE '%python%'",
            "recent_notes": "SELECT COUNT(*) FROM notes WHERE timestamp > datetime('now', '-30 days')",
            "embedding_count": "SELECT COUNT(*) FROM note_embeddings"
        }
        
        results = {}
        for test_name, query in tests.items():
            try:
                start_time = time.time()
                result = c.execute(query).fetchone()[0]
                execution_time = (time.time() - start_time) * 1000
                
                results[test_name] = {
                    "time_ms": execution_time,
                    "result_count": result
                }
                logger.debug(f"DB test '{test_name}': {execution_time:.2f}ms, {result} results")
                
            except Exception as e:
                results[test_name] = {"error": str(e)}
        
        # Check database size
        try:
            import os
            db_size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
            results["database_size_mb"] = db_size_mb
        except:
            results["database_size_mb"] = "unknown"
        
        conn.close()
        return results
    
    def analyze_search_quality(self, user_id: int = 1) -> Dict[str, Any]:
        """Analyze search result quality and relevance"""
        logger.info("Analyzing search quality...")
        
        quality_metrics = {}
        
        try:
            # Test query: "machine learning"
            test_query = "machine learning"
            
            # Get results from different search types
            from hybrid_search import HybridSearchEngine
            engine = HybridSearchEngine(self.db_path)
            
            fts_results = engine.search(test_query, user_id, 'fts', limit=10)
            hybrid_results = engine.search(test_query, user_id, 'hybrid', limit=10)
            
            quality_metrics = {
                "fts_results_count": len(fts_results),
                "hybrid_results_count": len(hybrid_results),
                "result_overlap": len(set(r.note_id for r in fts_results) & 
                                     set(r.note_id for r in hybrid_results)),
                "avg_fts_score": statistics.mean([r.fts_score for r in fts_results]) if fts_results else 0,
                "avg_combined_score": statistics.mean([r.combined_score for r in hybrid_results]) if hybrid_results else 0
            }
            
            # Test semantic search if available
            try:
                semantic_results = engine.search(test_query, user_id, 'semantic', limit=10)
                quality_metrics["semantic_results_count"] = len(semantic_results)
                if semantic_results:
                    quality_metrics["avg_semantic_score"] = statistics.mean([r.semantic_score for r in semantic_results])
            except:
                quality_metrics["semantic_available"] = False
            
        except Exception as e:
            logger.error(f"Quality analysis failed: {e}")
            quality_metrics["error"] = str(e)
        
        return quality_metrics
    
    def optimize_database(self):
        """Apply database optimizations"""
        logger.info("Applying database optimizations...")
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        optimizations = []
        
        try:
            # Analyze and optimize tables
            c.execute("ANALYZE")
            optimizations.append("Analyzed database statistics")
            
            # Vacuum to reclaim space
            c.execute("VACUUM")
            optimizations.append("Vacuumed database")
            
            # Ensure critical indexes exist
            indexes = [
                ("idx_notes_user_timestamp", "CREATE INDEX IF NOT EXISTS idx_notes_user_timestamp ON notes(user_id, timestamp)"),
                ("idx_notes_status", "CREATE INDEX IF NOT EXISTS idx_notes_status ON notes(status)"),
                ("idx_notes_type", "CREATE INDEX IF NOT EXISTS idx_notes_type ON notes(type)"),
                ("idx_embeddings_note_model", "CREATE INDEX IF NOT EXISTS idx_embeddings_note_model ON note_embeddings(note_id, embedding_model)"),
            ]
            
            for index_name, index_sql in indexes:
                c.execute(index_sql)
                optimizations.append(f"Ensured index: {index_name}")
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Database optimization failed: {e}")
            optimizations.append(f"Error: {e}")
        
        conn.close()
        return optimizations
    
    async def run_full_performance_suite(self) -> Dict[str, Any]:
        """Run complete performance test suite"""
        logger.info("🚀 Starting comprehensive search performance test suite...")
        
        # Setup
        self.setup_test_data()
        
        # Database optimization
        optimizations = self.optimize_database()
        
        # Run all performance tests
        results = {
            "test_timestamp": datetime.now().isoformat(),
            "database_optimizations": optimizations,
            "fts_performance": self.test_fts_performance(),
            "semantic_performance": await self.test_semantic_performance(),
            "hybrid_performance": self.test_hybrid_performance(),
            "database_performance": self.test_database_performance(),
            "search_quality": self.analyze_search_quality()
        }
        
        # Generate performance report
        self.generate_performance_report(results)
        
        return results
    
    def generate_performance_report(self, results: Dict[str, Any]):
        """Generate detailed performance report"""
        report_path = f"search_performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(report_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"📊 Performance report saved to: {report_path}")
        
        # Print summary
        print("\n" + "="*60)
        print("🔍 SEARCH PERFORMANCE SUMMARY")
        print("="*60)
        
        if "fts_performance" in results and "avg_time_ms" in results["fts_performance"]:
            print(f"📝 FTS Search: {results['fts_performance']['avg_time_ms']:.2f}ms avg")
            
        if "semantic_performance" in results and "avg_time_ms" in results["semantic_performance"]:
            print(f"🧠 Semantic Search: {results['semantic_performance']['avg_time_ms']:.2f}ms avg")
            
        if "hybrid_performance" in results and "avg_time_ms" in results["hybrid_performance"]:
            print(f"⚡ Hybrid Search: {results['hybrid_performance']['avg_time_ms']:.2f}ms avg")
        
        if "database_performance" in results:
            db_size = results["database_performance"].get("database_size_mb", "unknown")
            print(f"💾 Database Size: {db_size} MB")
        
        print("\n✅ Performance testing complete!")
        print(f"📄 Full report: {report_path}")
        print("="*60 + "\n")


async def main():
    """CLI interface for performance testing"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Search Performance Testing")
    parser.add_argument("--db", default="notes.db", help="Database path")
    parser.add_argument("--user-id", type=int, default=1, help="User ID for testing")
    parser.add_argument("--quick", action="store_true", help="Run quick tests only")
    parser.add_argument("--optimize", action="store_true", help="Apply database optimizations")
    parser.add_argument("--report", action="store_true", help="Generate detailed report")
    
    args = parser.parse_args()
    
    tester = SearchPerformanceTester(args.db)
    
    if args.quick:
        # Quick FTS test only
        results = tester.test_fts_performance(args.user_id)
        print(f"FTS Performance: {results}")
        
    elif args.optimize:
        # Just run optimizations
        optimizations = tester.optimize_database()
        print("Database optimizations applied:")
        for opt in optimizations:
            print(f"  ✅ {opt}")
            
    else:
        # Full test suite
        results = await tester.run_full_performance_suite()
        
        if args.report:
            print("Detailed performance report generated.")


if __name__ == "__main__":
    asyncio.run(main())
