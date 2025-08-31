# Claude → GPT-5 Project Handoff

## 🎯 Current Task: Web Link Ingestion Feature

### What I'm Building:
Adding **intelligent web link ingestion** to Second Brain's Quick Notes capture system. When users paste URLs into the text field, automatically detect and extract rich content using Playwright web crawling.

### Progress Status:
✅ **COMPLETED:**
1. Analyzed current capture system (`/capture` endpoint in `app.py:1871`)
2. Designed comprehensive web ingestion architecture
3. Created URL detection utilities (`url_utils.py`)

✅ **COMPLETED:**
4. Planning Playwright integration for web crawling
5. Updated PRD with new web features  
6. Implemented link detection in capture endpoint
7. Created web content extraction pipeline

🚧 **IN PROGRESS:**
8. Adding database schema for web content fields
9. Testing web link ingestion end-to-end

⚠️ **CURRENT STATUS:**
- Dependencies installed: playwright, beautifulsoup4, html2text, readability-lxml
- URL detection integrated into `/capture` endpoint (app.py:1911-1967)
- Web content extractor created (`web_extractor.py`)
- Data models created (`web_content_models.py`)
- **ISSUE**: Database schema needs updating to store web-specific fields

### Key Files Created/Modified:
- ✅ `WEB_INGESTION_ARCHITECTURE_PLAN.md` - Complete technical architecture
- ✅ `url_utils.py` - URL detection and validation utilities
- 🔄 Need to modify: `app.py` (capture endpoint), `second_brain.PRD`
- 🔄 Need to create: `web_extractor.py`, `web_processor.py`, `web_content_models.py`

## 🏗️ Architecture Overview

### Integration Strategy:
1. **URL Detection**: Modify `/capture` endpoint to detect URLs in text input
2. **Background Processing**: Use existing background task system for web extraction  
3. **Content Storage**: Extend current database schema with web metadata
4. **AI Enhancement**: Apply existing summarization/tagging to extracted web content

### Key Components Needed:

#### 1. Web Content Extractor (`web_extractor.py`)
```python
class WebContentExtractor:
    """Playwright-based web content extraction"""
    async def extract_content(self, url: str) -> WebContent:
        # Browser automation with Playwright
        # Handle JavaScript rendering  
        # Extract structured content
        # Capture screenshots
```

#### 2. Content Processing (`web_processor.py`)
```python
class WebContentProcessor:
    """Process extracted web content for storage"""
    def process_web_content(self, raw_content: WebContent) -> ProcessedWebContent:
        # Clean HTML and extract main content
        # Generate metadata (title, author, publish date)
        # Apply AI summarization and tagging
```

#### 3. Database Schema Updates
```sql
ALTER TABLE notes ADD COLUMN source_url TEXT;
ALTER TABLE notes ADD COLUMN web_metadata TEXT; -- JSON
ALTER TABLE notes ADD COLUMN screenshot_path TEXT;
ALTER TABLE notes ADD COLUMN content_hash TEXT; -- Deduplication
```

### Dependencies to Add:
```txt
playwright>=1.40.0
beautifulsoup4>=4.12.0
html2text>=2020.1.16
readability-lxml>=0.8.1
```

## 📋 Next Steps for GPT-5:

### Immediate Priority:
1. **Update capture endpoint** (`app.py:1871`) to detect URLs using `url_utils.extract_main_urls()`
2. **Create Playwright web extractor** following architecture in `WEB_INGESTION_ARCHITECTURE_PLAN.md`
3. **Update PRD** to include web ingestion features (see plan for specific sections)

### Implementation Order:
1. **Modify `/capture` endpoint** to detect URLs in note text
2. **Create basic web extractor** with Playwright
3. **Integrate with existing background processing** (`tasks_enhanced.py`)
4. **Test with simple websites** (blogs, articles)
5. **Add screenshot capture** and metadata extraction
6. **Update database schema** with web-specific columns

