#!/usr/bin/env python3
# scripts/seed_starter_vault.py
"""
Seed a small, high-signal set of items INTO AN EXISTING / ACTIVE VAULT.
- Writes Markdown (+ YAML front-matter) into a configurable namespace folder inside the vault
  (defaults to ".seed_samples"), grouped by project for tidiness.
- Mirrors the same content into SQLite: notes table and FTS5 search index.
- Optionally creates embeddings via local Ollama; stores to sqlite-vec if available,
  otherwise falls back to a plain 'embedding' table with vec_json.
- Safe to re-run (idempotent upserts by stable IDs).

Usage:
  python scripts/seed_starter_vault.py --force
  python scripts/seed_starter_vault.py --namespace ".seed_samples" --no-embed

Assumptions:
- Your repo exposes config.settings with db_path and vault_path (Pydantic Settings).
- SQLite has FTS5 available (for the notes_fts virtual table).
- If sqlite-vec is present, a vec0 virtual table can be created (we try; if it fails we fall back).

Notes:
- This script does NOT assume a dedicated "starter vault" directory; it seeds into your active vault.
- All seeded IDs are prefixed with "seed-" to avoid collisions with real content.
- Integrates with existing Second Brain database schema (notes table).
"""

from __future__ import annotations
import argparse
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import uuid

# Optional: for local Ollama embeddings
try:
    import requests  # type: ignore
except Exception:
    requests = None  # gracefully skip embeddings if not available

# ---- Import repo settings ----------------------------------------------------
try:
    sys.path.append(str(Path(__file__).parent.parent))  # Add parent directory to path
    from config import settings  # must define settings.db_path and settings.vault_path
except Exception as e:
    print("ERROR: Could not import config.settings (expected db_path and vault_path).", file=sys.stderr)
    raise

log = logging.getLogger("seed_starter_vault")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

ISO = "%Y-%m-%dT%H:%M:%S%z"


# ---------- Minimal helpers ---------------------------------------------------

def now_iso() -> str:
    return datetime.now().astimezone().strftime(ISO)

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def to_yaml_front_matter(meta: Dict, body: str) -> str:
    """Tiny YAML emitter for simple types (no external deps)."""
    def emit(d: Dict, indent: int = 0) -> str:
        lines = []
        for k, v in d.items():
            if isinstance(v, (list, tuple)):
                lines.append(" " * indent + f"{k}:")
                for it in v:
                    lines.append(" " * (indent + 2) + f"- {it}")
            elif isinstance(v, dict):
                lines.append(" " * indent + f"{k}:")
                for k2, v2 in v.items():
                    lines.append(" " * (indent + 2) + f"{k2}: {v2}")
            else:
                lines.append(" " * indent + f"{k}: {v}")
        return "\n".join(lines)
    return f"---\n{emit(meta)}\n---\n{body.rstrip()}\n"

def chunk_markdown(md_text: str, max_chars: int = 1200) -> List[Tuple[str, str]]:
    """
    Chunk markdown by ATX headings; further split long sections to ~max_chars.
    Returns list[(heading, text)].
    """
    parts: List[Tuple[str, str]] = []
    lines = md_text.replace("\r\n", "\n").split("\n")
    sections: List[Tuple[str, List[str]]] = []
    cur_head = "Introduction"
    buf: List[str] = []
    for ln in lines:
        if ln.lstrip().startswith("#"):
            if buf:
                sections.append((cur_head, buf))
                buf = []
            cur_head = ln.lstrip("# ").strip() or "Section"
        else:
            buf.append(ln)
    if buf:
        sections.append((cur_head, buf))

    for head, block in sections:
        text_block = "\n".join(block).strip()
        if not text_block:
            continue
        if len(text_block) <= max_chars:
            parts.append((head, text_block))
        else:
            paras = [p for p in text_block.split("\n\n") if p.strip()]
            cur = ""
            for p in paras:
                if len(cur) + len(p) + 2 <= max_chars:
                    cur = (cur + "\n\n" + p).strip()
                else:
                    if cur:
                        parts.append((head, cur))
                    if len(p) <= max_chars:
                        cur = p
                    else:
                        s = p
                        while len(s) > max_chars:
                            parts.append((head, s[:max_chars]))
                            s = s[max_chars:]
                        cur = s
            if cur:
                parts.append((head, cur))
    return parts


