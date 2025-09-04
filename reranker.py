#!/usr/bin/env python3
"""
Cross-Encoder Re-ranking for Second Brain
Implements sentence-transformers cross-encoder for result re-ranking
"""

import logging
import math
import time
from typing import List, Dict, Optional
from dataclasses import dataclass
from pathlib import Path

try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CROSS_ENCODER_AVAILABLE = False
    
from config import settings

logger = logging.getLogger(__name__)

@dataclass
class RerankResult:
    """Result from cross-encoder re-ranking"""
    note_id: int
    title: str
    content: str
    summary: str
    tags: List[str]
    timestamp: str
    original_score: float
    rerank_score: float
    combined_score: float
    snippet: str
    match_type: str
    rank_position: int

class CrossEncoderReranker:
    """Cross-encoder based re-ranking for search results"""
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Initialize cross-encoder re-ranker
        
        Args:
            model_name: Cross-encoder model to use
                       - "cross-encoder/ms-marco-MiniLM-L-6-v2" (fast, good quality)
                       - "cross-encoder/ms-marco-MiniLM-L-12-v2" (better quality, slower)
        """
        self.model_name = model_name
        self.model = None
        self.model_path = Path(settings.base_dir) / f"cross_encoder_model_{model_name.replace('/', '_')}"
        
        # Config
        self.rerank_top_k = 20  # How many results to re-rank
        self.final_top_k = 8    # Final number of results to return
        self.rerank_weight = 0.7  # Weight for re-ranking score in final combination
        self.original_weight = 0.3  # Weight for original score
        
        if CROSS_ENCODER_AVAILABLE:
            self._init_model()
    
    def _init_model(self):
        """Initialize the cross-encoder model"""
        try:
            logger.info(f"Loading cross-encoder model: {self.model_name}")
            
            # Try to load from cache first
            if self.model_path.exists():
                logger.info(f"Loading cached cross-encoder from {self.model_path}")
                self.model = CrossEncoder(str(self.model_path))
            else:
                logger.info(f"Downloading cross-encoder {self.model_name} (first time only)")
                self.model = CrossEncoder(self.model_name)
                # Cache the model locally
                self.model_path.mkdir(parents=True, exist_ok=True)
                self.model.save(str(self.model_path))
                logger.info(f"Cross-encoder cached to {self.model_path}")
            
            logger.info("✅ Cross-encoder model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load cross-encoder model: {e}")
            self.model = None
    
    def _prepare_text_for_reranking(self, result: Dict) -> str:
        """Prepare note text for cross-encoder input"""
        parts = []
        
        # Add title with higher importance
        if result.get('title'):
            parts.append(f"Title: {result['title']}")
        
        # Add summary if available
        if result.get('summary'):
            parts.append(f"Summary: {result['summary']}")
        
        # Add snippet or content (truncated)
        text_content = result.get('snippet') or result.get('content', '')
        if text_content:
            # Clean and limit text length for cross-encoder
            text_content = text_content.replace('<mark>', '').replace('</mark>', '')
            if len(text_content) > 500:
                text_content = text_content[:500] + "..."
            parts.append(text_content)
        
        # Add tags context
        if result.get('tags'):
            if isinstance(result['tags'], list):
                tags_str = ', '.join(result['tags'])
            else:
                tags_str = str(result['tags'])
            parts.append(f"Tags: {tags_str}")
        
        return " | ".join(parts)
    
    def rerank_results(self, query: str, results: List[Dict], 
                      top_k: Optional[int] = None) -> List[RerankResult]:
        """
        Re-rank search results using cross-encoder
        
        Args:
            query: Original search query
            results: List of search results (with fields: note_id, title, content, etc.)
            top_k: Number of top results to return (defaults to self.final_top_k)
            
        Returns:
            List of re-ranked results with scores
        """
        if not self.model or not CROSS_ENCODER_AVAILABLE:
            logger.warning("Cross-encoder not available, returning original results")
            return self._convert_to_rerank_results(results[:top_k or self.final_top_k])
        
        if not results:
            return []
        
        start_time = time.time()
        
        try:
            # Limit to top results for re-ranking
            top_results = results[:self.rerank_top_k]
            
            # Prepare query-document pairs for cross-encoder
            query_doc_pairs = []
            for result in top_results:
                doc_text = self._prepare_text_for_reranking(result)
                query_doc_pairs.append([query, doc_text])
            
            # Get re-ranking scores
            if query_doc_pairs:
                rerank_scores = self.model.predict(query_doc_pairs)
                
                # Convert numpy array to list
                if hasattr(rerank_scores, 'tolist'):
                    rerank_scores = rerank_scores.tolist()
                elif not isinstance(rerank_scores, list):
                    rerank_scores = [float(rerank_scores)]
            else:
                rerank_scores = []
            
            # Combine original and re-ranking scores
            reranked_results = []
            for i, (result, rerank_score) in enumerate(zip(top_results, rerank_scores)):
                # Get original score (could be semantic_score, fts_score, or combined_score)
                original_score = (
                    result.get('combined_score', 0) or 
                    result.get('semantic_score', 0) or 
                    result.get('fts_score', 0) or 
                    result.get('score', 0)
                )
                
                # Normalize rerank score (sigmoid to 0-1 range)  
                rerank_score_float = float(rerank_score)
                normalized_rerank = 1 / (1 + math.exp(-rerank_score_float))
                
                # Combine scores
                combined_score = (
                    normalized_rerank * self.rerank_weight + 
                    float(original_score) * self.original_weight
                )
                
                reranked_result = RerankResult(
                    note_id=result.get('note_id', 0),
                    title=result.get('title', ''),
                    content=result.get('content', ''),
                    summary=result.get('summary', ''),
                    tags=result.get('tags', []),
                    timestamp=result.get('timestamp', ''),
                    original_score=float(original_score),
                    rerank_score=float(rerank_score),
                    combined_score=combined_score,
                    snippet=result.get('snippet', ''),
                    match_type=f"{result.get('match_type', 'unknown')}_reranked",
                    rank_position=i + 1
                )
                
                reranked_results.append(reranked_result)
            
            # Sort by combined score
            reranked_results.sort(key=lambda x: x.combined_score, reverse=True)
            
            # Return top_k results
            final_top_k = top_k or self.final_top_k
            final_results = reranked_results[:final_top_k]
            
            # Update rank positions after sorting
            for i, result in enumerate(final_results):
                result.rank_position = i + 1
            
            execution_time = time.time() - start_time
            logger.info(f"Re-ranked {len(top_results)} results to {len(final_results)} in {execution_time:.3f}s")
            
            return final_results
            
        except Exception as e:
            logger.error(f"Cross-encoder re-ranking failed: {e}")
            # Fallback to original results
            return self._convert_to_rerank_results(results[:top_k or self.final_top_k])
    
    def _convert_to_rerank_results(self, results: List[Dict]) -> List[RerankResult]:
        """Convert original results to RerankResult format (fallback)"""
        rerank_results = []
        
        for i, result in enumerate(results):
            original_score = (
                result.get('combined_score', 0) or 
                result.get('semantic_score', 0) or 
                result.get('fts_score', 0) or 
                result.get('score', 0)
            )
            
            rerank_result = RerankResult(
                note_id=result.get('note_id', 0),
                title=result.get('title', ''),
                content=result.get('content', ''),
                summary=result.get('summary', ''),
                tags=result.get('tags', []),
                timestamp=result.get('timestamp', ''),
                original_score=float(original_score),
                rerank_score=float(original_score),  # Same as original
                combined_score=float(original_score),
                snippet=result.get('snippet', ''),
                match_type=result.get('match_type', 'unknown'),
                rank_position=i + 1
            )
            
            rerank_results.append(rerank_result)
        
        return rerank_results
    
    def update_config(self, rerank_top_k: int = None, final_top_k: int = None,
                     rerank_weight: float = None, original_weight: float = None):
        """Update re-ranking configuration"""
        if rerank_top_k is not None:
            self.rerank_top_k = rerank_top_k
        if final_top_k is not None:
            self.final_top_k = final_top_k
        if rerank_weight is not None:
            self.rerank_weight = rerank_weight
        if original_weight is not None:
            self.original_weight = original_weight
        
        logger.info(f"Updated reranker config: top_k={self.rerank_top_k}, "
                   f"final_k={self.final_top_k}, weights=({self.rerank_weight}, {self.original_weight})")
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model"""
        return {
            'model_name': self.model_name,
            'model_available': self.model is not None,
            'cross_encoder_available': CROSS_ENCODER_AVAILABLE,
            'model_path': str(self.model_path),
            'rerank_top_k': self.rerank_top_k,
            'final_top_k': self.final_top_k,
            'rerank_weight': self.rerank_weight,
            'original_weight': self.original_weight
        }

# Add numpy import
try:
    import numpy as np
except ImportError:
    # Fallback sigmoid implementation
    import math
    def sigmoid(x):
        return 1 / (1 + math.exp(-x))
    
    # Create a simple numpy-like interface
    class SimpleNP:
        @staticmethod
        def exp(x):
            if isinstance(x, (list, tuple)):
                return [math.exp(i) for i in x]
            return math.exp(x)
    
    np = SimpleNP()

# Global re-ranker instance
_reranker = None

def get_reranker() -> CrossEncoderReranker:
    """Get global re-ranker instance"""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker()
    return _reranker

# Configuration constants for easy tuning
RERANK_CONFIG = {
    'models': {
        'fast': "cross-encoder/ms-marco-MiniLM-L-6-v2",      # Fast, good quality
        'accurate': "cross-encoder/ms-marco-MiniLM-L-12-v2",  # Better quality, slower
        'best': "cross-encoder/ms-marco-electra-base"         # Highest quality, slowest
    },
    'default_model': 'fast',
    'rerank_top_k': 20,        # Re-rank top 20 results
    'final_top_k': 8,          # Return top 8 results
    'rerank_weight': 0.7,      # Weight for cross-encoder score
    'original_weight': 0.3,    # Weight for original score
}
