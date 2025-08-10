#!/usr/bin/env bash
# scaffold-006.sh
set -euo pipefail
STAMP="$(date +%Y%m%d-%H%M%S)"
b(){ [[ -f "$1" ]] && mv "$1" "$1.$STAMP.bak" && echo "• backup: $1 -> $1.$STAMP.bak" || true; }

mkdir -p templates/partials static

# =========================== app.py ===========================
b app.py
cat > app.py <<'PY'
from datetime import datetime
from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pathlib, sqlite3, os, re, httpx, json, math
from collections import Counter
try:
    import numpy as np
except Exception:
    np = None  # we'll gracefully fallback if numpy unavailable

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

-- Embeddings store: one row per note
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

# ---------------- settings helpers ----------------
def get_setting(conn, key: str, default: str | None = None):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return (r["value"] if r else None) or default

def put_setting(conn, key: str, value: str):
    conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()

# ---------------- embeddings ----------------
EMBED_BASE_ENV  = os.getenv("OLLAMA_EMBED_BASE_URL")
EMBED_MODEL_ENV = os.getenv("OLLAMA_EMBED_MODEL")

def _vec_to_blob(vec):
    # store float32 bytes
    if np is None:
        # fallback: store comma-separated text
        return (",".join(f"{float(x):.7f}" for x in vec)).encode("utf-8")
    arr = np.asarray(vec, dtype=np.float32)
    return arr.tobytes()

def _blob_to_vec(blob, dim_hint=None):
    if np is None:
        # parse text fallback
        s = blob.decode("utf-8")
        return [float(x) for x in s.split(",") if x]
    arr = np.frombuffer(blob, dtype=np.float32)
    if dim_hint and arr.size != dim_hint:
        # corrupted or changed model; ignore
        return arr.astype(np.float32)
    return arr.astype(np.float32)

def embed_text(text: str, base: str, model: str) -> list[float]:
    # Ollama /api/embeddings
    payload = {"model": model, "prompt": text}
    r = httpx.post(f"{base}/api/embeddings", json=payload, timeout=30.0)
    r.raise_for_status()
    data = r.json()
    vec = data.get("embedding") or data.get("data", [{}])[0].get("embedding")
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
        dim = len(vec)
        conn.execute("INSERT INTO note_embeddings(note_id, dim, vec) VALUES (?,?,?) ON CONFLICT(note_id) DO UPDATE SET dim=excluded.dim, vec=excluded.vec",
                     (note_id, dim, _vec_to_blob(vec)))
        conn.commit()
    except Exception as e:
        # swallow embedding errors so UX still flows
        print("Embedding error:", e)

def cosine(a, b):
    if np is not None:
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0: return 0.0
        return float(np.dot(a, b) / denom)
    # python fallback
    dot = sum(x*y for x,y in zip(a,b))
    na  = math.sqrt(sum(x*x for x in a))
    nb  = math.sqrt(sum(y*y for y in b))
    if na == 0 or nb == 0: return 0.0
    return dot / (na * nb)

def related_notes_semantic(conn, note_id: int, limit: int = 6):
    # need current note embedding
    row = conn.execute("SELECT e.dim, e.vec FROM note_embeddings e WHERE e.note_id=?", (note_id,)).fetchone()
    if not row: return []
    dim = row["dim"]; qvec = _blob_to_vec(row["vec"], dim_hint=dim)
    others = conn.execute("SELECT note_id, dim, vec FROM note_embeddings WHERE note_id != ?", (note_id,)).fetchall()
    if not others: return []
    scored = []
    for r in others:
        if r["dim"] != dim:  # skip mismatched dims (model changed mid-run)
            continue
        vec = _blob_to_vec(r["vec"], dim_hint=dim)
        s = cosine(qvec, vec)
        scored.append((r["note_id"], s))
    scored.sort(key=lambda x: x[1], reverse=True)
    top_ids = [i for (i, _) in scored[:limit]]
    if not top_ids: return []
    q = f"SELECT id, body, created_at FROM notes WHERE id IN ({','.join('?'*len(top_ids))})"
    rows = conn.execute(q, top_ids).fetchall()
    # preserve order of similarity
    order = {nid:i for i,nid in enumerate(top_ids)}
    rows.sort(key=lambda r: order[r["id"]])
    return rows

