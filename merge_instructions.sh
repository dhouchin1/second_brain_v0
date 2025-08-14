# Second Brain Integration - Step by Step

# 1. Backup current state
git add -A
git commit -m "backup: before enhancement integration"
git checkout -b feature/enhanced-integration

# 2. Update requirements.txt
cat >> requirements.txt << 'EOF'
sentence-transformers>=2.2.2
discord.py>=2.3.2
aiohttp>=3.9.0
python-frontmatter>=1.0.0
watchdog>=3.0.0
EOF

# 3. Create requirements-dev.txt
cat > requirements-dev.txt << 'EOF'
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
pytest-mock==3.12.0
pytest-html==4.1.1
httpx==0.25.2
ruff==0.1.6
mypy==1.7.1
coverage==7.3.2
EOF

# 4. Create enhanced search engine
# Copy search_engine.py from artifacts

# 5. Create Discord bot
# Copy discord_bot.py from artifacts

# 6. Create Obsidian sync
# Copy obsidian_sync.py from artifacts

# 7. Update app.py - add to imports
cat >> app_additions.py << 'EOF'
# Add these imports at top of app.py
from search_engine import EnhancedSearchEngine, SearchResult
from discord_bot import SecondBrainCog
from obsidian_sync import ObsidianSync

# Add these endpoints before the health check
@app.post("/api/search/enhanced")
async def enhanced_search(
    q: str = Query(..., description="Search query"),
    type: str = Query("hybrid", description="Search type: fts, semantic, or hybrid"),
    limit: int = Query(20, description="Number of results"),
    current_user: User = Depends(get_current_user)
):
    search_engine = EnhancedSearchEngine(str(settings.db_path))
    results = search_engine.search(q, current_user.id, limit, type)
    search_engine.log_search(current_user.id, q, len(results), type)
    
    return {
        "query": q,
        "results": [
            {
                "id": r.note_id,
                "title": r.title,
                "summary": r.summary,
                "tags": r.tags,
                "timestamp": r.timestamp,
                "score": r.score,
                "snippet": r.snippet,
                "match_type": r.match_type
            } for r in results
        ],
        "total": len(results),
        "search_type": type
    }

@app.post("/webhook/discord")
async def webhook_discord(
    data: dict = Body(...),
    current_user: User = Depends(get_current_user)
):
    # Discord webhook implementation
    note = data.get("note", "")
    tags = data.get("tags", "")
    note_type = data.get("type", "discord")
    
    result = ollama_summarize(note)
    summary = result.get("summary", "")
    ai_tags = result.get("tags", [])
    ai_actions = result.get("actions", [])
    
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    tag_list.extend([t for t in ai_tags if t and t not in tag_list])
    tags = ",".join(tag_list)
    actions = "\n".join(ai_actions)
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notes (title, content, summary, tags, actions, type, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            note[:60] + "..." if len(note) > 60 else note,
            note,
            summary,
            tags,
            actions,
            note_type,
            now,
            current_user.id,
        ),
    )
    conn.commit()
    note_id = c.lastrowid
    
    c.execute(
        "INSERT INTO notes_fts(rowid, title, summary, tags, actions, content) VALUES (?, ?, ?, ?, ?, ?)",
        (note_id, note[:60] + "..." if len(note) > 60 else note, summary, tags, actions, note),
    )
    conn.commit()
    conn.close()
    
    return {"status": "ok", "note_id": note_id}
EOF

# 8. Update database schema in init_db function
cat >> db_updates.sql << 'EOF'
-- Add to init_db() function in app.py

# Create Discord users table
c.execute('''
    CREATE TABLE IF NOT EXISTS discord_users (
        discord_id INTEGER PRIMARY KEY,
        user_id INTEGER,
        linked_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
''')

# Create reminders table  
c.execute('''
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER,
        user_id INTEGER,
        due_date TEXT,
        completed BOOLEAN DEFAULT FALSE,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(note_id) REFERENCES notes(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
''')

# Create enhanced FTS5 table
c.execute('''
    CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts5 USING fts5(
        title, content, summary, tags, actions,
        content='notes', content_rowid='id',
        tokenize='porter unicode61'
    )
''')

# Create search analytics
c.execute('''
    CREATE TABLE IF NOT EXISTS search_analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        query TEXT,
        results_count INTEGER,
        clicked_result_id INTEGER,
        search_type TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    )
''')
EOF

# 9. Replace templates with enhanced versions
# Backup current templates
cp templates/dashboard.html templates/dashboard.html.backup
cp templates/detail.html templates/detail.html.backup

# Copy new templates from artifacts
# Use the ShadCN dashboard and enhanced detail view

# 10. Add testing infrastructure
mkdir -p tests/{unit,integration,e2e}

# 11. Update CI workflow
# Copy enhanced workflow from artifacts

# 12. Create environment files
cat > .env.example << 'EOF'
# Database
DB_PATH=./notes.db
DATABASE_URL=sqlite:///./notes.db

# Paths  
VAULT_PATH=./vault
AUDIO_DIR=./audio
WHISPER_CPP_PATH=./whisper.cpp/build/bin/whisper-cli
WHISPER_MODEL_PATH=./whisper.cpp/models/ggml-base.en.bin

# AI Services
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Security
SECRET_KEY=your-super-secret-key-here
WEBHOOK_TOKEN=your-webhook-token

# Discord
DISCORD_BOT_TOKEN=your-discord-bot-token

# Optional Cloud Services
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
EOF

# 13. Test the integration
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run existing functionality
python -m pytest tests/ -v

# Start enhanced server
uvicorn app:app --reload --port 8084

# 14. Commit changes
git add .
git commit -m "feat: integrate enhanced features - search, discord, obsidian sync"

# 15. Create PR
git push origin feature/enhanced-integration
# Create PR to main branch