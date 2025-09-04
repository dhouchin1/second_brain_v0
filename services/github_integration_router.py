"""
GitHub/GitLab Integration FastAPI Router

Provides REST API endpoints for GitHub and GitLab integration including:
- Repository capture and synchronization
- User repositories and starred content
- Gists and code snippets
- Issues and pull requests
- Configuration and management
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl

from services.github_integration_service import GitHubIntegrationService
from services.auth_service import User

# Global service instances and functions (initialized by app.py)
github_service: Optional[GitHubIntegrationService] = None
get_conn = None
get_current_user = None

# FastAPI router
router = APIRouter(prefix="/api/github", tags=["github-integration"])

def init_github_integration_router(get_conn_func, get_current_user_func):
    """Initialize GitHub Integration router with dependencies"""
    global github_service, get_conn, get_current_user
    get_conn = get_conn_func
    get_current_user = get_current_user_func
    github_service = GitHubIntegrationService(get_conn_func)

# ─── Pydantic Models ───

class GitHubConfigRequest(BaseModel):
    """Request model for GitHub configuration"""
    github_token: str
    
class GitLabConfigRequest(BaseModel):
    """Request model for GitLab configuration"""
    gitlab_token: str
    instance_url: str = "https://gitlab.com"

class RepositoryCaptureRequest(BaseModel):
    """Request model for repository capture"""
    repository_url: HttpUrl
    
class UserRepositoriesRequest(BaseModel):
    """Request model for user repositories capture"""
    username: str
    platform: str = "github"
    limit: int = 10

class StarredRepositoriesRequest(BaseModel):
    """Request model for starred repositories capture"""
    username: str
    limit: int = 20

class GistsCaptureRequest(BaseModel):
    """Request model for gists capture"""
    username: str
    limit: int = 10

# ─── Configuration Endpoints ───

@router.post("/configure")
async def configure_github(
    request_data: GitHubConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """Configure GitHub API token for the user"""
    if not github_service:
        raise HTTPException(status_code=500, detail="GitHub integration service not initialized")
    
    try:
        # Configure the service (in production, store token securely per user)
        github_service.configure_github(request_data.github_token)
        
        # Test the token by making a simple API call
        test_response = github_service._make_github_request("https://api.github.com/user")
        
        if test_response:
            return JSONResponse(content={
                "success": True,
                "message": "GitHub integration configured successfully",
                "user_info": {
                    "login": test_response.get("login"),
                    "name": test_response.get("name"),
                    "public_repos": test_response.get("public_repos"),
                    "followers": test_response.get("followers")
                },
                "rate_limit": {
                    "remaining": github_service.rate_limit_remaining,
                    "reset_at": github_service.rate_limit_reset.isoformat() if github_service.rate_limit_reset else None
                }
            })
        else:
            raise HTTPException(status_code=401, detail="Invalid GitHub token")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to configure GitHub integration: {str(e)}")

@router.post("/gitlab/configure")
async def configure_gitlab(
    request_data: GitLabConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """Configure GitLab API token for the user"""
    if not github_service:
        raise HTTPException(status_code=500, detail="GitHub integration service not initialized")
    
    try:
        # Configure the service
        github_service.configure_gitlab(request_data.gitlab_token, request_data.instance_url)
        
        # Test the token
        test_response = github_service._make_gitlab_request(f"{request_data.instance_url}/api/v4/user")
        
        if test_response:
            return JSONResponse(content={
                "success": True,
                "message": "GitLab integration configured successfully",
                "user_info": {
                    "username": test_response.get("username"),
                    "name": test_response.get("name"),
                    "public_projects": test_response.get("public_projects_count", 0)
                },
                "instance_url": request_data.instance_url
            })
        else:
            raise HTTPException(status_code=401, detail="Invalid GitLab token")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to configure GitLab integration: {str(e)}")

# ─── Content Capture Endpoints ───

@router.post("/capture/repository")
async def capture_repository(
    request_data: RepositoryCaptureRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Capture a specific repository and its content"""
    if not github_service:
        raise HTTPException(status_code=500, detail="GitHub integration service not initialized")
    
    try:
        # Capture repository content
        contents = github_service.capture_repository(str(request_data.repository_url), current_user.id)
        
        if not contents:
            return JSONResponse(content={
                "success": False,
                "message": "No content captured from repository",
                "repository_url": str(request_data.repository_url)
            })
        
        # Save to notes database
        note_ids = github_service.save_content_to_notes(contents, current_user.id)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Successfully captured {len(contents)} items from repository",
            "repository_url": str(request_data.repository_url),
            "captured_count": len(contents),
            "note_ids": note_ids,
            "captured_items": [
                {
                    "type": content.type,
                    "title": content.title,
                    "url": content.url,
                    "tags": content.tags
                }
                for content in contents
            ]
        })
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to capture repository: {str(e)}")

