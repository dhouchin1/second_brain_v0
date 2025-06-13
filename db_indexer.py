import sqlite3
from pathlib import Path
import frontmatter

VAULT_PATH = Path("/Users/dhouchin/Obsidian/SecondBrain")
DB_PATH = VAULT_PATH / "secondbrain_index.db"

def create_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id TEXT PRIMARY KEY,
        path TEXT,
        title TEXT,
        timestamp TEXT,
        type TEXT,
        summary TEXT,
        tags TEXT,
        actions TEXT
    )
    """)
    conn.commit()
    conn.close()

def index_vault():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for note_path in VAULT_PATH.glob("*.md"):
        try:
            post = frontmatter.load(note_path)
            fm = post.metadata
            note_id = fm.get("id", note_path.stem)
            c.execute("""
                INSERT OR REPLACE INTO notes
                (id, path, title, timestamp, type, summary, tags, actions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                note_id,
                str(note_path.relative_to(VAULT_PATH)),
                fm.get("title", note_path.stem),
                fm.get("timestamp"),
                fm.get("type", "note"),
                fm.get("summary", ""),
                ",".join(fm.get("tags", [])),
                ",".join(fm.get("actions", []))
            ))
        except Exception as e:
            print(f"Failed to parse {note_path}: {e}")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_db()
    index_vault()
    print("Vault indexed!")
