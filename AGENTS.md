# AI Agent Integration Guide for Second Brain

This document outlines how AI agents (like Claude Code) can effectively work with the Second Brain project, providing structured approaches for development, enhancement, and maintenance.

## Project Overview

Second Brain is a comprehensive knowledge management system that captures, processes, and makes searchable various forms of content (text, audio, web content) using AI-powered analysis and hybrid search capabilities.

### Key Technologies
- **Backend**: FastAPI, SQLite with FTS5, Ollama (LLM), Whisper.cpp (audio)
- **API**: Modular routers in `api/routes_capture.py` and `api/routes_search.py`
- **Service Layer**: `services/` (search adapter, embeddings, jobs)
- **Frontend**: Vanilla JavaScript, Bootstrap, Server-Sent Events (SSE)
- **AI/ML**: Sentence-transformers, semantic embeddings, hybrid search
- **Integration**: Browser extension, Discord bot, Obsidian sync

## Agent Interaction Patterns

### 1. Claude Code Sub-Agent Integration

Claude Code provides specialized sub-agents that can be launched for complex multi-step tasks. Each sub-agent has specific capabilities and should be used strategically:

#### Available Sub-Agents
- **general-purpose**: Multi-step research, complex searches, file operations
- **code-writer**: Implementing code based on specifications or requirements  
- **project-planner**: Strategic planning, coordination, workflow optimization

#### Sub-Agent Usage Patterns
```python
# Use general-purpose agent for complex searches/analysis
- When searching across multiple files with uncertain matches
- For researching complex questions requiring multiple tool invocations
- When file patterns are unclear and multiple search rounds needed

# Use code-writer agent for implementation
- When you have clear specifications and need code written
- For implementing features based on existing plans or requirements
- When translating designs/specs into actual working code

# Use project-planner agent for coordination
- When breaking down large features into manageable tasks
- For optimizing multi-agent workflows and task coordination
- When strategic planning and subagent orchestration is needed
```

#### Integration with Second Brain Workflow
```bash
# Complex feature development with sub-agents
1. project-planner: Break down feature requirements
2. general-purpose: Research existing implementations  
3. code-writer: Implement the actual feature code
4. Main agent: Integration testing and validation
```

### 2. Development Workflow for Agents

When working on Second Brain, agents should follow this structured approach:

#### Phase 1: Analysis & Planning (Enhanced with Sub-Agents)
```bash
# Strategic planning for complex features
1. project-planner: Break down requirements from second_brain.PRD
2. general-purpose: Analyze current codebase state and patterns
3. Main agent: Create todo list and coordinate implementation plan

# For unknown codebases or complex searches
1. general-purpose: Deep research of file structure and dependencies
2. general-purpose: Multi-round search for specific implementation patterns
3. Main agent: Synthesize findings and create implementation plan

# Understanding current state
1. Read second_brain.PRD for comprehensive project requirements
2. Check git status and recent commits  
3. Review existing codebase structure (use general-purpose for complex analysis)
4. Identify specific task requirements (use project-planner for large features)
5. Create todo list using TodoWrite tool for complex tasks
```

#### Phase 2: Implementation (Enhanced with Sub-Agents)
```bash
# Code implementation workflow
1. code-writer: Implement features based on detailed specifications
2. general-purpose: Research integration patterns and dependencies
3. Main agent: Handle file operations, testing, and validation

# Systematic implementation
1. Use Read tool to understand existing code patterns (or general-purpose for complex analysis)
2. Follow established conventions and code style  
3. Prefer editing existing files over creating new ones
4. code-writer: Generate implementation code based on requirements
5. Test changes incrementally
6. Update todo list progress in real-time
```

#### Phase 3: Validation & Integration
```bash
# Ensuring quality
1. Run existing tests: python -m pytest tests/
2. Check for type errors: python -m mypy . (if configured)  
3. Verify database migrations work
4. Test API endpoints manually or with test scripts
5. Ensure UI components work as expected
```

### 2. Common Agent Tasks & Approaches

#### Adding New Features
- **Start with**: Read second_brain.PRD to understand how feature fits in roadmap
- **Database changes**: Create migration in `db/migrations/` following naming convention
- **API endpoints**: Add to the modular routers (`api/routes_capture.py`, `api/routes_search.py`) rather than `search_api.py`
- **Frontend**: Follow existing patterns in `static/js/` and `static/css/`
- **Testing**: Create test file in `tests/` directory

#### Bug Fixes
- **Reproduce issue**: Create minimal test case
- **Locate root cause**: Use Grep tool to find relevant code sections
- **Fix systematically**: Edit files using established patterns
- **Verify fix**: Run relevant tests and manual verification

