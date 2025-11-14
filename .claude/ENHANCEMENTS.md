# Claude Code Enhancements for Second Brain v0

This document outlines recommended Claude Skills, custom slash commands, and MCP servers to enhance your Second Brain development workflow.

## 📋 Table of Contents

1. [New Claude Skills](#new-claude-skills)
2. [Additional Slash Commands](#additional-slash-commands)
3. [MCP Server Enhancements](#mcp-server-enhancements)
4. [Recommended Third-Party MCP Servers](#recommended-third-party-mcp-servers)
5. [Implementation Priority](#implementation-priority)

---

## 🎯 New Claude Skills

### 1. **second-brain-tester** Skill
**Purpose:** Run comprehensive tests for Second Brain services

**Features:**
- Run pytest with coverage reports
- Execute smoke tests for critical services
- Test database migrations
- Validate API endpoints
- Check Ollama/Whisper integration

**Usage:**
```
You: Run all tests for the unified capture service
Claude: [Executes pytest with proper fixtures and shows results]
```

### 2. **service-inspector** Skill
**Purpose:** Analyze and document service architecture

**Features:**
- Map service dependencies
- Identify circular dependencies
- Generate service documentation
- Check for missing tests
- Analyze API routes

**Usage:**
```
You: Analyze the memory service dependencies
Claude: [Shows detailed dependency graph and potential issues]
```

### 3. **migration-helper** Skill
**Purpose:** Assist with database migrations

**Features:**
- Generate migration SQL files
- Validate migration syntax
- Check migration order
- Test rollback procedures
- Analyze schema changes

**Usage:**
```
You: Create a migration to add full-text search to tags
Claude: [Generates migration file with proper FTS5 syntax]
```

### 4. **obsidian-sync-debugger** Skill
**Purpose:** Debug Obsidian vault synchronization issues

**Features:**
- Validate YAML frontmatter
- Check file permissions
- Test vault connectivity
- Analyze sync conflicts
- Verify markdown formatting

**Usage:**
```
You: Debug why notes aren't syncing to Obsidian
Claude: [Runs diagnostic checks and suggests fixes]
```

### 5. **performance-analyzer** Skill
**Purpose:** Profile and optimize application performance

**Features:**
- Benchmark search queries
- Profile API endpoints
- Analyze database query performance
- Check embedding generation speed
- Monitor memory usage

**Usage:**
```
You: Profile the search_notes endpoint
Claude: [Runs performance tests and suggests optimizations]
```

---

## 🔧 Additional Slash Commands

### Development Commands

#### `/test-service [service_name]`
Test a specific service with all its test cases
```markdown
# Test Service

Run comprehensive tests for a specific Second Brain service.

## Instructions

1. Ask for service name if not provided
2. Locate test file in `tests/test_[service_name].py`
3. Run pytest with coverage and verbose output
4. Show test results and coverage report
5. Highlight any failures or warnings

## Example
` ``bash
pytest tests/test_unified_capture_service.py -v --cov=services.unified_capture_service --cov-report=term-missing
` ``
```

#### `/check-deps`
Verify all dependencies and external services
```markdown
# Check Dependencies

Verify all required dependencies and external services are available.

## Instructions

1. Check Python package installations
2. Verify Ollama is running and models are available
3. Test whisper.cpp installation
4. Check SQLite extensions (sqlite-vec)
5. Validate .env configuration
6. Test database connectivity

## Services to Check
- Ollama API (http://localhost:11434)
- Whisper.cpp binary and models
- SQLite FTS5 extension
- sqlite-vec extension (optional)
- Discord bot token (if configured)
- Email service (if configured)
```

#### `/fix-imports`
Automatically fix and organize Python imports
```markdown
# Fix Imports

Automatically organize and fix Python imports across the codebase.

## Instructions

1. Use isort to organize imports
2. Remove unused imports with autoflake
3. Group imports: stdlib, third-party, local
4. Fix circular import issues
5. Update import paths after refactoring

## Commands
` ``bash
# Organize imports
isort services/ --profile black

# Remove unused imports
autoflake --remove-all-unused-imports --in-place services/*.py
` ``
```

#### `/db-migrate [action]`
Manage database migrations
```markdown
# Database Migration Manager

Create, apply, or rollback database migrations.

## Instructions

**Actions:**
- `create [name]` - Create new migration file
- `apply` - Apply pending migrations
- `rollback` - Rollback last migration
- `status` - Show migration status

## Example
` ``bash
# Apply all migrations
python migrate_db.py

# Check migration status
sqlite3 notes.db "SELECT * FROM migrations ORDER BY id DESC LIMIT 5"
` ``
```

### Note Management Commands

#### `/bulk-import [source]`
Import notes from various sources
```markdown
# Bulk Import Notes

Import notes from external sources (Notion, Evernote, plain text files).

## Instructions

1. Ask for import source type
2. Validate file format
3. Parse and convert to Second Brain format
4. Create notes with proper metadata
5. Run embedding generation
6. Sync to Obsidian vault

## Supported Sources
- Plain text/markdown files
- JSON exports
- CSV files
- Obsidian vault (different vault)
- Notion export
```

#### `/export-vault [format]`
Export entire vault to different formats
```markdown
# Export Vault

Export all notes to various formats.

## Instructions

1. Ask for export format (JSON, Markdown, PDF, HTML)
2. Query all notes from database
3. Convert to requested format
4. Preserve metadata and tags
5. Create organized directory structure
6. Generate index file

## Formats
- **JSON**: Full metadata export
- **Markdown**: Clean markdown with frontmatter
- **PDF**: Formatted PDF documents
- **HTML**: Static website
```

#### `/memory-consolidate`
Trigger memory consolidation process
```markdown
# Memory Consolidation

Manually trigger the memory consolidation service.

## Instructions

1. Check pending memory extractions
2. Run memory_consolidation_service
3. Process episodic memories
4. Generate semantic memories
5. Update memory search index
6. Show consolidation results

## Code
` ``python
from services.memory_consolidation_service import get_consolidation_service
from database import get_db_connection

service = get_consolidation_service(get_db_connection)
results = service.process_pending_memories()
` ``
```

### Integration Commands

#### `/setup-discord`
Configure Discord bot integration
```markdown
# Setup Discord Bot

Interactive setup for Discord bot integration.

## Instructions

1. Run setup_discord_bot.py
2. Guide user through token configuration
3. Generate bot invite URL
4. Test bot connectivity
5. Configure slash commands
6. Set up webhook endpoints

## Files
- scripts/dev/setup_discord_bot.py
- scripts/dev/get_bot_invite.py
- scripts/dev/validate_bot_token.py
```

#### `/setup-shortcuts`
Configure Apple Shortcuts integration
```markdown
# Setup Apple Shortcuts

Configure iOS/macOS integration for quick capture.

## Instructions

1. Show webhook URL
2. Generate API token
3. Provide Shortcut template
4. Test capture endpoint
5. Configure location services
6. Set up voice input

## Endpoints
- POST /capture
- POST /webhook/apple
- GET /api/auth/token
```

#### `/sync-obsidian`
Manually trigger Obsidian sync
```markdown
# Sync Obsidian Vault

Manually synchronize with Obsidian vault.

## Instructions

1. Check vault path configuration
2. Run obsidian_sync.py
3. Update YAML frontmatter
4. Sync new notes to vault
5. Import notes from vault
6. Resolve conflicts

## Code
` ``python
from obsidian_sync import ObsidianSync
from config import VAULT_PATH

sync = ObsidianSync(VAULT_PATH)
sync.sync_all_notes()
` ``
```

### Search & Analytics Commands

#### `/analyze-search`
Analyze search performance and usage
```markdown
# Analyze Search Performance

Analyze search query performance and usage patterns.

## Instructions

1. Query search_history table
2. Show most common queries
3. Analyze query performance metrics
4. Identify slow queries
5. Suggest index optimizations
6. Show search quality metrics

## Metrics
- Average query time
- Top queries by frequency
- Failed queries
- Zero-result queries
- FTS5 vs vector search usage
```

#### `/rebuild-index`
Rebuild search indices
```markdown
# Rebuild Search Index

Rebuild FTS5 and vector search indices.

## Instructions

1. Backup current indices
2. Clear existing FTS5 data
3. Rebuild from notes table
4. Regenerate embeddings
5. Verify index integrity
6. Show rebuild statistics

## Code
` ``python
from services.search_index import SearchIndexer

indexer = SearchIndexer()
results = indexer.rebuild_all(embeddings=True)
print(f"Indexed {results['notes_indexed']} notes")
` ``
```

#### `/tag-cleanup`
Clean up and organize tags
```markdown
# Tag Cleanup

Analyze and clean up tag usage across notes.

## Instructions

1. Find all unique tags
2. Identify similar tags (typos, plurals)
3. Suggest tag merges
4. Show tag frequency
5. Find orphaned tags
6. Standardize tag format

## Analysis
- Similar tags: "productivity" vs "productive"
- Case variations: "AI" vs "ai"
- Plural/singular: "books" vs "book"
- Unused tags
```

### Debugging Commands

#### `/debug-capture`
Debug note capture issues
```markdown
# Debug Note Capture

Debug issues with the unified capture service.

## Instructions

1. Run debug_capture.py with test data
2. Check service dependencies (Ollama, whisper)
3. Test file processors (PDF, OCR, audio)
4. Validate API endpoints
5. Check error logs
6. Test with minimal example

## Common Issues
- Ollama not responding
- Whisper model missing
- File permission errors
- Database connection issues
- Embedding generation failures
```

#### `/trace-request [endpoint]`
Trace API request through the stack
```markdown
# Trace API Request

Follow an API request through the entire application stack.

## Instructions

1. Add detailed logging to endpoint
2. Enable FastAPI debug mode
3. Make test request
4. Show full request/response cycle
5. Display service calls
6. Show database queries
7. Measure timing at each step

## Example
` ``bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Start server with reload
uvicorn app:app --reload --log-level debug
` ``
```

#### `/check-health`
Run comprehensive health check
```markdown
# System Health Check

Run comprehensive health check on all services.

## Instructions

1. Check database connectivity
2. Verify all services are initialized
3. Test external dependencies (Ollama, Whisper)
4. Check disk space for uploads/audio
5. Validate configuration
6. Test critical endpoints
7. Generate health report

## Health Checks
- ✅ Database: Connected, migrations applied
- ✅ Ollama: Running, model available
- ✅ Whisper: Binary found, model loaded
- ✅ Storage: 50GB free
- ⚠️  Discord: Token not configured
```

---

## 🔌 MCP Server Enhancements

### New Tools to Add to `mcp_server.py`

#### 1. **search_memories**
Search episodic and semantic memories
```python
Tool(
    name="search_memories",
    description="Search through episodic and semantic memories",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "memory_type": {
                "type": "string",
                "enum": ["episodic", "semantic", "both"],
                "default": "both"
            },
            "limit": {"type": "number", "default": 10}
        }
    }
)
```

#### 2. **process_audio**
Submit audio for transcription
```python
Tool(
    name="process_audio",
    description="Transcribe audio file to text",
    inputSchema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "language": {"type": "string", "default": "en"}
        }
    }
)
```

#### 3. **analyze_note_relationships**
Analyze relationships between notes
```python
Tool(
    name="analyze_note_relationships",
    description="Find related notes using semantic similarity",
    inputSchema={
        "type": "object",
        "properties": {
            "note_id": {"type": "number"},
            "min_similarity": {"type": "number", "default": 0.7},
            "limit": {"type": "number", "default": 5}
        }
    }
)
```

#### 4. **get_note_history**
Get edit history for a note
```python
Tool(
    name="get_note_history",
    description="Retrieve edit history and versions of a note",
    inputSchema={
        "type": "object",
        "properties": {
            "note_id": {"type": "number"}
        }
    }
)
```

#### 5. **bulk_tag_operations**
Perform bulk operations on tags
```python
Tool(
    name="bulk_tag_operations",
    description="Rename, merge, or delete tags across multiple notes",
    inputSchema={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["rename", "merge", "delete"]
            },
            "source_tag": {"type": "string"},
            "target_tag": {"type": "string"}
        }
    }
)
```

#### 6. **export_notes**
Export notes in various formats
```python
Tool(
    name="export_notes",
    description="Export notes to JSON, Markdown, or other formats",
    inputSchema={
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "enum": ["json", "markdown", "html", "pdf"]
            },
            "note_ids": {"type": "array", "items": {"type": "number"}},
            "output_path": {"type": "string"}
        }
    }
)
```

#### 7. **get_processing_status**
Check status of background processing tasks
```python
Tool(
    name="get_processing_status",
    description="Check status of audio transcription and AI processing",
    inputSchema={
        "type": "object",
        "properties": {
            "note_id": {"type": "number"}
        }
    }
)
```

#### 8. **search_by_date**
Search notes within date range
```python
Tool(
    name="search_by_date",
    description="Search notes created or modified within a date range",
    inputSchema={
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "format": "date"},
            "end_date": {"type": "string", "format": "date"},
            "query": {"type": "string"}
        }
    }
)
```

---

## 🌐 Recommended Third-Party MCP Servers

### 1. **SQLite MCP Server**
**Why:** Direct database access for advanced queries

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "/home/user/second_brain_v0/notes.db"]
    }
  }
}
```

**Use Cases:**
- Run custom SQL queries on your notes database
- Analyze data with complex aggregations
- Debug database issues
- Generate custom reports

### 2. **File System MCP Server**
**Why:** Direct access to vault and audio files

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/second_brain_v0/vault", "/home/user/second_brain_v0/audio"]
    }
  }
}
```

**Use Cases:**
- Read and edit Obsidian vault files directly
- Manage audio file uploads
- Inspect log files
- Access static files

### 3. **Git MCP Server**
**Why:** Enhanced Git operations for version control

```json
{
  "mcpServers": {
    "git": {
      "command": "uvx",
      "args": ["mcp-server-git", "--repository", "/home/user/second_brain_v0"]
    }
  }
}
```

**Use Cases:**
- Manage feature branches
- Review commit history
- Analyze code changes
- Automate git workflows

### 4. **PostgreSQL MCP Server** (Future Migration)
**Why:** If you migrate from SQLite to PostgreSQL

```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/second_brain"]
    }
  }
}
```

**Use Cases:**
- Production-ready database
- Better concurrent access
- Advanced search features
- Real-time collaboration

### 5. **Memory MCP Server**
**Why:** Enhanced context retention for long sessions

```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

**Use Cases:**
- Remember context across sessions
- Store development decisions
- Track feature discussions
- Maintain project knowledge

### 6. **Fetch MCP Server**
**Why:** Web scraping and content extraction

```json
{
  "mcpServers": {
    "fetch": {
      "command": "uvx",
      "args": ["mcp-server-fetch"]
    }
  }
}
```

**Use Cases:**
- Import articles for knowledge base
- Extract content from web pages
- Monitor documentation updates
- Scrape research papers

### 7. **Brave Search MCP Server**
**Why:** Research and information gathering

```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "your-api-key"
      }
    }
  }
}
```

**Use Cases:**
- Research technical solutions
- Find documentation
- Gather information for notes
- Validate implementation approaches

### 8. **Obsidian MCP Server** (Custom)
**Why:** Direct integration with Obsidian API

*Note: You may need to create this custom server*

**Features:**
- Direct Obsidian plugin API access
- Graph view analysis
- Link suggestions
- Template management

---

## 📊 Implementation Priority

### Phase 1: Essential (Immediate)
1. ✅ Update MCP server with new tools (search_memories, process_audio)
2. ✅ Add `/test-service` and `/check-deps` commands
3. ✅ Install SQLite and File System MCP servers
4. ✅ Create `second-brain-tester` skill

### Phase 2: High Value (This Week)
1. Add `/db-migrate` and `/rebuild-index` commands
2. Create `service-inspector` and `migration-helper` skills
3. Add Git MCP server
4. Implement `/debug-capture` and `/check-health` commands

### Phase 3: Enhanced Workflow (Next Week)
1. Add Memory and Fetch MCP servers
2. Create `/bulk-import` and `/export-vault` commands
3. Implement `performance-analyzer` skill
4. Add `/analyze-search` and `/tag-cleanup` commands

### Phase 4: Advanced Features (Future)
1. Brave Search MCP server integration
2. Custom Obsidian MCP server
3. PostgreSQL migration support
4. Advanced collaboration features

---

## 🚀 Quick Start

### Install MCP Servers

```bash
# Install SQLite MCP server
pip install mcp-server-sqlite

# Install File System MCP server (requires Node.js)
npm install -g @modelcontextprotocol/server-filesystem

# Install Git MCP server
pip install mcp-server-git

# Install Fetch server
pip install mcp-server-fetch
```

### Configure Claude Code

Add to your Claude Code settings (`~/.config/claude-code/config.json`):

```json
{
  "mcpServers": {
    "second-brain": {
      "command": "python",
      "args": ["/home/user/second_brain_v0/mcp_server.py"]
    },
    "sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "/home/user/second_brain_v0/notes.db"]
    },
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/home/user/second_brain_v0/vault",
        "/home/user/second_brain_v0/audio"
      ]
    },
    "git": {
      "command": "uvx",
      "args": ["mcp-server-git", "--repository", "/home/user/second_brain_v0"]
    }
  }
}
```

### Test MCP Connection

```bash
# Test the Second Brain MCP server
python mcp_server.py

# In Claude Code, try:
# "Search my notes for productivity tips"
# "Create a note about MCP integration"
# "Show me vault statistics"
```

---

## 📚 Resources

- [MCP Documentation](https://modelcontextprotocol.io/introduction)
- [Claude Code Skills Guide](https://docs.anthropic.com/claude/docs/claude-code-skills)
- [MCP Server Repository](https://github.com/modelcontextprotocol/servers)
- [Second Brain Architecture](./CLAUDE.md)

---

## 🤝 Contributing

To add new commands or MCP tools:

1. **Slash Commands**: Create `.md` file in `.claude/commands/`
2. **Skills**: Create `.md` file in `.claude/skills/` (if supported)
3. **MCP Tools**: Edit `mcp_server.py` and add new tool definitions
4. **Test**: Restart Claude Code and test the new functionality

---

**Last Updated:** 2025-11-13
**Version:** 1.0
**Status:** Ready for implementation