@router.post("/capture/user-repos")
async def capture_user_repositories(
    request_data: UserRepositoriesRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Capture all repositories for a user"""
    if not github_service:
        raise HTTPException(status_code=500, detail="GitHub integration service not initialized")
    
    try:
        # Capture user repositories
        contents = github_service.capture_user_repositories(
            request_data.username, 
            current_user.id, 
            request_data.platform,
            request_data.limit
        )
        
        if not contents:
            return JSONResponse(content={
                "success": False,
                "message": f"No repositories found for user {request_data.username}",
                "username": request_data.username,
                "platform": request_data.platform
            })
        
        # Save to notes database
        note_ids = github_service.save_content_to_notes(contents, current_user.id)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Successfully captured {len(contents)} items from {request_data.username}'s repositories",
            "username": request_data.username,
            "platform": request_data.platform,
            "captured_count": len(contents),
            "note_ids": note_ids,
            "repositories_captured": len(set(content.metadata.get("repository", "") for content in contents))
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to capture user repositories: {str(e)}")

@router.post("/capture/starred")
async def capture_starred_repositories(
    request_data: StarredRepositoriesRequest,
    current_user: User = Depends(get_current_user)
):
    """Capture user's starred repositories"""
    if not github_service:
        raise HTTPException(status_code=500, detail="GitHub integration service not initialized")
    
    try:
        # Capture starred repositories
        contents = github_service.capture_starred_repositories(
            request_data.username, 
            current_user.id,
            request_data.limit
        )
        
        if not contents:
            return JSONResponse(content={
                "success": False,
                "message": f"No starred repositories found for user {request_data.username}",
                "username": request_data.username
            })
        
        # Save to notes database
        note_ids = github_service.save_content_to_notes(contents, current_user.id)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Successfully captured {len(contents)} starred repositories",
            "username": request_data.username,
            "captured_count": len(contents),
            "note_ids": note_ids,
            "starred_repos": [
                {
                    "title": content.title,
                    "url": content.url,
                    "language": content.metadata.get("language"),
                    "stars": content.metadata.get("stars")
                }
                for content in contents
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to capture starred repositories: {str(e)}")

@router.post("/capture/gists")
async def capture_gists(
    request_data: GistsCaptureRequest,
    current_user: User = Depends(get_current_user)
):
    """Capture user's gists"""
    if not github_service:
        raise HTTPException(status_code=500, detail="GitHub integration service not initialized")
    
    try:
        # Capture gists
        contents = github_service.capture_gists(
            request_data.username, 
            current_user.id,
            request_data.limit
        )
        
        if not contents:
            return JSONResponse(content={
                "success": False,
                "message": f"No gists found for user {request_data.username}",
                "username": request_data.username
            })
        
        # Save to notes database
        note_ids = github_service.save_content_to_notes(contents, current_user.id)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Successfully captured {len(contents)} gists",
            "username": request_data.username,
            "captured_count": len(contents),
            "note_ids": note_ids,
            "gists": [
                {
                    "title": content.title,
                    "url": content.url,
                    "files": content.metadata.get("files"),
                    "public": content.metadata.get("public")
                }
                for content in contents
            ]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to capture gists: {str(e)}")

# ─── Management and Statistics Endpoints ───

@router.get("/stats")
async def get_integration_stats(
    current_user: User = Depends(get_current_user)
):
    """Get GitHub/GitLab integration statistics"""
    if not github_service:
        raise HTTPException(status_code=500, detail="GitHub integration service not initialized")
    
    try:
        stats = github_service.get_integration_stats(current_user.id)
        
        return JSONResponse(content={
            "success": True,
            "user_id": current_user.id,
            **stats,
            "rate_limit_info": {
                "remaining": github_service.rate_limit_remaining,
                "reset_at": github_service.rate_limit_reset.isoformat() if github_service.rate_limit_reset else None
            } if github_service.github_token else None
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get integration stats: {str(e)}")

@router.get("/health")
async def github_integration_health():
    """Health check for GitHub integration service"""
    return JSONResponse(content={
        "status": "healthy" if github_service else "unavailable",
        "service": "GitHub/GitLab Integration",
        "features": {
            "github_repositories": True,
            "gitlab_projects": True,
            "issues_and_prs": True,
            "gists_and_snippets": True,
            "starred_repos": True,
            "user_repositories": True,
            "releases_and_tags": True,
            "documentation_capture": True,
            "rate_limiting": True,
            "background_processing": True
        },
        "supported_platforms": ["GitHub", "GitLab"],
        "supported_content": [
            "repositories", "issues", "pull_requests", "gists", 
            "releases", "documentation", "starred_repos", "wikis"
        ],
        "version": "1.0.0"
    })

# ─── Utility Endpoints ───

@router.get("/supported-urls")
async def get_supported_urls():
    """Get information about supported repository URLs"""
    return JSONResponse(content={
        "supported_platforms": {
            "github": {
                "base_url": "github.com",
                "example_urls": [
                    "https://github.com/owner/repo",
                    "https://github.com/owner/repo.git",
                    "git@github.com:owner/repo.git"
                ],
                "supported_content": [
                    "repository_info", "readme", "releases", "issues", 
                    "pull_requests", "gists", "starred_repos"
                ]
            },
            "gitlab": {
                "base_url": "gitlab.com",
                "example_urls": [
                    "https://gitlab.com/owner/repo",
                    "https://gitlab.com/owner/repo.git"
                ],
                "supported_content": [
                    "project_info", "readme", "issues", "merge_requests", 
                    "snippets", "wiki_pages"
                ]
            }
        },
        "url_patterns": [
            "https://github.com/{owner}/{repo}",
            "https://gitlab.com/{owner}/{repo}",
            "https://gitlab.example.com/{owner}/{repo}"
        ],
        "authentication": {
            "github": "Personal Access Token with repo scope",
            "gitlab": "Personal Access Token with read_api scope"
        }
    })

@router.post("/test-connection")
async def test_connection(
    current_user: User = Depends(get_current_user)
):
    """Test GitHub/GitLab API connections"""
    if not github_service:
        raise HTTPException(status_code=500, detail="GitHub integration service not initialized")
    
    results = {"github": None, "gitlab": None}
    
    # Test GitHub connection
    if github_service.github_token:
        try:
            github_user = github_service._make_github_request("https://api.github.com/user")
            if github_user:
                results["github"] = {
                    "status": "connected",
                    "user": github_user.get("login"),
                    "rate_limit_remaining": github_service.rate_limit_remaining
                }
            else:
                results["github"] = {"status": "error", "message": "Invalid token or API error"}
        except Exception as e:
            results["github"] = {"status": "error", "message": str(e)}
    else:
        results["github"] = {"status": "not_configured", "message": "No GitHub token configured"}
    
    # Test GitLab connection
    if github_service.gitlab_token:
        try:
            gitlab_user = github_service._make_gitlab_request(f"{github_service.gitlab_instance}/api/v4/user")
            if gitlab_user:
                results["gitlab"] = {
                    "status": "connected",
                    "user": gitlab_user.get("username"),
                    "instance": github_service.gitlab_instance
                }
            else:
                results["gitlab"] = {"status": "error", "message": "Invalid token or API error"}
        except Exception as e:
            results["gitlab"] = {"status": "error", "message": str(e)}
    else:
        results["gitlab"] = {"status": "not_configured", "message": "No GitLab token configured"}
    
    return JSONResponse(content={
        "success": True,
        "connections": results,
        "overall_status": "healthy" if any(r.get("status") == "connected" for r in results.values()) else "needs_configuration"
    })

print("[GitHub Integration Router] Loaded successfully")