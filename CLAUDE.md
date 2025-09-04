# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
Second Brain is a comprehensive knowledge management system combining multi-modal input capture, AI-powered processing, and intelligent retrieval. It integrates tightly with Obsidian vaults, Discord bots, and Apple Shortcuts for seamless cross-platform note-taking and search.

## Architecture Overview

### Core Application Layer
- **`app.py`** - Main FastAPI application with authentication, UI routes, and legacy endpoint handlers
- **`config.py`** - Centralized settings using Pydantic with environment variable loading
- **Database** - SQLite with FTS5 for full-text search and optional sqlite-vec extension for vector similarity

### Service Layer (`services/`)
The application uses a service-oriented architecture for modularity:
- **`search_adapter.py`** - Unified search service wrapping SQLite FTS5 + vector search with hybrid algorithms
- **`search_index.py`** - Advanced search indexer with chunk-based FTS5 and sqlite-vec integration
- **`embeddings.py`** - Sentence transformer embedding generation and management
- **`audio_queue.py`** - Asynchronous audio processing queue
- **`obsidian_sync.py`** - Service-layer Obsidian integration (newer implementation)
- **`auto_seeding_service.py`** - Automatic content seeding for new users to bootstrap search performance
- **`vault_seeding_service.py`** - Core vault seeding infrastructure with configurable content sets
- **Service Routers**: Modular FastAPI routers for specialized functionality (`*_router.py` files)

### Processing Pipeline
1. **Input Capture** - Multiple sources: web UI, Discord bot, Apple Shortcuts, file uploads
2. **Content Processing** - Audio transcription (whisper.cpp/Vosk), OCR, PDF extraction
3. **AI Enhancement** - LLM-powered summarization, tagging, and title generation via Ollama
4. **Storage & Indexing** - SQLite database with FTS5 and optional vector embeddings
5. **Auto-Seeding** - Intelligent content seeding for new users with starter knowledge base
6. **Obsidian Integration** - Real-time sync with YAML frontmatter for metadata

### Key Integration Points
- **Obsidian Sync**: Bi-directional sync with vault, YAML frontmatter processing for transcriptions and metadata
- **Discord Bot**: Slash commands for mobile/remote note capture via `discord_bot.py`
- **Apple Shortcuts**: Webhook endpoints (`/capture`, `/webhook/apple`) for iOS integration
- **Audio Processing**: Multi-backend transcription (whisper.cpp preferred, Vosk fallback)

## Development Commands

```bash
# Start development server
.venv/bin/python -m uvicorn app:app --reload --port 8082

# Database operations
python migrate_db.py                    # Run database migrations
python db_indexer.py                   # Legacy vault indexing (deprecated)

# Auto-seeding operations
python -c "from services.auto_seeding_service import get_auto_seeding_service; from database import get_db_connection; service = get_auto_seeding_service(get_db_connection); print(service.check_auto_seeding_status())"
python -c "from services.vault_seeding_service import get_seeding_service; from database import get_db_connection; service = get_seeding_service(get_db_connection); print(service.get_available_seed_content())"

# Search indexing operations
python -c "from services.search_index import SearchIndexer; indexer = SearchIndexer(); indexer.rebuild_all(embeddings=True)"

# Discord bot setup
python setup_discord_bot.py            # Configure Discord bot
python get_bot_invite.py              # Generate bot invite URL
python validate_bot_token.py          # Validate Discord token

# Email service setup (magic links)
python setup_email.py                 # Configure email service

# Testing utilities
python test_note_creation.py          # Test note creation flow
python test_file_processor.py         # Test file processing
python test_web_ingestion.py          # Test web content extraction
```

## Key Configuration

Environment variables are loaded via `config.py` from `.env` file:

### Required Setup
- **Whisper.cpp**: Audio transcription backend (build from source or download binary)
- **Ollama**: Local LLM server for AI processing (`ollama serve`, then `ollama pull llama3.2`)
- **SQLite Extensions**: Optional sqlite-vec for vector similarity search

### Critical Environment Variables
```bash
# Core paths
VAULT_PATH=./vault                     # Obsidian vault location
AUDIO_DIR=./audio                      # Audio file storage
WHISPER_CPP_PATH=./build/bin/whisper-cli
WHISPER_MODEL_PATH=./models/ggml-base.en.bin

# AI Services
OLLAMA_API_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=llama3.2

# Optional Extensions
SQLITE_VEC_PATH=/path/to/sqlite-vec0.dylib  # Vector similarity search
```

## Database Architecture

### Migration System
- Migrations in `db/migrations/*.sql` run automatically on startup
- Core schema: `001_core.sql` (notes, users, processing status)
- Vector extensions: `002_vec.sql` (requires sqlite-vec)

### Search Implementation
- **FTS5**: Primary full-text search via SQLite built-in with BM25 ranking and advanced snippet generation
- **Vector Search**: Optional semantic search via sqlite-vec extension with cosine similarity
- **Hybrid Search**: Advanced Reciprocal Rank Fusion (RRF) combining keyword + semantic results
- **Chunk-based Indexing**: Sophisticated content chunking for improved search granularity
- **Query Sanitization**: Robust FTS5 query preprocessing to handle special characters
- **Auto-Seeding**: Intelligent content bootstrapping with curated starter notes, bookmarks, and examples
- **Search Analytics**: Performance monitoring and query tracking for optimization

## Processing Flow

### Note Processing Pipeline (`tasks.py`)
1. Content extraction (text, audio transcription, OCR, PDF parsing)
2. AI processing (title generation, summarization, tag suggestion)
3. Embedding generation for vector search
4. Obsidian vault synchronization with YAML frontmatter
5. Search index updates

### Background Jobs
- Audio transcription queue with configurable concurrency
- Batch processing for multiple files
- CPU throttling for resource management
- Timeout handling for long-running operations

## Development Focus Areas

### Current Branch: `feature/smart-automation-multitenant`
- ✅ **Auto-seeding Complete**: Intelligent content seeding for new users with configurable namespaces
- ✅ **Advanced Search Indexer**: Chunk-based indexing with FTS5 + sqlite-vec hybrid search
- ✅ **Service Architecture**: Modular router system with comprehensive service layer
- 🔄 **Multi-tenant Foundations**: User isolation and intelligent content routing
- 🔄 **Smart Automation**: Workflow automation and intelligent content processing

### Key Integration Patterns
- **Service Registration**: Services auto-register with FastAPI via router inclusion
- **Background Processing**: Async queues for CPU-intensive operations
- **Configuration**: Environment-driven with sensible defaults
- **Error Handling**: Graceful degradation when optional services unavailable

## Testing Strategy
- Unit tests for individual components in `tests/`
- Integration tests for end-to-end flows
- Performance testing for search and processing pipelines
- Manual testing utilities in root directory (`test_*.py`)