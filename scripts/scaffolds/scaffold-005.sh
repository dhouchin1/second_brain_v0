#!/usr/bin/env bash
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
import pathlib, sqlite3, os, re, httpx, json
from collections import Counter

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

def title_from_body(body: str) -> str:
    """First non-empty line, trimmed to 80 chars."""
    for line in (body or "").splitlines():
        t = line.strip()
        if t:
            return (t[:80] + "…") if len(t) > 80 else t
    return "Untitled"

def related_notes(conn, note_id: int, limit: int = 6):
    # tag-overlap first
    rows = conn.execute("""
      WITH note_tags_set AS (
        SELECT t.id AS tag_id FROM note_tags nt JOIN tags t ON t.id=nt.tag_id WHERE nt.note_id=?
      )
      SELECT n.id, n.body, n.created_at, COUNT(*) AS overlap
      FROM notes n
      JOIN note_tags nt ON nt.note_id = n.id
      WHERE n.id != ? AND nt.tag_id IN (SELECT tag_id FROM note_tags_set)
      GROUP BY n.id
      ORDER BY overlap DESC, datetime(n.created_at) DESC
      LIMIT ?
    """, (note_id, note_id, limit)).fetchall()
    if rows:
        return rows
    # FTS fallback: use body of note as query
    q = conn.execute("SELECT body FROM notes WHERE id=?", (note_id,)).fetchone()
    if not q: return []
    return conn.execute("""
      SELECT n.id, n.body, n.created_at
      FROM notes_fts f JOIN notes n ON n.id=f.rowid
      WHERE n.id != ? AND notes_fts MATCH ?
      ORDER BY bm25(notes_fts) LIMIT ?
    """, (note_id, q["body"][:200], limit)).fetchall()

def hx_trigger_dict(event: str, payload: dict) -> dict:
    return {event: payload}

# ---------------- pages ----------------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"]
    recent = conn.execute("SELECT id, body, created_at FROM notes ORDER BY datetime(created_at) DESC LIMIT 5").fetchall()
    tagmap = map_note_tags(conn, recent)
    recent_list = [dict(r) | {"tags": tagmap.get(r["id"], "")} for r in recent]
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": {"notes": total}, "recent": recent_list})

# Notes (paged, full & partial)
@app.get("/notes", response_class=HTMLResponse)
def notes_page(request: Request, tag: str = "", page: int = 1):
    conn = get_conn()
    base_sql = "FROM notes n"
    where = ""
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

# Note detail + inline edit
@app.get("/notes/{note_id}", response_class=HTMLResponse)
def note_detail(request: Request, note_id: int):
    conn = get_conn()
    r = conn.execute("SELECT id, body, created_at FROM notes WHERE id=?", (note_id,)).fetchone()
    if not r: return RedirectResponse("/", status_code=302)
    note = dict(r) | {"tags": map_note_tags(conn, [r]).get(r["id"], "")}
    rel = related_notes(conn, note_id)
    rel_tagmap = map_note_tags(conn, rel)
    related = [dict(x) | {"tags": rel_tagmap.get(x["id"], "")} for x in rel]
    return templates.TemplateResponse("note_detail.html", {"request": request, "note": note, "related": related})

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

# Quick create (dashboard) with toast
@app.post("/notes", response_class=HTMLResponse)
def create_note(request: Request, body: str = Form(...), tags: str = Form("")):
    conn = get_conn()
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur = conn.execute("INSERT INTO notes(body, created_at) VALUES (?,?)", (body, now))
    nid = cur.lastrowid
    set_note_tags(conn, nid, parse_tags(tags))
    conn.commit()
    if request.headers.get("HX-Request"):
        row = conn.execute("SELECT id, body, created_at FROM notes WHERE id=?", (nid,)).fetchone()
        note = dict(row) | {"tags": map_note_tags(conn, [row]).get(nid, "")}
        headers = {"HX-Trigger": json.dumps(hx_trigger_dict("toast", {"type":"success","message":"Note saved"}))}
        return templates.TemplateResponse("partials/note_item.html", {"request": request, "n": note}, headers=headers)
    return RedirectResponse(f"/notes/{nid}", status_code=303)

