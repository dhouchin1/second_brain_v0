import sqlite3
import time
from datetime import datetime
from typing import Optional

from llm_utils import ollama_summarize, ollama_generate_title
from config import settings
from audio_utils import transcribe_audio


def get_conn():
    return sqlite3.connect(str(settings.db_path))


def process_note(note_id: int):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        conn.close()
        return
    cols = [d[0] for d in c.description]
    note = dict(zip(cols, row))
    content = note.get("content") or ""
    tags = note.get("tags", "")
    actions = note.get("actions", "")
    note_type = note.get("type", "note")
    audio_filename: Optional[str] = note.get("audio_filename")

    if note_type == "audio" and audio_filename:
        audio_path = settings.audio_dir / audio_filename
        transcript, converted_name = transcribe_audio(audio_path)
        if transcript:
            content = transcript
            audio_filename = converted_name
        else:
            content = ""

    title = ollama_generate_title(content) if content else "[No Title]"
    if not title or title.lower().startswith("untitled"):
        title = content.splitlines()[0][:60] if content else "[No Title]"
    result = ollama_summarize(content) if content else {"summary": "", "tags": [], "actions": []}
    summary = result.get("summary", "")
    ai_tags = result.get("tags", [])
    ai_actions = result.get("actions", [])
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    tag_list.extend([t for t in ai_tags if t and t not in tag_list])
    tags = ",".join(tag_list)
    actions = "\n".join(ai_actions)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute(
        "UPDATE notes SET title=?, content=?, summary=?, tags=?, actions=?, status='complete', timestamp=?, audio_filename=? WHERE id=?",
        (title, content, summary, tags, actions, now, audio_filename, note_id),
    )
    c.execute(
        "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
        (note_id, title, summary, tags, actions, content),
    )
    conn.commit()
    conn.close()


def run_worker(poll_interval: int = 5):
    while True:
        conn = get_conn()
        c = conn.cursor()
        row = c.execute("SELECT id FROM notes WHERE status='pending' ORDER BY id LIMIT 1").fetchone()
        conn.close()
        if row:
            process_note(row[0])
        else:
            time.sleep(poll_interval)


if __name__ == "__main__":
    run_worker()
