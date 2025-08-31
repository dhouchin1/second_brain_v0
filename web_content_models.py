#!/usr/bin/env python3
"""
Data models for web content in Second Brain
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from enum import Enum

class WebContentType(Enum):
    """Types of web content"""
    ARTICLE = "article"
    BLOG_POST = "blog_post"
    DOCUMENTATION = "documentation"
    SOCIAL_MEDIA = "social_media"
    NEWS = "news"
    ACADEMIC = "academic"
    PRODUCT_PAGE = "product_page"
    FORUM_POST = "forum_post"
    VIDEO_PAGE = "video_page"
    UNKNOWN = "unknown"

class ExtractionStatus(Enum):
    """Status of web content extraction"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"

@dataclass
class WebMetadata:
    """Metadata extracted from web content"""
    # Basic info
    url: str
    canonical_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    
    # Content info
    author: Optional[str] = None
    publish_date: Optional[str] = None
    keywords: Optional[str] = None
    language: Optional[str] = None
    
    # Open Graph data
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    og_type: Optional[str] = None
    og_site_name: Optional[str] = None
    
    # Twitter card data
    twitter_title: Optional[str] = None
    twitter_description: Optional[str] = None
    twitter_image: Optional[str] = None
    twitter_card: Optional[str] = None
    
    # Technical info
    content_type: Optional[str] = None
    charset: Optional[str] = None
    robots: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, filtering None values"""
        return {k: v for k, v in asdict(self).items() if v is not None}

@dataclass
class WebExtractionResult:
    """Result of web content extraction"""
    # Source info
    url: str
    original_text: str  # Original text containing the URL
    
    # Extraction results
    success: bool
    status: ExtractionStatus
    error_message: Optional[str] = None
    
    # Extracted content
    title: Optional[str] = None
    content: Optional[str] = None  # Main article content
    html: Optional[str] = None     # Raw HTML
    text_content: Optional[str] = None  # Plain text version
    
    # Metadata
    metadata: Optional[WebMetadata] = None
    content_type: WebContentType = WebContentType.UNKNOWN
    
    # Media
    screenshot_path: Optional[str] = None
    images: List[str] = None  # List of image URLs
    
    # Performance
    extraction_time_seconds: float = 0.0
    content_length: int = 0
    
    # Hashing for deduplication
    content_hash: Optional[str] = None
    url_hash: Optional[str] = None
    
    def __post_init__(self):
        if self.images is None:
            self.images = []
        
        # Calculate content length
        if self.content:
            self.content_length = len(self.content)
        
        # Generate hashes
        if self.url:
            import hashlib
            self.url_hash = hashlib.md5(self.url.encode()).hexdigest()
        
        if self.content:
            import hashlib
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        
        # Convert enums to strings
        result['status'] = self.status.value
        result['content_type'] = self.content_type.value
        
        # Convert metadata
        if self.metadata:
            result['metadata'] = self.metadata.to_dict()
        
        return result
    
    def get_best_title(self) -> str:
        """Get the best available title"""
        if self.title:
            return self.title
        if self.metadata and self.metadata.og_title:
            return self.metadata.og_title
        if self.metadata and self.metadata.twitter_title:
            return self.metadata.twitter_title
        if self.metadata and self.metadata.title:
            return self.metadata.title
        
        # Fallback to URL-based title
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        domain = parsed.netloc.replace('www.', '')
        return f"Web content from {domain}"
    
    def get_best_description(self) -> str:
        """Get the best available description"""
        if self.metadata:
            if self.metadata.description:
                return self.metadata.description
            if self.metadata.og_description:
                return self.metadata.og_description
            if self.metadata.twitter_description:
                return self.metadata.twitter_description
        
        # Fallback to content excerpt
        if self.text_content:
            # Get first paragraph or 200 characters
            lines = self.text_content.split('\n')
            for line in lines:
                line = line.strip()
                if len(line) > 50:  # Substantial content
                    return line[:200] + "..." if len(line) > 200 else line
        
        return f"Web content from {self.url}"
    
    def get_tags(self) -> List[str]:
        """Extract potential tags from content"""
        tags = []
        
        # From metadata keywords
        if self.metadata and self.metadata.keywords:
            keywords = self.metadata.keywords.split(',')
            tags.extend([k.strip().lower() for k in keywords if k.strip()])
        
        # From URL path
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        path_parts = [p for p in parsed.path.split('/') if p and not p.isdigit()]
        tags.extend([p.replace('-', ' ').replace('_', ' ') for p in path_parts[:3]])
        
        # From domain
        domain = parsed.netloc.replace('www.', '')
        if domain:
            tags.append(domain.split('.')[0])
        
        # Add web content tag
        tags.append('web-content')
        tags.append(self.content_type.value.replace('_', '-'))
        
        # Clean and deduplicate
        tags = [tag.strip().lower() for tag in tags if tag.strip()]
        tags = list(dict.fromkeys(tags))  # Remove duplicates while preserving order
        
        return tags[:10]  # Limit to 10 tags
    
    def is_substantial_content(self) -> bool:
        """Check if this represents substantial content worth saving"""
        if not self.success or not self.content:
            return False
        
        # Check content length
        if len(self.content) < 100:  # Less than 100 characters
            return False
        
        # Check if it's mostly navigation/boilerplate
        if self.text_content:
            words = self.text_content.split()
            if len(words) < 20:  # Less than 20 words
                return False
        
        return True

@dataclass  
class WebContentCache:
    """Cache entry for web content to avoid re-extraction"""
    url: str
    url_hash: str
    content_hash: str
    extraction_result: WebExtractionResult
    cached_at: str  # ISO timestamp
    access_count: int = 0
    last_accessed: Optional[str] = None  # ISO timestamp
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'url': self.url,
            'url_hash': self.url_hash, 
            'content_hash': self.content_hash,
            'extraction_result': self.extraction_result.to_dict(),
            'cached_at': self.cached_at,
            'access_count': self.access_count,
            'last_accessed': self.last_accessed
        }