# Batch actions
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
    items = []
    total = 0
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
OLLAMA_BASE_ENV = os.getenv("OLLAMA_BASE_URL")
OLLAMA_MODEL_ENV = os.getenv("OLLAMA_MODEL")

def get_setting(conn, key: str, default: str | None = None):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return (r["value"] if r else None) or default

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
    base = OLLAMA_BASE_ENV or get_setting(conn, "OLLAMA_BASE_URL", "http://localhost:11434")
    model = OLLAMA_MODEL_ENV or get_setting(conn, "OLLAMA_MODEL", "llama3.1:8b")
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

# Settings
@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    conn = get_conn()
    ctx = {
        "base": get_setting(conn, "OLLAMA_BASE_URL", OLLAMA_BASE_ENV or "http://localhost:11434"),
        "model": get_setting(conn, "OLLAMA_MODEL", OLLAMA_MODEL_ENV or "llama3.1:8b")
    }
    return templates.TemplateResponse("settings.html", {"request": request, **ctx})

@app.post("/settings/ollama", response_class=RedirectResponse)
def settings_ollama(base: str = Form(""), model: str = Form("")):
    conn = get_conn()
    base = base.strip() or "http://localhost:11434"
    model = model.strip() or "llama3.1:8b"
    conn.execute("INSERT INTO settings(key,value) VALUES('OLLAMA_BASE_URL',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (base,))
    conn.execute("INSERT INTO settings(key,value) VALUES('OLLAMA_MODEL',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (model,))
    conn.commit()
    return RedirectResponse("/settings?ok=1", status_code=303)

@app.post("/settings/ollama/test")
def settings_ollama_test(base: str = Form(""), model: str = Form("")):
    base = base.strip() or "http://localhost:11434"
    model = model.strip() or "llama3.1:8b"
    try:
        r = httpx.post(f"{base}/api/tags", timeout=3.0)  # will 404; just to measure reachability quickly
    except Exception:
        return JSONResponse({"ok": False, "latency_ms": None})
    return JSONResponse({"ok": True, "latency_ms": int(r.elapsed.total_seconds()*1000)})
PY

# =========================== base.html ===========================
b templates/base.html
cat > templates/base.html <<'HTML'
<!doctype html>
<html lang="en" x-data
      x-init="document.documentElement.classList.toggle('dark', localStorage.theme === 'dark')"
      class="scroll-smooth">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{% block title %}Second Brain Premium{% endblock %}</title>

  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: { sans: ['Inter','ui-sans-serif','system-ui','Arial'] },
          colors: { brand: {50:'#eef2ff',500:'#6366f1',600:'#4f46e5',700:'#4338ca'} }
        }
      },
      darkMode: 'class'
    }
  </script>
  <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">

  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>

  <link rel="icon" href="data:,">
</head>

