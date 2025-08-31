import sqlite3
import time
import asyncio
from datetime import datetime
from typing import Optional

from llm_utils import ollama_summarize, ollama_generate_title
from config import settings
from audio_utils import transcribe_audio


def get_conn():
    return sqlite3.connect(str(settings.db_path))


async def process_note_with_status(note_id: int):
    """Process note with real-time status updates"""
    # Import here to avoid circular imports
    try:
        from realtime_status import status_manager
    except ImportError:
        # Fallback to synchronous processing if realtime module unavailable
        return process_note(note_id)
    
    try:
        await status_manager.emit_progress(note_id, "starting", 0, "Initializing processing...")
        
        conn = get_conn()
        c = conn.cursor()
        row = c.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not row:
            conn.close()
            await status_manager.emit_completion(note_id, False, "Note not found")
            return
        
        cols = [d[0] for d in c.description]
        note = dict(zip(cols, row))
        content = note.get("content") or ""
        tags = note.get("tags", "")
        actions = note.get("actions", "")
        note_type = note.get("type", "note")
        audio_filename: Optional[str] = note.get("audio_filename")
        conn.close()

        # Gate transcription to run one-at-a-time across the worker (configurable)
        if note_type == "audio" and audio_filename:
            await status_manager.emit_progress(note_id, "transcribing", 20, "Transcribing audio...")
            audio_path = settings.audio_dir / audio_filename
            loop = asyncio.get_running_loop()
            # Create a module-level semaphore for transcription, default size=1
            global _TRANSCRIBE_SEM
            try:
                _TRANSCRIBE_SEM
            except NameError:
                _TRANSCRIBE_SEM = asyncio.Semaphore(getattr(settings, 'transcription_concurrency', 1) or 1)

            async def _do_transcribe():
                return await loop.run_in_executor(None, transcribe_audio, audio_path)

            if _TRANSCRIBE_SEM:
                async with _TRANSCRIBE_SEM:
                    transcript, converted_name = await _do_transcribe()
            else:
                transcript, converted_name = await _do_transcribe()
            if transcript:
                content = transcript
                audio_filename = converted_name
                await status_manager.emit_progress(note_id, "transcribing", 40, "Audio transcribed")
            else:
                content = ""
                await status_manager.emit_progress(note_id, "transcribing", 40, "Transcription failed")

        # Title generation (throttled/optional)
        if getattr(settings, 'ai_processing_enabled', True) and content:
            await status_manager.emit_progress(note_id, "generating_title", 50, "Generating title...")
            loop = asyncio.get_running_loop()
            title = await loop.run_in_executor(None, ollama_generate_title, content)
            if not title or title.lower().startswith("untitled"):
                title = content.splitlines()[0][:60] if content else "[No Title]"
        else:
            title = content.splitlines()[0][:60] if content else "[No Title]"

        # AI processing (chunked + throttle, optional)
        summary = ""
        ai_tags = []
        ai_actions = []
        if getattr(settings, 'ai_processing_enabled', True) and content:
            await status_manager.emit_progress(note_id, "ai_processing", 70, "AI analysis in progress...")
            chunk_size = max(200, int(getattr(settings, 'ai_chunk_size_chars', 1500) or 1500))
            delay = max(0, int(getattr(settings, 'ai_throttle_delay_seconds', 2) or 0))
            chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
            loop = asyncio.get_running_loop()
            combined_summary = []
            tag_set = []
            action_list = []
            for idx, ch in enumerate(chunks, 1):
                part = await loop.run_in_executor(None, ollama_summarize, ch)
                s = (part.get('summary') or '').strip()
                if s:
                    combined_summary.append(s)
                ts = part.get('tags') or []
                for t in ts:
                    if t and t not in tag_set:
                        tag_set.append(t)
                acts = part.get('actions') or []
                action_list.extend([a for a in acts if a])
                if delay:
                    await asyncio.sleep(delay)
            summary = "\n\n".join(combined_summary).strip()
            ai_tags = tag_set
            ai_actions = action_list
        
        # Finalize tags and actions
        await status_manager.emit_progress(note_id, "finalizing", 90, "Finalizing note...")
        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        tag_list.extend([t for t in ai_tags if t and t not in tag_list])
        tags = ",".join(tag_list)
        actions = "\n".join(ai_actions)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Save to database
        conn = get_conn()
        c = conn.cursor()
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
        
        # Emit completion
        await status_manager.emit_completion(note_id, True)
        
    except Exception as e:
        await status_manager.emit_completion(note_id, False, str(e))
        raise


def process_note(note_id: int):
    """Synchronous version for backward compatibility"""
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

    if getattr(settings, 'ai_processing_enabled', True) and content:
        title = ollama_generate_title(content)
        if not title or title.lower().startswith("untitled"):
            title = content.splitlines()[0][:60] if content else "[No Title]"
        # Chunked summarize (sync)
        chunk_size = max(200, int(getattr(settings, 'ai_chunk_size_chars', 1500) or 1500))
        delay = max(0, int(getattr(settings, 'ai_throttle_delay_seconds', 2) or 0))
        chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
        combined_summary = []
        tag_set = []
        action_list = []
        for ch in chunks:
            part = ollama_summarize(ch)
            s = (part.get('summary') or '').strip()
            if s:
                combined_summary.append(s)
            ts = part.get('tags') or []
            for t in ts:
                if t and t not in tag_set:
                    tag_set.append(t)
            acts = part.get('actions') or []
            action_list.extend([a for a in acts if a])
            if delay:
                time.sleep(delay)
        summary = "\n\n".join(combined_summary).strip()
        ai_tags = tag_set
        ai_actions = action_list
    else:
        title = content.splitlines()[0][:60] if content else "[No Title]"
        summary = ""
        ai_tags = []
        ai_actions = []
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


async def run_async_worker(poll_interval: int = 5):
    """Async worker with real-time status updates"""
    while True:
        conn = get_conn()
        c = conn.cursor()
        row = c.execute("SELECT id FROM notes WHERE status='pending' ORDER BY id LIMIT 1").fetchone()
        conn.close()
        
        if row:
            await process_note_with_status(row[0])
        else:
            await asyncio.sleep(poll_interval)


def run_worker(poll_interval: int = 5):
    """Synchronous worker (fallback)"""
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
    # Try to run async worker, fallback to sync
    try:
        asyncio.run(run_async_worker())
    except ImportError:
        print("Running synchronous worker (async dependencies not available)")
        run_worker()
