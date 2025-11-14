# Legacy search_engine removed from app imports; unified service is used instead
from schemas.discord import DiscordWebhook
from services.auth_service import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from discord_bot import SecondBrainCog
from obsidian_sync import ObsidianSync
from file_processor import FileProcessor
import sqlite3
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
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
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse, Response, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
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
from services.audio_queue import audio_queue
from services.auth_service import AuthService, Token, TokenData, User, UserInDB, oauth2_scheme, auth_scheme, verify_webhook_token, router as auth_router, init_auth_router
from services.webhook_service import WebhookService
from services.upload_service import UploadService
from services.analytics_service import AnalyticsService
from services.notification_service import get_notification_service, notify_processing_started, notify_processing_completed, notify_processing_failed, notify_note_created
from services.notification_router import router as notification_router, init_notification_router
from services.websocket_manager import get_connection_manager
from services.realtime_events import notify_note_update, schedule_note_update
from services.web_ingestion_service import WebIngestionService

try:
    from realtime_status import create_status_endpoint
    REALTIME_AVAILABLE = True
except ImportError:
    REALTIME_AVAILABLE = False

# Enhanced processing is optional; fall back gracefully if unavailable
try:
    from tasks_enhanced import process_note_with_status  # type: ignore
except ImportError:
    process_note_with_status = None  # type: ignore
from markupsafe import Markup, escape
from bs4 import BeautifulSoup
import re
from config import settings
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel
from markdown_writer import save_markdown, safe_filename
from audio_utils import transcribe_audio
from typing import Optional, List, Dict

# ---- Security Middleware Classes ----

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Security headers for production deployment
        # Allow-listed CDNs needed by our templates (Tailwind + Google Fonts)
        tailwind_cdn = "https://cdn.tailwindcss.com"
        gfonts_css = "https://fonts.googleapis.com"
        gfonts_static = "https://fonts.gstatic.com"

        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            # Production CSP: locked down but allow required CDNs
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                f"script-src 'self' 'unsafe-inline' 'unsafe-eval' {tailwind_cdn}; "
                f"style-src 'self' 'unsafe-inline' {gfonts_css}; "
                "img-src 'self' data: blob:; "
                f"font-src 'self' data: {gfonts_static}; "
                "connect-src 'self'; "
                "media-src 'self' blob:; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "frame-ancestors 'none'"
            )
        else:
            # More permissive CSP for development to unblock local testing
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                f"script-src 'self' 'unsafe-inline' 'unsafe-eval' {tailwind_cdn}; "
                f"style-src 'self' 'unsafe-inline' {gfonts_css}; "
                "img-src 'self' data: blob:; "
                f"font-src 'self' data: {gfonts_static}; "
                "connect-src 'self' ws: wss:; "
                "media-src 'self' blob:; "
                "object-src 'none'"
            )
        
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=(), "
            "accelerometer=(), ambient-light-sensor=()"
        )
        
        return response
# ---- FastAPI Setup with Lifespan ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await _startup_tasks()
    yield
    # Shutdown
    await _shutdown_tasks()

async def _startup_tasks():
    """Combined startup tasks from legacy on_event handlers"""
    # Ensure directories exist
    _ensure_base_directories()

    # Start background workers
    await _start_worker()
    await _start_automation()
    await _start_audio_worker()

    # Initialize memory system
    await _init_memory_system()

app = FastAPI(lifespan=lifespan)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---- Security Middleware Configuration ----

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)

# Add rate limiting middleware
app.add_middleware(SlowAPIMiddleware)

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

templates = Jinja2Templates(directory=str(settings.base_dir / "templates"))
app.mount("/static", StaticFiles(directory=str(settings.base_dir / "static")), name="static")

# Register real-time status endpoints (if module is available)
if REALTIME_AVAILABLE:
    try:
        create_status_endpoint(app)
    except Exception:
        # Non-fatal if realtime endpoints cannot be registered
        pass

def _ensure_base_directories():
    """Ensure base filesystem locations exist for vault/uploads/audio.

    Handles relative paths in .env by anchoring to the project base directory.
    """
    try:
        # Uploads and audio (app-local)
        pathlib.Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)
        pathlib.Path(settings.audio_dir).mkdir(parents=True, exist_ok=True)
        pathlib.Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
        pathlib.Path(settings.snapshots_dir).mkdir(parents=True, exist_ok=True)
        pathlib.Path(settings.videos_dir).mkdir(parents=True, exist_ok=True)
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

# Date formatting filter for HTMX templates
def format_datetime(value):
    """Format datetime string for display"""
    if not value:
        return ""
    try:
        from datetime import datetime
        if isinstance(value, str):
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        else:
            dt = value

        # Format as "Jan 1, 2024 at 3:45 PM"
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except Exception:
        return str(value)

templates.env.filters['format_datetime'] = format_datetime

def get_conn():
    return sqlite3.connect(str(settings.db_path))

# --- Service instances ---
auth_service = AuthService(get_conn)
webhook_service = WebhookService(get_conn, auth_service)
upload_service = UploadService(get_conn, auth_service, audio_queue)
analytics_service = AnalyticsService(get_conn)

# Access auth constants from service
#ACCESS_TOKEN_EXPIRE_MINUTES = auth_service.ACCESS_TOKEN_EXPIRE_MINUTES
#SECRET_KEY = auth_service.SECRET_KEY
#ALGORITHM = auth_service.ALGORITHM

