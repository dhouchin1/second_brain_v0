#!/usr/bin/env bash
set -euo pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"

backup_if_exists () {
  local path="$1"
  if [[ -f "$path" ]]; then
    mv "$path" "$path.$STAMP.bak"
    echo "  • Backed up $path -> $path.$STAMP.bak"
  fi
}

mkdir -p templates/partials static

echo "==> Writing FastAPI app with normalized SQLite schema + FTS5 + Tag Manager…"
backup_if_exists app.py
cat > app.py <<'PY'
from datetime import datetime
from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pathlib, sqlite3, os, re, json, httpx
from collections import Counter

app = FastAPI(title="Second Brain Premium")

BASE_DIR = pathlib.Path(__file__).parent.resolve()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

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

-- Full-text search (content=notes keeps it in sync via triggers)
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
    init_needed = not db.exists()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    if init_needed:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    else:
        # ensure schema pieces exist if upgrading
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    _maybe_migrate_legacy_tags_column(conn)
    return conn

def _maybe_migrate_legacy_tags_column(conn: sqlite3.Connection):
    # If an old 'tags' TEXT column existed on notes, migrate values to tags/note_tags
    cols = [r[1] for r in conn.execute("PRAGMA table_info(notes);").fetchall()]
    if "tags" not in cols:
        return
    rows = conn.execute("SELECT id, IFNULL(tags,'') AS tags FROM notes WHERE IFNULL(tags,'') <> ''").fetchall()
    for r in rows:
        note_id = r["id"]
        for name in _normalize_tag_list(r["tags"]):
            tag_id = _ensure_tag(conn, name)
            _link_note_tag(conn, note_id, tag_id)
    # drop column by rebuilding table if it still exists
    # (safe no-op if we already rebuilt)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS notes_new(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      body TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    INSERT INTO notes_new(id, body, created_at)
      SELECT id, body, COALESCE(created_at, datetime('now')) FROM notes;
    DROP TABLE notes;
    ALTER TABLE notes_new RENAME TO notes;
    """)
    # Recreate triggers and fts (in case dropping table removed them)
    conn.executescript(SCHEMA_SQL)
    conn.commit()

def _normalize_tag_list(csv_value: str):
    return [re.sub(r"[^a-z0-9\-]", "", t.strip().lower().replace("#","").replace(" ", "-"))
            for t in csv_value.split(",") if t.strip()]

def _ensure_tag(conn, name: str) -> int:
    cur = conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
    if cur.lastrowid:
        return cur.lastrowid
    return conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()["id"]

def _link_note_tag(conn, note_id: int, tag_id: int):
    conn.execute("INSERT OR IGNORE INTO note_tags(note_id, tag_id) VALUES (?,?)", (note_id, tag_id))

def _rows_with_tags(conn, rows):
    # attaches comma-joined tags to each note row (for templates)
    ids = [r["id"] for r in rows]
    if not ids: return {}
    q = f"""
    SELECT n.id, GROUP_CONCAT(t.name) AS tags
    FROM notes n
    LEFT JOIN note_tags nt ON nt.note_id = n.id
    LEFT JOIN tags t ON t.id = nt.tag_id
    WHERE n.id IN ({",".join("?"*len(ids))})
    GROUP BY n.id
    """
    tagmap = {r["id"]: (r["tags"] or "") for r in conn.execute(q, ids).fetchall()}
    return tagmap

# -------------------- Pages --------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    conn = get_conn()
    c = conn.cursor()
    total_notes = c.execute("SELECT COUNT(*) AS c FROM notes").fetchone()["c"]
    recent = c.execute(
        "SELECT id, body, created_at FROM notes ORDER BY datetime(created_at) DESC LIMIT 5"
    ).fetchall()
    tagmap = _rows_with_tags(conn, recent)
    # decorate
    recent_list = []
    for r in recent:
        d = dict(r)
        d["tags"] = tagmap.get(r["id"], "")
        recent_list.append(d)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "stats": {"notes": total_notes}, "recent": recent_list},
    )

@app.get("/notes", response_class=HTMLResponse)
async def notes_page(request: Request, tag: str = ""):
    conn = get_conn()
    c = conn.cursor()
    if tag:
        rows = c.execute(
            """
            SELECT n.id, n.body, n.created_at
            FROM notes n
            WHERE EXISTS (
               SELECT 1 FROM note_tags nt
               JOIN tags t ON t.id = nt.tag_id
               WHERE nt.note_id = n.id AND t.name = ?
            )
            ORDER BY datetime(n.created_at) DESC
            """, (tag,)
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT id, body, created_at FROM notes ORDER BY datetime(created_at) DESC"
        ).fetchall()
    tagmap = _rows_with_tags(conn, rows)
    notes = []
    for r in rows:
        d = dict(r)
        d["tags"] = tagmap.get(r["id"], "")
        notes.append(d)
    return templates.TemplateResponse("notes.html", {"request": request, "notes": notes, "active_tag": tag})

@app.get("/notes/{note_id}", response_class=HTMLResponse)
async def note_detail(request: Request, note_id: int):
    conn = get_conn()
    c = conn.cursor()
    r = c.execute("SELECT id, body, created_at FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not r:
        return RedirectResponse("/", status_code=302)
    d = dict(r)
    d["tags"] = _rows_with_tags(conn, [r]).get(r["id"], "")
    return templates.TemplateResponse("note_detail.html", {"request": request, "note": d})

@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    conn = get_conn()
    rows = []
    if q:
        # FTS5 search
        rows = conn.execute(
            """
            SELECT n.id, n.body, n.created_at
            FROM notes_fts f
            JOIN notes n ON n.id = f.rowid
            WHERE notes_fts MATCH ?
            ORDER BY bm25(notes_fts) LIMIT 50
            """,
            (q,)
        ).fetchall()
    tagmap = _rows_with_tags(conn, rows)
    notes = []
    for r in rows:
        d = dict(r)
        d["tags"] = tagmap.get(r["id"], "")
        notes.append(d)
    return templates.TemplateResponse("search.html", {"request": request, "q": q, "notes": notes})

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

# -------------------- Create Note + Tagging --------------------

@app.post("/notes", response_class=HTMLResponse)
async def create_note(request: Request, body: str = Form(...), tags: str = Form("")):
    conn = get_conn()
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur = conn.execute("INSERT INTO notes(body, created_at) VALUES (?,?)", (body, now))
    note_id = cur.lastrowid
    for name in _normalize_tag_list(tags):
        tag_id = _ensure_tag(conn, name)
        _link_note_tag(conn, note_id, tag_id)
    conn.commit()

    if request.headers.get("HX-Request"):
        # assemble single note dict with tags for partial
        d = {"id": note_id, "body": body, "created_at": now}
        d["tags"] = _rows_with_tags(conn, [sqlite3.Row(sqlite3.Cursor(conn), (note_id, body, now))]).get(note_id, "")
        # simpler: requery
        row = conn.execute("SELECT id, body, created_at FROM notes WHERE id=?", (note_id,)).fetchone()
        d = dict(row); d["tags"] = _rows_with_tags(conn, [row]).get(note_id, "")
        return templates.TemplateResponse("partials/note_item.html", {"request": request, "n": d})
    return RedirectResponse(f"/notes/{note_id}", status_code=303)

# -------------------- Tag Manager --------------------

@app.get("/tags", response_class=HTMLResponse)
async def tag_manager(request: Request):
    conn = get_conn()
    rows = conn.execute("""
      SELECT t.name, COUNT(nt.note_id) AS usage
      FROM tags t
      LEFT JOIN note_tags nt ON nt.tag_id = t.id
      GROUP BY t.id
      ORDER BY usage DESC, t.name ASC
    """).fetchall()
    tags = [dict(r) for r in rows]
    return templates.TemplateResponse("tags.html", {"request": request, "tags": tags})

@app.post("/tags/rename", response_class=RedirectResponse)
async def rename_tag(old_name: str = Form(...), new_name: str = Form(...)):
    conn = get_conn()
    new_name = re.sub(r"[^a-z0-9\-]", "", new_name.strip().lower().replace(" ", "-").replace("#",""))
    old = conn.execute("SELECT id FROM tags WHERE name=?", (old_name,)).fetchone()
    if not old:
        return RedirectResponse("/tags", status_code=303)
    existing = conn.execute("SELECT id FROM tags WHERE name=?", (new_name,)).fetchone()
    if existing:
        # merge
        conn.execute("UPDATE OR IGNORE note_tags SET tag_id=? WHERE tag_id=?", (existing["id"], old["id"]))
        conn.execute("DELETE FROM tags WHERE id=?", (old["id"],))
    else:
        conn.execute("UPDATE tags SET name=? WHERE id=?", (new_name, old["id"]))
    conn.commit()
    return RedirectResponse("/tags", status_code=303)

@app.post("/tags/delete", response_class=RedirectResponse)
async def delete_tag(name: str = Form(...)):
    conn = get_conn()
    row = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
    if row:
        conn.execute("DELETE FROM tags WHERE id=?", (row["id"],))
        conn.commit()
    return RedirectResponse("/tags", status_code=303)

# -------------------- Quick Search API (overlay) --------------------

@app.get("/api/q", response_class=HTMLResponse)
async def quick_search_partial(request: Request, q: str):
    conn = get_conn()
    q = q.strip()
    if not q:
        return HTMLResponse("")
    rows = conn.execute(
        """
        SELECT n.id, n.body, n.created_at
        FROM notes_fts f JOIN notes n ON n.id=f.rowid
        WHERE notes_fts MATCH ?
        ORDER BY bm25(notes_fts) LIMIT 20
        """,
        (q,)
    ).fetchall()
    tagmap = _rows_with_tags(conn, rows)
    items = []
    for r in rows:
        d = dict(r)
        d["tags"] = tagmap.get(r["id"], "")
        items.append(d)
    return templates.TemplateResponse("partials/search_results.html", {"request": request, "items": items})

# -------------------- LLM Tag Suggestions --------------------

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

TAG_PROMPT = """You are a tagging assistant. From the user note below, extract 3-7 SHORT tags.
Rules:
- lowercase
- no punctuation except hyphens
- no spaces; use hyphen for multiword (e.g., time-management)
- no leading '#'
- return ONLY a comma-separated list of tags, nothing else.

