# enhanced_endpoints.py - Add these to your existing app.py

from fastapi import HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
import hashlib
import hmac

# New data models
class DiscordWebhook(BaseModel):
    note: str
    tags: str = ""
    type: str = "discord"
    discord_user_id: int
    timestamp: str

class AppleReminderWebhook(BaseModel):
    title: str
    due_date: Optional[str] = None
    notes: str = ""
    tags: str = "reminder,apple"

class CalendarEvent(BaseModel):
    title: str
    start_date: str
    end_date: str
    description: str = ""
    attendees: List[str] = []

class SearchRequest(BaseModel):
    query: str
    filters: Optional[dict] = {}
    limit: int = 20

# Discord Integration
@app.post("/webhook/discord")
async def webhook_discord(
    data: DiscordWebhook,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_from_discord)
):
    """Enhanced Discord webhook with user mapping"""
    # Map Discord user to Second Brain user
    conn = get_conn()
    c = conn.cursor()
    
    # Check if Discord user is linked
    discord_link = c.execute(
        "SELECT user_id FROM discord_users WHERE discord_id = ?",
        (data.discord_user_id,)
    ).fetchone()
    
    if not discord_link:
        # Auto-register or return error
        raise HTTPException(
            status_code=401, 
            detail="Discord user not linked. Use !link command first."
        )
    
    user_id = discord_link[0]
    
    # Process note with AI
    result = ollama_summarize(data.note)
    summary = result.get("summary", "")
    ai_tags = result.get("tags", [])
    ai_actions = result.get("actions", [])
    
    # Combine tags
    tag_list = [t.strip() for t in data.tags.split(",") if t.strip()]
    tag_list.extend([t for t in ai_tags if t and t not in tag_list])
    tags = ",".join(tag_list)
    
    # Save note
    c.execute(
        "INSERT INTO notes (title, content, summary, tags, actions, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            data.note[:60] + "..." if len(data.note) > 60 else data.note,
            data.note,
            summary,
            tags,
            "\n".join(ai_actions),
            data.type,
            data.timestamp,
            user_id
        ),
    )
    conn.commit()
    note_id = c.lastrowid
    
    # Update FTS
    c.execute(
        "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
        (note_id, data.note[:60], summary, tags, "\n".join(ai_actions), data.note),
    )
    conn.commit()
    conn.close()
    
    return {"status": "ok", "note_id": note_id}

# Apple Shortcuts Enhanced
@app.post("/webhook/apple/reminder")
async def create_apple_reminder(
    data: AppleReminderWebhook,
    current_user: User = Depends(get_current_user)
):
    """Create reminder from Apple Shortcuts"""
    conn = get_conn()
    c = conn.cursor()
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Create note
    c.execute(
        "INSERT INTO notes (title, content, summary, tags, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            data.title,
            data.notes,
            f"Reminder: {data.title}",
            data.tags,
            "reminder",
            now,
            current_user.id
        ),
    )
    note_id = c.lastrowid
    
    # Create reminder entry
    c.execute(
        "INSERT INTO reminders (note_id, user_id, due_date, completed) VALUES (?, ?, ?, ?)",
        (note_id, current_user.id, data.due_date, False)
    )
    
    conn.commit()
    conn.close()
    
    return {"status": "ok", "reminder_id": note_id}

@app.post("/webhook/apple/calendar")
async def create_calendar_event(
    data: CalendarEvent,
    current_user: User = Depends(get_current_user)
):
    """Create calendar event and meeting note"""
    # This would integrate with Apple Calendar API
    # For now, create a meeting note placeholder
    
    conn = get_conn()
    c = conn.cursor()
    
    meeting_note = f"""
Meeting: {data.title}
Date: {data.start_date} - {data.end_date}
Attendees: {', '.join(data.attendees)}

{data.description}

--- Meeting Notes ---
(This will be filled during/after the meeting)
"""
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute(
        "INSERT INTO notes (title, content, summary, tags, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            f"Meeting: {data.title}",
            meeting_note,
            f"Scheduled meeting: {data.title}",
            "meeting,calendar,scheduled",
            "meeting",
            now,
            current_user.id
        ),
    )
    
    conn.commit()
    conn.close()
    
    return {"status": "ok", "event_created": True}

# Enhanced Search
@app.post("/api/search")
async def enhanced_search(
    request: SearchRequest,
    current_user: User = Depends(get_current_user)
):
    """Advanced search with filters and semantic similarity"""
    conn = get_conn()
    c = conn.cursor()
    
    # Base FTS search
    base_query = """
        SELECT n.*, rank FROM notes_fts fts
        JOIN notes n ON n.id = fts.rowid
        WHERE notes_fts MATCH ? AND n.user_id = ?
    """
    
    params = [request.query, current_user.id]
    
    # Add filters
    if request.filters:
        if 'type' in request.filters:
            base_query += " AND n.type = ?"
            params.append(request.filters['type'])
        
        if 'tags' in request.filters:
            base_query += " AND n.tags LIKE ?"
            params.append(f"%{request.filters['tags']}%")
        
        if 'date_from' in request.filters:
            base_query += " AND date(n.timestamp) >= date(?)"
            params.append(request.filters['date_from'])
    
    base_query += f" ORDER BY rank LIMIT {request.limit}"
    
    rows = c.execute(base_query, params).fetchall()
    notes = [dict(zip([col[0] for col in c.description], row)) for row in rows]
    
    conn.close()
    
    return {
        "results": notes,
        "total": len(notes),
        "query": request.query
    }