# ---------------- pages ----------------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"]
    recent = conn.execute("SELECT id, body, created_at FROM notes ORDER BY datetime(created_at) DESC LIMIT 5").fetchall()
    tagmap = map_note_tags(conn, recent)
    recent_list = [dict(r) | {"tags": tagmap.get(r["id"], "")} for r in recent]
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": {"notes": total}, "recent": recent_list})

# Notes (paged)
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

# Note detail + related (semantic -> tag overlap -> FTS)
@app.get("/notes/{note_id}", response_class=HTMLResponse)
def note_detail(request: Request, note_id: int):
    conn = get_conn()
    r = conn.execute("SELECT id, body, created_at FROM notes WHERE id=?", (note_id,)).fetchone()
    if not r: return RedirectResponse("/", status_code=302)
    note = dict(r) | {"tags": map_note_tags(conn, [r]).get(r["id"], "")}

    related_rows = related_notes_semantic(conn, note_id, limit=6)
    if not related_rows:
        # fallback: tag-overlap
        related_rows = conn.execute("""
          WITH note_tags_set AS (
            SELECT t.id AS tag_id FROM note_tags nt JOIN tags t ON t.id=nt.tag_id WHERE nt.note_id=?
          )
          SELECT n.id, n.body, n.created_at, COUNT(*) AS overlap
          FROM notes n
          JOIN note_tags nt ON nt.note_id = n.id
          WHERE n.id != ? AND nt.tag_id IN (SELECT tag_id FROM note_tags_set)
          GROUP BY n.id
          ORDER BY overlap DESC, datetime(n.created_at) DESC
          LIMIT 6
        """, (note_id, note_id)).fetchall()

    rel_tagmap = map_note_tags(conn, related_rows)
    related = [dict(x) | {"tags": rel_tagmap.get(x["id"], "")} for x in related_rows]
    return templates.TemplateResponse("note_detail.html", {"request": request, "note": note, "related": related})

# Inline edit
@app.get("/notes/{note_id}/edit", response_class=HTMLResponse)
def note_edit_partial(request: Request, note_id: int):
    conn = get_conn()
    r = conn.execute("SELECT id, body, created_at FROM notes WHERE id=?", (note_id,)).fetchone()
    if not r: return HTMLResponse("")
    note = dict(r) | {"tags": map_note_tags(conn, [r]).get(r["id"], "")}
    return templates.TemplateResponse("partials/note_edit_form.html", {"request": request, "note": note})

@app.post("/notes/{note_id}/update", response_class=HTMLResponse)
def note_update(request: Request, note_id: int, body: str = Form(...), tags: str = Form("")):
    conn = get_conn()
    conn.execute("UPDATE notes SET body=? WHERE id=?", (body, note_id))
    set_note_tags(conn, note_id, parse_tags(tags))
    conn.commit()
    # update embedding (best-effort)
    ensure_embedding_for_note(conn, note_id, body)
    r = conn.execute("SELECT id, body, created_at FROM notes WHERE id=?", (note_id,)).fetchone()
    note = dict(r) | {"tags": map_note_tags(conn, [r]).get(r["id"], "")}
    headers = {"HX-Trigger": json.dumps(hx_trigger_dict("toast", {"type":"success","message":"Note updated"}))}
    return templates.TemplateResponse("partials/note_view.html", {"request": request, "note": note}, headers=headers)

