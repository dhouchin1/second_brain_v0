#!/usr/bin/env bash
# scaffold-008.sh
set -euo pipefail
STAMP="$(date +%Y%m%d-%H%M%S)"
b(){ [[ -f "$1" ]] && mv "$1" "$1.$STAMP.bak" && echo "• backup: $1 -> $1.$STAMP.bak" || true; }

# --- Files ---
b discord_bot.py
cat > discord_bot.py <<'PY'
import os, re, math, json, asyncio, typing
import aiosqlite
import httpx
import discord
from discord import app_commands
from discord.ext import commands

try:
    import numpy as np
except Exception:
    np = None

# ---------- Env / Config ----------
DB_PATH         = os.getenv("NOTES_DB_PATH", "./notes.db")
APP_BASE_URL    = os.getenv("APP_BASE_URL", "http://localhost:8084")
DISCORD_TOKEN   = os.getenv("DISCORD_TOKEN", "")
DISCORD_GUILD   = os.getenv("DISCORD_GUILD_ID")  # optional (faster command sync)
OLLAMA_BASE     = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
EMBED_BASE      = os.getenv("OLLAMA_EMBED_BASE_URL", "http://localhost:11434")
EMBED_MODEL     = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")
PAGE_SIZE       = 5  # search results in Discord

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

def slugify_tag(s: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "", s.strip().lower().replace("#","").replace(" ", "-"))

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()

async def ensure_tag(db, name: str) -> int:
    name = slugify_tag(name)
    cur = await db.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
    await db.commit()
    if cur.lastrowid:
        return cur.lastrowid
    row = await db.execute_fetchone("SELECT id FROM tags WHERE name=?", (name,))
    return row["id"]

async def set_note_tags(db, note_id: int, tags_csv: str):
    names = [slugify_tag(x) for x in (tags_csv or "").split(",") if x.strip()]
    names = [n for n in dict.fromkeys(names) if n]
    await db.execute("DELETE FROM note_tags WHERE note_id=?", (note_id,))
    for nm in names:
        tid = await ensure_tag(db, nm)
        await db.execute("INSERT OR IGNORE INTO note_tags(note_id, tag_id) VALUES (?,?)", (note_id, tid))
    await db.commit()

async def add_note(db, body: str, tags: str) -> int:
    from datetime import datetime
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur = await db.execute("INSERT INTO notes(body, created_at) VALUES (?,?)", (body, now))
    nid = cur.lastrowid
    await set_note_tags(db, nid, tags)
    await db.commit()
    return nid

async def map_note_tags(db, ids: typing.List[int]) -> dict[int,str]:
    if not ids: return {}
    placeholders = ",".join("?"*len(ids))
    sql = f"""
    SELECT n.id, GROUP_CONCAT(t.name) AS tags
    FROM notes n
    LEFT JOIN note_tags nt ON nt.note_id=n.id
    LEFT JOIN tags t ON t.id=nt.tag_id
    WHERE n.id IN ({placeholders})
    GROUP BY n.id
    """
    rows = await db.execute_fetchall(sql, ids)
    return {r["id"]: (r["tags"] or "") for r in rows}

async def embed_text(text: str) -> typing.List[float]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{EMBED_BASE}/api/embeddings", json={"model": EMBED_MODEL, "prompt": text})
        r.raise_for_status()
        data = r.json()
        return data.get("embedding") or (data.get("data",[{}])[0].get("embedding"))

def cosine(a, b):
    if np is not None:
        a = np.asarray(a, dtype=np.float32)
        b = np.asarray(b, dtype=np.float32)
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0: return 0.0
        return float(np.dot(a, b) / denom)
    dot = sum(x*y for x,y in zip(a,b))
    na  = math.sqrt(sum(x*x for x in a))
    nb  = math.sqrt(sum(y*y for y in b))
    if na == 0 or nb == 0: return 0.0
    return dot / (na * nb)

