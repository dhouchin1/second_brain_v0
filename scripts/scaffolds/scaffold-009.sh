#!/usr/bin/env bash
# scaffold-009.sh
set -euo pipefail
STAMP="$(date +%Y%m%d-%H%M%S)"
b(){ [[ -f "$1" ]] && mv "$1" "$1.$STAMP.bak" && echo "• backup: $1 -> $1.$STAMP.bak" || true; }

# --- Enhanced Discord bot with listeners + C2 ---
b discord_bot.py
cat > discord_bot.py <<'PY'
import os, re, math, json, asyncio, typing
import datetime as dt
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
DISCORD_GUILD   = os.getenv("DISCORD_GUILD_ID")  # optional (faster sync)
OLLAMA_BASE     = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
EMBED_BASE      = os.getenv("OLLAMA_EMBED_BASE_URL", "http://localhost:11434")
EMBED_MODEL     = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")
PAGE_SIZE       = 5

# ---------- SQLite schema ----------
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

-- Channels bound for auto-capture
CREATE TABLE IF NOT EXISTS discord_bindings (
  guild_id   TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  enabled    INTEGER NOT NULL DEFAULT 1,
  default_tags TEXT NOT NULL DEFAULT 'discord',
  min_len    INTEGER NOT NULL DEFAULT 10,
  embed_semantic INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild_id, channel_id)
);