<body class="font-sans min-h-screen bg-gradient-to-br from-indigo-500 via-fuchsia-500 to-purple-600
             dark:from-slate-950 dark:via-slate-950 dark:to-zinc-900">
  <header class="sticky top-0 z-40 bg-white/70 dark:bg-slate-900/70 backdrop-blur border-b border-white/10">
    <nav class="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between">
      <a href="/" class="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100">
        <span class="text-2xl">🧠</span><span>Second Brain Premium</span>
      </a>
      <ul class="flex items-center gap-4 text-slate-700 dark:text-slate-300">
        <li><a class="hover:text-slate-900 dark:hover:text-white" href="/">Dashboard</a></li>
        <li><a class="hover:text-slate-900 dark:hover:text-white" href="/notes">Notes</a></li>
        <li><a class="hover:text-slate-900 dark:hover:text-white" href="/search">Search</a></li>
        <li><a class="hover:text-slate-900 dark:hover:text-white" href="/tags">Tags</a></li>
        <li><a class="hover:text-slate-900 dark:hover:text-white" href="/settings">Settings</a></li>
        <li><button id="themeToggle" class="rounded-xl px-3 py-1.5 bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm">Toggle Theme</button></li>
      </ul>
    </nav>
  </header>

  <main class="mx-auto max-w-6xl px-4 py-8">
    {% block content %}{% endblock %}
  </main>

  <footer class="mx-auto max-w-6xl px-4 pb-10 text-sm text-white/80">
    <div class="mt-8 text-center">FastAPI • Jinja • Tailwind • HTMX • SQLite FTS5 • Ollama</div>
  </footer>

  <!-- Quick Search Overlay -->
  <div id="qmask" class="hidden fixed inset-0 z-50 bg-black/50" role="presentation"></div>
  <section id="qwrap" class="hidden fixed left-1/2 top-24 -translate-x-1/2 z-50 w-[min(800px,94vw)]" aria-modal="true" role="dialog" aria-labelledby="qinput">
    <div class="rounded-2xl overflow-hidden shadow-2xl ring-1 ring-black/10">
      <div class="p-3 bg-white dark:bg-slate-950 border-b border-black/10 dark:border-white/10">
        <input id="qinput" type="text" placeholder="Search…" aria-label="Quick search input"
               class="w-full bg-transparent outline-none px-2 py-2 text-slate-900 dark:text-white" />
        <div class="text-xs text-slate-500 mt-1">Press Esc to close</div>
      </div>
      <div id="qresults" class="max-h-[60vh] overflow-y-auto bg-white/95 dark:bg-slate-950/90"
           hx-get="/api/q" hx-trigger="keyup changed delay:300ms from:#qinput"
           hx-target="#qresults" hx-include="#qinput" hx-vals='js:{q: document.getElementById("qinput").value}'></div>
    </div>
  </section>

  <!-- Toasts (Alpine store) -->
  <div x-data="ToastStack" class="fixed bottom-4 right-4 z-[60] space-y-2" aria-live="polite"></div>

  <!-- Shortcuts Help -->
  <div id="helpMask" class="hidden fixed inset-0 z-50 bg-black/50"></div>
  <section id="helpSheet" class="hidden fixed left-1/2 top-24 -translate-x-1/2 z-50 w-[min(720px,94vw)]">
    <div class="rounded-2xl overflow-hidden shadow-2xl ring-1 ring-black/10 bg-white dark:bg-slate-950">
      <div class="p-4 border-b border-black/10 dark:border-white/10 flex items-center justify-between">
        <h2 class="font-semibold">Keyboard Shortcuts</h2>
        <button id="helpClose" class="px-3 py-1.5 rounded-lg bg-slate-200 dark:bg-slate-800">Close</button>
      </div>
      <div class="p-4 text-sm text-slate-700 dark:text-slate-300 grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div><b>⌘/Ctrl + /</b> — Quick Search</div>
        <div><b>?</b> — This help</div>
        <div><b>e</b> — Edit on Note page</div>
        <div><b>⌘/Ctrl + s</b> — Save note (when editing)</div>
        <div><b>↑/↓ + Enter</b> — Pick tag autocomplete</div>
      </div>
    </div>
  </section>

  <script src="/static/app.js"></script>
</body>
</html>
HTML

# =========================== notes.html + partials ===========================
b templates/notes.html
cat > templates/notes.html <<'HTML'
{% extends "base.html" %}
{% block title %}All Notes — Second Brain Premium{% endblock %}
{% block content %}
<div class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
    <h1 class="text-xl font-semibold text-slate-900 dark:text-white">All Notes</h1>
    <form method="get" action="/notes" class="flex gap-2">
      <input name="tag" value="{{ active_tag or '' }}" placeholder="Filter by tag"
             class="rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5">
      <button class="px-3 py-1.5 rounded-xl bg-slate-900 text-white dark:bg-white dark:text-slate-900">Filter</button>
    </form>
  </div>

  <!-- Batch actions -->
  <form id="batchForm" class="mt-4 flex flex-wrap items-center gap-2" hx-post="/notes/batch" hx-vals='js:{ids: window.selectedNotes.join(",")}'
        hx-swap="none">
    <select name="action" class="rounded-lg border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5">
      <option value="add_tag">Add tag</option>
      <option value="remove_tag">Remove tag</option>
      <option value="delete">Delete</option>
    </select>
    <input name="tag" placeholder="tag (for add/remove)" class="rounded-lg border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5">
    <button class="px-3 py-1.5 rounded-lg bg-brand-600 text-white">Run</button>
  </form>

  <ul id="notes-list" class="mt-4 divide-y divide-slate-200/80 dark:divide-white/10">
    {% for n in notes %}
      {% include 'partials/note_row_selectable.html' %}
    {% else %}
      <li class="py-8 text-slate-500">No notes found.</li>
    {% endfor %}
  </ul>

  {% if next_page %}
    {% include 'partials/scroll_sentinel.html' with context %}
  {% endif %}
