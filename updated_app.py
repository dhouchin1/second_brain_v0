import sqlite3
from datetime import datetime, timedelta
from fastapi import (
    FastAPI,
    Request,
    Form,
    UploadFile,
    File,
    Body,
    Query,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from collections import defaultdict
import pathlib
from llm_utils import ollama_summarize, ollama_generate_title
from tasks import process_note
from markupsafe import Markup, escape
import re
from config import settings
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel
from markdown_writer import save_markdown, safe_filename
from audio_utils import transcribe_audio
from typing import Optional, List

# ---- FastAPI Setup ----
app = FastAPI()
templates = Jinja2Templates(directory=str(settings.base_dir / "templates"))
app.mount("/static", StaticFiles(directory=str(settings.base_dir / "static")), name="static")

def highlight(text, term):
    if not text or not term:
        return text
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    return Markup(pattern.sub(lambda m: f"<mark>{escape(m.group(0))}</mark>", text))
templates.env.filters['highlight'] = highlight

def get_conn():
    return sqlite3.connect(str(settings.db_path))

def get_last_sync():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS sync_status (id INTEGER PRIMARY KEY, last_sync TEXT)"
    )
    row = c.execute("SELECT last_sync FROM sync_status WHERE id = 1").fetchone()
    conn.close()
    return row[0] if row else None

def set_last_sync(ts: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS sync_status (id INTEGER PRIMARY KEY, last_sync TEXT)"
    )
    c.execute(
        "INSERT INTO sync_status (id, last_sync) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET last_sync=excluded.last_sync",
        (ts,),
    )
    conn.commit()
    conn.close()