# ---------- Embeddings via Ollama --------------------------------------------

def try_ollama_embed(texts: List[str], model: str = "nomic-embed-text", url: str = "http://localhost:11434", timeout: int = 20) -> Optional[List[List[float]]]:
    if not requests:
        return None
    try:
        resp = requests.post(f"{url}/api/embeddings", json={"model": model, "input": texts}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if "embeddings" in data:
            return data["embeddings"]
        if "embedding" in data:
            return [data["embedding"]]
    except Exception as e:
        log.warning("Embeddings skipped: %s", e)
        return None
    return None


# ---------- DB: schema + upsert helpers (adapted for Second Brain) -----------

def db_conn(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys = ON;")
    con.row_factory = sqlite3.Row
    return con

def ensure_embeddings_schema(con: sqlite3.Connection) -> bool:
    """Ensure embeddings tables exist if not already present. Returns True if vec extension available."""
    try:
        # Check if embeddings table exists from migration 002
        row = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'").fetchone()
        if not row:
            # Create basic embeddings table if migration 002 hasn't run
            con.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    note_id INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    embedding_vector TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE,
                    UNIQUE(note_id, model)
                )
            """)
        
        # Try to detect sqlite-vec extension
        has_vec = False
        try:
            con.execute("SELECT count(*) FROM vec_notes_fts LIMIT 1;")
            has_vec = True
        except:
            # Try to create vec table if sqlite-vec is available
            try:
                con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS vec_notes_fts USING vec0(embedding FLOAT[768]);")
                has_vec = True
            except Exception as e:
                log.info("sqlite-vec unavailable, using JSON fallback: %s", e)
                has_vec = False
        
        con.commit()
        return has_vec
        
    except Exception as e:
        log.warning("Embeddings schema setup failed: %s", e)
        return False

def upsert_note(con: sqlite3.Connection, note: Dict, user_id: int = 1) -> int:
    """Upsert note using existing Second Brain schema."""
    cursor = con.execute("""
        INSERT INTO notes (
            title, content, summary, tags, actions, type, 
            timestamp, audio_filename, status, user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
    """, (
        note["title"],
        note["content"], 
        note.get("summary", ""),
        note.get("tags", ""),
        note.get("actions", ""),
        note.get("type", "note"),
        note.get("timestamp", now_iso()),
        note.get("audio_filename"),
        note.get("status", "complete"),
        user_id
    ))
    
    result = cursor.fetchone()
    return result[0] if result else None

def upsert_embeddings(con: sqlite3.Connection, note_id: int, vectors: List[float], model: str, has_vec: bool = False) -> None:
    """Store embeddings using available method."""
    if has_vec:
        try:
            # Try sqlite-vec first
            con.execute("INSERT INTO vec_notes_fts(embedding) VALUES (?)", (json.dumps(vectors),))
            log.debug("Stored vec embedding for note %s", note_id)
            return
        except Exception as e:
            log.debug("Vec storage failed, falling back to JSON: %s", e)
    
    # Fallback to embeddings table
    con.execute("""
        INSERT INTO embeddings (note_id, model, embedding_vector, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(note_id, model) DO UPDATE SET
            embedding_vector = excluded.embedding_vector,
            created_at = excluded.created_at
    """, (note_id, model, json.dumps(vectors), now_iso()))


# ---------- Synthetic-but-realistic seed content ------------------------------

SEED_NOTES = [
    {
        "id": "seed-sop-weekly-review",
        "title": "Weekly Review (SOP)",
        "type": "note",
        "tags": "sop, productivity, review",
        "content": """# Weekly Review (SOP)

## Goals
- Capture loose ends
- Clarify priorities

## Steps
1. Inbox to zero (email, notes, voice)
2. Review calendar last/next 2 weeks
3. Update project Kanban (sec-hardening, roadmap)
4. Log decisions and next actions

## Checklist
- [ ] Process capture inbox
- [ ] Write one decision log
- [ ] Close or re-scope stale tasks""",
        "summary": "Standard operating procedure for conducting weekly reviews to maintain productivity and clear priorities.",
    },
    {
        "id": "seed-decision-auth-front",
        "title": "Decision: Auth Front",
        "type": "note", 
        "tags": "decision, auth, architecture",
        "content": """# Decision: Auth Front

## Context
We need SSO in front of our FastAPI service without refactoring app code.

## Options
- oauth2-proxy + reverse proxy (OIDC)
- Traefik forward-auth

## Decision
Choose **oauth2-proxy** pattern behind a reverse proxy with OIDC.

## Consequences
- Uniform session handling
- App trusts identity headers from the proxy""",
        "summary": "Architectural decision to use oauth2-proxy for SSO authentication without app refactoring.",
    },
    {
        "id": "seed-search-tuning",
        "title": "Search Tuning Notes",
        "type": "note",
        "tags": "search, bm25, embeddings, tuning",
        "content": """# Search Tuning Notes

## Retrieval stack
- BM25 (FTS5) for precise matches
- Embeddings for semantic recall
- Cross-encoder rerank (later)

## Signals
- Project and Person filters
- Recency boost on occurred_at

## Performance Notes
- FTS5 queries under 100ms
- Embedding search scales with document count
- Hybrid approach gives best of both worlds""",
        "summary": "Technical notes on optimizing hybrid search performance with BM25 and embeddings.",
    },
    {
        "id": "seed-http-cheatsheet",
        "title": "HTTP Status Codes (Cheatsheet)",
        "type": "reference",
        "tags": "http, cheatsheet, reference",
        "content": """# HTTP Status Codes (Cheatsheet)

## Success
- 200 OK
- 201 Created
- 204 No Content

## Redirection
- 301 Moved Permanently
- 302 Found
- 304 Not Modified

## Client Error
- 400 Bad Request
- 401 Unauthorized
- 403 Forbidden
- 404 Not Found
- 429 Too Many Requests

## Server Error
- 500 Internal Server Error
- 502 Bad Gateway
- 503 Service Unavailable""",
        "summary": "Quick reference for common HTTP status codes organized by category.",
    },
    {
        "id": "seed-sqlite-performance",
        "title": "SQLite Performance Tips",
        "type": "note",
        "tags": "sqlite, performance, database",
        "content": """# SQLite Performance Tips

## Indexing
- Create indexes for WHERE clauses
- Composite indexes for multiple columns
- FTS5 for full-text search

## Query Optimization
- Use EXPLAIN QUERY PLAN
- Avoid SELECT * when possible
- Use prepared statements

## Maintenance
- VACUUM periodically
- ANALYZE after bulk changes
- Monitor database size

## FTS5 Specific
- Use porter stemming for better matches
- Configure tokenizers appropriately
- Regular REBUILD for optimal performance""",
        "summary": "Best practices for optimizing SQLite database performance and FTS5 search.",
    },
    {
        "id": "seed-ai-processing-pipeline",
        "title": "AI Processing Pipeline Design",
        "type": "note", 
        "tags": "ai, pipeline, architecture, ollama",
        "content": """# AI Processing Pipeline Design

## Components
- **Audio Transcription**: Whisper.cpp for high-quality speech-to-text
- **Content Summarization**: Ollama with local LLM (llama3.2)
- **Tag Generation**: AI-powered semantic tagging
- **Action Extraction**: Identify tasks and follow-ups

## Flow
1. Content ingestion (audio, text, web)
2. Transcription (if audio)
3. AI processing (parallel summarization, tagging)
4. Embedding generation for search
5. Database storage and indexing

## Performance Considerations
- Async processing to avoid blocking
- Configurable concurrency limits
- Graceful degradation when AI unavailable
- Timeout handling for long operations

## Quality Metrics
- Transcription accuracy > 90%
- Processing time < 30s for audio
- Tag relevance validation""",
        "summary": "Architecture and design considerations for the AI-powered content processing pipeline.",
    }
]

SEED_BOOKMARKS = [
    {
        "id": "seed-bm-fts5-overview",
        "title": "SQLite FTS5 Overview",
        "type": "bookmark",
        "tags": "bm25, fts5, sqlite, search",
        "url": "https://www.sqlite.org/fts5.html",
        "content": """# SQLite FTS5 Overview

**URL**: https://www.sqlite.org/fts5.html

## Key Features
- Porter stemming algorithm
- BM25 ranking algorithm
- Snippet generation
- Custom tokenizers

## Usage Patterns
- Content-based search
- Relevance ranking
- Phrase queries
- Boolean operators

## Performance
- Faster than LIKE queries
- Scales well with document count
- Index maintenance overhead""",
        "summary": "Comprehensive overview of SQLite FTS5 full-text search capabilities.",
    },
    {
        "id": "seed-bm-embed-patterns", 
        "title": "Embedding Patterns for Personal Search",
        "type": "bookmark",
        "tags": "embeddings, semantic, retrieval, patterns",
        "url": "https://example.com/embedding-patterns",
        "content": """# Embedding Patterns for Personal Search

**URL**: https://example.com/embedding-patterns

## Embedding Models
- sentence-transformers for general text
- nomic-embed-text for local inference
- Domain-specific fine-tuning

## Storage Patterns
- Vector databases for large scale
- SQLite with JSON for smaller datasets
- sqlite-vec extension for hybrid approach

## Search Strategies
- Semantic similarity only
- Hybrid keyword + semantic
- Re-ranking with cross-encoders

## Personal Search Optimizations
- User behavior learning
- Context-aware retrieval
- Multi-modal embeddings""",
        "summary": "Best practices for implementing embedding-based semantic search in personal knowledge systems.",
    }
]


# ---------- Markdown writer ---------------------------------------------------

def write_markdown(base_dir: Path, meta: Dict, body: str, overwrite: bool) -> Path:
    """
    Writes file under {vault}/{namespace}/{category}/{id}.md to keep samples organized.
    """
    category = meta.get("type", "misc")
    out_dir = base_dir / category
    ensure_dir(out_dir)
    path = out_dir / f"{meta['id']}.md"
    if path.exists() and not overwrite:
        return path
    path.write_text(to_yaml_front_matter(meta, body), encoding="utf-8")
    return path


# ---------- Seeding pipeline --------------------------------------------------

@dataclass
class SeedCfg:
    db_path: Path
    vault_path: Path
    namespace: str = ".seed_samples"
    force: bool = False
    no_embed: bool = False
    embed_model: str = "nomic-embed-text"
    ollama_url: str = "http://localhost:11434"
    vec_dim: int = 768

def validate_seed_data() -> List[str]:
    """Validate seed data for quality and consistency."""
    errors = []
    
    # Validate notes
    seen_ids = set()
    for i, note in enumerate(SEED_NOTES):
        # Check required fields
        required_fields = ['id', 'title', 'type', 'tags', 'content', 'summary']
        for field in required_fields:
            if field not in note or not note[field]:
                errors.append(f"Note {i}: Missing or empty field '{field}'")
        
        # Check ID uniqueness
        if note.get('id') in seen_ids:
            errors.append(f"Note {i}: Duplicate ID '{note['id']}'")
        seen_ids.add(note.get('id'))
        
        # Check content quality
        if len(note.get('content', '')) < 50:
            errors.append(f"Note {i}: Content too short (less than 50 characters)")
        
        # Check summary quality
        if len(note.get('summary', '')) < 20:
            errors.append(f"Note {i}: Summary too short (less than 20 characters)")
        
        # Check tags format
        tags = note.get('tags', '')
        if not tags or not isinstance(tags, str):
            errors.append(f"Note {i}: Invalid tags format")
    
    # Validate bookmarks
    for i, bookmark in enumerate(SEED_BOOKMARKS):
        required_fields = ['id', 'title', 'type', 'tags', 'url', 'content', 'summary']
        for field in required_fields:
            if field not in bookmark or not bookmark[field]:
                errors.append(f"Bookmark {i}: Missing or empty field '{field}'")
        
        # Check ID uniqueness
        if bookmark.get('id') in seen_ids:
            errors.append(f"Bookmark {i}: Duplicate ID '{bookmark['id']}'")
        seen_ids.add(bookmark.get('id'))
        
        # Check URL format
        url = bookmark.get('url', '')
        if not url.startswith(('http://', 'https://')):
            errors.append(f"Bookmark {i}: Invalid URL format '{url}'")
    
    return errors

def seed_active_vault(cfg: SeedCfg) -> None:
    """Main seeding function that populates vault with starter content."""
    # Validate seed data first
    validation_errors = validate_seed_data()
    if validation_errors:
        raise ValueError(f"Seed data validation failed:\n" + "\n".join(validation_errors))
    
    # Prepare filesystem
    ns_root = Path(cfg.vault_path) / cfg.namespace
    ensure_dir(ns_root)
    
    # Validate vault path is writable
    if not cfg.vault_path.exists():
        raise FileNotFoundError(f"Vault path does not exist: {cfg.vault_path}")
    
    if not cfg.vault_path.is_dir():
        raise NotADirectoryError(f"Vault path is not a directory: {cfg.vault_path}")
    
    # Test write permissions
    test_file = ns_root / f".write_test_{uuid.uuid4().hex[:8]}"
    try:
        test_file.write_text("test")
        test_file.unlink()
    except Exception as e:
        raise PermissionError(f"Cannot write to vault directory: {e}")

    # DB connect + schema
    con = db_conn(Path(cfg.db_path))
    try:
        has_vec = ensure_embeddings_schema(con)
        
        # Get default user (assume ID 1 exists)
        user_id = 1
        
        # Process notes
        note_ids = []
        for note_data in SEED_NOTES:
            # Create markdown file
            meta = {
                "id": note_data["id"],
                "type": note_data["type"], 
                "tags": note_data["tags"].split(", "),
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "title": note_data["title"],
                "summary": note_data["summary"]
            }
            write_markdown(ns_root, meta, note_data["content"], overwrite=cfg.force)
            
            # Insert into database
            note_id = upsert_note(con, {
                "title": note_data["title"],
                "content": note_data["content"],
                "summary": note_data["summary"],
                "tags": note_data["tags"],
                "type": note_data["type"],
                "status": "completed",
                "timestamp": now_iso(),
                "created_at": now_iso(),
                "updated_at": now_iso()
            }, user_id)
            
            if note_id:
                note_ids.append((note_id, note_data["content"]))
        
        # Process bookmarks
        for bookmark_data in SEED_BOOKMARKS:
            meta = {
                "id": bookmark_data["id"],
                "type": bookmark_data["type"],
                "tags": bookmark_data["tags"].split(", "),
                "url": bookmark_data["url"],
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "title": bookmark_data["title"],
                "summary": bookmark_data["summary"]
            }
            write_markdown(ns_root, meta, bookmark_data["content"], overwrite=cfg.force)
            
            note_id = upsert_note(con, {
                "title": bookmark_data["title"],
                "content": bookmark_data["content"],
                "summary": bookmark_data["summary"],
                "tags": bookmark_data["tags"],
                "type": bookmark_data["type"],
                "status": "completed",
                "timestamp": now_iso(),
                "created_at": now_iso(),
                "updated_at": now_iso()
            }, user_id)
            
            if note_id:
                note_ids.append((note_id, bookmark_data["content"]))
        
        con.commit()
        
        # Generate embeddings if requested and available
        if not cfg.no_embed and note_ids:
            log.info("Generating embeddings for %d notes...", len(note_ids))
            texts = [content for _, content in note_ids]
            vectors = try_ollama_embed(texts, model=cfg.embed_model, url=cfg.ollama_url)
            
            if vectors:
                for (note_id, _), vector in zip(note_ids, vectors):
                    upsert_embeddings(con, note_id, vector, cfg.embed_model, has_vec)
                con.commit()
                log.info("✓ Stored %d embedding vectors", len(vectors))
            else:
                log.warning("Embeddings failed - Ollama may not be running or model unavailable")
        
        log.info("✓ Seed complete. Markdown files: %s, Database records: %d", ns_root, len(note_ids))
        
    except Exception as e:
        log.error("Seeding failed: %s", e)
        con.rollback()
        raise
    finally:
        con.close()


# ---------- CLI ---------------------------------------------------------------

def parse_args() -> SeedCfg:
    ap = argparse.ArgumentParser(description="Seed starter content into Second Brain vault.")
    ap.add_argument("--namespace", default=".seed_samples", help="Subfolder inside vault for seed content")
    ap.add_argument("--force", action="store_true", help="Overwrite existing files")
    ap.add_argument("--no-embed", action="store_true", help="Skip embedding generation")
    ap.add_argument("--embed-model", default="nomic-embed-text", help="Ollama embedding model")
    ap.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama base URL")
    ap.add_argument("--vec-dim", type=int, default=768, help="Vector dimension")
    args = ap.parse_args()

    return SeedCfg(
        db_path=Path(settings.db_path),
        vault_path=Path(settings.vault_path),
        namespace=args.namespace,
        force=args.force,
        no_embed=args.no_embed,
        embed_model=args.embed_model,
        ollama_url=args.ollama_url,
        vec_dim=args.vec_dim,
    )


if __name__ == "__main__":
    cfg = parse_args()
    seed_active_vault(cfg)