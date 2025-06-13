from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import Optional
from pathlib import Path
import shutil
import uuid
import os
import sqlite3

# --- Config ---
VAULT_PATH = Path(os.getenv("VAULT_PATH", "/Users/dhouchin/Obsidian/SecondBrain"))
AUDIO_PATH = VAULT_PATH / "audio"
AUDIO_PATH.mkdir(parents=True, exist_ok=True)
DB_PATH = VAULT_PATH / "secondbrain_index.db"

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Endpoints ---
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/capture")
async def capture(
    note: Optional[str] = Form(None),
    tags: Optional[str] = Form(""),
    project: Optional[str] = Form(""),
    file: Optional[UploadFile] = File(None),
):
    note_id = str(uuid.uuid4())
    if file:
        # Save uploaded audio
        filename = f"{note_id}_{file.filename}"
        audio_file = AUDIO_PATH / filename
        with open(audio_file, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        # (Optional: Trigger background processing here)
        response = {"status": "ok", "note_id": note_id, "audio_file": str(audio_file)}
    else:
        # Save text note
        note_file = VAULT_PATH / f"{note_id}.md"
        yaml_header = f"---\ntags: [{tags}]\nproject: {project}\n---\n"
        with open(note_file, "w") as f:
            f.write(yaml_header + (note or ""))
        response = {"status": "ok", "note_id": note_id, "file": str(note_file)}
    return JSONResponse(content=response)

@app.get("/timeline")
def timeline():
    # List latest notes/audio
    events = []
    # Find latest .md notes and audio files
    for md in sorted(VAULT_PATH.glob("*.md"), reverse=True):
        events.append({
            "id": md.stem,
            "type": "note",
            "path": str(md),
        })
    for audio in sorted(AUDIO_PATH.glob("*.m4a"), reverse=True):
        events.append({
            "id": audio.stem,
            "type": "audio",
            "path": str(audio),
        })
    return {"timeline": events[:50]}  # Most recent 50

@app.get("/detail/{note_id}")
def detail_view(request: Request, note_id: str):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    row = c.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        return templates.TemplateResponse("dashboard.html", {"request": request, "notes": [], "q": ""})
    note = dict(zip([col[0] for col in c.description], row))
    # Attach audio if available
    audio_files = list(AUDIO_PATH.glob(f"{note_id}_*.m4a"))
    note["audio_files"] = [str(a) for a in audio_files]
    # Add content if it's a text note
    md_file = VAULT_PATH / f"{note_id}.md"
    if md_file.exists():
        with open(md_file, "r") as f:
            note["content"] = f.read()
    else:
        note["content"] = ""
    return templates.TemplateResponse("detail.html", {"request": request, "note": note})

@app.get("/")
def dashboard(request: Request, q: str = "", type: str = "", tag: str = ""):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    sql = "SELECT * FROM notes WHERE 1=1"
    params = []
    if q:
        sql += " AND (title LIKE ? OR summary LIKE ? OR tags LIKE ?)"
        params += [f"%{q}%"]*3
    if type:
        sql += " AND type = ?"
        params.append(type)
    if tag:
        sql += " AND tags LIKE ?"
        params.append(f"%{tag}%")
    sql += " ORDER BY timestamp DESC LIMIT 50"
    rows = c.execute(sql, params)
    notes = [
        dict(zip([col[0] for col in c.description], row))
        for row in rows
    ]
    return templates.TemplateResponse("dashboard.html", {"request": request, "notes": notes, "q": q})

# --- Run with Uvicorn ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8082, reload=True)
