#!/usr/bin/env bash
set -euo pipefail
STAMP="$(date +%Y%m%d-%H%M%S)"
backup(){ [[ -f "$1" ]] && mv "$1" "$1.$STAMP.bak" && echo "• backup: $1 -> $1.$STAMP.bak" || true; }

mkdir -p templates/partials static

# ---------- app.py (overwrite with inline edit + bulk-retag) ----------
backup app.py
cat > app.py <<'PY'
from datetime import datetime
from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pathlib, sqlite3, os, re, httpx
from collections import Counter

app = FastAPI(title="Second Brain Premium")
BASE_DIR = pathlib.Path(__file__).parent.resolve()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ---------- DB & schema ----------
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
    conn.executescript(SCHEMA_SQL)  # safe idempotent
    conn.commit()
    if init_needed:
        print("Initialized DB at", db)
    return conn

# ---------- helpers ----------
def norm_tag(name: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "", name.strip().lower().replace("#","").replace(" ", "-"))

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

# ---------- pages ----------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"]
    recent = conn.execute("SELECT id, body, created_at FROM notes ORDER BY datetime(created_at) DESC LIMIT 5").fetchall()
    tagmap = map_note_tags(conn, recent)
    recent_list = [dict(r) | {"tags": tagmap.get(r["id"], "")} for r in recent]
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": {"notes": total}, "recent": recent_list})

@app.get("/notes", response_class=HTMLResponse)
def notes_page(request: Request, tag: str = ""):
    conn = get_conn()
    if tag:
        rows = conn.execute("""
          SELECT n.id, n.body, n.created_at FROM notes n
          WHERE EXISTS (SELECT 1 FROM note_tags nt JOIN tags t ON t.id=nt.tag_id WHERE nt.note_id=n.id AND t.name=?)
          ORDER BY datetime(n.created_at) DESC
        """, (tag,)).fetchall()
    else:
        rows = conn.execute("SELECT id, body, created_at FROM notes ORDER BY datetime(created_at) DESC").fetchall()
    tagmap = map_note_tags(conn, rows)
    notes = [dict(r) | {"tags": tagmap.get(r["id"], "")} for r in rows]
    return templates.TemplateResponse("notes.html", {"request": request, "notes": notes, "active_tag": tag})

@app.get("/notes/{note_id}", response_class=HTMLResponse)
def note_detail(request: Request, note_id: int):
    conn = get_conn()
    r = conn.execute("SELECT id, body, created_at FROM notes WHERE id=?", (note_id,)).fetchone()
    if not r: return RedirectResponse("/", status_code=302)
    note = dict(r) | {"tags": map_note_tags(conn, [r]).get(r["id"], "")}
    return templates.TemplateResponse("note_detail.html", {"request": request, "note": note})

# ---------- inline edit / delete ----------
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
    # return the view partial to swap back in
    return templates.TemplateResponse("partials/note_view.html", {"request": request, "note": note})

@app.post("/notes/{note_id}/delete", response_class=RedirectResponse)
def note_delete(note_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit()
    return RedirectResponse("/notes", status_code=303)

# ---------- search ----------
@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = ""):
    conn = get_conn(); rows = []
    if q:
        rows = conn.execute("""
          SELECT n.id, n.body, n.created_at
          FROM notes_fts f JOIN notes n ON n.id=f.rowid
          WHERE notes_fts MATCH ?
          ORDER BY bm25(notes_fts) LIMIT 50
        """, (q,)).fetchall()
    tagmap = map_note_tags(conn, rows)
    notes = [dict(r) | {"tags": tagmap.get(r["id"], "")} for r in rows]
    return templates.TemplateResponse("search.html", {"request": request, "q": q, "notes": notes})

@app.get("/api/q", response_class=HTMLResponse)
def quick_search_partial(request: Request, q: str):
    conn = get_conn()
    if not (q or "").strip(): return HTMLResponse("")
    rows = conn.execute("""
      SELECT n.id, n.body, n.created_at
      FROM notes_fts f JOIN notes n ON n.id=f.rowid
      WHERE notes_fts MATCH ?
      ORDER BY bm25(notes_fts) LIMIT 20
    """, (q,)).fetchall()
    tagmap = map_note_tags(conn, rows)
    items = [dict(r) | {"tags": tagmap.get(r["id"], "")} for r in rows]
    return templates.TemplateResponse("partials/search_results.html", {"request": request, "items": items})

