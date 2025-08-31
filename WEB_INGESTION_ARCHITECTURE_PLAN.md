# Web Link Ingestion Architecture Plan

## 🎯 Objective

Add intelligent web link ingestion to Second Brain's Quick Notes capture system. When a user pastes a URL into the text field, automatically detect it and extract rich content using Playwright for a seamless knowledge capture experience.

## 🏗️ Current Capture System Analysis

### Existing Flow:
1. User inputs text/file via `/capture` endpoint
2. System processes based on content type (text, audio, image, PDF)
3. AI processing generates summaries, tags, and actions
4. Content stored with metadata in SQLite database
5. Background processing for complex files (audio transcription)

### Integration Points:
- **Detection**: Modify content processing in `/capture` endpoint
- **Processing**: Add web content extraction pipeline
- **Storage**: Extend database schema for web content metadata
- **AI Enhancement**: Apply existing summarization/tagging to extracted content

## 🌐 Web Ingestion Architecture

### 1. URL Detection & Validation
```python
def detect_urls(text: str) -> List[str]:
    """Extract and validate URLs from input text"""
    # Regex pattern for URLs
    # Support for http/https schemes
    # Domain validation
    # Return list of valid URLs
```

### 2. Content Extraction Pipeline
```python
class WebContentExtractor:
    """Playwright-based web content extraction"""
    
    async def extract_content(self, url: str) -> WebContent:
        # Browser automation with Playwright
        # Handle JavaScript rendering
        # Extract structured content
        # Capture screenshots
        # Handle different content types
```

### 3. Content Processing & Enhancement
```python
class WebContentProcessor:
    """Process extracted web content for storage"""
    
    def process_web_content(self, raw_content: WebContent) -> ProcessedWebContent:
        # Clean and structure HTML
        # Extract metadata (title, description, author)
        # Generate intelligent summaries
        # Extract key information and entities
        # Create searchable content
```

### 4. Storage & Metadata
```sql
-- Extend notes table with web-specific fields
ALTER TABLE notes ADD COLUMN source_url TEXT;
ALTER TABLE notes ADD COLUMN web_metadata TEXT; -- JSON metadata
ALTER TABLE notes ADD COLUMN screenshot_path TEXT;
ALTER TABLE notes ADD COLUMN content_hash TEXT; -- For deduplication
```

## 🎨 User Experience Flow

### Seamless Integration:
1. **User pastes link** in Quick Notes: `https://example.com/article`
2. **System detects URL** and shows processing indicator
3. **Background extraction** using Playwright
4. **Content preview** with option to edit/confirm
5. **AI processing** generates summary, tags, actions
6. **Stored as rich note** with full text + metadata

