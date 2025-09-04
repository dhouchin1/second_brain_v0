#!/usr/bin/env python3
"""
URL Detection and Validation Utilities for Second Brain Web Ingestion
"""

import re
import logging
from typing import List, Optional, Tuple
from urllib.parse import urlparse
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class URLInfo:
    """Information extracted from a URL"""
    url: str
    scheme: str
    domain: str
    path: str
    is_valid: bool
    is_social_media: bool
    content_type_hint: str
    confidence_score: float

class URLDetector:
    """Detect and validate URLs in text input"""
    
    # Comprehensive URL regex pattern
    URL_PATTERN = re.compile(
        r'''
        (?i)\b
        (?:
            # Standard HTTP/HTTPS URLs
            (?:https?://)
            |
            # URLs without protocol (www. prefix)
            (?:www\.)
        )
        (?:
            # Domain part
            (?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+
            [a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?
        )
        (?:
            # Port
            :[0-9]{1,5}
        )?
        (?:
            # Path, query, fragment
            /[^\s<>"']*
        )?
        ''', re.VERBOSE | re.IGNORECASE
    )
    
    # Social media domains
    SOCIAL_MEDIA_DOMAINS = {
        'twitter.com', 'x.com', 'facebook.com', 'instagram.com', 'linkedin.com',
        'tiktok.com', 'youtube.com', 'reddit.com', 'pinterest.com', 'snapchat.com',
        'discord.com', 'telegram.org', 'whatsapp.com', 'medium.com'
    }
    
    # Domains likely to have rich content
    RICH_CONTENT_DOMAINS = {
        'github.com', 'stackoverflow.com', 'arxiv.org', 'wikipedia.org',
        'docs.python.org', 'developer.mozilla.org', 'blog.', 'medium.com',
        'substack.com', 'notion.so', 'airtable.com', 'figma.com'
    }
    
    # File extension hints
    DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.txt', '.md', '.html', '.htm'}
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}
    VIDEO_EXTENSIONS = {'.mp4', '.webm', '.avi', '.mov', '.wmv'}
    
    def __init__(self):
        self.blocked_domains = set()  # Can be configured to block certain domains
        self.max_url_length = 2048   # RFC 2616 recommendation
    
    def detect_urls(self, text: str) -> List[URLInfo]:
        """
        Detect and analyze URLs in the given text
        
        Args:
            text: Input text to scan for URLs
            
        Returns:
            List of URLInfo objects with detected URLs and metadata
        """
        if not text or len(text.strip()) == 0:
            return []
        
        urls = []
        matches = self.URL_PATTERN.finditer(text)
        
        for match in matches:
            raw_url = match.group(0).strip()
            
            # Clean up the URL
            clean_url = self._clean_url(raw_url)
            
            if clean_url and len(clean_url) <= self.max_url_length:
                url_info = self._analyze_url(clean_url)
                if url_info.is_valid:
                    urls.append(url_info)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url_info in urls:
            if url_info.url not in seen:
                seen.add(url_info.url)
                unique_urls.append(url_info)
        
        return unique_urls
    
    def _clean_url(self, raw_url: str) -> Optional[str]:
        """Clean and normalize a raw URL"""
        if not raw_url:
            return None
        
        # Remove common trailing punctuation
        url = raw_url.rstrip('.,;:!?)"\'')
        
        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            if url.startswith('www.'):
                url = 'https://' + url
            else:
                # Check if it looks like a domain
                if '.' in url and not url.startswith(('.', '/')):
                    url = 'https://' + url
        
        return url
    
    def _analyze_url(self, url: str) -> URLInfo:
        """Analyze a URL and extract metadata"""
        try:
            parsed = urlparse(url)
            
            # Basic validation
            if not parsed.netloc or not parsed.scheme:
                return URLInfo(
                    url=url, scheme='', domain='', path='', 
                    is_valid=False, is_social_media=False,
                    content_type_hint='invalid', confidence_score=0.0
                )
            
            domain = parsed.netloc.lower()
            
            # Remove www prefix for domain analysis
            domain_for_analysis = domain
            if domain_for_analysis.startswith('www.'):
                domain_for_analysis = domain_for_analysis[4:]
            
            # Check if blocked
            if domain_for_analysis in self.blocked_domains:
                return URLInfo(
                    url=url, scheme=parsed.scheme, domain=domain, path=parsed.path,
                    is_valid=False, is_social_media=False,
                    content_type_hint='blocked', confidence_score=0.0
                )
            
            # Analyze content type and confidence
            is_social_media = domain_for_analysis in self.SOCIAL_MEDIA_DOMAINS
            content_type_hint = self._get_content_type_hint(parsed, domain_for_analysis)
            confidence_score = self._calculate_confidence_score(parsed, domain_for_analysis)
            
            return URLInfo(
                url=url,
                scheme=parsed.scheme,
                domain=domain,
                path=parsed.path,
                is_valid=True,
                is_social_media=is_social_media,
                content_type_hint=content_type_hint,
                confidence_score=confidence_score
            )
            
        except Exception as e:
            logger.warning(f"Error analyzing URL {url}: {e}")
            return URLInfo(
                url=url, scheme='', domain='', path='',
                is_valid=False, is_social_media=False,
                content_type_hint='error', confidence_score=0.0
            )
    
    def _get_content_type_hint(self, parsed_url, domain: str) -> str:
        """Predict the likely content type of a URL"""
        path = parsed_url.path.lower()
        
        # Check file extension
        if any(path.endswith(ext) for ext in self.DOCUMENT_EXTENSIONS):
            return 'document'
        elif any(path.endswith(ext) for ext in self.IMAGE_EXTENSIONS):
            return 'image'
        elif any(path.endswith(ext) for ext in self.VIDEO_EXTENSIONS):
            return 'video'
        
        # Check domain patterns
        if domain in self.SOCIAL_MEDIA_DOMAINS:
            return 'social_media'
        elif domain in self.RICH_CONTENT_DOMAINS or 'blog' in domain:
            return 'article'
        elif 'github.com' in domain:
            if '/blob/' in path or path.endswith('.md'):
                return 'code_documentation'
            else:
                return 'code_repository'
        elif 'youtube.com' in domain or 'youtu.be' in domain:
            return 'video'
        elif 'stackoverflow.com' in domain:
            return 'qa_content'
        elif 'wikipedia.org' in domain:
            return 'encyclopedia'
        elif 'arxiv.org' in domain:
            return 'academic_paper'
        
        # Default for web pages
        return 'webpage'
    
    def _calculate_confidence_score(self, parsed_url, domain: str) -> float:
        """Calculate confidence score for successful extraction (0.0 to 1.0)"""
        score = 0.5  # Base score for valid URL
        
        # Boost for known good domains
        if domain in self.RICH_CONTENT_DOMAINS:
            score += 0.3
        elif domain.endswith(('.edu', '.gov', '.org')):
            score += 0.2
        elif 'blog' in domain or 'docs' in domain:
            score += 0.2
        
        # Boost for content indicators in path
        path = parsed_url.path.lower()
        if any(indicator in path for indicator in ['/article/', '/post/', '/blog/', '/doc/', '/guide/', '/tutorial/']):
            score += 0.1
        
        # Penalty for social media (harder to extract)
        if domain in self.SOCIAL_MEDIA_DOMAINS:
            score -= 0.2
        
        # Penalty for very short or very long paths
        if len(parsed_url.path) < 2:
            score -= 0.1
        elif len(parsed_url.path) > 200:
            score -= 0.1
        
        return max(0.0, min(1.0, score))
    
    def is_likely_extractable(self, url_info: URLInfo) -> bool:
        """Determine if a URL is likely to yield good content extraction"""
        if not url_info.is_valid:
            return False
        
        # High confidence URLs
        if url_info.confidence_score >= 0.7:
            return True
        
        # Medium confidence with good content type
        if (url_info.confidence_score >= 0.4 and 
            url_info.content_type_hint in ['article', 'webpage', 'documentation', 'academic_paper']):
            return True
        
        # Skip social media and low-confidence URLs
        if url_info.is_social_media or url_info.confidence_score < 0.3:
            return False
        
        return True
    
    def add_blocked_domain(self, domain: str):
        """Add a domain to the blocked list"""
        self.blocked_domains.add(domain.lower())
    
    def remove_blocked_domain(self, domain: str):
        """Remove a domain from the blocked list"""
        self.blocked_domains.discard(domain.lower())