Note:
"""

STOPWORDS = set("""
a an and the i you he she it we they to of for in on with from this that these those be is are was were am will would can could should as at by not or if into over under about after before during up down out very just
""".split())

def naive_tags(text: str, k: int = 6):
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{3,}", text.lower())
    words = [w for w in words if w not in STOPWORDS]
    counts = Counter(words)
    return [w for w, _ in counts.most_common(k)]

@app.post("/tags/suggest")
async def suggest_tags(payload: dict = Body(...)):
    text = (payload.get("text") or "").strip()
    if len(text) < 8:
        return JSONResponse({"tags": []})
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            req = {"model": OLLAMA_MODEL, "prompt": TAG_PROMPT + text + "\nTags:", "stream": False}
            r = await client.post(f"{OLLAMA_BASE}/api/generate", json=req)
            r.raise_for_status()
            raw = r.json().get("response", "")
            tags = [re.sub(r"[^a-z0-9\-]", "", t.strip().lower().replace("#","").replace(" ", "-"))
                    for t in raw.split(",") if t.strip()]
            if not tags:
                tags = naive_tags(text)
    except Exception:
        tags = naive_tags(text)
    tags = list(dict.fromkeys([t for t in tags if t]))[:7]
    return JSONResponse({"tags": tags})
PY

echo "==> Templates…"
backup_if_exists templates/base.html
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
  <div id="qmask" class="hidden fixed inset-0 z-50 bg-black/50"></div>
  <section id="qwrap" class="hidden fixed left-1/2 top-24 -translate-x-1/2 z-50 w-[min(800px,94vw)]">
    <div class="rounded-2xl overflow-hidden shadow-2xl ring-1 ring-black/10">
      <div class="p-3 bg-white dark:bg-slate-950 border-b border-black/10 dark:border-white/10">
        <input id="qinput" type="text" placeholder="Search…"
               class="w-full bg-transparent outline-none px-2 py-2 text-slate-900 dark:text-white" />
        <div class="text-xs text-slate-500 mt-1">Press Esc to close</div>
      </div>
      <div id="qresults" class="max-h-[60vh] overflow-y-auto bg-white/95 dark:bg-slate-950/90"
           hx-get="/api/q" hx-trigger="keyup changed delay:300ms from:#qinput"
           hx-target="#qresults" hx-include="#qinput" hx-vals='js:{q: document.getElementById("qinput").value}'></div>
    </div>
  </section>

  <script src="/static/app.js"></script>
</body>
</html>
HTML

backup_if_exists templates/dashboard.html
cat > templates/dashboard.html <<'HTML'
{% extends "base.html" %}
{% block title %}Dashboard — Second Brain Premium{% endblock %}
{% block content %}
<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
  <section class="lg:col-span-2 rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
    <h2 class="text-lg font-semibold text-slate-900 dark:text-white">Quick Capture</h2>
    <form class="mt-4 space-y-4"
          hx-post="/notes"
          hx-target="#recent-notes"
          hx-swap="afterbegin"
          hx-on:htmx:afterRequest="if(event.detail.successful){ this.reset(); window.TagEditor && window.TagEditor.reset(); }">
      <textarea id="body" name="body" required rows="5"
                class="w-full rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                placeholder="What's on your mind?"></textarea>

      <input type="hidden" id="tagsInput" name="tags" />
      <div>
        <div class="text-xs text-slate-500 mb-1">Tags</div>
        <div id="tag-editor" class="min-h-[44px] rounded-xl px-2 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 flex flex-wrap gap-2">
          <input id="tag-entry" type="text" placeholder="type and press Enter"
                 class="bg-transparent outline-none flex-1 min-w-[140px] text-slate-800 dark:text-slate-200 placeholder:text-slate-400" />
        </div>
        <div id="tag-suggestions" class="mt-2 flex flex-wrap gap-2"></div>
      </div>

      <button type="submit" class="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white shadow">Save Note</button>
    </form>
  </section>

  <aside class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
    <h2 class="text-lg font-semibold text-slate-900 dark:text-white">Overview</h2>
    <dl class="mt-4 grid grid-cols-2 gap-4">
      <div class="rounded-xl bg-slate-50 dark:bg-slate-900 p-4">
        <dt class="text-sm text-slate-500">Total Notes</dt>
        <dd class="text-2xl font-semibold text-slate-900 dark:text-white">{{ stats.notes }}</dd>
      </div>
      <div class="rounded-xl bg-slate-50 dark:bg-slate-900 p-4">
        <dt class="text-sm text-slate-500">Today</dt>
        <dd class="text-2xl font-semibold text-slate-900 dark:text-white">✨</dd>
      </div>
    </dl>
  </aside>
</div>

<section class="mt-6 rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <h2 class="text-lg font-semibold text-slate-900 dark:text-white">Recent Notes</h2>
  <ul id="recent-notes" class="mt-4 divide-y divide-slate-200/80 dark:divide-white/10">
    {% for n in recent %}
      {% include 'partials/note_item.html' %}
    {% else %}
      <li class="py-8 text-slate-500">No notes yet. Start capturing your thoughts!</li>
    {% endfor %}
  </ul>
</section>
{% endblock %}
HTML

backup_if_exists templates/partials/note_item.html
cat > templates/partials/note_item.html <<'HTML'
<li class="py-4 flex items-start gap-4">
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
             class="inline-block ml-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700">
            #{{ t.strip() }}
          </a>
        {% endfor %}
      {% endif %}
    </div>
  </div>
</li>
HTML

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

backup_if_exists templates/notes.html
cat > templates/notes.html <<'HTML'
{% extends "base.html" %}
{% block title %}All Notes — Second Brain Premium{% endblock %}
{% block content %}
<div class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <div class="flex items-center justify-between gap-4">
    <h1 class="text-xl font-semibold text-slate-900 dark:text-white">All Notes</h1>
    <form method="get" action="/notes" class="flex items-center gap-2">
      <input name="tag" value="{{ active_tag or '' }}" placeholder="Filter by tag"
             class="rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5">
      <button class="px-3 py-1.5 rounded-xl bg-slate-900 text-white dark:bg-white dark:text-slate-900">Filter</button>
    </form>
  </div>

  <ul class="mt-4 divide-y divide-slate-200/80 dark:divide-white/10">
    {% for n in notes %}
      {% include 'partials/note_item.html' %}
    {% else %}
      <li class="py-8 text-slate-500">No notes found.</li>
    {% endfor %}
  </ul>
</div>
{% endblock %}
HTML

backup_if_exists templates/note_detail.html
cat > templates/note_detail.html <<'HTML'
{% extends "base.html" %}
{% block title %}Note #{{ note.id }} — Second Brain Premium{% endblock %}
{% block content %}
<article class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <header class="mb-3">
    <div class="text-xs text-slate-500">{{ note.created_at }}</div>
    <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Note #{{ note.id }}</h1>
    {% if note.tags %}
      <div class="mt-2">
        {% for t in note.tags.split(',') if t.strip() %}
          <a href="/notes?tag={{ t.strip() }}" class="inline-block mr-2 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800">#{{ t.strip() }}</a>
        {% endfor %}
      </div>
    {% endif %}
  </header>
  <div class="prose prose-slate max-w-none dark:prose-invert whitespace-pre-wrap">{{ note.body }}</div>
  <footer class="mt-6">
    <a href="/notes" class="text-sm text-slate-600 hover:underline dark:text-slate-300">← Back to notes</a>
  </footer>
</article>
{% endblock %}
HTML

backup_if_exists templates/search.html
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
    <ul class="mt-2 divide-y divide-slate-200/80 dark:divide-white/10">
      {% for n in notes %}
        {% include 'partials/note_item.html' %}
      {% else %}
        <li class="py-8 text-slate-500">No results.</li>
      {% endfor %}
    </ul>
  {% endif %}
</div>
{% endblock %}
HTML

cat > templates/tags.html <<'HTML'
{% extends "base.html" %}
{% block title %}Tag Manager — Second Brain Premium{% endblock %}
{% block content %}
<div class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Tag Manager</h1>
  <p class="text-sm text-slate-500 mt-1">Rename (or merge into an existing tag) and delete tags. Counts reflect linked notes.</p>

  <div class="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
    {% for t in tags %}
      <div class="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
        <div class="flex items-center justify-between">
          <div class="font-medium text-slate-900 dark:text-white">#{{ t.name }}</div>
          <div class="text-xs text-slate-500">{{ t.usage }} notes</div>
        </div>

        <form class="mt-3 flex gap-2 items-center" method="post" action="/tags/rename">
          <input type="hidden" name="old_name" value="{{ t.name }}">
          <input name="new_name" placeholder="new-name" class="flex-1 rounded-lg border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5">
          <button class="px-3 py-1.5 rounded-lg bg-brand-600 text-white">Rename/Merge</button>
        </form>

        <form class="mt-2" method="post" action="/tags/delete" onsubmit="return confirm('Delete #{{ t.name }}? This only detaches the tag from notes.');">
          <input type="hidden" name="name" value="{{ t.name }}">
          <button class="px-3 py-1.5 rounded-lg bg-rose-600 text-white">Delete Tag</button>
        </form>
      </div>
    {% else %}
      <div class="text-slate-500">No tags yet.</div>
    {% endfor %}
  </div>
</div>
{% endblock %}
HTML

backup_if_exists templates/settings.html
cat > templates/settings.html <<'HTML'
{% extends "base.html" %}
{% block title %}Settings — Second Brain Premium{% endblock %}
{% block content %}
<div class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Settings</h1>
  <div class="mt-6 space-y-6">
    <section>
      <h2 class="font-medium text-slate-900 dark:text-white">Theme</h2>
      <p class="text-sm text-slate-500">Use the “Toggle Theme” button in the header. Preference is saved to your browser.</p>
    </section>
    <section>
      <h2 class="font-medium text-slate-900 dark:text-white">Ollama</h2>
      <p class="text-sm text-slate-500">Set <code>OLLAMA_BASE_URL</code> and <code>OLLAMA_MODEL</code>. Defaults: <code>http://localhost:11434</code>, <code>llama3.1:8b</code>.</p>
    </section>
  </div>
</div>
{% endblock %}
HTML

echo "==> Static JS (theme, tag editor, LLM suggestions, quick-search overlay)…"
backup_if_exists static/app.js
cat > static/app.js <<'JS'
// Dark mode toggle
const btn = document.getElementById('themeToggle');
if (btn) {
  btn.addEventListener('click', () => {
    const el = document.documentElement;
    const isDark = el.classList.toggle('dark');
    localStorage.theme = isDark ? 'dark' : 'light';
  });
}

// Quick Search overlay (Cmd+/ or Ctrl+/)
const qwrap = document.getElementById('qwrap');
const qmask = document.getElementById('qmask');
const qinput = document.getElementById('qinput');

function openQ() {
  qwrap.classList.remove('hidden');
  qmask.classList.remove('hidden');
  qinput.value = '';
  qinput.focus();
  // trigger a blank load to clear results
  const evt = new Event('keyup');
  qinput.dispatchEvent(evt);
}
function closeQ() {
  qwrap.classList.add('hidden');
  qmask.classList.add('hidden');
}

document.addEventListener('keydown', (e) => {
  const isCmdSlash = (e.metaKey || e.ctrlKey) && e.key === '/';
  if (isCmdSlash) { e.preventDefault(); openQ(); }
  if (e.key === 'Escape' && !qwrap.classList.contains('hidden')) { closeQ(); }
});
qmask && qmask.addEventListener('click', closeQ);

// --- Tag Editor + Suggestions ---
(function () {
  const editor = document.getElementById('tag-editor');
  const entry  = document.getElementById('tag-entry');
  const hidden = document.getElementById('tagsInput');
  const suggestWrap = document.getElementById('tag-suggestions');
  const noteBody = document.getElementById('body');
  if (!editor || !entry || !hidden) return;

  let tags = new Set();
  function syncHidden(){ hidden.value = Array.from(tags).join(','); }
  function token(t){
    const chip = document.createElement('span');
    chip.className = 'tag-chip inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200';
    chip.innerHTML = `#${t} <button type="button" class="remove text-xs opacity-70 hover:opacity-100">×</button>`;
    chip.querySelector('button.remove').addEventListener('click', () => { tags.delete(t); render(); });
    return chip;
  }
  function render(){
    Array.from(editor.querySelectorAll('.tag-chip')).forEach(el => el.remove());
    tags.forEach(t => editor.insertBefore(token(t), entry));
    syncHidden();
  }
  function addTag(raw){
    const t = raw.trim().toLowerCase().replace(/^#/, '').replace(/\s+/g,'-').replace(/[^a-z0-9\-]/g,'');
    if (!t) return; tags.add(t); render();
  }
  function parseEntry(){
    entry.value.split(/[,\s]+/).filter(Boolean).forEach(addTag);
    entry.value = '';
  }
  window.TagEditor = { reset(){ tags = new Set(); render(); } };

  entry.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ','){ e.preventDefault(); parseEntry(); }
    else if (e.key === 'Backspace' && entry.value === '') { const last = Array.from(tags).pop(); if (last){ tags.delete(last); render(); } }
  });

  // Suggestions from LLM (debounced)
  let timer; const debounce = (fn,ms=600)=>(...a)=>{ clearTimeout(timer); timer=setTimeout(()=>fn(...a),ms); };
  async function suggest(text){
    try{
      const res = await fetch('/tags/suggest',{ method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text}) });
      if (!res.ok) throw 0;
      const data = await res.json();
      renderSuggestions(Array.isArray(data.tags)?data.tags:[]);
    }catch{ renderSuggestions([]); }
  }
  function renderSuggestions(list){
    suggestWrap.innerHTML = '';
    list.forEach(t=>{
      if (tags.has(t)) return;
      const b=document.createElement('button');
      b.type='button'; b.className='px-2 py-1 rounded-lg bg-brand-600 text-white text-xs hover:bg-brand-700'; b.textContent = `#${t}`;
      b.addEventListener('click',()=>addTag(t));
      suggestWrap.appendChild(b);
    });
  }
  if (noteBody){ noteBody.addEventListener('input', debounce(()=>{ const v=noteBody.value.trim(); if (v.length<8){ renderSuggestions([]); return; } suggest(v); }, 650)); }
})();
JS

echo "==> requirements.txt…"
backup_if_exists requirements.txt
cat > requirements.txt <<'REQ'
fastapi==0.115.0
uvicorn[standard]==0.30.6
jinja2==3.1.4
httpx==0.27.2
REQ

echo "==> Done.

Next steps:
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  # optional: export OLLAMA_BASE_URL and OLLAMA_MODEL
  uvicorn app:app --reload --host 0.0.0.0 --port 8084

Open http://localhost:8084
Hotkeys: ⌘/ or Ctrl+/ for quick search.
"
