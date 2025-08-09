import sqlite3
import frontmatter
from config import settings

def create_db():
    db_path = settings.vault_path / "secondbrain_index.db"
    conn = sqlite3.connect(db_path)
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
    db_path = settings.vault_path / "secondbrain_index.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    for note_path in settings.vault_path.glob("*.md"):
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
                str(note_path.relative_to(settings.vault_path)),
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
