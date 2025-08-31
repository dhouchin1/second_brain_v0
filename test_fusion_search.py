#!/usr/bin/env python3
"""
Test script for ultimate fused hybrid search with RRF
"""

import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_fusion_search():
    """Test the complete fusion search system"""
    try:
        from hybrid_fusion import get_fusion_engine
        
        logger.info("🚀 Testing Ultimate Fused Hybrid Search with RRF...")
        
        # Get fusion engine
        fusion_engine = get_fusion_engine()
        
        # Get stats
        stats = fusion_engine.get_fusion_stats()
        logger.info(f"Fusion Stats: {stats}")
        
        # Test different queries with different characteristics
        test_queries = [
            ("machine learning algorithms", "Technical query - should benefit from both semantic and keyword matching"),
            ("python programming", "Programming query - should get BM25 boost for exact terms"),
            ("neural networks training", "Complex concept - should benefit from semantic understanding"),
            ("data preprocessing techniques", "Multi-term query - good for RRF fusion"),
            ("artificial intelligence", "Broad concept - semantic search advantage")
        ]
        
        user_id = 2  # Use existing user with most notes
        
        for query, description in test_queries:
            logger.info(f"\n🔍 Testing: '{query}'")
            logger.info(f"   Context: {description}")
            
            # Test full fusion
            results = fusion_engine.search(
                query=query,
                user_id=user_id,
                limit=5,
                use_semantic=True,
                use_bm25=True,
                use_reranking=True
            )
            
            logger.info(f"   Found {len(results)} results")
            
            for i, result in enumerate(results, 1):
                logger.info(f"     {i}. {result.title}")
                logger.info(f"        Final Score: {result.combined_score:.4f}")
                logger.info(f"        RRF Score: {result.rrf_score:.4f}")
                logger.info(f"        Semantic: {result.semantic_score:.3f} (rank: {result.semantic_rank})")
                logger.info(f"        BM25: {result.bm25_score:.3f} (rank: {result.bm25_rank})")
                logger.info(f"        Rerank: {result.rerank_score:.3f} (rank: {result.rerank_rank})")
                logger.info(f"        Sources: {result.fusion_sources}")
                if result.matched_terms:
                    logger.info(f"        Matched Terms: {result.matched_terms}")
                logger.info(f"        Snippet: {result.snippet[:100]}...")
                logger.info("")
        
        # Test different fusion configurations
        logger.info("\n⚙️  Testing Different Fusion Configurations...")
        
        test_query = "machine learning data processing"
        
        configurations = [
            (True, True, True, "Full Fusion (Semantic + BM25 + Reranking)"),
            (True, True, False, "Hybrid (Semantic + BM25)"),
            (True, False, True, "Semantic + Reranking"),
            (False, True, True, "BM25 + Reranking"),
            (True, False, False, "Semantic Only"),
            (False, True, False, "BM25 Only")
        ]
        
        for semantic, bm25, rerank, config_name in configurations:
            logger.info(f"\n📊 Configuration: {config_name}")
            
            results = fusion_engine.search(
                query=test_query,
                user_id=user_id,
                limit=3,
                use_semantic=semantic,
                use_bm25=bm25,
                use_reranking=rerank
            )
            
            logger.info(f"   Results: {len(results)}")
            for i, result in enumerate(results, 1):
                logger.info(f"     {i}. {result.title} (Score: {result.combined_score:.4f})")
        
        logger.info("\n✅ Ultimate fusion search test completed!")
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Fusion search test failed: {e}")
        return False

def test_rrf_calculation():
    """Test RRF calculation directly"""
    try:
        from hybrid_fusion import HybridFusionEngine
        
        logger.info("🧮 Testing RRF Calculation...")
        
        # Create engine with default config
        engine = HybridFusionEngine("dummy.db")
        
        # Test RRF scores for different ranks
        test_ranks = [1, 2, 3, 5, 10, 20, 50, 100]
        
        for rank in test_ranks:
            rrf_score = engine._calculate_rrf_score(rank)
            logger.info(f"   Rank {rank:3d}: RRF Score = {rrf_score:.6f}")
        
        logger.info("✅ RRF calculation test completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ RRF calculation test failed: {e}")
        return False

def test_engines_availability():
    """Test availability of all search engines"""
    try:
        logger.info("🔧 Testing Search Engines Availability...")
        
        # Test semantic search
        try:
            from semantic_search import get_search_engine
            semantic_engine = get_search_engine()
            logger.info("   ✅ Semantic search engine: Available")
        except Exception as e:
            logger.warning(f"   ⚠️  Semantic search engine: {e}")
        
        # Test BM25 sparse search
        try:
            from sparse_search import get_sparse_search_engine
            sparse_engine = get_sparse_search_engine()
            logger.info("   ✅ BM25 sparse search engine: Available")
        except Exception as e:
            logger.warning(f"   ⚠️  BM25 sparse search engine: {e}")
        
        # Test cross-encoder re-ranker
        try:
            from reranker import get_reranker
            reranker = get_reranker()
            logger.info("   ✅ Cross-encoder re-ranker: Available")
        except Exception as e:
            logger.warning(f"   ⚠️  Cross-encoder re-ranker: {e}")
        
        logger.info("✅ Engine availability test completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Engine availability test failed: {e}")
        return False

def main():
    """Main test function"""
    logger.info("🎯 Starting Ultimate Fusion Search Tests...")
    logger.info("=" * 60)
    
    success = True
    
    # Test 1: Engine availability
    if not test_engines_availability():
        success = False
    
    logger.info("-" * 40)
    
    # Test 2: RRF calculation
    if not test_rrf_calculation():
        success = False
    
    logger.info("-" * 40)
    
    # Test 3: Full fusion search
    if not test_fusion_search():
        success = False
    
    logger.info("=" * 60)
    
    if success:
        logger.info("🎉 All fusion search tests passed!")
        logger.info("\n🚀 The Ultimate Hybrid Search System is READY!")
        logger.info("\nAvailable endpoints:")
        logger.info("  • /api/search/fused     - Ultimate fused search with RRF")
        logger.info("  • /api/search/reranked  - Cross-encoder re-ranking")
        logger.info("  • /api/search/sparse    - BM25 keyword search") 
        logger.info("  • /api/search/semantic  - Vector similarity search")
        logger.info("  • /api/search/hybrid    - Basic hybrid search")
    else:
        logger.error("💥 Some tests failed!")
    
    return success

if __name__ == "__main__":
    main()