async def semantic_search(db, query: str, limit: int = PAGE_SIZE):
    qvec = await embed_text(query)
    rows = await db.execute_fetchall("SELECT note_id, dim, vec FROM note_embeddings")
    out = []
    for r in rows:
        if r["dim"] != len(qvec): continue
        blob = r["vec"]
        if np is None:
            v = [float(x) for x in blob.decode("utf-8").split(",") if x]
        else:
            v = np.frombuffer(blob, dtype=np.float32)
        out.append((r["note_id"], cosine(v, qvec)))
    out.sort(key=lambda x: x[1], reverse=True)
    top_ids = [i for (i, _) in out[:limit]]
    if not top_ids: return []
    ph = ",".join("?"*len(top_ids))
    rows = await db.execute_fetchall(f"SELECT id, body, created_at FROM notes WHERE id IN ({ph})", top_ids)
    order = {nid:i for i,nid in enumerate(top_ids)}
    rows.sort(key=lambda r: order[r["id"]])
    return rows

async def fts_search(db, q: str, limit: int = PAGE_SIZE):
    sql = """
    SELECT n.id, n.body, n.created_at
    FROM notes_fts f JOIN notes n ON n.id=f.rowid
    WHERE notes_fts MATCH ?
    ORDER BY bm25(notes_fts) LIMIT ?
    """
    return await db.execute_fetchall(sql, (q, limit))

async def ensure_embedding_for_note(db, note_id: int, body: str):
    try:
        vec = await embed_text(body)
        if np is None:
            blob = (",".join(f"{float(x):.7f}" for x in vec)).encode("utf-8")
        else:
            blob = np.asarray(vec, dtype=np.float32).tobytes()
        await db.execute(
            "INSERT INTO note_embeddings(note_id, dim, vec) VALUES (?,?,?) "
            "ON CONFLICT(note_id) DO UPDATE SET dim=excluded.dim, vec=excluded.vec",
            (note_id, len(vec), blob)
        )
        await db.commit()
    except Exception as e:
        # keep UX flowing even if embed fails
        print("embed error:", e)

async def suggest_tags_llm(text: str) -> list[str]:
    prompt = ("You are a tagging assistant. From the note, extract 3-7 short tags.\n"
              "- lowercase\n- hyphen for multiword\n- no '#'\n- comma-separated only\n\nNote:\n" + text + "\nTags:")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{OLLAMA_BASE}/api/generate", json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False})
            r.raise_for_status()
            raw = r.json().get("response","")
    except Exception:
        raw = ""
    tags = [slugify_tag(t) for t in raw.split(",")]
    return [t for t in dict.fromkeys(tags) if t][:7]

# ---------- Discord bot ----------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    try:
        synced = []
        if DISCORD_GUILD:
            g = discord.Object(id=int(DISCORD_GUILD))
            synced = await bot.tree.sync(guild=g)
        else:
            synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print("Sync error:", e)

# ---- /note add (modal) ----
class AddNoteModal(discord.ui.Modal, title="Add Note"):
    body = discord.ui.TextInput(label="Body", style=discord.TextStyle.long, required=True, max_length=4000)
    tags = discord.ui.TextInput(label="Tags (comma-separated)", required=False, max_length=200, placeholder="project-x, research, idea")
    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.executescript("PRAGMA journal_mode=WAL;")
            nid = await add_note(db, str(self.body), str(self.tags))
            # best-effort embed
            await ensure_embedding_for_note(db, nid, str(self.body))
        url = f"{APP_BASE_URL}/notes/{nid}"
        await interaction.followup.send(f"✅ Note saved: {url}", ephemeral=True)

@bot.tree.command(name="note_add", description="Add a note via modal input")
async def note_add(interaction: discord.Interaction):
    await interaction.response.send_modal(AddNoteModal())

