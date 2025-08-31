#!/usr/bin/env python3
"""
Convert existing stored images to PNG and update DB records.

Usage:
  python scripts/convert_images_to_png.py [--dry-run]

- Scans notes with image attachments (by file_type or file_mime_type)
- Converts non-PNG files to PNG using FileProcessor.convert_image_to_png()
- Updates notes.file_filename, notes.file_mime_type, notes.file_size accordingly
"""
from __future__ import annotations

import sqlite3
import argparse
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
    ap.add_argument('--dry-run', action='store_true', help='Preview changes without writing')
    args = ap.parse_args()

    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Find image notes with non-PNG or unknown mime
    rows = c.execute(
        """
        SELECT id, file_filename, file_type, file_mime_type
        FROM notes
        WHERE file_filename IS NOT NULL AND file_filename != ''
          AND (
                file_type = 'image'
             OR (file_mime_type IS NOT NULL AND file_mime_type LIKE 'image/%')
          )
        ORDER BY id ASC
        """
    ).fetchall()

    proc = FileProcessor()

    converted = 0
    skipped = 0
    missing = 0

    for r in rows:
        nid = r['id']
        fn = r['file_filename']
        if not fn:
            skipped += 1
            continue
        src = settings.uploads_dir / fn
        if not src.exists():
            # In rare cases image might be in audio dir; check there
            alt = settings.audio_dir / fn
            if alt.exists():
                src = alt
            else:
                print(f"[note {nid}] missing file: {fn}")
                missing += 1
                continue

        # Skip if already PNG or GIF (keep animation)
        if src.suffix.lower() in ('.png', '.gif'):
            skipped += 1
            continue

        target = proc.convert_image_to_png(src)
        if not target.exists():
            print(f"[note {nid}] conversion failed (no target): {src}")
            skipped += 1
            continue

        # If target differs and not dry-run, delete original
        if not args.dry_run and target != src:
            try:
                src.unlink()
            except Exception:
                pass

        if args.dry_run:
            print(f"[DRY] note {nid}: {fn} -> {target.name}")
        else:
            size = target.stat().st_size
            c.execute(
                "UPDATE notes SET file_filename=?, file_mime_type=?, file_type=?, file_size=? WHERE id=?",
                (target.name, 'image/png', 'image', size, nid)
            )
            conn.commit()
            print(f"[OK] note {nid}: {fn} -> {target.name}")
            converted += 1

    conn.close()
    print(f"Done. converted={converted}, skipped={skipped}, missing={missing}")


if __name__ == '__main__':
    main()