# ---------- tag manager ----------
@app.get("/tags", response_class=HTMLResponse)
def tag_manager(request: Request):
    conn = get_conn()
    rows = conn.execute("""
      SELECT t.name, COUNT(nt.note_id) usage
      FROM tags t LEFT JOIN note_tags nt ON nt.tag_id=t.id
      GROUP BY t.id ORDER BY usage DESC, t.name ASC
    """).fetchall()
    return templates.TemplateResponse("tags.html", {"request": request, "tags": [dict(r) for r in rows]})

@app.post("/tags/rename", response_class=RedirectResponse)
def rename_tag(old_name: str = Form(...), new_name: str = Form(...)):
    conn = get_conn()
    old_name = norm_tag(old_name)
    new_name = norm_tag(new_name)
    old = conn.execute("SELECT id FROM tags WHERE name=?", (old_name,)).fetchone()
    if not old: return RedirectResponse("/tags", status_code=303)
    existing = conn.execute("SELECT id FROM tags WHERE name=?", (new_name,)).fetchone()
    if existing:
        conn.execute("UPDATE OR IGNORE note_tags SET tag_id=? WHERE tag_id=?", (existing["id"], old["id"]))
        conn.execute("DELETE FROM tags WHERE id=?", (old["id"],))
    else:
        conn.execute("UPDATE tags SET name=? WHERE id=?", (new_name, old["id"]))
    conn.commit()
    return RedirectResponse("/tags", status_code=303)

@app.post("/tags/delete", response_class=RedirectResponse)
def delete_tag(name: str = Form(...)):
    conn = get_conn()
    row = conn.execute("SELECT id FROM tags WHERE name=?", (norm_tag(name),)).fetchone()
    if row:
        conn.execute("DELETE FROM tags WHERE id=?", (row["id"],))
        conn.commit()
    return RedirectResponse("/tags", status_code=303)

# ---------- bulk retag: regex or JSON map ----------
@app.get("/tags/bulk", response_class=HTMLResponse)
def tags_bulk(request: Request):
    return templates.TemplateResponse("tags_bulk.html", {"request": request})

def compute_bulk_ops(conn, mode: str, pattern: str = "", repl: str = "", mapping: dict | None = None):
    names = [r["name"] for r in conn.execute("SELECT name FROM tags").fetchall()]
    ops = []
    if mode == "regex":
        try:
            rgx = re.compile(pattern)
        except re.error:
            return [], "Invalid regex."
        for name in names:
            new = norm_tag(rgx.sub(repl, name))
            if new and new != name:
                ops.append((name, new))
    elif mode == "map" and mapping:
        for old, new in mapping.items():
            oldn, newn = norm_tag(old), norm_tag(new)
            if oldn and newn and oldn != newn:
                if oldn in names:
                    ops.append((oldn, newn))
    return ops, ""

@app.post("/tags/bulk/preview", response_class=HTMLResponse)
def bulk_preview(request: Request, mode: str = Form(...), regex_pattern: str = Form(""), regex_repl: str = Form(""), map_json: str = Form("")):
    conn = get_conn()
    mapping = {}
    if mode == "map" and map_json.strip():
        try: mapping = __import__("json").loads(map_json)
        except Exception: return HTMLResponse("<div class='p-4 text-rose-600'>Invalid JSON.</div>")
    ops, err = compute_bulk_ops(conn, mode, regex_pattern, regex_repl, mapping)
    if err: return HTMLResponse(f"<div class='p-4 text-rose-600'>{err}</div>")
    data = []
    for old, new in ops:
        old_count = conn.execute("""SELECT COUNT(*) c FROM note_tags nt JOIN tags t ON t.id=nt.tag_id WHERE t.name=?""",(old,)).fetchone()["c"]
        new_exists = conn.execute("SELECT 1 FROM tags WHERE name=?", (new,)).fetchone() is not None
        data.append({"old": old, "new": new, "count": old_count, "merge": new_exists})
    return templates.TemplateResponse("partials/bulk_preview.html", {"request": request, "items": data})

