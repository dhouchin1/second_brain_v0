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
from llm_utils import ollama_summarize, ollama_generate_title
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

def highlight(text, term):
    if not text or not term:
        return text
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    return Markup(pattern.sub(lambda m: f"<mark>{escape(m.group(0))}</mark>", text))
templates.env.filters['highlight'] = highlight

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
            timestamp TEXT,
            audio_filename TEXT,
            content TEXT
        )
    ''')
    c.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            title, summary, tags, content, content='notes', content_rowid='id'
        )
    ''')
    conn.commit()
    conn.close()
init_db()  # Ensure tables are ready

def transcribe_audio(audio_path):
    import time
    wav_path = audio_path.with_suffix('.converted.wav')
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", str(audio_path),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)
    ]
    result = subprocess.run(ffmpeg_cmd, capture_output=True)
    if result.returncode != 0:
        print("ffmpeg failed to convert audio:", result.stderr)
        return "", None
    print(f"Converted audio: {wav_path} (size: {os.path.getsize(wav_path)} bytes)")
    out_txt_path = wav_path.with_suffix(wav_path.suffix + '.txt')
    whisper_cmd = [
        str(WHISPER_CPP_PATH),
        "-m", str(WHISPER_MODEL_PATH),
        "-f", str(wav_path),
        "-otxt"
    ]
    result = subprocess.run(whisper_cmd, capture_output=True, text=True)
    print(f"Looking for transcript at: {out_txt_path}")

    # Wait for up to 2 seconds for the file to be written
    for _ in range(20):
        if out_txt_path.exists() and out_txt_path.stat().st_size > 0:
            break
        time.sleep(0.1)
    if out_txt_path.exists() and out_txt_path.stat().st_size > 0:
        content = out_txt_path.read_text().strip()
        print(f"Transcript content: '{content}'")
        return content, wav_path.name
    else:
        print("Whisper.cpp failed or output file missing/empty")
        return "", wav_path.name

    
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

@app.get("/audio/{filename}")
def get_audio(filename: str):
    audio_path = AUDIO_DIR / filename
    if audio_path.exists():
        return FileResponse(str(audio_path))
    return {"error": "Audio not found"}

@app.post("/capture")
async def capture(
    request: Request,
    note: str = Form(""),
    tags: str = Form(""),
    file: UploadFile = File(None)
):
    content = note.strip()
    note_type = "note"
    summary = ""
    title = ""
    audio_filename = None

    if file:
        AUDIO_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        safe_name = f"{timestamp}-{file.filename.replace(' ', '_')}"
        audio_path = AUDIO_DIR / safe_name
        with open(audio_path, "wb") as out_f:
            out_f.write(await file.read())
        transcript, converted_name = transcribe_audio(audio_path)
        audio_filename = converted_name
        if transcript:
            content = transcript
            print(f"[capture] Transcript to summarize: {repr(content[:200])}")
            # AI TITLE!
            title = ollama_generate_title(transcript)
            if not title or title.lower().startswith("untitled"):
                # fallback: first line, 60 chars max
                title = transcript.splitlines()[0][:60] if transcript.strip() else "[Audio Note]"
            summary = ollama_summarize(transcript)
        else:
            title = f"[Transcription failed for {safe_name}]"
            content = ""
            summary = title
        note_type = "audio"
    else:
        print(f"[capture] Note content to summarize: {repr(content[:200])}")
        # AI TITLE!
        title = ollama_generate_title(content) if content else "[No Title]"
        if not title or title.lower().startswith("untitled"):
            title = content[:60] if content else "[No Title]"
        summary = ollama_summarize(content)
        audio_filename = None

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"About to insert note. Title: '{title}', summary: '{summary}', audio_filename: '{audio_filename}'")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notes (title, content, summary, tags, type, timestamp, audio_filename) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, content, summary, tags, note_type, now, audio_filename)
    )
    conn.commit()
    note_id = c.lastrowid
    c.execute(
        "INSERT INTO notes_fts(rowid, title, summary, tags, content) VALUES (?, ?, ?, ?, ?)",
        (note_id, title, summary, tags, content)
    )
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=302)

@app.post("/webhook/apple")
async def webhook_apple(data: dict = Body(...)):
    print("APPLE WEBHOOK RECEIVED:", data)
    note = data.get("note", "")
    tags = data.get("tags", "")
    note_type = data.get("type", "apple")
    summary = ollama_summarize(note)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notes (title, content, summary, tags, type, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (note[:60] + "..." if len(note) > 60 else note, note, summary, tags, note_type, now)
    )
    conn.commit()
    note_id = c.lastrowid
    c.execute(
        "INSERT INTO notes_fts(rowid, title, summary, tags, content) VALUES (?, ?, ?, ?, ?)",
        (note_id, note[:60] + "..." if len(note) > 60 else note, summary, tags, note)
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
