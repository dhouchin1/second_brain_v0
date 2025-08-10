#!/usr/bin/env bash
# scaffold-007.sh
set -euo pipefail
STAMP="$(date +%Y%m%d-%H%M%S)"
b(){ [[ -f "$1" ]] && mv "$1" "$1.$STAMP.bak" && echo "• backup: $1 -> $1.$STAMP.bak" || true; }

mkdir -p templates/partials static

# =========================== app.py ===========================
b app.py
cat > app.py <<'PY'
from datetime import datetime
from fastapi import FastAPI, Request, Form, Body, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pathlib, sqlite3, os, re, httpx, json, math, io, zipfile, typing
from collections import Counter
try:
    import numpy as np
except Exception:
    np = None  # optional; falls back to pure Python

app = FastAPI(title="Second Brain Premium")
BASE_DIR = pathlib.Path(__file__).parent.resolve()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

PAGE_SIZE = 20

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS note_tags (
  note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
  PRIMARY KEY (note_id, tag_id)
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);

-- Embeddings store
CREATE TABLE IF NOT EXISTS note_embeddings (
  note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
  dim INTEGER NOT NULL,
  vec BLOB NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
USING fts5(body, content='notes', content_rowid='id');

CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
  INSERT INTO notes_fts(rowid, body) VALUES (new.id, new.body);
END;
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, body) VALUES('delete', old.id, old.body);
  INSERT INTO notes_fts(rowid, body) VALUES (new.id, new.body);