# --- Search helpers moved to services/search_router.py ---

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
    # Ensure SSE token placeholder is available for templates. The client now
    # relies on cookie-authenticated EventSource connections, so we no longer
    # issue signed tokens by default.
    ctx["sse_token"] = ""
    try:
        u = ctx.get("user") or get_current_user_silent(request)
        if u and "user" not in ctx:
            ctx["user"] = u
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
        "SELECT title, COALESCE(body, content) as content, COALESCE(timestamp, created_at) as ts FROM notes WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    for title, content, ts in rows:
        file_ts = ts.replace(":", "-").replace(" ", "_") if ts else datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        fname = f"{file_ts}-{safe_filename(title or 'note')}.md"
        save_markdown(title or "", content or "", fname)
    set_last_sync(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    conn.close()

# Auth setup moved to services/auth_service.py

# Auth models and functions moved to services/auth_service.py

# Enhanced data models
# Webhook models moved to services/webhook_service.py

# Service-based search endpoint using unified adapter

# All auth functions moved to services/auth_service.py

# Convenient function aliases that delegate to auth service
def validate_csrf(request: Request, csrf_token: Optional[str]) -> bool:
    return auth_service.validate_csrf(request, csrf_token)

def create_file_token(user_id: int, filename: str, ttl_seconds: int = 600) -> str:
    return auth_service.create_file_token(user_id, filename, ttl_seconds)

def get_current_user_silent(request: Request) -> Optional[User]:
    return auth_service.get_current_user_silent(request)

async def get_current_user(request: Request, token: Optional[str] = None):
    return await auth_service.get_current_user(request, token)

def authenticate_user(username: str, password: str):
    return auth_service.authenticate_user(username, password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    return auth_service.create_access_token(data, expires_delta)

def get_password_hash(password: str) -> str:
    return auth_service.get_password_hash(password)

def get_user_by_email(email: str) -> Optional[UserInDB]:
    return auth_service.get_user_by_email(email)

def create_magic_link_token() -> str:
    return auth_service.create_magic_link_token()

def store_magic_link_token(email: str, token: str, expires_minutes: int = 15) -> bool:
    return auth_service.store_magic_link_token(email, token, expires_minutes)

def validate_magic_link_token(token: str) -> Optional[str]:
    return auth_service.validate_magic_link_token(token)

def send_magic_link_email(email: str, token: str, request_url: str) -> bool:
    return auth_service.send_magic_link_email(email, token, request_url)

def cleanup_expired_magic_links():
    return auth_service.cleanup_expired_magic_links()

def get_current_user_from_discord_header(authorization: str = Header(None)) -> User:
    return auth_service.get_current_user_from_discord(authorization)

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
    
    # Ensure columns exist (compatibility with legacy schema)
    cols = [row[1] for row in c.execute("PRAGMA table_info(notes)")]
    if 'status' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN status TEXT DEFAULT 'complete'")
        c.execute("UPDATE notes SET status='complete' WHERE status IS NULL")
    if 'user_id' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN user_id INTEGER")
    # Legacy content fields expected by various services/routes
    if 'summary' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN summary TEXT")
    if 'content' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN content TEXT")
    if 'timestamp' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN timestamp TEXT")
    if 'type' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN type TEXT")
    if 'audio_filename' not in cols:
        c.execute("ALTER TABLE notes ADD COLUMN audio_filename TEXT")
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

    # One-time backfill: align legacy fields to core schema
    try:
        c.execute("UPDATE notes SET body=COALESCE(content, '') WHERE (body IS NULL OR body='') AND content IS NOT NULL")
    except Exception:
        pass
    try:
        c.execute("UPDATE notes SET timestamp = COALESCE(timestamp, created_at) WHERE timestamp IS NULL")
    except Exception:
        pass

    # Update FTS if needed: ensure FTS matches core schema: (title, body, tags)
    try:
        fts_cols = [row[1] for row in c.execute("PRAGMA table_info(notes_fts)")]
    except sqlite3.OperationalError:
        fts_cols = []
    # Drop/recreate FTS if columns don't match expected core set
    expected_fts = {"title", "body", "tags"}
    if set(fts_cols) != expected_fts:
        c.execute("DROP TABLE IF EXISTS notes_fts")
        c.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
              title, body, tags,
              content='notes', content_rowid='id'
            )
        ''')
        # Populate FTS from notes; prefer body, fall back to content
        rows = c.execute(
            "SELECT id, title, CASE WHEN COALESCE(body,'') <> '' THEN body ELSE COALESCE(content,'') END AS body, tags FROM notes"
        ).fetchall()
        if rows:
            c.executemany(
                "INSERT INTO notes_fts(rowid, title, body, tags) VALUES (?, ?, ?, ?)",
                rows,
            )

    # Ensure notes_fts5 population only if table exists (legacy advanced search)
    try:
        exists_fts5 = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='notes_fts5'"
        ).fetchone()
        if exists_fts5:
            count_fts5 = c.execute("SELECT count(*) FROM notes_fts5").fetchone()[0]
            if count_fts5 == 0:
                rows5 = c.execute("SELECT id, title, content, summary, tags, actions FROM notes").fetchall()
                if rows5:
                    c.executemany(
                        "INSERT INTO notes_fts5(rowid, title, content, summary, tags, actions) VALUES (?, ?, ?, ?, ?, ?)",
                        rows5,
                    )
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()

init_db()

# --- Include Search Router ---
from services.search_router import router as search_router, init_search_router
init_search_router(get_conn, get_current_user, get_current_user_silent)  # Initialize with functions
app.include_router(search_router)

# --- Include Auth Router ---
init_auth_router(get_conn, render_page, set_flash, auth_service)
app.include_router(auth_router)

# --- Include Smart Automation Router ---
from services.smart_automation_router import router as automation_router, init_smart_automation_router
init_smart_automation_router(get_conn)
app.include_router(automation_router)

# --- Include Web Ingestion Router ---
from services.web_ingestion_router import router as web_router, init_web_ingestion_router
from services.workflow_engine import WorkflowEngine
workflow_engine = WorkflowEngine(get_conn)
init_web_ingestion_router(get_conn, workflow_engine, get_current_user)
app.include_router(web_router)

# --- Include Apple Shortcuts Router ---
from services.apple_shortcuts_router import router as shortcuts_router, init_apple_shortcuts_router
init_apple_shortcuts_router(get_conn, get_current_user)
app.include_router(shortcuts_router)

# --- Smart Templates Router archived ---
# init_smart_templates_router(get_conn, get_current_user)
# app.include_router(templates_router)

# --- Include Bulk Operations Router ---
from services.bulk_operations_router import router as bulk_router, init_bulk_operations_router
init_bulk_operations_router(get_conn, get_current_user)
app.include_router(bulk_router)

# --- Include GitHub Integration Router ---
from services.github_integration_router import router as github_router, init_github_integration_router
init_github_integration_router(get_conn, get_current_user)
app.include_router(github_router)

# --- Include ArXiv Integration Router ---
from services.arxiv_integration_router import router as arxiv_router, init_arxiv_integration_router
init_arxiv_integration_router(get_conn, get_current_user)
app.include_router(arxiv_router)

# --- Include Mobile Capture Router ---
from services.mobile_capture_router import router as mobile_router, init_mobile_capture_router
init_mobile_capture_router(get_conn, get_current_user)
app.include_router(mobile_router)

# --- Include Unified Search Router ---
from services.search_router import router as search_router, init_search_router
init_search_router(get_conn, get_current_user, get_current_user_silent)
app.include_router(search_router)

# --- Include Diagnostics Router ---
from services.diagnostics_router import router as diagnostics_router, init_diagnostics_router
init_diagnostics_router(get_conn, get_current_user)
app.include_router(diagnostics_router)

# --- Include Search Benchmarking Router ---
# ---- Advanced Capture Router ----
from services.advanced_capture_router import router as advanced_capture_router, init_advanced_capture_router
init_advanced_capture_router(get_conn)
app.include_router(advanced_capture_router)

# ---- Enhanced Apple Shortcuts Router ----
from services.enhanced_apple_shortcuts_router import router as enhanced_shortcuts_router, init_enhanced_apple_shortcuts_router
init_enhanced_apple_shortcuts_router(get_conn)
app.include_router(enhanced_shortcuts_router)

# ---- Unified Capture Router ----
from services.unified_capture_router import router as unified_capture_router, init_unified_capture_router
init_unified_capture_router(get_conn)
app.include_router(unified_capture_router)

# ---- Enhanced Discord Router ----
from services.enhanced_discord_router import router as enhanced_discord_router, init_enhanced_discord_router
init_enhanced_discord_router(get_conn)
app.include_router(enhanced_discord_router)

# ---- Notification Router ----
init_notification_router(get_current_user)
app.include_router(notification_router)

# ---- Memory-Augmented Chat Router ----
from api.routes_chat import router as chat_router
app.include_router(chat_router)

# ---- Build Log Router ----
from services.build_log_router import router as build_log_router, init_build_log_router
init_build_log_router(get_conn)
app.include_router(build_log_router)

# ---- Theme Router ----
from services.theme_router import router as theme_router
app.include_router(theme_router)

# ---- Advanced Search Router ----
from services.advanced_search_router import router as advanced_search_router
app.include_router(advanced_search_router)

# ---- Demo Data Router ----

# --- Simple FIFO job worker for note processing ---
import asyncio

def _claim_next_pending_note():
    conn = get_conn()
    conn.isolation_level = None  # autocommit mode for immediate lock/retry simplicity
    c = conn.cursor()
    row = c.execute(
        "SELECT id FROM notes WHERE status = 'pending' ORDER BY COALESCE(timestamp, created_at) ASC LIMIT 1"
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

async def _start_worker():
    if getattr(app.state, "job_worker_started", False):
        return
    app.state.job_worker_started = True
    asyncio.create_task(job_worker())

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

async def _start_audio_worker():
    """Start automated audio processing worker"""
    if getattr(app.state, "audio_worker_started", False):
        return
    app.state.audio_worker_started = True

    async def audio_processing_worker():
        """Background worker that processes audio queue regularly"""
        from tasks import process_audio_queue

        while True:
            try:
                # Process one item from the audio queue
                process_audio_queue()
                # Wait 10 seconds before checking again
                await asyncio.sleep(10)
            except Exception as e:
                print(f"Audio worker error: {e}")
                # Wait longer on errors to avoid spam
                await asyncio.sleep(30)

    asyncio.create_task(audio_processing_worker())
    print("🎵 Audio processing worker started (checking every 10 seconds)")
    queue_stats = audio_queue.get_queue_status()
    queued_count = queue_stats.get('status_counts', {}).get('queued', 0)
    print(f"📊 Found {queued_count} items in audio processing queue")

async def _init_memory_system():
    """Initialize memory augmentation system on startup"""
    if getattr(app.state, "memory_system_started", False):
        return
    app.state.memory_system_started = True

    try:
        if not settings.memory_extraction_enabled:
            print("⚠️  Memory extraction disabled in config")
            return

        from services.memory_service import MemoryService
        from services.memory_extraction_service import MemoryExtractionService
        from services.memory_consolidation_service import init_consolidation_queue
        from services.model_manager import get_model_manager

        # Initialize services
        db = get_conn()
        embeddings = get_embeddings_service()
        memory_service = MemoryService(db, embeddings)
        model_manager = get_model_manager()

        extraction_service = MemoryExtractionService(
            memory_service=memory_service,
            ollama_url=settings.ollama_api_url,
            model_manager=model_manager
        )

        # Start consolidation queue
        init_consolidation_queue(extraction_service)

        print("🧠 Memory augmentation system initialized successfully")

    except Exception as e:
        print(f"⚠️  Failed to initialize memory system: {e}")
        # Don't fail startup - memory system is optional
        print("⚠️  Continuing without memory augmentation")

async def _shutdown_tasks():
    """Shutdown tasks for graceful cleanup"""
    try:
        from services.memory_consolidation_service import shutdown_consolidation_queue
        shutdown_consolidation_queue()
        print("🧠 Memory system shutdown complete")
    except Exception as e:
        print(f"⚠️  Error during memory system shutdown: {e}")

# Add real-time status endpoints if available
if REALTIME_AVAILABLE:
    create_status_endpoint(app)

async def process_audio_queue():
    """Background task to process audio queue in FIFO order"""
    next_item = audio_queue.get_next_for_processing()
    if next_item:
        note_id, user_id = next_item
        try:
            if process_note_with_status is not None:
                await process_note_with_status(note_id)  # type: ignore
            else:
                import asyncio
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, process_note, note_id)
        except Exception as e:
            print(f"Error processing audio note {note_id}: {e}")
            # Mark as failed in queue
            audio_queue.mark_completed(note_id, success=False)

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

# Search router removed - functionality integrated into main app

# Search page route (redirects to login if unauthenticated)
@app.get("/search")
async def search_page(request: Request):
    user = get_current_user_silent(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return render_page(request, "search.html", {"user": user})
# Auth endpoints moved to services/auth_service.py
# All auth endpoints moved to services/auth_service.py

@app.get("/saas")
def saas_landing_page(request: Request):
    """Modern SaaS landing page for marketing and showcase"""
    return render_page(request, "landing_saas.html", {})
@app.get("/landing-saas")
def saas_landing_page_alt(request: Request):
    """Alternative URL for the modern SaaS landing page"""
    return render_page(request, "landing_saas.html", {})

# Enhanced health monitoring and diagnostics
import psutil
import shutil
import subprocess
import requests
import time
import logging
import logging.config
from pathlib import Path

# Configure logging for memory system and other services
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        },
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'level': 'INFO'
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': 'memory_system.log',
            'formatter': 'detailed',
            'level': 'DEBUG'
        }
    },
    'loggers': {
        'services.memory_service': {'level': 'DEBUG', 'handlers': ['console', 'file'], 'propagate': False},
        'services.memory_extraction_service': {'level': 'DEBUG', 'handlers': ['console', 'file'], 'propagate': False},
        'services.memory_consolidation_service': {'level': 'INFO', 'handlers': ['console', 'file'], 'propagate': False},
        'services.model_manager': {'level': 'INFO', 'handlers': ['console', 'file'], 'propagate': False},
        'api.routes_chat': {'level': 'DEBUG', 'handlers': ['console', 'file'], 'propagate': False},
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO'
    }
}

logging.config.dictConfig(LOGGING_CONFIG)

# Initialize logger for health monitoring
logger = logging.getLogger(__name__)

@app.get("/health")
def health():
    """Comprehensive system health check with detailed diagnostics"""
    health_data = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {},
        "database": {},
        "resources": {},
        "issues": []
    }
    
    try:
        # Database health check
        db_health = _check_database_health()
        health_data["database"] = db_health
        if not db_health.get("healthy", False):
            health_data["status"] = "degraded"
            health_data["issues"].extend(db_health.get("issues", []))
        
        # Service availability checks
        services_health = _check_services_health()
        health_data["services"] = services_health
        for service_name, service_data in services_health.items():
            if not service_data.get("healthy", False):
                health_data["status"] = "degraded"
                health_data["issues"].append(f"{service_name}: {service_data.get('error', 'Unknown issue')}")
        
        # Resource monitoring
        resources_health = _check_resources_health()
        health_data["resources"] = resources_health
        if resources_health.get("disk_space_critical", False) or resources_health.get("memory_critical", False):
            health_data["status"] = "critical"
            health_data["issues"].extend(resources_health.get("warnings", []))
        
        # Processing queue health
        queue_health = _check_queue_health()
        health_data["processing_queue"] = queue_health
        if queue_health.get("stalled_tasks", 0) > 5:
            health_data["status"] = "degraded"
            health_data["issues"].append(f"Queue has {queue_health['stalled_tasks']} stalled tasks")
            
    except Exception as e:
        health_data["status"] = "error"
        health_data["issues"].append(f"Health check failed: {str(e)}")
        logger.error(f"Health check error: {e}", exc_info=True)
    
    # Set appropriate HTTP status code
    status_code = 200
    if health_data["status"] == "degraded":
        status_code = 200  # Still operational
    elif health_data["status"] in ["critical", "error"]:
        status_code = 503  # Service unavailable
    
    return JSONResponse(content=health_data, status_code=status_code)

def _check_database_health():
    """Check SQLite database connectivity and integrity"""
    health_info = {
        "healthy": False,
        "connection_test": False,
        "tables_present": False,
        "fts_index_status": "unknown",
        "integrity_check": "unknown",
        "statistics": {},
        "issues": []
    }
    
    try:
        # Basic connection test
        conn = get_conn()
        c = conn.cursor()
        health_info["connection_test"] = True
        
        # Check required tables exist
        tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        required_tables = ["users", "notes", "audio_processing_queue"]
        missing_tables = [t for t in required_tables if t not in table_names]
        
        if missing_tables:
            health_info["issues"].append(f"Missing tables: {', '.join(missing_tables)}")
        else:
            health_info["tables_present"] = True
        
        # Database statistics
        stats = {}
        for table in ["users", "notes", "reminders", "search_analytics"]:
            if table in table_names:
                count = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                stats[f"{table}_count"] = count
        
        # Check FTS5 index if notes table exists
        if "notes" in table_names:
            try:
                fts_tables = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'notes_fts%'").fetchall()
                if fts_tables:
                    health_info["fts_index_status"] = "present"
                    # Test FTS search functionality
                    c.execute("SELECT COUNT(*) FROM notes_fts WHERE notes_fts MATCH 'test' LIMIT 1")
                    health_info["fts_index_status"] = "functional"
                else:
                    health_info["fts_index_status"] = "missing"
                    health_info["issues"].append("FTS5 index not found")
            except Exception as e:
                health_info["fts_index_status"] = "error"
                health_info["issues"].append(f"FTS5 index error: {str(e)}")
        
        # Database integrity check (quick version)
        try:
            integrity_result = c.execute("PRAGMA quick_check").fetchone()[0]
            health_info["integrity_check"] = integrity_result
            if integrity_result != "ok":
                health_info["issues"].append(f"Database integrity issue: {integrity_result}")
        except Exception as e:
            health_info["integrity_check"] = "error"
            health_info["issues"].append(f"Integrity check failed: {str(e)}")
        
        health_info["statistics"] = stats
        health_info["healthy"] = len(health_info["issues"]) == 0
        
        conn.close()
        
    except Exception as e:
        health_info["issues"].append(f"Database connection failed: {str(e)}")
        
    return health_info

def _check_services_health():
    """Check external service availability"""
    services = {}
    
    # Ollama service check
    ollama_health = {"healthy": False, "response_time_ms": None, "error": None}
    try:
        start_time = time.time()
        response = requests.get(
            settings.ollama_api_url.replace("/api/generate", "/api/tags"),
            timeout=5
        )
        response_time = (time.time() - start_time) * 1000
        ollama_health["response_time_ms"] = round(response_time, 2)
        
        if response.status_code == 200:
            ollama_health["healthy"] = True
            data = response.json()
            ollama_health["models"] = [m.get("name", "unknown") for m in data.get("models", [])]
        else:
            ollama_health["error"] = f"HTTP {response.status_code}"
    except Exception as e:
        ollama_health["error"] = str(e)
    
    services["ollama"] = ollama_health
    
    # Whisper.cpp availability check
    whisper_health = {"healthy": False, "path_exists": False, "executable": False, "error": None}
    try:
        whisper_path = settings.whisper_cpp_path
        whisper_health["path_exists"] = whisper_path.exists()
        whisper_health["executable"] = whisper_path.exists() and whisper_path.is_file()
        
        if whisper_health["executable"]:
            # Quick test run (this might not work on all systems, so we'll catch errors)
            try:
                result = subprocess.run(
                    [str(whisper_path), "--help"],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                whisper_health["healthy"] = result.returncode == 0 or "whisper" in result.stderr.lower()
            except subprocess.TimeoutExpired:
                whisper_health["healthy"] = True  # If it hangs on --help, it's probably working
            except Exception as e:
                whisper_health["error"] = f"Test run failed: {str(e)}"
        else:
            whisper_health["error"] = "Binary not found or not executable"
    except Exception as e:
        whisper_health["error"] = str(e)
    
    services["whisper"] = whisper_health
    
    # Email service check (if enabled)
    if settings.email_enabled:
        email_health = {"healthy": False, "configured": False, "error": None}
        try:
            email_health["configured"] = bool(settings.email_api_key)
            email_health["service_type"] = settings.email_service
            
            if email_health["configured"]:
                # Basic configuration check without sending actual email
                email_health["healthy"] = True
            else:
                email_health["error"] = "No API key configured"
        except Exception as e:
            email_health["error"] = str(e)
        
        services["email"] = email_health
    
    return services

def _check_resources_health():
    """Check system resource usage"""
    resources = {
        "disk_space": {},
        "memory": {},
        "disk_space_critical": False,
        "memory_critical": False,
        "warnings": []
    }
    
    try:
        # Disk space check
        base_dir = settings.base_dir
        disk_usage = shutil.disk_usage(base_dir)
        total_gb = disk_usage.total / (1024**3)
        free_gb = disk_usage.free / (1024**3)
        used_percent = ((disk_usage.total - disk_usage.free) / disk_usage.total) * 100
        
        resources["disk_space"] = {
            "total_gb": round(total_gb, 2),
            "free_gb": round(free_gb, 2),
            "used_percent": round(used_percent, 1)
        }
        
        if used_percent > 95:
            resources["disk_space_critical"] = True
            resources["warnings"].append(f"Critical disk space: {used_percent:.1f}% used")
        elif used_percent > 85:
            resources["warnings"].append(f"Low disk space: {used_percent:.1f}% used")
        
        # Memory usage
        memory = psutil.virtual_memory()
        resources["memory"] = {
            "total_gb": round(memory.total / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "used_percent": memory.percent
        }
        
        if memory.percent > 95:
            resources["memory_critical"] = True
            resources["warnings"].append(f"Critical memory usage: {memory.percent:.1f}%")
        elif memory.percent > 85:
            resources["warnings"].append(f"High memory usage: {memory.percent:.1f}%")
        
        # File system health for key directories
        key_dirs = {
            "vault": settings.vault_path,
            "audio": settings.audio_dir,
            "uploads": settings.uploads_dir
        }
        
        dir_info = {}
        for name, path in key_dirs.items():
            if path.exists():
                dir_info[name] = {
                    "exists": True,
                    "writable": os.access(path, os.W_OK),
                    "files_count": len(list(path.iterdir())) if path.is_dir() else 0
                }
            else:
                dir_info[name] = {"exists": False, "writable": False}
                resources["warnings"].append(f"Directory missing: {name} ({path})")
        
        resources["directories"] = dir_info
        
    except Exception as e:
        resources["warnings"].append(f"Resource check error: {str(e)}")
    
    return resources

def _check_queue_health():
    """Check processing queue health and performance"""
    queue_info = {
        "healthy": True,
        "queued_tasks": 0,
        "processing_tasks": 0,
        "stalled_tasks": 0,
        "completed_today": 0,
        "average_processing_time_minutes": None,
        "issues": []
    }
    
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # Check audio processing queue
        from services.audio_queue import audio_queue
        
        # Get current queue status
        queue_status = audio_queue.get_batch_status()
        queue_info.update({
            "queued_tasks": queue_status.get("queued", 0),
            "processing_tasks": queue_status.get("processing", 0),
            "batch_mode": queue_status.get("batch_mode", False)
        })
        
        # Check for stalled tasks (processing for more than 2 hours)
        stalled_threshold = datetime.utcnow() - timedelta(hours=2)
        stalled_count = c.execute("""
            SELECT COUNT(*) FROM audio_processing_queue 
            WHERE status = 'processing' AND started_at < ?
        """, (stalled_threshold.isoformat(),)).fetchone()[0]
        
        queue_info["stalled_tasks"] = stalled_count
        
        # Tasks completed today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        completed_today = c.execute("""
            SELECT COUNT(*) FROM audio_processing_queue 
            WHERE status = 'completed' AND completed_at >= ?
        """, (today_start.isoformat(),)).fetchone()[0]
        
        queue_info["completed_today"] = completed_today
        
        # Average processing time for completed tasks (last 100)
        avg_time_query = c.execute("""
            SELECT AVG(
                (julianday(completed_at) - julianday(started_at)) * 1440
            ) as avg_minutes
            FROM audio_processing_queue 
            WHERE status = 'completed' AND started_at IS NOT NULL 
            ORDER BY completed_at DESC LIMIT 100
        """).fetchone()
        
        if avg_time_query and avg_time_query[0]:
            queue_info["average_processing_time_minutes"] = round(avg_time_query[0], 2)
        
        # Check notes table for processing status
        notes_status = c.execute("""
            SELECT status, COUNT(*) 
            FROM notes 
            WHERE type = 'audio' 
            GROUP BY status
        """).fetchall()
        
        status_counts = dict(notes_status)
        queue_info["notes_by_status"] = status_counts
        
        # Check for failed tasks
        failed_count = status_counts.get("failed", 0) + status_counts.get("failed:timeout", 0)
        if failed_count > 0:
            queue_info["issues"].append(f"{failed_count} failed audio processing tasks")
        
        conn.close()
        
    except Exception as e:
        queue_info["healthy"] = False
        queue_info["issues"].append(f"Queue check error: {str(e)}")
    
    return queue_info

# PWA Offline Page
@app.get("/offline")
def offline_page(request: Request):
    """Offline page for PWA functionality"""
    return render_page(request, "offline.html", {})

# Mobile Capture Interface
@app.get("/capture/mobile")
def mobile_capture_page(request: Request):
    """Mobile-optimized capture interface"""
    return render_page(request, "mobile_capture.html", {})

# Enhanced Capture Dashboard
@app.get("/capture/enhanced")
def enhanced_capture_dashboard(request: Request):
    """Enhanced capture dashboard with all capture methods"""
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    
    return render_page(request, "enhanced_capture_dashboard.html", {
        "user": current_user
    })

# Main endpoints (keep existing)
@app.get("/")
def dashboard(
    request: Request,
):
    current_user = get_current_user_silent(request)
    if not current_user:
        # Public landing page for visitors
        return render_page(request, "landing.html", {})
    conn = get_conn()
    c = conn.cursor()
    # Always load recent notes without URL parameters
    rows = c.execute(
        "SELECT * FROM notes WHERE user_id = ? ORDER BY COALESCE(timestamp, created_at) DESC LIMIT 100",
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
                n["file_url"] = f"/files/{ff}"
        except Exception:
            # Non-fatal; previews just won't render
            pass
        # Add word count and audio duration for display
        try:
            n["word_count"] = _word_count(n.get("body") or n.get("content") or n.get("summary") or "")
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
        SELECT id, title, type, COALESCE(timestamp, created_at) as timestamp, audio_filename, status, tags,
               file_filename, file_type, file_mime_type
        FROM notes
        WHERE user_id = ?
        ORDER BY (tags LIKE '%pinned%') DESC, COALESCE(timestamp, created_at) DESC
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
                item["file_url"] = f"/files/{ff}"
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
    # For logged-in users, redirect to v3 dashboard by default
    return RedirectResponse(url="/dashboard/v3", status_code=302)

# =========================
# Resumable Upload Endpoints
# =========================
from pathlib import Path

def _get_incoming_dir() -> Path:
    d = settings.uploads_dir / "incoming"
    d.mkdir(parents=True, exist_ok=True)
    return d

# Upload helper functions moved to services/upload_service.py

@app.post("/upload/init")
async def upload_init(
    request: Request,
    data: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    """Initialize a resumable upload."""
    return await upload_service.init_upload(request, data, current_user)

@app.get("/upload/status")
async def upload_status(
    upload_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get upload status."""
    return await upload_service.get_upload_status(upload_id, current_user)

@app.put("/upload/chunk")
async def upload_chunk(
    request: Request,
    upload_id: str = Query(...),
    offset: int = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Append a chunk to an active upload."""
    return await upload_service.upload_chunk(request, upload_id, offset, current_user)

@app.post("/upload/finalize")
async def upload_finalize(
    request: Request,
    background_tasks: BackgroundTasks,
    upload_id: str = Body(..., embed=True),
    note: str = Body(""),
    tags: str = Body(""),
    current_user: User = Depends(get_current_user),
):
    """Finalize an upload and create a note."""
    return await upload_service.finalize_upload(request, background_tasks, upload_id, note, tags, current_user)

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
@app.get("/api/audio-queue/status")
async def get_audio_queue_status(current_user: User = Depends(get_current_user)):
    """Get current audio processing queue status for the user"""
    status = audio_queue.get_queue_status(current_user.id)
    
    # Also get recent processing activity
    conn = get_conn()
    c = conn.cursor()
    
    # Get user's audio notes with their current status
    c.execute("""
        SELECT n.id, n.title, n.status, COALESCE(n.timestamp, n.created_at) as timestamp, n.audio_filename,
               CASE 
                 WHEN n.status LIKE '%:%' THEN CAST(SUBSTR(n.status, INSTR(n.status, ':') + 1) AS INTEGER)
                 ELSE 0
               END as progress_percent
        FROM notes n
        WHERE n.user_id = ? AND n.type = 'audio' 
        ORDER BY COALESCE(n.timestamp, n.created_at) DESC
        LIMIT 10
    """, (current_user.id,))
    
    recent_audio = []
    for row in c.fetchall():
        recent_audio.append({
            "id": row[0],
            "title": row[1] or "Untitled Audio",
            "status": row[2],
            "timestamp": row[3],
            "filename": row[4],
            "progress_percent": row[5]
        })
    
    conn.close()
    
    return {
        "queue_status": status,
        "recent_audio": recent_audio
    }
@app.get("/api/transcribe/status")
async def transcribe_status(current_user: User = Depends(get_current_user)):
    """Report basic transcription queue status and settings."""
    conn = get_conn()
    c = conn.cursor()
    pending = c.execute(
        "SELECT COUNT(*) FROM notes WHERE user_id=? AND status='pending' AND type='audio'",
        (current_user.id,),
    ).fetchone()[0]
    in_prog = c.execute(
        "SELECT COUNT(*) FROM notes WHERE user_id=? AND status LIKE 'transcribing:%' AND type='audio'",
        (current_user.id,),
    ).fetchone()[0]
    last_done = c.execute(
        "SELECT COALESCE(timestamp, created_at) FROM notes WHERE user_id=? AND type='audio' AND status='complete' ORDER BY COALESCE(timestamp, created_at) DESC LIMIT 1",
        (current_user.id,),
    ).fetchone()
    conn.close()
    return {
        "pending": int(pending),
        "in_progress": int(in_prog),
        "last_completed": last_done[0] if last_done else None,
        "settings": {
            "transcription_concurrency": getattr(settings, 'transcription_concurrency', 1),
            "transcription_segment_seconds": getattr(settings, 'transcription_segment_seconds', 600),
        },
    }
@app.get("/api/batch/status")
async def get_batch_status(current_user: User = Depends(get_current_user)):
    """Get batch processing status and configuration"""
    return audio_queue.get_batch_status()
# Public health check endpoints (no authentication required)
@app.get("/api/audio-queue/health")
async def audio_queue_health():
    """Public health check for audio queue system"""
    try:
        # Get basic system status without user-specific data
        conn = sqlite3.connect(audio_queue.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM audio_processing_queue WHERE status = 'queued'")
        total_pending = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM audio_processing_queue WHERE status = 'processing'")
        total_processing = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "status": "healthy",
            "service": "audio-queue",
            "queue_status": {
                "pending": total_pending,
                "processing": total_processing
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy", 
            "service": "audio-queue",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/batch/health")  
async def batch_health():
    """Public health check for batch processing system"""
    try:
        batch_status = audio_queue.get_batch_status()
        return {
            "status": "healthy",
            "service": "batch-processing", 
            "batch_enabled": batch_status.get("batch_enabled", False),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "batch-processing",
            "error": str(e), 
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/batch/process-now")
async def process_batch_now(current_user: User = Depends(get_current_user)):
    """Immediately process all queued items in batch mode"""
    try:
        # Import here to avoid circular imports
        from tasks import process_batch
        process_batch()
        return {"message": "Batch processing initiated", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting batch processing: {str(e)}")
@app.post("/api/transcribe/requeue")
async def transcribe_requeue(
    background_tasks: BackgroundTasks,
    limit: int = Body(50, embed=True),
    current_user: User = Depends(get_current_user),
):
    """Requeue pending/incomplete audio notes for transcription.

    Schedules background jobs for notes with status 'pending' or 'transcribing:*'.
    """
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute(
        """
        SELECT id FROM notes
        WHERE user_id=? AND type='audio' AND (status='pending' OR status LIKE 'transcribing:%')
        ORDER BY id DESC LIMIT ?
        """,
        (current_user.id, int(limit)),
    ).fetchall()
    conn.close()
    count = 0
    for (nid,) in rows:
        try:
            if REALTIME_AVAILABLE:
                background_tasks.add_task(process_note_with_status, nid)
            else:
                background_tasks.add_task(process_note, nid)
            count += 1
        except Exception:
            background_tasks.add_task(process_note, nid)
            count += 1
    return {"success": True, "requeued": count}
@app.post("/webhook/audio")
async def webhook_audio_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tags: str = Form(""),
    user_id: int = Form(1)  # Default user ID for webhook (adjust as needed)
):
    """
    Fast audio webhook endpoint for Apple Shortcuts and external integrations.
    Quickly saves audio and queues for background processing without blocking.

    If called from authenticated dashboard, uses the logged-in user's ID.
    If called from external webhook (Apple Shortcuts, etc.), uses the provided user_id.
    """
    # Try to get authenticated user first (for dashboard uploads)
    try:
        authenticated_user = get_current_user_silent(request)
        if authenticated_user:
            user_id = authenticated_user.id
            logging.getLogger(__name__).info(f"Voice upload from authenticated user: {authenticated_user.username} (ID: {user_id})")
    except Exception:
        # No authentication, use provided user_id (webhook mode)
        logging.getLogger(__name__).info(f"Voice upload from webhook with user_id: {user_id}")

    return await webhook_service.process_audio_webhook(background_tasks, file, tags, user_id)
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
        if k == 'content':
            set_parts.append("body = ?")
            params.append(v)
            set_parts.append("content = ?")
            params.append(v)
        else:
            set_parts.append(f"{k} = ?")
            params.append(v)
    set_parts.append("updated_at = datetime('now')")
    params.extend([note_id, current_user.id])
    c.execute(
        f"UPDATE notes SET {', '.join(set_parts)} WHERE id = ? AND user_id = ?",
        params,
    )

    conn.commit()
    conn.close()

    return {"success": True, "note": {"id": note_id, **fields}}

# Enhanced Search Endpoint - MOVED to services/search_router.py
# New data models
# Removed duplicate DiscordWebhook class - using definition from line ~232

# Apple webhook models moved to services/webhook_service.py

# Removed SearchRequest class - moved to services/search_router.py
# Removed redundant search endpoint - consolidated into /api/search

# Discord Integration
@app.post("/webhook/discord/legacy", include_in_schema=False)
async def webhook_discord_legacy1(
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_from_discord_header)
):
    """Enhanced Discord webhook with user mapping"""
    from services.webhook_service import DiscordWebhook
    webhook_data = DiscordWebhook(**data)
    return await webhook_service.process_discord_webhook_legacy(webhook_data, background_tasks)

# Apple Shortcuts Enhanced
@app.post("/webhook/apple/reminder")
async def create_apple_reminder(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Create reminder from Apple Shortcuts"""
    from services.webhook_service import AppleReminderWebhook
    webhook_data = AppleReminderWebhook(**data)
    return webhook_service.process_apple_reminder_webhook(webhook_data, current_user.id)

@app.post("/webhook/apple/calendar")
async def create_calendar_event(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Create calendar event and meeting note"""
    from services.webhook_service import CalendarEvent
    webhook_data = CalendarEvent(**data)
    return webhook_service.process_apple_calendar_webhook(webhook_data, current_user.id)

# Enhanced Search - MOVED to services/search_router.py
# Hybrid Search - MOVED to services/search_router.py
# Search Suggestions - MOVED to services/search_router.py
# Helper functions _fuzzy_match and _extract_phrases - MOVED to services/search_router.py
# Search Enhancement Endpoint - MOVED to services/search_router.py
@app.get("/api/analytics")
async def get_analytics(current_user: User = Depends(get_current_user)):
    """Get user analytics and insights"""
    return analytics_service.get_user_analytics(current_user)

# Discord Bot Management Endpoints
@app.get("/api/discord/status")
async def get_discord_bot_status(current_user: User = Depends(get_current_user)):
    """Get Discord bot connection status and statistics"""
    try:
        # Check if Discord bot is configured
        import os
        bot_token = os.getenv('DISCORD_BOT_TOKEN')
        
        if not bot_token:
            return {
                "connected": False,
                "error": "Discord bot not configured",
                "stats": {"messages": 0, "users": 0},
                "recentActivity": []
            }
        
        # Try to get basic Discord user mapping statistics
        conn = get_conn()
        c = conn.cursor()
        
        # Get Discord user count
        discord_user_count = c.execute(
            "SELECT COUNT(*) as count FROM discord_users"
        ).fetchone()
        
        # Get recent Discord activity count
        recent_activity_count = c.execute(
            """
            SELECT COUNT(*) as count 
            FROM discord_activity_log 
            WHERE created_at >= datetime('now', '-1 day')
            """
        ).fetchone()
        
        # Get recent Discord activity for display
        recent_activities = c.execute(
            """
            SELECT discord_username, command, action, description, created_at, success
            FROM discord_activity_log 
            ORDER BY created_at DESC 
            LIMIT 10
            """
        ).fetchall()
        
        conn.close()
        
        # Format activities for frontend
        formatted_activities = []
        for activity in recent_activities:
            icon = "✅" if activity[5] else "❌"  # success
            if activity[1]:  # command
                icon = {"save": "💾", "search": "🔍", "upload": "📤", "status": "📊", "help": "❓"}.get(activity[1], "🤖")
            
            formatted_activities.append({
                "user": activity[0] or "Unknown User",
                "command": activity[1],
                "action": activity[2],
                "description": activity[3] or f"Used /{activity[1]}" if activity[1] else activity[2],
                "timestamp": activity[4],
                "icon": icon,
                "success": activity[5]
            })
        
        return {
            "connected": True,  # Assume connected if token is set
            "uptime": "Unknown",  # We don't track bot uptime currently
            "stats": {
                "messages": recent_activity_count[0] if recent_activity_count else 0,
                "users": discord_user_count[0] if discord_user_count else 0
            },
            "recentActivity": formatted_activities
        }
        
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "stats": {"messages": 0, "users": 0},
            "recentActivity": []
        }

@app.post("/api/discord/test")
async def test_discord_bot_connection(current_user: User = Depends(get_current_user)):
    """Test Discord bot connection"""
    try:
        import os
        bot_token = os.getenv('DISCORD_BOT_TOKEN')
        
        if not bot_token:
            return {
                "success": False,
                "error": "Discord bot token not configured. Please set DISCORD_BOT_TOKEN environment variable."
            }
        
        # Basic token validation (check format)
        if not bot_token.startswith(('Bot ', 'mfa.')) and not '.' in bot_token:
            return {
                "success": False,
                "error": "Invalid Discord bot token format"
            }
        
        # For now, just validate token format
        # In a full implementation, you would make an API call to Discord
        return {
            "success": True,
            "message": "Discord bot token format appears valid",
            "note": "Bot functionality depends on discord_bot.py being running separately"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Connection test failed: {str(e)}"
        }

@app.get("/api/discord/activity")
async def get_discord_activity_logs(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """Get Discord bot activity logs with pagination"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # Get total count
        total_count = c.execute(
            "SELECT COUNT(*) as count FROM discord_activity_log"
        ).fetchone()[0]
        
        # Get paginated activity logs
        activities = c.execute(
            """
            SELECT discord_user_id, discord_username, command, action, 
                   description, created_at, success, error_message, metadata
            FROM discord_activity_log 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        ).fetchall()
        
        conn.close()
        
        # Format activities
        formatted_activities = []
        for activity in activities:
            icon = "✅" if activity[6] else "❌"  # success
            if activity[2]:  # command
                icon = {
                    "save": "💾", "search": "🔍", "upload": "📤", "status": "📊", 
                    "help": "❓", "recent": "📋", "stats": "📈", "sync": "🔄",
                    "restart": "🔄", "cleanup": "🧹", "tags": "🏷️", "queue": "⏳",
                    "retry": "🔁", "export": "📤", "duplicate": "📋", "activity": "⚡"
                }.get(activity[2], "🤖")
            
            formatted_activities.append({
                "id": activity[0],  # discord_user_id
                "user": activity[1] or "Unknown User",
                "command": activity[2],
                "action": activity[3],
                "description": activity[4] or f"Used /{activity[2]}" if activity[2] else activity[3],
                "timestamp": activity[5],
                "success": activity[6],
                "error": activity[7],
                "icon": icon,
                "metadata": activity[8] or "{}"
            })
        
        return {
            "activities": formatted_activities,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "hasMore": offset + limit < total_count
        }
        
    except Exception as e:
        return {
            "activities": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "hasMore": False,
            "error": str(e)
        }

@app.post("/api/discord/log-activity")
async def log_discord_activity(
    discord_user_id: str,
    action: str,
    discord_username: str = None,
    command: str = None,
    description: str = None,
    success: bool = True,
    error_message: str = None,
    metadata: dict = None
):
    """Log Discord bot activity (called by Discord bot)"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        import json
        metadata_json = json.dumps(metadata or {})
        
        c.execute(
            """
            INSERT INTO discord_activity_log 
            (discord_user_id, discord_username, command, action, description, success, error_message, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (discord_user_id, discord_username, command, action, description, success, error_message, metadata_json)
        )
        
        conn.commit()
        conn.close()
        
        return {"success": True, "message": "Activity logged successfully"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/recent-activity")
async def get_recent_activity(
    limit: int = 10,
    current_user: User = Depends(get_current_user)
):
    """Get recent activity for Quick Actions panel"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # Get recent notes
        recent_notes = c.execute(
            """
            SELECT id, title, type, COALESCE(timestamp, created_at, updated_at) AS sort_ts, status
            FROM notes 
            WHERE user_id = ?
            ORDER BY sort_ts DESC 
            LIMIT ?
            """,
            (current_user.id, limit)
        ).fetchall()
        
        # Get recent Discord activities if available
        recent_discord = []
        try:
            recent_discord = c.execute(
                """
                SELECT command, action, created_at
                FROM discord_activity_log 
                ORDER BY created_at DESC 
                LIMIT 3
                """
            ).fetchall()
        except:
            pass  # Table might not exist
        
        conn.close()
        
        # Format activities
        activities = []
        
        # Add recent notes
        for note in recent_notes:
            icon = {"audio": "🎤", "file": "📁", "web": "🌐"}.get(note[2], "📝")
            activities.append({
                "type": "note",
                "icon": icon,
                "title": note[1] or "Untitled Note",
                "description": f"Created {note[2] or 'note'}",
                "timestamp": note[3],
                "status": note[4],
                "id": note[0]
            })
        
        # Add recent Discord activities
        for activity in recent_discord:
            activities.append({
                "type": "discord",
                "icon": "🤖",
                "title": f"Discord: /{activity[0]}" if activity[0] else "Discord Activity",
                "description": activity[1] or "Bot interaction",
                "timestamp": activity[2],
                "status": "completed"
            })
        
        # Sort by timestamp and limit
        activities.sort(key=lambda x: x["timestamp"], reverse=True)
        activities = activities[:limit]
        
        return {
            "activities": activities,
            "total": len(activities)
        }
        
    except Exception as e:
        return {
            "activities": [],
            "total": 0,
            "error": str(e)
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
        SELECT id, title, type, status, file_filename, file_type, file_mime_type, file_size, COALESCE(timestamp, created_at) as timestamp
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
async def get_current_user_from_discord_id(discord_id: int = None):
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

def get_current_user_from_discord_header(authorization: str = Header(None)) -> User:
    return auth_service.get_current_user_from_discord(authorization)

# /webhook/discord/legacy should use the header token flow
@app.post("/webhook/discord/legacy", include_in_schema=False)
async def webhook_discord_legacy1(
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_from_discord_header)
):
    from services.webhook_service import DiscordWebhook
    webhook_data = DiscordWebhook(**data)
    return await webhook_service.process_discord_webhook_legacy(webhook_data, background_tasks)
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
        "INSERT INTO notes (title, body, content, summary, tags, actions, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            note[:60] + "..." if len(note) > 60 else note,
            note,
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
    conn.close()
    
    return {"status": "ok", "note_id": note_id}
# /webhook/discord/upload uses the form field discord_user_id mapping flow
@app.post("/webhook/discord/upload")
async def webhook_discord_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    note: str = Form(""),
    tags: str = Form(""),
    discord_user_id: str = Form(...),
    type: str = Form("discord_upload"),
    current_user: User = Depends(get_current_user_from_discord_header)
):
    return await webhook_service.process_discord_upload_webhook(file, note, tags, discord_user_id, type, background_tasks)

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

    file_metadata_raw = note.get("file_metadata")
    parsed_file_metadata = {}
    if file_metadata_raw:
        try:
            parsed_file_metadata = json.loads(file_metadata_raw)
        except Exception:
            parsed_file_metadata = {}
    note["file_metadata_json"] = parsed_file_metadata
    note["snapshot_manifest_path"] = parsed_file_metadata.get("manifest_path")
    note["snapshot_artifacts"] = parsed_file_metadata.get("artifacts", [])

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
        file_url = f"/files/{note['file_filename']}"
    return render_page(
        request,
        "detail.html",
        {"note": note, "related": related, "user": current_user, "file_url": file_url},
    )
@app.get("/snapshot/{note_id}")
def snapshot_view(request: Request, note_id: int):
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

    columns = [col[0] for col in c.description]
    note = dict(zip(columns, row))
    conn.close()
    file_metadata_raw = note.get("file_metadata")
    file_metadata = {}
    if file_metadata_raw:
        try:
            file_metadata = json.loads(file_metadata_raw)
        except Exception:
            file_metadata = {}

    manifest_path = file_metadata.get("manifest_path")
    manifest = {}
    if manifest_path:
        try:
            manifest_file = pathlib.Path(manifest_path)
            if manifest_file.exists():
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    raw_artifacts = file_metadata.get("artifacts", []) or []
    artifacts: List[dict] = []
    for artifact in raw_artifacts:
        entry = dict(artifact)
        artifact_id = entry.get("id")
        if artifact_id:
            entry["view_url"] = f"/snapshot/{note_id}/artifact/{artifact_id}"
            mime = entry.get("mime_type") or ""
            if "html" in mime:
                entry["inline_url"] = f"/snapshot/{note_id}/artifact/{artifact_id}/inline"
        artifacts.append(entry)

    context = {
        "note": note,
        "manifest": manifest,
        "file_metadata": file_metadata,
        "artifacts": artifacts,
    }

    return render_page(request, "snapshot_view.html", context)
@app.get("/snapshot/{note_id}/artifact/{artifact_id}")
def snapshot_artifact(request: Request, note_id: int, artifact_id: str):
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)

    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT file_metadata FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user.id),
    ).fetchone()
    conn.close()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Artifact not found")

    try:
        metadata = json.loads(row[0])
    except Exception:
        metadata = {}

    artifacts = metadata.get("artifacts", [])
    artifact = next((a for a in artifacts if a.get("id") == artifact_id), None)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    path = pathlib.Path(artifact.get("path", ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file missing")

    return FileResponse(
        str(path),
        media_type=artifact.get("mime_type") or "application/octet-stream",
        filename=path.name,
    )
@app.get("/snapshot/{note_id}/artifact/{artifact_id}/inline")
def snapshot_artifact_inline(request: Request, note_id: int, artifact_id: str):
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)

    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT file_metadata FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user.id),
    ).fetchone()
    conn.close()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Artifact not found")

    try:
        metadata = json.loads(row[0])
    except Exception:
        metadata = {}

    artifacts = metadata.get("artifacts", [])
    artifact = next((a for a in artifacts if a.get("id") == artifact_id), None)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    mime_type = (artifact.get("mime_type") or "").lower()
    if "html" not in mime_type:
        return RedirectResponse(f"/snapshot/{note_id}/artifact/{artifact_id}")

    path = pathlib.Path(artifact.get("path", ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file missing")

    try:
        html_content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to read artifact content")

    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "iframe", "object", "embed"]):
        tag.decompose()

    safe_html = soup.prettify()
    page = f"""<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <title>Snapshot Preview</title>
    <style>
      body {{
        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        margin: 1.5rem;
        background-color: #0f172a;
        color: #e2e8f0;
      }}
      a {{ color: #38bdf8; }}
      img, video {{ max-width: 100%; height: auto; }}
      pre {{ white-space: pre-wrap; }}
    </style>
  </head>
  <body>
    {safe_html}
  </body>
</html>"""

    return HTMLResponse(content=page)
@app.get("/web/jobs")
def web_ingestion_jobs(request: Request, limit: int = 50):
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)

    try:
        limit = max(1, min(int(limit), 200))
    except Exception:
        limit = 50

    job_service = WebIngestionService(get_conn)
    jobs = job_service.list_jobs(current_user.id, limit=limit)

    return render_page(
        request,
        "web_jobs.html",
        {
            "jobs": jobs,
            "limit": limit,
            "user": current_user,
        },
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
        "UPDATE notes SET body = ?, content = ?, tags = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
        (content, content, tags, note_id, current_user.id),
    )
    row = c.execute(
        "SELECT title, summary, actions FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user.id),
    ).fetchone()
    if row:
        title, summary, actions = row
        c.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
        # FTS triggers keep notes_fts in sync; no manual insert needed
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
@app.head("/audio/{filename}")
def get_audio(filename: str, request: Request, token: str = None):
    # Use session-based authentication for audio files (works with HTML audio elements)
    current_user = get_current_user_silent(request)

    # If no session auth, try token-based auth as fallback for audio streaming
    if not current_user and token:
        try:
            from jose import jwt
            from services.auth_service import SECRET_KEY, ALGORITHM
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username:
                current_user = auth_service.get_user(username)
        except:
            pass

    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT 1 FROM notes WHERE audio_filename = ? AND user_id = ?",
        (filename, current_user.id),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Audio not found")

    # Try playback version first (better quality), fallback to converted version
    playback_filename = filename.replace('.converted.wav', '.playback.wav')
    playback_path = settings.audio_dir / playback_filename

    if playback_path.exists():
        return FileResponse(str(playback_path), media_type="audio/wav")

    # Fallback to original converted version
    audio_path = settings.audio_dir / filename
    if audio_path.exists():
        return FileResponse(str(audio_path), media_type="audio/wav")

    raise HTTPException(status_code=404, detail="Audio not found")

@app.get("/files/{filename}")
def get_file(filename: str, request: Request, token: str | None = None):
    """Serve uploaded files (images, PDFs, etc.) with auth.

    AuthN strategies:
    - Cookie-based session (preferred, same-origin)
    - Optional signed URL token (?token=...) for cross-origin or share links
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
                        resp = RedirectResponse("/dashboard/v3", status_code=302)
                        set_flash(resp, error_msg, "error")
                        return resp
                    out.write(chunk)

            # Process saved file
            processor = FileProcessor()
            result = processor.process_saved_file(tmp_path, file.filename)
            
            if not result['success']:
                error_msg = f"File processing failed: {result['error']}"
                if "application/json" in request.headers.get("accept", ""):
                    raise HTTPException(status_code=400, detail=error_msg)
                resp = RedirectResponse("/dashboard/v3", status_code=302)
                set_flash(resp, error_msg, "error")
                return resp
            
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
            resp = RedirectResponse("/dashboard/v3", status_code=302)
            set_flash(resp, error_msg, "error")
            return resp
    
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
                title, body, content, summary, tags, actions, type, timestamp, 
                audio_filename, file_filename, file_type, file_mime_type, 
                file_size, extracted_text, file_metadata, status, user_id,
                source_url, web_metadata, screenshot_path, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            title,
            content,
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
        
        conn.commit()
        
        # Trigger Smart Automation workflows
        try:
            from services.workflow_engine import TriggerType
            trigger_data = {
                "note_id": note_id,
                "user_id": current_user.id,
                "title": title,
                "content": content,
                "tags": tags,
                "note_type": note_type
            }
            
            # Trigger content created workflow (which includes URL detection)
            await workflow_engine.trigger_workflow(TriggerType.CONTENT_CREATED, trigger_data)
            
        except Exception as e:
            print(f"Smart Automation workflow trigger failed: {e}")
            # Continue without blocking the main capture flow
        
        # Queue background processing if needed
        if processing_status == "pending":
            # Prefer realtime-enabled enhanced tasks if available; otherwise fallback
            try:
                if REALTIME_AVAILABLE:
                    background_tasks.add_task(process_note_with_status, note_id)
                else:
                    background_tasks.add_task(process_note, note_id)
            except Exception:
                # Final fallback to basic processor
                background_tasks.add_task(process_note, note_id)
        
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
            resp = RedirectResponse("/dashboard/v3", status_code=302)
            set_flash(resp, success_msg, "success")
            return resp
            
    except Exception as e:
        conn.rollback()
        import logging, traceback
        logging.getLogger(__name__).error("Database insert failed in /capture: %s", e)
        logging.getLogger(__name__).error("Traceback:\n%s", traceback.format_exc())
        error_msg = f"Database error: {str(e)}"
        if "application/json" in request.headers.get("accept", ""):
            raise HTTPException(status_code=500, detail=error_msg)
        resp = RedirectResponse("/dashboard/v3", status_code=302)
        set_flash(resp, error_msg, "error")
        return resp
    finally:
        conn.close()

@app.post("/webhook/apple")
async def webhook_apple(
    data: dict = Body(...),
    authorization: str = Header(None)
):
    """Apple Shortcuts webhook handler with token authentication"""
    # Verify webhook token
    expected_token = settings.webhook_token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format. Use: Bearer <token>")

    token = authorization.split(" ", 1)[1].strip()
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    # Default to user ID 1 for Apple Shortcuts (adjust as needed)
    user_id = data.get("user_id", 1)

    return webhook_service.process_apple_webhook(data, user_id)

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

    base_query = "SELECT id, summary, type, COALESCE(timestamp, created_at) as timestamp FROM notes WHERE user_id = ?"
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
    base_query += " ORDER BY COALESCE(timestamp, created_at) DESC LIMIT 100"

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
# Removed duplicate analytics endpoint - kept first implementation at line ~2784
# Removed deprecated legacy search endpoint - functionality consolidated in main search service

@app.post("/webhook/discord/upload")
async def webhook_discord_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    note: str = Form(""),
    tags: str = Form(""),
    discord_user_id: str = Form(...),
    type: str = Form("discord_upload"),
    current_user: User = Depends(get_current_user_from_discord_header)
):
    """Discord-specific file upload webhook that bypasses CSRF"""
    return await webhook_service.process_discord_upload_webhook(file, note, tags, discord_user_id, type, background_tasks)

@app.post("/webhook/discord")
async def webhook_discord(
    data: dict = Body(...),
    current_user: User = Depends(get_current_user)
):
    """Discord webhook implementation"""
    return webhook_service.process_discord_webhook(data, current_user.id)

@app.get("/api/diagnostics")
def system_diagnostics(current_user: User = Depends(get_current_user)):
    """Advanced system diagnostics and performance analysis"""
    diagnostics = {
        "timestamp": datetime.utcnow().isoformat(),
        "database_analytics": {},
        "search_performance": {},
        "processing_analytics": {},
        "configuration_validation": {},
        "optimization_recommendations": []
    }
    
    try:
        # Database analytics and performance
        db_analytics = _get_database_analytics()
        diagnostics["database_analytics"] = db_analytics
        
        # Search system performance analysis
        search_analytics = _get_search_performance_analytics()
        diagnostics["search_performance"] = search_analytics
        
        # Processing pipeline analysis
        processing_analytics = _get_processing_analytics()
        diagnostics["processing_analytics"] = processing_analytics
        
        # Configuration validation
        config_validation = _validate_configuration()
        diagnostics["configuration_validation"] = config_validation
        
        # Generate optimization recommendations
        recommendations = _generate_optimization_recommendations(
            db_analytics, search_analytics, processing_analytics, config_validation
        )
        diagnostics["optimization_recommendations"] = recommendations
        
    except Exception as e:
        logger.error(f"Diagnostics error: {e}", exc_info=True)
        diagnostics["error"] = str(e)
    
    return diagnostics

@app.post("/api/diagnostics/auto-heal")
def auto_heal_system(current_user: User = Depends(get_current_user)):
    """Perform automatic system healing and optimization"""
    healing_results = {
        "timestamp": datetime.utcnow().isoformat(),
        "actions_performed": [],
        "errors": [],
        "recommendations": []
    }
    
    try:
        # Database optimization
        db_results = _perform_database_healing()
        healing_results["actions_performed"].extend(db_results.get("actions", []))
        healing_results["errors"].extend(db_results.get("errors", []))
        
        # Queue cleanup
        queue_results = _perform_queue_healing()
        healing_results["actions_performed"].extend(queue_results.get("actions", []))
        healing_results["errors"].extend(queue_results.get("errors", []))
        
        # Search index optimization
        search_results = _perform_search_healing()
        healing_results["actions_performed"].extend(search_results.get("actions", []))
        healing_results["errors"].extend(search_results.get("errors", []))
        
        # Directory structure healing
        dir_results = _perform_directory_healing()
        healing_results["actions_performed"].extend(dir_results.get("actions", []))
        healing_results["errors"].extend(dir_results.get("errors", []))
        
    except Exception as e:
        logger.error(f"Auto-heal error: {e}", exc_info=True)
        healing_results["errors"].append(f"Auto-heal failed: {str(e)}")
    
    return healing_results

def _get_database_analytics():
    """Get detailed database performance analytics"""
    analytics = {
        "table_statistics": {},
        "index_usage": {},
        "query_performance": {},
        "fragmentation": {}
    }
    
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # Table statistics with size information
        tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for table_row in tables:
            table = table_row[0]
            if not table.startswith('sqlite_'):
                count = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                
                # Get table size (approximation)
                page_count = c.execute(f"PRAGMA table_info({table})").fetchall()
                analytics["table_statistics"][table] = {
                    "row_count": count,
                    "column_count": len(page_count)
                }
        
        # Index analysis
        indexes = c.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'").fetchall()
        for idx_name, tbl_name in indexes:
            analytics["index_usage"][idx_name] = {"table": tbl_name}
        
        # Database file size and page info
        page_size = c.execute("PRAGMA page_size").fetchone()[0]
        page_count = c.execute("PRAGMA page_count").fetchone()[0]
        freelist_count = c.execute("PRAGMA freelist_count").fetchone()[0]
        
        analytics["fragmentation"] = {
            "page_size": page_size,
            "total_pages": page_count,
            "free_pages": freelist_count,
            "fragmentation_percent": round((freelist_count / max(page_count, 1)) * 100, 2),
            "database_size_mb": round((page_count * page_size) / (1024 * 1024), 2)
        }
        
        conn.close()
        
    except Exception as e:
        analytics["error"] = str(e)
    
    return analytics

def _get_search_performance_analytics():
    """Analyze search system performance"""
    analytics = {
        "fts_index_health": {},
        "search_patterns": {},
        "performance_metrics": {}
    }
    
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # FTS index analysis
        try:
            fts_stats = c.execute("SELECT COUNT(*) FROM notes_fts").fetchone()
            if fts_stats:
                analytics["fts_index_health"]["indexed_documents"] = fts_stats[0]
                analytics["fts_index_health"]["status"] = "functional"
                
                # Test search performance
                import time
                start_time = time.time()
                c.execute("SELECT COUNT(*) FROM notes_fts WHERE notes_fts MATCH 'test' LIMIT 10")
                search_time = (time.time() - start_time) * 1000
                analytics["performance_metrics"]["fts_search_time_ms"] = round(search_time, 2)
        except Exception as e:
            analytics["fts_index_health"]["status"] = "error"
            analytics["fts_index_health"]["error"] = str(e)
        
        # Search analytics if table exists
        try:
            recent_searches = c.execute("""
                SELECT query, COUNT(*) as frequency 
                FROM search_analytics 
                WHERE timestamp > datetime('now', '-7 days')
                GROUP BY query 
                ORDER BY frequency DESC 
                LIMIT 10
            """).fetchall()
            
            analytics["search_patterns"]["top_queries"] = [
                {"query": query, "frequency": freq} for query, freq in recent_searches
            ]
            
            avg_results = c.execute("""
                SELECT AVG(results_count) 
                FROM search_analytics 
                WHERE timestamp > datetime('now', '-7 days')
            """).fetchone()
            
            if avg_results and avg_results[0]:
                analytics["performance_metrics"]["avg_results_per_search"] = round(avg_results[0], 2)
                
        except sqlite3.OperationalError:
            # search_analytics table doesn't exist
            analytics["search_patterns"]["status"] = "no_analytics_data"
        
        conn.close()
        
    except Exception as e:
        analytics["error"] = str(e)
    
    return analytics

def _get_processing_analytics():
    """Analyze processing pipeline performance"""
    analytics = {
        "processing_stats": {},
        "bottlenecks": [],
        "resource_usage": {}
    }
    
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # Processing queue analytics
        queue_stats = c.execute("""
            SELECT 
                status,
                COUNT(*) as count,
                AVG(CASE 
                    WHEN started_at IS NOT NULL AND completed_at IS NOT NULL 
                    THEN (julianday(completed_at) - julianday(started_at)) * 1440 
                    END) as avg_processing_minutes
            FROM audio_processing_queue 
            GROUP BY status
        """).fetchall()
        
        for status, count, avg_time in queue_stats:
            analytics["processing_stats"][status] = {
                "count": count,
                "avg_processing_time_minutes": round(avg_time, 2) if avg_time else None
            }
        
        # Identify bottlenecks
        long_running = c.execute("""
            SELECT COUNT(*) 
            FROM audio_processing_queue 
            WHERE status = 'processing' 
            AND started_at < datetime('now', '-1 hour')
        """).fetchone()[0]
        
        if long_running > 0:
            analytics["bottlenecks"].append(f"{long_running} tasks running for over 1 hour")
        
        # Failed task analysis
        failed_reasons = c.execute("""
            SELECT status, COUNT(*) 
            FROM notes 
            WHERE status LIKE 'failed%' AND type = 'audio'
            GROUP BY status
        """).fetchall()
        
        if failed_reasons:
            analytics["processing_stats"]["failures"] = dict(failed_reasons)
        
        conn.close()
        
    except Exception as e:
        analytics["error"] = str(e)
    
    return analytics

def _validate_configuration():
    """Validate system configuration"""
    validation = {
        "ollama_config": {},
        "whisper_config": {},
        "email_config": {},
        "paths_config": {},
        "warnings": []
    }
    
    # Ollama configuration
    validation["ollama_config"] = {
        "api_url": settings.ollama_api_url,
        "model": settings.ollama_model,
        "configured": bool(settings.ollama_api_url and settings.ollama_model)
    }
    
    # Whisper configuration
    whisper_exists = settings.whisper_cpp_path.exists()
    model_exists = settings.whisper_model_path.exists()
    
    validation["whisper_config"] = {
        "binary_path": str(settings.whisper_cpp_path),
        "binary_exists": whisper_exists,
        "model_path": str(settings.whisper_model_path),
        "model_exists": model_exists,
        "transcriber": settings.transcriber
    }
    
    if not whisper_exists:
        validation["warnings"].append("Whisper binary not found")
    if not model_exists:
        validation["warnings"].append("Whisper model file not found")
    
    # Email configuration
    validation["email_config"] = {
        "enabled": settings.email_enabled,
        "service": settings.email_service,
        "configured": bool(settings.email_api_key) if settings.email_enabled else True
    }
    
    # Path configuration
    paths_to_check = {
        "vault": settings.vault_path,
        "audio": settings.audio_dir,
        "uploads": settings.uploads_dir
    }
    
    for name, path in paths_to_check.items():
        validation["paths_config"][name] = {
            "path": str(path),
            "exists": path.exists(),
            "writable": path.exists() and os.access(path, os.W_OK)
        }
        
        if not path.exists():
            validation["warnings"].append(f"Path does not exist: {name}")
    
    return validation

def _generate_optimization_recommendations(db_analytics, search_analytics, processing_analytics, config_validation):
    """Generate system optimization recommendations"""
    recommendations = []
    
    # Database optimization recommendations
    fragmentation = db_analytics.get("fragmentation", {})
    if fragmentation.get("fragmentation_percent", 0) > 10:
        recommendations.append({
            "category": "database",
            "priority": "medium",
            "title": "Database fragmentation detected",
            "description": f"Database is {fragmentation['fragmentation_percent']:.1f}% fragmented",
            "action": "Run VACUUM command to defragment database",
            "auto_fixable": True
        })
    
    # Search index recommendations
    fts_health = search_analytics.get("fts_index_health", {})
    if fts_health.get("status") == "error":
        recommendations.append({
            "category": "search",
            "priority": "high",
            "title": "FTS index issues detected",
            "description": f"Search index error: {fts_health.get('error', 'Unknown error')}",
            "action": "Rebuild FTS search index",
            "auto_fixable": True
        })
    
    # Processing queue recommendations
    processing_stats = processing_analytics.get("processing_stats", {})
    if processing_stats.get("processing", {}).get("count", 0) > 10:
        recommendations.append({
            "category": "processing",
            "priority": "medium",
            "title": "Large processing queue detected",
            "description": f"{processing_stats['processing']['count']} items currently processing",
            "action": "Consider increasing processing concurrency",
            "auto_fixable": False
        })
    
    # Configuration recommendations
    warnings = config_validation.get("warnings", [])
    for warning in warnings:
        recommendations.append({
            "category": "configuration",
            "priority": "high" if "not found" in warning else "medium",
            "title": "Configuration issue",
            "description": warning,
            "action": "Check configuration and file paths",
            "auto_fixable": False
        })
    
    return recommendations

def _perform_database_healing():
    """Perform automatic database optimization"""
    results = {"actions": [], "errors": []}
    
    try:
        conn = get_conn()
        
        # Check if VACUUM is needed
        fragmentation_check = conn.execute("PRAGMA freelist_count").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        
        if fragmentation_check > 0 and (fragmentation_check / max(page_count, 1)) > 0.1:
            conn.execute("VACUUM")
            results["actions"].append("Database defragmented using VACUUM")
        
        # Optimize database
        conn.execute("PRAGMA optimize")
        results["actions"].append("Database statistics optimized")
        
        conn.close()
        
    except Exception as e:
        results["errors"].append(f"Database healing error: {str(e)}")
    
    return results

def _perform_queue_healing():
    """Clean up stalled processing queue items"""
    results = {"actions": [], "errors": []}
    
    try:
        from services.audio_queue import audio_queue
        
        # Reset stalled tasks (processing for more than 4 hours)
        stalled_threshold = datetime.utcnow() - timedelta(hours=4)
        
        conn = get_conn()
        c = conn.cursor()
        
        stalled_tasks = c.execute("""
            SELECT note_id FROM audio_processing_queue 
            WHERE status = 'processing' AND started_at < ?
        """, (stalled_threshold.isoformat(),)).fetchall()
        
        if stalled_tasks:
            c.execute("""
                UPDATE audio_processing_queue 
                SET status = 'queued', started_at = NULL 
                WHERE status = 'processing' AND started_at < ?
            """, (stalled_threshold.isoformat(),))
            
            conn.commit()
            results["actions"].append(f"Reset {len(stalled_tasks)} stalled processing tasks")
        
        conn.close()
        
    except Exception as e:
        results["errors"].append(f"Queue healing error: {str(e)}")
    
    return results

def _perform_search_healing():
    """Optimize search indexes"""
    results = {"actions": [], "errors": []}
    
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # Check if FTS index needs rebuilding
        try:
            c.execute("SELECT COUNT(*) FROM notes_fts WHERE notes_fts MATCH 'test' LIMIT 1")
            results["actions"].append("FTS index verified as functional")
        except Exception as e:
            # Try to rebuild FTS index
            try:
                c.execute("INSERT INTO notes_fts(notes_fts) VALUES('rebuild')")
                results["actions"].append("FTS index rebuilt")
            except Exception as rebuild_error:
                results["errors"].append(f"FTS index rebuild failed: {str(rebuild_error)}")
        
        conn.close()
        
    except Exception as e:
        results["errors"].append(f"Search healing error: {str(e)}")
    
    return results

def _perform_directory_healing():
    """Ensure required directories exist"""
    results = {"actions": [], "errors": []}
    
    try:
        required_dirs = [
            settings.vault_path,
            settings.audio_dir,
            settings.uploads_dir
        ]
        
        for dir_path in required_dirs:
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                results["actions"].append(f"Created missing directory: {dir_path}")
        
    except Exception as e:
        results["errors"].append(f"Directory healing error: {str(e)}")
    
    return results

# Add this to your app.py - Browser Extension Integration

from typing import Dict, Any
# Unused imports removed - moved to webhook service

# BrowserCapture model moved to services/webhook_service.py

@app.post("/webhook/browser")
async def webhook_browser(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """Enhanced browser capture endpoint with metadata processing"""
    from services.webhook_service import BrowserCapture
    webhook_data = BrowserCapture(**data)
    return await webhook_service.process_browser_webhook(webhook_data, current_user.id)

# Helper functions moved to webhook_service.py

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
    
    query += " ORDER BY COALESCE(timestamp, created_at) DESC LIMIT ?"
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

# Removed unused database migration function add_browser_capture_columns()

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
        # Keep body and content in sync during transition
        updates.append("body = ?")
        params.append(update_data['content'])
        updates.append("content = ?")
        params.append(update_data['content'])
    
    if 'tags' in update_data and update_data['tags'] is not None:
        updates.append("tags = ?")
        params.append(update_data['tags'])
    
    if updates:
        # Add timestamp and updated_at
        updates.append("timestamp = ?")
        params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        updates.append("updated_at = datetime('now')")
        
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
        SET title = ?, body = ?, content = ?, tags = ?, timestamp = ?, updated_at = datetime('now')
        WHERE id = ? AND user_id = ?
    """, (
        update_data.get('title', ''),
        update_data.get('content', ''),
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

# Admin Endpoints for Discord Bot
@app.post("/api/admin/restart-tasks")
async def restart_processing_tasks(
    request: dict,
    current_user: User = Depends(get_current_user)
):
    """Restart processing tasks (for Discord bot admin commands)"""
    task_type = request.get("task_type", "failed")
    
    conn = get_conn()
    cursor = conn.cursor()
    
    try:
        if task_type == "all":
            cursor.execute("UPDATE processing_tasks SET status = 'pending' WHERE status != 'completed'")
        elif task_type == "failed":
            cursor.execute("UPDATE processing_tasks SET status = 'pending' WHERE status = 'failed'")
        elif task_type == "pending":
            # Reset stuck pending tasks
            cursor.execute(
                "UPDATE processing_tasks SET status = 'pending' WHERE status = 'pending' AND updated_at < datetime('now', '-1 hour')"
            )
        
        restarted = cursor.rowcount
        conn.commit()
        
        return {
            "status": "success",
            "restarted": restarted,
            "task_type": task_type
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

@app.post("/api/admin/cleanup") 
async def cleanup_old_data(
    request: dict,
    current_user: User = Depends(get_current_user)
):
    """Clean up old data (for Discord bot admin commands)"""
    days = request.get("days", 30)
    
    conn = get_conn()
    cursor = conn.cursor()
    
    try:
        # Remove old completed processing tasks
        cursor.execute(
            "DELETE FROM processing_tasks WHERE status = 'completed' AND created_at < datetime('now', '-{} days')".format(days)
        )
        removed_tasks = cursor.rowcount
        
        # Remove old magic link tokens
        cursor.execute(
            "DELETE FROM magic_links WHERE expires_at < datetime('now')"
        )
        removed_links = cursor.rowcount
        
        # Get database size before cleanup
        cursor.execute("PRAGMA page_count")
        page_count = cursor.fetchone()[0]
        cursor.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        
        # Run VACUUM to reclaim space
        cursor.execute("VACUUM")
        
        conn.commit()
        
        # Calculate approximate space freed (rough estimate)
        space_freed_mb = (removed_tasks + removed_links) * 0.01  # Very rough estimate
        
        return {
            "status": "success", 
            "removed": removed_tasks + removed_links,
            "space_freed": round(space_freed_mb, 2),
            "details": {
                "removed_tasks": removed_tasks,
                "removed_links": removed_links
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

@app.get("/api/stats")
async def get_system_stats(current_user: User = Depends(get_current_user)):
    """Get system statistics (for Discord bot)"""
    conn = get_conn()
    cursor = conn.cursor()
    
    try:
        # Get note stats
        cursor.execute("SELECT COUNT(*) FROM notes")
        total_notes = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT tags) FROM (SELECT TRIM(tag) as tags FROM notes, json_each('["' || REPLACE(REPLACE(tags, ',', '","'), ' ', '') || '"]') WHERE tags IS NOT NULL AND tags != '')")
        total_tags = cursor.fetchone()[0] if cursor.fetchone() else 0
        
        cursor.execute("SELECT COUNT(*) FROM notes WHERE type IN ('audio', 'image', 'pdf', 'file')")
        total_files = cursor.fetchone()[0]
        
        # Get search stats (approximate)
        total_searches = 0  # Would track in separate table in production
        avg_response_time = 150  # Placeholder
        
        return {
            "total_notes": total_notes,
            "total_tags": total_tags, 
            "total_files": total_files,
            "total_searches": total_searches,
            "avg_response_time": avg_response_time
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

@app.get("/api/notes/recent")
async def get_recent_notes(
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user)
):
    """Get recent notes (for Discord bot)"""
    conn = get_conn()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            SELECT id, title, COALESCE(body, content) AS content,
                   COALESCE(timestamp, created_at, updated_at) AS sort_ts,
                   type, tags
            FROM notes 
            WHERE user_id = ?
            ORDER BY sort_ts DESC 
            LIMIT ?
            """,
            (current_user.id, limit)
        )
        
        notes = []
        for row in cursor.fetchall():
            notes.append({
                "id": row[0],
                "title": row[1] or "Untitled",
                "content": (row[2] or "")[:200],  # Truncate for Discord
                "created_at": row[3],
                "type": row[4],
                "tags": row[5]
            })
        
        return notes
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()
@app.get("/api/snapshots")
async def get_snapshots_list(
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    """Get list of notes with snapshot data (clean URL implementation)"""
    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id, title, summary,
                   COALESCE(timestamp, created_at, updated_at) AS sort_ts,
                   file_metadata
            FROM notes
            WHERE user_id = ? AND file_metadata IS NOT NULL AND file_metadata != ''
            ORDER BY sort_ts DESC
            LIMIT ?
            """,
            (current_user.id, limit)
        )

        snapshots = []
        for row in cursor.fetchall():
            snapshot_data = {
                "id": row[0],
                "title": row[1] or "Untitled Snapshot",
                "summary": row[2],
                "created_at": row[3],
                "file_metadata": row[4]
            }
            snapshots.append(snapshot_data)

        return snapshots
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()
@app.get("/api/snapshot/{note_id}")
async def get_snapshot_data(
    note_id: int,
    current_user: User = Depends(get_current_user)
):
    """Get detailed snapshot data for a specific note (clean URL implementation)"""
    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT * FROM notes WHERE id = ? AND user_id = ?",
            (note_id, current_user.id)
        )

        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Snapshot not found")

        # Get column names
        columns = [col[0] for col in cursor.description]
        note = dict(zip(columns, row))

        # Parse file metadata
        file_metadata = {}
        if note.get("file_metadata"):
            try:
                file_metadata = json.loads(note["file_metadata"])
            except Exception:
                file_metadata = {}

        # Parse manifest if available
        manifest = {}
        manifest_path = file_metadata.get("manifest_path")
        if manifest_path:
            try:
                manifest_full_path = pathlib.Path(settings.base_dir) / manifest_path
                if manifest_full_path.exists():
                    with open(manifest_full_path, 'r') as f:
                        manifest = json.load(f)
            except Exception:
                manifest = {}

        # Get artifacts
        artifacts = []
        artifacts_data = file_metadata.get("artifacts", [])
        for artifact in artifacts_data:
            artifact_entry = artifact.copy()
            # Create view URLs without exposing internal paths
            if artifact.get("path"):
                artifact_id = artifact.get("id") or f"artifact_{len(artifacts)}"
                artifact_entry["view_url"] = f"/snapshot/{note_id}/artifact/{artifact_id}"

                # Check if it's HTML for inline viewing
                mime_type = artifact.get("mime_type", "")
                if "html" in mime_type:
                    artifact_entry["inline_url"] = f"/snapshot/{note_id}/artifact/{artifact_id}/inline"

            artifacts.append(artifact_entry)

        return {
            "note": note,
            "manifest": manifest,
            "file_metadata": file_metadata,
            "artifacts": artifacts
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

def verify_webhook_token_local(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme)):
    # Delegate to auth service imported function
    from services.auth_service import verify_webhook_token
    return verify_webhook_token(credentials)

# ============================================================================
# Frontend API Endpoints for Dashboard v2
# ============================================================================

@app.get("/api/auth/token")
async def get_auth_token(request: Request, current_user: User = Depends(get_current_user)):
    """
    Get authentication token for the current user.
    Used by frontend for authenticated audio file access.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {
        "token": token,
        "user_id": current_user.id,
        "username": current_user.username
    }

@app.get("/api/notes")
async def api_get_notes(
    limit: int = Query(10, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user)
):
    """Get notes for the current user with rich metadata for the Notes view."""
    conn = get_conn()
    c = conn.cursor()
    
    try:
        # Include optional file + source fields so the Notes view can classify
        rows = c.execute(
            """
            SELECT 
                id,
                title,
                body,
                content,
                summary,
                tags,
                type,
                status,
                timestamp,
                created_at,
                updated_at,
                audio_filename,
                file_filename,
                file_type,
                file_mime_type,
                source_url
            FROM notes 
            WHERE user_id = ? 
            ORDER BY COALESCE(timestamp, created_at, updated_at) DESC 
            LIMIT ? OFFSET ?
            """,
            (current_user.id, limit, offset),
        ).fetchall()

        notes = []
        col_names = [col[0] for col in c.description]
        for row in rows:
            note = dict(zip(col_names, row))
            # Normalize timestamps for frontend
            note["created_at"] = note.get("created_at") or note.get("timestamp") or note.get("updated_at")
            # Derive basic file classification if not explicitly set
            mt = (note.get("file_mime_type") or "").lower()
            if not note.get("type") and note.get("audio_filename"):
                note["type"] = "audio"
            elif not note.get("type") and mt.startswith("image/"):
                note["type"] = "image"

            # Normalize tags
            tags_raw = note.get("tags") or ""
            if isinstance(tags_raw, str):
                tags_list = [t.strip() for t in tags_raw.replace("#", " ").replace(",", " ").split() if t.strip()]
            elif isinstance(tags_raw, list):
                tags_list = [str(t).strip() for t in tags_raw if str(t).strip()]
            else:
                tags_list = []
            note["tags_list"] = tags_list

            # Enrich with preview URL for images/PDFs
            try:
                ff = note.get("file_filename")
                ft = (note.get("file_type") or "").lower()
                typ = (note.get("type") or "").lower()
                if ff and (ft == "image" or typ == "image" or mt.startswith("image/") or ft == "document" or mt == "application/pdf"):
                    note["file_url"] = f"/files/{ff}"
            except Exception:
                pass

            # Lightweight metadata
            try:
                if (note.get("type") or "").lower() == "audio":
                    note["audio_duration_hms"] = _audio_duration_from_note(note)
            except Exception:
                pass
            notes.append(note)
        return notes
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch notes: {str(e)}")
    finally:
        conn.close()

@app.post("/api/notes")
async def api_create_note(
    note_data: dict = Body(...),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user)
):
    """Create a new note"""
    title = note_data.get('title', '').strip()
    content = note_data.get('content', '').strip()
    tags = note_data.get('tags', '').strip()
    
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    
    # Generate title if not provided
    if not title:
        try:
            title = ollama_generate_title(content)
            if not title or title.strip() == "":
                title = content[:50] + ("..." if len(content) > 50 else "")
        except:
            title = content[:50] + ("..." if len(content) > 50 else "")
    
    conn = get_conn()
    c = conn.cursor()
    
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO notes (title, body, content, tags, type, timestamp, user_id, status) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, content, content, tags, 'text', now, current_user.id, 'active'))
        
        note_id = c.lastrowid
        conn.commit()
        
        note_payload = {
            "id": note_id,
            "title": title,
            "content": content,
            "tags": tags,
            "created_at": now,
            "status": "created"
        }

        # Send notification about note creation
        await notify_note_created(current_user.id, str(note_id), title)

        # Broadcast realtime update
        await notify_note_change(current_user.id, "created", note_payload)
        
        # Queue for AI processing if available
        if background_tasks:
            background_tasks.add_task(process_note, note_id)
        
        return note_payload
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create note: {str(e)}")
    finally:
        conn.close()

@app.get("/api/search")
async def api_search_notes(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user)
):
    """Search notes using the unified search service"""
    try:
        from services.search_adapter import get_search_service
        search_service = get_search_service()
        
        # Use the unified search service
        results = search_service.search(
            query=q,
            user_id=current_user.id,
            limit=limit,
            mode="hybrid"  # Use hybrid search by default
        )
        
        return results.get("results", [])
    except Exception as e:
        # Fallback to basic SQL search if unified search fails
        conn = get_conn()
        c = conn.cursor()
        
        try:
            search_query = f"%{q}%"
            rows = c.execute("""
                SELECT id, title, content, summary, tags, type, timestamp, created_at, updated_at
                FROM notes 
                WHERE user_id = ? AND (
                    title LIKE ? OR 
                    content LIKE ? OR 
                    summary LIKE ? OR 
                    tags LIKE ?
                )
                ORDER BY COALESCE(timestamp, created_at, updated_at) DESC 
                LIMIT ?
            """, (current_user.id, search_query, search_query, search_query, search_query, limit)).fetchall()
            
            results = []
            for row in rows:
                note_dict = dict(zip([col[0] for col in c.description], row))
                created_at = note_dict.get('created_at') or note_dict.get('timestamp') or note_dict.get('updated_at')
                note_dict['created_at'] = created_at
                results.append(note_dict)
            
            return results
        except Exception as fallback_error:
            raise HTTPException(status_code=500, detail=f"Search failed: {str(fallback_error)}")
        finally:
            conn.close()

@app.get("/api/stats")
async def api_get_stats(current_user: User = Depends(get_current_user)):
    """Get user statistics"""
    conn = get_conn()
    c = conn.cursor()
    
    try:
        # Total notes
        total_notes = c.execute(
            "SELECT COUNT(*) FROM notes WHERE user_id = ? AND status != 'deleted'",
            (current_user.id,)
        ).fetchone()[0]
        
        # Notes from this week
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        weekly_notes = c.execute("""
            SELECT COUNT(*) FROM notes 
            WHERE user_id = ? AND status != 'deleted' 
            AND COALESCE(timestamp, created_at, updated_at) >= ?
        """, (current_user.id, week_ago)).fetchone()[0]
        
        return {
            "total_notes": total_notes,
            "weekly_notes": weekly_notes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")
    finally:
        conn.close()

# Additional API endpoints for enhanced frontend

@app.get("/api/notes/{note_id}")
async def api_get_note(note_id: int, current_user: User = Depends(get_current_user)):
    """Get a specific note by ID"""
    conn = get_conn()
    c = conn.cursor()
    
    try:
        row = c.execute("""
            SELECT 
                id,
                title,
                content,
                body,
                summary,
                tags,
                type,
                status,
                timestamp,
                created_at,
                updated_at,
                audio_filename,
                file_filename,
                file_type,
                file_mime_type,
                actions
            FROM notes 
            WHERE id = ? AND user_id = ?
        """, (note_id, current_user.id)).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Note not found")
        
        note_dict = dict(zip([col[0] for col in c.description], row))
        # Ensure we have a display date
        created_at = note_dict.get('created_at') or note_dict.get('timestamp') or note_dict.get('updated_at')
        note_dict['created_at'] = created_at
        
        # Provide audio filename fallback for legacy notes
        if not note_dict.get('audio_filename') and (note_dict.get('type') or '').lower() == 'audio':
            original = note_dict.get('file_filename')
            if original:
                note_dict['audio_filename'] = original
        
        # Expose an explicit audio URL to simplify frontend logic (auth enforced by endpoint)
        audio_filename = note_dict.get('audio_filename')
        if audio_filename:
            note_dict['audio_url'] = f"/audio/{audio_filename}"

        return note_dict
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch note: {str(e)}")
    finally:
        conn.close()

@app.put("/api/notes/{note_id}")
async def api_update_note(
    note_id: int,
    note_data: dict = Body(...),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user)
):
    """Update a specific note"""
    conn = get_conn()
    c = conn.cursor()
    
    try:
        # Verify note exists and belongs to user
        existing = c.execute(
            "SELECT id FROM notes WHERE id = ? AND user_id = ?",
            (note_id, current_user.id)
        ).fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="Note not found")
        
        title = note_data.get('title', '').strip()
        content = note_data.get('content', '').strip()
        tags = note_data.get('tags', '').strip()
        
        if not content:
            raise HTTPException(status_code=400, detail="Content is required")
        
        # Update note
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            UPDATE notes 
            SET title = ?, content = ?, body = ?, tags = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        """, (title, content, content, tags, now, note_id, current_user.id))
        
        conn.commit()

        note_response = {
            "id": note_id,
            "title": title,
            "content": content,
            "tags": tags,
            "updated_at": now,
            "status": "updated"
        }

        # Broadcast realtime update
        await notify_note_change(current_user.id, "updated", note_response)

        # Queue for AI processing if available
        if background_tasks:
            background_tasks.add_task(process_note, note_id)
        
        return note_response
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update note: {str(e)}")
    finally:
        conn.close()

@app.delete("/api/notes/{note_id}")
async def api_delete_note(note_id: int, current_user: User = Depends(get_current_user)):
    """Delete a specific note"""
    conn = get_conn()
    c = conn.cursor()
    
    try:
        # Verify note exists and belongs to user
        existing = c.execute(
            "SELECT id FROM notes WHERE id = ? AND user_id = ?",
            (note_id, current_user.id)
        ).fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="Note not found")
        
        # Soft delete by updating status
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            UPDATE notes 
            SET status = 'deleted', updated_at = ?
            WHERE id = ? AND user_id = ?
        """, (now, note_id, current_user.id))
        
        conn.commit()

        payload = {"status": "deleted", "id": note_id}
        await notify_note_change(current_user.id, "deleted", payload)
        
        return payload
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete note: {str(e)}")
    finally:
        conn.close()

@app.get("/api/notes/random")
async def api_get_random_note(current_user: User = Depends(get_current_user)):
    """Get a random note"""
    conn = get_conn()
    c = conn.cursor()
    
    try:
        row = c.execute("""
            SELECT id, title, content, summary, tags, type, status, timestamp, created_at, updated_at
            FROM notes 
            WHERE user_id = ? AND status != 'deleted' 
            ORDER BY RANDOM() 
            LIMIT 1
        """, (current_user.id,)).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="No notes found")
        
        note_dict = dict(zip([col[0] for col in c.description], row))
        created_at = note_dict.get('created_at') or note_dict.get('timestamp') or note_dict.get('updated_at')
        note_dict['created_at'] = created_at
        
        return note_dict
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch random note: {str(e)}")
    finally:
        conn.close()

@app.get("/api/search/advanced")
async def api_advanced_search(
    q: str = Query("", description="Search query"),
    date_range: str = Query("", description="Date range filter"),
    type: str = Query("", description="Note type filter"), 
    tags: str = Query("", description="Tags filter"),
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user)
):
    """Advanced search with filters"""
    conn = get_conn()
    c = conn.cursor()
    
    try:
        # Build query conditions
        conditions = ["user_id = ?", "status != 'deleted'"]
        params = [current_user.id]
        
        # Text search
        if q:
            conditions.append("(title LIKE ? OR content LIKE ? OR summary LIKE ?)")
            search_term = f"%{q}%"
            params.extend([search_term, search_term, search_term])
        
        # Date range filter
        if date_range:
            now = datetime.now()
            if date_range == "today":
                start_date = now.strftime("%Y-%m-%d 00:00:00")
                conditions.append("COALESCE(timestamp, created_at, updated_at) >= ?")
                params.append(start_date)
            elif date_range == "week":
                start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
                conditions.append("COALESCE(timestamp, created_at, updated_at) >= ?")
                params.append(start_date)
            elif date_range == "month":
                start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
                conditions.append("COALESCE(timestamp, created_at, updated_at) >= ?")
                params.append(start_date)
            elif date_range == "year":
                start_date = (now - timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
                conditions.append("COALESCE(timestamp, created_at, updated_at) >= ?")
                params.append(start_date)
        
        # Type filter
        if type:
            conditions.append("type = ?")
            params.append(type)
        
        # Tags filter
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
            tag_conditions = []
            for tag in tag_list:
                tag_conditions.append("tags LIKE ?")
                params.append(f"%{tag}%")
            if tag_conditions:
                conditions.append(f"({' OR '.join(tag_conditions)})")
        
        # Execute query
        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, title, content, summary, tags, type, timestamp, created_at, updated_at
            FROM notes 
            WHERE {where_clause}
            ORDER BY COALESCE(timestamp, created_at, updated_at) DESC 
            LIMIT ?
        """
        params.append(limit)
        
        rows = c.execute(query, params).fetchall()
        
        results = []
        for row in rows:
            note_dict = dict(zip([col[0] for col in c.description], row))
            created_at = note_dict.get('created_at') or note_dict.get('timestamp') or note_dict.get('updated_at')
            note_dict['created_at'] = created_at
            results.append(note_dict)
        
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Advanced search failed: {str(e)}")
    finally:
        conn.close()

@app.get("/api/export/{format}")
async def api_export_notes(
    format: str,
    current_user: User = Depends(get_current_user)
):
    """Export notes in various formats"""
    if format not in ["json", "csv", "markdown"]:
        raise HTTPException(status_code=400, detail="Unsupported export format")
    
    conn = get_conn()
    c = conn.cursor()
    
    try:
        rows = c.execute("""
            SELECT id, title, content, summary, tags, type, timestamp, created_at, updated_at
            FROM notes 
            WHERE user_id = ? AND status != 'deleted'
            ORDER BY COALESCE(timestamp, created_at, updated_at) DESC
        """, (current_user.id,)).fetchall()
        
        notes = []
        for row in rows:
            note_dict = dict(zip([col[0] for col in c.description], row))
            created_at = note_dict.get('created_at') or note_dict.get('timestamp') or note_dict.get('updated_at')
            note_dict['created_at'] = created_at
            notes.append(note_dict)
        
        if format == "json":
            content = json.dumps(notes, indent=2, default=str)
            media_type = "application/json"
        elif format == "csv":
            import csv
            import io
            output = io.StringIO()
            if notes:
                fieldnames = notes[0].keys()
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(notes)
            content = output.getvalue()
            media_type = "text/csv"
        elif format == "markdown":
            content = "# Second Brain Export\n\n"
            for note in notes:
                content += f"## {note.get('title', 'Untitled')}\n\n"
                if note.get('tags'):
                    content += f"**Tags:** {note['tags']}\n\n"
                content += f"{note.get('content', '')}\n\n"
                content += f"*Created: {note.get('created_at', 'Unknown')}*\n\n"
                content += "---\n\n"
            media_type = "text/markdown"
        
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename=second-brain-export.{format}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
    finally:
        conn.close()

# WebSocket Connection Manager for Real-time Updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict = {}  # user_id -> list of websockets
    
    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        print(f"User {user_id} connected. Active connections: {len(self.active_connections.get(user_id, []))}")
    
    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        print(f"User {user_id} disconnected. Active connections: {len(self.active_connections.get(user_id, []))}")
    
    async def send_to_user(self, user_id: int, message: dict):
        if user_id in self.active_connections:
            disconnected = []
            for websocket in self.active_connections[user_id]:
                try:
                    await websocket.send_json(message)
                except:
                    disconnected.append(websocket)
            
            # Clean up disconnected websockets
            for ws in disconnected:
                self.disconnect(ws, user_id)
    
    async def broadcast_to_all(self, message: dict):
        for user_id in list(self.active_connections.keys()):
            await self.send_to_user(user_id, message)

# Use enhanced WebSocket connection manager
manager = get_connection_manager()

# WebSocket endpoint for real-time updates
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    connection_id = await manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            await manager.handle_message(connection_id, data)
    except WebSocketDisconnect:
        await manager.disconnect(connection_id, user_id)

# Enhanced note creation with real-time updates
async def notify_note_change(user_id: int, action: str, note_data: dict) -> None:
    """Backward-compatible wrapper around realtime broadcast helper."""
    await notify_note_update(user_id, action, note_data)

# Update existing endpoints to include real-time notifications
@app.post("/api/notes/realtime")
async def api_create_note_realtime(
    note_data: dict = Body(...),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user)
):
    """Create a new note with real-time notifications"""
    title = note_data.get('title', '').strip()
    content = note_data.get('content', '').strip()
    tags = note_data.get('tags', '').strip()
    
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    
    # Generate title if not provided
    if not title:
        try:
            title = ollama_generate_title(content)
            if not title or title.strip() == "":
                title = content[:50] + ("..." if len(content) > 50 else "")
        except:
            title = content[:50] + ("..." if len(content) > 50 else "")
    
    conn = get_conn()
    c = conn.cursor()
    
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO notes (title, body, content, tags, type, timestamp, user_id, status) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, content, content, tags, 'text', now, current_user.id, 'active'))
        
        note_id = c.lastrowid
        conn.commit()
        
        note_response = {
            "id": note_id,
            "title": title,
            "content": content,
            "tags": tags,
            "created_at": now,
            "status": "created"
        }
        
        # Send real-time notification
        await notify_note_change(current_user.id, "created", note_response)
        
        # Queue for AI processing if available
        if background_tasks:
            background_tasks.add_task(process_note, note_id)
        
        return note_response
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create note: {str(e)}")
    finally:
        conn.close()

@app.put("/api/notes/{note_id}/realtime")
async def api_update_note_realtime(
    note_id: int,
    note_data: dict = Body(...),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user)
):
    """Update a specific note with real-time notifications"""
    conn = get_conn()
    c = conn.cursor()
    
    try:
        # Verify note exists and belongs to user
        existing = c.execute(
            "SELECT id FROM notes WHERE id = ? AND user_id = ?",
            (note_id, current_user.id)
        ).fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="Note not found")
        
        title = note_data.get('title', '').strip()
        content = note_data.get('content', '').strip()
        tags = note_data.get('tags', '').strip()
        
        if not content:
            raise HTTPException(status_code=400, detail="Content is required")
        
        # Update note
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            UPDATE notes 
            SET title = ?, content = ?, body = ?, tags = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        """, (title, content, content, tags, now, note_id, current_user.id))
        
        conn.commit()
        
        note_response = {
            "id": note_id,
            "title": title,
            "content": content,
            "tags": tags,
            "updated_at": now,
            "status": "updated"
        }
        
        # Send real-time notification
        await notify_note_change(current_user.id, "updated", note_response)
        
        # Queue for AI processing if available
        if background_tasks:
            background_tasks.add_task(process_note, note_id)
        
        return note_response
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update note: {str(e)}")
    finally:
        conn.close()

@app.delete("/api/notes/{note_id}/realtime")
async def api_delete_note_realtime(note_id: int, current_user: User = Depends(get_current_user)):
    """Delete a specific note with real-time notifications"""
    conn = get_conn()
    c = conn.cursor()
    
    try:
        # Get note data before deletion for notification
        note_row = c.execute(
            "SELECT id, title FROM notes WHERE id = ? AND user_id = ?",
            (note_id, current_user.id)
        ).fetchone()
        
        if not note_row:
            raise HTTPException(status_code=404, detail="Note not found")
        
        # Soft delete by updating status
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            UPDATE notes 
            SET status = 'deleted', updated_at = ?
            WHERE id = ? AND user_id = ?
        """, (now, note_id, current_user.id))
        
        conn.commit()
        
        # Send real-time notification
        await notify_note_change(current_user.id, "deleted", {
            "id": note_id,
            "title": note_row[1] if note_row else f"Note {note_id}",
            "status": "deleted"
        })
        
        return {"status": "deleted", "id": note_id}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete note: {str(e)}")
    finally:
        conn.close()

# System status endpoint for monitoring
@app.get("/api/system/status")
async def get_system_status():
    """Get system status including WebSocket connections"""
    total_connections = sum(len(connections) for connections in manager.active_connections.values())
    return {
        "status": "healthy",
        "websocket_connections": total_connections,
        "connected_users": len(manager.active_connections),
        "timestamp": datetime.now().isoformat()
    }

# ===== AI ASSISTANT API ENDPOINTS =====

@app.post("/api/suggest-tags")
async def api_suggest_tags(
    request_data: dict = Body(...),
    current_user: User = Depends(get_current_user)
):
    """Generate tag suggestions for note content using AI"""
    content = request_data.get('content', '')
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    
    try:
        # Use Ollama to generate tag suggestions
        prompt = f"""Analyze the following text and suggest 3-5 relevant tags that would help categorize this note. 
        Return only the tags as a comma-separated list, no explanations:

        {content[:1000]}"""  # Limit content to avoid token limits
        
        # Try to get AI suggestions
        try:
            from llm_utils import ollama_generate
            ai_response = ollama_generate(prompt)
            if ai_response and ai_response.strip():
                tags = [tag.strip() for tag in ai_response.split(',') if tag.strip()]
                tags = tags[:5]  # Limit to 5 tags max
            else:
                raise Exception("Empty AI response")
        except Exception as ai_error:
            # Fallback to rule-based tag generation
            tags = generate_fallback_tags(content)
        
        return {"tags": tags}
    except Exception as e:
        # Return fallback tags even on error
        fallback_tags = generate_fallback_tags(content)
        return {"tags": fallback_tags}

def generate_fallback_tags(content):
    """Generate tags using simple keyword matching"""
    tags = []
    content_lower = content.lower()
    
    # Common tag patterns
    if any(word in content_lower for word in ['meeting', 'call', 'discussion', 'conference']):
        tags.append('meeting')
    if any(word in content_lower for word in ['project', 'task', 'todo', 'deadline']):
        tags.append('project')
    if any(word in content_lower for word in ['idea', 'brainstorm', 'concept', 'thought']):
        tags.append('idea')
    if any(word in content_lower for word in ['research', 'study', 'analysis', 'findings']):
        tags.append('research')
    if any(word in content_lower for word in ['code', 'programming', 'development', 'software']):
        tags.append('development')
    if any(word in content_lower for word in ['note', 'memo', 'reminder']):
        tags.append('notes')
    if any(word in content_lower for word in ['important', 'urgent', 'priority']):
        tags.append('important')
    
    # Default tags if none found
    if not tags:
        tags = ['general', 'personal']
    
    return tags[:5]  # Limit to 5 tags

@app.post("/api/generate-summary")
async def api_generate_summary(
    request_data: dict = Body(...),
    current_user: User = Depends(get_current_user)
):
    """Generate a summary for note content using AI"""
    content = request_data.get('content', '')
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    
    try:
        # Use existing Ollama summarization
        summary = ollama_summarize(content)
        
        if not summary or summary.strip() == "":
            # Fallback to simple summary
            summary = generate_simple_summary(content)
        
        return {"summary": summary}
    except Exception as e:
        # Fallback summary generation
        summary = generate_simple_summary(content)
        return {"summary": summary}

def generate_simple_summary(content):
    """Generate a simple extractive summary"""
    sentences = [s.strip() for s in re.split(r'[.!?]+', content) if s.strip() and len(s.strip()) > 20]
    
    if len(sentences) <= 3:
        return content[:200] + ('...' if len(content) > 200 else '')
    
    # Take first 2-3 sentences as summary
    summary_sentences = sentences[:3]
    summary = '. '.join(summary_sentences) + '.'
    
    # Ensure reasonable length
    if len(summary) > 300:
        summary = summary[:300] + '...'
    
    return summary

@app.post("/api/semantic-search")
async def api_semantic_search(
    request_data: dict = Body(...),
    current_user: User = Depends(get_current_user)
):
    """Perform semantic search using vector similarities"""
    query = request_data.get('query', '')
    limit = request_data.get('limit', 10)
    
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")
    
    try:
        # Try to use the advanced search service
        from services.search_adapter import get_search_service
        search_service = get_search_service()
        
        # Use vector search mode if available
        results = search_service.search(
            query=query,
            user_id=current_user.id,
            limit=limit,
            mode="vector"
        )
        
        return results.get("results", [])
    except Exception as e:
        # Fallback to regular text search
        conn = get_conn()
        c = conn.cursor()
        
        try:
            search_query = f"%{query}%"
            rows = c.execute("""
                SELECT id, title, content, summary, tags, type, timestamp, created_at, updated_at
                FROM notes 
                WHERE user_id = ? AND (
                    title LIKE ? OR 
                    content LIKE ? OR 
                    summary LIKE ? OR 
                    tags LIKE ?
                )
                ORDER BY COALESCE(timestamp, created_at, updated_at) DESC 
                LIMIT ?
            """, (current_user.id, search_query, search_query, search_query, search_query, limit)).fetchall()
            
            results = []
            for row in rows:
                note_dict = dict(zip([col[0] for col in c.description], row))
                created_at = note_dict.get('created_at') or note_dict.get('timestamp') or note_dict.get('updated_at')
                
                results.append({
                    "id": note_dict['id'],
                    "title": note_dict.get('title', 'Untitled'),
                    "content": note_dict.get('content', ''),
                    "summary": note_dict.get('summary', ''),
                    "tags": note_dict.get('tags', ''),
                    "created_at": created_at,
                    "type": note_dict.get('type', 'text')
                })
            
            return results
        except Exception as db_error:
            raise HTTPException(status_code=500, detail=f"Search failed: {str(db_error)}")
        finally:
            conn.close()

@app.post("/api/search/suggestions")
async def api_search_suggestions(
    request_data: dict = Body(...),
    current_user: User = Depends(get_current_user)
):
    """Get search suggestions based on user's notes and search history"""
    query = request_data.get('query', '').strip()
    limit = min(request_data.get('limit', 5), 10)  # Max 10 suggestions
    
    if not query or len(query) < 2:
        return {"suggestions": []}
    
    conn = get_conn()
    try:
        c = conn.cursor()
        suggestions = []
        
        # Get suggestions from note titles and tags
        search_query = f"%{query}%"
        rows = c.execute("""
            SELECT DISTINCT title, tags, type 
            FROM notes 
            WHERE user_id = ? AND (
                title LIKE ? OR 
                tags LIKE ?
            )
            ORDER BY COALESCE(timestamp, created_at) DESC 
            LIMIT ?
        """, (current_user.id, search_query, search_query, limit * 2)).fetchall()
        
        # Process title suggestions
        for title, tags, note_type in rows:
            if title and query.lower() in title.lower():
                suggestions.append({
                    "type": "title",
                    "text": title,
                    "context": note_type or "note"
                })
        
        # Process tag suggestions  
        for title, tags, note_type in rows:
            if tags:
                tag_list = [t.strip() for t in tags.split(',') if t.strip()]
                for tag in tag_list:
                    if query.lower() in tag.lower() and len(suggestions) < limit:
                        suggestions.append({
                            "type": "tag", 
                            "text": tag,
                            "context": "tag"
                        })
        
        # Remove duplicates and limit results
        seen = set()
        unique_suggestions = []
        for suggestion in suggestions:
            key = (suggestion['type'], suggestion['text'])
            if key not in seen and len(unique_suggestions) < limit:
                seen.add(key)
                unique_suggestions.append(suggestion)
        
        return {"suggestions": unique_suggestions}
        
    except Exception as e:
        print(f"Search suggestions error: {e}")
        return {"suggestions": []}
    finally:
        conn.close()

@app.get("/api/user/activity")
async def api_user_activity(
    days: int = Query(7, ge=1, le=365),
    current_user: User = Depends(get_current_user)
):
    """Get user activity statistics for analytics"""
    conn = get_conn()
    c = conn.cursor()
    
    try:
        # Get notes created in the last N days
        cutoff_date = datetime.now() - timedelta(days=days)
        rows = c.execute("""
            SELECT 
                DATE(COALESCE(created_at, timestamp)) as date,
                COUNT(*) as count,
                COUNT(CASE WHEN type = 'audio' THEN 1 END) as audio_notes,
                COUNT(CASE WHEN type = 'text' THEN 1 END) as text_notes,
                AVG(LENGTH(content)) as avg_length
            FROM notes 
            WHERE user_id = ? AND COALESCE(created_at, timestamp) >= ?
            GROUP BY DATE(COALESCE(created_at, timestamp))
            ORDER BY date DESC
        """, (current_user.id, cutoff_date.strftime("%Y-%m-%d"))).fetchall()
        
        activity_data = []
        for row in rows:
            activity_data.append({
                "date": row[0],
                "count": row[1],
                "audio_notes": row[2],
                "text_notes": row[3],
                "avg_length": round(row[4] or 0, 2)
            })
        
        # Get total statistics
        total_row = c.execute("""
            SELECT 
                COUNT(*) as total_notes,
                COUNT(CASE WHEN type = 'audio' THEN 1 END) as total_audio,
                COUNT(CASE WHEN type = 'text' THEN 1 END) as total_text,
                AVG(LENGTH(content)) as avg_content_length
            FROM notes 
            WHERE user_id = ?
        """, (current_user.id,)).fetchone()
        
        return {
            "activity": activity_data,
            "totals": {
                "total_notes": total_row[0],
                "total_audio": total_row[1],
                "total_text": total_row[2],
                "avg_content_length": round(total_row[3] or 0, 2)
            },
            "period_days": days
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get activity data: {str(e)}")
    finally:
        conn.close()

@app.get("/api/user/preferences")
async def api_get_user_preferences(current_user: User = Depends(get_current_user)):
    """Get user preferences for the frontend"""
    # For now, return default preferences - in the future this could be stored in DB
    return {
        "theme": "light",
        "notifications": True,
        "auto_save": True,
        "ai_suggestions": True,
        "advanced_search": True,
        "collaborative_editing": False,
        "analytics_tracking": True
    }

@app.post("/api/user/preferences")
async def api_update_user_preferences(
    preferences: dict = Body(...),
    current_user: User = Depends(get_current_user)
):
    """Update user preferences (stored in localStorage for now)"""
    # For now, just validate and return the preferences
    # In the future, these could be stored in the database
    allowed_preferences = {
        'theme', 'notifications', 'auto_save', 'ai_suggestions', 
        'advanced_search', 'collaborative_editing', 'analytics_tracking'
    }
    
    filtered_preferences = {k: v for k, v in preferences.items() if k in allowed_preferences}
    
    return {
        "status": "updated",
        "preferences": filtered_preferences,
        "message": "Preferences updated successfully"
    }

# Route to serve the new dashboard
@app.get("/dashboard/v2")
def dashboard_v2(request: Request):
    """Serve the new modern dashboard"""
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    
    return templates.TemplateResponse("dashboard_v2.html", {
        "request": request,
        "current_user": current_user
    })

@app.get("/dashboard/v3")
def dashboard_v3(request: Request):
    """Ultra-modern React-style dashboard with Obsidian/Discord/Notion/Spotify inspired design"""
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    
    return templates.TemplateResponse("dashboard_v3.html", {
        "request": request,
        "current_user": current_user
    })

@app.get("/dashboard/legacy")
def dashboard_legacy(request: Request):
    """Serve the original/legacy dashboard"""
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    
    return render_page(request, "dashboard.html", {
        "current_user": current_user,
        "notes": [],
        "search_query": "",
        "search_type": "fts"
    })

# Route to serve the analytics dashboard
@app.get("/analytics")
def analytics_dashboard(request: Request):
    """Serve the advanced analytics dashboard"""
    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)
    
    return templates.TemplateResponse("analytics_dashboard.html", {
        "request": request,
        "current_user": current_user
    })

# ============================================================================
# HTMX Dashboard Routes
# ============================================================================

@app.get("/dashboard/htmx")
def dashboard_htmx(request: Request):
    """Serve the HTMX-powered dashboard"""
    from services.htmx_helpers import is_htmx_request

    current_user = get_current_user_silent(request)
    if not current_user:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse("pages/dashboard_htmx.html", {
        "request": request,
        "current_user": current_user,
        "config": settings
    })


@app.get("/api/notes/fragment")
async def get_notes_fragment(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user)
):
    """Return HTML fragment of notes for HTMX infinite scroll"""
    from services.htmx_helpers import is_htmx_request

    conn = get_conn()
    c = conn.cursor()

    try:
        rows = c.execute(
            """
            SELECT
                id, title, body, content, summary, tags, type, status,
                timestamp, created_at, updated_at, audio_filename
            FROM notes
            WHERE user_id = ?
            ORDER BY COALESCE(timestamp, created_at, updated_at) DESC
            LIMIT ? OFFSET ?
            """,
            (current_user.id, limit, skip),
        ).fetchall()

        notes = []
        col_names = [col[0] for col in c.description]
        for row in rows:
            note = dict(zip(col_names, row))
            # Normalize tags
            tags_raw = note.get("tags") or ""
            if isinstance(tags_raw, str):
                tags_list = [t.strip() for t in tags_raw.replace("#", " ").replace(",", " ").split() if t.strip()]
            else:
                tags_list = tags_raw if isinstance(tags_raw, list) else []
            note["tags"] = tags_list

            # Add processing status
            note["processing_status"] = note.get("status", "completed")
            note["note_type"] = note.get("type", "text")

            notes.append(note)
    finally:
        conn.close()

    return templates.TemplateResponse("components/notes/note_list.html", {
        "request": request,
        "notes": notes,
        "skip": skip,
        "limit": limit
    })


@app.get("/api/stats/fragment")
async def get_stats_fragment(request: Request, current_user: User = Depends(get_current_user)):
    """Return HTML fragment of stats widget for HTMX auto-refresh"""
    from services.htmx_helpers import is_htmx_request

    conn = get_conn()
    c = conn.cursor()

    try:
        # Total notes
        total_notes = c.execute(
            "SELECT COUNT(*) FROM notes WHERE user_id = ?",
            (current_user.id,)
        ).fetchone()[0]

        # Notes today
        notes_today = c.execute(
            """
            SELECT COUNT(*) FROM notes
            WHERE user_id = ?
            AND DATE(COALESCE(timestamp, created_at)) = DATE('now')
            """,
            (current_user.id,)
        ).fetchone()[0]

        # Processing count
        processing = c.execute(
            "SELECT COUNT(*) FROM notes WHERE user_id = ? AND status = 'processing'",
            (current_user.id,)
        ).fetchone()[0]

        # Total unique tags
        tags_result = c.execute(
            "SELECT tags FROM notes WHERE user_id = ? AND tags IS NOT NULL",
            (current_user.id,)
        ).fetchall()

        all_tags = set()
        for (tags_str,) in tags_result:
            if tags_str:
                tag_list = [t.strip() for t in tags_str.replace("#", " ").replace(",", " ").split() if t.strip()]
                all_tags.update(tag_list)

        stats = {
            "total_notes": total_notes,
            "notes_today": notes_today,
            "processing": processing,
            "total_tags": len(all_tags)
        }
    finally:
        conn.close()

    return templates.TemplateResponse("components/ui/stats_widget.html", {
        "request": request,
        "stats": stats
    })


@app.get("/api/search/fragment")
async def search_fragment(
    request: Request,
    q: str = Query("", description="Search query"),
    type: Optional[str] = Query(None, description="Note type filter"),
    date_range: Optional[str] = Query(None, description="Date range filter"),
    sort: str = Query("relevance", description="Sort order"),
    current_user: User = Depends(get_current_user)
):
    """Return HTML fragment of search results for HTMX search-as-you-type"""
    from services.htmx_helpers import is_htmx_request
    from services.search_adapter import get_search_service

    results = []

    if q:  # Only search if there's a query
        try:
            search_service = get_search_service()
            search_results = search_service.search(
                query=q,
                user_id=current_user.id,
                limit=50
            )

            # Convert search results to note format
            for result in search_results:
                note = result.copy()
                # Normalize tags
                tags_raw = note.get("tags") or ""
                if isinstance(tags_raw, str):
                    tags_list = [t.strip() for t in tags_raw.replace("#", " ").replace(",", " ").split() if t.strip()]
                else:
                    tags_list = tags_raw if isinstance(tags_raw, list) else []
                note["tags"] = tags_list
                results.append(note)

            # Apply filters
            if type:
                results = [r for r in results if r.get("type") == type]

            # Apply date range filter
            if date_range:
                from datetime import datetime, timedelta
                now = datetime.now()
                if date_range == "today":
                    cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
                elif date_range == "week":
                    cutoff = now - timedelta(days=7)
                elif date_range == "month":
                    cutoff = now - timedelta(days=30)
                elif date_range == "year":
                    cutoff = now - timedelta(days=365)
                else:
                    cutoff = None

                if cutoff:
                    results = [
                        r for r in results
                        if datetime.fromisoformat(r.get("created_at", "1970-01-01")) >= cutoff
                    ]

            # Apply sorting
            if sort == "date_desc":
                results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
            elif sort == "date_asc":
                results.sort(key=lambda r: r.get("created_at", ""))
            elif sort == "title":
                results.sort(key=lambda r: r.get("title", "").lower())

        except Exception as e:
            print(f"Search error: {e}")
            results = []

    return templates.TemplateResponse("components/search/search_results.html", {
        "request": request,
        "results": results,
        "query": q
    })


@app.get("/debug/voice")
async def debug_voice_recording():
    """Debug page for testing voice recording functionality"""
    debug_html = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Voice Debug</title>
<style>body{font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;background:#1a1a1a;color:white}
.debug-section{background:#2a2a2a;padding:15px;margin:10px 0;border-radius:8px}
.error{color:#ff6b6b}.success{color:#51cf66}.info{color:#74c0fc}
button{background:#e03131;color:white;border:none;padding:10px 20px;border-radius:5px;cursor:pointer;margin:5px}
button:hover{background:#c92a2a}#console-output{background:#000;border:1px solid #333;padding:10px;height:300px;overflow-y:auto;font-family:monospace;font-size:12px}</style></head>
<body><h1>🎤 Voice Recording Debug</h1>
<div class="debug-section"><h3>System Capabilities</h3><div id="capabilities"></div></div>
<div class="debug-section"><h3>Recording Test</h3>
<button onclick="testRecording()">Test Recording (3 sec)</button>
<button onclick="requestPermission()">Request Permission</button>
<div id="status"></div></div>
<div class="debug-section"><h3>Console Output</h3>
<div id="console-output"></div><button onclick="clearConsole()">Clear</button></div>
<script>
const originalLog = console.log, originalError = console.error;
function addToConsole(message, type = 'log') {
    const output = document.getElementById('console-output');
    const timestamp = new Date().toLocaleTimeString();
    const color = type === 'error' ? '#ff6b6b' : '#51cf66';
    output.innerHTML += '<div style="color: '+color+'">['+timestamp+'] '+message+'</div>';
    output.scrollTop = output.scrollHeight;
}
console.log = function(...args) { addToConsole(args.join(' '), 'log'); originalLog.apply(console, args); };
console.error = function(...args) { addToConsole(args.join(' '), 'error'); originalError.apply(console, args); };
function clearConsole() { document.getElementById('console-output').innerHTML = ''; }

function checkCapabilities() {
    const caps = document.getElementById('capabilities');
    let html = '';
    html += '<div class="'+(navigator.mediaDevices ? 'success' : 'error')+'">MediaDevices: '+(navigator.mediaDevices ? '✓' : '✗')+'</div>';
    html += '<div class="'+(navigator.mediaDevices?.getUserMedia ? 'success' : 'error')+'">getUserMedia: '+(navigator.mediaDevices?.getUserMedia ? '✓' : '✗')+'</div>';
    html += '<div class="'+(typeof MediaRecorder !== 'undefined' ? 'success' : 'error')+'">MediaRecorder: '+(typeof MediaRecorder !== 'undefined' ? '✓' : '✗')+'</div>';
    html += '<div class="'+(window.isSecureContext ? 'success' : 'error')+'">Secure Context: '+(window.isSecureContext ? '✓' : '✗')+'</div>';
    if (typeof MediaRecorder !== 'undefined') {
        const formats = ['audio/webm', 'audio/webm;codecs=opus'];
        formats.forEach(format => {
            const supported = MediaRecorder.isTypeSupported(format);
            html += '<div class="'+(supported ? 'success' : 'error')+'">'+format+': '+(supported ? '✓' : '✗')+'</div>';
        });
    }
    caps.innerHTML = html;
}

let mediaRecorder = null, audioChunks = [];

async function requestPermission() {
    console.log('🎤 Requesting microphone permission...');
    document.getElementById('status').innerHTML = '<div class="info">Requesting permission...</div>';
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log('🎤 Permission granted');
        document.getElementById('status').innerHTML = '<div class="success">Permission granted ✓</div>';
        stream.getTracks().forEach(track => track.stop());
        return true;
    } catch (error) {
        console.error('🎤 Permission error:', error);
        document.getElementById('status').innerHTML = '<div class="error">Permission denied: '+error.message+'</div>';
        return false;
    }
}

async function testRecording() {
    console.log('🎤 Starting recording test...');
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log('🎤 Got microphone stream');
        
        let mimeType = 'audio/webm';
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
            mimeType = 'audio/webm;codecs=opus';
        }
        console.log('🎤 Using:', mimeType);
        
        mediaRecorder = new MediaRecorder(stream, { mimeType });
        console.log('🎤 MediaRecorder created');
        
        audioChunks = [];
        mediaRecorder.ondataavailable = (event) => {
            console.log('🎤 Data available:', event.data.size, 'bytes');
            audioChunks.push(event.data);
        };
        
        mediaRecorder.onstop = () => {
            console.log('🎤 Recording stopped');
            const audioBlob = new Blob(audioChunks, { type: mimeType });
            console.log('🎤 Created blob:', audioBlob.size, 'bytes');
            
            const url = URL.createObjectURL(audioBlob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'test-recording.webm';
            a.textContent = '⬇️ Download Recording';
            a.style.display = 'block';
            document.getElementById('status').appendChild(a);
            
            stream.getTracks().forEach(track => track.stop());
        };
        
        mediaRecorder.start();
        console.log('🎤 Recording started');
        document.getElementById('status').innerHTML = '<div class="success">🔴 Recording... (3 seconds)</div>';
        
        setTimeout(() => {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
                console.log('🎤 Auto-stopped');
            }
        }, 3000);
        
    } catch (error) {
        console.error('🎤 Test failed:', error);
        document.getElementById('status').innerHTML = '<div class="error">Test failed: '+error.message+'</div>';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('🎤 Debug tool loaded');
    checkCapabilities();
});
</script></body></html>"""
    return Response(content=debug_html, media_type="text/html")
