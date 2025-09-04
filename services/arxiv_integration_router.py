"""
ArXiv Research Paper Integration FastAPI Router

Provides REST API endpoints for ArXiv integration including:
- Paper search and discovery by query, author, category
- Recent and trending paper retrieval
- Specific paper fetching by ArXiv ID
- Category browsing and statistics
- Automatic paper saving to notes
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.arxiv_integration_service import ArXivIntegrationService, ArXivPaper
from services.auth_service import User

# Global service instances and functions (initialized by app.py)
arxiv_service: Optional[ArXivIntegrationService] = None
get_conn = None
get_current_user = None

# FastAPI router
router = APIRouter(prefix="/api/arxiv", tags=["arxiv-integration"])

def init_arxiv_integration_router(get_conn_func, get_current_user_func):
    """Initialize ArXiv Integration router with dependencies"""
    global arxiv_service, get_conn, get_current_user
    get_conn = get_conn_func
    get_current_user = get_current_user_func
    arxiv_service = ArXivIntegrationService(get_conn_func)

# ─── Pydantic Models ───

class SearchPapersRequest(BaseModel):
    """Request model for paper search"""
    query: str
    max_results: int = 20
    category: Optional[str] = None

class AuthorPapersRequest(BaseModel):
    """Request model for author papers"""
    author: str
    max_results: int = 10

class CategoryPapersRequest(BaseModel):
    """Request model for category papers"""
    category: str
    max_results: int = 20

class RecentPapersRequest(BaseModel):
    """Request model for recent papers"""
    days: int = 7
    categories: Optional[List[str]] = None
    max_results: int = 50

class TrendingPapersRequest(BaseModel):
    """Request model for trending papers"""
    category: Optional[str] = None
    days: int = 30

class DiscoverPapersRequest(BaseModel):
    """Request model for paper discovery"""
    keywords: List[str]
    max_results: int = 30

class PaperIDRequest(BaseModel):
    """Request model for specific paper by ID"""
    arxiv_id: str

# ─── Paper Search and Discovery Endpoints ───

@router.post("/search")
async def search_papers(
    request_data: SearchPapersRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Search for papers by query string with optional category filter"""
    if not arxiv_service:
        raise HTTPException(status_code=500, detail="ArXiv integration service not initialized")
    
    try:
        # Search for papers
        papers = arxiv_service.search_papers(
            query=request_data.query,
            max_results=request_data.max_results,
            category=request_data.category
        )
        
        if not papers:
            return JSONResponse(content={
                "success": False,
                "message": f"No papers found for query: {request_data.query}",
                "query": request_data.query,
                "category": request_data.category
            })
        
        # Save papers to notes in background
        def save_papers():
            arxiv_service.save_papers_to_notes(papers, current_user.id)
        
        background_tasks.add_task(save_papers)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Found {len(papers)} papers for query: {request_data.query}",
            "query": request_data.query,
            "category": request_data.category,
            "papers_found": len(papers),
            "papers": [
                {
                    "id": paper.id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "primary_category": paper.primary_category,
                    "published": paper.published.isoformat(),
                    "arxiv_url": paper.arxiv_url,
                    "pdf_url": paper.pdf_url,
                    "abstract_preview": paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
                }
                for paper in papers
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search papers: {str(e)}")

@router.get("/author/{author}")
async def get_papers_by_author(
    author: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    max_results: int = 10
):
    """Get papers by a specific author"""
    if not arxiv_service:
        raise HTTPException(status_code=500, detail="ArXiv integration service not initialized")
    
    try:
        papers = arxiv_service.get_papers_by_author(author, max_results)
        
        if not papers:
            return JSONResponse(content={
                "success": False,
                "message": f"No papers found for author: {author}",
                "author": author
            })
        
        # Save papers to notes in background
        def save_papers():
            arxiv_service.save_papers_to_notes(papers, current_user.id)
        
        background_tasks.add_task(save_papers)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Found {len(papers)} papers by {author}",
            "author": author,
            "papers_found": len(papers),
            "papers": [
                {
                    "id": paper.id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "primary_category": paper.primary_category,
                    "published": paper.published.isoformat(),
                    "arxiv_url": paper.arxiv_url,
                    "pdf_url": paper.pdf_url,
                    "abstract_preview": paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
                }
                for paper in papers
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get papers by author: {str(e)}")

@router.get("/category/{category}")
async def get_papers_by_category(
    category: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    max_results: int = 20
):
    """Get recent papers from a specific category"""
    if not arxiv_service:
        raise HTTPException(status_code=500, detail="ArXiv integration service not initialized")
    
    try:
        papers = arxiv_service.get_papers_by_category(category, max_results)
        
        if not papers:
            return JSONResponse(content={
                "success": False,
                "message": f"No papers found for category: {category}",
                "category": category
            })
        
        # Save papers to notes in background
        def save_papers():
            arxiv_service.save_papers_to_notes(papers, current_user.id)
        
        background_tasks.add_task(save_papers)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Found {len(papers)} papers in category {category}",
            "category": category,
            "papers_found": len(papers),
            "papers": [
                {
                    "id": paper.id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "primary_category": paper.primary_category,
                    "published": paper.published.isoformat(),
                    "arxiv_url": paper.arxiv_url,
                    "pdf_url": paper.pdf_url,
                    "abstract_preview": paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
                }
                for paper in papers
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get papers by category: {str(e)}")

@router.post("/recent")
async def get_recent_papers(
    request_data: RecentPapersRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Get papers submitted in the last N days"""
    if not arxiv_service:
        raise HTTPException(status_code=500, detail="ArXiv integration service not initialized")
    
    try:
        papers = arxiv_service.get_recent_papers(
            days=request_data.days,
            categories=request_data.categories,
            max_results=request_data.max_results
        )
        
        if not papers:
            return JSONResponse(content={
                "success": False,
                "message": f"No recent papers found from the last {request_data.days} days",
                "days": request_data.days,
                "categories": request_data.categories
            })
        
        # Save papers to notes in background
        def save_papers():
            arxiv_service.save_papers_to_notes(papers, current_user.id)
        
        background_tasks.add_task(save_papers)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Found {len(papers)} recent papers from the last {request_data.days} days",
            "days": request_data.days,
            "categories": request_data.categories,
            "papers_found": len(papers),
            "papers": [
                {
                    "id": paper.id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "primary_category": paper.primary_category,
                    "published": paper.published.isoformat(),
                    "arxiv_url": paper.arxiv_url,
                    "pdf_url": paper.pdf_url,
                    "abstract_preview": paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
                }
                for paper in papers
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get recent papers: {str(e)}")

@router.post("/trending")
async def get_trending_papers(
    request_data: TrendingPapersRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Get trending papers with good relevance scores"""
    if not arxiv_service:
        raise HTTPException(status_code=500, detail="ArXiv integration service not initialized")
    
    try:
        papers = arxiv_service.get_trending_papers(
            category=request_data.category,
            days=request_data.days
        )
        
        if not papers:
            return JSONResponse(content={
                "success": False,
                "message": f"No trending papers found",
                "category": request_data.category,
                "days": request_data.days
            })
        
        # Save papers to notes in background
        def save_papers():
            arxiv_service.save_papers_to_notes(papers, current_user.id)
        
        background_tasks.add_task(save_papers)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Found {len(papers)} trending papers",
            "category": request_data.category,
            "days": request_data.days,
            "papers_found": len(papers),
            "papers": [
                {
                    "id": paper.id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "primary_category": paper.primary_category,
                    "published": paper.published.isoformat(),
                    "arxiv_url": paper.arxiv_url,
                    "pdf_url": paper.pdf_url,
                    "trending_score": paper.metadata.get("trending_score", 0),
                    "abstract_preview": paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
                }
                for paper in papers
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trending papers: {str(e)}")

@router.get("/paper/{arxiv_id}")
async def get_paper_by_id(
    arxiv_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Get a specific paper by ArXiv ID"""
    if not arxiv_service:
        raise HTTPException(status_code=500, detail="ArXiv integration service not initialized")
    
    try:
        paper = arxiv_service.get_paper_by_id(arxiv_id)
        
        if not paper:
            return JSONResponse(content={
                "success": False,
                "message": f"Paper not found with ArXiv ID: {arxiv_id}",
                "arxiv_id": arxiv_id
            })
        
        # Save paper to notes in background
        def save_paper():
            arxiv_service.save_papers_to_notes([paper], current_user.id)
        
        background_tasks.add_task(save_paper)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Found paper: {paper.title}",
            "arxiv_id": arxiv_id,
            "paper": {
                "id": paper.id,
                "title": paper.title,
                "abstract": paper.abstract,
                "authors": paper.authors,
                "categories": paper.categories,
                "primary_category": paper.primary_category,
                "published": paper.published.isoformat(),
                "updated": paper.updated.isoformat(),
                "arxiv_url": paper.arxiv_url,
                "pdf_url": paper.pdf_url,
                "tags": paper.tags,
                "metadata": paper.metadata
            }
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get paper by ID: {str(e)}")

@router.post("/discover")
async def discover_papers_by_keywords(
    request_data: DiscoverPapersRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Discover papers using multiple keywords with OR logic"""
    if not arxiv_service:
        raise HTTPException(status_code=500, detail="ArXiv integration service not initialized")
    
    try:
        papers = arxiv_service.discover_papers_by_keywords(
            keywords=request_data.keywords,
            max_results=request_data.max_results
        )
        
        if not papers:
            return JSONResponse(content={
                "success": False,
                "message": f"No papers found for keywords: {', '.join(request_data.keywords)}",
                "keywords": request_data.keywords
            })
        
        # Save papers to notes in background
        def save_papers():
            arxiv_service.save_papers_to_notes(papers, current_user.id)
        
        background_tasks.add_task(save_papers)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Discovered {len(papers)} papers using keywords: {', '.join(request_data.keywords)}",
            "keywords": request_data.keywords,
            "papers_found": len(papers),
            "papers": [
                {
                    "id": paper.id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "primary_category": paper.primary_category,
                    "published": paper.published.isoformat(),
                    "arxiv_url": paper.arxiv_url,
                    "pdf_url": paper.pdf_url,
                    "abstract_preview": paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
                }
                for paper in papers
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to discover papers: {str(e)}")

# ─── Information and Configuration Endpoints ───

@router.get("/categories")
async def get_available_categories():
    """Get available ArXiv categories with descriptions"""
    if not arxiv_service:
        raise HTTPException(status_code=500, detail="ArXiv integration service not initialized")
    
    try:
        categories = arxiv_service.get_arxiv_categories()
        
        return JSONResponse(content={
            "success": True,
            "total_categories": len(categories),
            "categories": categories,
            "major_subjects": {
                "Computer Science": [k for k in categories.keys() if k.startswith('cs.')],
                "Physics": [k for k in categories.keys() if k.startswith('physics.') or k.startswith('quant-ph') or k.startswith('hep-') or k.startswith('astro-ph') or k.startswith('cond-mat.')],
                "Mathematics": [k for k in categories.keys() if k.startswith('math.') or k.startswith('stat.')],
                "Biology": [k for k in categories.keys() if k.startswith('q-bio.')],
                "Economics": [k for k in categories.keys() if k.startswith('econ.') or k.startswith('q-fin.')]
            }
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get categories: {str(e)}")

@router.get("/stats")
async def get_integration_stats(
    current_user: User = Depends(get_current_user)
):
    """Get ArXiv integration statistics"""
    if not arxiv_service:
        raise HTTPException(status_code=500, detail="ArXiv integration service not initialized")
    
    try:
        stats = arxiv_service.get_integration_stats(current_user.id)
        
        return JSONResponse(content={
            "success": True,
            "user_id": current_user.id,
            **stats
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get integration stats: {str(e)}")

@router.get("/health")
async def arxiv_integration_health():
    """Health check for ArXiv integration service"""
    return JSONResponse(content={
        "status": "healthy" if arxiv_service else "unavailable",
        "service": "ArXiv Research Paper Integration",
        "features": {
            "paper_search": True,
            "author_papers": True,
            "category_browsing": True,
            "recent_papers": True,
            "trending_papers": True,
            "specific_paper_lookup": True,
            "keyword_discovery": True,
            "automatic_note_saving": True,
            "rate_limiting": True,
            "background_processing": True
        },
        "supported_categories": [
            "Computer Science", "Physics", "Mathematics", 
            "Biology", "Economics", "Statistics"
        ],
        "api_rate_limit": "3 seconds between requests (ArXiv requirement)",
        "data_source": "ArXiv.org",
        "version": "1.0.0"
    })

# ─── Utility Endpoints ───

@router.get("/help/search")
async def get_search_help():
    """Get help information about search capabilities"""
    return JSONResponse(content={
        "search_types": {
            "query_search": {
                "endpoint": "/api/arxiv/search",
                "description": "Search papers by keywords, titles, or content",
                "parameters": ["query", "max_results", "category"],
                "examples": [
                    "machine learning",
                    "neural networks transformer",
                    "quantum computing algorithms"
                ]
            },
            "author_search": {
                "endpoint": "/api/arxiv/author/{author}",
                "description": "Find all papers by a specific author",
                "parameters": ["author", "max_results"],
                "examples": [
                    "Geoffrey Hinton",
                    "Yoshua Bengio",
                    "Andrew Ng"
                ]
            },
            "category_search": {
                "endpoint": "/api/arxiv/category/{category}",
                "description": "Get recent papers from a specific category",
                "parameters": ["category", "max_results"],
                "examples": [
                    "cs.AI",
                    "cs.LG",
                    "cs.CV"
                ]
            },
            "keyword_discovery": {
                "endpoint": "/api/arxiv/discover",
                "description": "Discover papers using multiple keywords with OR logic",
                "parameters": ["keywords", "max_results"],
                "examples": [
                    ["deep learning", "neural networks"],
                    ["quantum", "cryptography"],
                    ["nlp", "transformer", "attention"]
                ]
            }
        },
        "tips": {
            "search_optimization": [
                "Use specific technical terms for better results",
                "Combine multiple keywords for broader discovery",
                "Use category filters to narrow down results",
                "Try different phrasings if initial search fails"
            ],
            "category_codes": "Use /api/arxiv/categories to see all available categories",
            "rate_limiting": "ArXiv enforces 3-second delays between requests",
            "automatic_saving": "All retrieved papers are automatically saved as notes"
        }
    })

@router.get("/help/categories")
async def get_category_help():
    """Get help information about ArXiv categories"""
    if not arxiv_service:
        raise HTTPException(status_code=500, detail="ArXiv integration service not initialized")
    
    try:
        categories = arxiv_service.get_arxiv_categories()
        
        # Group categories by main subject
        grouped = {}
        for code, description in categories.items():
            subject = code.split('.')[0]
            if subject not in grouped:
                grouped[subject] = []
            grouped[subject].append({"code": code, "description": description})
        
        return JSONResponse(content={
            "category_help": {
                "description": "ArXiv uses hierarchical category codes to organize papers",
                "format": "subject.subcategory (e.g., cs.AI for Computer Science - Artificial Intelligence)",
                "usage": "Use category codes in search filters or browse specific categories"
            },
            "major_subjects": {
                "cs": "Computer Science",
                "physics": "Physics",
                "math": "Mathematics", 
                "stat": "Statistics",
                "q-bio": "Quantitative Biology",
                "q-fin": "Quantitative Finance",
                "econ": "Economics"
            },
            "categories_by_subject": grouped,
            "popular_categories": {
                "cs.AI": "Artificial Intelligence",
                "cs.LG": "Machine Learning",
                "cs.CV": "Computer Vision",
                "cs.CL": "Natural Language Processing",
                "quant-ph": "Quantum Physics",
                "math.ST": "Statistics Theory",
                "stat.ML": "Statistics - Machine Learning"
            },
            "total_categories": len(categories)
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get category help: {str(e)}")

print("[ArXiv Integration Router] Loaded successfully")