def extract_main_urls(text: str) -> List[str]:
    """
    Simple function to extract main URLs from text
    
    Args:
        text: Input text
        
    Returns:
        List of clean URLs suitable for processing
    """
    detector = URLDetector()
    url_infos = detector.detect_urls(text)
    
    # Return only extractable URLs
    return [info.url for info in url_infos if detector.is_likely_extractable(info)]

def is_url_extractable(url: str) -> Tuple[bool, str]:
    """
    Check if a single URL is extractable
    
    Args:
        url: URL to check
        
    Returns:
        Tuple of (is_extractable: bool, reason: str)
    """
    detector = URLDetector()
    url_infos = detector.detect_urls(url)
    
    if not url_infos:
        return False, "No valid URL found"
    
    url_info = url_infos[0]  # Take first URL
    
    if not url_info.is_valid:
        return False, f"Invalid URL: {url_info.content_type_hint}"
    
    if detector.is_likely_extractable(url_info):
        return True, f"Extractable {url_info.content_type_hint} (confidence: {url_info.confidence_score:.2f})"
    else:
        return False, f"Low extraction confidence: {url_info.content_type_hint} ({url_info.confidence_score:.2f})"

# Configuration for different extraction strategies
EXTRACTION_CONFIG = {
    'article': {
        'timeout': 30,
        'wait_for': 'networkidle',
        'screenshot': True,
        'full_content': True
    },
    'social_media': {
        'timeout': 15, 
        'wait_for': 'domcontentloaded',
        'screenshot': True,
        'full_content': False
    },
    'code_repository': {
        'timeout': 20,
        'wait_for': 'networkidle',
        'screenshot': True,
        'full_content': True
    },
    'academic_paper': {
        'timeout': 45,
        'wait_for': 'networkidle',
        'screenshot': True,
        'full_content': True
    },
    'default': {
        'timeout': 25,
        'wait_for': 'networkidle',
        'screenshot': True,
        'full_content': True
    }
}
