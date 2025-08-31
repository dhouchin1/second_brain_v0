#!/usr/bin/env python3
"""
Test script for BM25 sparse search functionality
"""

import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_sparse_search():
    """Test BM25 sparse search functionality"""
    try:
        from sparse_search import BM25SparseSearchEngine
        
        logger.info("🧪 Testing BM25 Sparse Search...")
        
        # Use actual database path
        db_path = "/Users/dhouchin/second_brain/notes.db"
        
        # Initialize sparse search engine
        search_engine = BM25SparseSearchEngine(db_path)
        
        # Get stats
        stats = search_engine.get_stats()
        logger.info(f"BM25 Stats: {stats}")
        
        if not stats['bm25_available']:
            logger.error("❌ BM25 not available")
            return False
        
        if not stats['index_built']:
            logger.warning("⚠️ BM25 index not built")
            return False
        
        # Test searches
        test_queries = [
            "machine learning",
            "python programming", 
            "data preprocessing",
            "artificial intelligence",
            "neural networks"
        ]
        
        for query in test_queries:
            logger.info(f"Testing query: '{query}'")
            
            # Use user_id=2 (has most notes: 116)
            results = search_engine.search(query, user_id=2, limit=5, min_score=0.01)
            
            logger.info(f"  Found {len(results)} results")
            for i, result in enumerate(results, 1):
                logger.info(f"    {i}. {result.title} (Score: {result.bm25_score:.3f})")
                if result.matched_terms:
                    logger.info(f"       Matched: {result.matched_terms}")
                logger.info(f"       Snippet: {result.snippet[:100]}...")
            logger.info("")
        
        logger.info("✅ BM25 sparse search test completed!")
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ BM25 test failed: {e}")
        return False

def test_tokenization():
    """Test BM25 tokenization"""
    try:
        from sparse_search import BM25SparseSearchEngine
        
        logger.info("🧪 Testing BM25 Tokenization...")
        
        # Test tokenizer
        search_engine = BM25SparseSearchEngine("dummy.db")
        
        test_texts = [
            "Machine learning algorithms and techniques",
            "Python programming with pandas and numpy",
            "Cross-validation and model_selection methods",
            "API endpoints with REST and GraphQL",
            "Deep neural networks for NLP tasks"
        ]
        
        for text in test_texts:
            tokens = search_engine._tokenize_text(text)
            logger.info(f"Text: '{text}'")
            logger.info(f"Tokens: {tokens}")
            logger.info("")
        
        logger.info("✅ Tokenization test completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Tokenization test failed: {e}")
        return False

def main():
    """Main test function"""
    logger.info("🚀 Starting BM25 Sparse Search Tests...")
    logger.info("=" * 50)
    
    success = True
    
    # Test 1: Basic tokenization
    if not test_tokenization():
        success = False
    
    logger.info("-" * 30)
    
    # Test 2: Full sparse search
    if not test_sparse_search():
        success = False
    
    logger.info("=" * 50)
    
    if success:
        logger.info("🎉 All sparse search tests passed!")
    else:
        logger.error("💥 Some tests failed!")
    
    return success

if __name__ == "__main__":
    main()