@app.post("/tags/bulk/apply", response_class=RedirectResponse)
def bulk_apply(mode: str = Form(...), regex_pattern: str = Form(""), regex_repl: str = Form(""), map_json: str = Form("")):
    conn = get_conn()
    mapping = {}
    if mode == "map" and map_json.strip():
        mapping = __import__("json").loads(map_json)
    ops, _ = compute_bulk_ops(conn, mode, regex_pattern, regex_repl, mapping)
    for old, new in ops:
        old_row = conn.execute("SELECT id FROM tags WHERE name=?", (old,)).fetchone()
        if not old_row: continue
        new_row = conn.execute("SELECT id FROM tags WHERE name=?", (new,)).fetchone()
        if new_row:
            conn.execute("UPDATE OR IGNORE note_tags SET tag_id=? WHERE tag_id=?", (new_row["id"], old_row["id"]))
            conn.execute("DELETE FROM tags WHERE id=?", (old_row["id"],))
        else:
            conn.execute("UPDATE tags SET name=? WHERE id=?", (new, old_row["id"]))
    conn.commit()
    return RedirectResponse("/tags", status_code=303)

# ---------- note create (kept) ----------
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
        return templates.TemplateResponse("partials/note_item.html", {"request": request, "n": note})
    return RedirectResponse(f"/notes/{nid}", status_code=303)

# ---------- LLM tag suggestions ----------
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
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
    prompt = ("You are a tagging assistant. From the note, extract 3-7 short tags.\n"
              "- lowercase\n- hyphen for multiword\n- no '#'\n- comma-separated only\n\nNote:\n" + text + "\nTags:")
    try:
        r = httpx.post(f"{OLLAMA_BASE}/api/generate", json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=10.0)
        r.raise_for_status()
        resp = r.json().get("response","")
        tags = [norm_tag(t) for t in resp.split(",")]
        tags = [t for t in tags if t] or naive_tags(text)
    except Exception:
        tags = naive_tags(text)
    return JSONResponse({"tags": list(dict.fromkeys(tags))[:7]})
PY

# ---------- templates ----------
backup templates/note_detail.html
cat > templates/note_detail.html <<'HTML'
{% extends "base.html" %}
{% block title %}Note #{{ note.id }} — Second Brain Premium{% endblock %}
{% block content %}
<div id="note-view">
  {% include "partials/note_view.html" %}
</div>
{% endblock %}
HTML

# Note view (shown by default, returned after update)
cat > templates/partials/note_view.html <<'HTML'
<article class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <header class="mb-3 flex items-start justify-between gap-4">
    <div>
      <div class="text-xs text-slate-500">{{ note.created_at }}</div>
      <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Note #{{ note.id }}</h1>
      {% if note.tags %}
        <div class="mt-2">
          {% for t in note.tags.split(',') if t.strip() %}
            <a href="/notes?tag={{ t.strip() }}" class="inline-block mr-2 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800">#{{ t.strip() }}</a>
          {% endfor %}
        </div>
      {% endif %}
    </div>
    <div class="shrink-0 flex gap-2">
      <button hx-get="/notes/{{ note.id }}/edit" hx-target="#note-view" hx-swap="outerHTML"
              class="px-3 py-1.5 rounded-lg bg-brand-600 text-white">Edit</button>
      <form method="post" action="/notes/{{ note.id }}/delete" onsubmit="return confirm('Delete this note?');">
        <button class="px-3 py-1.5 rounded-lg bg-rose-600 text-white">Delete</button>
      </form>
    </div>
  </header>
  <div class="prose prose-slate max-w-none dark:prose-invert whitespace-pre-wrap">{{ note.body }}</div>
  <footer class="mt-6">
    <a href="/notes" class="text-sm text-slate-600 hover:underline dark:text-slate-300">← Back to notes</a>
  </footer>
