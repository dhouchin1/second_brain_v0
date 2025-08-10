#!/usr/bin/env bash
# scaffold-010.sh
set -euo pipefail
STAMP="$(date +%Y%m%d-%H%M%S)"
b(){ [[ -f "$1" ]] && mv "$1" "$1.$STAMP.bak" && echo "• backup: $1 -> $1.$STAMP.bak" || true; }

# 1) Enhanced discord_bot.py with rules, redaction, auto-summary, daily digest
b discord_bot.py
cat > discord_bot.py <<'PY'
import os, re, math, json, asyncio, typing, datetime as dt
import aiosqlite, httpx, discord
from discord import app_commands
from discord.ext import commands, tasks

try:
    import numpy as np
except Exception:
    np = None

# ---------- Env / Config ----------
DB_PATH         = os.getenv("NOTES_DB_PATH", "./notes.db")
APP_BASE_URL    = os.getenv("APP_BASE_URL", "http://localhost:8084")
DISCORD_TOKEN   = os.getenv("DISCORD_TOKEN", "")
DISCORD_GUILD   = os.getenv("DISCORD_GUILD_ID")
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

-- Auto-capture bindings with rules
CREATE TABLE IF NOT EXISTS discord_bindings (
  guild_id      TEXT NOT NULL,
  channel_id    TEXT NOT NULL,
  enabled       INTEGER NOT NULL DEFAULT 1,
  default_tags  TEXT NOT NULL DEFAULT 'discord',
  min_len       INTEGER NOT NULL DEFAULT 10,
  embed_semantic INTEGER NOT NULL DEFAULT 0,
  allow_regex   TEXT,
  deny_regex    TEXT,
  required_role_id TEXT,
  summarize_enabled INTEGER NOT NULL DEFAULT 0,
  redact_enabled INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (guild_id, channel_id)
);

-- Dedupe of captured messages
CREATE TABLE IF NOT EXISTS discord_captures (
  message_id TEXT PRIMARY KEY,
  note_id    INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL
);