</div>
<script>window.selectedNotes = [];</script>
HTML

# list page chunk + sentinel
cat > templates/partials/note_page.html <<'HTML'
{% for n in notes %}
  {% include 'partials/note_row_selectable.html' %}
{% endfor %}
{% if next_page %}
  {% include 'partials/scroll_sentinel.html' with context %}
{% endif %}
HTML

cat > templates/partials/note_row_selectable.html <<'HTML'
<li class="py-4 flex items-start gap-4">
  <input type="checkbox" class="mt-1" aria-label="Select note {{ n.id }}"
         onchange="(this.checked ? window.selectedNotes.push({{ n.id }}) : window.selectedNotes = window.selectedNotes.filter(x=>x!=={{ n.id }}))">
  <div class="flex-1">
    <a href="/notes/{{ n.id }}" class="block text-slate-900 dark:text-white font-medium hover:underline">
      {{ (n.body[:140] ~ ('…' if n.body|length > 140 else '')) | e }}
    </a>
    <div class="mt-1 text-xs text-slate-500">
      {{ n.created_at }}
      {% if n.tags %}
        •
        {% for t in n.tags.split(',') if t.strip() %}
          <a href="/notes?tag={{ t.strip() }}"
             class="inline-block ml-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700">#{{ t.strip() }}</a>
        {% endfor %}
      {% endif %}
    </div>
  </div>
</li>
HTML

cat > templates/partials/scroll_sentinel.html <<'HTML'
<div class="mt-4 h-10 flex items-center justify-center" 
     hx-get="/notes?page={{ next_page }}{% if tag %}&tag={{ tag }}{% endif %}{% if q %}&q={{ q }}{% endif %}"
     hx-trigger="revealed once"
     hx-target="#notes-list"
     hx-swap="beforeend">
  <div class="animate-pulse text-white/70">Loading…</div>
</div>
HTML

# =========================== note detail (related + editing) ===========================
b templates/note_detail.html
cat > templates/note_detail.html <<'HTML'
{% extends "base.html" %}
{% block title %}{{ (note.body.splitlines()[0] or ('Note #' ~ note.id)) | e }} — Second Brain Premium{% endblock %}
{% block content %}
<div class="grid grid-cols-1 lg:grid-cols-3 gap-6" id="note-view">
  <div class="lg:col-span-2">
    {% include "partials/note_view.html" %}
  </div>
  <aside class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
    <h2 class="text-lg font-semibold text-slate-900 dark:text-white">Related</h2>
    <ul class="mt-3 divide-y divide-slate-200/80 dark:divide-white/10">
      {% for r in related %}
        <li class="py-3">
          <a href="/notes/{{ r.id }}" class="font-medium text-slate-900 dark:text-white hover:underline">
            {{ (r.body.splitlines()[0] or ('Note #' ~ r.id)) | e }}
          </a>
          <div class="mt-1 text-xs text-slate-500">
            {{ r.created_at }}
            {% if r.tags %} •
              {% for t in r.tags.split(',') if t.strip() %}
                <a href="/notes?tag={{ t.strip() }}" class="inline-block ml-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800">#{{ t.strip() }}</a>
              {% endfor %}
            {% endif %}
          </div>
        </li>
      {% else %}
        <li class="py-6 text-slate-500">No related notes yet.</li>
      {% endfor %}
    </ul>
  </aside>
</div>
{% endblock %}
HTML

