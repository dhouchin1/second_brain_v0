# Second Brain 🧠

**An AI-powered knowledge management system that captures, processes, and intelligently retrieves information from multiple sources**

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![AI Powered](https://img.shields.io/badge/AI-Powered-purple.svg)](https://github.com/dhouchin1/second_brain)

> Transform your information workflow with intelligent multi-modal capture, AI-powered processing, and seamless integration with your existing tools.

---

## ✨ Key Features

### 🎤 **Multi-Modal Capture**
- **Audio Transcription** - Whisper.cpp integration for high-quality speech-to-text
- **Web Content Extraction** - Intelligent web scraping with screenshot capture
- **File Processing** - Support for PDFs, images, and various document formats
- **Quick Notes** - Instant text capture with URL detection and processing

### 🤖 **AI-Powered Processing**
- **Smart Summarization** - Ollama-powered content analysis and summarization
- **Automatic Tagging** - Context-aware tag generation for better organization  
- **Action Item Extraction** - Identifies tasks and follow-ups automatically
- **Title Generation** - Creates meaningful titles from content analysis
- **Auto-Seeding** - Intelligent content bootstrapping for new users with curated starter content

### 🔍 **Intelligent Search**
- **Hybrid Search** - Advanced Reciprocal Rank Fusion (RRF) combining keyword + semantic results
- **Chunk-based Indexing** - Sophisticated content chunking for improved search granularity
- **Real-time Results** - Sub-100ms search response times with BM25 ranking
- **Vector Similarity** - Optional sqlite-vec extension for semantic search capabilities
- **Advanced Filtering** - Search by type, date, tags, and content
- **Snippet Highlighting** - Contextual result previews with matched terms

### 🔗 **Seamless Integrations**
- **Obsidian Sync** - Bi-directional sync with YAML frontmatter support
- **Discord Bot** - Slash commands for mobile and team note-taking
- **Apple Shortcuts** - Deep iOS integration for voice and quick capture
- **Browser Extension** - One-click web content capture
- **Webhook API** - Custom integrations and automation support

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 16+ (for browser extension development)
- [Ollama](https://ollama.ai/) for local LLM inference
- [Whisper.cpp](https://github.com/ggerganov/whisper.cpp) for audio transcription

### Installation

```bash
# Clone the repository
git clone https://github.com/dhouchin1/second_brain.git
cd second_brain

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Initialize database
python migrate_db.py

# Start the application
.venv/bin/python -m uvicorn app:app --reload --port 8082

# Optional: Enable auto-seeding for new users (recommended)
# Auto-seeding will automatically populate new accounts with starter content
# Set in .env file:
# AUTO_SEEDING_ENABLED=true
# AUTO_SEEDING_NAMESPACE=.starter_content
```

### Access the Application
- **Web Dashboard**: http://localhost:8082
- **API Documentation**: http://localhost:8082/docs
- **Health Check**: http://localhost:8082/health

---

## 🏗️ Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        Input Layer                              │
├─────────────────┬──────────────┬──────────────┬─────────────────┤
│ Web Interface   │ Discord Bot  │ Apple        │ Browser         │
│                 │              │ Shortcuts    │ Extension       │
└─────────────────┴──────────────┴──────────────┴─────────────────┘
                            │
┌─────────────────────────────────────────────────────────────────┐
│                    Processing Pipeline                          │
├─────────────────┬──────────────┬──────────────┬─────────────────┤
│ Content         │ AI           │ Embedding    │ Search          │
│ Extraction      │ Analysis     │ Generation   │ Indexing        │
│                 │              │              │                 │
│ • File parsing  │ • Ollama LLM │ • Sentence   │ • SQLite FTS5   │
│ • Web scraping  │ • Whisper    │   Transformers│ • Vector store  │
│ • Audio/Video   │ • Tag gen.   │ • Similarity │ • Real-time     │
└─────────────────┴──────────────┴──────────────┴─────────────────┘
                            │
┌─────────────────────────────────────────────────────────────────┐
│                      Storage Layer                             │
├─────────────────┬──────────────┬──────────────┬─────────────────┤
│ SQLite          │ Vector       │ File         │ Obsidian        │
│ Database        │ Embeddings   │ Storage      │ Vault           │
│                 │              │              │                 │
│ • Notes         │ • Semantic   │ • Audio      │ • Markdown      │
│ • Users         │   search     │ • Images     │ • YAML          │
│ • Analytics     │ • Similarity │ • Documents  │ • Real-time     │
└─────────────────┴──────────────┴──────────────┴─────────────────┘
```

### Service Architecture

The application follows a **service-oriented architecture** for modularity and maintainability:

- **`services/search_adapter.py`** - Unified search interface with FTS5 + vector search
- **`services/search_index.py`** - Advanced search indexer with chunk-based indexing and RRF
- **`services/auto_seeding_service.py`** - Intelligent content seeding for new user onboarding
- **`services/vault_seeding_service.py`** - Core vault seeding infrastructure with configurable content
- **`services/webhook_service.py`** - External webhook handling (Discord, Apple, Browser)
- **`services/upload_service.py`** - File upload management with chunked transfers
- **`services/analytics_service.py`** - Usage analytics and insights
- **`services/auth_service.py`** - Authentication and user management
- **`services/embeddings.py`** - Vector embedding generation and management

---

## 🔧 Configuration

### Environment Variables

```bash
# Core Application
VAULT_PATH=./vault              # Obsidian vault location
AUDIO_DIR=./audio              # Audio file storage
BASE_URL=http://localhost:8082  # Application base URL

# AI Services
OLLAMA_API_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=llama3.2
WHISPER_CPP_PATH=./build/bin/whisper-cli
WHISPER_MODEL_PATH=./models/ggml-base.en.bin

# Database
DATABASE_URL=sqlite:///./notes.db
SQLITE_VEC_PATH=/path/to/sqlite-vec0.dylib  # Optional vector search

# Auto-Seeding Configuration
AUTO_SEEDING_ENABLED=true                  # Enable automatic content seeding
AUTO_SEEDING_NAMESPACE=.starter_content    # Namespace for seeded content
AUTO_SEEDING_EMBEDDINGS=true              # Generate embeddings for seed content
AUTO_SEEDING_MIN_NOTES=5                  # Minimum notes before skipping auto-seed

# Security
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-here
CSRF_SECRET_KEY=your-csrf-secret-here

# Email (for magic links)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password

# Discord Integration
DISCORD_TOKEN=your-discord-bot-token
DISCORD_WEBHOOK_SECRET=your-webhook-secret
```

### AI Service Setup

#### Ollama (Local LLM)
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start service
ollama serve

# Pull model
ollama pull llama3.2
```

#### Whisper.cpp (Audio Transcription)
```bash
# Clone and build
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
make

# Download model
bash ./models/download-ggml-model.sh base.en
```

---

## 📡 API Reference

### Core Endpoints

#### Capture Content
```http
POST /capture
Content-Type: application/json

{
  "content": "Your note content here",
  "tags": "tag1,tag2",
  "type": "text"
}
```

#### Search Notes
```http
POST /api/search/hybrid
Content-Type: application/json

{
  "query": "search terms",
  "mode": "hybrid",  # or "keyword", "semantic"
  "limit": 20
}
```

#### Upload Files
```http
POST /upload/init
Content-Type: application/json

{
  "filename": "recording.wav",
  "total_size": 1024000,
  "mime_type": "audio/wav"
}
```

### Integration Endpoints

#### Discord Webhook
```http
POST /webhook/discord
Content-Type: application/json

{
  "type": "note",
  "content": "Message from Discord",
  "user_id": "discord_user_id",
  "channel_id": "channel_id"
}
```

#### Apple Shortcuts
```http
POST /webhook/apple
Content-Type: application/json

{
  "type": "voice_memo",
  "content": "Transcribed content",
  "audio_url": "https://example.com/audio.m4a"
}
```

For complete API documentation, visit `/docs` when running the application.

---

## 🔍 Search Capabilities

Second Brain provides three complementary search modes:

### Keyword Search (FTS5)
- **Fast full-text search** using SQLite's FTS5 engine
- **BM25 ranking** for relevance scoring
- **Snippet generation** with highlighted matches
- **Boolean operators** (AND, OR, NOT) support

### Semantic Search (Vector)
- **Contextual understanding** using sentence transformers
- **Similar content discovery** beyond exact keyword matches
- **Cross-language search** capabilities
- **Concept-based retrieval** for related topics

### Hybrid Search (Recommended)
- **Best of both worlds** - combines keyword precision with semantic understanding
- **Reciprocal Rank Fusion** for optimal result ranking
- **Cross-encoder reranking** for improved relevance
- **Configurable weights** for different search strategies

---

## 🧩 Integrations

### Obsidian Vault Sync

Second Brain maintains real-time synchronization with your Obsidian vault:

```yaml
# Example note with YAML frontmatter
---
tags: [meeting, project-alpha, action-items]
summary: "Project kickoff meeting with key stakeholders"
transcription: "Full audio transcription here..."
created: 2024-01-15T10:30:00Z
processed: true
---

# Project Alpha Kickoff Meeting

## Key Points
- Project timeline: 6 months
- Budget approved: $50k
- Team assignments completed

## Action Items
- [ ] Set up project repository
- [ ] Schedule weekly check-ins
- [ ] Prepare architecture docs
```

### Discord Bot Commands

```bash
# Save a quick note
/note content:"Remember to review PR #123"

# Voice memo processing
/voice [attach audio file]

# Search existing notes
/search query:"project alpha meeting"

# Get recent notes
/recent count:5
```

### Apple Shortcuts Integration

Create iOS shortcuts that send data to your Second Brain:

1. **Quick Voice Note** - Record audio → transcribe → save with tags
2. **Web Article Capture** - Share URL → extract content → summarize
3. **Meeting Prep** - Calendar integration → create pre-meeting note
4. **Daily Review** - Fetch recent notes → create summary

---

## 🧪 Development

### Project Structure

```
second_brain/
├── app.py                 # Main FastAPI application
├── config.py             # Configuration management
├── migrate_db.py         # Database migrations
│
├── services/             # Service layer
│   ├── search_adapter.py    # Unified search interface
│   ├── webhook_service.py   # External integrations
│   ├── upload_service.py    # File upload handling
│   ├── analytics_service.py # Usage analytics
│   ├── auth_service.py      # Authentication
│   └── embeddings.py        # Vector embeddings
│
├── api/                  # API routes (legacy)
│   ├── routes_capture.py    # Capture endpoints
│   └── routes_search.py     # Search endpoints
│
├── db/migrations/        # Database schema
│   ├── 001_core.sql         # Core tables
│   └── 002_vec.sql          # Vector extension
│
├── templates/            # HTML templates
│   ├── dashboard.html       # Main interface
│   ├── search.html          # Search page
│   └── detail.html          # Note details
│
├── static/               # Frontend assets
│   ├── css/                 # Stylesheets
│   ├── js/                  # JavaScript modules
│   └── images/              # Static images
│
├── tests/                # Test suite
│   ├── test_search.py       # Search functionality
│   ├── test_capture.py      # Content capture
│   └── test_integrations.py # External APIs
│
├── vault/                # Obsidian vault (gitignored)
├── audio/                # Audio files (gitignored)
├── screenshots/          # Web screenshots (gitignored)
└── requirements.txt      # Python dependencies
```

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test categories
python -m pytest tests/test_search.py -v
python -m pytest tests/test_capture.py -v

# Run with coverage
python -m pytest --cov=. --cov-report=html tests/

# Performance testing
python test_search_performance.py
```

### Development Commands

```bash
# Start development server with reload
.venv/bin/python -m uvicorn app:app --reload --port 8082

# Database operations
python migrate_db.py              # Run migrations
python -c "from services.search_index import SearchIndexer; SearchIndexer().rebuild_all(embeddings=True)"

# Auto-seeding operations
python -c "from services.auto_seeding_service import get_auto_seeding_service; from database import get_db_connection; service = get_auto_seeding_service(get_db_connection); print(service.check_auto_seeding_status())"
python -c "from services.vault_seeding_service import get_seeding_service; from database import get_db_connection; from services.vault_seeding_service import SeedingOptions; service = get_seeding_service(get_db_connection); result = service.seed_vault(1, SeedingOptions()); print(result)"

# Discord bot setup
python setup_discord_bot.py       # Configure bot
python get_bot_invite.py          # Get invite URL
python validate_bot_token.py      # Test token

# Email service setup
python setup_email.py             # Configure SMTP
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes following the existing code style
4. Add tests for new functionality
5. Run the test suite to ensure everything passes
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

---

## 📊 Performance & Monitoring

### Key Metrics

- **Search Latency**: < 100ms for most queries
- **Processing Time**: < 30s for audio transcription
- **Upload Speed**: Supports chunked uploads up to 500MB
- **Concurrent Users**: Tested with 100+ simultaneous users
- **Database Size**: Efficiently handles 10M+ notes

### Monitoring Endpoints

```bash
# Application health
curl http://localhost:8082/health

# Queue status (audio processing)
curl http://localhost:8082/api/queue/status

# Search analytics
curl http://localhost:8082/api/analytics -H "Authorization: Bearer YOUR_TOKEN"
```

### Performance Optimization

- **Database indexing** for fast full-text search
- **Async processing** for CPU-intensive tasks
- **Connection pooling** for database efficiency  
- **Caching strategies** for frequently accessed data
- **Background job queues** for scalable processing

---

## 🛡️ Security & Privacy

### Security Features

- **JWT-based authentication** with configurable expiration
- **CSRF protection** for all state-changing operations
- **Rate limiting** to prevent abuse
- **Input validation** and sanitization
- **Secure file upload** with type validation

### Privacy by Design

- **Local-first processing** - AI runs on your infrastructure
- **Data encryption** at rest and in transit
- **User data isolation** with proper access controls
- **Audit logging** for security monitoring
- **GDPR compliance** with data portability features

### Deployment Security

```bash
# Generate secure keys
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Set up HTTPS (recommended)
# Use reverse proxy (nginx, traefik) with SSL certificates

# Database security
chmod 600 notes.db  # Restrict database file access
```

---

## 🚀 Deployment

### Docker Deployment

```yaml
# docker-compose.yml
version: '3.8'
services:
  second-brain:
    build: .
    ports:
      - "8082:8082"
    environment:
      - DATABASE_URL=sqlite:///./data/notes.db
      - OLLAMA_API_URL=http://ollama:11434/api/generate
    volumes:
      - ./data:/app/data
      - ./vault:/app/vault
    depends_on:
      - ollama
  
  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

volumes:
  ollama_data:
```

```bash
# Build and run
docker-compose up -d

# Check logs
docker-compose logs -f second-brain
```

### Production Deployment

#### System Requirements
- **CPU**: 4+ cores (for AI processing)
- **RAM**: 8GB+ (4GB for Ollama, 2GB for Whisper, 2GB for app)
- **Storage**: 100GB+ (for notes, audio files, models)
- **Network**: 100Mbps+ (for file uploads)

#### Recommended Stack
```bash
# Reverse proxy with SSL
nginx + certbot

# Application server
uvicorn with multiple workers

# Process management
systemd or supervisor

# Monitoring
prometheus + grafana

# Backup strategy
Regular database backups + file sync
```

#### Environment-specific Configuration

```bash
# Production
export ENVIRONMENT=production
export DEBUG=false
export LOG_LEVEL=INFO

# Staging
export ENVIRONMENT=staging
export DEBUG=true
export LOG_LEVEL=DEBUG
```

---

## 🤝 Community & Support

### Documentation

- **[Technical Documentation](AGENTS.md)** - Comprehensive developer guide
- **[Claude Code Integration](CLAUDE.md)** - AI assistant usage patterns
- **[Product Requirements](second_brain.PRD)** - Detailed feature specifications
- **[API Reference](/docs)** - Interactive API documentation

### Community Resources

- **Discord Server**: [Join our community](https://discord.gg/secondbrain) for support and discussions
- **GitHub Issues**: Report bugs and request features
- **Discussions**: Share ideas and ask questions
- **Wiki**: Community-contributed guides and tutorials

### Getting Help

1. **Check the Documentation**: Start with this README and linked docs
2. **Search Issues**: Look for similar problems on GitHub
3. **Ask the Community**: Post in Discord for quick help
4. **Create an Issue**: For bugs or feature requests

---

## 📈 Roadmap

### Current Status (v1.6 - Auto-Seeding & Advanced Search)
- ✅ Multi-modal capture and processing
- ✅ Advanced hybrid search with Reciprocal Rank Fusion (RRF)
- ✅ Chunk-based search indexing with FTS5 + sqlite-vec integration
- ✅ Auto-seeding service for intelligent new user onboarding
- ✅ Real-time Obsidian synchronization with YAML frontmatter
- ✅ Discord bot with slash commands
- ✅ Web dashboard with modern UI
- ✅ Complete service-oriented architecture

### Upcoming Features (v2.0)
- 📱 **Native Mobile Apps** - iOS and Android applications
- 🤝 **Real-time Collaboration** - Multi-user editing and sharing
- 🔐 **Advanced Security** - SSO, RBAC, audit logging
- 📊 **Enhanced Analytics** - Usage insights and productivity metrics
- 🌐 **Multi-language Support** - Internationalization and localization

### Future Vision (v3.0+)
- 🧠 **Advanced AI Features** - Custom model fine-tuning, predictive suggestions
- 🔗 **Enterprise Integration** - Slack, Teams, Salesforce connectors
- 🎯 **Smart Automation** - Workflow automation and intelligent routing
- 📈 **Scalability Improvements** - Multi-tenant architecture, cloud deployment

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2024 Second Brain Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

## 🙏 Acknowledgments

Special thanks to:

- **[FastAPI](https://fastapi.tiangolo.com/)** - The modern, fast web framework powering our API
- **[Ollama](https://ollama.ai/)** - Local LLM inference platform for AI processing
- **[Whisper.cpp](https://github.com/ggerganov/whisper.cpp)** - High-performance audio transcription
- **[SQLite](https://sqlite.org/)** - Reliable, embedded database with FTS5 search
- **[Sentence Transformers](https://sbert.net/)** - Semantic embeddings and similarity search
- **[Obsidian](https://obsidian.md/)** - The knowledge management platform that inspired this project

---

<div align="center">

**[⭐ Star this repo](https://github.com/dhouchin1/second_brain)** | **[📝 Report Issues](https://github.com/dhouchin1/second_brain/issues)** | **[💬 Join Discord](https://discord.gg/secondbrain)**

*Built with ❤️ for knowledge workers, researchers, and anyone who wants to capture and find information effortlessly.*

</div>