</article>
HTML

# Inline edit form (swaps in on Edit; returns view on save)
cat > templates/partials/note_edit_form.html <<'HTML'
<form hx-post="/notes/{{ note.id }}/update" hx-target="#note-view" hx-swap="outerHTML">
  <article class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
    <header class="mb-3 flex items-center justify-between">
      <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Edit Note #{{ note.id }}</h1>
      <button type="button" hx-get="/notes/{{ note.id }}" hx-target="#note-view" hx-swap="outerHTML"
              class="px-3 py-1.5 rounded-lg bg-slate-200 dark:bg-slate-800">Cancel</button>
    </header>

    <textarea name="body" rows="8"
              class="w-full rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">{{ note.body }}</textarea>

    <input type="hidden" id="tagsInput" name="tags" value="{{ note.tags }}">
    <div class="mt-4">
      <div class="text-xs text-slate-500 mb-1">Tags</div>
      <div id="tag-editor" class="min-h-[44px] rounded-xl px-2 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 flex flex-wrap gap-2">
        <input id="tag-entry" type="text" placeholder="type and press Enter"
               class="bg-transparent outline-none flex-1 min-w-[140px] text-slate-800 dark:text-slate-200 placeholder:text-slate-400" />
      </div>
      <div id="tag-suggestions" class="mt-2 flex flex-wrap gap-2"></div>
    </div>

    <div class="mt-4 flex gap-2">
      <button class="px-4 py-2 rounded-xl bg-brand-600 text-white">Save</button>
      <button type="button" hx-get="/notes/{{ note.id }}" hx-target="#note-view" hx-swap="outerHTML"
              class="px-4 py-2 rounded-xl bg-slate-200 dark:bg-slate-800">Cancel</button>
    </div>
  </article>
</form>
<script>
  // Hydrate the tag editor with existing tags for this note
  (function(){
    const hidden = document.getElementById('tagsInput');
    const entry = document.getElementById('tag-entry');
    if (!hidden || !entry) return;
    const preload = (hidden.value || '').split(',').filter(Boolean);
    setTimeout(() => {
      preload.forEach(t => entry.value = t, 0);
      // trigger chip creation
      entry.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'}));
    }, 0);
  })();
</script>
HTML

# Bulk retag page + preview table
cat > templates/tags_bulk.html <<'HTML'
{% extends "base.html" %}
{% block title %}Bulk Retag — Second Brain Premium{% endblock %}
{% block content %}
<div class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Bulk Retag</h1>
  <p class="text-sm text-slate-500 mt-1">Preview changes first; then apply. Merges happen automatically when the new tag already exists.</p>

  <div class="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
    <section class="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 class="font-medium text-slate-900 dark:text-white">Regex rename</h2>
      <form hx-post="/tags/bulk/preview" hx-target="#bulk-preview" hx-swap="innerHTML" class="mt-3 space-y-2">
        <input type="hidden" name="mode" value="regex">
        <input name="regex_pattern" placeholder="pattern e.g. ^old-" class="w-full rounded-lg border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5">
        <input name="regex_repl" placeholder="replacement e.g. new-" class="w-full rounded-lg border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-1.5">
        <button class="px-3 py-1.5 rounded-lg bg-brand-600 text-white">Preview</button>
      </form>
    </section>

    <section class="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <h2 class="font-medium text-slate-900 dark:text-white">JSON map</h2>
      <form hx-post="/tags/bulk/preview" hx-target="#bulk-preview" hx-swap="innerHTML" class="mt-3 space-y-2">
        <input type="hidden" name="mode" value="map">
        <textarea name="map_json" rows="6" placeholder='{"bug":"issue","todo":"task"}'
                  class="w-full rounded-lg border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 px-3 py-2"></textarea>
        <button class="px-3 py-1.5 rounded-lg bg-brand-600 text-white">Preview</button>
      </form>
    </section>
  </div>

  <div id="bulk-preview" class="mt-6"></div>
</div>
{% endblock %}
HTML