cat > templates/partials/note_view.html <<'HTML'
<article class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <header class="mb-3 flex items-start justify-between gap-4">
    <div>
      <div class="text-xs text-slate-500">{{ note.created_at }}</div>
      <h1 class="text-xl font-semibold text-slate-900 dark:text-white">{{ (note.body.splitlines()[0] or ('Note #' ~ note.id)) | e }}</h1>
      {% if note.tags %}
        <div class="mt-2">
          {% for t in note.tags.split(',') if t.strip() %}
            <a href="/notes?tag={{ t.strip() }}" class="inline-block mr-2 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800">#{{ t.strip() }}</a>
          {% endfor %}
        </div>
      {% endif %}
    </div>
    <div class="shrink-0 flex gap-2">
      <button id="editBtn" hx-get="/notes/{{ note.id }}/edit" hx-target="#note-view" hx-swap="outerHTML"
              class="px-3 py-1.5 rounded-lg bg-brand-600 text-white">Edit</button>
      <form method="post" action="/notes/{{ note.id }}/delete" onsubmit="return confirm('Delete this note?');">
        <button class="px-3 py-1.5 rounded-lg bg-rose-600 text-white">Delete</button>
      </form>
    </div>
  </header>
  <div class="prose prose-slate max-w-none dark:prose-invert whitespace-pre-wrap">
    {{ note.body }}
  </div>
  <footer class="mt-6">
    <a href="/notes" class="text-sm text-slate-600 hover:underline dark:text-slate-300">← Back to notes</a>
  </footer>
</article>
HTML

# =========================== search.html (infinite scroll) ===========================
b templates/search.html
cat > templates/search.html <<'HTML'
{% extends "base.html" %}
{% block title %}Search — Second Brain Premium{% endblock %}
{% block content %}
<div class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Search</h1>
  <form method="get" action="/search" class="mt-4 flex items-center gap-2">
    <input name="q" value="{{ q or '' }}" placeholder="Find text or #tag"
           class="flex-1 rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-2">
    <button class="px-3 py-2 rounded-xl bg-brand-600 text-white">Search</button>
  </form>

  {% if q %}
    <h2 class="mt-6 text-sm text-slate-500">Results for “{{ q }}”</h2>
    <ul id="notes-list" class="mt-2 divide-y divide-slate-200/80 dark:divide-white/10">
      {% for n in notes %}
        {% include 'partials/note_row_selectable.html' %}
      {% else %}
        <li class="py-8 text-slate-500">No results.</li>
      {% endfor %}
    </ul>
    {% if next_page %}
      {% set q=q %}
      {% include 'partials/scroll_sentinel.html' with context %}
    {% endif %}
  {% endif %}
</div>
{% endblock %}
HTML

# =========================== edit form with markdown preview & tag auto ===========================
cat > templates/partials/note_edit_form.html <<'HTML'
<form hx-post="/notes/{{ note.id }}/update" hx-target="#note-view" hx-swap="outerHTML" x-data="{preview:false}">
  <article class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
    <header class="mb-3 flex items-center justify-between">
      <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Edit Note #{{ note.id }}</h1>
      <div class="flex gap-2">
        <button type="button" @click="preview=!preview" class="px-3 py-1.5 rounded-lg bg-slate-200 dark:bg-slate-800" x-text="preview ? 'Edit' : 'Preview'"></button>
        <button type="button" hx-get="/notes/{{ note.id }}" hx-target="#note-view" hx-swap="outerHTML"
                class="px-3 py-1.5 rounded-lg bg-slate-200 dark:bg-slate-800">Cancel</button>
      </div>
    </header>

    <template x-if="!preview">
      <textarea id="editBody" name="body" rows="10"
                class="w-full rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">{{ note.body }}</textarea>
    </template>
    <template x-if="preview">
      <div class="prose prose-slate max-w-none dark:prose-invert" x-html="marked.parse(document.getElementById('editBody').value)"></div>
    </template>

    <input type="hidden" id="tagsInput" name="tags" value="{{ note.tags }}">
    <div class="mt-4">
      <div class="text-xs text-slate-500 mb-1">Tags</div>
      <div id="tag-editor" class="min-h-[44px] rounded-xl px-2 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 flex flex-wrap gap-2 relative">
        <!-- chips -->
        <input id="tag-entry" type="text" placeholder="type, Tab/Enter to accept"
               class="bg-transparent outline-none flex-1 min-w-[140px] text-slate-800 dark:text-slate-200 placeholder:text-slate-400" />
        <div id="tag-auto" class="absolute left-2 right-2 top-full mt-1 hidden rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-hidden"></div>
      </div>
      <div id="tag-suggestions" class="mt-2 flex flex-wrap gap-2"></div>
    </div>

    <div class="mt-4 flex gap-2">
      <button id="saveBtn" class="px-4 py-2 rounded-xl bg-brand-600 text-white">Save</button>
      <button type="button" hx-get="/notes/{{ note.id }}" hx-target="#note-view" hx-swap="outerHTML"
              class="px-4 py-2 rounded-xl bg-slate-200 dark:bg-slate-800">Cancel</button>
    </div>
  </article>
