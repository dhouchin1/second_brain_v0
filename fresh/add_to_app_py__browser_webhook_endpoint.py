# Add this to your app.py - Browser Extension Integration

from typing import Dict, Any
import json
import hashlib
import base64
from urllib.parse import urlparse

class BrowserCapture(BaseModel):
    note: str
    tags: str = ""
    type: str = "browser"
    metadata: Dict[str, Any] = {}

@app.post("/webhook/browser")
async def webhook_browser(
    data: BrowserCapture,
    current_user: User = Depends(get_current_user)
):
    """Enhanced browser capture endpoint with metadata processing"""
    
    # Extract metadata
    metadata = data.metadata
    url = metadata.get('url', '')
    title = metadata.get('title', '')
    capture_type = metadata.get('captureType', 'unknown')
    
    # Enhanced content processing
    content = data.note
    if capture_type == 'page':
        content = f"# {title}\n\nSource: {url}\n\n{content}"
    elif capture_type == 'selection':
        content = f"Selection from: {title}\nURL: {url}\n\n> {content}"
    elif capture_type == 'bookmark':
        content = f"# {title}\n\nURL: {url}\n\n{content}"
    
    # Process with AI
    result = ollama_summarize(content)
    summary = result.get("summary", "")
    ai_tags = result.get("tags", [])
    ai_actions = result.get("actions", [])
    
    # Enhanced tag generation
    tag_list = [t.strip() for t in data.tags.split(",") if t.strip()]
    tag_list.extend([t for t in ai_tags if t and t not in tag_list])
    
    # Add smart tags based on content and URL
    smart_tags = generate_smart_tags(content, url, metadata)
    tag_list.extend([t for t in smart_tags if t not in tag_list])
    
    tags = ",".join(tag_list)
    actions = "\n".join(ai_actions)
    
    # Generate title
    note_title = generate_browser_note_title(title, capture_type, content)
    
    # Save to database
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    c = conn.cursor()
    
    c.execute(
        """INSERT INTO notes 
           (title, content, summary, tags, actions, type, timestamp, user_id, metadata) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            note_title,
            content,
            summary,
            tags,
            actions,
            data.type,
            now,
            current_user.id,
            json.dumps(metadata)
        ),
    )
    
    conn.commit()
    note_id = c.lastrowid
    
    # Update FTS index
    c.execute(
        "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
        (note_id, note_title, summary, tags, actions, content),
    )
    
    conn.commit()
    conn.close()
    
    # Optional: Process screenshots or HTML archival
    if metadata.get('html') and capture_type == 'page':
        await save_html_archive(note_id, metadata['html'], url)
    
    return {
        "status": "ok", 
        "note_id": note_id,
        "title": note_title,
        "tags": tag_list,
        "summary": summary
    }

def generate_smart_tags(content: str, url: str, metadata: Dict) -> List[str]:
    """Generate intelligent tags based on content and context"""
    tags = []
    
    # Domain-based tags
    if url:
        try:
            domain = urlparse(url).netloc.replace('www.', '')
            tags.append(domain)
            
            # Special site handling
            if 'github.com' in domain:
                tags.extend(['code', 'development'])
            elif 'stackoverflow.com' in domain:
                tags.extend(['programming', 'qa'])
            elif 'medium.com' in domain or 'blog' in domain:
                tags.extend(['blog', 'article'])
            elif 'youtube.com' in domain:
                tags.extend(['video', 'tutorial'])
            elif 'twitter.com' in domain or 'x.com' in domain:
                tags.extend(['social', 'tweet'])
            elif 'reddit.com' in domain:
                tags.extend(['reddit', 'discussion'])
            elif 'arxiv.org' in domain:
                tags.extend(['research', 'paper'])
            elif 'wikipedia.org' in domain:
                tags.extend(['reference', 'wiki'])
                
        except Exception:
            pass
    
    # Content-based smart tagging
    content_lower = content.lower()
    
    # Technical content
    tech_keywords = {
        'python': ['python', 'programming'],
        'javascript': ['javascript', 'programming', 'web'],
        'react': ['react', 'frontend', 'javascript'],
        'api': ['api', 'development'],
        'docker': ['docker', 'devops'],
        'kubernetes': ['kubernetes', 'devops'],
        'machine learning': ['ml', 'ai'],
        'artificial intelligence': ['ai', 'technology'],
        'blockchain': ['blockchain', 'crypto'],
        'cybersecurity': ['security', 'infosec']
    }
    
    for keyword, related_tags in tech_keywords.items():
        if keyword in content_lower:
            tags.extend(related_tags)
    
    # Content type detection
    if any(word in content_lower for word in ['recipe', 'ingredients', 'cooking']):
        tags.extend(['recipe', 'cooking'])
    elif any(word in content_lower for word in ['workout', 'exercise', 'fitness']):
        tags.extend(['fitness', 'health'])
    elif any(word in content_lower for word in ['tutorial', 'how to', 'guide']):
        tags.extend(['tutorial', 'howto'])
    elif any(word in content_lower for word in ['news', 'breaking', 'report']):
        tags.extend(['news', 'current-events'])
    elif any(word in content_lower for word in ['research', 'study', 'analysis']):
        tags.extend(['research', 'academic'])
    
    # Remove duplicates and return
    return list(set(tags))

def generate_browser_note_title(page_title: str, capture_type: str, content: str) -> str:
    """Generate meaningful titles for browser captures"""
    
    if capture_type == 'selection':
        # Use first few words of selection
        words = content.split()[:8]
        title = ' '.join(words)
        if len(content.split()) > 8:
            title += '...'
        return f"Selection: {title}"
    
    elif capture_type == 'bookmark':
        return f"Bookmark: {page_title}"
    
    elif capture_type == 'page':
        return page_title or "Web Page"
    
    elif capture_type == 'manual':
        # Extract first sentence or line
        first_line = content.split('\n')[0][:60]
        return first_line if first_line else "Manual Note"
    
    else:
        return page_title or "Web Capture"

async def save_html_archive(note_id: int, html_content: str, url: str):
    """Save HTML content for archival (optional feature)"""
    try:
        archive_dir = settings.base_dir / "archives"
        archive_dir.mkdir(exist_ok=True)
        
        # Create filename from note ID and URL hash
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        filename = f"note_{note_id}_{url_hash}.html"
        
        # Save HTML with basic metadata
        html_with_meta = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Archived from {url}</title>
    <meta name="original-url" content="{url}">
    <meta name="archived-date" content="{datetime.now().isoformat()}">
    <meta name="second-brain-note-id" content="{note_id}">
    <style>
        .second-brain-archive-header {{
            background: #f3f4f6;
            padding: 1rem;
            border-bottom: 1px solid #d1d5db;
            font-family: system-ui, -apple-system, sans-serif;
        }}
    </style>
</head>
<body>
    <div class="second-brain-archive-header">
        <p><strong>Archived from:</strong> <a href="{url}">{url}</a></p>
        <p><strong>Saved on:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Second Brain Note ID:</strong> {note_id}</p>
    </div>
    {html_content}
</body>
</html>
"""
        
        archive_path = archive_dir / filename
        archive_path.write_text(html_with_meta, encoding='utf-8')
        
        # Update note metadata to include archive path
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE notes SET archive_path = ? WHERE id = ?",
            (str(archive_path), note_id)
        )
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Failed to save HTML archive: {e}")

