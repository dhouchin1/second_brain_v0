# Vault Seeding Guide

## Overview

Vault seeding is the process of populating a Second Brain vault with high-quality starter content to improve search algorithm performance and provide users with immediately useful examples. This system allows for both programmatic seeding via scripts and user-friendly seeding through the web interface.

## Why Seed a Vault?

1. **Enhanced Search Performance**: More data provides better training for search algorithms, especially semantic search with embeddings
2. **Immediate Value**: Users get useful content right away instead of starting with an empty vault
3. **Usage Examples**: Seed content demonstrates best practices for note-taking, tagging, and organization
4. **Algorithm Training**: FTS5 and vector search work better with a diverse corpus of content

## Architecture

### Components

1. **Seed Script** (`scripts/seed_starter_vault.py`): Core seeding logic and data
2. **Seeding Service** (`services/vault_seeding_service.py`): Service layer for web integration
3. **Seeding Router** (`services/vault_seeding_router.py`): HTTP API endpoints
4. **Web Interface** (`templates/vault_seeding.html`): User-friendly seeding management
5. **Seed Data**: Curated notes, bookmarks, and reference content

### Data Flow

```
Seed Data (Python) → Validation → Markdown Files → Database → Search Index
                                     ↓
                            Vault/.seed_samples/
                               ├── note/
                               ├── bookmark/
                               └── reference/
```

## Seed Content Categories

### Notes
- **SOPs (Standard Operating Procedures)**: Productivity and workflow templates
- **Decision Records**: Architecture and technical decision documentation
- **Research Notes**: Technical learning and documentation
- **Performance Guides**: Optimization and tuning references

### Bookmarks
- **Technical References**: Links to important documentation and resources
- **Tools and Services**: Curated links to useful development tools
- **Learning Resources**: Educational content and tutorials

### Content Quality Standards

All seed content must meet these criteria:
- **Minimum Length**: Notes >50 chars, summaries >20 chars
- **Proper Tagging**: Relevant, searchable tags
- **Clear Summaries**: Concise, informative descriptions
- **Unique IDs**: No duplicate identifiers
- **Valid URLs**: Properly formatted links for bookmarks

## Usage

### Web Interface

1. Navigate to `/vault/seeding` in the application
2. Review current seeding status and system dependencies
3. Preview available seed content
4. Configure seeding options:
   - **Namespace**: Folder name for seed content (default: `.seed_samples`)
   - **Force Overwrite**: Replace existing files
   - **Include Embeddings**: Generate embeddings for semantic search
5. Click "Seed Vault" to populate with starter content

### Command Line

```bash
# Basic seeding
python scripts/seed_starter_vault.py

# Custom namespace
python scripts/seed_starter_vault.py --namespace "starter_content"

# Skip embeddings (faster, no Ollama required)
python scripts/seed_starter_vault.py --no-embed

# Force overwrite existing files
python scripts/seed_starter_vault.py --force

# Custom Ollama settings
python scripts/seed_starter_vault.py --embed-model "nomic-embed-text" --ollama-url "http://localhost:11434"
```

### Programmatic API

```python
from services.vault_seeding_service import get_seeding_service, SeedingOptions

# Get service instance
service = get_seeding_service(get_conn)

# Check current status
status = service.get_seeding_status(user_id)

# Preview seeding impact
preview = service.preview_seeding_impact(user_id)

# Perform seeding
options = SeedingOptions(
    namespace=".seed_samples",
    force_overwrite=False,
    include_embeddings=True
)
result = service.seed_vault(user_id, options)

# Clear seed content
result = service.clear_seed_content(user_id)
```

## HTTP API Endpoints

### GET `/api/vault/seeding/status`
Returns current seeding status for the authenticated user.

**Response:**
```json
{
  "success": true,
  "data": {
    "is_seeded": false,
    "seed_notes_count": 0,
    "seed_files_exist": false,
    "vault_path": "/path/to/vault"
  }
}
```

### GET `/api/vault/seeding/available-content`
Returns information about available seed content.

**Response:**
```json
{
  "success": true,
  "data": {
    "notes": [...],
    "bookmarks": [...],
    "total_items": 8
  }
}
```

### POST `/api/vault/seeding/seed`
Performs vault seeding with the specified options.

**Request:**
```json
{
  "namespace": ".seed_samples",
  "force_overwrite": false,
  "include_embeddings": true,
  "embed_model": "nomic-embed-text",
  "ollama_url": "http://localhost:11434"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully seeded vault with 8 notes and 8 files",
  "data": {
    "notes_created": 8,
    "embeddings_created": 8,
    "files_written": 8
  }
}
```

### POST `/api/vault/seeding/clear`
Removes all seed content from the vault and database.