@app.post("/notes/{note_id}/delete", response_class=RedirectResponse)
def note_delete(note_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit()
    return RedirectResponse("/notes", status_code=303)

# Create note + embedding
@app.post("/notes", response_class=HTMLResponse)
def create_note(request: Request, body: str = Form(...), tags: str = Form("")):
    conn = get_conn()
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur = conn.execute("INSERT INTO notes(body, created_at) VALUES (?,?)", (body, now))
    nid = cur.lastrowid
    set_note_tags(conn, nid, parse_tags(tags))
    conn.commit()
    # embed (best-effort)
    ensure_embedding_for_note(conn, nid, body)
    if request.headers.get("HX-Request"):
        row = conn.execute("SELECT id, body, created_at FROM notes WHERE id=?", (nid,)).fetchone()
        note = dict(row) | {"tags": map_note_tags(conn, [row]).get(nid, "")}
        headers = {"HX-Trigger": json.dumps(hx_trigger_dict("toast", {"type":"success","message":"Note saved"}))}
        return templates.TemplateResponse("partials/note_item.html", {"request": request, "n": note}, headers=headers)
    return RedirectResponse(f"/notes/{nid}", status_code=303)

# Batch actions (unchanged)
@app.post("/notes/batch", response_class=HTMLResponse)
def notes_batch(request: Request, action: str = Form(...), ids: str = Form(...), tag: str = Form("")):
    conn = get_conn()
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not id_list:
        return Response(status_code=204, headers={"HX-Trigger": json.dumps(hx_trigger_dict("toast", {"type":"info","message":"No notes selected"}))})
    if action == "delete":
        conn.executemany("DELETE FROM notes WHERE id=?", [(i,) for i in id_list])
    elif action == "add_tag":
        nm = norm_tag(tag); 
        if nm:
            tid = ensure_tag(conn, nm)
            conn.executemany("INSERT OR IGNORE INTO note_tags(note_id, tag_id) VALUES (?,?)", [(i, tid) for i in id_list])
    elif action == "remove_tag":
        nm = norm_tag(tag)
        if nm:
            row = conn.execute("SELECT id FROM tags WHERE name=?", (nm,)).fetchone()
            if row:
                conn.executemany("DELETE FROM note_tags WHERE note_id=? AND tag_id=?", [(i, row["id"]) for i in id_list])
    conn.commit()
    headers = {"HX-Trigger": json.dumps(hx_trigger_dict("toast", {"type":"success","message":"Batch action completed"}))}
    return Response(status_code=204, headers=headers)

# Search (paged)
@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = "", page: int = 1):
    conn = get_conn()
    items = []; total = 0
    if q:
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
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/note_page.html", {"request": request, "notes": notes, "q": q, "next_page": (page+1) if has_more else None})
    return templates.TemplateResponse("search.html", {"request": request, "q": q, "notes": notes, "next_page": (2 if has_more else None)})

# Quick search overlay partial
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

# Tag APIs: suggest (LLM) & autocomplete (DB)
STOPWORDS = set("a an and the i you he she it we they to of for in on with from this that these those be is are was were am will would can could should as at by not or if into over under about after before during up down out very just".split())
def naive_tags(text: str, k: int = 6):
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{3,}", text.lower())
    words = [w for w in words if w not in STOPWORDS]
    cnt = Counter(words)
    return [w for w,_ in cnt.most_common(k)]

@app.post("/tags/suggest")
def suggest_tags(payload: dict = Body(...)):
    text = (payload.get("text") or "").strip()
    if len(text) < 8: return JSONResponse({"tags": []})
    conn = get_conn()
    base = get_setting(conn, "OLLAMA_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    model = get_setting(conn, "OLLAMA_MODEL", os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
    prompt = ("You are a tagging assistant. From the note, extract 3-7 short tags.\n"
              "- lowercase\n- hyphen for multiword\n- no '#'\n- comma-separated only\n\nNote:\n" + text + "\nTags:")
    try:
        r = httpx.post(f"{base}/api/generate", json={"model": model, "prompt": prompt, "stream": False}, timeout=10.0)
        r.raise_for_status()
        resp = r.json().get("response","")
        tags = [norm_tag(t) for t in resp.split(",")]
        tags = [t for t in tags if t] or naive_tags(text)
    except Exception:
        tags = naive_tags(text)
    return {"tags": list(dict.fromkeys(tags))[:7]}

@app.get("/api/tags")
def tags_autocomplete(q: str = ""):
    conn = get_conn()
    qn = norm_tag(q)
    if qn:
        rows = conn.execute("""
          SELECT t.name, COUNT(nt.note_id) usage
          FROM tags t LEFT JOIN note_tags nt ON nt.tag_id=t.id
          WHERE t.name LIKE ? || '%'
          GROUP BY t.id
          ORDER BY usage DESC, t.name ASC
          LIMIT 10
        """, (qn,)).fetchall()
    else:
        rows = conn.execute("""
          SELECT t.name, COUNT(nt.note_id) usage
          FROM tags t LEFT JOIN note_tags nt ON nt.tag_id=t.id
          GROUP BY t.id ORDER BY usage DESC, t.name ASC LIMIT 10
        """).fetchall()
    return {"tags": [r["name"] for r in rows]}

# Settings + Embeddings admin
@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    conn = get_conn()
    ctx = {
        "base": get_setting(conn, "OLLAMA_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")),
        "model": get_setting(conn, "OLLAMA_MODEL", os.getenv("OLLAMA_MODEL", "llama3.1:8b")),
        "emb_base": get_setting(conn, "OLLAMA_EMBED_BASE_URL", EMBED_BASE_ENV or "http://localhost:11434"),
        "emb_model": get_setting(conn, "OLLAMA_EMBED_MODEL", EMBED_MODEL_ENV or "nomic-embed-text:latest"),
    }
    return templates.TemplateResponse("settings.html", {"request": request, **ctx})