#### Performance Optimization
- **Profile first**: Use `test_search_performance.py` as example
- **Database**: Check indexes, query optimization, VACUUM/ANALYZE
- **Code**: Focus on hot paths, caching, async operations
- **Frontend**: Minimize network requests, optimize rendering

### 3. File Structure & Navigation

#### Core Application Files
```
/Users/dhouchin/second_brain/
├── app.py                  # Main FastAPI application
├── config.py              # Configuration settings
├── second_brain.PRD       # Product Requirements Document
├── AGENTS.md              # This file - agent interaction guide
├── 
├── Core Processing/
│   ├── processor.py        # Note processing pipeline
│   ├── tasks.py           # Background task processing  
│   ├── tasks_enhanced.py  # Enhanced tasks with real-time status
│   └── llm_utils.py       # LLM integration utilities
├── 
├── Search System/
│   ├── search_engine.py    # FTS search engine
│   ├── semantic_search.py  # Semantic similarity search
│   ├── hybrid_search.py    # Hybrid FTS+semantic search  
│   ├── embedding_manager.py # Vector embedding management
│   └── search_api.py       # Legacy consolidated API (see api/routes_*.py)
├── 
├── API Routers/
│   ├── api/routes_capture.py  # Capture-related endpoints
│   └── api/routes_search.py   # Search-related endpoints
├── 
├── Services/
│   ├── services/search_adapter.py  # Unified search service over SQLite FTS5 (+optional sqlite-vec)
│   ├── services/embeddings.py      # Embedding utilities used by the adapter
│   ├── services/jobs.py            # Background job helpers
│   └── services/obsidian_sync.py   # Service-oriented Obsidian sync (SearchService-based)
├── 
├── Real-time Features/
│   ├── realtime_status.py  # SSE status broadcasting
│   └── test_realtime.py    # Real-time system testing
├── 
├── Database/
│   ├── notes.db           # Main SQLite database
│   ├── migrate_db.py      # Migration runner
│   └── db/migrations/     # Database schema migrations
├── 
├── Frontend/
│   ├── templates/         # Jinja2 HTML templates
│   ├── static/js/         # JavaScript modules
│   └── static/css/        # Stylesheets
├── 
├── Browser Extension/
│   └── browser-extension/ # Complete browser extension
├── 
├── Integrations/
│   ├── discord_bot.py     # Discord integration
│   ├── obsidian_sync.py   # Obsidian markdown export (root variant used by app)
│   └── audio_utils.py     # Audio processing utilities
└── 
└── Testing & Utils/
    ├── tests/             # Test suite
    ├── test_search_performance.py # Performance testing
    └── scripts/           # Utility scripts
```

Note: Two Obsidian sync implementations exist: `obsidian_sync.py` (root, used by `app.py`) and `services/obsidian_sync.py` (service-based, pairs with `SearchService`). Prefer the root module for app endpoints unless migrating to the service layer.

#### Key Configuration Files
- `config.py` - All settings and paths
- `requirements.txt` - Python dependencies  
- `requirements-dev.txt` - Development dependencies
- `.gitignore` - Git exclusions

### 4. Agent Best Practices

#### Code Style & Conventions
```python
# Follow existing patterns
- Use existing imports and utilities
- Match indentation and formatting style
- Add docstrings for new functions/classes
- Use type hints where established
- Follow naming conventions (snake_case for functions/variables)
```

#### Database Operations
```python
# Always use established patterns
conn = sqlite3.connect(db_path)
c = conn.cursor()
try:
    # Database operations
    c.execute("SELECT ...", (params,))
    results = c.fetchall()
    conn.commit()
finally:
    conn.close()
```

#### Error Handling
```python
# Graceful degradation pattern used throughout
try:
    from optional_dependency import SomeFeature  
    feature_available = True
except ImportError:
    feature_available = False
    logger.warning("Optional feature not available")

if feature_available:
    # Use feature
else:
    # Fallback behavior
```

#### API Response Format
```python
# Consistent API response structure
return {
    "success": True,
    "data": results,
    "message": "Operation completed",
    "metadata": {
        "count": len(results),
        "timestamp": datetime.now().isoformat()
    }
}
```

### 5. Testing Strategies for Agents

#### Automated Testing
```bash
# Run existing tests
python -m pytest tests/ -v

# Performance testing
python test_search_performance.py --quick

# Database migration testing
python migrate_db.py --dry-run
```

#### Manual Testing Workflows
```bash
# Start application
python app.py
# or
uvicorn app:app --reload --port 8084

# Test key workflows:
1. Upload audio file -> verify transcription -> check search
2. Create text note -> verify processing -> test semantic search  
3. Use browser extension -> verify capture -> check dashboard
4. Test real-time updates -> verify SSE events -> check progress
```

