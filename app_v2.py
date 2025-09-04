from fastapi import FastAPI, Request, Form, UploadFile, File, Body
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import sqlite3, pathlib, datetime, subprocess
from llm_utils import ollama_summarize

app = FastAPI()
BASE_DIR = pathlib.Path(__file__).parent.resolve()
DB_PATH = BASE_DIR / "notes.db"
AUDIO_DIR = BASE_DIR / "audio"
WHISPER_CPP_PATH = BASE_DIR / "whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL_PATH = BASE_DIR / "whisper.cpp/models/ggml-base.en.bin"
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

def get_conn():
    return sqlite3.connect(str(DB_PATH))

def transcribe_audio(audio_path):
    wav_path = audio_path.with_suffix('.wav')
    if not audio_path.suffix.lower() == ".wav":
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

def find_related_notes(note_id, tags, conn):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    if not tag_list:
        return []
    q = " OR ".join(["tags LIKE ?"] * len(tag_list))
    params = [f"%{tag}%" for tag in tag_list]
    sql = f"SELECT id, title FROM notes WHERE id != ? AND ({q}) LIMIT 3"
    params = [note_id] + params
    rows = conn.execute(sql, params).fetchall()
    return [{"id": row[0], "title": row[1]} for row in rows]

@app.get("/")
def dashboard(request: Request, q: str = "", type: str = "", tag: str = "", calendar: str = ""):
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
    else:
        sql = "SELECT * FROM notes WHERE 1=1"
        params = []
        if type:
            sql += " AND type = ?"
            params.append(type)
        if tag:
            sql += " AND tags LIKE ?"
            params.append(f"%{tag}%")
        if calendar:
            sql += " AND timestamp LIKE ?"
            params.append(f"{calendar}%")
        sql += " ORDER BY timestamp DESC LIMIT 100"
        rows = c.execute(sql, params).fetchall()
    notes = [dict(zip([col[0] for col in c.description], row)) for row in rows]
    today = datetime.datetime.now().date().isoformat()
    week_ago = (datetime.datetime.now().date() - datetime.timedelta(days=7)).isoformat()
    from collections import defaultdict
    grouped = defaultdict(list)
    for note in notes:
        note_date = note["timestamp"][:10] if note.get("timestamp") else ""
        if note_date == today:
            grouped["today"].append(note)
        elif note_date > week_ago:
            grouped["week"].append(note)
        else:
            grouped["earlier"].append(note)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "today_notes": grouped["today"],
            "week_notes": grouped["week"],
            "older_notes": grouped["earlier"],
            "notes": notes,
            "today": today,
            "week_ago": week_ago,
            "q": q,
            "type": type,
            "tag": tag,
            "calendar": calendar,
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
    related = find_related_notes(note_id, note["tags"], conn)
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
async def capture(request: Request, note: str = Form(""), tags: str = Form(""), file: UploadFile = File(None)):
    note_type = "note"
    text = note.strip()
    transcript = ""
    audio_filename = None
    if file:
        AUDIO_DIR.mkdir(exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
        safe_name = f"{timestamp}-{file.filename.replace(' ', '_')}"
        audio_path = AUDIO_DIR / safe_name
        with open(audio_path, "wb") as out_f:
            out_f.write(await file.read())
        transcript = transcribe_audio(audio_path)
        text = transcript or f"[Transcription failed for {safe_name}]"
        note_type = "audio"
        audio_filename = safe_name
    result = ollama_summarize(text)
    summary = result.get("summary", "")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notes (title, summary, tags, type, timestamp) VALUES (?, ?, ?, ?, ?)",
        (text[:60] + "..." if len(text) > 60 else text, summary, tags, note_type, now)
    )
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=302)

@app.post("/webhook/apple")
async def webhook_apple(data: dict = Body(...)):
    note = data.get("note", "")
    tags = data.get("tags", "")
    note_type = data.get("type", "apple")
    result = ollama_summarize(note)
    summary = result.get("summary", "")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notes (title, summary, tags, type, timestamp) VALUES (?, ?, ?, ?, ?)",
        (note[:60] + "..." if len(note) > 60 else note, summary, tags, note_type, now)
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}