### Smart Features:
- **Auto-title generation** from page title
- **Screenshot capture** for visual context  
- **Content deduplication** (don't re-process same URLs)
- **Metadata extraction** (author, publish date, site)
- **Related content linking** to existing notes

## 🔧 Technical Implementation Plan

### Phase 1: Core Web Extraction
```python
# New files to create:
- web_extractor.py      # Playwright-based content extraction
- web_processor.py      # Content cleaning and processing  
- url_utils.py          # URL detection and validation
- web_content_models.py # Data models for web content
```

### Phase 2: Integration with Capture System
```python
# Modified files:
- app.py                # Update /capture endpoint with URL detection
- file_processor.py     # Add web content processing capability
- tasks_enhanced.py     # Background web processing tasks
```

### Phase 3: Database & Storage
```sql
-- Database schema updates:
- Add web-specific columns to notes table
- Create web_content_cache table for performance
- Add indexes for URL-based queries
```

### Phase 4: AI Enhancement
```python
# Enhanced AI processing:
- Apply existing summarization to web content
- Intelligent tagging based on content type
- Action item extraction from articles
- Entity recognition for people, companies, concepts
```

## 📋 PRD Updates Required

### New Features Section:
```markdown
#### 3.1.5 Web Content Ingestion
- **URL Detection**: Automatic recognition of web links in Quick Notes
- **Content Extraction**: Playwright-powered web scraping and content extraction
- **Rich Metadata**: Capture page title, description, author, publish date
- **Screenshot Capture**: Visual snapshot of web pages for context
- **Content Processing**: AI-powered summarization and tagging of web content
- **Deduplication**: Smart handling of duplicate URLs and content
```

### Technical Architecture Updates:
```markdown
### 4.1 Technology Stack (Updated)
- **Web Scraping**: Playwright for JavaScript-heavy sites and content extraction
- **Content Processing**: BeautifulSoup for HTML parsing and cleaning
- **Deduplication**: Content hashing for smart duplicate detection
- **Screenshot Storage**: Local file system with optimization
```

### API Endpoints:
```markdown
#### 4.3.1 Core Endpoints (Updated)
- `POST /capture` - Enhanced with URL detection and web content processing
- `GET /web-preview/{note_id}` - Preview extracted web content
- `POST /web-extract` - Manual web content extraction
- `GET /web-metadata/{url_hash}` - Cached web content metadata
```

## 🛠️ Implementation Details

### Dependencies to Add:
```txt
playwright>=1.40.0
beautifulsoup4>=4.12.0
html2text>=2020.1.16
readability-lxml>=0.8.1
newspaper3k>=0.2.8  # Alternative content extractor
```

### Configuration Options:
```python
# config.py additions
web_extraction_enabled: bool = True
playwright_timeout: int = 30  # seconds
max_content_length: int = 100000  # characters
screenshot_enabled: bool = True
screenshot_format: str = "webp"  # webp, png, jpeg
content_cache_ttl: int = 86400  # 24 hours
```

### Error Handling:
- **Network timeouts**: Graceful fallback to basic metadata
- **JavaScript failures**: Fallback to static HTML parsing
- **Access restrictions**: Handle 403/404 errors appropriately  
- **Malformed URLs**: Validation and user feedback
- **Rate limiting**: Respect robots.txt and implement delays

## 🎯 Content Extraction Strategy

### Multi-Stage Extraction:
1. **Basic metadata**: Title, description from HTML meta tags
2. **Content extraction**: Main article content using readability algorithms
3. **Enhanced processing**: Full rendering with Playwright for JS-heavy sites
4. **Screenshot capture**: Visual representation for context
5. **Content cleaning**: Remove ads, navigation, boilerplate

### Supported Content Types:
- **Articles & Blogs**: Full text extraction with metadata
- **Documentation**: Technical content with code examples
- **Social Media**: Posts with media (where accessible)
- **Academic Papers**: Abstract and content extraction
- **News Articles**: Headlines, content, publish date
- **Product Pages**: Descriptions, specifications, reviews

## 📈 Performance Considerations

### Optimization Strategies:
- **Async processing**: Background extraction to avoid UI blocking
- **Content caching**: Cache extracted content to avoid re-processing
- **Lazy loading**: Load screenshots and full content on demand
- **Rate limiting**: Respect website policies and avoid overloading
- **Resource management**: Playwright browser lifecycle management

### Scalability:
- **Queue system**: Handle multiple URL extractions efficiently
- **Resource limits**: Prevent memory/CPU exhaustion
- **Cleanup strategies**: Automatic cleanup of old cached content
- **Monitor usage**: Track extraction success rates and performance

## 🔒 Security & Privacy

### Security Measures:
- **URL validation**: Prevent SSRF attacks
- **Content sanitization**: Clean extracted HTML/text
- **File system protection**: Secure screenshot storage
- **Rate limiting**: Prevent abuse of extraction service

### Privacy Considerations:
- **User consent**: Clear indication when web extraction occurs
- **Data retention**: Configurable retention policies for web content
- **Access logs**: Optional logging of extracted URLs
- **Content sensitivity**: Handle private/authenticated content appropriately

## 🧪 Testing Strategy

### Test Coverage:
- **URL detection**: Various URL formats and edge cases
- **Content extraction**: Different website structures and frameworks
- **Error handling**: Network failures, malformed content
- **Performance**: Extraction speed and resource usage
- **Integration**: Full capture workflow with web content

### Test Sites:
- **Static HTML**: Simple blogs and documentation sites
- **JavaScript-heavy**: SPAs and dynamic content sites
- **Complex layouts**: News sites with ads and navigation
- **Error scenarios**: 404s, timeouts, restricted access

## 🚀 Deployment Considerations

### Infrastructure:
- **Playwright setup**: Browser installation and management
- **Resource allocation**: CPU/memory requirements for browser automation
- **Storage planning**: Screenshot and content cache storage
- **Monitoring**: Track extraction success rates and errors

### Configuration Management:
- **Environment variables**: Feature toggles and limits
- **Content policies**: What types of content to extract
- **Performance tuning**: Timeouts, concurrency limits
- **Fallback strategies**: What to do when extraction fails

---

## 🎉 Expected Benefits

### User Experience:
- **Frictionless capture**: Just paste a link and get rich content
- **Better organization**: Automatic tagging and summarization
- **Visual context**: Screenshots provide immediate recognition
- **Search enhancement**: Full-text search of web content

### Knowledge Management:
- **Content preservation**: Capture content before it disappears
- **Metadata enrichment**: Rich context for future reference
- **Relationship mapping**: Connect web content to existing notes
- **AI insights**: Automatic analysis of captured content

### Productivity:
- **Time savings**: No manual copy-paste of web content
- **Better retention**: Structured storage vs bookmarks
- **Enhanced search**: Find content within captured pages
- **Action extraction**: Identify tasks and follow-ups from articles

This architecture provides a solid foundation for implementing comprehensive web link ingestion that integrates seamlessly with Second Brain's existing capture and processing pipeline.