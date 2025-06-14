import pathlib
import sqlite3
from datetime import datetime
from fastapi import FastAPI, Request, Form, UploadFile, File, Body, Query
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from collections import defaultdict
import subprocess
import os
from llm_utils import ollama_summarize
from markupsafe import Markup, escape
import re

# ---- Config ----
BASE_DIR = pathlib.Path(__file__).parent.resolve()
DB_PATH = BASE_DIR / "notes.db"
AUDIO_DIR = BASE_DIR / "audio"
WHISPER_CPP_PATH = BASE_DIR / "whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL_PATH = BASE_DIR / "whisper.cpp/models/ggml-base.en.bin"

# ---- FastAPI Setup ----
app = FastAPI()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ---- Highlight Filter for Search ----
def highlight(text, term):
    if not text or not term:
        return text
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    return Markup(pattern.sub(lambda m: f"<mark>{escape(m.group(0))}</mark>", text))
templates.env.filters['highlight'] = highlight

# ---- Database Initialization ----
def get_conn():
    return sqlite3.connect(str(DB_PATH))

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            summary TEXT,
            tags TEXT,
            type TEXT,
            timestamp TEXT
        )
    ''')
    c.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            title, summary, tags, content='notes', content_rowid='id'
        )
    ''')
    conn.commit()
    conn.close()
init_db()  # Ensure tables are ready

# ---- Audio Transcription ----
def transcribe_audio(audio_path):
    wav_path = audio_path.with_suffix('.wav')
    # Convert to .wav if needed
    if audio_path.suffix.lower() != ".wav":
        subprocess.run([
            "ffmpeg", "-y", "-i", str(audio_path), str(wav_path)
        ], capture_output=True)
    else:
        wav_path = audio_path
    out_txt_path = wav_path.with_suffix('.txt')
    whisper_cmd = [
        str(WHISPER_CPP_PATH),
        "-m", str(WHISPER_MODEL_PATH),
        "-f", str(wav_path),
        "-otxt"
    ]
    result = subprocess.run(whisper_cmd, capture_output=True, text=True)
    if result.returncode == 0 and out_txt_path.exists():
        return out_txt_path.read_text().strip()
    else:
        print("Whisper.cpp failed:", result.stderr)
        return ""

# ---- Find Related Notes ----
def find_related_notes(note_id, tags, conn):
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    if not tag_list:
        return []
    q = " OR ".join(["tags LIKE ?"] * len(tag_list))
    params = [f"%{tag}%" for tag in tag_list]
    sql = f"SELECT id, title FROM notes WHERE id != ? AND ({q}) LIMIT 3"
    params = [note_id] + params
    rows = conn.execute(sql, params).fetchall()
    return [{"id": row[0], "title": row[1]} for row in rows]

# ---- Timeline Dashboard ----
@app.get("/")
def dashboard(request: Request, q: str = "", tag: str = ""):
    conn = get_conn()
    c = conn.cursor()
    if q:
        rows = c.execute("""
            SELECT n.*
            FROM notes_fts fts
            JOIN notes n ON n.id = fts.rowid
            WHERE notes_fts MATCH ?
            ORDER BY n.timestamp DESC LIMIT 100
        """, (q,)).fetchall()
    elif tag:
        rows = c.execute("SELECT * FROM notes WHERE tags LIKE ? ORDER BY timestamp DESC", (f"%{tag}%",)).fetchall()
    else:
        rows = c.execute("SELECT * FROM notes ORDER BY timestamp DESC LIMIT 100").fetchall()
    notes = [dict(zip([col[0] for col in c.description], row)) for row in rows]
    # Group notes by day
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
        },
    )

# ---- Detail View ----
@app.get("/detail/{note_id}")
def detail(request: Request, note_id: int):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        return RedirectResponse("/", status_code=302)
    note = dict(zip([col[0] for col in c.description], row))
    related = find_related_notes(note_id, note.get("tags", ""), conn)
    return templates.TemplateResponse(
        "detail.html",
        {"request": request, "note": note, "related": related}
    )

# ---- Audio Serving ----
@app.get("/audio/{filename}")
def get_audio(filename: str):
    audio_path = AUDIO_DIR / filename
    if audio_path.exists():
        return FileResponse(str(audio_path))
    return {"error": "Audio not found"}

# ---- Note & Audio Capture ----
@app.post("/capture")
async def capture(
    request: Request,
    note: str = Form(""),
    tags: str = Form(""),
    file: UploadFile = File(None)
):
    text = note.strip()
    note_type = "note"
    transcript = ""
    audio_filename = None
    if file:
        AUDIO_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        safe_name = f"{timestamp}-{file.filename.replace(' ', '_')}"
        audio_path = AUDIO_DIR / safe_name
        with open(audio_path, "wb") as out_f:
            out_f.write(await file.read())
        transcript = transcribe_audio(audio_path)
        text = transcript or f"[Transcription failed for {safe_name}]"
        note_type = "audio"
        audio_filename = safe_name
    summary = ollama_summarize(text)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notes (title, summary, tags, type, timestamp) VALUES (?, ?, ?, ?, ?)",
        (text[:60] + "..." if len(text) > 60 else text, summary, tags, note_type, now)
    )
    conn.commit()
    # Optionally, keep FTS index up to date
    note_id = c.lastrowid
    c.execute(
        "INSERT INTO notes_fts(rowid, title, summary, tags) VALUES (?, ?, ?, ?)",
        (note_id, text[:60] + "..." if len(text) > 60 else text, summary, tags)
    )
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=302)

# ---- Apple Shortcuts/Webhook ----
@app.post("/webhook/apple")
async def webhook_apple(data: dict = Body(...)):
    note = data.get("note", "")
    tags = data.get("tags", "")
    note_type = data.get("type", "apple")
    summary = ollama_summarize(note)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notes (title, summary, tags, type, timestamp) VALUES (?, ?, ?, ?, ?)",
        (note[:60] + "..." if len(note) > 60 else note, summary, tags, note_type, now)
    )
    conn.commit()
    note_id = c.lastrowid
    c.execute(
        "INSERT INTO notes_fts(rowid, title, summary, tags) VALUES (?, ?, ?, ?)",
        (note_id, note[:60] + "..." if len(note) > 60 else note, summary, tags)
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}

# ---- Activity Timeline ----
@app.get("/activity")
def activity_timeline(
    request: Request,
    activity_type: str = Query("all", alias="type"),
    start: str = "",
    end: str = "",
):
    conn = get_conn()
    c = conn.cursor()

    base_query = "SELECT id, summary, type, timestamp FROM notes"
    conditions = []
    params: list[str] = []
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
        base_query += " WHERE " + " AND ".join(conditions)
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

# ---- Health Check ----
@app.get("/health")
def health():
    conn = get_conn()
    c = conn.cursor()
    tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    return {"tables": [t[0] for t in tables]}
