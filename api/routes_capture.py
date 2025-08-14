# ──────────────────────────────────────────────────────────────────────────────
# File: api/routes_capture.py
# ──────────────────────────────────────────────────────────────────────────────
"""
Apple Shortcuts-friendly capture endpoints:
- POST /capture          (JSON)   → create a text note
- POST /capture/audio    (multipart/form-data) → save audio, convert to WAV, optional Whisper transcript → note
"""
from __future__ import annotations
import os, io, tempfile, subprocess, time
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from services.search_adapter import SearchService
import shutil

router = APIRouter(prefix="", tags=["capture"])
svc = SearchService(db_path=os.getenv('SQLITE_DB','notes.db'), vec_ext_path=os.getenv('SQLITE_VEC_PATH'))

AUDIO_DIR = Path(os.getenv('AUDIO_DIR', 'audio'))
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

class CaptureIn(BaseModel):
    type: str = 'text'
    text: str
    tags: str | None = ''
    title: str | None = None

@router.post('/capture')
def capture_text(payload: CaptureIn):
    title = payload.title or (payload.text[:80] + ('…' if len(payload.text) > 80 else ''))
    note_id = svc.upsert_note(None, title, payload.text, payload.tags or '')
    return {"ok": True, "id": note_id}


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
    return p.returncode, out, err


def _to_wav(src_path: Path, dst_path: Path) -> None:
    ffmpeg = os.getenv('FFMPEG_BIN', 'ffmpeg')
    code, out, err = _run([ffmpeg, '-y', '-i', str(src_path), '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(dst_path)])
    if code != 0:
        raise RuntimeError(f"ffmpeg failed: {err[:300]}")


def _transcribe(wav_path: Path) -> str | None:
    bin_ = os.getenv('WHISPER_BIN', 'whisper-cli')
    model = os.getenv('WHISPER_MODEL', 'ggml-base.en.bin')
    if not shutil.which(bin_):
        return None
    with tempfile.TemporaryDirectory() as td:
        outbase = Path(td) / 'out'
        code, out, err = _run([bin_, '-m', model, '-f', str(wav_path), '-otxt', '-of', str(outbase)])
        if code != 0:
            return None
        txt = (outbase.with_suffix('.txt'))
        return txt.read_text(encoding='utf-8') if txt.exists() else None

@router.post('/capture/audio')
def capture_audio(file: UploadFile = File(...), title: str | None = Form(None), tags: str | None = Form('')):
    # Save upload
    ts = int(time.time())
    raw_path = AUDIO_DIR / f"rec_{ts}_{file.filename or 'audio'}"
    with raw_path.open('wb') as f:
        f.write(file.file.read())
    # Convert to wav
    wav_path = raw_path.with_suffix('.wav')
    try:
        _to_wav(raw_path, wav_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Audio convert failed: {e}")
    # Try to transcribe (optional)
    transcript = None
    try:
        transcript = _transcribe(wav_path)
    except Exception:
        transcript = None
    # Build note body
    body_lines = [f"[Audio] {raw_path.name}", f"WAV: {wav_path.name}"]
    if transcript:
        body_lines += ["", "Transcript:", transcript]
    body = "\n".join(body_lines)
    note_title = title or (transcript[:80] + '…' if transcript else f"Voice Capture {ts}")
    note_id = svc.upsert_note(None, note_title, body, tags or '')
    return {"ok": True, "id": note_id, "transcribed": bool(transcript)}