def export_notes_to_obsidian(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute(
        "SELECT title, content, timestamp FROM notes WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    for title, content, ts in rows:
        file_ts = ts.replace(":", "-").replace(" ", "_") if ts else datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        fname = f"{file_ts}-{safe_filename(title or 'note')}.md"
        save_markdown(title or "", content or "", fname)
    set_last_sync(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    conn.close()

# Auth setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None

class User(BaseModel):
    id: int
    username: str

class UserInDB(User):
    hashed_password: str

# Enhanced data models
class DiscordWebhook(BaseModel):
    note: str
    tags: str = ""
    type: str = "discord"
    discord_user_id: Optional[int] = None
    timestamp: Optional[str] = None

class SearchRequest(BaseModel):
    query: str
    filters: Optional[dict] = {}
    limit: int = 20

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user(username: str):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT id, username, hashed_password FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()
    if row:
        return UserInDB(id=row[0], username=row[1], hashed_password=row[2])
    return None

def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(token_data.username)
    if user is None:
        raise credentials_exception
    return user

def init_db():
    conn = get_conn()
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL
        )
    ''')
    
    # Notes table
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            summary TEXT,
            tags TEXT,
            actions TEXT,
            type TEXT,
            timestamp TEXT,
            audio_filename TEXT,
            content TEXT,
            status TEXT DEFAULT 'complete',
            user_id INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    # FTS table
    c.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            title, summary, tags, actions, content, content='notes', content_rowid='id'
        )
    ''')
    
    # Enhanced FTS5 table
    c.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts5 USING fts5(
            title, content, summary, tags, actions,
            content='notes', content_rowid='id',
            tokenize='porter unicode61'
        )
    ''')
    
    # Discord users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS discord_users (
            discord_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            linked_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    # Reminders table
    c.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id INTEGER,
            user_id INTEGER,
            due_date TEXT,
            completed BOOLEAN DEFAULT FALSE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(note_id) REFERENCES notes(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    # Search analytics
    c.execute('''
        CREATE TABLE IF NOT EXISTS search_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            query TEXT,
            results_count INTEGER,
            clicked_result_id INTEGER,
            search_type TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS sync_status (
            id INTEGER PRIMARY KEY,
            last_sync TEXT
        )
    ''')
    
    # Ensure columns exist
    cols = [row[1] for row in c.execute("PRAGMA table_info(notes)")]
    if 'status' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN status TEXT DEFAULT 'complete'")
        c.execute("UPDATE notes SET status='complete' WHERE status IS NULL")
    if 'user_id' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN user_id INTEGER")
    if 'actions' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN actions TEXT")

    # Update FTS if needed
    fts_cols = [row[1] for row in c.execute("PRAGMA table_info(notes_fts)")]
    if 'actions' not in fts_cols:
        c.execute("DROP TABLE IF EXISTS notes_fts")
        c.execute('''
            CREATE VIRTUAL TABLE notes_fts USING fts5(
                title, summary, tags, actions, content, content='notes', content_rowid='id'
            )
        ''')
        rows = c.execute("SELECT id, title, summary, tags, actions, content FROM notes").fetchall()
        c.executemany(
            "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    
    conn.commit()
    conn.close()

init_db()

def find_related_notes(note_id, tags, user_id, conn):
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    if not tag_list:
        return []
    q = " OR ".join(["tags LIKE ?"] * len(tag_list))
    params = [f"%{tag}%" for tag in tag_list]
    sql = f"SELECT id, title FROM notes WHERE id != ? AND user_id = ? AND ({q}) LIMIT 3"
    params = [note_id, user_id] + params
    rows = conn.execute(sql, params).fetchall()
    return [{"id": row[0], "title": row[1]} for row in rows]

# Auth endpoints
@app.post("/register", response_model=User)
def register(username: str = Form(...), password: str = Form(...)):
    conn = get_conn()
    c = conn.cursor()
    hashed = get_password_hash(password)
    try:
        c.execute(
            "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
            (username, hashed),
        )
        conn.commit()
        user_id = c.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already registered")
    conn.close()
    return User(id=user_id, username=username)

@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect username or password",
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Main endpoints (keep existing)
@app.get("/")
def dashboard(
    request: Request,
    q: str = "",
    tag: str = "",
    current_user: User = Depends(get_current_user),
):
    conn = get_conn()
    c = conn.cursor()
    if q:
        rows = c.execute(
            """
            SELECT n.*
            FROM notes_fts fts
            JOIN notes n ON n.id = fts.rowid
            WHERE notes_fts MATCH ? AND n.user_id = ?
            ORDER BY n.timestamp DESC LIMIT 100
        """,
            (q, current_user.id),
        ).fetchall()
    elif tag:
        rows = c.execute(
            "SELECT * FROM notes WHERE tags LIKE ? AND user_id = ? ORDER BY timestamp DESC",
            (f"%{tag}%", current_user.id),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM notes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 100",
            (current_user.id,),
        ).fetchall()
    notes = [dict(zip([col[0] for col in c.description], row)) for row in rows]
    notes_by_day = defaultdict(list)
    for note in notes:
        day = note["timestamp"][:10] if note.get("timestamp") else "Unknown"
        notes_by_day[day].append(note)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "notes_by_day": dict(notes_by_day),
            "q": q,
            "tag": tag,
            "last_sync": get_last_sync(),
        },
    )

# Enhanced Search Endpoint
@app.post("/api/search/enhanced")
async def enhanced_search(
    request: SearchRequest,
    current_user: User = Depends(get_current_user)
):
    """Enhanced search with FTS and semantic similarity"""
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
    
    # Log search
    c.execute(
        "INSERT INTO search_analytics (user_id, query, results_count, search_type) VALUES (?, ?, ?, ?)",
        (current_user.id, request.query, len(notes), "fts")
    )
    
    conn.commit()
    conn.close()
    
    return {
        "results": notes,
        "total": len(notes),
        "query": request.query
    }

# Discord Integration
@app.post("/webhook/discord")
async def webhook_discord(
    data: DiscordWebhook,
    current_user: User = Depends(get_current_user)
):
    """Discord webhook endpoint"""
    note = data.note
    tags = data.tags
    note_type = data.type
    
    result = ollama_summarize(note)
    summary = result.get("summary", "")
    ai_tags = result.get("tags", [])
    ai_actions = result.get("actions", [])
    
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    tag_list.extend([t for t in ai_tags if t and t not in tag_list])
    tags = ",".join(tag_list)
    actions = "\n".join(ai_actions)
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notes (title, content, summary, tags, actions, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            note[:60] + "..." if len(note) > 60 else note,
            note,
            summary,
            tags,
            actions,
            note_type,
            now,
            current_user.id,
        ),
    )
    conn.commit()
    note_id = c.lastrowid
    
    c.execute(
        "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
        (note_id, note[:60] + "..." if len(note) > 60 else note, summary, tags, actions, note),
    )
    conn.commit()
    conn.close()
    
    return {"status": "ok", "note_id": note_id}

# Keep all existing endpoints (detail, edit, delete, capture, etc.)
@app.get("/detail/{note_id}")
def detail(
    request: Request,
    note_id: int,
    current_user: User = Depends(get_current_user),
):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT * FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user.id),
    ).fetchone()
    if not row:
        return RedirectResponse("/", status_code=302)
    note = dict(zip([col[0] for col in c.description], row))
    related = find_related_notes(note_id, note.get("tags", ""), current_user.id, conn)
    return templates.TemplateResponse(
        "detail.html",
        {"request": request, "note": note, "related": related}
    )

@app.get("/edit/{note_id}")
def edit_get(
    request: Request,
    note_id: int,
    current_user: User = Depends(get_current_user),
):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT * FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user.id),
    ).fetchone()
    if not row:
        conn.close()
        return RedirectResponse("/", status_code=302)
    note = dict(zip([col[0] for col in c.description], row))
    conn.close()
    return templates.TemplateResponse(
        "edit.html", {"request": request, "note": note}
    )

@app.post("/edit/{note_id}")
def edit_post(
    request: Request,
    note_id: int,
    content: str = Form(""),
    tags: str = Form(""),
    current_user: User = Depends(get_current_user),
):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE notes SET content = ?, tags = ? WHERE id = ? AND user_id = ?",
        (content, tags, note_id, current_user.id),
    )
    row = c.execute(
        "SELECT title, summary, actions FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user.id),
    ).fetchone()
    if row:
        title, summary, actions = row
        c.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
        c.execute(
            "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, title, summary, tags, actions, content),
        )
    conn.commit()
    conn.close()
    if "application/json" in request.headers.get("accept", ""):
        return {"status": "ok"}
    return RedirectResponse(f"/detail/{note_id}", status_code=302)

@app.post("/delete/{note_id}")
def delete_note(
    request: Request,
    note_id: int,
    current_user: User = Depends(get_current_user),
):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT audio_filename FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user.id),
    ).fetchone()
    if row and row[0]:
        audio_path = settings.audio_dir / row[0]
        converted = audio_path.with_suffix('.converted.wav')
        transcript = pathlib.Path(str(converted) + '.txt')
        for p in [audio_path, converted, transcript]:
            if p.exists():
                p.unlink()
    c.execute(
        "DELETE FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user.id),
    )
    c.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
    conn.commit()
    conn.close()
    if "application/json" in request.headers.get("accept", ""):
        return {"status": "deleted"}
    return RedirectResponse("/", status_code=302)

@app.get("/audio/{filename}")
def get_audio(filename: str, current_user: User = Depends(get_current_user)):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT 1 FROM notes WHERE audio_filename = ? AND user_id = ?",
        (filename, current_user.id),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Audio not found")
    audio_path = settings.audio_dir / filename
    if audio_path.exists():
        return FileResponse(str(audio_path))
    raise HTTPException(status_code=404, detail="Audio not found")

@app.post("/capture")
async def capture(
    request: Request,
    background_tasks: BackgroundTasks,
    note: str = Form(""),
    tags: str = Form(""),
    file: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
):
    content = note.strip()
    note_type = "note"
    audio_filename = None

    if file:
        settings.audio_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        safe_name = f"{timestamp}-{file.filename.replace(' ', '_')}"
        audio_path = settings.audio_dir / safe_name
        with open(audio_path, "wb") as out_f:
            out_f.write(await file.read())
        audio_filename = safe_name
        note_type = "audio"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notes (title, content, summary, tags, actions, type, timestamp, audio_filename, status, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "[Processing]",
            content if note_type == "note" else "",
            "",
            tags,
            "",
            note_type,
            now,
            audio_filename,
            "pending",
            current_user.id,
        ),
    )
    conn.commit()
    note_id = c.lastrowid
    conn.close()

    background_tasks.add_task(process_note, note_id)

    if "application/json" in request.headers.get("accept", ""):
        return {"id": note_id, "status": "pending"}
    return RedirectResponse("/", status_code=302)

@app.post("/webhook/apple")
async def webhook_apple(
    data: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    print("APPLE WEBHOOK RECEIVED:", data)
    note = data.get("note", "")
    tags = data.get("tags", "")
    note_type = data.get("type", "apple")
    result = ollama_summarize(note)
    summary = result.get("summary", "")
    ai_tags = result.get("tags", [])
    ai_actions = result.get("actions", [])
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    tag_list.extend([t for t in ai_tags if t and t not in tag_list])
    tags = ",".join(tag_list)
    actions = "\n".join(ai_actions)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notes (title, content, summary, tags, actions, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            note[:60] + "..." if len(note) > 60 else note,
            note,
            summary,
            tags,
            actions,
            note_type,
            now,
            current_user.id,
        ),
    )
    conn.commit()
    note_id = c.lastrowid
    c.execute(
        "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
        (note_id, note[:60] + "..." if len(note) > 60 else note, summary, tags, actions, note),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.post("/sync/obsidian")
def sync_obsidian(
    background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)
):
    background_tasks.add_task(export_notes_to_obsidian, current_user.id)
    return {"status": "queued"}

@app.get("/activity")
def activity_timeline(
    request: Request,
    activity_type: str = Query("all", alias="type"),
    start: str = "",
    end: str = "",
    current_user: User = Depends(get_current_user),
):
    conn = get_conn()
    c = conn.cursor()

    base_query = "SELECT id, summary, type, timestamp FROM notes WHERE user_id = ?"
    conditions = []
    params = [current_user.id]
    if activity_type and activity_type != "all":
        conditions.append("type = ?")
        params.append(activity_type)
    if start:
        conditions.append("date(timestamp) >= date(?)")
        params.append(start)
    if end:
        conditions.append("date(timestamp) <= date(?)")
        params.append(end)
    if conditions:
        base_query += " AND " + " AND ".join(conditions)
    base_query += " ORDER BY timestamp DESC LIMIT 100"

    rows = c.execute(base_query, params).fetchall()
    activities = [
        dict(zip([col[0] for col in c.description], row)) for row in rows
    ]
    conn.close()
    return templates.TemplateResponse(
        "activity_timeline.html",
        {
            "request": request,
            "activities": activities,
            "activity_type": activity_type,
            "start": start,
            "end": end,
        },
    )

@app.get("/status/{note_id}")
def note_status(note_id: int, current_user: User = Depends(get_current_user)):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT status FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user.id),
    ).fetchone()
    conn.close()
    if not row:
        return {"status": "missing"}
    return {"status": row[0]}

# Enhanced Analytics endpoint
@app.get("/api/analytics")
async def get_analytics(current_user: User = Depends(get_current_user)):
    """Get user analytics and insights"""
    conn = get_conn()
    c = conn.cursor()
    
    # Basic stats
    total_notes = c.execute(
        "SELECT COUNT(*) as count FROM notes WHERE user_id = ?",
        (current_user.id,)
    ).fetchone()[0]
    
    # This week
    this_week = c.execute(
        "SELECT COUNT(*) as count FROM notes WHERE user_id = ? AND date(timestamp) >= date('now', '-7 days')",
        (current_user.id,)
    ).fetchone()[0]
    
    # By type
    by_type_rows = c.execute(
        "SELECT type, COUNT(*) as count FROM notes WHERE user_id = ? GROUP BY type",
        (current_user.id,)
    ).fetchall()
    by_type = [{"type": row[0], "count": row[1]} for row in by_type_rows]
    
    # Popular tags
    tag_counts = {}
    tag_rows = c.execute(
        "SELECT tags FROM notes WHERE user_id = ? AND tags IS NOT NULL",
        (current_user.id,)
    ).fetchall()
    
    for row in tag_rows:
        if row[0]:
            tags = row[0].split(",")
            for tag in tags:
                tag = tag.strip()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    popular_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    conn.close()
    
    return {
        "total_notes": total_notes,
        "this_week": this_week,
        "by_type": by_type,
        "popular_tags": [{"name": tag, "count": count} for tag, count in popular_tags]
    }

@app.get("/health")
def health():
    conn = get_conn()
    c = conn.cursor()
    tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    return {"tables": [t[0] for t in tables]}