</form>
HTML

# =========================== settings.html (ollama form) ===========================
b templates/settings.html
cat > templates/settings.html <<'HTML'
{% extends "base.html" %}
{% block title %}Settings — Second Brain Premium{% endblock %}
{% block content %}
<div class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Settings</h1>

  <form class="mt-6 grid grid-cols-1 md:grid-cols-3 gap-3" method="post" action="/settings/ollama">
    <input name="base" value="{{ base }}" placeholder="Ollama Base URL"
           class="rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5 md:col-span-2">
    <input name="model" value="{{ model }}" placeholder="Model (e.g., llama3.1:8b)"
           class="rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5">
    <div class="flex gap-2">
      <button class="px-3 py-1.5 rounded-xl bg-brand-600 text-white">Save</button>
      <button formaction="/settings/ollama/test" formmethod="post"
              class="px-3 py-1.5 rounded-xl bg-slate-900 text-white dark:bg-white dark:text-slate-900">Test</button>
    </div>
  </form>
</div>
{% endblock %}
HTML

# =========================== static/app.js ===========================
b static/app.js
cat > static/app.js <<'JS'
// Theme
const btn=document.getElementById('themeToggle');
if(btn){btn.addEventListener('click',()=>{const d=document.documentElement;const t=d.classList.toggle('dark');localStorage.theme=t?'dark':'light';});}

// Quick Search overlay (Cmd/Ctrl+/)
const qwrap=document.getElementById('qwrap'),qmask=document.getElementById('qmask'),qinput=document.getElementById('qinput');
function openQ(){if(!qwrap)return;qwrap.classList.remove('hidden');qmask.classList.remove('hidden');qinput.value='';qinput.focus();qinput.dispatchEvent(new Event('keyup'));}
function closeQ(){if(!qwrap)return;qwrap.classList.add('hidden');qmask.classList.add('hidden');}
document.addEventListener('keydown',(e)=>{if((e.metaKey||e.ctrlKey)&&e.key==='/'){e.preventDefault();openQ();} if(e.key==='Escape'){closeQ();}}); qmask&&qmask.addEventListener('click',closeQ);

// Help sheet (?)
const helpMask=document.getElementById('helpMask'),helpSheet=document.getElementById('helpSheet');
document.addEventListener('keydown',(e)=>{ if(e.key==='?'){ e.preventDefault(); helpMask.classList.remove('hidden'); helpSheet.classList.remove('hidden');}});
document.getElementById('helpClose')?.addEventListener('click',()=>{helpMask.classList.add('hidden'); helpSheet.classList.add('hidden');});
helpMask?.addEventListener('click',()=>{helpMask.classList.add('hidden'); helpSheet.classList.add('hidden');});

// Alpine toast store + HTMX bridge
document.addEventListener('alpine:init', () => {
  Alpine.data('ToastStack', () => ({
    items: [],
    init(){
      document.body.addEventListener('toast', (e) => {
        const detail = e.detail || {};
        this.push(detail.type||'info', detail.message||'');
      });
      // HTMX header bridge (HX-Trigger: {"toast":{...}})
      document.body.addEventListener('htmx:afterOnLoad', (e)=>{
        const trig = e.detail.xhr.getResponseHeader('HX-Trigger');
        if(trig){
          try{ const obj = JSON.parse(trig); if(obj.toast){ this.push(obj.toast.type||'info', obj.toast.message||''); }}catch{}
        }
      });
    },
    push(type, message){
      if(!message) return;
      const id = Date.now()+Math.random();
      this.items.push({id, type, message});
      setTimeout(()=>{ this.items = this.items.filter(x=>x.id!==id); }, 3500);
    }
  }));
});