@app.post("/settings/ollama", response_class=RedirectResponse)
def settings_ollama(base: str = Form(""), model: str = Form(""), emb_base: str = Form(""), emb_model: str = Form("")):
    conn = get_conn()
    put_setting(conn, "OLLAMA_BASE_URL", base.strip() or "http://localhost:11434")
    put_setting(conn, "OLLAMA_MODEL", model.strip() or "llama3.1:8b")
    put_setting(conn, "OLLAMA_EMBED_BASE_URL", emb_base.strip() or "http://localhost:11434")
    put_setting(conn, "OLLAMA_EMBED_MODEL", emb_model.strip() or "nomic-embed-text:latest")
    return RedirectResponse("/settings?ok=1", status_code=303)

@app.get("/embeddings", response_class=HTMLResponse)
def embeddings_admin(request: Request):
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"]
    embedded = conn.execute("SELECT COUNT(*) c FROM note_embeddings").fetchone()["c"]
    missing = total - embedded
    return templates.TemplateResponse("embeddings.html", {"request": request, "total": total, "embedded": embedded, "missing": missing})

@app.post("/embeddings/rebuild", response_class=HTMLResponse)
def embeddings_rebuild(request: Request, limit: int = Form(100), force: int = Form(0)):
    conn = get_conn()
    base = get_setting(conn, "OLLAMA_EMBED_BASE_URL", EMBED_BASE_ENV or "http://localhost:11434")
    model = get_setting(conn, "OLLAMA_EMBED_MODEL", EMBED_MODEL_ENV or "nomic-embed-text:latest")
    if force:
        rows = conn.execute("SELECT id, body FROM notes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    else:
        rows = conn.execute("""
          SELECT n.id, n.body
          FROM notes n
          LEFT JOIN note_embeddings e ON e.note_id = n.id
          WHERE e.note_id IS NULL
          ORDER BY n.id DESC LIMIT ?
        """, (limit,)).fetchall()
    done = 0; errors = 0
    for r in rows:
        try:
            vec = embed_text(r["body"], base, model)
            conn.execute("INSERT INTO note_embeddings(note_id, dim, vec) VALUES (?,?,?) ON CONFLICT(note_id) DO UPDATE SET dim=excluded.dim, vec=excluded.vec",
                         (r["id"], len(vec), _vec_to_blob(vec)))
            done += 1
        except Exception:
            errors += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"]
    embedded = conn.execute("SELECT COUNT(*) c FROM note_embeddings").fetchone()["c"]
    missing = total - embedded
    return templates.TemplateResponse("partials/emb_progress.html",
        {"request": request, "total": total, "embedded": embedded, "missing": missing, "just_done": done, "errors": errors})

# Health ping for embed base/model
@app.post("/settings/ollama/test")
def settings_ollama_test(base: str = Form(""), model: str = Form("")):
    base = base.strip() or "http://localhost:11434"
    model = model.strip() or "llama3.1:8b"
    try:
        r = httpx.get(f"{base}/api/tags", timeout=3.0)  # will 404; check reachability
        ok = True
        lat = int(r.elapsed.total_seconds()*1000)
    except Exception:
        ok = False; lat = None
    return JSONResponse({"ok": ok, "latency_ms": lat})
PY

# =========================== templates: Settings + Embeddings ===========================
b templates/settings.html
cat > templates/settings.html <<'HTML'
{% extends "base.html" %}
{% block title %}Settings — Second Brain Premium{% endblock %}
{% block content %}
<div class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Settings</h1>

  <form class="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4" method="post" action="/settings/ollama">
    <div class="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 class="font-medium">Chat/Summarization Model</h2>
      <label class="block mt-2 text-sm">Base URL</label>
      <input name="base" value="{{ base }}" class="w-full rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5">
      <label class="block mt-3 text-sm">Model</label>
      <input name="model" value="{{ model }}" class="w-full rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5">
    </div>

    <div class="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 class="font-medium">Embeddings (Semantic Related Notes)</h2>
      <label class="block mt-2 text-sm">Embed Base URL</label>
      <input name="emb_base" value="{{ emb_base }}" class="w-full rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5">
      <label class="block mt-3 text-sm">Embed Model</label>
      <input name="emb_model" value="{{ emb_model }}" class="w-full rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5">
      <p class="text-xs text-slate-500 mt-2">Recommended: <code>nomic-embed-text:latest</code>, <code>mxbai-embed-large:latest</code>, or <code>jina-embeddings-v2:base-en</code> (if available locally).</p>
      <div class="mt-3">
        <a href="/embeddings" class="px-3 py-1.5 rounded-xl bg-slate-900 text-white dark:bg-white dark:text-slate-900">Open Embeddings Admin</a>
        <button formaction="/settings/ollama/test" formmethod="post"
                class="px-3 py-1.5 rounded-xl bg-brand-600 text-white">Test Reachability</button>
      </div>
    </div>

    <div class="md:col-span-2 text-sm text-slate-500">Settings are saved in the SQLite <code>settings</code> table.</div>
    <div class="md:col-span-2">
      <button class="px-4 py-2 rounded-xl bg-brand-600 text-white">Save Settings</button>
    </div>
  </form>
</div>
{% endblock %}
HTML

cat > templates/embeddings.html <<'HTML'
{% extends "base.html" %}
{% block title %}Embeddings Admin — Second Brain Premium{% endblock %}
{% block content %}
<div class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Embeddings Admin</h1>
  <p class="text-sm text-slate-500 mt-1">Compute or rebuild local embeddings for better “Related notes.” Safe to run in chunks.</p>

  <div id="emb-status" hx-post="/embeddings/rebuild" hx-vals='{"limit": 0, "force": 0}' hx-swap="outerHTML" hx-trigger="load">
    {% include "partials/emb_progress.html" %}
  </div>

  <div class="mt-4 flex flex-wrap gap-2">
    <form hx-post="/embeddings/rebuild" hx-target="#emb-status" hx-swap="outerHTML">
      <input type="hidden" name="limit" value="100">
      <input type="hidden" name="force" value="0">
      <button class="px-3 py-1.5 rounded-lg bg-brand-600 text-white">Process next 100 missing</button>
    </form>
    <form hx-post="/embeddings/rebuild" hx-target="#emb-status" hx-swap="outerHTML" onsubmit="return confirm('Recompute for ALL notes (slow)?');">
      <input type="hidden" name="limit" value="200">
      <input type="hidden" name="force" value="1">
      <button class="px-3 py-1.5 rounded-lg bg-rose-600 text-white">Rebuild 200 (force)</button>
    </form>
  </div>
</div>
{% endblock %}
HTML

cat > templates/partials/emb_progress.html <<'HTML'
<div class="rounded-xl border border-slate-200 dark:border-slate-800 p-4 bg-white/70 dark:bg-slate-900/70">
  <div class="grid grid-cols-3 gap-4 text-center">
    <div><div class="text-xs text-slate-500">Total notes</div><div class="text-xl font-semibold">{{ total }}</div></div>
    <div><div class="text-xs text-slate-500">Embedded</div><div class="text-xl font-semibold">{{ embedded }}</div></div>
    <div><div class="text-xs text-slate-500">Missing</div><div class="text-xl font-semibold">{{ missing }}</div></div>
  </div>
  {% if just_done is defined %}
    <div class="mt-3 text-sm text-slate-600 dark:text-slate-300">{{ just_done }} processed{% if errors %}, {{ errors }} errors{% endif %}.</div>
  {% endif %}
</div>
HTML

# =========================== requirements ===========================
# numpy optional but recommended for speed
if [[ ! -f requirements.txt ]]; then
  cat > requirements.txt <<'REQ'
fastapi==0.115.0
uvicorn[standard]==0.30.6
jinja2==3.1.4
httpx==0.27.2
numpy>=1.24,<3
REQ
else
  if ! grep -q numpy requirements.txt; then
    echo "numpy>=1.24,<3" >> requirements.txt
  fi
fi

echo "Done.

Next steps:
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  # (optional) export OLLAMA_EMBED_BASE_URL and OLLAMA_EMBED_MODEL; otherwise set in Settings
  uvicorn app:app --reload --host 0.0.0.0 --port 8084

Use: Settings → Embeddings → 'Open Embeddings Admin' to process batches.
Related notes now prioritize semantic similarity (falls back to tags/FTS if unavailable).
"
