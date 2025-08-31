# Legacy search_engine removed from app imports; unified service is used instead
from discord_bot import SecondBrainCog
from obsidian_sync import ObsidianSync
from file_processor import FileProcessor
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
    Header,
    HTTPException,
    status,
)
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from collections import defaultdict
import pathlib
import json
import hashlib
from urllib.parse import urlparse
import secrets
import uuid
import os
from llm_utils import ollama_summarize, ollama_generate_title
from tasks import process_note

try:
    from tasks_enhanced import process_note_with_status
    from realtime_status import create_status_endpoint
    REALTIME_AVAILABLE = True
except ImportError:
    REALTIME_AVAILABLE = False
from markupsafe import Markup, escape
import re
from config import settings
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel
from markdown_writer import save_markdown, safe_filename
from audio_utils import transcribe_audio
from typing import Optional, List, Dict

# ---- FastAPI Setup ----
app = FastAPI()
templates = Jinja2Templates(directory=str(settings.base_dir / "templates"))
app.mount("/static", StaticFiles(directory=str(settings.base_dir / "static")), name="static")

# Search API router will be included after auth functions are defined

@app.on_event("startup")
def _ensure_base_directories():
    """Ensure base filesystem locations exist for vault/uploads/audio.

    Handles relative paths in .env by anchoring to the project base directory.
    """
    try:
        # Uploads and audio (app-local)
        pathlib.Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)
        pathlib.Path(settings.audio_dir).mkdir(parents=True, exist_ok=True)
        # Obsidian vault and subdirs
        v = pathlib.Path(settings.vault_path)
        if not v.is_absolute():
            v = pathlib.Path(settings.base_dir) / v
        v.mkdir(parents=True, exist_ok=True)
        (v / ".secondbrain").mkdir(parents=True, exist_ok=True)
        (v / "audio").mkdir(parents=True, exist_ok=True)
        (v / "attachments").mkdir(parents=True, exist_ok=True)
    except Exception:
        # Directory creation is best-effort; failures will be surfaced later in usage paths
        pass

def highlight(text, term):
    if not text or not term:
        return text
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    return Markup(pattern.sub(lambda m: f"<mark>{escape(m.group(0))}</mark>", text))
templates.env.filters['highlight'] = highlight

def get_conn():
    return sqlite3.connect(str(settings.db_path))

# --- Search helpers (unified service) ---
def _get_search_service():
    from services.search_adapter import SearchService
    db_path = os.getenv('SQLITE_DB', str(settings.db_path))
    return SearchService(db_path=db_path, vec_ext_path=os.getenv('SQLITE_VEC_PATH'))

def _resolve_search_mode(filters: Optional[dict]) -> str:
    mode = 'hybrid'
    if filters and isinstance(filters, dict):
        t = filters.get('type') or filters.get('mode')
        if t in {'fts','keyword'}:
            mode = 'keyword'
        elif t in {'semantic','vector'}:
            mode = 'semantic'
        elif t in {'hybrid','both'}:
            mode = 'hybrid'
    return mode

# --- Flash + CSRF helpers ---
def render_page(request: Request, template_name: str, context: dict):
    ctx = dict(context)
    ctx["request"] = request
    # flash
    flash = None
    raw = request.cookies.get("flash")
    if raw:
        try:
            flash = json.loads(raw)
        except Exception:
            flash = None
    if flash:
        ctx["flash"] = flash
    # csrf
    token = request.cookies.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
    ctx["csrf_token"] = token
    # Inject SSE token for realtime auth on any page where a user is present
    try:
        u = ctx.get("user") or get_current_user_silent(request)
        if u:
            # Longer-lived token to avoid frequent SSE reconnect 401s
            ctx["sse_token"] = create_file_token(u.id, "sse", ttl_seconds=60*60*8)
    except Exception:
        pass

    resp = templates.TemplateResponse(template_name, ctx)
    # ensure cookie set and clear flash
    if request.cookies.get("csrf_token") != token:
        resp.set_cookie("csrf_token", token, httponly=True, samesite="lax", max_age=60*60*8)
    if flash:
        resp.delete_cookie("flash")
    return resp

def set_flash(resp, message: str, category: str = "info"):
    data = {"message": message, "category": category}
    resp.set_cookie("flash", json.dumps(data), samesite="lax", max_age=60)

def validate_csrf(request: Request, csrf_token: Optional[str]) -> bool:
    return csrf_token and csrf_token == request.cookies.get("csrf_token")

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