-- Guild preferences (daily digest)
CREATE TABLE IF NOT EXISTS discord_guild_prefs (
  guild_id TEXT PRIMARY KEY,
  digest_channel_id TEXT,
  digest_time_utc TEXT, -- 'HH:MM'
  last_digest_date TEXT  -- 'YYYY-MM-DD'
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
    cur = await db.execute(sql, params); row = await cur.fetchone(); await cur.close(); return row
async def fetchall(db, sql, params=()):
    cur = await db.execute(sql, params); rows = await cur.fetchall(); await cur.close(); return rows

# ---------- tag & note helpers ----------
def slugify_tag(s: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "", s.strip().lower().replace("#","").replace(" ", "-"))

def parse_hashtags(text: str) -> list[str]:
    tags = set()
    for m in re.findall(r"#([A-Za-z0-9][\w\-]*)", text or ""):
        tags.add(slugify_tag(m.replace("_","-")))
    return [t for t in tags if t]

async def ensure_tag(db, name: str) -> int:
    name = slugify_tag(name)
    cur = await db.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
    await db.commit()
    if cur.lastrowid: return cur.lastrowid
    row = await fetchone(db, "SELECT id FROM tags WHERE name=?", (name,)); return row["id"]

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

async def map_note_tags(db, ids: list[int]) -> dict[int,str]:
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

# ---------- embeddings & similarity ----------
async def embed_text(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{EMBED_BASE}/api/embeddings", json={"model": EMBED_MODEL, "prompt": text})
        r.raise_for_status(); data = r.json()
        return data.get("embedding") or (data.get("data",[{}])[0].get("embedding"))

async def ensure_embedding_for_note(db, note_id: int, body: str):
    try:
        vec = await embed_text(body)
        blob = (",".join(f"{float(x):.7f}" for x in vec)).encode("utf-8") if np is None else np.asarray(vec, dtype=np.float32).tobytes()
        await db.execute(
            "INSERT INTO note_embeddings(note_id, dim, vec) VALUES (?,?,?) "
            "ON CONFLICT(note_id) DO UPDATE SET dim=excluded.dim, vec=excluded.vec",
            (note_id, len(vec), blob)
        )
        await db.commit()
    except Exception as e:
        print("embed error:", e)

def cosine(a, b):
    if np is not None:
        a = np.asarray(a, dtype=np.float32); b = np.asarray(b, dtype=np.float32)
        denom = (np.linalg.norm(a) * np.linalg.norm(b)); 
        if denom == 0: return 0.0
        return float(np.dot(a, b)/denom)
    dot = sum(x*y for x,y in zip(a,b))
    na  = math.sqrt(sum(x*x for x in a)); nb = math.sqrt(sum(y*y for y in b))
    return 0.0 if na==0 or nb==0 else dot/(na*nb)

# ---------- redaction ----------
RE_EMAIL = re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b')
RE_JWT   = re.compile(r'\b[A-Za-z0-9_\-]+=*\.[A-Za-z0-9_\-]+=*\.[A-Za-z0-9_\-]+=*\b')
RE_HEX40 = re.compile(r'\b[a-f0-9]{40,}\b', re.IGNORECASE)
RE_SK    = re.compile(r'\b(sk|rk|pk|ak|token|key)[\-\_][A-Za-z0-9]{16,}\b', re.IGNORECASE)
RE_GH    = re.compile(r'\bgh[pous]_[A-Za-z0-9]{20,}\b')
RE_AWS   = re.compile(r'\bAKIA[0-9A-Z]{16}\b')
RE_LONGNUM = re.compile(r'\b\d{16,}\b')

def redact_sensitive(text: str) -> str:
    s = text
    s = RE_EMAIL.sub('[redacted email]', s)
    s = RE_JWT.sub('[redacted jwt]', s)
    s = RE_GH.sub('[redacted token]', s)
    s = RE_SK.sub('[redacted token]', s)
    s = RE_AWS.sub('[redacted key]', s)
    s = RE_HEX40.sub('[redacted token]', s)
    s = RE_LONGNUM.sub('[redacted number]', s)
    return s

# ---------- LLM summary ----------
async def summarize_text(text: str) -> str:
    prompt = (
        "Summarize the message below into 3-6 crisp bullet points.\n"
        "- Keep it factual, no fluff\n"
        "- 12 words max per bullet\n"
        "- Use plain text dashes ('- ')\n\n"
        f"Message:\n{text}\n\nSummary:\n"
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(f"{OLLAMA_BASE}/api/generate", json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False})
            r.raise_for_status()
            resp = r.json().get("response","").strip()
            # normalize bullets
            lines = [re.sub(r'^\s*[-•]\s*', '', ln).strip() for ln in resp.splitlines() if ln.strip()]
            lines = [ln for ln in lines if ln] or []
            if not lines:
                return ""
            return "\n".join(f"- {ln}" for ln in lines[:6])
    except Exception:
        return ""

# ---------- bindings ----------
async def get_binding(db, guild_id: int, channel_id: int):
    return await fetchone(db, "SELECT * FROM discord_bindings WHERE guild_id=? AND channel_id=?", (str(guild_id), str(channel_id)))

async def upsert_binding(db, guild_id: int, channel_id: int, enabled: bool, default_tags: str,
                         min_len: int, embed_semantic: bool, allow_regex: str|None,
                         deny_regex: str|None, required_role_id: str|None,
                         summarize_enabled: bool, redact_enabled: bool):
    await db.execute(
        "INSERT INTO discord_bindings(guild_id, channel_id, enabled, default_tags, min_len, embed_semantic, allow_regex, deny_regex, required_role_id, summarize_enabled, redact_enabled) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(guild_id,channel_id) DO UPDATE SET enabled=excluded.enabled, default_tags=excluded.default_tags, min_len=excluded.min_len, embed_semantic=excluded.embed_semantic, allow_regex=excluded.allow_regex, deny_regex=excluded.deny_regex, required_role_id=excluded.required_role_id, summarize_enabled=excluded.summarize_enabled, redact_enabled=excluded.redact_enabled",
        (str(guild_id), str(channel_id), 1 if enabled else 0, default_tags, int(min_len),
         1 if embed_semantic else 0, allow_regex or None, deny_regex or None,
         str(required_role_id) if required_role_id else None,
         1 if summarize_enabled else 0, 1 if redact_enabled else 0)
    )
    await db.commit()

async def remove_binding(db, guild_id: int, channel_id: int):
    await db.execute("DELETE FROM discord_bindings WHERE guild_id=? AND channel_id=?", (str(guild_id), str(channel_id)))
    await db.commit()

# ---------- formatting ----------
def message_url(guild_id: int, channel_id: int, message_id: int) -> str:
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

def format_discord_note(message: discord.Message, source: str) -> str:
    a = message.author; g = message.guild; ch = message.channel
    header = [
        "Discord capture\n",
        f"Guild: {g.name} ({g.id})\n" if g else "Guild: DM\n",
        f"Channel: #{getattr(ch,'name','dm')} ({ch.id})\n",
        f"Author: {a} ({a.id})\n",
        f"Message: {message_url(g.id if g else 0, ch.id, message.id)}\n",
        f"Created: {message.created_at.replace(tzinfo=dt.timezone.utc).isoformat()}\n",
        f"CapturedBy: {source}\n",
        "\nContent:\n"
    ]
    parts = ["".join(header), message.content or ""]
    if message.attachments:
        parts.append("\n\nAttachments:\n")
        for att in message.attachments:
            parts.append(f"- {att.url} ({att.filename})\n")
    return "".join(parts)

# ---------- capture pipeline ----------
async def save_message_to_note(message: discord.Message, forced_tags: list[str]|None=None, source: str="listener") -> typing.Optional[int]:
    if message.author.bot or message.guild is None:
        return None
    g = message.guild
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript("PRAGMA journal_mode=WAL;")

        # dedupe
        ex = await fetchone(db, "SELECT note_id FROM discord_captures WHERE message_id=?", (str(message.id),))
        if ex: return ex["note_id"]

        bind = await get_binding(db, g.id, message.channel.id)
        if not bind or not bind["enabled"]:
            return None

        # role requirement
        req_role = bind["required_role_id"]
        if req_role:
            have = any(str(r.id) == str(req_role) for r in getattr(message.author, "roles", []))
            if not have: return None

        text = message.content or ""
        # allow/deny regex
        try:
            if bind["allow_regex"]:
                if not re.search(bind["allow_regex"], text, flags=re.IGNORECASE|re.MULTILINE):
                    return None
            if bind["deny_regex"]:
                if re.search(bind["deny_regex"], text, flags=re.IGNORECASE|re.MULTILINE):
                    return None
        except re.error:
            # invalid regex in DB -> fail open (capture)
            pass

        if len(text.strip()) < int(bind["min_len"]) and not message.attachments:
            return None

        # tags: default + hashtags + channel tag + forced
        default_tags = bind["default_tags"] or "discord"
        collected = parse_hashtags(text)
        if forced_tags: collected += [slugify_tag(t) for t in forced_tags]
        ch_tag = slugify_tag(f"discord-{getattr(message.channel,'name','dm')}")
        tags_csv = ",".join(dict.fromkeys((default_tags.split(",") if default_tags else []) + collected + [ch_tag]))

        # redact if enabled
        body_raw = format_discord_note(message, source)
        body = redact_sensitive(body_raw) if bind["redact_enabled"] else body_raw

        # save
        nid = await add_note(db, body, tags_csv)

        # summarize if enabled
        if bind["summarize_enabled"]:
            summary = await summarize_text(text)
            if summary:
                new_body = f"Summary:\n{summary}\n\n---\n{body}"
                await db.execute("UPDATE notes SET body=? WHERE id=?", (new_body, nid))
                await set_note_tags_csv(db, nid, tags_csv + ",summary")
                await db.commit()

        # embed best-effort
        try: await ensure_embedding_for_note(db, nid, body)
        except Exception: pass

        await db.execute("INSERT INTO discord_captures(message_id, note_id, created_at) VALUES (?,?,?)",
                         (str(message.id), nid, dt.datetime.utcnow().isoformat(timespec="seconds")))
        await db.commit()
        return nid

# ---------- search helpers (for commands) ----------
async def fts_search(db, q: str, limit: int = PAGE_SIZE):
    sql = """
    SELECT n.id, n.body, n.created_at
    FROM notes_fts f JOIN notes n ON n.id=f.rowid
    WHERE notes_fts MATCH ?
    ORDER BY bm25(notes_fts) LIMIT ?
    """
    return await fetchall(db, sql, (q, limit))

async def semantic_search(db, query: str, limit: int = PAGE_SIZE):
    qvec = await embed_text(query)
    rows = await fetchall(db, "SELECT note_id, dim, vec FROM note_embeddings")
    out = []
    for r in rows:
        if r["dim"] != len(qvec): continue
        v = [float(x) for x in r["vec"].decode("utf-8").split(",")] if np is None else np.frombuffer(r["vec"], dtype=np.float32)
        # cosine with qvec
        if np is None:
            dot = sum(x*y for x,y in zip(v, qvec)); na = math.sqrt(sum(x*x for x in v)); nb = math.sqrt(sum(y*y for y in qvec))
            s = 0.0 if na==0 or nb==0 else dot/(na*nb)
        else:
            s = float(np.dot(v, qvec) / (np.linalg.norm(v) * np.linalg.norm(qvec)))
        out.append((r["note_id"], s))
    out.sort(key=lambda x: x[1], reverse=True)
    ids = [i for (i, _) in out[:limit]]
    if not ids: return []
    ph = ",".join("?"*len(ids))
    rows = await fetchall(db, f"SELECT id, body, created_at FROM notes WHERE id IN ({ph})", ids)
    order = {nid:i for i,nid in enumerate(ids)}
    rows.sort(key=lambda r: order[r["id"]])
    return rows

# ---------- Discord bot ----------
intents = discord.Intents.default()
intents.message_content = True
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
    digest_loop.start()

# ---------- Message listeners ----------
@bot.event
async def on_message(message: discord.Message):
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

# ---------- Slash commands: note ops (quick, get, search) ----------
@bot.tree.command(name="note_quick", description="Add a note quickly")
@app_commands.describe(body="Note body", tags="Comma-separated tags (optional)")
async def note_quick(interaction: discord.Interaction, body: str, tags: str = ""):
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
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

# ---------- Slash commands: bindings & rules ----------
@bot.tree.command(name="brain_bind", description="Bind a channel for auto-capture (with options)")
@app_commands.describe(
  channel="Channel to bind",
  default_tags="Comma tags (e.g., discord,ideas)",
  min_len="Minimum text length",
  embed_semantic="Prefer semantic for searches",
  enabled="Turn on/off",
  summarize_enabled="Auto-summarize captured messages",
  redact_enabled="Redact emails/tokens before saving"
)
async def brain_bind(interaction: discord.Interaction, channel: discord.TextChannel,
                     default_tags: str = "discord", min_len: app_commands.Range[int,0,10000]=10,
                     embed_semantic: bool=False, enabled: bool=True, summarize_enabled: bool=False, redact_enabled: bool=True):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Need Manage Server permission.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await upsert_binding(db, interaction.guild.id, channel.id, enabled, default_tags, int(min_len),
                             embed_semantic, None, None, None, summarize_enabled, redact_enabled)
    await interaction.followup.send(f"✅ Bound <#{channel.id}> (enabled={enabled}, min_len={min_len}, tags={default_tags}, summary={summarize_enabled}, redact={redact_enabled})", ephemeral=True)

@bot.tree.command(name="brain_rules", description="Set channel allow/deny regex & required role")
@app_commands.describe(channel="Channel", allow_regex="Capture only if matches (optional)", deny_regex="Skip if matches (optional)", required_role="Must have this role (optional)")
async def brain_rules(interaction: discord.Interaction, channel: discord.TextChannel,
                      allow_regex: str = "", deny_regex: str = "", required_role: discord.Role | None = None):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Need Manage Server permission.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True, thinking=True)
    # quick sanity compile
    for rgx in (allow_regex, deny_regex):
        if rgx:
            try: re.compile(rgx)
            except re.error as e:
                await interaction.followup.send(f"Invalid regex: `{rgx}` — {e}", ephemeral=True); return
    async with aiosqlite.connect(DB_PATH) as db:
        current = await get_binding(db, interaction.guild.id, channel.id)
        if not current:
            await upsert_binding(db, interaction.guild.id, channel.id, True, "discord", 10, False,
                                 allow_regex or None, deny_regex or None, str(required_role.id) if required_role else None,
                                 False, True)
        else:
            await upsert_binding(db, interaction.guild.id, channel.id, bool(current["enabled"]), current["default_tags"],
                                 int(current["min_len"]), bool(current["embed_semantic"]),
                                 allow_regex or None, deny_regex or None, str(required_role.id) if required_role else None,
                                 bool(current["summarize_enabled"]), bool(current["redact_enabled"]))
    rid = required_role.id if required_role else None
    await interaction.followup.send(f"✅ Rules set for <#{channel.id}> (allow='{allow_regex or '—'}', deny='{deny_regex or '—'}', role={rid or '—'})", ephemeral=True)

@bot.tree.command(name="brain_unbind", description="Unbind a channel")
@app_commands.describe(channel="Channel to unbind")
async def brain_unbind(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Need Manage Server permission.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await remove_binding(db, interaction.guild.id, channel.id)
    await interaction.followup.send(f"✅ Unbound <#{channel.id}>", ephemeral=True)

@bot.tree.command(name="brain_list", description="List bound channels & rules")
async def brain_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await fetchall(db, "SELECT * FROM discord_bindings WHERE guild_id=?", (str(interaction.guild.id),))
    if not rows:
        await interaction.followup.send("No channels bound.", ephemeral=True); return
    lines=[]
    for r in rows:
        lines.append(
            f"• <#{r['channel_id']}> — enabled={bool(r['enabled'])}, min_len={r['min_len']}, tags={r['default_tags']}, "
            f"summary={bool(r['summarize_enabled'])}, redact={bool(r['redact_enabled'])}, "
            f"allow={r['allow_regex'] or '—'}, deny={r['deny_regex'] or '—'}, role={r['required_role_id'] or '—'}"
        )
    await interaction.followup.send("\n".join(lines[:15]), ephemeral=True)

# ---------- Slash commands: daily digest ----------
@bot.tree.command(name="digest_set", description="Enable daily digest to a channel at HH:MM (UTC)")
@app_commands.describe(channel="Target channel", time_utc="HH:MM 24h UTC, e.g., 13:00")
async def digest_set(interaction: discord.Interaction, channel: discord.TextChannel, time_utc: str):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Need Manage Server permission.", ephemeral=True); return
    if not re.fullmatch(r"\d{2}:\d{2}", time_utc):
        await interaction.response.send_message("Time must be HH:MM (UTC).", ephemeral=True); return
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO discord_guild_prefs(guild_id, digest_channel_id, digest_time_utc, last_digest_date) "
            "VALUES(?,?,?,COALESCE((SELECT last_digest_date FROM discord_guild_prefs WHERE guild_id=?), NULL)) "
            "ON CONFLICT(guild_id) DO UPDATE SET digest_channel_id=excluded.digest_channel_id, digest_time_utc=excluded.digest_time_utc",
            (str(interaction.guild.id), str(channel.id), time_utc, str(interaction.guild.id))
        )
        await db.commit()
    await interaction.followup.send(f"✅ Digest set: <#{channel.id}> at {time_utc} UTC", ephemeral=True)

@bot.tree.command(name="digest_off", description="Disable daily digest")
async def digest_off(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Need Manage Server permission.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE discord_guild_prefs SET digest_channel_id=NULL WHERE guild_id=?", (str(interaction.guild.id),))
        await db.commit()
    await interaction.followup.send("✅ Digest disabled.", ephemeral=True)

@bot.tree.command(name="digest_status", description="Show digest settings")
async def digest_status(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    async with aiosqlite.connect(DB_PATH) as db:
        row = await fetchone(db, "SELECT digest_channel_id, digest_time_utc, last_digest_date FROM discord_guild_prefs WHERE guild_id=?", (str(interaction.guild.id),))
    if not row or not row["digest_channel_id"]:
        await interaction.followup.send("Digest: disabled.", ephemeral=True); return
    await interaction.followup.send(f"Digest → <#{row['digest_channel_id']}> at {row['digest_time_utc']} UTC • last sent: {row['last_digest_date'] or '—'}", ephemeral=True)

@bot.tree.command(name="digest_test", description="Send today's digest now")
async def digest_test(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Need Manage Server permission.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True, thinking=True)
    ok, msg = await send_digest_for_guild(interaction.guild)
    await interaction.followup.send(msg, ephemeral=True)

# ---------- Digest loop ----------
async def send_digest_for_guild(guild: discord.Guild) -> tuple[bool,str]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        prefs = await fetchone(db, "SELECT digest_channel_id, digest_time_utc, last_digest_date FROM discord_guild_prefs WHERE guild_id=?", (str(guild.id),))
        if not prefs or not prefs["digest_channel_id"]:
            return False, "Digest disabled."
        channel_id = int(prefs["digest_channel_id"])
        ch = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)

        # select today's notes (UTC day)
        today = dt.datetime.utcnow().date().isoformat()
        rows = await fetchall(db, "SELECT id, body, created_at FROM notes WHERE date(created_at)=date('now') ORDER BY datetime(created_at) DESC LIMIT 20")
        if not rows:
            await ch.send("📬 Daily digest: No new notes today."); 
            # still mark sent
            await db.execute("UPDATE discord_guild_prefs SET last_digest_date=? WHERE guild_id=?", (today, str(guild.id))); await db.commit()
            return True, "Sent empty digest."

        lines=[]
        for r in rows:
            title = (r["body"].splitlines()[0] or f"Note #{r['id']}")[:80]
            url = f"{APP_BASE_URL}/notes/{r['id']}"
            lines.append(f"• **{title}** — <{url}>")
        embed = discord.Embed(title=f"Daily digest — {today}", description="\n".join(lines), color=0x5865F2)
        await ch.send(embed=embed)
        await db.execute("UPDATE discord_guild_prefs SET last_digest_date=? WHERE guild_id=?", (today, str(guild.id))); await db.commit()
        return True, "Digest sent."

@tasks.loop(minutes=1.0)
async def digest_loop():
    # run every minute: if time >= HH:MM and not sent today, send
    now = dt.datetime.utcnow()
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await fetchall(db, "SELECT guild_id, digest_channel_id, digest_time_utc, last_digest_date FROM discord_guild_prefs WHERE digest_channel_id IS NOT NULL")
    for r in rows:
        if not r["digest_time_utc"]: continue
        hh, mm = map(int, r["digest_time_utc"].split(":"))
        due = now.hour > hh or (now.hour == hh and now.minute >= mm)
        already = (r["last_digest_date"] == now.date().isoformat())
        if due and not already:
            g = bot.get_guild(int(r["guild_id"]))
            if g:
                try:
                    await send_digest_for_guild(g)
                except Exception as e:
                    print("digest error:", e)

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

# 2) requirements (no new packages beyond previous)
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

# 3) .env example (non-destructive create)
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

New stuff:
  • Channel rules: /brain_rules (allow/deny regex, required role)
  • Summaries: toggle via /brain_bind summarize_enabled:true
  • Redaction: on by default; toggle via /brain_bind redact_enabled:false
  • Daily digest: /digest_set channel:#foo time_utc:13:00 • /digest_status • /digest_test • /digest_off

Run:
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  source .env && python discord_bot.py

Make sure 'Message Content Intent' is enabled for your bot."
