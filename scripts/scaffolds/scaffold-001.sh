#!/usr/bin/env bash
set -euo pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="$(pwd)"

backup_if_exists () {
  local path="$1"
  if [[ -f "$path" ]]; then
    mv "$path" "$path.$STAMP.bak"
    echo "  • Backed up $path -> $path.$STAMP.bak"
  fi
}

mkdir -p templates/partials static

echo "==> Writing Python app (FastAPI + Ollama tag suggestions)…"
backup_if_exists app.py
cat > app.py <<'PY'
from datetime import datetime
from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import pathlib, sqlite3, os, re, json, asyncio
from collections import Counter
import httpx

app = FastAPI(title="Second Brain Premium")

BASE_DIR = pathlib.Path(__file__).parent.resolve()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

def get_conn():
    db = BASE_DIR / "notes.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            body TEXT NOT NULL,
            tags TEXT,
            created_at TEXT
        )
    """)
    return conn

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    c = get_conn().cursor()
    total_notes = c.execute("SELECT COUNT(*) AS c FROM notes").fetchone()["c"]
    recent = c.execute(
        "SELECT id, body, tags, created_at FROM notes ORDER BY datetime(created_at) DESC LIMIT 5"
    ).fetchall()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "stats": {"notes": total_notes}, "recent": recent},
    )

@app.get("/notes", response_class=HTMLResponse)
async def notes_page(request: Request, tag: str = ""):
    c = get_conn().cursor()
    if tag:
        rows = c.execute(
            "SELECT id, body, tags, created_at "
            "FROM notes WHERE (','||IFNULL(tags,'')||',') LIKE ? "
            "ORDER BY datetime(created_at) DESC",
            (f"%,{tag},%",),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT id, body, tags, created_at FROM notes "
            "ORDER BY datetime(created_at) DESC"
        ).fetchall()
    return templates.TemplateResponse("notes.html", {"request": request, "notes": rows, "active_tag": tag})

@app.get("/notes/{note_id}", response_class=HTMLResponse)
async def note_detail(request: Request, note_id: int):
    c = get_conn().cursor()
    row = c.execute(
        "SELECT id, body, tags, created_at FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if not row:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("note_detail.html", {"request": request, "note": row})

@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    c = get_conn().cursor()
    rows = []
    if q:
        rows = c.execute(
            "SELECT id, body, tags, created_at FROM notes "
            "WHERE body LIKE ? OR IFNULL(tags,'') LIKE ? "
            "ORDER BY datetime(created_at) DESC",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
    return templates.TemplateResponse("search.html", {"request": request, "q": q, "notes": rows})

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

@app.post("/notes", response_class=HTMLResponse)
async def create_note(request: Request, body: str = Form(...), tags: str = Form("")):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat(timespec="seconds")
    # normalize tags: strip/uniq/lower
    tag_list = [t.strip().lower().replace("#","") for t in tags.split(",") if t.strip()]
    tag_list = list(dict.fromkeys(tag_list))
    tags_norm = ",".join(tag_list) if tag_list else None

    c.execute("INSERT INTO notes (body, tags, created_at) VALUES (?, ?, ?)", (body, tags_norm, now))
    conn.commit()
    note_id = c.lastrowid
    row = c.execute(
        "SELECT id, body, tags, created_at FROM notes WHERE id = ?", (note_id,)
    ).fetchone()

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/note_item.html", {"request": request, "n": row})
    return RedirectResponse(f"/notes/{note_id}", status_code=303)

# ---------- Automated Tag Suggestions (Ollama) ----------
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
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            # Prefer the /api/generate endpoint for simple prompts
            req = {
                "model": OLLAMA_MODEL,
                "prompt": TAG_PROMPT + text + "\nTags:",
                "stream": False,
            }
            r = await client.post(f"{OLLAMA_BASE}/api/generate", json=req)
            r.raise_for_status()
            data = r.json()
            raw = data.get("response", "")
            tags = [t.strip().lower().replace("#","").replace(" ", "-") for t in raw.split(",") if t.strip()]
            tags = [re.sub(r"[^a-z0-9\-]", "", t) for t in tags]
            tags = [t for t in tags if t]
            if not tags:
                tags = naive_tags(text)
    except Exception:
        tags = naive_tags(text)

    # uniq + cap length
    tags = list(dict.fromkeys(tags))[:7]
    return JSONResponse({"tags": tags})
PY

echo "==> Writing templates…"
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

  <!-- Tailwind CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'Arial'] },
          colors: { brand: {50:'#eef2ff', 500:'#6366f1', 600:'#4f46e5', 700:'#4338ca'} }
        }
      },
      darkMode: 'class'
    }
  </script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">

  <!-- Alpine + HTMX -->
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>

  <link rel="icon" href="data:,">
</head>

<body class="font-sans min-h-screen bg-gradient-to-br from-indigo-500 via-fuchsia-500 to-purple-600
             dark:from-slate-950 dark:via-slate-950 dark:to-zinc-900">
  <header class="sticky top-0 z-40 bg-white/70 dark:bg-slate-900/70 backdrop-blur border-b border-white/10">
    <nav class="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between">
      <a href="/" class="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100">
        <span class="text-2xl">🧠</span>
        <span>Second Brain Premium</span>
      </a>
      <ul class="flex items-center gap-4 text-slate-700 dark:text-slate-300">
        <li><a class="hover:text-slate-900 dark:hover:text-white" href="/">Dashboard</a></li>
        <li><a class="hover:text-slate-900 dark:hover:text-white" href="/notes">Notes</a></li>
        <li><a class="hover:text-slate-900 dark:hover:text-white" href="/search">Search</a></li>
        <li><a class="hover:text-slate-900 dark:hover:text-white" href="/settings">Settings</a></li>
        <li>
          <button id="themeToggle"
                  class="rounded-xl px-3 py-1.5 bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm">
            Toggle Theme
          </button>
        </li>
      </ul>
    </nav>
  </header>

  <main class="mx-auto max-w-6xl px-4 py-8">
    {% block content %}{% endblock %}
  </main>

  <footer class="mx-auto max-w-6xl px-4 pb-10 text-sm text-white/80">
    <div class="mt-8 text-center">Built with FastAPI • Jinja • Tailwind • HTMX • Ollama</div>
  </footer>

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
  <!-- Quick Capture -->
  <section class="lg:col-span-2 rounded-2xl bg-white/95 dark:bg-slate-950/90 shadow-xl ring-1 ring-black/5 p-6">
    <h2 class="text-lg font-semibold text-slate-900 dark:text-white">Quick Capture</h2>
    <form class="mt-4 space-y-4"
          hx-post="/notes"
          hx-target="#recent-notes"
          hx-swap="afterbegin"
          hx-on:htmx:afterRequest="if(event.detail.successful){ this.reset(); window.TagEditor && window.TagEditor.reset(); }">
      <label class="sr-only" for="body">What's on your mind?</label>
      <textarea id="body" name="body" required rows="5"
                class="w-full rounded-xl border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                placeholder="What's on your mind?"></textarea>

      <!-- Smart Tag Editor -->
      <input type="hidden" id="tagsInput" name="tags" />
      <div>
        <div class="text-xs text-slate-500 mb-1">Tags</div>
        <div id="tag-editor"
             class="min-h-[44px] rounded-xl px-2 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 flex flex-wrap gap-2">
          <!-- tokens injected here -->
          <input id="tag-entry" type="text" placeholder="type and press Enter"
                 class="bg-transparent outline-none flex-1 min-w-[140px] text-slate-800 dark:text-slate-200 placeholder:text-slate-400" />
        </div>
        <div id="tag-suggestions" class="mt-2 flex flex-wrap gap-2"></div>
      </div>

      <button type="submit"
              class="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white shadow">
        Save Note
      </button>
    </form>
  </section>

  <!-- Stats -->
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

<!-- Recent Notes -->
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
      <button class="px-3 py-1.5 rounded-xl bg-slate-900 text-white dark:bg-white dark:text-slate-900">
        Filter
      </button>
    </form>
  </div>

  <ul class="mt-4 divide-y divide-slate-200/80 dark:divide-white/10">
    {% for n in notes %}
      {% set note=n %}
      {% include 'partials/note_item.html' with context %}
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
  <div class="prose prose-slate max-w-none dark:prose-invert whitespace-pre-wrap">
    {{ note.body }}
  </div>
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
        {% set note=n %}
        {% include 'partials/note_item.html' with context %}
      {% else %}
        <li class="py-8 text-slate-500">No results.</li>
      {% endfor %}
    </ul>
  {% endif %}
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
  <p class="mt-2 text-slate-600 dark:text-slate-300">App preferences and integrations.</p>

  <div class="mt-6 space-y-6">
    <section>
      <h2 class="font-medium text-slate-900 dark:text-white">Theme</h2>
      <p class="text-sm text-slate-500">Use the “Toggle Theme” button in the header. Preference is saved to your browser.</p>
    </section>

    <section>
      <h2 class="font-medium text-slate-900 dark:text-white">Apple Shortcuts</h2>
      <p class="text-sm text-slate-500">POST to <code>/notes</code> with <code>body</code> and <code>tags</code> form fields.</p>
    </section>

    <section>
      <h2 class="font-medium text-slate-900 dark:text-white">Ollama</h2>
      <p class="text-sm text-slate-500">Set <code>OLLAMA_BASE_URL</code> and <code>OLLAMA_MODEL</code> env vars if needed. Defaults: <code>http://localhost:11434</code>, <code>llama3.1:8b</code>.</p>
    </section>
  </div>
</div>
{% endblock %}
HTML

echo "==> Writing static JS (theme + tag editor + LLM suggestions)…"
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

// --- Tiny Tag Editor + Suggestions ---
(function () {
  const editor = document.getElementById('tag-editor');
  const entry  = document.getElementById('tag-entry');
  const hidden = document.getElementById('tagsInput');
  const suggestWrap = document.getElementById('tag-suggestions');
  const noteBody = document.getElementById('body');
  if (!editor || !entry || !hidden) return;

  let tags = new Set();

  function syncHidden() { hidden.value = Array.from(tags).join(','); }
  function renderTokens() {
    // remove all chips except the input
    Array.from(editor.querySelectorAll('.tag-chip')).forEach(el => el.remove());
    tags.forEach(t => {
      const chip = document.createElement('span');
      chip.className = 'tag-chip inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200';
      chip.innerHTML = `#${t} <button type="button" class="remove text-xs opacity-70 hover:opacity-100">×</button>`;
      chip.querySelector('button.remove').addEventListener('click', () => { tags.delete(t); renderTokens(); syncHidden(); });
      editor.insertBefore(chip, entry);
    });
  }
  function addTag(raw) {
    const t = raw.trim().toLowerCase().replace(/^#/, '').replace(/\s+/g, '-').replace(/[^a-z0-9\-]/g, '');
    if (!t) return;
    tags.add(t);
    renderTokens(); syncHidden();
  }
  function parseEntryAndAdd() {
    const parts = entry.value.split(/[,\s]+/).filter(Boolean);
    parts.forEach(addTag);
    entry.value = '';
  }

  // expose for HTMX form reset hook
  window.TagEditor = { reset() { tags = new Set(); renderTokens(); syncHidden(); } };

  entry.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      parseEntryAndAdd();
    } else if (e.key === 'Backspace' && entry.value === '') {
      // quick remove last tag
      const last = Array.from(tags).pop();
      if (last) { tags.delete(last); renderTokens(); syncHidden(); }
    }
  });

  // LLM suggestions with debounce
  let timer = null;
  const debounce = (fn, ms=600) => (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };

  async function fetchSuggestions(text) {
    try {
      const res = await fetch('/tags/suggest', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ text })
      });
      if (!res.ok) throw new Error('bad response');
      const data = await res.json();
      renderSuggestions(Array.isArray(data.tags) ? data.tags : []);
    } catch (e) {
      renderSuggestions([]);
    }
  }

  function renderSuggestions(list) {
    suggestWrap.innerHTML = '';
    if (!list.length) return;
    list.forEach(tag => {
      if (tags.has(tag)) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'px-2 py-1 rounded-lg bg-brand-600 text-white text-xs hover:bg-brand-700';
      btn.textContent = `#${tag}`;
      btn.addEventListener('click', () => { addTag(tag); });
      suggestWrap.appendChild(btn);
    });
  }

  if (noteBody) {
    noteBody.addEventListener('input', debounce(() => {
      const text = noteBody.value.trim();
      if (text.length < 8) { renderSuggestions([]); return; }
      fetchSuggestions(text);
    }, 650));
  }
})();
JS

echo "==> Writing requirements.txt…"
backup_if_exists requirements.txt
cat > requirements.txt <<'REQ'
fastapi==0.115.0
uvicorn[standard]==0.30.6
jinja2==3.1.4
httpx==0.27.2
REQ

echo "==> Done.

Quick start:
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  # (optional) export OLLAMA_BASE_URL and OLLAMA_MODEL
  uvicorn app:app --reload --host 0.0.0.0 --port 8084

Open http://localhost:8084
"