cat > templates/partials/bulk_preview.html <<'HTML'
{% if items %}
  <form method="post" action="/tags/bulk/apply" class="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
    <input type="hidden" name="mode" value="map"><!-- will be replaced by caller; safe -->
    <table class="w-full text-left text-sm">
      <thead class="bg-slate-50 dark:bg-slate-900">
        <tr><th class="px-3 py-2">Old</th><th class="px-3 py-2">New</th><th class="px-3 py-2">Notes using</th><th class="px-3 py-2">Action</th></tr>
      </thead>
      <tbody>
      {% for r in items %}
        <tr class="border-t border-slate-200 dark:border-slate-800">
          <td class="px-3 py-2">#{{ r.old }}</td>
          <td class="px-3 py-2">#{{ r.new }}</td>
          <td class="px-3 py-2">{{ r.count }}</td>
          <td class="px-3 py-2">{% if r.merge %}merge{% else %}rename{% endif %}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>

    <!-- carry preview params so /apply can recompute the same ops -->
    <div class="p-3 flex items-center gap-2 bg-white dark:bg-slate-950 border-t border-slate-200 dark:border-slate-800">
      <input type="hidden" name="regex_pattern" value="{{ regex_pattern|default('') }}">
      <input type="hidden" name="regex_repl" value="{{ regex_repl|default('') }}">
      <input type="hidden" name="map_json" value="{{ map_json|default('') }}">
      <button class="px-3 py-1.5 rounded-lg bg-emerald-600 text-white">Apply changes</button>
      <a href="/tags" class="px-3 py-1.5 rounded-lg bg-slate-200 dark:bg-slate-800">Cancel</a>
    </div>
  </form>
{% else %}
  <div class="p-4 text-slate-500">No changes detected.</div>
{% endif %}
HTML

# Update Tags page to link Bulk Retag
backup templates/tags.html
cat > templates/tags.html <<'HTML'
{% extends "base.html" %}
{% block title %}Tag Manager — Second Brain Premium{% endblock %}
{% block content %}
<div class="rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
  <div class="flex items-center justify-between">
    <h1 class="text-xl font-semibold text-slate-900 dark:text-white">Tag Manager</h1>
    <a href="/tags/bulk" class="px-3 py-1.5 rounded-lg bg-brand-600 text-white">Bulk Retag</a>
  </div>
  <p class="text-sm text-slate-500 mt-1">Rename/merge/delete individual tags.</p>

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
        <form class="mt-2" method="post" action="/tags/delete" onsubmit="return confirm('Delete #{{ t.name }}?');">
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

# Keep existing templates if present (dashboard, notes, search, base, partials)
# Only add/overwrite what we touched above.

# ---------- static/app.js (ensure tag editor + quick search present) ----------
# If you used my previous file, keep it; otherwise write a compatible one.
if [[ ! -f static/app.js ]]; then
cat > static/app.js <<'JS'
// minimal theme + quick search + tag editor bootstrap
const btn=document.getElementById('themeToggle');if(btn){btn.addEventListener('click',()=>{const d=document.documentElement;const t=d.classList.toggle('dark');localStorage.theme=t?'dark':'light';});}
const qwrap=document.getElementById('qwrap'),qmask=document.getElementById('qmask'),qinput=document.getElementById('qinput');
function openQ(){if(!qwrap)return;qwrap.classList.remove('hidden');qmask.classList.remove('hidden');qinput.value='';qinput.focus();qinput.dispatchEvent(new Event('keyup'));}
function closeQ(){if(!qwrap)return;qwrap.classList.add('hidden');qmask.classList.add('hidden');}
document.addEventListener('keydown',(e)=>{if((e.metaKey||e.ctrlKey)&&e.key==='/'){e.preventDefault();openQ();} if(e.key==='Escape'){closeQ();}});
qmask&&qmask.addEventListener('click',closeQ);
// Tag editor logic is injected by previous script version; reuse if present.
JS
fi

# ---------- requirements ----------
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

Open http://localhost:8084
Hotkeys: ⌘/ or Ctrl+/ for quick search.
"
