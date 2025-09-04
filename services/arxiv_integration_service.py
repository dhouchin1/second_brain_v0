"""
ArXiv Research Paper Integration Service

Provides integration with ArXiv API to automatically capture:
- Research papers with abstracts and metadata
- Author information and citations
- Categories and subject classifications
- PDF content extraction and processing
- Search and discovery of relevant papers
"""

import json
import requests
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass
from urllib.parse import quote_plus
import re
import time

@dataclass
class ArXivPaper:
    id: str
    title: str
    abstract: str
    authors: List[str]
    categories: List[str]
    published: datetime
    updated: datetime
    pdf_url: str
    arxiv_url: str
    primary_category: str
    tags: List[str]
    metadata: Dict[str, Any]

class ArXivIntegrationService:
    def __init__(self, get_conn: Callable[[], sqlite3.Connection]):
        self.get_conn = get_conn
        self.base_url = "http://export.arxiv.org/api/query"
        self.rate_limit_delay = 3  # ArXiv requests 3 second delay between requests
        self.last_request_time = 0
        
    def _rate_limit(self):
        """Enforce ArXiv API rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            print(f"Rate limiting: waiting {sleep_time:.1f} seconds")
            time.sleep(sleep_time)
        self.last_request_time = time.time()
    
    def _make_arxiv_request(self, params: Dict[str, Any]) -> Optional[str]:
        """Make request to ArXiv API with rate limiting"""
        self._rate_limit()
        
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            if response.status_code == 200:
                return response.text
            else:
                print(f"ArXiv API error {response.status_code}: {response.text}")
                return None
        except Exception as e:
            print(f"ArXiv API request failed: {e}")
            return None
    
    def _parse_arxiv_response(self, xml_content: str) -> List[ArXivPaper]:
        """Parse ArXiv API XML response into ArXivPaper objects"""
        papers = []
        
        try:
            root = ET.fromstring(xml_content)
            
            # Define namespaces
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            # Find all entry elements (papers)
            entries = root.findall('atom:entry', namespaces)
            
            for entry in entries:
                try:
                    # Extract basic information
                    id_elem = entry.find('atom:id', namespaces)
                    arxiv_id = id_elem.text.split('/')[-1] if id_elem is not None else ""
                    
                    title_elem = entry.find('atom:title', namespaces)
                    title = title_elem.text.strip() if title_elem is not None else ""
                    
                    summary_elem = entry.find('atom:summary', namespaces)
                    abstract = summary_elem.text.strip() if summary_elem is not None else ""
                    
                    # Extract authors
                    authors = []
                    for author in entry.findall('atom:author', namespaces):
                        name_elem = author.find('atom:name', namespaces)
                        if name_elem is not None:
                            authors.append(name_elem.text.strip())
                    
                    # Extract categories
                    categories = []
                    primary_category = ""
                    
                    primary_cat_elem = entry.find('arxiv:primary_category', namespaces)
                    if primary_cat_elem is not None:
                        primary_category = primary_cat_elem.get('term', '')
                        categories.append(primary_category)
                    
                    for category in entry.findall('atom:category', namespaces):
                        cat_term = category.get('term', '')
                        if cat_term and cat_term not in categories:
                            categories.append(cat_term)
                    
                    # Extract dates
                    published_elem = entry.find('atom:published', namespaces)
                    published = datetime.fromisoformat(published_elem.text.replace('Z', '+00:00')) if published_elem is not None else datetime.now()
                    
                    updated_elem = entry.find('atom:updated', namespaces)
                    updated = datetime.fromisoformat(updated_elem.text.replace('Z', '+00:00')) if updated_elem is not None else published
                    
                    # Extract links (PDF and ArXiv page)
                    pdf_url = ""
                    arxiv_url = ""
                    
                    for link in entry.findall('atom:link', namespaces):
                        rel = link.get('rel', '')
                        href = link.get('href', '')
                        link_type = link.get('type', '')
                        
                        if link_type == 'application/pdf':
                            pdf_url = href
                        elif rel == 'alternate':
                            arxiv_url = href
                    
                    # Generate tags
                    tags = ['arxiv', 'research', 'paper'] + categories
                    if authors:
                        tags.append('academic')
                    
                    # Create metadata
                    metadata = {
                        'arxiv_id': arxiv_id,
                        'author_count': len(authors),
                        'category_count': len(categories),
                        'word_count_estimate': len(abstract.split()),
                        'submission_date': published.isoformat(),
                        'last_updated': updated.isoformat()
                    }
                    
                    # Create ArXivPaper object
                    paper = ArXivPaper(
                        id=f"arxiv_{arxiv_id.replace(':', '_').replace('.', '_')}",
                        title=title,
                        abstract=abstract,
                        authors=authors,
                        categories=categories,
                        published=published,
                        updated=updated,
                        pdf_url=pdf_url,
                        arxiv_url=arxiv_url,
                        primary_category=primary_category,
                        tags=tags,
                        metadata=metadata
                    )
                    
                    papers.append(paper)
                    
                except Exception as e:
                    print(f"Error parsing ArXiv entry: {e}")
                    continue
            
        except Exception as e:
            print(f"Error parsing ArXiv XML response: {e}")
        
        return papers
    
    def search_papers(self, query: str, max_results: int = 20, category: Optional[str] = None) -> List[ArXivPaper]:
        """Search for papers by query string"""
        # Build search query
        search_query = f"all:{query}"
        
        if category:
            search_query += f" AND cat:{category}"
        
        params = {
            'search_query': search_query,
            'start': 0,
            'max_results': max_results,
            'sortBy': 'relevance',
            'sortOrder': 'descending'
        }
        
        xml_response = self._make_arxiv_request(params)
        if xml_response:
            return self._parse_arxiv_response(xml_response)
        return []
    
    def get_papers_by_author(self, author: str, max_results: int = 10) -> List[ArXivPaper]:
        """Get papers by a specific author"""
        params = {
            'search_query': f'au:"{author}"',
            'start': 0,
            'max_results': max_results,
            'sortBy': 'submittedDate',
            'sortOrder': 'descending'
        }
        
        xml_response = self._make_arxiv_request(params)
        if xml_response:
            return self._parse_arxiv_response(xml_response)
        return []
    
    def get_papers_by_category(self, category: str, max_results: int = 20) -> List[ArXivPaper]:
        """Get recent papers from a specific category"""
        params = {
            'search_query': f'cat:{category}',
            'start': 0,
            'max_results': max_results,
            'sortBy': 'submittedDate',
            'sortOrder': 'descending'
        }
        
        xml_response = self._make_arxiv_request(params)
        if xml_response:
            return self._parse_arxiv_response(xml_response)
        return []
    
    def get_recent_papers(self, days: int = 7, categories: Optional[List[str]] = None, max_results: int = 50) -> List[ArXivPaper]:
        """Get papers submitted in the last N days"""
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Format dates for ArXiv API
        start_str = start_date.strftime("%Y%m%d%H%M")
        end_str = end_date.strftime("%Y%m%d%H%M")
        
        # Build query
        search_query = f"submittedDate:[{start_str} TO {end_str}]"
        
        if categories:
            category_query = " OR ".join([f"cat:{cat}" for cat in categories])
            search_query += f" AND ({category_query})"
        
        params = {
            'search_query': search_query,
            'start': 0,
            'max_results': max_results,
            'sortBy': 'submittedDate',
            'sortOrder': 'descending'
        }
        
        xml_response = self._make_arxiv_request(params)
        if xml_response:
            return self._parse_arxiv_response(xml_response)
        return []
    
    def get_paper_by_id(self, arxiv_id: str) -> Optional[ArXivPaper]:
        """Get a specific paper by ArXiv ID"""
        params = {
            'id_list': arxiv_id
        }
        
        xml_response = self._make_arxiv_request(params)
        if xml_response:
            papers = self._parse_arxiv_response(xml_response)
            return papers[0] if papers else None
        return None
    
    def discover_papers_by_keywords(self, keywords: List[str], max_results: int = 30) -> List[ArXivPaper]:
        """Discover papers using multiple keywords with OR logic"""
        keyword_query = " OR ".join([f'all:"{keyword}"' for keyword in keywords])
        
        params = {
            'search_query': keyword_query,
            'start': 0,
            'max_results': max_results,
            'sortBy': 'relevance',
            'sortOrder': 'descending'
        }
        
        xml_response = self._make_arxiv_request(params)
        if xml_response:
            return self._parse_arxiv_response(xml_response)
        return []
    
    def get_trending_papers(self, category: Optional[str] = None, days: int = 30) -> List[ArXivPaper]:
        """Get trending papers (recent papers with good relevance scores)"""
        # Get recent papers and sort by a combination of recency and relevance
        recent_papers = self.get_recent_papers(days=days, max_results=100)
        
        if category:
            recent_papers = [p for p in recent_papers if category in p.categories]
        
        # Simple trending score: newer papers get higher scores
        for paper in recent_papers:
            days_old = (datetime.now() - paper.published.replace(tzinfo=None)).days
            paper.metadata['trending_score'] = max(0, 30 - days_old) + len(paper.authors)
        
        # Sort by trending score
        recent_papers.sort(key=lambda p: p.metadata.get('trending_score', 0), reverse=True)
        
        return recent_papers[:20]
    
    def save_papers_to_notes(self, papers: List[ArXivPaper], user_id: int) -> List[int]:
        """Save ArXiv papers as notes in the database"""
        conn = self.get_conn()
        cursor = conn.cursor()
        note_ids = []
        
        try:
            for paper in papers:
                # Check if paper already exists
                cursor.execute(
                    "SELECT id FROM notes WHERE user_id = ? AND external_id = ?",
                    (user_id, paper.id)
                )
                
                existing = cursor.fetchone()
                
                # Create note content
                content = self._format_paper_content(paper)
                tags_str = ", ".join(paper.tags)
                
                if existing:
                    # Update existing note
                    cursor.execute("""
                        UPDATE notes 
                        SET title = ?, content = ?, tags = ?, updated_at = CURRENT_TIMESTAMP,
                            metadata = ?
                        WHERE id = ? AND user_id = ?
                    """, (
                        paper.title,
                        content,
                        tags_str,
                        json.dumps(paper.metadata),
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
                        paper.title,
                        content,
                        tags_str,
                        'research_paper',
                        paper.id,
                        paper.arxiv_url,
                        json.dumps(paper.metadata)
                    ))
                    note_ids.append(cursor.lastrowid)
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            print(f"Error saving papers to notes: {e}")
            raise
        
        return note_ids
    
    def _format_paper_content(self, paper: ArXivPaper) -> str:
        """Format ArXiv paper data into readable note content"""
        content = f"# {paper.title}\n\n"
        
        # Authors
        if paper.authors:
            if len(paper.authors) == 1:
                content += f"**Author:** {paper.authors[0]}\n"
            else:
                content += f"**Authors:** {', '.join(paper.authors)}\n"
        
        # Categories
        content += f"**Primary Category:** {paper.primary_category}\n"
        if len(paper.categories) > 1:
            content += f"**Categories:** {', '.join(paper.categories)}\n"
        
        # Dates
        content += f"**Published:** {paper.published.strftime('%Y-%m-%d')}\n"
        if paper.updated != paper.published:
            content += f"**Updated:** {paper.updated.strftime('%Y-%m-%d')}\n"
        
        # Links
        content += f"**ArXiv:** [{paper.arxiv_url}]({paper.arxiv_url})\n"
        if paper.pdf_url:
            content += f"**PDF:** [{paper.pdf_url}]({paper.pdf_url})\n"
        
        content += "\n## Abstract\n\n"
        content += paper.abstract + "\n\n"
        
        # ArXiv ID for reference
        content += f"**ArXiv ID:** {paper.metadata.get('arxiv_id', '')}\n"
        
        return content
    
    def get_arxiv_categories(self) -> Dict[str, str]:
        """Get available ArXiv categories with descriptions"""
        return {
            # Computer Science
            'cs.AI': 'Artificial Intelligence',
            'cs.CL': 'Computation and Language (NLP)',
            'cs.CV': 'Computer Vision and Pattern Recognition',
            'cs.LG': 'Machine Learning',
            'cs.NE': 'Neural and Evolutionary Computing',
            'cs.RO': 'Robotics',
            'cs.DS': 'Data Structures and Algorithms',
            'cs.CR': 'Cryptography and Security',
            'cs.DB': 'Databases',
            'cs.DC': 'Distributed Computing',
            'cs.SE': 'Software Engineering',
            'cs.SY': 'Systems and Control',
            
            # Physics
            'physics.app-ph': 'Applied Physics',
            'physics.comp-ph': 'Computational Physics',
            'physics.data-an': 'Data Analysis, Statistics and Probability',
            'cond-mat.mtrl-sci': 'Materials Science',
            'quant-ph': 'Quantum Physics',
            'hep-th': 'High Energy Physics - Theory',
            'astro-ph': 'Astrophysics',
            
            # Mathematics
            'math.NA': 'Numerical Analysis',
            'math.OC': 'Optimization and Control',
            'math.PR': 'Probability',
            'math.ST': 'Statistics Theory',
            'stat.ML': 'Statistics - Machine Learning',
            
            # Biology
            'q-bio.BM': 'Biomolecules',
            'q-bio.GN': 'Genomics',
            'q-bio.NC': 'Neurons and Cognition',
            'q-bio.QM': 'Quantitative Methods',
            
            # Economics and Finance
            'econ.EM': 'Econometrics',
            'q-fin.CP': 'Computational Finance',
            'q-fin.RM': 'Risk Management'
        }
    
    def get_integration_stats(self, user_id: int) -> Dict[str, Any]:
        """Get ArXiv integration statistics"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        try:
            # Count ArXiv papers by category
            cursor.execute("""
                SELECT json_extract(metadata, '$.primary_category') as category, COUNT(*) 
                FROM notes 
                WHERE user_id = ? AND external_id LIKE 'arxiv_%' AND file_type = 'research_paper'
                GROUP BY category
            """, (user_id,))
            
            category_counts = dict(cursor.fetchall())
            
            # Total papers
            cursor.execute("""
                SELECT COUNT(*) 
                FROM notes 
                WHERE user_id = ? AND external_id LIKE 'arxiv_%' AND file_type = 'research_paper'
            """, (user_id,))
            
            total_papers = cursor.fetchone()[0]
            
            # Recent papers (last 7 days)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM notes 
                WHERE user_id = ? AND external_id LIKE 'arxiv_%' AND file_type = 'research_paper'
                  AND created_at >= datetime('now', '-7 days')
            """, (user_id,))
            
            recent_papers = cursor.fetchone()[0]
            
            # Author count (approximate from metadata)
            cursor.execute("""
                SELECT AVG(json_extract(metadata, '$.author_count')) 
                FROM notes 
                WHERE user_id = ? AND external_id LIKE 'arxiv_%' AND file_type = 'research_paper'
            """, (user_id,))
            
            avg_authors = cursor.fetchone()[0] or 0
            
            return {
                "total_papers": total_papers,
                "papers_by_category": category_counts,
                "recent_papers_7_days": recent_papers,
                "average_authors_per_paper": round(avg_authors, 1),
                "supported_categories": len(self.get_arxiv_categories()),
                "data_source": "ArXiv.org"
            }
            
        except Exception as e:
            return {"error": str(e)}

print("[ArXiv Integration Service] Loaded successfully")