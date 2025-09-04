# Legacy search_engine removed from app imports; unified service is used instead
from schemas.discord import DiscordWebhook
from services.auth_service import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
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
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm, HTTPBearer, HTTPAuthorizationCredentials
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
try:
    if REALTIME_AVAILABLE:
        create_status_endpoint(app)
except Exception:
    # Non-fatal if realtime endpoints cannot be registered
    pass

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

# --- Include Smart Templates Router ---
from services.smart_templates_router import router as templates_router, init_smart_templates_router
init_smart_templates_router(get_conn, get_current_user)
app.include_router(templates_router)

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

# --- Include Vault Seeding Router ---
from services.vault_seeding_router import router as seeding_router, init_vault_seeding_router
init_vault_seeding_router(get_conn, get_current_user)
app.include_router(seeding_router)

# --- Include Search Benchmarking Router ---
from services.search_benchmarking_router import router as benchmarking_router, init_search_benchmarking_router
init_search_benchmarking_router(get_conn)
app.include_router(benchmarking_router)

# Initialize Interactive Seeding router
from services.interactive_seeding_router import router as interactive_seeding_router, init_interactive_seeding_router
init_interactive_seeding_router(get_conn)
app.include_router(interactive_seeding_router)

# --- Auto-seeding and Initialization ---
from services.initialization_service import get_initialization_service

async def _perform_auto_seeding_initialization():
    """Perform auto-seeding for fresh installations (non-blocking background task)."""
    try:
        init_service = get_initialization_service(get_conn)
        
        if init_service.is_fresh_installation():
            print("[STARTUP] Fresh installation detected, performing auto-seeding...")
            result = init_service.perform_first_run_setup()
            
            if result["success"]:
                print(f"[STARTUP] Auto-seeding completed: {result.get('message', 'Success')}")
            else:
                print(f"[STARTUP] Auto-seeding failed: {result.get('error', 'Unknown error')}")
        else:
            print("[STARTUP] Existing installation detected, skipping auto-seeding")
            
    except Exception as e:
        print(f"[STARTUP] Auto-seeding initialization failed: {e}")

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

@app.on_event("startup")
async def _perform_auto_seeding_initialization():
    """Perform auto-seeding initialization for fresh installations."""
    if getattr(app.state, "auto_seeding_initialized", False):
        return
    app.state.auto_seeding_initialized = True
    
    try:
        from services.initialization_service import get_initialization_service
        
        # Run initialization in background to avoid blocking startup
        async def perform_initialization():
            try:
                init_service = get_initialization_service(get_conn)
                
                # Check if this is a fresh installation
                if init_service.is_fresh_installation():
                    print("🌱 Fresh installation detected, performing first-run setup...")
                    result = init_service.perform_first_run_setup()
                    
                    if result["success"]:
                        print(f"✅ First-run setup completed: {result['message']}")
                        if "auto_seeding_result" in result:
                            seeding_result = result["auto_seeding_result"]
                            if seeding_result.get("success"):
                                print(f"🌱 Auto-seeding successful: {seeding_result.get('message', 'Content seeded')}")
                            else:
                                print(f"⚠️  Auto-seeding skipped: {seeding_result.get('reason', 'Unknown reason')}")
                    else:
                        print(f"❌ First-run setup failed: {result.get('error', 'Unknown error')}")
                else:
                    print("ℹ️  Existing installation detected, skipping auto-seeding initialization")
                    
            except Exception as e:
                print(f"❌ Auto-seeding initialization failed: {e}")
        
        # Create background task for initialization
        asyncio.create_task(perform_initialization())
        
    except ImportError as e:
        print(f"⚠️  Auto-seeding initialization not available: {e}")

# Add real-time status endpoints if available
if REALTIME_AVAILABLE:
    create_status_endpoint(app)

async def process_audio_queue():
    """Background task to process audio queue in FIFO order"""
    next_item = audio_queue.get_next_for_processing()
    if next_item:
        note_id, user_id = next_item
        try:
            if REALTIME_AVAILABLE:
                from tasks_enhanced import process_note_with_status
                await process_note_with_status(note_id)
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

