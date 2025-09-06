# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## GitHub Repository
- **Repository**: [dhouchin1/second_brain](https://github.com/dhouchin1/second_brain)
- **Primary Branch**: `main`
- **Development Model**: Feature branches with PR-based workflow
- **Recent Activity**: Active development with automated PR integration (#18)

## Project Overview
Second Brain is a comprehensive knowledge management system combining multi-modal input capture, AI-powered processing, and intelligent retrieval. It integrates tightly with Obsidian vaults, Discord bots, and Apple Shortcuts for seamless cross-platform note-taking and search.

## Current Development Status (2025-09-05)
**Phase:** Feature Complete MVP with Advanced Capture
**Test Coverage:** 58/77 tests passing (75% success rate)
**Stability:** Core unified capture system fully tested and stable
**Next Phase:** Comprehensive manual testing and deployment preparation

## Architecture Overview

### Core Application Layer
- **`app.py`** - Main FastAPI application with authentication, UI routes, and legacy endpoint handlers
- **`config.py`** - Centralized settings using Pydantic with environment variable loading
- **Database** - SQLite with FTS5 for full-text search and optional sqlite-vec extension for vector similarity

### Service Layer (`services/`)
The application uses a service-oriented architecture for modularity:

#### Core Services (Fully Tested ✅)
- **`unified_capture_service.py`** - Central orchestration for all content capture (16/16 tests passing)
- **`unified_capture_router.py`** - Enhanced REST API with flexible request handling
- **`search_adapter.py`** - Unified search service wrapping SQLite FTS5 + vector search with hybrid algorithms
- **`search_index.py`** - Advanced search indexer with chunk-based FTS5 and sqlite-vec integration
- **`embeddings.py`** - Sentence transformer embedding generation and management

#### Advanced Capture Services (Implemented, Testing In Progress ⚠️)
- **`advanced_capture_service.py`** - OCR, PDF, YouTube processing with dependency management
- **`enhanced_apple_shortcuts_service.py`** - iOS/macOS integration with location and context data
- **`enhanced_discord_service.py`** - Discord bot integration with thread processing

#### Supporting Services
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

## Frontend Development Roadmap

### Current Status (2025-09-06)
✅ **Foundation Complete**: Modern dashboard v2 created with TailwindCSS and vanilla JavaScript
✅ **Core API Endpoints**: RESTful API for notes CRUD, search, and statistics
✅ **Basic Dashboard**: Clean interface with note creation, search, recent notes, and stats
✅ **PWA Support**: Service worker, manifest, offline capabilities via existing base.html

### Phase 1: Core Functionality (Current - Week 1)
**Status: ✅ COMPLETED**
- [x] Modern dashboard UI with TailwindCSS
- [x] Note creation and display
- [x] Basic search functionality
- [x] Statistics dashboard
- [x] RESTful API endpoints (`/api/notes`, `/api/search`, `/api/stats`)
- [x] Responsive design foundation

**Access:** Visit `/dashboard/v2` for the new interface

### Phase 2: Enhanced UX (Week 2-3)
**Priority: HIGH**
- [ ] **Real-time Updates**: WebSocket integration for live note updates
- [ ] **Advanced Search UI**: 
  - Search filters (date, type, tags)
  - Search suggestions and autocomplete
  - Saved searches
- [ ] **Note Management**:
  - Individual note viewing modal
  - Inline editing
  - Note deletion and archiving
  - Bulk operations
- [ ] **Improved Mobile UX**:
  - Mobile-first responsive improvements
  - Touch-friendly interactions
  - Mobile capture shortcuts

### Phase 3: Advanced Features (Week 4-5)
**Priority: MEDIUM**
- [ ] **Rich Text Editor**: Markdown support with preview
- [ ] **File Upload Integration**: Drag-and-drop file uploads
- [ ] **Audio Recording**: Browser-based voice note capture
- [ ] **Tagging System**: 
  - Tag autocomplete
  - Tag-based filtering
  - Tag clouds and analytics
- [ ] **Keyboard Shortcuts**: Power user shortcuts (Ctrl+N, Ctrl+S, etc.)

### Phase 4: Smart Features (Week 6-8)
**Priority: MEDIUM**
- [ ] **AI Integration UI**:
  - Smart title suggestions
  - Content summarization display
  - AI-powered tag suggestions
- [ ] **Related Notes**: Visual connections and suggestions
- [ ] **Search Analytics**: Search performance and insights
- [ ] **Content Organization**:
  - Folders/categories
  - Custom views and layouts
  - Note templates

### Phase 5: Collaboration & Sync (Week 9-12)
**Priority: LOW**
- [ ] **Multi-user Features**: If implementing multi-tenancy
- [ ] **Export/Import**: Various formats (Markdown, JSON, PDF)
- [ ] **Advanced Obsidian Integration**: Bi-directional sync UI
- [ ] **Browser Extension Integration**: Enhanced popup and capture

### Technical Architecture

#### Frontend Stack
- **Framework**: Vanilla JavaScript (for simplicity and speed)
- **Styling**: TailwindCSS with custom design system
- **Icons**: Heroicons (via TailwindCSS)
- **State Management**: Simple JavaScript objects and local storage
- **Build Process**: None (keeping it simple for now)

#### API Design
- **RESTful Endpoints**: `/api/notes`, `/api/search`, `/api/stats`
- **Authentication**: Existing FastAPI session-based auth
- **Response Format**: JSON with consistent error handling
- **Rate Limiting**: To be implemented in Phase 2

#### Performance Considerations
- **Lazy Loading**: Implement for large note lists
- **Search Debouncing**: 300ms delay on search input
- **Caching**: Browser-side caching for static data
- **Progressive Loading**: Load notes in batches of 20

### Browser Support
- **Target**: Modern browsers (Chrome 90+, Firefox 88+, Safari 14+)
- **PWA**: Full Progressive Web App support
- **Mobile**: iOS Safari, Android Chrome
- **Offline**: Basic offline support via service worker

### Development Commands (Updated)

```bash
# Start development server with new frontend
.venv/bin/python -m uvicorn app:app --reload --port 8082

# Access new dashboard
# Visit: http://localhost:8082/dashboard/v2

# API testing
curl -X GET "http://localhost:8082/api/notes" -H "Authorization: Bearer YOUR_TOKEN"
curl -X POST "http://localhost:8082/api/notes" -H "Content-Type: application/json" -d '{"content":"Test note"}'
curl -X GET "http://localhost:8082/api/search?q=test"
```

### Migration Strategy
- **Backward Compatibility**: Original dashboard remains at `/` route
- **Gradual Migration**: Users can opt into new interface
- **Feature Parity**: Ensure all existing features work in new UI
- **Data Compatibility**: No database changes required