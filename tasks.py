import sqlite3
import time
from datetime import datetime
from typing import Optional

from llm_utils import ollama_summarize, ollama_generate_title
from config import settings
from audio_utils import transcribe_audio
from services.audio_queue import audio_queue
try:
    # Optional realtime status broadcasting
    from realtime_status import status_manager  # type: ignore
    _REALTIME = True
except Exception:
    _REALTIME = False


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
        # Mark start of transcription
        try:
            c.execute("UPDATE notes SET status=? WHERE id=?", ("transcribing:0", note_id))
            conn.commit()
            if _REALTIME:
                # Best-effort broadcast; ignore errors
                try:
                    import asyncio
                    asyncio.run(status_manager.emit_progress(note_id, "transcribing", 10, "Starting transcription"))
                except Exception:
                    pass
        except Exception:
            pass

        def _on_progress(done: int, total: int):
            pct = 10 + int((done / max(total, 1)) * 70)
            try:
                c2 = get_conn().cursor()
                c2.execute("UPDATE notes SET status=? WHERE id=?", (f"transcribing:{pct}", note_id))
                c2.connection.commit()
                c2.connection.close()
                if _REALTIME:
                    try:
                        import asyncio
                        asyncio.run(status_manager.emit_progress(note_id, "transcribing", pct, f"Segment {done}/{total}"))
                    except Exception:
                        pass
            except Exception:
                pass

        transcript, converted_name = transcribe_audio(audio_path, progress_cb=_on_progress)
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
    
    # Mark as completed in FIFO queue
    audio_queue.mark_completed(note_id, success=True)

    # Update Obsidian export with finalized content
    try:
        from obsidian_sync import ObsidianSync
        ObsidianSync().export_note_to_obsidian(note_id)
    except Exception:
        pass


def run_worker(poll_interval: int = 5):
    """Worker that processes notes from FIFO queue with batch processing support"""
    while True:
        # Check if batch processing should be enabled
        if audio_queue.should_enable_batch_processing():
            # Process batch mode
            process_batch()
        else:
            # Process single item from FIFO queue
            next_item = audio_queue.get_next_for_processing()
            if next_item:
                note_id, user_id = next_item
                try:
                    process_note(note_id)
                except Exception as e:
                    print(f"Error processing note {note_id}: {e}")
                    # Mark as failed in queue
                    audio_queue.mark_completed(note_id, success=False)
            else:
                # No items in queue, sleep
                time.sleep(poll_interval)


def process_batch():
    """Process all queued items in batch mode"""
    conn = get_conn()
    cursor = conn.cursor()
    
    # Get all queued items in FIFO order
    cursor.execute("""
        SELECT q.note_id, q.user_id 
        FROM audio_processing_queue q
        JOIN notes n ON q.note_id = n.id
        WHERE q.status = 'queued'
        ORDER BY q.priority DESC, n.timestamp ASC
    """)
    
    queued_items = cursor.fetchall()
    conn.close()
    
    if not queued_items:
        return
    
    print(f"Starting batch processing of {len(queued_items)} items")
    
    for note_id, user_id in queued_items:
        # Mark as processing (this will be handled by get_next_for_processing)
        next_item = audio_queue.get_next_for_processing()
        if next_item and next_item[0] == note_id:
            try:
                process_note(note_id)
                print(f"Batch processed note {note_id}")
            except Exception as e:
                print(f"Error in batch processing note {note_id}: {e}")
                audio_queue.mark_completed(note_id, success=False)
        
        # Small delay between batch items to prevent system overload
        time.sleep(1)
    
    print(f"Completed batch processing of {len(queued_items)} items")


if __name__ == "__main__":
    run_worker()