### GET `/api/vault/seeding/test-dependencies`
Tests system dependencies (Ollama, vault permissions).

## Dependencies

### Required
- **Python 3.8+**: Core runtime
- **SQLite with FTS5**: Full-text search capabilities
- **Writable Vault Directory**: File system access

### Optional
- **Ollama**: For embedding generation (`localhost:11434`)
- **sqlite-vec**: Enhanced vector search capabilities
- **requests**: HTTP client for Ollama API

## File Organization

Seed content is organized in the vault as follows:

```
vault/
└── .seed_samples/          # Default namespace
    ├── note/               # Note-type content
    │   ├── seed-sop-weekly-review.md
    │   ├── seed-decision-auth-front.md
    │   └── ...
    ├── bookmark/           # Bookmark-type content
    │   ├── seed-bm-fts5-overview.md
    │   └── ...
    └── reference/          # Reference-type content
        └── seed-http-cheatsheet.md
```

Each file contains:
- **YAML Frontmatter**: Metadata (tags, type, timestamps)
- **Markdown Content**: Structured, searchable text
- **Obsidian Compatibility**: Native markdown format

## Validation and Quality Control

### Pre-Seeding Validation
- Content structure validation
- ID uniqueness checks
- Required field verification
- URL format validation
- Content length requirements

### Runtime Checks
- Vault path existence and permissions
- Database connectivity
- Optional service availability (Ollama)
- Write permission testing

### Error Handling
- Graceful degradation when services unavailable
- Detailed error messages and logging
- Rollback on partial failures
- User-friendly error reporting

## Search Integration

Seeded content automatically integrates with Second Brain's search systems:

### FTS5 Full-Text Search
- Content indexed in `notes_fts` virtual table
- BM25 ranking for relevance scoring
- Porter stemming for better matching

### Semantic Search
- Vector embeddings generated via Ollama
- Stored in sqlite-vec or JSON fallback
- Hybrid search combining keyword + semantic

### Search Analytics
- Seeded content contributes to search result quality
- Performance metrics tracked and analyzed
- User behavior learning enhanced with diverse content

## Maintenance and Updates

### Adding New Seed Content

1. **Update Seed Data**: Modify `SEED_NOTES` or `SEED_BOOKMARKS` in the seed script
2. **Validate Content**: Ensure all quality standards are met
3. **Test Changes**: Run validation and test seeding process
4. **Deploy**: Update production with new seed data

### Content Categories

Consider adding content in these areas:
- **Domain-Specific Knowledge**: Industry or field-specific information
- **Workflow Templates**: Common productivity patterns
- **Integration Examples**: API usage, tool configurations
- **Learning Pathways**: Educational content sequences

### Monitoring and Metrics

- Track seeding success/failure rates
- Monitor search performance improvements
- Analyze user engagement with seed content
- Measure vault adoption and usage patterns

## Security Considerations

### Data Privacy
- No personal information in seed content
- Generic, educational examples only
- Safe for multi-tenant environments

### File System Security
- Seed content isolated in designated namespace
- Permission validation before file operations
- Safe cleanup and removal processes

### API Security
- Authentication required for all operations
- User-scoped data access only
- Rate limiting and request validation

## Troubleshooting

### Common Issues

**"Ollama connection failed"**
- Ensure Ollama is running on specified port
- Check firewall and network connectivity
- Verify model availability (`ollama list`)

**"Permission denied writing to vault"**
- Check vault directory permissions
- Ensure application has write access
- Verify disk space availability

**"Seed data validation failed"**
- Review error messages for specific issues
- Check content format and required fields
- Validate URL formats and ID uniqueness

### Debug Mode
```bash
# Enable detailed logging
PYTHONPATH=. python scripts/seed_starter_vault.py --help 2>&1 | head -20
```

### Recovery
- Use `clear_seed_content()` to remove problematic seeding
- Check database integrity with SQLite tools
- Restore from backup if necessary

## Future Enhancements

### Planned Features
- **Custom Seed Packs**: User-defined content collections
- **Dynamic Content**: API-driven seed content updates  
- **A/B Testing**: Different seed strategies for optimization
- **Community Seeds**: Shared seed content from users

### Integration Opportunities
- **Knowledge Graph**: Enhanced semantic relationships
- **AI Curation**: Automatic content quality improvement
- **Multi-Modal**: Audio, image, and video seed content
- **Collaborative**: Team-based seed content management

---

## Quick Start

1. **Web Interface**: Visit `/vault/seeding` and click "Seed Vault"
2. **Command Line**: Run `python scripts/seed_starter_vault.py --no-embed`
3. **Verify**: Check vault files and search functionality

This seeding system provides immediate value to new users while improving the platform's search capabilities through diverse, high-quality content.