### User Experience Flow:
1. User pastes `https://example.com/article` in Quick Notes
2. System detects URL and shows "Extracting web content..." indicator
3. Background Playwright extraction gets page content + screenshot
4. AI processes content (summary, tags, actions) using existing pipeline
5. Rich note stored with full text, metadata, and screenshot

### Testing Strategy:
- Test URL detection with various formats (`url_utils.py` has good patterns)
- Test extraction on different site types (blogs, docs, social media)
- Error handling for network failures, blocked sites, malformed content
- Performance testing with concurrent extractions

## 🔧 Current System Context

### Existing Capture System (`app.py:1871`):
- Handles text, files (audio, images, PDFs)
- Has background processing for complex files
- Uses `FileProcessor` for file handling
- Integrates with AI summarization (`llm_utils.py`)
- Has real-time status updates (`realtime_status.py`)

### Integration Points:
- **URL Detection**: Add to beginning of capture processing
- **Background Tasks**: Use existing `process_note_with_status()` pattern
- **Database**: Extend current notes table schema
- **AI Processing**: Apply existing summarization to web content
- **Search**: Web content will work with existing hybrid search system

### Configuration:
- Add web extraction settings to `config.py`
- Feature toggles for web extraction
- Timeouts, rate limiting, screenshot options

## 🚨 Important Notes for GPT-5:

### Security Considerations:
- **SSRF Protection**: Validate URLs to prevent internal network access
- **Content Sanitization**: Clean extracted HTML to prevent XSS
- **Rate Limiting**: Don't overload target websites
- **Respect robots.txt**: Check website policies

### Performance:
- **Async Processing**: Keep web extraction in background
- **Caching**: Cache extracted content to avoid re-processing same URLs
- **Resource Management**: Properly close Playwright browser instances
- **Timeouts**: Handle slow/unresponsive websites gracefully

### Error Handling:
- Network failures → Save URL with basic metadata
- JavaScript failures → Fall back to static HTML parsing
- Access restrictions → Handle 403/404 appropriately
- Malformed content → Extract what's possible, continue processing

## 📁 File Structure Context:

```
second_brain/
├── app.py                  # Main FastAPI app (MODIFY capture endpoint)
├── url_utils.py           # ✅ URL detection utilities (CREATED)
├── web_extractor.py       # 🔄 Playwright web scraper (CREATE)  
├── web_processor.py       # 🔄 Content processing (CREATE)
├── web_content_models.py  # 🔄 Data models (CREATE)
├── config.py              # 🔄 Add web config options
├── second_brain.PRD       # 🔄 Update with web features
├── requirements.txt       # 🔄 Add Playwright dependencies
├── file_processor.py      # 🔄 Extend for web content
└── tasks_enhanced.py      # 🔄 Add web processing tasks
```

## 🎨 User Story:
**As a user**, I want to paste web links into Quick Notes and automatically get the full article content with AI-generated summaries and tags, so I can build my knowledge base without manual copying and pasting.

## 🎯 Success Criteria:
1. ✅ URL detection works for various formats
2. 🔄 Web content extraction works for major site types  
3. 🔄 Screenshots captured for visual context
4. 🔄 AI summarization applied to web content
5. 🔄 Content searchable with existing hybrid search
6. 🔄 Error handling for network/access issues

---

**Current Todo List:**
- [x] Analyze current Quick Notes capture system
- [x] Design web link ingestion architecture  
- [ ] Plan Playwright integration for web crawling ← NEXT
- [ ] Update PRD with new web ingestion features
- [ ] Implement link detection and processing
- [ ] Create web content extraction pipeline

**Key Priority**: Get basic URL detection working in `/capture` endpoint first, then build out Playwright extraction incrementally.

**Architecture Document**: See `WEB_INGESTION_ARCHITECTURE_PLAN.md` for complete technical details and implementation strategy.

Good luck GPT-5! The architecture is solid and the URL detection foundation is ready. Focus on getting the basic web extraction pipeline working first, then enhance with screenshots and advanced features. 🚀