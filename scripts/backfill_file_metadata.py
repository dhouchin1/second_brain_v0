#!/usr/bin/env python3
"""
Backfill file metadata for existing notes.

Populates notes.file_type and notes.file_mime_type based on stored files.
Optionally extracts text for images/PDFs (requires Pillow/pytesseract/PyPDF2).

Usage:
  python scripts/backfill_file_metadata.py [--do-ocr] [--limit N] [--dry-run]
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Optional, Tuple

import sys
import pathlib as _p
ROOT = _p.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from config import settings

try:
    from file_processor import FileProcessor
except Exception as e:
    raise SystemExit(f"Failed to import FileProcessor: {e}")


def ensure_columns(conn: sqlite3.Connection) -> Tuple[bool, bool, bool]:
    c = conn.cursor()
    cols = {r[1] for r in c.execute("PRAGMA table_info(notes)").fetchall()}
    has_file_type = "file_type" in cols
    has_file_mime = "file_mime_type" in cols
    has_extracted = "extracted_text" in cols
    return has_file_type, has_file_mime, has_extracted


def fts_has_extracted(conn: sqlite3.Connection) -> bool:
    c = conn.cursor()
    try:
        cols = {r[1] for r in c.execute("PRAGMA table_info(notes_fts)").fetchall()}
        return "extracted_text" in cols
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--do-ocr", action="store_true", help="Also extract text for images/PDFs when missing")
    ap.add_argument("--fix-type", action="store_true", help="Update notes.type to match file_type when present")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of rows processed (0 = no limit)")
    ap.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = ap.parse_args()

    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    has_file_type, has_file_mime, has_extracted = ensure_columns(conn)
    if not (has_file_type and has_file_mime):
        raise SystemExit("Database missing file_type/file_mime_type columns in notes table.")
    has_fts_extracted = fts_has_extracted(conn)

    processor = FileProcessor()
    uploads_dir = settings.uploads_dir
    audio_dir = settings.audio_dir

    # Select candidates with files
    q_all = (
        "SELECT id, file_filename, file_type, file_mime_type, extracted_text, type "
        "FROM notes WHERE file_filename IS NOT NULL AND file_filename != '' "
        "ORDER BY id DESC"
    )
    rows_all = conn.execute(q_all).fetchall()

    # Filter for metadata-missing set
    rows = [r for r in rows_all if (not r["file_type"] or not r["file_mime_type"])]
    if args.limit and len(rows) > args.limit:
        rows = rows[: args.limit]

    updated = 0
    ocred = 0
    missing_files = 0
    skipped = 0

    for r in rows_all if args.fix_type else rows:
        note_id = r["id"]
        ff = r["file_filename"]
        if not ff:
            skipped += 1
            continue

        # Try resolve path
        path_candidates = [uploads_dir / ff, audio_dir / ff]
        file_path: Optional[Path] = None
        for p in path_candidates:
            if p.exists():
                file_path = p
                break
        if not file_path:
            missing_files += 1
            continue

        # Detect type/mime using FileProcessor logic
        try:
            data = file_path.read_bytes()
            mime, category = processor.detect_file_type(data, file_path.name)
        except Exception:
            skipped += 1
            continue

        # Prepare updates
        new_file_type = category
        new_mime = mime

        # Optional OCR/PDF extraction when requested and extracted_text missing
        new_extracted: Optional[str] = None
        if args.do_ocr and (r["extracted_text"] is None or r["extracted_text"] == ""):
            try:
                if category == "image":
                    text, meta = processor.extract_image_text(file_path)
                    new_extracted = text or None
                elif category == "document":
                    text, meta = processor.extract_pdf_text(file_path)
                    new_extracted = text or None
                # Don't OCR audio here
            except Exception:
                new_extracted = None

        # Apply updates
        changed = False
        if args.dry_run:
            msg = f"[DRY] note {note_id}: {ff}"
            if not (r["file_type"] and r["file_mime_type"]):
                msg += f" -> type={new_file_type}, mime={new_mime}"
            if args.fix_type and (r["type"] != new_file_type) and new_file_type in ("image","document","audio"):
                msg += f" (fix type from {r['type']} -> {new_file_type})"
            msg += f" extracted={bool(new_extracted)}"
            print(msg)
        else:
            if not (r["file_type"] and r["file_mime_type"]):
                conn.execute(
                    "UPDATE notes SET file_type=?, file_mime_type=? WHERE id=?",
                    (new_file_type, new_mime, note_id),
                )
                changed = True
            if args.fix_type and (r["type"] != new_file_type) and new_file_type in ("image","document","audio"):
                conn.execute("UPDATE notes SET type=? WHERE id=?", (new_file_type, note_id))
                changed = True
            if new_extracted is not None and has_extracted:
                conn.execute(
                    "UPDATE notes SET extracted_text=? WHERE id=?",
                    (new_extracted, note_id),
                )
                if has_fts_extracted:
                    # Refresh FTS row to include extracted_text
                    row2 = conn.execute(
                        "SELECT title, summary, tags, actions, content FROM notes WHERE id=?",
                        (note_id,),
                    ).fetchone()
                    if row2:
                        conn.execute("DELETE FROM notes_fts WHERE rowid=?", (note_id,))
                        conn.execute(
                            "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content, extracted_text) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (note_id, row2["title"], row2["summary"], row2["tags"], row2["actions"], row2["content"], new_extracted),
                        )
                ocred += 1
            if changed:
                updated += 1
            conn.commit()

    print(
        f"Backfill complete: updated={updated}, ocred={ocred}, missing_files={missing_files}, skipped={skipped}"
    )


if __name__ == "__main__":
    main()