END;
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, body) VALUES('delete', old.id, old.body);
END;
"""

def get_conn():
    db = BASE_DIR / "notes.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn

# ---------------- helpers ----------------
def norm_tag(name: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "", (name or "").strip().lower().replace("#","").replace(" ", "-"))

def parse_tags(csv: str):
    return [t for t in {norm_tag(x) for x in (csv or "").split(",")} if t]

def ensure_tag(conn, name: str) -> int:
    cur = conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
    if cur.lastrowid:
        return cur.lastrowid
    return conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()["id"]

def set_note_tags(conn, note_id: int, names):
    conn.execute("DELETE FROM note_tags WHERE note_id=?", (note_id,))
    for nm in names:
        tid = ensure_tag(conn, nm)
        conn.execute("INSERT OR IGNORE INTO note_tags(note_id, tag_id) VALUES (?,?)", (note_id, tid))

def map_note_tags(conn, rows):
    ids = [r["id"] for r in rows] if rows else []
    if not ids: return {}
    q = f"""
    SELECT n.id, GROUP_CONCAT(t.name) AS tags
    FROM notes n
    LEFT JOIN note_tags nt ON nt.note_id=n.id
    LEFT JOIN tags t ON t.id=nt.tag_id
    WHERE n.id IN ({",".join("?"*len(ids))})
    GROUP BY n.id
    """
    return {r["id"]: (r["tags"] or "") for r in conn.execute(q, ids).fetchall()}

def hx_trigger_dict(event: str, payload: dict) -> dict:
    return {event: payload}

# -------- settings helpers --------
def get_setting(conn, key: str, default: str | None = None):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return (r["value"] if r else None) or default

def put_setting(conn, key: str, value: str):
    conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()

# -------- embeddings + similarity --------
EMBED_BASE_ENV  = os.getenv("OLLAMA_EMBED_BASE_URL")
EMBED_MODEL_ENV = os.getenv("OLLAMA_EMBED_MODEL")

def _vec_to_blob(vec):
    if np is None:
        return (",".join(f"{float(x):.7f}" for x in vec)).encode("utf-8")
    arr = np.asarray(vec, dtype=np.float32)
    return arr.tobytes()

def _blob_to_vec(blob, dim_hint=None):
    if np is None:
        s = blob.decode("utf-8")
        return [float(x) for x in s.split(",") if x]
    arr = np.frombuffer(blob, dtype=np.float32)
    return arr.astype(np.float32)

def embed_text(text: str, base: str, model: str) -> typing.List[float]:
    payload = {"model": model, "prompt": text}
    r = httpx.post(f"{base}/api/embeddings", json=payload, timeout=30.0)
    r.raise_for_status()
    data = r.json()
    vec = data.get("embedding") or (data.get("data",[{}])[0].get("embedding"))
    if not vec:
        raise RuntimeError("No embedding returned")
    return vec

def ensure_embedding_for_note(conn, note_id: int, body: str):
    base = EMBED_BASE_ENV or get_setting(conn, "OLLAMA_EMBED_BASE_URL", "http://localhost:11434")
    model = EMBED_MODEL_ENV or get_setting(conn, "OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")
    text = body.strip()
    if not text: return
    try:
        vec = embed_text(text, base, model)
        conn.execute(
            "INSERT INTO note_embeddings(note_id, dim, vec) VALUES (?,?,?) "
            "ON CONFLICT(note_id) DO UPDATE SET dim=excluded.dim, vec=excluded.vec",
            (note_id, len(vec), _vec_to_blob(vec))
        )
        conn.commit()
    except Exception as e:
        print("Embedding error:", e)

def cosine(a, b):
    if np is not None:
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0: return 0.0
        return float(np.dot(a, b) / denom)
    dot = sum(x*y for x,y in zip(a,b))
    na  = math.sqrt(sum(x*x for x in a))
    nb  = math.sqrt(sum(y*y for y in b))
    if na == 0 or nb == 0: return 0.0
    return dot / (na * nb)

def semantic_search(conn, query: str, page: int = 1, page_size: int = PAGE_SIZE):
    base = EMBED_BASE_ENV or get_setting(conn, "OLLAMA_EMBED_BASE_URL", "http://localhost:11434")
    model = EMBED_MODEL_ENV or get_setting(conn, "OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")
    qvec = embed_text(query, base, model)
    # pull all embeddings (fine for small/med datasets; for huge, use FAISS)
    rows = conn.execute("SELECT note_id, dim, vec FROM note_embeddings").fetchall()
    scored = []
    for r in rows:
        if r["dim"] != len(qvec):
            continue
        v = _blob_to_vec(r["vec"], dim_hint=r["dim"])
        s = cosine(v, qvec)
        scored.append((r["note_id"], s))
    scored.sort(key=lambda x: x[1], reverse=True)
    total = len(scored)
    start = (page - 1) * page_size
    end   = start + page_size
    page_ids = [i for (i, _) in scored[start:end]]
    if not page_ids:
        return [], 0
    q = f"SELECT id, body, created_at FROM notes WHERE id IN ({','.join('?'*len(page_ids))})"
    items = conn.execute(q, page_ids).fetchall()
    order = {nid:i for i,nid in enumerate(page_ids)}
    items.sort(key=lambda r: order[r["id"]])
    return items, total

# ---------------- pages (unchanged + minor additions) ----------------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"]
    recent = conn.execute("SELECT id, body, created_at FROM notes ORDER BY datetime(created_at) DESC LIMIT 5").fetchall()
    tagmap = map_note_tags(conn, recent)
    recent_list = [dict(r) | {"tags": tagmap.get(r["id"], "")} for r in recent]
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": {"notes": total}, "recent": recent_list})

@app.get("/notes", response_class=HTMLResponse)
def notes_page(request: Request, tag: str = "", page: int = 1):
    conn = get_conn()
    base_sql = "FROM notes n"
    params = []
    if tag:
        base_sql += " WHERE EXISTS (SELECT 1 FROM note_tags nt JOIN tags t ON t.id=nt.tag_id WHERE nt.note_id=n.id AND t.name=?)"
        params.append(tag)
    count = conn.execute(f"SELECT COUNT(*) c {base_sql}", params).fetchone()["c"]
    offset = (page - 1) * PAGE_SIZE
    rows = conn.execute(f"SELECT n.id, n.body, n.created_at {base_sql} ORDER BY datetime(n.created_at) DESC LIMIT ? OFFSET ?", (*params, PAGE_SIZE, offset)).fetchall()
    tagmap = map_note_tags(conn, rows)
    notes = [dict(r) | {"tags": tagmap.get(r["id"], "")} for r in rows]
    has_more = (offset + PAGE_SIZE) < count
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/note_page.html", {"request": request, "notes": notes, "tag": tag, "next_page": (page+1) if has_more else None})
    return templates.TemplateResponse("notes.html", {"request": request, "notes": notes, "active_tag": tag, "next_page": (2 if has_more else None)})

# Note detail / editing endpoints omitted here for brevity, but assumed present from previous scaffold.
# --- Keep your existing /notes/{id}, /notes/{id}/edit, /notes/{id}/update, /notes POST, /notes/batch, etc. ---

# ---------------- Search (FTS and Semantic) ----------------
@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = "", page: int = 1, embed: int = 0):
    conn = get_conn()
    items = []; total = 0
    using_embed = bool(embed)
    if q:
        if using_embed:
            try:
                items, total = semantic_search(conn, q, page=page, page_size=PAGE_SIZE)
            except Exception:
                # fallback to FTS on any embedding error
                using_embed = False
        if not using_embed:
            total = conn.execute("SELECT COUNT(*) c FROM notes_fts WHERE notes_fts MATCH ?", (q,)).fetchone()["c"]
            offset = (page - 1) * PAGE_SIZE
            items = conn.execute("""
              SELECT n.id, n.body, n.created_at
              FROM notes_fts f JOIN notes n ON n.id=f.rowid
              WHERE notes_fts MATCH ?
              ORDER BY bm25(notes_fts) LIMIT ? OFFSET ?
            """, (q, PAGE_SIZE, offset)).fetchall()
    tagmap = map_note_tags(conn, items)
    notes = [dict(r) | {"tags": tagmap.get(r["id"], "")} for r in items]
    has_more = (page * PAGE_SIZE) < total
    ctx = {"request": request, "q": q, "notes": notes, "next_page": (page+1) if has_more else None, "embed": 1 if using_embed else 0}
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/note_page.html", ctx)
    return templates.TemplateResponse("search.html", ctx)

# Quick search overlay stays FTS for speed
@app.get("/api/q", response_class=HTMLResponse)
def quick_search_partial(request: Request, q: str):
    conn = get_conn()
    q = (q or "").strip()
    if not q: return HTMLResponse("")
    rows = conn.execute("""
      SELECT n.id, n.body, n.created_at
      FROM notes_fts f JOIN notes n ON n.id=f.rowid
      WHERE notes_fts MATCH ?
      ORDER BY bm25(notes_fts) LIMIT 20
    """, (q,)).fetchall()
    tagmap = map_note_tags(conn, rows)
    items = [dict(r) | {"tags": tagmap.get(r["id"], "")} for r in rows]
    return templates.TemplateResponse("partials/search_results.html", {"request": request, "items": items})

# ---------------- Exports ----------------
def _all_notes(conn):
    rows = conn.execute("SELECT id, body, created_at FROM notes ORDER BY id ASC").fetchall()
    tagmap = map_note_tags(conn, rows)
    out = []
    for r in rows:
        out.append({"id": r["id"], "body": r["body"], "created_at": r["created_at"], "tags": [t for t in (tagmap.get(r["id"], "") or "").split(",") if t]})
    return out

@app.get("/export", response_class=HTMLResponse)
def export_page(request: Request):
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"]
    tags  = conn.execute("SELECT COUNT(*) c FROM tags").fetchone()["c"]
    return templates.TemplateResponse("export.html", {"request": request, "total": total, "tags": tags})

@app.get("/export/json")
def export_json():
    conn = get_conn()
    data = {"exported_at": datetime.utcnow().isoformat(timespec="seconds")+"Z", "notes": _all_notes(conn)}
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    headers = {"Content-Disposition": 'attachment; filename="second_brain_export.json"'}
    return Response(content=payload, media_type="application/json", headers=headers)

def _slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s)
    return s[:60] or "note"

def _title_from_body(body: str) -> str:
    for line in (body or "").splitlines():
        t = line.strip()
        if t: return t
    return "Untitled"

@app.get("/export/markdown.zip")
def export_markdown_zip():
    conn = get_conn()
    notes = _all_notes(conn)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in notes:
            title = _title_from_body(n["body"])
            name = f'{n["id"]}-{_slugify(title)}.md'
            fm_tags = ", ".join(n["tags"])
            content = f"""--- 
