#!/usr/bin/env python3
"""Standalone/legacy search API router.

The current application primarily uses endpoints defined in `app.py` backed by
the unified `services.SearchService`. This module is kept for reference and
optional standalone router usage.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Optional, List
from pydantic import BaseModel
import logging
import time

logger = logging.getLogger(__name__)

# Pydantic models for API requests
class HybridSearchRequest(BaseModel):
    query: str
    search_type: str = 'hybrid'  # hybrid, fts, semantic
    fts_weight: float = 0.4
    semantic_weight: float = 0.6
    limit: int = 20
    min_fts_score: float = 0.1
    min_semantic_score: float = 0.1
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    tags: Optional[List[str]] = []
    types: Optional[List[str]] = []
    status: Optional[List[str]] = []

class RerankedSearchRequest(BaseModel):
    query: str
    limit: int = 8
    use_reranking: bool = True
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    tags: Optional[List[str]] = []
    types: Optional[List[str]] = []
    status: Optional[List[str]] = []

class SparseSearchRequest(BaseModel):
    query: str
    limit: int = 20
    min_score: float = 0.1
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    tags: Optional[List[str]] = []
    types: Optional[List[str]] = []
    status: Optional[List[str]] = []

class FusedSearchRequest(BaseModel):
    query: str
    limit: int = 8
    use_semantic: bool = True
    use_bm25: bool = True
    use_reranking: bool = True
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    tags: Optional[List[str]] = []
    types: Optional[List[str]] = []
    status: Optional[List[str]] = []

class SearchSuggestionsRequest(BaseModel):
    query: str
    limit: int = 5

class SearchAnalyticsRequest(BaseModel):
    user_id: Optional[int] = None
    days: int = 30

# Create router
router = APIRouter(prefix="/api/search", tags=["search"])

# This will be injected from main app
def get_current_user():
    """Placeholder - will be replaced by main app dependency"""
    pass

def create_search_router(user_dependency, db_path: str):
    """Factory function to create search router with dependencies"""
    
    @router.post("/hybrid")
    async def hybrid_search(
        request: HybridSearchRequest,
        current_user = Depends(user_dependency)
    ):
        """Hybrid search combining FTS and semantic similarity"""
        try:
            # Lazy import to avoid circular dependencies
            from hybrid_search import HybridSearchEngine
            import sqlite3
            
            engine = HybridSearchEngine(db_path)
            
            start_time = time.time()
            results = engine.search(
                query=request.query,
                user_id=current_user.id,
                search_type=request.search_type,
                fts_weight=request.fts_weight,
                semantic_weight=request.semantic_weight,
                limit=request.limit,
                min_fts_score=request.min_fts_score,
                min_semantic_score=request.min_semantic_score
            )
            execution_time = int((time.time() - start_time) * 1000)
            
            # Enrich with note type/status and apply server-side filters
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            results_data = []
            from jose import jwt
            SECRET_KEY = "super-secret-key"
            ALGORITHM = "HS256"

            def build_file_url(uid: int, filename: str) -> str:
                import datetime as _dt
                exp = _dt.datetime.utcnow() + _dt.timedelta(seconds=600)
                token = jwt.encode({"uid": uid, "fn": filename, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)
                return f"/files/{filename}?token={token}"

            for r in results:
                row = conn.execute(
                    "SELECT type, status, tags, timestamp, file_filename, file_type, file_mime_type FROM notes WHERE id=? AND user_id=?",
                    (r.note_id, current_user.id)
                ).fetchone()
                note_type = row["type"] if row else None
                note_status = row["status"] if row else None
                note_tags = r.tags if r.tags else (row["tags"].split(',') if row and row["tags"] else [])
                note_ts = r.timestamp or (row["timestamp"] if row else None)
                file_filename = row["file_filename"] if row else None
                file_type = row["file_type"] if row else None
                file_mime_type = row["file_mime_type"] if row else None
                file_url = None
                try:
                    if file_filename:
                        ft = (file_type or '').lower()
                        mt = (file_mime_type or '').lower()
                        t = (note_type or '').lower()
                        if ft == 'image' or t == 'image' or mt.startswith('image/'):
                            file_url = build_file_url(current_user.id, file_filename)
                except Exception:
                    file_url = None

                # Apply filters
                if request.types and note_type and note_type not in request.types:
                    continue
                if request.status and note_status and note_status not in request.status:
                    continue
                if request.tags:
                    if not note_tags:
                        continue
                    # require all requested tags to be present
                    tagset = {t.strip() for t in (note_tags if isinstance(note_tags, list) else str(note_tags).split(',')) if t.strip()}
                    if any(t not in tagset for t in request.tags):
                        continue
                if request.date_start and note_ts and note_ts[:10] < request.date_start:
                    continue
                if request.date_end and note_ts and note_ts[:10] > request.date_end:
                    continue

                results_data.append({
                    "note_id": r.note_id,
                    "title": r.title,
                    "content": r.content[:500] if r.content else "",
                    "summary": r.summary,
                    "tags": list(note_tags) if isinstance(note_tags, set) else note_tags,
                    "timestamp": note_ts,
                    "type": note_type,
                    "status": note_status,
                    "file_filename": file_filename,
                    "file_type": file_type,
                    "file_mime_type": file_mime_type,
                    "file_url": file_url,
                    "fts_score": r.fts_score,
                    "semantic_score": r.semantic_score,
                    "combined_score": r.combined_score,
                    "snippet": r.snippet,
                    "match_type": r.match_type,
                    "ranking_factors": getattr(r, 'ranking_factors', {})
                })
            conn.close()

            # Enforce limit post-filtering
            results_data = results_data[: request.limit]
            
            return {
                "results": results_data,
                "total": len(results_data),
                "query": request.query,
                "search_type": request.search_type,
                "analytics": {
                    "execution_time_ms": execution_time,
                    "fts_results": len([r for r in results if r.fts_score > 0]),
                    "semantic_results": len([r for r in results if r.semantic_score > 0]),
                    "total_results": len(results),
                    "weights": {
                        "fts": request.fts_weight,
                        "semantic": request.semantic_weight
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
    
    @router.post("/reranked")
    async def reranked_search(
        request: RerankedSearchRequest,
        current_user = Depends(user_dependency)
    ):
        """
        Enhanced search with cross-encoder re-ranking (Priority 1 - Highest ROI)
        
        Provides 20-30% better precision by re-ranking top results using cross-encoder.
        This is the most advanced search method available.
        """
        try:
            from semantic_search import get_search_engine
            import sqlite3
            
            search_engine = get_search_engine()
            
            start_time = time.time()
            results = search_engine.reranked_search(
                query=request.query,
                user_id=current_user.id,
                limit=request.limit,
                use_reranking=request.use_reranking
            )
            execution_time = int((time.time() - start_time) * 1000)
            
            # Enrich with note metadata and apply filters
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            results_data = []
            
            from jose import jwt
            SECRET_KEY = "super-secret-key"
            ALGORITHM = "HS256"

            def build_file_url(uid: int, filename: str) -> str:
                import datetime as _dt
                exp = _dt.datetime.utcnow() + _dt.timedelta(seconds=600)
                token = jwt.encode({"uid": uid, "fn": filename, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)
                return f"/files/{filename}?token={token}"

            for r in results:
                row = conn.execute(
                    "SELECT type, status, tags, timestamp, file_filename, file_type, file_mime_type FROM notes WHERE id=? AND user_id=?",
                    (r.note_id, current_user.id)
                ).fetchone()
                
                note_type = row["type"] if row else None
                note_status = row["status"] if row else None
                note_tags = r.tags if r.tags else (row["tags"].split(',') if row and row["tags"] else [])
                note_ts = r.timestamp or (row["timestamp"] if row else None)
                file_filename = row["file_filename"] if row else None
                file_type = row["file_type"] if row else None
                file_mime_type = row["file_mime_type"] if row else None
                file_url = None
                
                try:
                    if file_filename:
                        ft = (file_type or '').lower()
                        mt = (file_mime_type or '').lower()
                        t = (note_type or '').lower()
                        if ft == 'image' or t == 'image' or mt.startswith('image/'):
                            file_url = build_file_url(current_user.id, file_filename)
                except Exception:
                    file_url = None

                # Apply filters
                if request.types and note_type and note_type not in request.types:
                    continue
                if request.status and note_status and note_status not in request.status:
                    continue
                if request.tags:
                    if not note_tags:
                        continue
                    tagset = {t.strip() for t in (note_tags if isinstance(note_tags, list) else str(note_tags).split(',')) if t.strip()}
                    if any(t not in tagset for t in request.tags):
                        continue
                if request.date_start and note_ts and note_ts[:10] < request.date_start:
                    continue
                if request.date_end and note_ts and note_ts[:10] > request.date_end:
                    continue

                results_data.append({
                    "note_id": r.note_id,
                    "title": r.title,
                    "content": r.content[:500] if r.content else "",
                    "summary": r.summary,
                    "tags": list(note_tags) if isinstance(note_tags, set) else note_tags,
                    "timestamp": note_ts,
                    "type": note_type,
                    "status": note_status,
                    "file_filename": file_filename,
                    "file_type": file_type,
                    "file_mime_type": file_mime_type,
                    "file_url": file_url,
                    "combined_score": r.combined_score,
                    "rerank_score": r.embedding_similarity,  # This contains the rerank score
                    "snippet": r.snippet,
                    "match_type": r.match_type,
                    "rank_position": len(results_data) + 1
                })
            
            conn.close()

            # Enforce limit post-filtering
            results_data = results_data[:request.limit]
            
            return {
                "results": results_data,
                "total": len(results_data),
                "query": request.query,
                "search_type": "reranked_hybrid",
                "reranking_enabled": request.use_reranking,
                "analytics": {
                    "execution_time_ms": execution_time,
                    "total_results": len(results),
                    "reranking_applied": request.use_reranking and len(results) > 0,
                    "model_info": "cross-encoder/ms-marco-MiniLM-L-6-v2"
                }
            }
            
        except Exception as e:
            logger.error(f"Reranked search failed: {e}")
            raise HTTPException(status_code=500, detail=f"Reranked search failed: {str(e)}")
    
    @router.post("/sparse")
    async def sparse_search(
        request: SparseSearchRequest,
        current_user = Depends(user_dependency)
    ):
        """
        BM25 sparse search for exact keyword matching (Priority 2)
        
        Excellent for technical terms, exact phrases, and keyword-based queries.
        Complements semantic search by catching precise term matches.
        """
        try:
            from sparse_search import get_sparse_search_engine
            import sqlite3
            
            search_engine = get_sparse_search_engine()
            
            start_time = time.time()
            results = search_engine.search(
                query=request.query,
                user_id=current_user.id,
                limit=request.limit,
                min_score=request.min_score
            )
            execution_time = int((time.time() - start_time) * 1000)
            
            # Enrich with note metadata and apply filters
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            results_data = []
            
            from jose import jwt
            SECRET_KEY = "super-secret-key"
            ALGORITHM = "HS256"

            def build_file_url(uid: int, filename: str) -> str:
                import datetime as _dt
                exp = _dt.datetime.utcnow() + _dt.timedelta(seconds=600)
                token = jwt.encode({"uid": uid, "fn": filename, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)
                return f"/files/{filename}?token={token}"

            for r in results:
                row = conn.execute(
                    "SELECT type, status, tags, timestamp, file_filename, file_type, file_mime_type FROM notes WHERE id=? AND user_id=?",
                    (r.note_id, current_user.id)
                ).fetchone()
                
                note_type = row["type"] if row else None
                note_status = row["status"] if row else None
                note_tags = r.tags if r.tags else (row["tags"].split(',') if row and row["tags"] else [])
                note_ts = r.timestamp or (row["timestamp"] if row else None)
                file_filename = row["file_filename"] if row else None
                file_type = row["file_type"] if row else None
                file_mime_type = row["file_mime_type"] if row else None
                file_url = None
                
                try:
                    if file_filename:
                        ft = (file_type or '').lower()
                        mt = (file_mime_type or '').lower()
                        t = (note_type or '').lower()
                        if ft == 'image' or t == 'image' or mt.startswith('image/'):
                            file_url = build_file_url(current_user.id, file_filename)
                except Exception:
                    file_url = None

                # Apply filters
                if request.types and note_type and note_type not in request.types:
                    continue
                if request.status and note_status and note_status not in request.status:
                    continue
                if request.tags:
                    if not note_tags:
                        continue
                    tagset = {t.strip() for t in (note_tags if isinstance(note_tags, list) else str(note_tags).split(',')) if t.strip()}
                    if any(t not in tagset for t in request.tags):
                        continue
                if request.date_start and note_ts and note_ts[:10] < request.date_start:
                    continue
                if request.date_end and note_ts and note_ts[:10] > request.date_end:
                    continue

                results_data.append({
                    "note_id": r.note_id,
                    "title": r.title,
                    "content": r.content[:500] if r.content else "",
                    "summary": r.summary,
                    "tags": list(note_tags) if isinstance(note_tags, set) else note_tags,
                    "timestamp": note_ts,
                    "type": note_type,
                    "status": note_status,
                    "file_filename": file_filename,
                    "file_type": file_type,
                    "file_mime_type": file_mime_type,
                    "file_url": file_url,
                    "bm25_score": r.bm25_score,
                    "snippet": r.snippet,
                    "match_type": r.match_type,
                    "matched_terms": r.matched_terms
                })
            
            conn.close()

            # Enforce limit post-filtering
            results_data = results_data[:request.limit]
            
            return {
                "results": results_data,
                "total": len(results_data),
                "query": request.query,
                "search_type": "sparse_bm25",
                "analytics": {
                    "execution_time_ms": execution_time,
                    "total_results": len(results),
                    "min_score_threshold": request.min_score,
                    "bm25_parameters": {
                        "k1": search_engine.k1,
                        "b": search_engine.b
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Sparse search failed: {e}")
            raise HTTPException(status_code=500, detail=f"Sparse search failed: {str(e)}")
    
    @router.post("/fused")
    async def fused_search(
        request: FusedSearchRequest,
        current_user = Depends(user_dependency)
    ):
        """
        Ultimate Fused Hybrid Search with RRF (Priority 3 - Best Quality)
        
        Combines semantic search, BM25 keyword matching, and cross-encoder re-ranking
        using Reciprocal Rank Fusion (RRF) for the highest quality search results.
        
        This is the most advanced search method providing optimal precision and recall.
        """
        try:
            from hybrid_fusion import get_fusion_engine
            import sqlite3
            
            fusion_engine = get_fusion_engine()
            
            start_time = time.time()
            results = fusion_engine.search(
                query=request.query,
                user_id=current_user.id,
                limit=request.limit,
                use_semantic=request.use_semantic,
                use_bm25=request.use_bm25,
                use_reranking=request.use_reranking
            )
            execution_time = int((time.time() - start_time) * 1000)
            
            # Enrich with note metadata and apply filters
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            results_data = []
            
            from jose import jwt
            SECRET_KEY = "super-secret-key"
            ALGORITHM = "HS256"

            def build_file_url(uid: int, filename: str) -> str:
                import datetime as _dt
                exp = _dt.datetime.utcnow() + _dt.timedelta(seconds=600)
                token = jwt.encode({"uid": uid, "fn": filename, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)
                return f"/files/{filename}?token={token}"

            for r in results:
                row = conn.execute(
                    "SELECT type, status, tags, timestamp, file_filename, file_type, file_mime_type FROM notes WHERE id=? AND user_id=?",
                    (r.note_id, current_user.id)
                ).fetchone()
                
                note_type = row["type"] if row else None
                note_status = row["status"] if row else None
                note_tags = r.tags if r.tags else (row["tags"].split(',') if row and row["tags"] else [])
                note_ts = r.timestamp or (row["timestamp"] if row else None)
                file_filename = row["file_filename"] if row else None
                file_type = row["file_type"] if row else None
                file_mime_type = row["file_mime_type"] if row else None
                file_url = None
                
                try:
                    if file_filename:
                        ft = (file_type or '').lower()
                        mt = (file_mime_type or '').lower()
                        t = (note_type or '').lower()
                        if ft == 'image' or t == 'image' or mt.startswith('image/'):
                            file_url = build_file_url(current_user.id, file_filename)
                except Exception:
                    file_url = None

                # Apply filters
                if request.types and note_type and note_type not in request.types:
                    continue
                if request.status and note_status and note_status not in request.status:
                    continue
                if request.tags:
                    if not note_tags:
                        continue
                    tagset = {t.strip() for t in (note_tags if isinstance(note_tags, list) else str(note_tags).split(',')) if t.strip()}
                    if any(t not in tagset for t in request.tags):
                        continue
                if request.date_start and note_ts and note_ts[:10] < request.date_start:
                    continue
                if request.date_end and note_ts and note_ts[:10] > request.date_end:
                    continue

                results_data.append({
                    "note_id": r.note_id,
                    "title": r.title,
                    "content": r.content[:500] if r.content else "",
                    "summary": r.summary,
                    "tags": list(note_tags) if isinstance(note_tags, set) else note_tags,
                    "timestamp": note_ts,
                    "type": note_type,
                    "status": note_status,
                    "file_filename": file_filename,
                    "file_type": file_type,
                    "file_mime_type": file_mime_type,
                    "file_url": file_url,
                    
                    # Fusion-specific scores
                    "semantic_score": r.semantic_score,
                    "bm25_score": r.bm25_score,
                    "rerank_score": r.rerank_score,
                    "rrf_score": r.rrf_score,
                    "combined_score": r.combined_score,
                    
                    # Rankings
                    "semantic_rank": r.semantic_rank,
                    "bm25_rank": r.bm25_rank,
                    "rerank_rank": r.rerank_rank,
                    "final_rank": r.final_rank,
                    
                    "snippet": r.snippet,
                    "match_type": r.match_type,
                    "matched_terms": r.matched_terms,
                    "fusion_sources": r.fusion_sources
                })
            
            conn.close()

            # Enforce limit post-filtering
            results_data = results_data[:request.limit]
            
            # Get fusion stats
            fusion_stats = fusion_engine.get_fusion_stats()
            
            return {
                "results": results_data,
                "total": len(results_data),
                "query": request.query,
                "search_type": "fused_hybrid_rrf",
                "fusion_config": {
                    "use_semantic": request.use_semantic,
                    "use_bm25": request.use_bm25,
                    "use_reranking": request.use_reranking
                },
                "analytics": {
                    "execution_time_ms": execution_time,
                    "total_results": len(results),
                    "fusion_stats": fusion_stats,
                    "engines_used": [
                        method for method, enabled in [
                            ("semantic", request.use_semantic),
                            ("bm25", request.use_bm25),
                            ("reranking", request.use_reranking)
                        ] if enabled
                    ]
                }
            }
            
        except Exception as e:
            logger.error(f"Fused search failed: {e}")
            raise HTTPException(status_code=500, detail=f"Fused search failed: {str(e)}")
    
    @router.get("/suggestions")
    async def get_search_suggestions(
        q: str = Query(..., description="Query for suggestions"),
        limit: int = Query(5, description="Number of suggestions"),
        current_user = Depends(user_dependency)
    ):
        """Get search suggestions based on query and history"""
        try:
            from hybrid_search import HybridSearchEngine
            
            engine = HybridSearchEngine(db_path)
            suggestions = engine.get_search_suggestions(q, current_user.id, limit)
            
            return {
                "suggestions": suggestions,
                "query": q
            }
            
        except Exception as e:
            logger.error(f"Failed to get suggestions: {e}")
            return {"suggestions": [], "query": q}
    
    @router.post("/semantic")
    async def semantic_search(
        query: str = Body(..., description="Search query"),
        limit: int = Body(20, description="Number of results"),
        min_similarity: float = Body(0.1, description="Minimum similarity score"),
        current_user = Depends(user_dependency)
    ):
        """Semantic search only"""
        try:
            from semantic_search import SemanticSearchEngine
            
            search_engine = SemanticSearchEngine(db_path)
            results = search_engine.semantic_search(
                query, current_user.id, limit, min_similarity
            )
            
            results_data = []
            for result in results:
                results_data.append({
                    "note_id": result.note_id,
                    "title": result.title,
                    "content": result.content[:500] if result.content else "",
                    "summary": result.summary,
                    "tags": result.tags,
                    "timestamp": result.timestamp,
                    "similarity_score": result.similarity_score,
                    "snippet": result.snippet,
                    "match_type": "semantic"
                })
            
            return {
                "results": results_data,
                "total": len(results),
                "query": query,
                "search_type": "semantic"
            }
            
        except ImportError:
            raise HTTPException(
                status_code=503, 
                detail="Semantic search not available - sentence-transformers not installed"
            )
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
    
    @router.get("/analytics")
    async def get_search_analytics(
        days: int = Query(30, description="Number of days for analytics"),
        current_user = Depends(user_dependency)
    ):
        """Get search analytics and statistics"""
        try:
            from hybrid_search import HybridSearchEngine
            
            engine = HybridSearchEngine(db_path)
            analytics = engine.get_search_analytics(current_user.id, days)
            
            return {
                "analytics": analytics,
                "user_id": current_user.id,
                "period_days": days
            }
            
        except Exception as e:
            logger.error(f"Failed to get analytics: {e}")
            return {"analytics": {}, "user_id": current_user.id, "period_days": days}
    
    @router.post("/embeddings/generate")
    async def generate_embeddings(
        note_ids: Optional[List[int]] = Body(None, description="Specific note IDs to process"),
        force_regenerate: bool = Body(False, description="Force regeneration of existing embeddings"),
        current_user = Depends(user_dependency)
    ):
        """Generate embeddings for notes"""
        try:
            from embedding_manager import EmbeddingManager
            
            manager = EmbeddingManager(db_path)
            
            if note_ids:
                # Generate for specific notes
                for note_id in note_ids:
                    manager.create_embedding_job(note_id)
                processed = await manager.process_pending_jobs()
            else:
                # Generate for all user's notes without embeddings
                manager.rebuild_embeddings(force=force_regenerate)
                processed = await manager.process_pending_jobs()
            
            stats = manager.get_embedding_stats()
            
            return {
                "message": f"Processed {processed} embedding jobs",
                "stats": stats,
                "force_regenerate": force_regenerate
            }
            
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="Embedding generation not available - required dependencies not installed"
            )
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to generate embeddings: {str(e)}")
    
    @router.get("/embeddings/stats")
    async def get_embedding_stats(
        current_user = Depends(user_dependency)
    ):
        """Get embedding statistics"""
        try:
            from embedding_manager import EmbeddingManager
            
            manager = EmbeddingManager(db_path)
            stats = manager.get_embedding_stats()
            
            return {
                "stats": stats,
                "user_id": current_user.id
            }
            
        except ImportError:
            return {
                "stats": {"error": "Embedding system not available"},
                "user_id": current_user.id
            }
        except Exception as e:
            logger.error(f"Failed to get embedding stats: {e}")
            return {
                "stats": {"error": str(e)},
                "user_id": current_user.id
            }
    
    @router.get("/similar/{note_id}")
    async def find_similar_notes(
        note_id: int,
        limit: int = Query(10, description="Number of similar notes"),
        min_similarity: float = Query(0.3, description="Minimum similarity score"),
        include_types: Optional[List[str]] = Query(None, description="Filter by note types"),
        current_user = Depends(user_dependency)
    ):
        """Find notes similar to the specified note"""
        try:
            from note_relationships import NoteRelationshipEngine
            
            engine = NoteRelationshipEngine(db_path)
            similar_notes = engine.find_similar_notes(
                note_id, current_user.id, limit, min_similarity, include_types
            )
            
            # Convert to API response format
            results = []
            for note in similar_notes:
                results.append({
                    "note_id": note.note_id,
                    "title": note.title,
                    "summary": note.summary,
                    "tags": note.tags,
                    "similarity_score": note.similarity_score,
                    "relationship_type": note.relationship_type,
                    "snippet": note.snippet,
                    "timestamp": note.timestamp
                })
            
            return {
                "source_note_id": note_id,
                "similar_notes": results,
                "total": len(results),
                "parameters": {
                    "limit": limit,
                    "min_similarity": min_similarity,
                    "include_types": include_types
                }
            }
            
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="Note relationships not available - dependencies not installed"
            )
        except Exception as e:
            logger.error(f"Failed to find similar notes: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to find similar notes: {str(e)}")
    
    @router.post("/clusters/discover")
    async def discover_clusters(
        min_cluster_size: int = Body(3, description="Minimum notes per cluster"),
        similarity_threshold: float = Body(0.4, description="Similarity threshold for clustering"),
        current_user = Depends(user_dependency)
    ):
        """Discover clusters of related notes"""
        try:
            from note_relationships import NoteRelationshipEngine
            
            engine = NoteRelationshipEngine(db_path)
            clusters = engine.discover_note_clusters(
                current_user.id, min_cluster_size, similarity_threshold
            )
            
            # Convert to API response format
            results = []
            for cluster in clusters:
                results.append({
                    "cluster_id": cluster.cluster_id,
                    "theme": cluster.cluster_theme,
                    "note_ids": cluster.note_ids,
                    "representative_note_id": cluster.representative_note_id,
                    "avg_similarity": cluster.avg_similarity,
                    "note_count": len(cluster.note_ids),
                    "created_at": cluster.created_at
                })
            
            return {
                "clusters": results,
                "total_clusters": len(results),
                "parameters": {
                    "min_cluster_size": min_cluster_size,
                    "similarity_threshold": similarity_threshold
                }
            }
            
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="Clustering not available - dependencies not installed"
            )
        except Exception as e:
            logger.error(f"Failed to discover clusters: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to discover clusters: {str(e)}")
    
    @router.get("/clusters")
    async def get_clusters(
        current_user = Depends(user_dependency)
    ):
        """Get existing note clusters"""
        try:
            from note_relationships import NoteRelationshipEngine
            
            engine = NoteRelationshipEngine(db_path)
            clusters = engine.get_note_clusters(current_user.id)
            
            return {
                "clusters": clusters,
                "total": len(clusters)
            }
            
        except ImportError:
            return {
                "clusters": [],
                "total": 0,
                "error": "Clustering not available"
            }
        except Exception as e:
            logger.error(f"Failed to get clusters: {e}")
            return {
                "clusters": [],
                "total": 0,
                "error": str(e)
            }
    
    @router.get("/relationships/stats")
    async def get_relationship_stats(
        current_user = Depends(user_dependency)
    ):
        """Get statistics about note relationships"""
        try:
            from note_relationships import NoteRelationshipEngine
            
            engine = NoteRelationshipEngine(db_path)
            stats = engine.get_relationship_stats(current_user.id)
            
            return {
                "stats": stats,
                "user_id": current_user.id
            }
            
        except ImportError:
            return {
                "stats": {"error": "Relationship engine not available"},
                "user_id": current_user.id
            }
        except Exception as e:
            logger.error(f"Failed to get relationship stats: {e}")
            return {
                "stats": {"error": str(e)},
                "user_id": current_user.id
            }
    
    return router