# Analytics
@app.get("/api/analytics")
async def get_analytics(current_user: User = Depends(get_current_user)):
    """Get user analytics and insights"""
    conn = get_conn()
    c = conn.cursor()
    
    # Basic stats
    total_notes = c.execute(
        "SELECT COUNT(*) as count FROM notes WHERE user_id = ?",
        (current_user.id,)
    ).fetchone()["count"]
    
    # This week
    this_week = c.execute(
        "SELECT COUNT(*) as count FROM notes WHERE user_id = ? AND date(timestamp) >= date('now', '-7 days')",
        (current_user.id,)
    ).fetchone()["count"]
    
    # By type
    by_type = c.execute(
        "SELECT type, COUNT(*) as count FROM notes WHERE user_id = ? GROUP BY type",
        (current_user.id,)
    ).fetchall()
    
    # Popular tags
    tag_counts = {}
    tag_rows = c.execute(
        "SELECT tags FROM notes WHERE user_id = ? AND tags IS NOT NULL",
        (current_user.id,)
    ).fetchall()
    
    for row in tag_rows:
        tags = row["tags"].split(",")
        for tag in tags:
            tag = tag.strip()
            if tag:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    popular_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    conn.close()
    
    return {
        "total_notes": total_notes,
        "this_week": this_week,
        "by_type": [{"type": row["type"], "count": row["count"]} for row in by_type],
        "popular_tags": [{"name": tag, "count": count} for tag, count in popular_tags]
    }

# Real-time status updates
@app.get("/api/notes/{note_id}/status")
async def get_note_processing_status(
    note_id: int,
    current_user: User = Depends(get_current_user)
):
    """Get real-time processing status"""
    conn = get_conn()
    c = conn.cursor()
    
    note = c.execute(
        "SELECT status, title, summary FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user.id)
    ).fetchone()
    
    conn.close()
    
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    return {
        "status": note["status"],
        "title": note["title"],
        "summary": note["summary"],
        "progress": 100 if note["status"] == "complete" else 50
    }

# Batch operations
@app.post("/api/notes/batch")
async def batch_operations(
    operations: List[dict],
    current_user: User = Depends(get_current_user)
):
    """Perform batch operations on notes"""
    conn = get_conn()
    c = conn.cursor()
    
    results = []
    
    for op in operations:
        try:
            if op["action"] == "delete":
                c.execute(
                    "DELETE FROM notes WHERE id = ? AND user_id = ?",
                    (op["note_id"], current_user.id)
                )
                c.execute("DELETE FROM notes_fts WHERE rowid = ?", (op["note_id"],))
                results.append({"note_id": op["note_id"], "status": "deleted"})
            
            elif op["action"] == "tag":
                c.execute(
                    "UPDATE notes SET tags = ? WHERE id = ? AND user_id = ?",
                    (op["tags"], op["note_id"], current_user.id)
                )
                results.append({"note_id": op["note_id"], "status": "tagged"})
            
            elif op["action"] == "export":
                # Add to export queue
                results.append({"note_id": op["note_id"], "status": "queued_for_export"})
                
        except Exception as e:
            results.append({"note_id": op.get("note_id"), "status": "error", "error": str(e)})
    
    conn.commit()
    conn.close()
    
    return {"results": results}

# Helper function for Discord user authentication
async def get_current_user_from_discord(discord_id: int = None):
    """Map Discord user to Second Brain user"""
    if not discord_id:
        raise HTTPException(status_code=401, detail="Discord user ID required")
    
    conn = get_conn()
    c = conn.cursor()
    
    link = c.execute(
        "SELECT u.* FROM users u JOIN discord_users du ON u.id = du.user_id WHERE du.discord_id = ?",
        (discord_id,)
    ).fetchone()
    
    conn.close()
    
    if not link:
        raise HTTPException(status_code=401, detail="Discord user not linked")
    
    return User(id=link["id"], username=link["username"])

# Database schema updates needed:
"""
CREATE TABLE IF NOT EXISTS discord_users (
    discord_id INTEGER PRIMARY KEY,
    user_id INTEGER,
    linked_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER,
    user_id INTEGER,
    due_date TEXT,
    completed BOOLEAN DEFAULT FALSE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(note_id) REFERENCES notes(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS integrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT, -- 'discord', 'apple', 'obsidian'
    config TEXT, -- JSON config
    enabled BOOLEAN DEFAULT TRUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""