@app.get("/vault/seeding")
async def vault_seeding_page(request: Request):
    """Vault seeding interface for adding starter content"""
    user = get_current_user_silent(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return render_page(request, "vault_seeding.html", {"user": user})

@app.get("/interactive-seeding")
async def interactive_seeding_page(request: Request):
    """Interactive seeding interface for guided content collection"""
    user = get_current_user_silent(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return render_page(request, "interactive_seeding.html", {"user": user})

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
from pathlib import Path

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
        SELECT n.id, n.title, n.status, n.timestamp, n.audio_filename,
               CASE 
                 WHEN n.status LIKE '%:%' THEN CAST(SUBSTR(n.status, INSTR(n.status, ':') + 1) AS INTEGER)
                 ELSE 0
               END as progress_percent
        FROM notes n
        WHERE n.user_id = ? AND n.type = 'audio' 
        ORDER BY n.timestamp DESC
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
        "SELECT timestamp FROM notes WHERE user_id=? AND type='audio' AND status='complete' ORDER BY timestamp DESC LIMIT 1",
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
        total_pending = audio_queue.conn.execute("SELECT COUNT(*) FROM audio_processing_queue WHERE status = 'pending'").fetchone()[0]
        total_processing = audio_queue.conn.execute("SELECT COUNT(*) FROM audio_processing_queue WHERE status = 'processing'").fetchone()[0]
        
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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tags: str = Form(""),
    user_id: int = Form(2)  # Default user ID for webhook (adjust as needed)
):
    """
    Fast audio webhook endpoint for Apple Shortcuts and external integrations.
    Quickly saves audio and queues for background processing without blocking.
    """
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
    """Apple Shortcuts webhook handler"""
    return webhook_service.process_apple_webhook(data, current_user.id)

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

# --- Auto-seeding Admin Endpoints ---

@app.get("/api/admin/auto-seeding/status")
async def get_auto_seeding_status(current_user: User = Depends(get_current_user)):
    """Get auto-seeding system status and configuration."""
    try:
        from services.auto_seeding_service import get_auto_seeding_service
        from services.initialization_service import get_initialization_service
        
        auto_seeding_service = get_auto_seeding_service(get_conn)
        init_service = get_initialization_service(get_conn)
        
        # Get overall system status
        auto_seeding_status = auto_seeding_service.check_auto_seeding_status()
        initialization_status = init_service.get_initialization_status()
        
        # Get user-specific auto-seeding history
        user_history = auto_seeding_service.get_auto_seeding_history(current_user.id)
        
        # Check if current user should be auto-seeded
        user_seed_check = auto_seeding_service.should_auto_seed(current_user.id)
        
        return {
            "system_status": auto_seeding_status,
            "initialization_status": initialization_status,
            "user_history": user_history,
            "user_seed_check": user_seed_check,
            "user_id": current_user.id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get auto-seeding status: {str(e)}")

@app.post("/api/admin/auto-seeding/trigger")
async def trigger_auto_seeding(
    background_tasks: BackgroundTasks,
    user_id: int = Query(None, description="User ID to seed (defaults to current user)"),
    force: bool = Query(False, description="Force seeding even if conditions aren't met"),
    current_user: User = Depends(get_current_user)
):
    """Manually trigger auto-seeding for a user."""
    try:
        from services.auto_seeding_service import get_auto_seeding_service
        
        # Use current user if no user_id specified
        target_user_id = user_id if user_id is not None else current_user.id
        
        auto_seeding_service = get_auto_seeding_service(get_conn)
        
        # Perform auto-seeding in background
        def perform_seeding():
            try:
                result = auto_seeding_service.perform_auto_seeding(target_user_id, force=force)
                print(f"🌱 Manual auto-seeding triggered for user {target_user_id}: {result}")
                return result
            except Exception as e:
                print(f"❌ Manual auto-seeding failed for user {target_user_id}: {e}")
                raise
        
        background_tasks.add_task(perform_seeding)
        
        return {
            "success": True,
            "message": f"Auto-seeding triggered for user {target_user_id}",
            "target_user_id": target_user_id,
            "force": force
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger auto-seeding: {str(e)}")

@app.get("/api/admin/auto-seeding/failed-onboardings")
async def get_failed_onboardings(
    limit: int = Query(50, description="Maximum number of failed onboardings to return"),
    current_user: User = Depends(get_current_user)
):
    """Get list of users that had failed onboarding attempts."""
    try:
        from services.initialization_service import get_initialization_service
        
        init_service = get_initialization_service(get_conn)
        failed_onboardings = init_service.get_failed_onboardings(limit)
        
        return {
            "failed_onboardings": failed_onboardings,
            "count": len(failed_onboardings),
            "limit": limit
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get failed onboardings: {str(e)}")

@app.post("/api/admin/auto-seeding/retry-failed")
async def retry_failed_onboardings(
    background_tasks: BackgroundTasks,
    user_id: int = Query(None, description="Specific user ID to retry (optional)"),
    current_user: User = Depends(get_current_user)
):
    """Retry failed onboarding attempts."""
    try:
        from services.initialization_service import get_initialization_service
        from services.auth_service import _perform_user_auto_seeding
        
        init_service = get_initialization_service(get_conn)
        
        if user_id:
            # Retry specific user
            background_tasks.add_task(_perform_user_auto_seeding, user_id, 0)
            return {
                "success": True,
                "message": f"Retry scheduled for user {user_id}",
                "retried_users": [user_id]
            }
        else:
            # Retry all failed onboardings
            failed_onboardings = init_service.get_failed_onboardings(50)
            retried_users = []
            
            for onboarding in failed_onboardings:
                user_id = onboarding["user_id"]
                background_tasks.add_task(_perform_user_auto_seeding, user_id, 0)
                retried_users.append(user_id)
            
            return {
                "success": True,
                "message": f"Retry scheduled for {len(retried_users)} users",
                "retried_users": retried_users
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retry failed onboardings: {str(e)}")

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
            SELECT id, title, content, created_at, type, tags
            FROM notes 
            WHERE user_id = ?
            ORDER BY created_at DESC 
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

def verify_webhook_token_local(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme)):
    # Delegate to auth service imported function
    from services.auth_service import verify_webhook_token
    return verify_webhook_token(credentials)