# --- Signed URL support for file serving ---
def create_file_token(user_id: int, filename: str, ttl_seconds: int = 600) -> str:
    """Create a short-lived JWT token for accessing a specific file.

    Encodes: user id, filename, and expiry. Used for img/pdf links where
    cookies may not be reliably attached (e.g., cross-origin contexts).
    """
    expire = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    payload = {"uid": user_id, "fn": filename, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

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

# Duplicate removed; SearchRequest is defined earlier

# (moved below auth functions) Service-based search endpoint using unified adapter

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

def get_current_user_from_discord(authorization: str = Header(None)) -> User:
    """Authenticate Discord webhook requests using a shared bearer token.

    The Discord bot sends `Authorization: Bearer <WEBHOOK_TOKEN>`. We validate
    the token and return a placeholder user, since the endpoint determines the
    actual `user_id` by mapping the provided `discord_user_id` in the payload.
    """
    expected = os.getenv("WEBHOOK_TOKEN", "your-secret-token")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    return User(id=0, username="discord-webhook")

async def get_current_user(request: Request, token: Optional[str] = Depends(lambda: None)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Support Authorization header or cookie-based token for browser navigation
    if not token:
        auth = request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
        else:
            token = request.cookies.get("access_token")
    if not token:
        raise credentials_exception
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

def get_current_user_silent(request: Request) -> Optional[User]:
    """Best-effort user extraction for browser pages. Returns None if invalid."""
    token = None
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    else:
        token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            return None
        user = get_user(username)
        return user
    except Exception:
        return None

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
    # New file-related columns used by capture pipeline
    if 'file_filename' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN file_filename TEXT")
    if 'file_type' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN file_type TEXT")
    if 'file_mime_type' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN file_mime_type TEXT")
    if 'file_size' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN file_size INTEGER")
    if 'extracted_text' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN extracted_text TEXT")
    if 'file_metadata' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN file_metadata TEXT")
    # Web ingestion metadata
    if 'source_url' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN source_url TEXT")
    if 'web_metadata' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN web_metadata TEXT")
    if 'screenshot_path' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN screenshot_path TEXT")
    if 'content_hash' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN content_hash TEXT")

    # Update FTS if needed (ensure both actions and extracted_text columns exist)
    try:
        fts_cols = [row[1] for row in c.execute("PRAGMA table_info(notes_fts)")]
    except sqlite3.OperationalError:
        fts_cols = []
    if ('actions' not in fts_cols) or ('extracted_text' not in fts_cols):
        c.execute("DROP TABLE IF EXISTS notes_fts")
        c.execute('''
            CREATE VIRTUAL TABLE notes_fts USING fts5(
                title, summary, tags, actions, content, extracted_text,
                content='notes', content_rowid='id'
            )
        ''')
        rows = c.execute("SELECT id, title, summary, tags, actions, content, extracted_text FROM notes").fetchall()
        c.executemany(
            "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    # Ensure notes_fts5 is populated as well (used by advanced search)
    try:
        count_fts5 = c.execute("SELECT count(*) FROM notes_fts5").fetchone()[0]
    except sqlite3.OperationalError:
        count_fts5 = 0
    if count_fts5 == 0:
        rows5 = c.execute("SELECT id, title, content, summary, tags, actions FROM notes").fetchall()
        if rows5:
            c.executemany(
                "INSERT INTO notes_fts5(rowid, title, content, summary, tags, actions) VALUES (?, ?, ?, ?, ?, ?)",
                rows5,
            )
    
    conn.commit()
    conn.close()

init_db()

# --- Simple FIFO job worker for note processing ---
import asyncio

def _claim_next_pending_note():
    conn = get_conn()
    conn.isolation_level = None  # autocommit mode for immediate lock/retry simplicity
    c = conn.cursor()
    row = c.execute(
        "SELECT id FROM notes WHERE status = 'pending' ORDER BY timestamp ASC LIMIT 1"
    ).fetchone()
    if not row:
        conn.close()
        return None
    note_id = row[0]
    # Attempt to claim atomically by status check
    c.execute("UPDATE notes SET status='processing' WHERE id=? AND status='pending'", (note_id,))
    if c.rowcount == 0:
        conn.close()
        return None
    conn.close()
    return note_id

async def _process_note_id(note_id: int):
    conn = get_conn()
    conn.close()  # no-op here; processing uses helpers
    try:
        timeout = getattr(settings, 'processing_timeout_seconds', 600) or 600
        async def _run():
            if REALTIME_AVAILABLE:
                await process_note_with_status(note_id)
            else:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, process_note, note_id)
        await asyncio.wait_for(_run(), timeout=timeout)
    except asyncio.TimeoutError:
        conn = get_conn()
        conn.execute("UPDATE notes SET status='failed:timeout' WHERE id=?", (note_id,))
        conn.commit()
        conn.close()
    except Exception:
        # Mark as failed
        conn = get_conn()
        conn.execute("UPDATE notes SET status='failed' WHERE id=?", (note_id,))
        conn.commit()
        conn.close()
    return True

async def job_worker():
    # Simple in-process worker pool honoring configured concurrency
    limit = getattr(settings, 'processing_concurrency', 2) or 1
    active: set[asyncio.Task] = set()
    async def _spawn_one():
        note_id = _claim_next_pending_note()
        if note_id is None:
            return False
        t = asyncio.create_task(_process_note_id(note_id))
        active.add(t)
        t.add_done_callback(lambda fut: active.discard(fut))
        return True
    while True:
        # Refill up to limit
        spawned = False
        while len(active) < limit:
            claimed = await _spawn_one()
            spawned = spawned or claimed
            if not claimed:
                break
        await asyncio.sleep(0.2 if spawned or active else 1.0)

@app.on_event("startup")
async def _start_worker():
    if getattr(app.state, "job_worker_started", False):
        return
    app.state.job_worker_started = True
    asyncio.create_task(job_worker())

@app.on_event("startup")
async def _start_automation():
    """Start automated relationship discovery system"""
    if getattr(app.state, "automation_started", False):
        return
    app.state.automation_started = True
    
    # TEMPORARILY DISABLED to resolve database locking issues
    # try:
    #     from automated_relationships import get_automation_engine
    #     automation_engine = get_automation_engine(str(settings.db_path))
    #     app.state.automation_engine = automation_engine
    #     asyncio.create_task(automation_engine.start_automation())
    #     print("🤖 Automated relationship discovery started")
    # except ImportError:
    #     print("⚠️  Automated relationships not available")
    print("⚠️  Automated relationship discovery temporarily disabled to resolve database locking")

# Add real-time status endpoints if available
if REALTIME_AVAILABLE:
    create_status_endpoint(app)

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

# Include search API router
try:
    from search_api import create_search_router
    search_router = create_search_router(get_current_user, str(settings.db_path))
    app.include_router(search_router)
except ImportError:
    pass  # Graceful degradation if search API not available

# Search page route (redirects to login if unauthenticated)
@app.get("/search")
async def search_page(request: Request):
    user = get_current_user_silent(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return render_page(request, "search.html", {"user": user})

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

# Simple browser login/logout using cookie for token storage
@app.get("/login")
def login_page(request: Request):
    return render_page(request, "login.html", {})

@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    if not validate_csrf(request, csrf_token):
        return render_page(request, "login.html", {"error": "Invalid form. Please refresh."})
    user = authenticate_user(username, password)
    if not user:
        resp = render_page(request, "login.html", {"error": "Invalid username or password"})
        resp.status_code = 400
        return resp
    token = create_access_token({"sub": user.username}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    resp = RedirectResponse(url="/", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES*60)
    set_flash(resp, "Welcome back!", "success")
    return resp

@app.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    if not validate_csrf(request, csrf_token):
        return RedirectResponse(url="/login", status_code=302)
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie("access_token")
    set_flash(resp, "Logged out.")
    return resp

# Web Registration (UI)
@app.get("/signup")
def signup_page(request: Request):
    return render_page(request, "register.html", {})

@app.post("/signup")
def signup_submit(request: Request, username: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    if not validate_csrf(request, csrf_token):
        return render_page(request, "register.html", {"error": "Invalid form. Please refresh."})
    # Reuse registration logic, then log in
    conn = get_conn()
    c = conn.cursor()
    hashed = get_password_hash(password)
    try:
        c.execute(
            "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
            (username, hashed),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        resp = render_page(request, "register.html", {"error": "Username already registered"})
        resp.status_code = 400
        return resp
    conn.close()
    token = create_access_token({"sub": username}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    resp = RedirectResponse(url="/", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=ACCESS_TOKEN_EXPIRE_MINUTES*60)
    set_flash(resp, "Account created!", "success")
    return resp

# Simple health check
@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

# Main endpoints (keep existing)
@app.get("/")
def dashboard(
    request: Request,
    q: str = "",
    tag: str = "",
):
    current_user = get_current_user_silent(request)
    if not current_user:
        # Public landing page for visitors
        return render_page(request, "landing.html", {})
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
    
    # Helpers to compute metadata for display
    def _word_count(text: str | None) -> int:
        if not text:
            return 0
        return len([w for w in text.split() if w.strip()])

    def _format_hms(total_seconds: float) -> str:
        try:
            total_seconds = int(round(total_seconds))
            h, rem = divmod(total_seconds, 3600)
            m, s = divmod(rem, 60)
            return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        except Exception:
            return ""

    def _probe_duration_hms(path: str) -> str:
        """Use ffprobe to get media duration in seconds and format as H:MM:SS."""
        try:
            import subprocess
            result = subprocess.run(
                [
                    'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1', path
                ],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                seconds = float(result.stdout.strip())
                return _format_hms(seconds)
        except Exception:
            pass
        return ""

    def _audio_duration_from_note(note: dict) -> str:
        """Determine audio duration from converted wav if present, else via ffprobe on original."""
        try:
            import wave
            # Prefer audio_filename field
            fname = (note.get('audio_filename') or '').strip() or (note.get('file_filename') or '').strip()
            if not fname:
                return ""
            p = settings.audio_dir / fname
            # Prefer converted WAV if present
            if not p.suffix.lower().endswith('.wav'):
                alt = p.with_suffix('.converted.wav')
                if alt.exists():
                    p = alt
            if p.exists() and p.suffix.lower().endswith('.wav'):
                with wave.open(str(p), 'rb') as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    if rate:
                        return _format_hms(frames / float(rate))
            # Fall back to probing the original container via ffprobe
            if (settings.audio_dir / fname).exists():
                return _probe_duration_hms(str(settings.audio_dir / fname))
        except Exception:
            pass
        return ""

    def _tz_abbrev(ts: str | None) -> str:
        """Return local timezone abbreviation for the given timestamp string.
        Expects format %Y-%m-%d %H:%M:%S and treats it as local time.
        """
        if not ts:
            return ""
        try:
            import time
            tm = time.strptime(ts, "%Y-%m-%d %H:%M:%S")
            epoch = time.mktime(tm)
            return time.strftime('%Z', time.localtime(epoch)) or ""
        except Exception:
            return ""
    # Enrich notes with signed file URLs for image previews and add meta (duration/word count)
    for n in notes:
        try:
            ff = n.get("file_filename")
            ft = (n.get("file_type") or "").lower()
            mt = (n.get("file_mime_type") or "").lower()
            typ = (n.get("type") or "").lower()
            if ff and (ft == "image" or typ == "image" or mt.startswith("image/") or ft == "document" or mt == "application/pdf"):
                tok = create_file_token(current_user.id, ff, ttl_seconds=600)
                n["file_url"] = f"/files/{ff}?token={tok}"
        except Exception:
            # Non-fatal; previews just won't render
            pass
        # Add word count and audio duration for display
        try:
            n["word_count"] = _word_count(n.get("content") or n.get("summary") or "")
            if (n.get("type") or "").lower() == "audio":
                n["audio_duration_hms"] = _audio_duration_from_note(n)
            n["tz_abbr"] = _tz_abbrev(n.get("timestamp"))
        except Exception:
            pass
    notes_by_day = defaultdict(list)
    for note in notes:
        day = note["timestamp"][:10] if note.get("timestamp") else "Unknown"
        notes_by_day[day].append(note)
    # Recent notes panel data (always last 10)
    recent_rows = c.execute(
        """
        SELECT id, title, type, timestamp, audio_filename, status, tags,
               file_filename, file_type, file_mime_type
        FROM notes
        WHERE user_id = ?
        ORDER BY (tags LIKE '%pinned%') DESC, timestamp DESC
        LIMIT 10
        """,
        (current_user.id,),
    ).fetchall()
    recent_notes = []
    for r in recent_rows:
        item = {
            "id": r[0],
            "title": r[1],
            "type": r[2],
            "timestamp": r[3],
            "audio_filename": r[4],
            "status": r[5],
            "tags": r[6],
            "file_filename": r[7],
            "file_type": r[8],
            "file_mime_type": r[9],
        }
        ff = item.get("file_filename")
        ft = (item.get("file_type") or "").lower()
        mt = (item.get("file_mime_type") or "").lower()
        typ = (item.get("type") or "").lower()
        try:
            if ff and (ft == "image" or typ == "image" or mt.startswith("image/") or ft == "document" or mt == "application/pdf"):
                tok = create_file_token(current_user.id, ff, ttl_seconds=600)
                item["file_url"] = f"/files/{ff}?token={tok}"
        except Exception:
            pass
        # Add lightweight metadata for recent list (duration if audio)
        try:
            if (item.get("type") or "").lower() == "audio":
                item["audio_duration_hms"] = _audio_duration_from_note(item)
            item["tz_abbr"] = _tz_abbrev(item.get("timestamp"))
        except Exception:
            pass
        recent_notes.append(item)
    return render_page(
        request,
        "dashboard.html",
        {
            "notes_by_day": dict(notes_by_day),
            "q": q,
            "tag": tag,
            "last_sync": get_last_sync(),
            "user": current_user,
            "recent_notes": recent_notes,
            # Provide a signed SSE token for auth without headers
            "sse_token": create_file_token(current_user.id, "sse")
        },
    )

# =========================
# Resumable Upload Endpoints
# =========================
from pathlib import Path

def _get_incoming_dir() -> Path:
    d = settings.uploads_dir / "incoming"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _get_manifest_path(upload_id: str) -> Path:
    return _get_incoming_dir() / f"{upload_id}.json"

def _get_part_path(upload_id: str) -> Path:
    return _get_incoming_dir() / f"{upload_id}.part"

def _load_manifest(upload_id: str) -> dict | None:
    p = _get_manifest_path(upload_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None

def _save_manifest(upload_id: str, data: dict) -> None:
    p = _get_manifest_path(upload_id)
    p.write_text(json.dumps(data))

@app.post("/upload/init")
async def upload_init(
    request: Request,
    data: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    """Initialize a resumable upload.

    Expects JSON: { filename: str, total_size?: int, mime_type?: str }
    Returns: { upload_id, offset }
    Requires CSRF via X-CSRF-Token header matching cookie.
    """
    csrf_header = request.headers.get("X-CSRF-Token")
    if not validate_csrf(request, csrf_header):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")

    filename = (data or {}).get("filename")
    total_size = (data or {}).get("total_size")
    mime_type = (data or {}).get("mime_type")
    if not filename:
        raise HTTPException(status_code=400, detail="filename required")

    upload_id = uuid.uuid4().hex
    manifest = {
        "upload_id": upload_id,
        "filename": filename,
        "total_size": int(total_size) if total_size is not None else None,
        "mime_type": mime_type,
        "created_by": current_user.id,
        "created_at": datetime.utcnow().isoformat(),
        "status": "active",
    }
    _save_manifest(upload_id, manifest)
    # Ensure empty part file
    _get_part_path(upload_id).write_bytes(b"")
    return {"upload_id": upload_id, "offset": 0}

@app.get("/upload/status")
async def upload_status(
    request: Request,
    upload_id: str,
    current_user: User = Depends(get_current_user),
):
    manifest = _load_manifest(upload_id)
    if not manifest or manifest.get("created_by") != current_user.id:
        raise HTTPException(status_code=404, detail="Upload not found")
    part_path = _get_part_path(upload_id)
    size = part_path.stat().st_size if part_path.exists() else 0
    return {
        "upload_id": upload_id,
        "offset": size,
        "status": manifest.get("status", "active"),
        "filename": manifest.get("filename"),
        "total_size": manifest.get("total_size"),
    }

@app.put("/upload/chunk")
async def upload_chunk(
    request: Request,
    upload_id: str = Query(...),
    offset: int = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Append a chunk to an active upload.

    Query params: upload_id, offset (expected start position)
    Body: raw bytes (Content-Length required)
    CSRF: X-CSRF-Token header required
    """
    csrf_header = request.headers.get("X-CSRF-Token")
    if not validate_csrf(request, csrf_header):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")

    manifest = _load_manifest(upload_id)
    if not manifest or manifest.get("created_by") != current_user.id:
        raise HTTPException(status_code=404, detail="Upload not found")
    if manifest.get("status") != "active":
        raise HTTPException(status_code=400, detail="Upload not active")

    part_path = _get_part_path(upload_id)
    part_path.parent.mkdir(parents=True, exist_ok=True)
    current_size = part_path.stat().st_size if part_path.exists() else 0
    if current_size != int(offset):
        # Client should resume from server-reported offset
        return JSONResponse({"expected_offset": current_size}, status_code=409)

    # Read raw body in chunks and append
    max_size = settings.max_file_size
    total_after = current_size
    try:
        with open(part_path, "ab") as out:
            async for chunk in request.stream():
                if not chunk:
                    continue
                total_after += len(chunk)
                if total_after > max_size:
                    raise HTTPException(status_code=400, detail=f"File too large (>{max_size} bytes)")
                out.write(chunk)
        return {"upload_id": upload_id, "offset": total_after}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chunk append failed: {e}")

@app.post("/upload/finalize")
async def upload_finalize(
    request: Request,
    background_tasks: BackgroundTasks,
    upload_id: str = Body(..., embed=True),
    note: str = Body(""),
    tags: str = Body(""),
    current_user: User = Depends(get_current_user),
):
    """Finalize an upload and create a note, mirroring /capture for files."""
    csrf_header = request.headers.get("X-CSRF-Token")
    if not validate_csrf(request, csrf_header):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")

    manifest = _load_manifest(upload_id)
    if not manifest or manifest.get("created_by") != current_user.id:
        raise HTTPException(status_code=404, detail="Upload not found")
    if manifest.get("status") != "active":
        raise HTTPException(status_code=400, detail="Upload not active")

    part_path = _get_part_path(upload_id)
    if not part_path.exists():
        raise HTTPException(status_code=400, detail="No data uploaded")

    # Process the saved file
    processor = FileProcessor()
    result = processor.process_saved_file(part_path, manifest.get("filename") or "uploaded.bin")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=f"File processing failed: {result.get('error')}")

    manifest["status"] = "finalized"
    _save_manifest(upload_id, manifest)

    file_info = result['file_info']
    note_type = file_info['category']
    stored_filename = result['stored_filename']
    extracted_text = result.get('extracted_text', "")
    file_metadata = {
        'original_filename': file_info['original_filename'],
        'mime_type': file_info['mime_type'],
        'size_bytes': file_info['size_bytes'],
        'processing_type': result['processing_type'],
        'metadata': result.get('metadata'),
    }
    processing_status = "pending" if note_type == 'audio' else "complete"
    content = (note or "").strip()
    if processing_status == "complete" and not content and extracted_text:
        content = extracted_text[:1000]

    title = content[:60] if content else (f"File: {file_info['original_filename']}" if file_info['original_filename'] else "New Note")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Save to database
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT INTO notes (
                title, content, summary, tags, actions, type, timestamp,
                audio_filename, file_filename, file_type, file_mime_type,
                file_size, extracted_text, file_metadata, status, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                content,
                "",
                tags,
                "",
                note_type,
                now,
                stored_filename if note_type == 'audio' else None,
                stored_filename,
                note_type,
                file_metadata.get('mime_type'),
                file_metadata.get('size_bytes'),
                extracted_text,
                json.dumps(file_metadata, default=str) if file_metadata else None,
                processing_status,
                current_user.id,
            ),
        )
        note_id = c.lastrowid
        c.execute(
            """
            INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (note_id, title, "", tags, "", content, extracted_text),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        conn.close()

    # Queue background processing for audio
    try:
        if processing_status == "pending":
            from tasks_enhanced import process_note_with_status
            background_tasks.add_task(process_note_with_status, note_id)
            return {
                "success": True,
                "id": note_id,
                "status": processing_status,
                "file_type": note_type,
                "message": "Upload finalized and queued for processing",
            }
    except Exception:
        pass

    return {"success": True, "id": note_id, "status": processing_status, "file_type": note_type, "message": "Upload finalized"}

@app.post("/api/notes/{note_id}/update")
async def api_update_note(
    note_id: int,
    data: dict = Body(...),
    request: Request = None,
    current_user: User = Depends(get_current_user),
):
    """Lightweight update for title/tags/content with CSRF header.

    Expects header 'X-CSRF-Token' to match cookie 'csrf_token'.
    """
    csrf_header = request.headers.get("X-CSRF-Token") if request else None
    if not validate_csrf(request, csrf_header):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")

@app.get("/api/sse-token")
async def api_sse_token(request: Request):
    """Return a fresh signed SSE token for the current user.

    Used by the frontend to refresh EventSource tokens when a page stays open
    for long periods and the previous token expires.
    """
    user = get_current_user_silent(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Issue a fresh token (8h)
    token = create_file_token(user.id, "sse", ttl_seconds=60*60*8)
    # Support cross-origin consumption similar to SSE endpoints
    origin = request.headers.get('origin')
    headers = {}
    if origin:
        headers.update({
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
            "Access-Control-Allow-Credentials": "true",
        })
    return JSONResponse({"token": token}, headers=headers)

    fields = {k: v for k, v in data.items() if k in {"title", "tags", "content"}}
    if not fields:
        return {"success": False, "message": "No valid fields"}

    conn = get_conn()
    c = conn.cursor()
    # Ensure ownership
    row = c.execute(
        "SELECT id FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user.id),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Note not found")

    # Update main table
    set_parts = []
    params = []
    for k, v in fields.items():
        set_parts.append(f"{k} = ?")
        params.append(v)
    params.extend([note_id, current_user.id])
    c.execute(
        f"UPDATE notes SET {', '.join(set_parts)} WHERE id = ? AND user_id = ?",
        params,
    )

    # Refresh FTS row
    row2 = c.execute(
        "SELECT title, summary, tags, actions, content FROM notes WHERE id = ?",
        (note_id,),
    ).fetchone()
    if row2:
        title, summary, tags, actions, content = row2
        c.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
        c.execute(
            "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, title, summary, tags, actions, content),
        )

    conn.commit()
    conn.close()

    return {"success": True, "note": {"id": note_id, **fields}}

# Enhanced Search Endpoint (now via SearchService)
@app.post("/api/search/enhanced")
async def enhanced_search(
    request: "SearchRequest",
    current_user: User = Depends(get_current_user)
):
    """Enhanced search delegating to the unified SearchService.

    Applies optional filters client-side for tags/type to preserve previous behavior.
    """
    svc = _get_search_service()
    f = request.filters or {}
    mode = _resolve_search_mode(f)
    rows = svc.search(request.query, mode=mode, k=request.limit or 20)
    notes = [{k: row[k] for k in row.keys()} for row in rows]
    # Apply simple filters client-side to match legacy endpoint
    if 'tags' in f and f['tags']:
        tag_q = str(f['tags']).strip()
        notes = [n for n in notes if tag_q in (n.get('tags') or '')]
    if 'type' in f and f['type'] not in {'fts','keyword','semantic','vector','hybrid','both'}:
        notes = [n for n in notes if n.get('type') == f['type']]
    return {
        "results": notes,
        "total": len(notes),
        "query": request.query,
        "mode": mode
    }


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

# Service-based search endpoint using unified adapter
@app.post("/api/search/service")
async def search_service_endpoint(
    request: "SearchRequest",
    current_user: User = Depends(get_current_user)
):
    svc = _get_search_service()
    rows = svc.search(request.query, mode='hybrid', k=request.limit or 20)
    data = [{k: row[k] for k in row.keys()} for row in rows]
    return {
        "success": True,
        "data": data,
        "metadata": {"count": len(data), "mode": "hybrid"}
    }

# Discord Integration
@app.post("/webhook/discord/legacy", include_in_schema=False)
async def webhook_discord_legacy1(
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

# Enhanced Search (now backed by unified SearchService)
@app.post("/api/search")
async def enhanced_search(
    request: SearchRequest,
    current_user: User = Depends(get_current_user)
):
    """Advanced search with filters and semantic similarity via SearchService."""
    svc = _get_search_service()
    mode = _resolve_search_mode(request.filters)
    rows = svc.search(request.query, mode=mode, k=request.limit or 20)
    # Convert sqlite3.Row to dict
    notes = [{k: row[k] for k in row.keys()} for row in rows]
    return {
        "results": notes,
        "total": len(notes),
        "query": request.query,
        "mode": mode
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

# Debug: list recent uploads with file info
@app.get("/api/debug/uploads")
async def debug_recent_uploads(current_user: User = Depends(get_current_user)):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    rows = c.execute(
        """
        SELECT id, title, type, status, file_filename, file_type, file_mime_type, file_size, timestamp
        FROM notes
        WHERE user_id = ? AND file_filename IS NOT NULL AND file_filename != ''
        ORDER BY id DESC
        LIMIT 20
        """,
        (current_user.id,),
    ).fetchall()
    conn.close()
    return {
        "success": True,
        "count": len(rows),
        "items": [dict(r) for r in rows],
    }

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


# Discord Integration
@app.post("/webhook/discord/legacy2", include_in_schema=False)
async def webhook_discord_legacy2(
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
):
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
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
    
    # Enhance with automated similar notes
    try:
        from ui_enhancements import get_ui_enhancer
        enhancer = get_ui_enhancer(str(settings.db_path))
        similar_widget = enhancer.get_similar_notes_widget(note_id, current_user.id, limit=6)
        
        # Convert to format compatible with existing template
        if similar_widget.get("enabled") and similar_widget.get("notes"):
            automated_related = []
            for sim_note in similar_widget["notes"]:
                automated_related.append({
                    "id": sim_note["id"],
                    "title": sim_note["title"],
                    "summary": sim_note["snippet"],
                    "similarity": sim_note["similarity"],
                    "relationship_type": sim_note["relationship_type"]
                })
            
            # Merge with existing related notes, avoiding duplicates
            existing_ids = {r["id"] for r in related}
            for auto_rel in automated_related:
                if auto_rel["id"] not in existing_ids:
                    related.append(auto_rel)
        
    except Exception as e:
        print(f"Failed to enhance detail with similar notes: {e}")
    
    # Build signed file URL if file exists
    file_url = None
    if note.get("file_filename"):
        try:
            tok = create_file_token(current_user.id, note["file_filename"], ttl_seconds=600)
            file_url = f"/files/{note['file_filename']}?token={tok}"
        except Exception:
            file_url = f"/files/{note['file_filename']}"
    return render_page(
        request,
        "detail.html",
        {"note": note, "related": related, "user": current_user, "file_url": file_url},
    )

@app.get("/edit/{note_id}")
def edit_get(
    request: Request,
    note_id: int,
):
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
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
        "edit.html", {"request": request, "note": note, "user": current_user}
    )

@app.post("/edit/{note_id}")
def edit_post(
    request: Request,
    note_id: int,
    content: str = Form(""),
    tags: str = Form(""),
    csrf_token: str = Form(...),
):
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    if not validate_csrf(request, csrf_token):
        return RedirectResponse(f"/edit/{note_id}", status_code=302)
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
    resp = RedirectResponse(f"/detail/{note_id}", status_code=302)
    set_flash(resp, "Note updated", "success")
    return resp

@app.post("/delete/{note_id}")
def delete_note(
    request: Request,
    note_id: int,
    csrf_token: str = Form(...),
):
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    if not validate_csrf(request, csrf_token):
        return RedirectResponse("/", status_code=302)
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
    resp = RedirectResponse("/", status_code=302)
    set_flash(resp, "Note deleted", "success")
    return resp

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

@app.get("/files/{filename}")
def get_file(filename: str, request: Request, token: str | None = None):
    """Serve uploaded files (images, PDFs, etc.) with auth.

    AuthN strategies:
    - Cookie-based session (preferred, same-origin)
    - Signed URL token (?token=...) for when cookies are not sent
    """
    import mimetypes

    # 1) Cookie/session-based auth (same origin)
    current_user = get_current_user_silent(request)

    # 2) Fallback to signed file token if no user from cookie
    if not current_user and token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            uid = payload.get("uid")
            fn = payload.get("fn")
            if not uid or not fn or fn != filename:
                raise HTTPException(status_code=401, detail="Invalid token")
            # Lookup user from id
            conn = get_conn()
            c = conn.cursor()
            urow = c.execute("SELECT id, username, hashed_password FROM users WHERE id=?", (uid,)).fetchone()
            conn.close()
            if not urow:
                raise HTTPException(status_code=401, detail="User not found")
            current_user = UserInDB(id=urow[0], username=urow[1], hashed_password=urow[2])
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Verify file belongs to this user
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT file_type, file_mime_type FROM notes WHERE file_filename = ? AND user_id = ?",
        (filename, current_user.id),
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="File not found")

    file_type, mime_type = row

    # Determine file path based on type
    if file_type == 'audio':
        file_path = settings.audio_dir / filename
    else:
        file_path = settings.uploads_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Determine content type
    content_type = mime_type or mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream'

    # If caller explicitly requests download, set Content-Disposition via filename.
    # Otherwise, omit filename so the browser renders inline (images/PDFs in <img>/<embed>). 
    if request.query_params.get('download'):
        return FileResponse(
            str(file_path),
            media_type=content_type,
            filename=filename,
        )
    else:
        return FileResponse(
            str(file_path),
            media_type=content_type,
        )

@app.post("/capture")
async def capture(
    request: Request,
    background_tasks: BackgroundTasks,
    note: str = Form(""),
    tags: str = Form(""),
    file: UploadFile = File(None),
    csrf_token: str | None = Form(None),
):
    """Enhanced capture endpoint with multi-file type support"""
    import logging
    logger = logging.getLogger(__name__)
    
    # Auth validation
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    
    # CSRF validation
    csrf_valid = validate_csrf(request, csrf_token)
    if not csrf_valid:
        header_token = request.headers.get("X-CSRF-Token")
        if header_token:
            csrf_valid = validate_csrf(request, header_token)
    
    if not csrf_valid:
        error_msg = "CSRF token validation failed"
        if "application/json" in request.headers.get("accept", ""):
            raise HTTPException(status_code=400, detail=error_msg)
        return RedirectResponse("/", status_code=302)
    
    # Process the submission
    content = note.strip()
    note_type = "text"  # Default type
    stored_filename = None
    extracted_text = ""
    file_metadata = {}
    processing_status = "complete"  # Text notes are complete immediately
    source_url = None
    web_metadata = None
    screenshot_path = None
    content_hash = None
    
    # Check for web links in content (NEW WEB INGESTION FEATURE)
    if content and not file:  # Only check text content, not files
        try:
            from url_utils import extract_main_urls
            from web_extractor import extract_web_content_sync
            import hashlib
            
            urls = extract_main_urls(content)
            if urls:
                # For now, extract content from the first URL found
                url = urls[0]
                logger.info(f"Detected URL in content: {url}")
                
                # Extract web content
                web_result = extract_web_content_sync(url)
                
                if web_result.success:
                    logger.info(f"Successfully extracted web content from {url}")
                    # Update note with web content
                    note_type = "web_content"
                    source_url = url
                    content_hash = hashlib.sha256(web_result.content.encode() if web_result.content else b"").hexdigest()[:16]
                    screenshot_path = web_result.screenshot_path
                    
                    # Store web metadata
                    web_metadata = {
                        'url': url,
                        'title': web_result.title,
                        'extraction_time': web_result.extraction_time,
                        'content_length': len(web_result.content) if web_result.content else 0,
                        'metadata': web_result.metadata
                    }
                    
                    # Use extracted content if available
                    if web_result.content:
                        extracted_text = web_result.content
                        # Keep original pasted content but add extracted content
                        content = f"Original: {content}\n\n--- Extracted Content ---\n{web_result.text_content[:2000]}"
                        if len(web_result.text_content) > 2000:
                            content += "...\n[Content truncated - see full content in extracted_text field]"
                    
                    # Set processing status
                    processing_status = "complete"
                    
                    logger.info(f"Web content extraction successful for {url}")
                else:
                    logger.warning(f"Failed to extract web content from {url}: {web_result.error_message}")
                    # Still save the URL for reference
                    source_url = url
                    web_metadata = {'url': url, 'error': web_result.error_message}
                    
        except Exception as e:
            import traceback
            logger.error(f"Web content extraction failed: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Continue with normal processing if web extraction fails
    
    # Handle file upload if present
    if file and file.filename:
        try:
            # Stream file to a temporary path to keep memory flat
            import uuid
            tmp_dir = settings.uploads_dir
            tmp_dir.mkdir(exist_ok=True)
            tmp_path = tmp_dir / f"upload-{uuid.uuid4().hex}.part"
            size = 0
            CHUNK = 1024 * 1024  # 1MB
            with open(tmp_path, 'wb') as out:
                while True:
                    chunk = await file.read(CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > settings.max_file_size:
                        out.flush()
                        out.close()
                        try:
                            tmp_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        error_msg = f"File too large ({size} bytes, max {settings.max_file_size})"
                        if "application/json" in request.headers.get("accept", ""):
                            raise HTTPException(status_code=400, detail=error_msg)
                        return RedirectResponse("/?error=" + error_msg, status_code=302)
                    out.write(chunk)

            # Process saved file
            processor = FileProcessor()
            result = processor.process_saved_file(tmp_path, file.filename)
            
            if not result['success']:
                error_msg = f"File processing failed: {result['error']}"
                if "application/json" in request.headers.get("accept", ""):
                    raise HTTPException(status_code=400, detail=error_msg)
                return RedirectResponse("/?error=" + error_msg, status_code=302)
            
            # Update note details based on file processing
            file_info = result['file_info']
            note_type = file_info['category']
            stored_filename = result['stored_filename']
            extracted_text = result['extracted_text']
            file_metadata = {
                'original_filename': file_info['original_filename'],
                'mime_type': file_info['mime_type'],
                'size_bytes': file_info['size_bytes'],
                'processing_type': result['processing_type'],
                'metadata': result['metadata']
            }
            
            # Set processing status based on file type
            if note_type == 'audio':
                processing_status = "pending"  # Audio needs transcription
            else:
                processing_status = "complete"  # Images/PDFs are processed immediately
                # Use extracted text as content if no manual note provided
                if not content and extracted_text:
                    content = extracted_text[:1000]  # Limit initial content
                    
        except Exception as e:
            import traceback
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"File upload failed: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            error_msg = f"File upload failed: {str(e)}"
            if "application/json" in request.headers.get("accept", ""):
                raise HTTPException(status_code=400, detail=error_msg)
            return RedirectResponse("/?error=" + error_msg, status_code=302)
    
    # Generate title and prepare for database
    title = content[:60] if content else (
        f"File: {file.filename}" if file and file.filename else "New Note"
    )
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Save to database
    conn = get_conn()
    c = conn.cursor()
    
    try:
        # Insert main note record
        c.execute("""
            INSERT INTO notes (
                title, content, summary, tags, actions, type, timestamp, 
                audio_filename, file_filename, file_type, file_mime_type, 
                file_size, extracted_text, file_metadata, status, user_id,
                source_url, web_metadata, screenshot_path, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            title,
            content,
            "",  # summary will be generated later
            tags,
            "",  # actions will be generated later
            note_type,
            now,
            stored_filename if note_type == 'audio' else None,  # legacy audio field
            stored_filename,  # new generic file field
            note_type,
            file_metadata.get('mime_type') if file_metadata else None,
            file_metadata.get('size_bytes') if file_metadata else None,
            extracted_text,
            json.dumps(file_metadata, default=str) if file_metadata else None,
            processing_status,
            current_user.id,
            source_url,
            json.dumps(web_metadata, default=str) if web_metadata else None,
            screenshot_path,
            content_hash
        ))
        
        note_id = c.lastrowid
        
        # Insert into FTS
        c.execute("""
            INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (note_id, title, "", tags, "", content, extracted_text))
        
        conn.commit()
        
        # Trigger automated relationship discovery (TEMPORARILY DISABLED)
        # try:
        #     automation_engine = getattr(app.state, 'automation_engine', None)
        #     if automation_engine:
        #         await automation_engine.on_note_created(note_id, current_user.id)
        # except Exception as e:
        #     print(f"Automation trigger failed: {e}")
        
        # Queue background processing if needed
        if processing_status == "pending":
            from tasks_enhanced import process_note_with_status
            background_tasks.add_task(
                process_note_with_status,
                note_id
            )
        
        # Return success response
        if "application/json" in request.headers.get("accept", ""):
            return {
                "success": True, 
                "id": note_id,
                "status": processing_status,
                "file_type": note_type,
                "extracted_text_length": len(extracted_text),
                "message": f"{'File uploaded and queued for processing' if processing_status == 'pending' else 'Note saved successfully'}"
            }
        else:
            success_msg = f"Note saved successfully"
            if processing_status == "pending":
                success_msg += " and queued for processing"
            return RedirectResponse(f"/?success={success_msg}", status_code=302)
            
    except Exception as e:
        conn.rollback()
        import logging, traceback
        logging.getLogger(__name__).error("Database insert failed in /capture: %s", e)
        logging.getLogger(__name__).error("Traceback:\n%s", traceback.format_exc())
        error_msg = f"Database error: {str(e)}"
        if "application/json" in request.headers.get("accept", ""):
            raise HTTPException(status_code=500, detail=error_msg)
        return RedirectResponse("/?error=" + error_msg, status_code=302)
    finally:
        conn.close()

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

# Obsidian Sync API
@app.post("/api/obsidian/sync")
async def obsidian_sync_api(
    background_tasks: BackgroundTasks,
    direction: str = Query("to_obsidian"),
    current_user: User = Depends(get_current_user),
):
    """Sync with Obsidian vault via ObsidianSync class.

    direction: one of 'to_obsidian', 'from_obsidian', 'bidirectional'
    """
    from obsidian_sync import ObsidianSync

    def perform_sync(user_id: int, sync_direction: str):
        if sync_direction not in {"to_obsidian", "from_obsidian", "bidirectional"}:
            raise HTTPException(status_code=400, detail="Invalid direction")
        sync = ObsidianSync()
        if sync_direction == "to_obsidian":
            result = {"exported": sync.sync_all_to_obsidian(user_id)}
        elif sync_direction == "from_obsidian":
            result = {"imported": sync.sync_from_obsidian()}
        else:
            result = sync.bidirectional_sync(user_id)
        # record last sync timestamp
        set_last_sync(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return result

    background_tasks.add_task(perform_sync, current_user.id, direction)
    return {"status": "sync_started", "direction": direction}

@app.get("/api/obsidian/status")
async def obsidian_status_api(current_user: User = Depends(get_current_user)):
    from obsidian_sync import ObsidianSync
    sync = ObsidianSync()
    # Count vault files
    try:
        vault_files = len(list(sync.vault_path.rglob("*.md")))
    except Exception:
        vault_files = 0
    # Count notes
    conn = get_conn()
    c = conn.cursor()
    db_notes = c.execute(
        "SELECT COUNT(*) FROM notes WHERE user_id = ?",
        (current_user.id,),
    ).fetchone()[0]
    conn.close()
    return {
        "vault_path": str(sync.vault_path),
        "vault_files": vault_files,
        "database_notes": db_notes,
        "last_sync": get_last_sync(),
    }

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


# Add these endpoints before the health check
@app.post("/api/search/enhanced_legacy", include_in_schema=False)
async def enhanced_search_legacy(
    q: str = Query(..., description="Search query"),
    type: str = Query("hybrid", description="Search type: fts, semantic, or hybrid"),
    limit: int = Query(20, description="Number of results"),
    current_user: User = Depends(get_current_user)
):
    """Deprecated: legacy enhanced search. Delegates to SearchService."""
    svc = _get_search_service()
    mode = 'hybrid'
    if type in {'fts','keyword'}:
        mode = 'keyword'
    elif type in {'semantic','vector'}:
        mode = 'semantic'
    rows = svc.search(q, mode=mode, k=limit or 20)
    results = [
        {
            "id": r["id"],
            "title": r.get("title"),
            "summary": r.get("summary") if "summary" in r.keys() else r.get("body"),
            "tags": r.get("tags"),
            "timestamp": r.get("updated_at") or r.get("created_at"),
            "score": None,
            "snippet": None,
            "match_type": mode,
        }
        for r in rows
    ]
    return {
        "query": q,
        "results": results,
        "total": len(results),
        "search_type": type,
        "deprecated": True,
    }

@app.post("/webhook/discord")
async def webhook_discord(
    data: dict = Body(...),
    current_user: User = Depends(get_current_user)
):
    # Discord webhook implementation
    note = data.get("note", "")
    tags = data.get("tags", "")
    note_type = data.get("type", "discord")
    
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

@app.get("/health")
def health():
    conn = get_conn()
    c = conn.cursor()
    tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    return {"tables": [t[0] for t in tables]}

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
    
    # Trigger automated relationship discovery
    try:
        automation_engine = getattr(app.state, 'automation_engine', None)
        if automation_engine:
            await automation_engine.on_note_created(note_id, current_user.id)
    except Exception as e:
        print(f"Browser capture automation trigger failed: {e}")
    
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

@app.get("/api/queue/status")
async def queue_status(request: Request):
    """Report simple FIFO queue status for this user.

    If unauthenticated, return zeros (200 OK) to avoid noisy 401 logs from background polling.
    """
    origin = request.headers.get('origin')
    user = get_current_user_silent(request)
    if not user:
        payload = {"pending": 0, "processing": 0, "complete": 0}
        if origin:
            return JSONResponse(payload, headers={
                "Access-Control-Allow-Origin": origin,
                "Vary": "Origin",
                "Access-Control-Allow-Credentials": "true",
            })
        return payload
    conn = get_conn()
    c = conn.cursor()
    pending = c.execute("SELECT COUNT(*) FROM notes WHERE user_id=? AND status='pending'", (user.id,)).fetchone()[0]
    processing = c.execute("SELECT COUNT(*) FROM notes WHERE user_id=? AND status='processing'", (user.id,)).fetchone()[0]
    completed = c.execute("SELECT COUNT(*) FROM notes WHERE user_id=? AND status='complete'", (user.id,)).fetchone()[0]
    conn.close()
    payload = {"pending": pending, "processing": processing, "complete": completed}
    if origin:
        return JSONResponse(payload, headers={
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
            "Access-Control-Allow-Credentials": "true",
        })
    return payload

@app.post("/api/notes/{note_id}/retry")
async def retry_note(note_id: int, current_user: User = Depends(get_current_user)):
    """Reset a failed note back to pending so the worker picks it up again."""
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT status, user_id FROM notes WHERE id=?", (note_id,)).fetchone()
    if not row or row[1] != current_user.id:
        conn.close()
        raise HTTPException(status_code=404, detail="Note not found")
    status = row[0] or ''
    if status.startswith('processing') or status == 'processing':
        conn.close()
        raise HTTPException(status_code=400, detail="Already processing")
    if status == 'pending':
        conn.close()
        return {"ok": True, "status": status}
    c.execute("UPDATE notes SET status='pending' WHERE id=?", (note_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "status": "pending"}

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

# ---- Enhanced Note API Endpoints ----

@app.get("/api/tags")
async def get_all_tags(current_user: User = Depends(get_current_user)):
    """Get all unique tags for autocomplete"""
    conn = get_conn()
    c = conn.cursor()
    
    # Get all tags from user's notes
    rows = c.execute("""
        SELECT DISTINCT tags 
        FROM notes 
        WHERE user_id = ? AND tags IS NOT NULL AND tags != ''
    """, (current_user.id,)).fetchall()
    
    # Extract individual tags
    all_tags = set()
    for row in rows:
        if row[0]:
            tags = [tag.strip() for tag in row[0].split(',') if tag.strip()]
            all_tags.update(tags)
    
    conn.close()
    return sorted(list(all_tags))

@app.patch("/api/notes/{note_id}")
async def update_note_partial(
    note_id: int,
    update_data: dict = Body(...),
    current_user: User = Depends(get_current_user)
):
    """Partially update a note (for auto-save)"""
    conn = get_conn()
    c = conn.cursor()
    
    # Check if note belongs to user
    note = c.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", 
                    (note_id, current_user.id)).fetchone()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Build update query for non-null fields
    updates = []
    params = []
    
    if 'title' in update_data and update_data['title'] is not None:
        updates.append("title = ?")
        params.append(update_data['title'])
    
    if 'content' in update_data and update_data['content'] is not None:
        updates.append("content = ?")
        params.append(update_data['content'])
    
    if 'tags' in update_data and update_data['tags'] is not None:
        updates.append("tags = ?")
        params.append(update_data['tags'])
    
    if updates:
        # Add timestamp update
        updates.append("timestamp = ?")
        params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        query = f"UPDATE notes SET {', '.join(updates)} WHERE id = ? AND user_id = ?"
        params.extend([note_id, current_user.id])
        
        c.execute(query, params)
        conn.commit()
    
    conn.close()
    return {"status": "success", "message": "Note updated"}

@app.put("/api/notes/{note_id}")
async def update_note_full(
    note_id: int,
    update_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Fully update a note"""
    conn = get_conn()
    c = conn.cursor()
    
    # Check if note belongs to user
    note = c.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", 
                    (note_id, current_user.id)).fetchone()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Update note
    c.execute("""
        UPDATE notes 
        SET title = ?, content = ?, tags = ?, timestamp = ?
        WHERE id = ? AND user_id = ?
    """, (
        update_data.get('title', ''),
        update_data.get('content', ''),
        update_data.get('tags', ''),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        note_id,
        current_user.id
    ))
    
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": "Note saved"}

@app.delete("/api/notes/{note_id}")
async def delete_note_api(note_id: int, current_user: User = Depends(get_current_user)):
    """Delete a note via API"""
    conn = get_conn()
    c = conn.cursor()
    
    # Check if note belongs to user
    note = c.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", 
                    (note_id, current_user.id)).fetchone()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Delete the note
    c.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, current_user.id))
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": "Note deleted"}

@app.get("/api/notes/{note_id}/export")
async def export_note(
    note_id: int,
    format: str = Query("markdown", regex="^(markdown|json|txt)$"),
    current_user: User = Depends(get_current_user)
):
    """Export note in various formats"""
    conn = get_conn()
    c = conn.cursor()
    
    # Get note
    note = c.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", 
                    (note_id, current_user.id)).fetchone()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Convert to dict
    note_dict = dict(zip([col[0] for col in c.description], note))
    conn.close()
    
    # Generate export content based on format
    if format == "markdown":
        content = generate_markdown_export(note_dict)
        filename = f"{safe_filename(note_dict['title'] or 'note')}.md"
        media_type = "text/markdown"
    elif format == "json":
        content = json.dumps(note_dict, indent=2, default=str)
        filename = f"{safe_filename(note_dict['title'] or 'note')}.json"
        media_type = "application/json"
    elif format == "txt":
        content = generate_text_export(note_dict)
        filename = f"{safe_filename(note_dict['title'] or 'note')}.txt"
        media_type = "text/plain"
    
    # Return file response
    from fastapi.responses import Response
    return Response(
        content=content.encode('utf-8'),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/notes/{note_id}/duplicate")
async def duplicate_note(note_id: int, current_user: User = Depends(get_current_user)):
    """Duplicate a note"""
    conn = get_conn()
    c = conn.cursor()
    
    # Get original note
    note = c.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", 
                    (note_id, current_user.id)).fetchone()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Convert to dict
    note_dict = dict(zip([col[0] for col in c.description], note))
    
    # Create duplicate
    new_title = f"{note_dict['title']} (Copy)" if note_dict['title'] else "Untitled Note (Copy)"
    
    c.execute("""
        INSERT INTO notes 
        (user_id, title, content, summary, actions, tags, type, audio_filename, status, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        current_user.id,
        new_title,
        note_dict.get('content', ''),
        note_dict.get('summary', ''),
        note_dict.get('actions', ''),
        note_dict.get('tags', ''),
        note_dict.get('type', 'text'),
        None,  # Don't duplicate audio files
        'complete',
        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ))
    
    new_note_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return {"id": new_note_id, "status": "success", "message": "Note duplicated"}

@app.post("/api/notes/{note_id}/sync-obsidian")
async def sync_note_to_obsidian(note_id: int, current_user: User = Depends(get_current_user)):
    """Sync a single note to Obsidian"""
    conn = get_conn()
    c = conn.cursor()
    
    # Get note
    note = c.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", 
                    (note_id, current_user.id)).fetchone()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Convert to dict
    note_dict = dict(zip([col[0] for col in c.description], note))
    conn.close()
    
    try:
        # Use existing Obsidian sync functionality
        sync = ObsidianSync()
        filename = safe_filename(note_dict['title'] or f'note_{note_id}')
        
        # Generate markdown content
        markdown_content = generate_markdown_export(note_dict)
        
        # Save to Obsidian vault
        success = await sync.save_note_to_obsidian(filename, markdown_content)
        
        if success:
            return {"status": "success", "message": "Note synced to Obsidian"}
        else:
            raise HTTPException(status_code=500, detail="Failed to sync to Obsidian")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Obsidian sync error: {str(e)}")

def generate_markdown_export(note_dict):
    """Generate markdown export of a note"""
    lines = []
    
    # Title
    if note_dict.get('title'):
        lines.append(f"# {note_dict['title']}")
        lines.append("")
    
    # Metadata
    lines.append("---")
    lines.append(f"created: {note_dict.get('timestamp', '')}")
    lines.append(f"type: {note_dict.get('type', 'text')}")
    if note_dict.get('tags'):
        lines.append(f"tags: {note_dict['tags']}")
    lines.append("---")
    lines.append("")
    
    # Summary
    if note_dict.get('summary'):
        lines.append("## Summary")
        lines.append("")
        lines.append(note_dict['summary'])
        lines.append("")
    
    # Actions
    if note_dict.get('actions'):
        lines.append("## Action Items")
        lines.append("")
        for action in note_dict['actions'].split('\n'):
            if action.strip():
                lines.append(f"- {action.strip()}")
        lines.append("")
    
    # Content
    if note_dict.get('content'):
        lines.append("## Content")
        lines.append("")
        lines.append(note_dict['content'])
    
    return "\n".join(lines)

def generate_text_export(note_dict):
    """Generate plain text export of a note"""
    lines = []
    
    # Title
    if note_dict.get('title'):
        lines.append(note_dict['title'])
        lines.append("=" * len(note_dict['title']))
        lines.append("")
    
    # Metadata
    lines.append(f"Created: {note_dict.get('timestamp', '')}")
    lines.append(f"Type: {note_dict.get('type', 'text')}")
    if note_dict.get('tags'):
        lines.append(f"Tags: {note_dict['tags']}")
    lines.append("")
    
    # Summary
    if note_dict.get('summary'):
        lines.append("SUMMARY")
        lines.append("-------")
        lines.append(note_dict['summary'])
        lines.append("")
    
    # Actions
    if note_dict.get('actions'):
        lines.append("ACTION ITEMS")
        lines.append("-----------")
        for action in note_dict['actions'].split('\n'):
            if action.strip():
                lines.append(f"• {action.strip()}")
        lines.append("")
    
    # Content
    if note_dict.get('content'):
        lines.append("CONTENT")
        lines.append("-------")
        lines.append(note_dict['content'])
    
    return "\n".join(lines)
