#!/usr/bin/env python3
"""
Hybrid Score Fusion with Reciprocal Rank Fusion (RRF)
Intelligently combines multiple search methods: Vector + BM25 + Cross-encoder
"""

import logging
import math
import time
from typing import List, Dict, Any
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class FusedSearchResult:
    """Result from fused hybrid search combining multiple methods"""
    note_id: int
    title: str
    content: str
    summary: str
    tags: List[str]
    timestamp: str
    
    # Individual scores
    semantic_score: float = 0.0
    bm25_score: float = 0.0
    rerank_score: float = 0.0
    
    # Fusion metrics
    rrf_score: float = 0.0
    combined_score: float = 0.0
    
    # Rankings
    semantic_rank: int = 0
    bm25_rank: int = 0
    rerank_rank: int = 0
    final_rank: int = 0
    
    # Metadata
    snippet: str = ""
    match_type: str = "fused"
    matched_terms: List[str] = None
    fusion_sources: List[str] = None

class HybridFusionEngine:
    """
    Advanced hybrid search using Reciprocal Rank Fusion (RRF)
    
    Combines:
    1. Semantic search (vector similarity)
    2. BM25 sparse search (keyword matching)  
    3. Cross-encoder re-ranking (query-document relevance)
    
    Uses RRF to intelligently fuse rankings from different methods.
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        
        # RRF parameters
        self.rrf_k = 60  # RRF constant (typical range: 20-100)
        
        # Method weights for final scoring
        self.semantic_weight = 0.4
        self.bm25_weight = 0.3
        self.rerank_weight = 0.3
        
        # Import search engines
        self._semantic_engine = None
        self._sparse_engine = None
        self._reranker = None
        
        self._init_engines()
    
    def _init_engines(self):
        """Initialize search engines lazily"""
        try:
            from semantic_search import get_search_engine
            self._semantic_engine = get_search_engine()
            logger.info("✅ Semantic search engine loaded")
        except ImportError as e:
            logger.warning(f"Semantic search not available: {e}")
        
        try:
            from sparse_search import get_sparse_search_engine
            self._sparse_engine = get_sparse_search_engine()
            logger.info("✅ BM25 sparse search engine loaded")
        except ImportError as e:
            logger.warning(f"BM25 sparse search not available: {e}")
        
        try:
            from reranker import get_reranker
            self._reranker = get_reranker()
            logger.info("✅ Cross-encoder re-ranker loaded")
        except ImportError as e:
            logger.warning(f"Cross-encoder re-ranker not available: {e}")
    
    def _calculate_rrf_score(self, rank: int) -> float:
        """Calculate Reciprocal Rank Fusion score"""
        return 1.0 / (self.rrf_k + rank)
    
    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """Normalize scores to 0-1 range using min-max normalization"""
        if not scores or all(s == 0 for s in scores):
            return scores
        
        min_score = min(scores)
        max_score = max(scores)
        
        if min_score == max_score:
            return [1.0] * len(scores)
        
        return [(s - min_score) / (max_score - min_score) for s in scores]
    
    def _get_semantic_results(self, query: str, user_id: int, limit: int = 50) -> List[Dict]:
        """Get semantic search results"""
        if not self._semantic_engine:
            return []
        
        try:
            results = self._semantic_engine.semantic_search(
                query, user_id, limit, similarity_threshold=0.1
            )
            
            semantic_results = []
            for i, result in enumerate(results, 1):
                semantic_results.append({
                    'note_id': result.note_id,
                    'title': result.title,
                    'content': result.content,
                    'summary': result.summary,
                    'tags': result.tags,
                    'timestamp': result.timestamp,
                    'snippet': result.snippet,
                    'semantic_score': result.semantic_score,
                    'semantic_rank': i,
                    'source': 'semantic'
                })
            
            return semantic_results
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    def _get_bm25_results(self, query: str, user_id: int, limit: int = 50) -> List[Dict]:
        """Get BM25 sparse search results"""
        if not self._sparse_engine:
            return []
        
        try:
            results = self._sparse_engine.search(
                query, user_id, limit, min_score=0.01
            )
            
            bm25_results = []
            for i, result in enumerate(results, 1):
                bm25_results.append({
                    'note_id': result.note_id,
                    'title': result.title,
                    'content': result.content,
                    'summary': result.summary,
                    'tags': result.tags,
                    'timestamp': result.timestamp,
                    'snippet': result.snippet,
                    'bm25_score': result.bm25_score,
                    'bm25_rank': i,
                    'matched_terms': result.matched_terms,
                    'source': 'bm25'
                })
            
            return bm25_results
            
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []
    
    def _apply_reranking(self, query: str, combined_results: List[Dict]) -> List[Dict]:
        """Apply cross-encoder re-ranking to combined results"""
        if not self._reranker or not combined_results:
            return combined_results
        
        try:
            # Prepare results for re-ranking
            rerank_input = []
            for result in combined_results:
                rerank_input.append({
                    'note_id': result['note_id'],
                    'title': result.get('title', ''),
                    'content': result.get('content', ''),
                    'summary': result.get('summary', ''),
                    'tags': result.get('tags', []),
                    'snippet': result.get('snippet', ''),
                    'combined_score': result.get('rrf_score', 0.0)
                })
            
            # Apply re-ranking
            reranked_results = self._reranker.rerank_results(
                query, rerank_input, top_k=len(rerank_input)
            )
            
            # Update combined results with re-ranking information
            rerank_lookup = {r.note_id: (r.rerank_score, i+1) for i, r in enumerate(reranked_results)}
            
            for result in combined_results:
                if result['note_id'] in rerank_lookup:
                    rerank_score, rerank_rank = rerank_lookup[result['note_id']]
                    result['rerank_score'] = rerank_score
                    result['rerank_rank'] = rerank_rank
                else:
                    result['rerank_score'] = 0.0
                    result['rerank_rank'] = 999
            
            return combined_results
            
        except Exception as e:
            logger.error(f"Re-ranking failed: {e}")
            # Return original results without re-ranking
            for result in combined_results:
                result['rerank_score'] = 0.0
                result['rerank_rank'] = 999
            return combined_results
    
    def search(self, query: str, user_id: int, limit: int = 8, 
               use_semantic: bool = True, use_bm25: bool = True, use_reranking: bool = True) -> List[FusedSearchResult]:
        """
        Perform fused hybrid search with RRF
        
        Args:
            query: Search query
            user_id: User ID for scoped search
            limit: Final number of results to return
            use_semantic: Whether to include semantic search
            use_bm25: Whether to include BM25 search
            use_reranking: Whether to apply cross-encoder re-ranking
        
        Returns:
            List of fused search results ranked by RRF + re-ranking
        """
        start_time = time.time()
        
        try:
            logger.info(f"Starting fused hybrid search: '{query}' for user {user_id}")
            
            # Step 1: Gather results from different sources
            all_results = {}  # note_id -> result_data
            search_limit = max(50, limit * 5)  # Get more results for better fusion
            
            # Get semantic results
            if use_semantic:
                semantic_results = self._get_semantic_results(query, user_id, search_limit)
                logger.info(f"Semantic search: {len(semantic_results)} results")
                
                for result in semantic_results:
                    note_id = result['note_id']
                    if note_id not in all_results:
                        all_results[note_id] = result
                        all_results[note_id]['fusion_sources'] = []
                    
                    all_results[note_id]['semantic_score'] = result['semantic_score']
                    all_results[note_id]['semantic_rank'] = result['semantic_rank']
                    all_results[note_id]['fusion_sources'].append('semantic')
            
            # Get BM25 results
            if use_bm25:
                bm25_results = self._get_bm25_results(query, user_id, search_limit)
                logger.info(f"BM25 search: {len(bm25_results)} results")
                
                for result in bm25_results:
                    note_id = result['note_id']
                    if note_id not in all_results:
                        all_results[note_id] = result
                        all_results[note_id]['fusion_sources'] = []
                    
                    all_results[note_id]['bm25_score'] = result['bm25_score']
                    all_results[note_id]['bm25_rank'] = result['bm25_rank']
                    all_results[note_id]['matched_terms'] = result.get('matched_terms', [])
                    all_results[note_id]['fusion_sources'].append('bm25')
                    
                    # Prefer BM25 snippet if it has matched terms
                    if result.get('matched_terms'):
                        all_results[note_id]['snippet'] = result['snippet']
            
            if not all_results:
                logger.info("No results found from any search method")
                return []
            
            # Step 2: Calculate RRF scores
            combined_results = list(all_results.values())
            
            for result in combined_results:
                rrf_score = 0.0
                
                # Add RRF contribution from each method
                if result.get('semantic_rank', 0) > 0:
                    rrf_score += self._calculate_rrf_score(result['semantic_rank']) * self.semantic_weight
                
                if result.get('bm25_rank', 0) > 0:
                    rrf_score += self._calculate_rrf_score(result['bm25_rank']) * self.bm25_weight
                
                result['rrf_score'] = rrf_score
            
            # Step 3: Apply cross-encoder re-ranking
            if use_reranking:
                logger.info("Applying cross-encoder re-ranking...")
                combined_results = self._apply_reranking(query, combined_results)
            
            # Step 4: Calculate final combined scores
            for result in combined_results:
                # Normalize re-ranking score (sigmoid)
                rerank_score = result.get('rerank_score', 0.0)
                normalized_rerank = 1 / (1 + math.exp(-float(rerank_score))) if use_reranking else 0.0
                
                # Combine RRF score with re-ranking
                if use_reranking and rerank_score != 0.0:
                    result['combined_score'] = (
                        result['rrf_score'] * 0.5 +  # RRF contribution
                        normalized_rerank * self.rerank_weight * 0.5  # Re-ranking contribution
                    )
                else:
                    result['combined_score'] = result['rrf_score']
            
            # Step 5: Final ranking and result formatting
            combined_results.sort(key=lambda x: x['combined_score'], reverse=True)
            
            # Convert to FusedSearchResult objects
            final_results = []
            for i, result in enumerate(combined_results[:limit], 1):
                fused_result = FusedSearchResult(
                    note_id=result['note_id'],
                    title=result.get('title', ''),
                    content=result.get('content', ''),
                    summary=result.get('summary', ''),
                    tags=result.get('tags', []),
                    timestamp=result.get('timestamp', ''),
                    semantic_score=result.get('semantic_score', 0.0),
                    bm25_score=result.get('bm25_score', 0.0),
                    rerank_score=result.get('rerank_score', 0.0),
                    rrf_score=result.get('rrf_score', 0.0),
                    combined_score=result.get('combined_score', 0.0),
                    semantic_rank=result.get('semantic_rank', 0),
                    bm25_rank=result.get('bm25_rank', 0),
                    rerank_rank=result.get('rerank_rank', 0),
                    final_rank=i,
                    snippet=result.get('snippet', ''),
                    match_type='fused',
                    matched_terms=result.get('matched_terms', []),
                    fusion_sources=result.get('fusion_sources', [])
                )
                final_results.append(fused_result)
            
            execution_time = time.time() - start_time
            logger.info(f"✅ Fused hybrid search completed: {len(final_results)} results in {execution_time:.3f}s")
            
            return final_results
            
        except Exception as e:
            logger.error(f"Fused hybrid search failed: {e}")
            return []
    
    def update_config(self, rrf_k: int = None, semantic_weight: float = None,
                     bm25_weight: float = None, rerank_weight: float = None):
        """Update fusion configuration"""
        if rrf_k is not None:
            self.rrf_k = rrf_k
        if semantic_weight is not None:
            self.semantic_weight = semantic_weight
        if bm25_weight is not None:
            self.bm25_weight = bm25_weight
        if rerank_weight is not None:
            self.rerank_weight = rerank_weight
        
        logger.info(f"Updated fusion config: RRF_k={self.rrf_k}, weights=({self.semantic_weight}, {self.bm25_weight}, {self.rerank_weight})")
    
    def get_fusion_stats(self) -> Dict[str, Any]:
        """Get fusion engine statistics"""
        return {
            'engines_available': {
                'semantic': self._semantic_engine is not None,
                'bm25': self._sparse_engine is not None,
                'reranker': self._reranker is not None
            },
            'rrf_parameters': {
                'k': self.rrf_k
            },
            'weights': {
                'semantic': self.semantic_weight,
                'bm25': self.bm25_weight,
                'rerank': self.rerank_weight
            }
        }

# Global fusion engine instance
_fusion_engine = None

def get_fusion_engine() -> HybridFusionEngine:
    """Get global fusion engine instance"""
    global _fusion_engine
    if _fusion_engine is None:
        from config import settings
        _fusion_engine = HybridFusionEngine(str(settings.db_path))
    return _fusion_engine
