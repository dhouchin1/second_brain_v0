#!/usr/bin/env python3
"""
Simple test for cross-encoder re-ranking
"""

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_basic_imports():
    """Test basic imports"""
    try:
        logger.info("Testing basic imports...")
        
        # Test sentence transformers
        from sentence_transformers import CrossEncoder
        logger.info("✅ CrossEncoder import successful")
        
        # Test rank-bm25
        from rank_bm25 import BM25Okapi
        logger.info("✅ BM25Okapi import successful")
        
        # Test sklearn
        from sklearn.metrics.pairwise import cosine_similarity
        logger.info("✅ cosine_similarity import successful")
        
        return True
    except Exception as e:
        logger.error(f"❌ Import failed: {e}")
        return False

def test_cross_encoder():
    """Test cross encoder functionality"""
    try:
        logger.info("Testing CrossEncoder...")
        
        from sentence_transformers import CrossEncoder
        import numpy as np
        
        # Initialize model
        model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
        model = CrossEncoder(model_name)
        logger.info(f"✅ Loaded model: {model_name}")
        
        # Test query-document pairs
        query = "machine learning algorithms"
        documents = [
            "Introduction to machine learning and artificial intelligence",
            "Python programming tutorial for beginners", 
            "Data preprocessing techniques for ML models"
        ]
        
        # Create query-document pairs
        pairs = [[query, doc] for doc in documents]
        
        # Get predictions
        scores = model.predict(pairs)
        logger.info(f"✅ Got {len(scores)} relevance scores")
        
        # Display results
        for i, (doc, score) in enumerate(zip(documents, scores)):
            logger.info(f"  Doc {i+1}: {score:.4f} - {doc[:50]}...")
        
        return True
    except Exception as e:
        logger.error(f"❌ CrossEncoder test failed: {e}")
        return False

def test_bm25():
    """Test BM25 functionality"""
    try:
        logger.info("Testing BM25...")
        
        from rank_bm25 import BM25Okapi
        
        # Sample documents
        documents = [
            "machine learning algorithms and techniques",
            "python programming language tutorial",
            "data preprocessing for machine learning"
        ]
        
        # Tokenize documents
        tokenized_docs = [doc.split() for doc in documents]
        
        # Initialize BM25
        bm25 = BM25Okapi(tokenized_docs)
        logger.info("✅ BM25 initialized")
        
        # Test query
        query = "machine learning"
        tokenized_query = query.split()
        
        # Get scores
        scores = bm25.get_scores(tokenized_query)
        logger.info(f"✅ Got {len(scores)} BM25 scores")
        
        # Display results
        for i, (doc, score) in enumerate(zip(documents, scores)):
            logger.info(f"  Doc {i+1}: {score:.4f} - {doc}")
        
        return True
    except Exception as e:
        logger.error(f"❌ BM25 test failed: {e}")
        return False

def main():
    """Main test function"""
    logger.info("🚀 Starting Simple Re-ranking Tests...")
    
    success = True
    
    if not test_basic_imports():
        success = False
        
    if not test_cross_encoder():
        success = False
        
    if not test_bm25():
        success = False
    
    if success:
        logger.info("🎉 All basic tests passed!")
    else:
        logger.error("💥 Some tests failed!")
    
    return success

if __name__ == "__main__":
    main()