// Inline toast renderer
(function(){
  const root = document.querySelector('[x-data="ToastStack"]');
  if(!root) return;
  const tpl = `
    <template x-for="t in items" :key="t.id">
      <div x-show
           class="rounded-xl px-3 py-2 text-sm text-white shadow-lg"
           :class="{'bg-emerald-600': t.type==='success','bg-rose-600':t.type==='error','bg-slate-900':t.type!=='success' && t.type!=='error'}"
           x-text="t.message"></div>
    </template>`;
  root.insertAdjacentHTML('beforeend', tpl);
})();

// Global shortcuts: on note page e to edit, Cmd/Ctrl+s to save
document.addEventListener('keydown', (e) => {
  const onNotePage = !!document.getElementById('note-view');
  if(onNotePage && e.key==='e' && !e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey){
    const btn = document.getElementById('editBtn'); if(btn){ e.preventDefault(); btn.click(); }
  }
  if((e.metaKey||e.ctrlKey) && e.key.toLowerCase()==='s'){
    const save = document.getElementById('saveBtn');
    if(save){ e.preventDefault(); save.click(); }
  }
});

// ---- Tag editor + autocomplete + suggestions (works on dashboard & edit form) ----
(function () {
  const editor = document.getElementById('tag-editor');
  const entry  = document.getElementById('tag-entry');
  const hidden = document.getElementById('tagsInput');
  const suggestWrap = document.getElementById('tag-suggestions');
  const autoMenu = document.getElementById('tag-auto');
  const noteBody = document.getElementById('body') || document.getElementById('editBody');
  if (!editor || !entry || !hidden) return;

  let tags = new Set((hidden.value||'').split(',').filter(Boolean));
  function syncHidden(){ hidden.value = Array.from(tags).join(','); }
  function chip(t){
    const el = document.createElement('span');
    el.className = 'tag-chip inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200';
    el.innerHTML = `#${t} <button type="button" class="remove text-xs opacity-70 hover:opacity-100" aria-label="Remove tag ${t}">×</button>`;
    el.querySelector('button.remove').addEventListener('click',()=>{ tags.delete(t); render(); });
    return el;
  }
  function render(){
    Array.from(editor.querySelectorAll('.tag-chip')).forEach(el => el.remove());
    tags.forEach(t => editor.insertBefore(chip(t), entry));
    syncHidden();
  }
  function addTag(raw){
    const t = (raw||'').trim().toLowerCase().replace(/^#/, '').replace(/\s+/g,'-').replace(/[^a-z0-9\-]/g,'');
    if (!t) return; if(tags.has(t)) return; tags.add(t); render(); hideAuto();
  }
  function parseEntry(){ entry.value.split(/[,\s]+/).filter(Boolean).forEach(addTag); entry.value=''; }

  // Suggestions from note body via LLM
  let timer; const debounce = (fn,ms=600)=>(...a)=>{ clearTimeout(timer); timer=setTimeout(()=>fn(...a),ms); };
  async function llmSuggest(text){
    try{
      const res = await fetch('/tags/suggest',{ method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text}) });
      const data = await res.json();
      renderLLMSuggestions(Array.isArray(data.tags)?data.tags:[]);
    }catch{ renderLLMSuggestions([]); }
  }
  function renderLLMSuggestions(list){
    suggestWrap.innerHTML = '';
    list.forEach(t=>{
      if (tags.has(t)) return;
      const b=document.createElement('button');
      b.type='button'; b.className='px-2 py-1 rounded-lg bg-brand-600 text-white text-xs hover:bg-brand-700'; b.textContent = `#${t}`;
      b.addEventListener('click',()=>addTag(t));
      suggestWrap.appendChild(b);
    });
  }

  // Autocomplete menu
  let autoItems = [], autoIndex = -1;
  function hideAuto(){ if(autoMenu){ autoMenu.classList.add('hidden'); autoMenu.innerHTML=''; autoItems=[]; autoIndex=-1; } }
  function showAuto(list){
    if(!autoMenu) return;
    autoMenu.innerHTML = list.map((t,i)=>`<button type="button" data-i="${i}" class="w-full text-left px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 ${i===0?'bg-slate-50 dark:bg-slate-800':''}">#${t}</button>`).join('');
    autoMenu.classList.remove('hidden');
    autoItems = list.slice(0); autoIndex = 0;
    autoMenu.querySelectorAll('button').forEach(btn => btn.addEventListener('click', ()=>{ addTag(btn.textContent.replace('#','')); entry.focus(); }));
  }
  async function fetchAuto(q){
    try{
      const res = await fetch('/api/tags?q='+encodeURIComponent(q));
      const data = await res.json();
      const list = (data.tags||[]).filter(t=>!tags.has(t) && t!==q);
      if(list.length) showAuto(list); else hideAuto();
    }catch{ hideAuto(); }
  }

  entry.addEventListener('input', debounce(()=>{ const v=entry.value.trim(); if(v.length>0) fetchAuto(v); else hideAuto(); }, 200));
  entry.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ','){ e.preventDefault(); if(autoItems.length){ addTag(autoItems[autoIndex]); } else { parseEntry(); } }
    else if (e.key === 'Tab'){ if(autoItems.length){ e.preventDefault(); addTag(autoItems[autoIndex]); } }
    else if (e.key === 'ArrowDown'){ if(autoItems.length){ e.preventDefault(); autoIndex=(autoIndex+1)%autoItems.length; highlightAuto(); } }
    else if (e.key === 'ArrowUp'){ if(autoItems.length){ e.preventDefault(); autoIndex=(autoIndex-1+autoItems.length)%autoItems.length; highlightAuto(); } }
    else if (e.key === 'Backspace' && entry.value===''){ const last = Array.from(tags).pop(); if(last){ tags.delete(last); render(); } }
  });
  function highlightAuto(){ if(!autoMenu) return; autoMenu.querySelectorAll('button').forEach((b,i)=>{ b.classList.toggle('bg-slate-50', i===autoIndex); b.classList.toggle('dark:bg-slate-800', i===autoIndex);}); }

  // preload chips (for edit form)
  render();

  // Debounced LLM suggestions based on note body
  if(noteBody){ noteBody.addEventListener('input', debounce(()=>{ const v=noteBody.value.trim(); if(v.length<8){ renderLLMSuggestions([]); return; } llmSuggest(v); }, 650)); }
})();