-- Dedupe: which Discord messages have been captured
CREATE TABLE IF NOT EXISTS discord_captures (
  message_id TEXT PRIMARY KEY,
  note_id    INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL
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

# ---------- aiosqlite helpers ----------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(SCHEMA_SQL)
        await db.commit()

async def fetchone(db, sql, params=()):
    cur = await db.execute(sql, params)
    row = await cur.fetchone()
    await cur.close()
    return row

async def fetchall(db, sql, params=()):
    cur = await db.execute(sql, params)
    rows = await cur.fetchall()
    await cur.close()
    return rows

# ---------- tag & note helpers ----------
def slugify_tag(s: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "", s.strip().lower().replace("#","").replace(" ", "-"))

def parse_hashtags(text: str) -> list[str]:
    # #tag or #multi-word -> multi-word => multi-word (dash)
    tags = set()
    for m in re.findall(r"#([A-Za-z0-9][\w\-]*)", text or ""):
        tags.add(slugify_tag(m.replace("_","-")))
    return [t for t in tags if t]

async def ensure_tag(db, name: str) -> int:
    name = slugify_tag(name)
    cur = await db.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
    await db.commit()
    if cur.lastrowid:
        return cur.lastrowid
    row = await fetchone(db, "SELECT id FROM tags WHERE name=?", (name,))
    return row["id"]

async def set_note_tags_csv(db, note_id: int, tags_csv: str):
    names = [slugify_tag(x) for x in (tags_csv or "").split(",") if x.strip()]
    names = [n for n in dict.fromkeys(names) if n]
    await db.execute("DELETE FROM note_tags WHERE note_id=?", (note_id,))
    for nm in names:
        tid = await ensure_tag(db, nm)
        await db.execute("INSERT OR IGNORE INTO note_tags(note_id, tag_id) VALUES (?,?)", (note_id, tid))
    await db.commit()

async def add_note(db, body: str, tags_csv: str) -> int:
    now = dt.datetime.utcnow().isoformat(timespec="seconds")
    cur = await db.execute("INSERT INTO notes(body, created_at) VALUES (?,?)", (body, now))
    nid = cur.lastrowid
    await set_note_tags_csv(db, nid, tags_csv)
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
    rows = await fetchall(db, sql, ids)
    return {r["id"]: (r["tags"] or "") for r in rows}

# ---------- embeddings ----------
async def embed_text(text: str) -> typing.List[float]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{EMBED_BASE}/api/embeddings", json={"model": EMBED_MODEL, "prompt": text})
        r.raise_for_status()
        data = r.json()
        return data.get("embedding") or (data.get("data",[{}])[0].get("embedding"))

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
        print("embed error:", e)

# ---------- links & formatting ----------
def message_url(guild_id: int, channel_id: int, message_id: int) -> str:
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

def header_line(k: str, v: str) -> str:
    return f"{k}: {v}\n"

def format_discord_message_note(message: discord.Message, extra: dict) -> str:
    a = message.author
    g = message.guild
    ch = message.channel
    parts = []
    parts.append("Discord capture\n")
    parts.append(header_line("Guild", f"{g.name} ({g.id})" if g else "DM"))
    parts.append(header_line("Channel", f"#{getattr(ch,'name','dm')} ({ch.id})"))
    parts.append(header_line("Author", f"{a} ({a.id})"))
    parts.append(header_line("Message", message_url(g.id if g else 0, ch.id, message.id)))
    parts.append(header_line("Created", message.created_at.replace(tzinfo=dt.timezone.utc).isoformat()))
    if extra.get("source"): parts.append(header_line("CapturedBy", extra["source"]))
    parts.append("\nContent:\n")
    parts.append(message.content or "")
    if message.attachments:
        parts.append("\n\nAttachments:\n")
        for att in message.attachments:
            parts.append(f"- {att.url} ({att.filename})\n")
    return "".join(parts)

# ---------- bindings ----------
async def get_binding(db, guild_id: int, channel_id: int):
    return await fetchone(db,
        "SELECT * FROM discord_bindings WHERE guild_id=? AND channel_id=?",
        (str(guild_id), str(channel_id))
    )

async def upsert_binding(db, guild_id: int, channel_id: int, enabled: bool, default_tags: str, min_len: int, embed_semantic: bool):
    await db.execute(
        "INSERT INTO discord_bindings(guild_id, channel_id, enabled, default_tags, min_len, embed_semantic) "
        "VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(guild_id,channel_id) DO UPDATE SET enabled=excluded.enabled, default_tags=excluded.default_tags, min_len=excluded.min_len, embed_semantic=excluded.embed_semantic",
        (str(guild_id), str(channel_id), 1 if enabled else 0, default_tags, int(min_len), 1 if embed_semantic else 0)
    )
    await db.commit()

async def remove_binding(db, guild_id: int, channel_id: int):
    await db.execute("DELETE FROM discord_bindings WHERE guild_id=? AND channel_id=?", (str(guild_id), str(channel_id)))
    await db.commit()

# ---------- capture core ----------
async def save_message_to_note(message: discord.Message, forced_tags: list[str]|None=None, source: str="listener") -> typing.Optional[int]:
    if message.author.bot:  # ignore bots
        return None
    g = message.guild
    if g is None:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript("PRAGMA journal_mode=WAL;")
        # dedupe
        exist = await fetchone(db, "SELECT note_id FROM discord_captures WHERE message_id=?", (str(message.id),))
        if exist:
            return exist["note_id"]

        bind = await get_binding(db, g.id, message.channel.id)
        if bind and not bind["enabled"]:
            return None

        min_len = (bind["min_len"] if bind else 10)
        if len(message.content.strip()) < int(min_len) and not message.attachments:
            return None

        default_tags = (bind["default_tags"] if bind else "discord")
        collected = parse_hashtags(message.content)
        if forced_tags:
            collected.extend([slugify_tag(t) for t in forced_tags])
        # channel tag for context
        ch_name = getattr(message.channel, "name", "dm")
        collected.append(slugify_tag(f"discord-{ch_name}"))
        tags_csv = ",".join(dict.fromkeys((default_tags.split(",") if default_tags else []) + collected))

        body = format_discord_message_note(message, {"source": source})
        nid = await add_note(db, body, tags_csv)
        # embeddings best-effort
        await ensure_embedding_for_note(db, nid, body)
        await db.execute("INSERT INTO discord_captures(message_id, note_id, created_at) VALUES (?,?,?)",
                         (str(message.id), nid, dt.datetime.utcnow().isoformat(timespec="seconds")))
        await db.commit()
        return nid

# ---------- search helpers (for slash commands) ----------
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
    rows = await fetchall(db, "SELECT note_id, dim, vec FROM note_embeddings")
    out = []
    for r in rows:
        if r["dim"] != len(qvec): continue
        blob = r["vec"]
        v = [float(x) for x in blob.decode("utf-8").split(",")] if np is None else np.frombuffer(blob, dtype=np.float32)
        out.append((r["note_id"], cosine(v, qvec)))
    out.sort(key=lambda x: x[1], reverse=True)
    top_ids = [i for (i, _) in out[:limit]]
    if not top_ids: return []
    ph = ",".join("?"*len(top_ids))
    rows = await fetchall(db, f"SELECT id, body, created_at FROM notes WHERE id IN ({ph})", top_ids)
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
    return await fetchall(db, sql, (q, limit))

# ---------- Discord bot ----------
intents = discord.Intents.default()
intents.message_content = True   # REQUIRED for on_message content
intents.guilds = True
intents.messages = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    try:
        if DISCORD_GUILD:
            g = discord.Object(id=int(DISCORD_GUILD))
            bot.tree.copy_global_to(guild=g)
            synced = await bot.tree.sync(guild=g)
        else:
            synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print("Sync error:", e)

# ---------- Message listeners ----------
@bot.event
async def on_message(message: discord.Message):
    # Let commands still work
    await bot.process_commands(message)

    try:
        nid = await save_message_to_note(message, source="auto-channel")
        if nid:
            try: await message.add_reaction("🧠")
            except Exception: pass
    except Exception as e:
        print("on_message error:", e)

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # Save on 💾 or 🧠
    if str(payload.emoji) not in ("💾", "🧠"): return
    if payload.user_id == bot.user.id: return
    guild = bot.get_guild(payload.guild_id)
    if not guild: return
    channel = guild.get_channel(payload.channel_id) or await guild.fetch_channel(payload.channel_id)
    try:
        message = await channel.fetch_message(payload.message_id)
    except Exception:
        return
    try:
        nid = await save_message_to_note(message, source="reaction")
        if nid:
            try: await message.add_reaction("✅")
            except Exception: pass
    except Exception as e:
        print("reaction save error:", e)

# ---------- Slash commands: note ops (kept) ----------
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

@bot.tree.command(name="note_get", description="Get a note by ID")
@app_commands.describe(id="Note ID")
async def note_get(interaction: discord.Interaction, id: int):
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await fetchone(db, "SELECT id, body, created_at FROM notes WHERE id=?", (id,))
        if not row: 
            await interaction.followup.send("Not found.", ephemeral=True); return
        tagmap = await map_note_tags(db, [row["id"]])
    url = f"{APP_BASE_URL}/notes/{row['id']}"
    title = (row["body"].splitlines()[0] or f"Note #{row['id']}")[:80]
    embed = discord.Embed(title=title, description=(row["body"][:500] + ("…" if len(row["body"])>500 else "")), color=0x5865F2)
    embed.add_field(name="Tags", value=(tagmap.get(row["id"], "") or "—"), inline=False)
    embed.add_field(name="Created", value=row["created_at"], inline=True)
    embed.add_field(name="Open", value=url, inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="note_search", description="Search notes (FTS or Semantic)")
@app_commands.describe(q="Query string", embed="Semantic instead of text search")
async def note_search(interaction: discord.Interaction, q: str, embed: bool=False):
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (semantic_search(db, q, PAGE_SIZE) if embed else fts_search(db, q, PAGE_SIZE))
        tagmap = await map_note_tags(db, [r["id"] for r in rows])
    if not rows:
        await interaction.followup.send("No results.", ephemeral=True); return
    embeds=[]
    for r in rows:
        url = f"{APP_BASE_URL}/notes/{r['id']}"
        t = (r["body"].splitlines()[0] or f"Note #{r['id']}")[:80]
        e = discord.Embed(title=t, description=(r["body"][:300] + ("…" if len(r["body"])>300 else "")),
                          color=0x57F287 if embed else 0x5865F2)
        e.add_field(name="Tags", value=(tagmap.get(r["id"], "") or "—"), inline=False)
        e.add_field(name="Open", value=url, inline=True)
        embeds.append(e)
    await interaction.followup.send(embeds=embeds, ephemeral=True)

# ---------- Slash commands: bindings / C2 ----------
@bot.tree.command(name="brain_bind", description="Bind a channel for auto-capture")
@app_commands.describe(channel="Channel to bind", default_tags="Comma tags (e.g., discord,ideas)", min_len="Minimum text length", embed_semantic="Prefer semantic for /note_search", enabled="Turn on/off")
async def brain_bind(interaction: discord.Interaction,
                     channel: discord.TextChannel,
                     default_tags: str = "discord",
                     min_len: app_commands.Range[int,0,10000]=10,
                     embed_semantic: bool = False,
                     enabled: bool = True):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Need Manage Server permission.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await upsert_binding(db, interaction.guild.id, channel.id, enabled, default_tags, int(min_len), embed_semantic)
    await interaction.followup.send(f"✅ Bound <#{channel.id}> (enabled={enabled}, min_len={min_len}, tags={default_tags}, semantic={embed_semantic})", ephemeral=True)

@bot.tree.command(name="brain_unbind", description="Unbind a channel")
@app_commands.describe(channel="Channel to unbind")
async def brain_unbind(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Need Manage Server permission.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await remove_binding(db, interaction.guild.id, channel.id)
    await interaction.followup.send(f"✅ Unbound <#{channel.id}>", ephemeral=True)

@bot.tree.command(name="brain_list", description="List bound channels")
async def brain_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await fetchall(db, "SELECT * FROM discord_bindings WHERE guild_id=?", (str(interaction.guild.id),))
    if not rows:
        await interaction.followup.send("No channels bound.", ephemeral=True); return
    lines=[]
    for r in rows:
        lines.append(f"• <#{r['channel_id']}> — enabled={bool(r['enabled'])}, min_len={r['min_len']}, tags={r['default_tags']}, semantic={bool(r['embed_semantic'])}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)

@bot.tree.command(name="brain_settings", description="Set Ollama bases/models (persist to app)")
@app_commands.describe(base="Chat base URL", model="Chat model", emb_base="Embed base URL", emb_model="Embed model")
async def brain_settings(interaction: discord.Interaction, base: str, model: str, emb_base: str, emb_model: str):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Need Manage Server permission.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO settings(key,value) VALUES('OLLAMA_BASE_URL',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (base,))
        await db.execute("INSERT INTO settings(key,value) VALUES('OLLAMA_MODEL',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (model,))
        await db.execute("INSERT INTO settings(key,value) VALUES('OLLAMA_EMBED_BASE_URL',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (emb_base,))
        await db.execute("INSERT INTO settings(key,value) VALUES('OLLAMA_EMBED_MODEL',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (emb_model,))
        await db.commit()
    await interaction.followup.send("✅ Settings saved.", ephemeral=True)

@bot.tree.command(name="brain_status", description="Show DB status (notes/tags/embeddings)")
async def brain_status(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        tot = await fetchone(db, "SELECT COUNT(*) c FROM notes")
        tgs = await fetchone(db, "SELECT COUNT(*) c FROM tags")
        emb = await fetchone(db, "SELECT COUNT(*) c FROM note_embeddings")
    await interaction.followup.send(f"Notes: {tot['c']} • Tags: {tgs['c']} • Embedded: {emb['c']}", ephemeral=True)

@bot.tree.command(name="brain_rebuild_embeddings", description="Rebuild N embeddings (force)")
@app_commands.describe(limit="How many notes to process")
async def brain_rebuild_embeddings(interaction: discord.Interaction, limit: app_commands.Range[int,1,1000]=100):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Need Manage Server permission.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True, thinking=True)
    done = 0; errors = 0
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await fetchall(db, "SELECT id, body FROM notes ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows:
            try:
                await ensure_embedding_for_note(db, r["id"], r["body"]); done += 1
            except Exception:
                errors += 1
    await interaction.followup.send(f"Rebuilt {done} embeddings ({errors} errors).", ephemeral=True)

# ---------- Thread capture ----------
@bot.tree.command(name="thread_capture", description="Capture this thread into a single note")
@app_commands.describe(tags="Extra comma tags", min_len="Minimum length to include a message")
async def thread_capture(interaction: discord.Interaction, tags: str = "", min_len: app_commands.Range[int,0,10000]=0):
    ch = interaction.channel
    if not isinstance(ch, (discord.Thread,)):
        await interaction.response.send_message("Run this inside a thread.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True, thinking=True)

    history = []
    async for m in ch.history(limit=None, oldest_first=True):
        if m.author.bot: continue
        if len(m.content.strip()) < int(min_len) and not m.attachments: continue
        when = m.created_at.replace(tzinfo=dt.timezone.utc).isoformat()
        history.append(f"- {when} — {m.author}: {m.content}\n  {message_url(ch.guild.id, ch.id, m.id)}")
        for att in m.attachments:
            history.append(f"  attachment: {att.url}")

    if not history:
        await interaction.followup.send("Thread is empty after filters.", ephemeral=True); return

    title = f"Discord thread capture — #{getattr(ch.parent,'name','thread')}/{ch.name}"
    body = f"{title}\n\n" + "\n".join(history)
    # tags: default + thread-specific
    extra = ",".join([t for t in [tags, slugify_tag(f\"discord-{getattr(ch.parent,'name','thread')}\")] if t])
    async with aiosqlite.connect(DB_PATH) as db:
        nid = await add_note(db, body, extra or "discord")
        await ensure_embedding_for_note(db, nid, body)
    url = f"{APP_BASE_URL}/notes/{nid}"
    await interaction.followup.send(f"🧵 Captured thread to note: {url}", ephemeral=True)

# ---------- Entry ----------
async def amain():
    if not DISCORD_TOKEN:
        raise RuntimeError("Set DISCORD_TOKEN env var.")
    await init_db()
    await bot.start(DISCORD_TOKEN)

def main():
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
PY

# --- requirements ---
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
  grep -q "python-multipart" requirements.txt || echo "python-multipart==0.0.9" >> requirements.txt
fi

# --- .env example additions (non-destructive) ---
if [[ ! -f .env.example ]]; then
  cat > .env.example <<'ENV'
DISCORD_TOKEN=put-your-bot-token-here
DISCORD_GUILD_ID=
NOTES_DB_PATH=./notes.db
APP_BASE_URL=http://localhost:8084
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBED_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text:latest
ENV
fi

echo "Done.

Next:
  1) Enable 'Message Content Intent' for your bot in Discord dev portal.
  2) source .env    # or export env vars
  3) python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
  4) Run your web app (uvicorn app:app --reload --port 8084)
  5) Run the bot: python discord_bot.py

Try:
  /brain_bind channel:#brain default_tags:\"discord,ideas\" min_len:10 enabled:true
  React with 💾 to any message to save it.
  Post in #brain — messages will auto-save (🧠 reaction confirms).
  /thread_capture (inside a thread) to roll it up into one note.
  /brain_list, /brain_settings, /brain_status, /brain_rebuild_embeddings
"
