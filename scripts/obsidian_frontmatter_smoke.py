"""
Quick smoke test for obsidian_common.load_frontmatter_file/dump_frontmatter_file.

Writes a temporary markdown with frontmatter, then reads it back and asserts
round-trip integrity for a few fields. Designed to run without python-frontmatter
installed, but will also pass if it is available.
"""
from __future__ import annotations
import tempfile
from pathlib import Path
from obsidian_common import load_frontmatter_file, dump_frontmatter_file

def main() -> int:
    meta = {
        "id": 123,
        "title": "Test Note",
        "tags": ["#demo", "#test"],
        "created": "2024-01-01T00:00:00",
    }
    content = "Hello world!\nThis is a test body."

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "note.md"
        dump_frontmatter_file(p, content, meta)
        m2, c2 = load_frontmatter_file(p)
        assert m2.get("id") == meta["id"], (m2, meta)
        assert m2.get("title") == meta["title"], (m2, meta)
        assert c2.strip().endswith("test body."), c2
        print("OK: obsidian frontmatter load/dump smoke passed →", p)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