// HTMX global error → toast
document.body.addEventListener('htmx:responseError', ()=>{document.body.dispatchEvent(new CustomEvent('toast',{detail:{type:'error',message:'Request failed'}}));});
document.body.addEventListener('htmx:send', ()=>{/* could show spinner */});
JS

# =========================== search_results partial (unchanged if exists) ===========================
if [[ ! -f templates/partials/search_results.html ]]; then
cat > templates/partials/search_results.html <<'HTML'
<ul class="divide-y divide-slate-200/80 dark:divide-white/10">
  {% for n in items %}
    <li class="py-3 px-4 hover:bg-slate-50 dark:hover:bg-slate-900">
      <a href="/notes/{{ n.id }}" class="block">
        <div class="font-medium text-slate-900 dark:text-white">{{ (n.body[:100] ~ ('…' if n.body|length > 100 else '')) | e }}</div>
        <div class="text-xs text-slate-500">{{ n.created_at }}
          {% if n.tags %} •
            {% for t in n.tags.split(',') if t.strip() %}
              <span class="inline-block ml-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800">#{{ t.strip() }}</span>
            {% endfor %}
          {% endif %}
        </div>
      </a>
    </li>
  {% else %}
    <li class="py-6 text-center text-slate-500">No results.</li>
  {% endfor %}
</ul>
HTML
fi

# =========================== requirements ===========================
if ! grep -q fastapi requirements.txt 2>/dev/null; then
cat > requirements.txt <<'REQ'
fastapi==0.115.0
uvicorn[standard]==0.30.6
jinja2==3.1.4
httpx==0.27.2
REQ
fi

echo "Done.

Run:
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  uvicorn app:app --reload --host 0.0.0.0 --port 8084

Hotkeys:
  ⌘/Ctrl + / : Quick Search
  ?           : Shortcuts help
  e           : Edit on Note page
  ⌘/Ctrl + s  : Save in editor

Toasts appear bottom-right. Tag autocomplete: type in the tag box, navigate with ↑/↓, Enter/Tab to accept.
"