# ---- /note quick ----
@bot.tree.command(name="note_quick", description="Add a note quickly")
@app_commands.describe(body="Note body", tags="Comma-separated tags (optional)")
async def note_quick(interaction: discord.Interaction, body: str, tags: str = ""):
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript("PRAGMA journal_mode=WAL;")
        nid = await add_note(db, body, tags)
        await ensure_embedding_for_note(db, nid, body)
    url = f"{APP_BASE_URL}/notes/{nid}"
    await interaction.followup.send(f"✅ Note saved: {url}", ephemeral=True)

# ---- /note get ----
@bot.tree.command(name="note_get", description="Get a note by ID")
@app_commands.describe(id="Note ID")
async def note_get(interaction: discord.Interaction, id: int):
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await db.execute_fetchone("SELECT id, body, created_at FROM notes WHERE id=?", (id,))
        if not row:
            await interaction.followup.send("Not found.", ephemeral=True); return
        tagmap = await map_note_tags(db, [row["id"]])
        tags = tagmap.get(row["id"], "")
    url = f"{APP_BASE_URL}/notes/{row['id']}"
    title = (row["body"].splitlines()[0] or f"Note #{row['id']}")[:80]
    embed = discord.Embed(title=title, description=(row["body"][:500] + ("…" if len(row["body"])>500 else "")), color=0x5865F2)
    embed.add_field(name="Tags", value=(tags or "—"), inline=False)
    embed.add_field(name="Created", value=row["created_at"], inline=True)
    embed.add_field(name="Open", value=url, inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)

# ---- /note recent ----
@bot.tree.command(name="note_recent", description="Show recent notes")
@app_commands.describe(count="How many (1-10)")
async def note_recent(interaction: discord.Interaction, count: app_commands.Range[int,1,10]=5):
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT id, body, created_at FROM notes ORDER BY datetime(created_at) DESC LIMIT ?", (count,)
        )
        tagmap = await map_note_tags(db, [r["id"] for r in rows])
    if not rows:
        await interaction.followup.send("No notes yet.", ephemeral=True); return
    embeds=[]
    for r in rows:
        url = f"{APP_BASE_URL}/notes/{r['id']}"
        t = (r["body"].splitlines()[0] or f"Note #{r['id']}")[:80]
        e = discord.Embed(title=t, description=(r["body"][:300] + ("…" if len(r["body"])>300 else "")), color=0x5865F2)
        e.add_field(name="Tags", value=(tagmap.get(r["id"], "") or "—"), inline=False)
        e.add_field(name="Created", value=r["created_at"], inline=True)
        e.add_field(name="Open", value=url, inline=True)
        embeds.append(e)
    await interaction.followup.send(embeds=embeds[:10], ephemeral=True)

# ---- /note search ----
@bot.tree.command(name="note_search", description="Search notes (FTS or Semantic)")
@app_commands.describe(q="Query string", embed="Semantic instead of text search (requires embeddings)")
async def note_search(interaction: discord.Interaction, q: str, embed: bool=False):
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if embed:
            try:
                rows = await semantic_search(db, q, limit=PAGE_SIZE)
            except Exception as e:
                rows = []
        else:
            rows = await fts_search(db, q, limit=PAGE_SIZE)
        tagmap = await map_note_tags(db, [r["id"] for r in rows])
    if not rows:
        await interaction.followup.send("No results.", ephemeral=True); return
    embeds=[]
    for r in rows:
        url = f"{APP_BASE_URL}/notes/{r['id']}"
        t = (r["body"].splitlines()[0] or f"Note #{r['id']}")[:80]
        e = discord.Embed(title=t, description=(r["body"][:300] + ("…" if len(r["body"])>300 else "")), color=0x57F287 if embed else 0x5865F2)
        e.add_field(name="Tags", value=(tagmap.get(r["id"], "") or "—"), inline=False)
        e.add_field(name="Open", value=url, inline=True)
        embeds.append(e)
    await interaction.followup.send(embeds=embeds, ephemeral=True)