# Add recent captures endpoint for extension
@app.get("/api/captures/recent")
async def get_recent_captures(
    limit: int = Query(10, le=50),
    type: str = Query(None),
    current_user: User = Depends(get_current_user)
):
    """Get recent captures for the browser extension"""
    conn = get_conn()
    c = conn.cursor()
    
    query = "SELECT * FROM notes WHERE user_id = ?"
    params = [current_user.id]
    
    if type:
        query += " AND type = ?"
        params.append(type)
    
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    rows = c.execute(query, params).fetchall()
    notes = [dict(zip([col[0] for col in c.description], row)) for row in rows]
    
    # Parse metadata for each note
    for note in notes:
        if note.get('metadata'):
            try:
                note['metadata'] = json.loads(note['metadata'])
            except:
                note['metadata'] = {}
    
    conn.close()
    
    return notes

# Database migration to add metadata and archive_path columns
def add_browser_capture_columns():
    """Add columns for browser capture functionality"""
    conn = get_conn()
    c = conn.cursor()
    
    # Check if columns exist
    columns = [row[1] for row in c.execute("PRAGMA table_info(notes)")]
    
    if 'metadata' not in columns:
        c.execute("ALTER TABLE notes ADD COLUMN metadata TEXT")
    
    if 'archive_path' not in columns:
        c.execute("ALTER TABLE notes ADD COLUMN archive_path TEXT")
    
    conn.commit()
    conn.close()

# Call this in your init_db() function
# add_browser_capture_columns()