id: {n["id"]}
created_at: {n["created_at"]}
tags: [{fm_tags}]
---
{n["body"]}
"""
            zf.writestr(name, content)
    buf.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="second_brain_markdown.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)
PY

# =========================== templates (Search + Export + Nav) ===========================
b templates/search.html
cat > templates/search.html <<'HTML'
{% extends "base.html" %}
{% block title %}Search — Second Brain Premium{% endblock %}
{% block content %}
<div class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Search</h1>
  <form method="get" action="/search" class="mt-4 grid grid-cols-1 md:grid-cols-5 gap-2 items-center">
    <input name="q" value="{{ q or '' }}" placeholder="Find text or #tag" class="md:col-span-3 rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-2">
    <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
      <input type="checkbox" name="embed" value="1" {% if embed %}checked{% endif %}> Semantic
    </label>
    <button class="px-3 py-2 rounded-xl bg-brand-600 text-white">Search</button>
  </form>

  {% if q %}
    <h2 class="mt-6 text-sm text-slate-500">Results for “{{ q }}” {% if embed %}<span class="ml-2 inline-block px-2 py-0.5 rounded bg-indigo-600 text-white">semantic</span>{% endif %}</h2>
    <ul id="notes-list" class="mt-2 divide-y divide-slate-200/80 dark:divide-white/10">
      {% for n in notes %}
        {% include 'partials/note_row_selectable.html' %}
      {% else %}
        <li class="py-8 text-slate-500">No results.</li>
      {% endfor %}
    </ul>
    {% if next_page %}
      {% set q=q %}
      {% set embed=embed %}
      {% include 'partials/scroll_sentinel.html' with context %}
    {% endif %}
  {% endif %}
</div>
{% endblock %}
HTML

# Update scroll sentinel to preserve embed param too
b templates/partials/scroll_sentinel.html
cat > templates/partials/scroll_sentinel.html <<'HTML'
<div class="mt-4 h-10 flex items-center justify-center" 
     hx-get="/notes?page={{ next_page }}{% if tag %}&tag={{ tag }}{% endif %}{% if q %}/search?q={{ q | urlencode }}{% if embed %}&embed=1{% endif %}{% endif %}"
     hx-trigger="revealed once"
     hx-target="#notes-list"
     hx-swap="beforeend">
  <div class="animate-pulse text-white/70">Loading…</div>
</div>
HTML

# Export page
b templates/export.html
cat > templates/export.html <<'HTML'
{% extends "base.html" %}
{% block title %}Export — Second Brain Premium{% endblock %}
{% block content %}
<div class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Export</h1>
  <p class="text-sm text-slate-500 mt-1">Download all your notes with tags. JSON for interoperability, Markdown ZIP for vaults like Obsidian.</p>

  <div class="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
    <section class="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 class="font-medium text-slate-900 dark:text-white">JSON export</h2>
      <p class="text-sm text-slate-500">Single file with <code>notes[id, body, created_at, tags[]]</code>.</p>
      <a href="/export/json" class="inline-block mt-3 px-3 py-1.5 rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900">Download JSON</a>
    </section>
    <section class="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 class="font-medium text-slate-900 dark:text-white">Markdown ZIP</h2>
      <p class="text-sm text-slate-500">Each note as <code>.md</code> with YAML front-matter.</p>
      <a href="/export/markdown.zip" class="inline-block mt-3 px-3 py-1.5 rounded-lg bg-brand-600 text-white">Download ZIP</a>
    </section>
  </div>

  <div class="mt-6 text-sm text-slate-500">Notes: <b>{{ total }}</b> • Tags: <b>{{ tags }}</b></div>
</div>
{% endblock %}
HTML

# Add Export to nav if not present
if grep -q "<li><a .*href=\"/settings\"" templates/base.html 2>/dev/null; then
  b templates/base.html
  awk '1; /href="\/settings"/ && !x {print "        <li><a class=\"hover:text-slate-900 dark:hover:text-white\" href=\"/export\">Export</a></li>"; x=1}' templates/base.html.$STAMP.bak > templates/base.html
fi

# =========================== requirements ===========================
# Add python-multipart if not present (FastAPI forms need it in some envs)
if [[ ! -f requirements.txt ]]; then
  cat > requirements.txt <<'REQ'
fastapi==0.115.0
uvicorn[standard]==0.30.6
jinja2==3.1.4
httpx==0.27.2
numpy>=1.24,<3
python-multipart==0.0.9
REQ
else
  grep -q "python-multipart" requirements.txt || echo "python-multipart==0.0.9" >> requirements.txt
  grep -q "numpy" requirements.txt || echo "numpy>=1.24,<3" >> requirements.txt
fi

echo "Done.

What changed:
  • Semantic search toggle on /search (use ?embed=1)
  • JSON export:  /export/json
  • Markdown ZIP: /export/markdown.zip
  • Export page:  /export (linked in nav)

Run:
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  uvicorn app:app --reload --host 0.0.0.0 --port 8084
"
