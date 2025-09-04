"""
GitHub/GitLab Integration Service

Provides integration with GitHub and GitLab APIs to automatically capture:
- Repository information, READMEs, and documentation
- Issues, pull requests, and discussions
- Code snippets, gists, and releases
- Wiki pages and project documentation
- User repositories and starred content
"""

import json
import requests
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from urllib.parse import urlparse
import time
import re

@dataclass
class GitHubContent:
    id: str
    title: str
    content: str
    url: str
    type: str  # repository, issue, pr, gist, wiki, etc.
    author: str
    created_at: datetime
    updated_at: datetime
    tags: List[str]
    metadata: Dict[str, Any]

class GitHubIntegrationService:
    def __init__(self, get_conn: Callable[[], sqlite3.Connection]):
        self.get_conn = get_conn
        self.github_token = None
        self.gitlab_token = None
        self.rate_limit_remaining = 5000
        self.rate_limit_reset = None
        
    def configure_github(self, token: str):
        """Configure GitHub API token"""
        self.github_token = token
        
    def configure_gitlab(self, token: str, instance_url: str = "https://gitlab.com"):
        """Configure GitLab API token and instance URL"""
        self.gitlab_token = token
        self.gitlab_instance = instance_url
        
    def _make_github_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make authenticated GitHub API request with rate limiting"""
        if not self.github_token:
            raise ValueError("GitHub token not configured")
            
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SecondBrain-Integration/1.0"
        }
        
        # Check rate limit
        if self.rate_limit_remaining <= 10:
            if self.rate_limit_reset and datetime.now() < self.rate_limit_reset:
                wait_time = (self.rate_limit_reset - datetime.now()).total_seconds()
                print(f"Rate limit near exhaustion, waiting {wait_time:.0f} seconds")
                time.sleep(wait_time)
        
        try:
            response = requests.get(url, headers=headers, params=params or {})
            
            # Update rate limit info
            self.rate_limit_remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
            reset_timestamp = response.headers.get("X-RateLimit-Reset")
            if reset_timestamp:
                self.rate_limit_reset = datetime.fromtimestamp(int(reset_timestamp))
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                print(f"GitHub API error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            print(f"GitHub API request failed: {e}")
            return None
    
    def _make_gitlab_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make authenticated GitLab API request"""
        if not self.gitlab_token:
            raise ValueError("GitLab token not configured")
            
        headers = {
            "Authorization": f"Bearer {self.gitlab_token}",
            "User-Agent": "SecondBrain-Integration/1.0"
        }
        
        try:
            response = requests.get(url, headers=headers, params=params or {})
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                print(f"GitLab API error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            print(f"GitLab API request failed: {e}")
            return None
    
    def capture_repository(self, repo_url: str, user_id: int) -> List[GitHubContent]:
        """Capture repository information and key files"""
        results = []
        
        # Parse repository URL
        parsed = urlparse(repo_url)
        if "github.com" in parsed.netloc:
            platform = "github"
        elif "gitlab.com" in parsed.netloc or "gitlab" in parsed.netloc:
            platform = "gitlab"
        else:
            raise ValueError("Unsupported repository platform")
        
        # Extract owner/repo from path
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) < 2:
            raise ValueError("Invalid repository URL format")
        
        owner, repo = path_parts[0], path_parts[1]
        
        if platform == "github":
            results.extend(self._capture_github_repository(owner, repo, user_id))
        else:
            results.extend(self._capture_gitlab_repository(f"{owner}/{repo}", user_id))
        
        return results
    
    def _capture_github_repository(self, owner: str, repo: str, user_id: int) -> List[GitHubContent]:
        """Capture GitHub repository content"""
        results = []
        
        # Get repository info
        repo_data = self._make_github_request(f"https://api.github.com/repos/{owner}/{repo}")
        if not repo_data:
            return results
        
        # Repository overview
        repo_content = GitHubContent(
            id=f"github_repo_{repo_data['id']}",
            title=f"{repo_data['name']} - {repo_data.get('description', 'Repository')}",
            content=self._format_repository_overview(repo_data),
            url=repo_data['html_url'],
            type="repository",
            author=repo_data['owner']['login'],
            created_at=datetime.fromisoformat(repo_data['created_at'].replace('Z', '+00:00')),
            updated_at=datetime.fromisoformat(repo_data['updated_at'].replace('Z', '+00:00')),
            tags=["github", "repository", repo_data['language']] + repo_data.get('topics', []),
            metadata={
                "stars": repo_data['stargazers_count'],
                "forks": repo_data['forks_count'],
                "language": repo_data['language'],
                "license": repo_data.get('license', {}).get('name') if repo_data.get('license') else None,
                "size": repo_data['size']
            }
        )
        results.append(repo_content)
        
        # Capture README
        readme = self._make_github_request(f"https://api.github.com/repos/{owner}/{repo}/readme")
        if readme:
            readme_content = requests.get(readme['download_url']).text
            readme_item = GitHubContent(
                id=f"github_readme_{repo_data['id']}",
                title=f"{repo_data['name']} README",
                content=readme_content,
                url=readme['html_url'],
                type="documentation",
                author=repo_data['owner']['login'],
                created_at=datetime.now(),
                updated_at=datetime.now(),
                tags=["github", "readme", "documentation"],
                metadata={"repository": f"{owner}/{repo}", "file_type": "markdown"}
            )
            results.append(readme_item)
        
        # Capture recent releases
        releases = self._make_github_request(f"https://api.github.com/repos/{owner}/{repo}/releases", {"per_page": 5})
        if releases:
            for release in releases:
                release_item = GitHubContent(
                    id=f"github_release_{release['id']}",
                    title=f"{repo_data['name']} Release {release['tag_name']}",
                    content=f"# {release['name']}\n\n{release.get('body', '')}",
                    url=release['html_url'],
                    type="release",
                    author=release['author']['login'],
                    created_at=datetime.fromisoformat(release['created_at'].replace('Z', '+00:00')),
                    updated_at=datetime.fromisoformat(release['published_at'].replace('Z', '+00:00')),
                    tags=["github", "release", "changelog"],
                    metadata={
                        "repository": f"{owner}/{repo}",
                        "version": release['tag_name'],
                        "prerelease": release['prerelease']
                    }
                )
                results.append(release_item)
        
        # Capture recent issues (open and notable closed ones)
        issues = self._make_github_request(f"https://api.github.com/repos/{owner}/{repo}/issues", 
                                         {"state": "all", "per_page": 20, "sort": "updated"})
        if issues:
            for issue in issues:
                if 'pull_request' in issue:  # Skip PRs, handle them separately
                    continue
                    
                issue_item = GitHubContent(
                    id=f"github_issue_{issue['id']}",
                    title=f"Issue #{issue['number']}: {issue['title']}",
                    content=f"# {issue['title']}\n\n{issue.get('body', '')}",
                    url=issue['html_url'],
                    type="issue",
                    author=issue['user']['login'],
                    created_at=datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00')),
                    updated_at=datetime.fromisoformat(issue['updated_at'].replace('Z', '+00:00')),
                    tags=["github", "issue", issue['state']] + [label['name'] for label in issue.get('labels', [])],
                    metadata={
                        "repository": f"{owner}/{repo}",
                        "number": issue['number'],
                        "state": issue['state'],
                        "comments": issue['comments']
                    }
                )
                results.append(issue_item)
        
        return results
    
    def _capture_gitlab_repository(self, project_path: str, user_id: int) -> List[GitHubContent]:
        """Capture GitLab repository content"""
        results = []
        
        # URL encode project path
        encoded_path = project_path.replace("/", "%2F")
        
        # Get project info
        project_data = self._make_gitlab_request(f"{self.gitlab_instance}/api/v4/projects/{encoded_path}")
        if not project_data:
            return results
        
        # Project overview
        project_content = GitHubContent(
            id=f"gitlab_project_{project_data['id']}",
            title=f"{project_data['name']} - {project_data.get('description', 'Project')}",
            content=self._format_project_overview(project_data),
            url=project_data['web_url'],
            type="repository",
            author=project_data['namespace']['name'],
            created_at=datetime.fromisoformat(project_data['created_at'].replace('Z', '+00:00')),
            updated_at=datetime.fromisoformat(project_data['last_activity_at'].replace('Z', '+00:00')),
            tags=["gitlab", "project"] + project_data.get('topics', []),
            metadata={
                "stars": project_data['star_count'],
                "forks": project_data['forks_count'],
                "visibility": project_data['visibility']
            }
        )
        results.append(project_content)
        
        return results
    
    def capture_user_repositories(self, username: str, user_id: int, platform: str = "github", limit: int = 10) -> List[GitHubContent]:
        """Capture user's repositories"""
        results = []
        
        if platform == "github":
            repos = self._make_github_request(f"https://api.github.com/users/{username}/repos", 
                                            {"per_page": limit, "sort": "updated"})
            if repos:
                for repo in repos:
                    results.extend(self._capture_github_repository(repo['owner']['login'], repo['name'], user_id))
        
        return results
    
    def capture_starred_repositories(self, username: str, user_id: int, limit: int = 20) -> List[GitHubContent]:
        """Capture user's starred repositories"""
        results = []
        
        starred = self._make_github_request(f"https://api.github.com/users/{username}/starred", {"per_page": limit})
        if starred:
            for repo in starred:
                starred_item = GitHubContent(
                    id=f"github_starred_{repo['id']}",
                    title=f"⭐ {repo['full_name']} - {repo.get('description', '')}",
                    content=self._format_repository_overview(repo),
                    url=repo['html_url'],
                    type="starred_repository",
                    author=repo['owner']['login'],
                    created_at=datetime.fromisoformat(repo['created_at'].replace('Z', '+00:00')),
                    updated_at=datetime.fromisoformat(repo['updated_at'].replace('Z', '+00:00')),
                    tags=["github", "starred", repo['language']] + repo.get('topics', []),
                    metadata={
                        "stars": repo['stargazers_count'],
                        "forks": repo['forks_count'],
                        "language": repo['language']
                    }
                )
                results.append(starred_item)
        
        return results
    
    def capture_gists(self, username: str, user_id: int, limit: int = 10) -> List[GitHubContent]:
        """Capture user's gists"""
        results = []
        
        gists = self._make_github_request(f"https://api.github.com/users/{username}/gists", {"per_page": limit})
        if gists:
            for gist in gists:
                # Get gist content
                gist_detail = self._make_github_request(gist['url'])
                if gist_detail:
                    files_content = []
                    for filename, file_info in gist_detail['files'].items():
                        files_content.append(f"## {filename}\n\n```{file_info.get('language', '').lower()}\n{file_info['content']}\n```")
                    
                    gist_item = GitHubContent(
                        id=f"github_gist_{gist['id']}",
                        title=f"Gist: {gist.get('description') or list(gist['files'].keys())[0]}",
                        content="\n\n".join(files_content),
                        url=gist['html_url'],
                        type="gist",
                        author=gist['owner']['login'],
                        created_at=datetime.fromisoformat(gist['created_at'].replace('Z', '+00:00')),
                        updated_at=datetime.fromisoformat(gist['updated_at'].replace('Z', '+00:00')),
                        tags=["github", "gist", "code"],
                        metadata={
                            "files": list(gist['files'].keys()),
                            "public": gist['public'],
                            "comments": gist['comments']
                        }
                    )
                    results.append(gist_item)
        
        return results
    
    def _format_repository_overview(self, repo_data: Dict[str, Any]) -> str:
        """Format repository data into readable content"""
        content = f"# {repo_data['full_name']}\n\n"
        
        if repo_data.get('description'):
            content += f"{repo_data['description']}\n\n"
        
        content += f"**Language:** {repo_data.get('language', 'Not specified')}\n"
        content += f"**Stars:** {repo_data['stargazers_count']}\n"
        content += f"**Forks:** {repo_data['forks_count']}\n"
        content += f"**Created:** {repo_data['created_at']}\n"
        content += f"**Updated:** {repo_data['updated_at']}\n\n"
        
        if repo_data.get('topics'):
            content += f"**Topics:** {', '.join(repo_data['topics'])}\n\n"
        
        if repo_data.get('license'):
            content += f"**License:** {repo_data['license']['name']}\n\n"
        
        content += f"**Repository URL:** {repo_data['html_url']}\n"
        
        return content
    
    def _format_project_overview(self, project_data: Dict[str, Any]) -> str:
        """Format GitLab project data into readable content"""
        content = f"# {project_data['name_with_namespace']}\n\n"
        
        if project_data.get('description'):
            content += f"{project_data['description']}\n\n"
        
        content += f"**Visibility:** {project_data['visibility']}\n"
        content += f"**Stars:** {project_data['star_count']}\n"
        content += f"**Forks:** {project_data['forks_count']}\n"
        content += f"**Created:** {project_data['created_at']}\n"
        content += f"**Last Activity:** {project_data['last_activity_at']}\n\n"
        
        if project_data.get('topics'):
            content += f"**Topics:** {', '.join(project_data['topics'])}\n\n"
        
        content += f"**Project URL:** {project_data['web_url']}\n"
        
        return content
    
    def save_content_to_notes(self, contents: List[GitHubContent], user_id: int) -> List[int]:
        """Save captured content as notes in the database"""
        conn = self.get_conn()
        cursor = conn.cursor()
        note_ids = []
        
        try:
            for content in contents:
                # Check if content already exists
                cursor.execute(
                    "SELECT id FROM notes WHERE user_id = ? AND external_id = ?",
                    (user_id, content.id)
                )
                
                existing = cursor.fetchone()
                if existing:
                    # Update existing note
                    cursor.execute("""
                        UPDATE notes 
                        SET title = ?, content = ?, tags = ?, updated_at = CURRENT_TIMESTAMP,
                            metadata = ?
                        WHERE id = ? AND user_id = ?
                    """, (
                        content.title,
                        content.content,
                        ", ".join(content.tags),
                        json.dumps(content.metadata),
                        existing[0],
                        user_id
                    ))
                    note_ids.append(existing[0])
                else:
                    # Create new note
                    cursor.execute("""
                        INSERT INTO notes (user_id, title, content, tags, file_type, status, 
                                         external_id, external_url, metadata, created_at)
                        VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        user_id,
                        content.title,
                        content.content,
                        ", ".join(content.tags),
                        content.type,
                        content.id,
                        content.url,
                        json.dumps(content.metadata)
                    ))
                    note_ids.append(cursor.lastrowid)
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            print(f"Error saving content to notes: {e}")
            raise
        
        return note_ids
    
    def get_integration_stats(self, user_id: int) -> Dict[str, Any]:
        """Get GitHub/GitLab integration statistics"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        try:
            # Count notes by source
            cursor.execute("""
                SELECT file_type, COUNT(*) 
                FROM notes 
                WHERE user_id = ? AND external_id LIKE 'github_%' OR external_id LIKE 'gitlab_%'
                GROUP BY file_type
            """, (user_id,))
            
            type_counts = dict(cursor.fetchall())
            
            # Recent captures
            cursor.execute("""
                SELECT COUNT(*) 
                FROM notes 
                WHERE user_id = ? AND (external_id LIKE 'github_%' OR external_id LIKE 'gitlab_%')
                  AND created_at >= datetime('now', '-7 days')
            """, (user_id,))
            
            recent_captures = cursor.fetchone()[0]
            
            return {
                "total_captured_content": sum(type_counts.values()),
                "content_by_type": type_counts,
                "recent_captures_7_days": recent_captures,
                "supported_platforms": ["GitHub", "GitLab"],
                "capture_types": [
                    "repositories", "issues", "pull_requests", "gists", 
                    "releases", "documentation", "starred_repos"
                ]
            }
            
        except Exception as e:
            return {"error": str(e)}

print("[GitHub Integration Service] Loaded successfully")