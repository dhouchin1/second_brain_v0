import pathlib
import sqlite3
import subprocess
import time
from datetime import datetime
from typing import Optional

from llm_utils import ollama_summarize, ollama_generate_title
from config import settings


def get_conn():
    return sqlite3.connect(str(settings.db_path))


def transcribe_audio(audio_path: pathlib.Path):
    wav_path = audio_path.with_suffix('.converted.wav')
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", str(audio_path),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)
    ]
    result = subprocess.run(ffmpeg_cmd, capture_output=True)
    if result.returncode != 0:
        print("ffmpeg failed to convert audio:", result.stderr)
        return "", None
    out_txt_path = wav_path.with_suffix(wav_path.suffix + '.txt')
    whisper_cmd = [
        str(settings.whisper_cpp_path),
        "-m", str(settings.whisper_model_path),
        "-f", str(wav_path),
        "-otxt",
    ]
    subprocess.run(whisper_cmd, capture_output=True, text=True)
    for _ in range(20):
        if out_txt_path.exists() and out_txt_path.stat().st_size > 0:
            break
        time.sleep(0.1)
    if out_txt_path.exists() and out_txt_path.stat().st_size > 0:
        content = out_txt_path.read_text().strip()
        return content, wav_path.name
    return "", wav_path.name


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
    summary = ollama_summarize(content) if content else ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute(
        "UPDATE notes SET title=?, content=?, summary=?, status='complete', timestamp=?, audio_filename=? WHERE id=?",
        (title, content, summary, now, audio_filename, note_id),
    )
    c.execute(
        "INSERT INTO notes_fts(rowid, title, summary, tags, content) VALUES (?, ?, ?, ?, ?)",
        (note_id, title, summary, tags, content),
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
