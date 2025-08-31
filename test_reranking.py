#!/usr/bin/env python3
"""
Test script for cross-encoder re-ranking functionality
"""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_reranker():
    """Test the cross-encoder re-ranker"""
    try:
        from reranker import get_reranker
        
        logger.info("🧪 Testing Cross-Encoder Re-ranking...")
        
        # Get reranker instance
        reranker = get_reranker()
        
        # Test model info
        model_info = reranker.get_model_info()
        logger.info(f"Model Info: {model_info}")
        
        # Create dummy search results for testing
        dummy_results = [
            {
                'note_id': 1,
                'title': 'Machine Learning Basics',
                'content': 'Introduction to machine learning algorithms and techniques. Covers supervised learning, unsupervised learning, and deep learning fundamentals.',
                'summary': 'ML fundamentals guide',
                'tags': ['ml', 'ai', 'learning'],
                'timestamp': '2024-01-01T10:00:00',
                'snippet': 'machine learning algorithms and techniques',
                'combined_score': 0.85,
                'match_type': 'hybrid'
            },
            {
                'note_id': 2, 
                'title': 'Python Programming',
                'content': 'Python is a versatile programming language used for web development, data science, automation, and machine learning applications.',
                'summary': 'Python overview',
                'tags': ['python', 'programming'],
                'timestamp': '2024-01-02T14:30:00', 
                'snippet': 'Python programming language for data science',
                'combined_score': 0.75,
                'match_type': 'semantic'
            },
            {
                'note_id': 3,
                'title': 'Data Preprocessing',
                'content': 'Data preprocessing is crucial for machine learning. It involves cleaning data, handling missing values, and feature engineering.',
                'summary': 'Data prep for ML',
                'tags': ['data', 'preprocessing', 'ml'],
                'timestamp': '2024-01-03T09:15:00',
                'snippet': 'data preprocessing for machine learning',
                'combined_score': 0.70,
                'match_type': 'fts'
            }
        ]
        
        # Test query
        query = "machine learning data preprocessing"
        
        logger.info(f"Testing query: '{query}'")
        logger.info(f"Original results count: {len(dummy_results)}")
        
        # Apply re-ranking
        reranked_results = reranker.rerank_results(query, dummy_results, top_k=3)
        
        logger.info(f"Re-ranked results count: {len(reranked_results)}")
        
        # Display results
        logger.info("🎯 Re-ranking Results:")
        for i, result in enumerate(reranked_results, 1):
            logger.info(f"  {i}. Note {result.note_id}: {result.title}")
            logger.info(f"     Original Score: {result.original_score:.3f}")
            logger.info(f"     Rerank Score: {result.rerank_score:.3f}")  
            logger.info(f"     Combined Score: {result.combined_score:.3f}")
            logger.info(f"     Match Type: {result.match_type}")
            logger.info("")
        
        logger.info("✅ Re-ranking test completed successfully!")
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error - dependencies not available: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Re-ranking test failed: {e}")
        return False

def test_semantic_search_integration():
    """Test integration with semantic search engine"""
    try:
        from semantic_search import get_search_engine
        
        logger.info("🔍 Testing Semantic Search Integration...")
        
        search_engine = get_search_engine()
        
        # Get search engine stats
        stats = search_engine.get_search_stats()
        logger.info(f"Search Engine Stats: {stats}")
        
        logger.info("✅ Semantic search integration test completed!")
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error - semantic search not available: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Semantic search test failed: {e}")
        return False

def main():
    """Main test function"""
    logger.info("🚀 Starting Re-ranking Tests...")
    logger.info("=" * 50)
    
    success = True
    
    # Test 1: Basic re-ranker functionality
    if not test_reranker():
        success = False
    
    logger.info("-" * 30)
    
    # Test 2: Integration with semantic search
    if not test_semantic_search_integration():
        success = False
    
    logger.info("=" * 50)
    
    if success:
        logger.info("🎉 All tests passed!")
        sys.exit(0)
    else:
        logger.error("💥 Some tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()