#### Integration Testing
```bash
# Test external dependencies
1. Ollama service availability
2. Whisper.cpp installation
3. Sentence-transformers model download
4. Browser extension loading
5. Discord bot connectivity (if configured)
6. sqlite-vec (optional vector search)
   - Ensure SQLITE_VEC_PATH points to the loadable extension file
   - Quick test: `python scripts/sqlite_vec_check.py`
```

### 6. Sub-Agent Development Scenarios for Second Brain

#### Scenario A: Complex Feature Development with Sub-Agents
**Task**: Implement advanced semantic search with reranking
```bash
1. project-planner: "Break down semantic search feature into implementation steps"
   - Analyzes requirements, creates task breakdown
   - Identifies dependencies and integration points
   - Suggests optimal development sequence

2. general-purpose: "Research current search implementation and semantic libraries"
   - Deep analysis of existing search_engine.py, hybrid_search.py
   - Investigates sentence-transformers integration patterns
   - Finds optimal embedding and reranking approaches

3. code-writer: "Implement semantic search backend based on research findings"
   - Creates new semantic search modules
   - Implements embedding generation and storage
   - Adds reranking algorithms and API endpoints

4. Main agent: Integration testing, database migrations, UI updates
```

#### Scenario B: Discord Bot Enhancement with Sub-Agents  
**Task**: Add comprehensive slash command system
```bash
1. general-purpose: "Analyze current Discord bot implementation and available API endpoints"
   - Maps existing bot commands to backend capabilities
   - Identifies missing functionality and integration opportunities
   - Researches Discord.py patterns and best practices

2. code-writer: "Implement additional slash commands based on API analysis"
   - Generates new command handlers with proper error handling
   - Creates rich embed responses and user interaction flows
   - Implements authentication and permission checks

3. Main agent: Testing commands, deployment, documentation updates
```

#### Scenario C: Large-Scale Refactoring with Sub-Agents
**Task**: Migrate from monolithic search to service-oriented architecture
```bash
1. project-planner: "Create migration strategy for search service refactoring"
   - Analyzes current search_api.py and plans modular decomposition
   - Identifies service boundaries and interface contracts
   - Creates phased migration plan with rollback strategies

2. general-purpose: "Research service patterns and extract existing functionality"
   - Deep analysis of current search implementations
   - Maps dependencies and data flows between components
   - Identifies reusable patterns and potential service interfaces

3. code-writer: "Implement new service modules based on migration plan"
   - Creates service classes with clean interfaces
   - Implements service registration and dependency injection
   - Migrates existing functionality to new service structure

4. Main agent: Database updates, configuration changes, integration testing
```

### 7. Common Development Scenarios

#### Scenario A: Adding New Search Filter
1. **Backend**: Add filter parameter to `HybridSearchRequest` in `search_api.py`
2. **Search Logic**: Update search methods in `hybrid_search.py` 
3. **Frontend**: Add UI control in `templates/search.html`
4. **JavaScript**: Update `static/js/advanced-search.js` to handle new filter
5. **CSS**: Style new UI element in `static/css/advanced-search.css`
6. **Test**: Verify filter works across all search modes

#### Scenario B: Improving Processing Pipeline
1. **Analysis**: Check `processor.py` and `tasks.py` for current logic
2. **Enhancement**: Modify processing steps, maintain backward compatibility
3. **Status Updates**: Update `tasks_enhanced.py` for real-time feedback
4. **Database**: Add migration if schema changes needed
5. **Test**: Verify processing works with real audio/text files

#### Scenario C: UI/UX Enhancement  
1. **Templates**: Update Jinja2 templates in `templates/`
2. **Styling**: Modify CSS in `static/css/` following existing patterns
3. **Interactivity**: Update JavaScript in `static/js/`
4. **Responsiveness**: Ensure mobile compatibility
5. **Test**: Verify across browsers and screen sizes

### 7. Troubleshooting Guide for Agents

#### Common Issues & Solutions

**Database Errors**
```bash
# Check database integrity
sqlite3 notes.db "PRAGMA integrity_check;"

# Apply missing migrations  
python migrate_db.py

# Rebuild search indexes
sqlite3 notes.db "INSERT INTO notes_fts(notes_fts) VALUES('rebuild');"
```

**Import Errors**
```bash
# Check dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Verify optional dependencies
python -c "import sentence_transformers; print('✅ Semantic search available')"
```