# ---- /tags top ----
@bot.tree.command(name="tags_top", description="Most used tags")
@app_commands.describe(count="How many (1-20)")
async def tags_top(interaction: discord.Interaction, count: app_commands.Range[int,1,20]=10):
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall("""
            SELECT t.name, COUNT(nt.note_id) usage
            FROM tags t LEFT JOIN note_tags nt ON nt.tag_id=t.id
            GROUP BY t.id ORDER BY usage DESC, t.name ASC LIMIT ?
        """, (count,))
    if not rows:
        await interaction.followup.send("No tags yet.", ephemeral=True); return
    lines = [f"• **#{r['name']}** — {r['usage']}" for r in rows]
    await interaction.followup.send("\n".join(lines), ephemeral=True)

# ---- /tags suggest (modal) ----
class SuggestTagsModal(discord.ui.Modal, title="Suggest Tags"):
    text = discord.ui.TextInput(label="Paste note text", style=discord.TextStyle.long, required=True, max_length=4000)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        tags = await suggest_tags_llm(str(self.text))
        if not tags:
            await interaction.followup.send("No suggestions.", ephemeral=True); return
        await interaction.followup.send("Suggestions: " + " ".join(f"`#{t}`" for t in tags), ephemeral=True)

@bot.tree.command(name="tags_suggest", description="Get tag suggestions from text")
async def tags_suggest(interaction: discord.Interaction):
    await interaction.response.send_modal(SuggestTagsModal())

# ---------- Entry ----------
async def amain():
    if not DISCORD_TOKEN:
        raise RuntimeError("Set DISCORD_TOKEN env var.")
    await init_db()
    # discord.py requires running the bot; sync per-guild for fast availability if guild id provided
    if DISCORD_GUILD:
        bot.tree.copy_global_to(guild=discord.Object(id=int(DISCORD_GUILD)))
    await bot.start(DISCORD_TOKEN)

def main():
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
PY

# .env example
b .env.example
cat > .env.example <<'ENV'
# --- Discord bot ---
DISCORD_TOKEN=put-your-bot-token-here
DISCORD_GUILD_ID= # optional; if set, commands sync instantly to this guild

# --- App / DB paths ---
NOTES_DB_PATH=./notes.db
APP_BASE_URL=http://localhost:8084

# --- Ollama models ---
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBED_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text:latest
ENV

# optional systemd unit for the bot
mkdir -p deploy
b deploy/discord-bot.service
cat > deploy/discord-bot.service <<'UNIT'
[Unit]
Description=Second Brain Discord Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/second-brain
EnvironmentFile=%h/second-brain/.env
ExecStart=%h/second-brain/.venv/bin/python discord_bot.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

# requirements
if [[ ! -f requirements.txt ]]; then
  cat > requirements.txt <<'REQ'
fastapi==0.115.0
uvicorn[standard]==0.30.6
jinja2==3.1.4
httpx==0.27.2
numpy>=1.24,<3
python-multipart==0.0.9
aiosqlite==0.20.0
discord.py==2.4.0
REQ
else
  grep -q "aiosqlite" requirements.txt || echo "aiosqlite==0.20.0" >> requirements.txt
  grep -q "discord.py" requirements.txt || echo "discord.py==2.4.0" >> requirements.txt
  grep -q "numpy" requirements.txt || echo "numpy>=1.24,<3" >> requirements.txt
fi

echo "Done.

Next:
  # 1) Set env vars (copy and edit .env.example)
  cp -n .env.example .env || true
  # 2) Create venv and install
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  # 3) Run your web app (if not already)
  uvicorn app:app --reload --host 0.0.0.0 --port 8084
  # 4) Run the Discord bot
  source .env && python discord_bot.py

Invite the bot to your server, then try:
  /note add
  /note quick body:\"My idea\" tags:\"ideas, scratch\"
  /note search q:\"vector db\" embed:true
  /tags top
"
