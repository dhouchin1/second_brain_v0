#!/usr/bin/env python3
"""
Attach an existing uploaded file to a note by ID.

Usage:
  python scripts/attach_file_to_note.py --note-id 99 --filename 2025-08-29-164431-91594c5b.png [--user-id 2]
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Optional

import sys
import pathlib as _p
ROOT = _p.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from file_processor import FileProcessor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--note-id', type=int, required=True)
    ap.add_argument('--filename', type=str, required=True)
    ap.add_argument('--user-id', type=int, default=None, help='Verify note ownership (optional)')
    args = ap.parse_args()

    fn = args.filename
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    row = c.execute('SELECT id, user_id FROM notes WHERE id=?', (args.note_id,)).fetchone()
    if not row:
        raise SystemExit(f'Note {args.note_id} not found')
    if args.user_id is not None and row['user_id'] != args.user_id:
        raise SystemExit(f'Note {args.note_id} not owned by user {args.user_id}')

    uploads = settings.uploads_dir / fn
    audio = settings.audio_dir / fn
    path: Optional[Path] = None
    if uploads.exists():
        path = uploads
    elif audio.exists():
        path = audio
    else:
        raise SystemExit(f'File not found in uploads or audio: {fn}')

    data = path.read_bytes()
    proc = FileProcessor()
    mime, category = proc.detect_file_type(data, path.name)
    size = path.stat().st_size

    # attach to note
    c.execute(
        'UPDATE notes SET file_filename=?, file_type=?, file_mime_type=?, file_size=? WHERE id=?',
        (fn, category, mime, size, args.note_id)
    )
    # optional: ensure FTS row exists (no change to text content here)
    conn.commit()
    conn.close()
    print(f'Attached {fn} to note {args.note_id} (type={category}, mime={mime}, size={size})')


if __name__ == '__main__':
    main()