**Search Performance Issues**
```bash
# Run performance analysis
python test_search_performance.py --optimize

# Check embedding coverage
python -c "
from embedding_manager import EmbeddingManager
em = EmbeddingManager('notes.db')  
print(em.get_embedding_stats())
"
```

**Real-time Features Not Working**
```bash
# Test SSE endpoint
curl -N http://localhost:8084/api/status/stream/1

# Check status manager
python test_realtime.py
```

### 8. Sub-Agent Coordination Best Practices

#### When to Use Sub-Agents vs Direct Implementation
```python
# Use sub-agents for:
- Multi-file analysis requiring multiple search rounds
- Complex feature planning with many interdependent steps  
- Code generation based on specifications or existing patterns
- Research tasks requiring deep investigation

# Handle directly for:
- Single file edits or simple modifications
- Straightforward configuration changes
- Basic testing and validation tasks
- Simple database operations or API calls
```

#### Sub-Agent Task Coordination
```bash
# Effective sub-agent workflow
1. Launch sub-agents with specific, detailed prompts
2. Provide context about Second Brain architecture
3. Request structured output for easy integration
4. Coordinate findings between multiple sub-agents
5. Handle integration and testing at main agent level

# Example coordination:
- project-planner: Returns structured task breakdown
- general-purpose: Returns analysis with code locations and patterns
- code-writer: Returns implementable code following project patterns
```

#### Sub-Agent Output Integration
```python
# Structure sub-agent prompts for integration
"Research the current search implementation in Second Brain.
Focus on:
- File locations and key functions
- Integration patterns with SQLite and FTS5
- Error handling and configuration approaches
- Return structured findings for implementation planning"

# Handle sub-agent responses
- Validate findings against current codebase
- Integrate recommendations into todo list
- Use structured output to guide implementation
- Cross-reference between multiple sub-agent analyses
```

### 9. Agent Communication Patterns

#### Effective Status Updates
```markdown
✅ Completed: Feature X implementation
🔄 Working on: Feature Y database integration  
⏳ Next: Feature Y frontend interface
📊 Progress: 3/5 tasks complete
```

#### Code Review Requests
```markdown
Please review the following changes:
- Modified: app.py (lines 45-67) - Added new endpoint
- Added: search_filters.py - New filtering logic
- Updated: templates/search.html - New UI elements
- Test: Verified with curl and browser testing
```

#### Problem Reporting
```markdown
Issue: Search performance degraded after adding semantic search
Context: 500+ notes, semantic search taking >2000ms
Investigation: Need to check embedding generation and indexing
Next Steps: Run performance profiler, optimize database queries
```

### 9. Integration with External Tools

#### Ollama Integration
```python
# Standard pattern for LLM calls
from llm_utils import ollama_summarize, ollama_generate_title

result = ollama_summarize(content)
summary = result.get("summary", "")
tags = result.get("tags", [])
actions = result.get("actions", [])
```

#### Browser Extension Communication
```javascript  
// Message format for extension->app communication
{
  "type": "capture",
  "data": {
    "content": text,
    "url": currentUrl,
    "title": pageTitle,
    "tags": selectedTags
  }
}
```

#### Discord Bot Integration
```python
# Bot command pattern
@bot.command()
async def save_note(ctx, *, content):
    # Process content
    # Save to database
    # Respond with confirmation
```

### 10. Future Development Guidance

#### Planned Features (from PRD)
- **Phase 2**: Advanced AI analysis, mobile app, collaboration features
- **Phase 3**: Enterprise features, advanced integrations, workflow automation  
- **Phase 4**: AI assistant, predictive features, advanced analytics

#### Architecture Considerations
- **Scalability**: Consider database sharding for large installations
- **Security**: Implement proper authentication, data encryption
- **Performance**: Monitor and optimize search response times
- **Reliability**: Add error recovery, data backup strategies

#### Technology Evolution
- **AI Models**: Plan for model updates, fine-tuning capabilities
- **Search Technology**: Consider vector databases for large-scale deployments
- **Frontend**: Potential migration to modern framework (React/Vue)
- **Mobile**: React Native or native app development

---

## Quick Reference Commands

```bash
# Start development server
python app.py

# Run tests  
python -m pytest tests/

# Apply database migrations
python migrate_db.py

# Generate embeddings
python -c "
import asyncio
from embedding_manager import EmbeddingManager
em = EmbeddingManager('notes.db')
em.rebuild_embeddings()
asyncio.run(em.process_pending_jobs())
"

# Performance testing
python test_search_performance.py

# Real-time testing
python test_realtime.py

# Check application health
curl http://localhost:8084/health
```

This guide should be referenced alongside `second_brain.PRD` for comprehensive understanding of project requirements, architecture, and development approaches.
