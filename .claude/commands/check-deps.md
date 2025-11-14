# Check Dependencies

Verify all required dependencies and external services are properly configured.

## Instructions

Run a comprehensive health check of all Second Brain dependencies:

1. **Python packages** - Verify all required packages are installed
2. **External services** - Check Ollama and Whisper are available
3. **Database** - Verify SQLite and extensions
4. **Configuration** - Check .env variables
5. **File system** - Verify directories exist with proper permissions
6. **Network services** - Test API endpoints if configured

## Dependency Checklist

### Core Dependencies

```bash
# Check Python version
python --version  # Should be 3.9+

# Check key packages
python -c "import fastapi; print(f'FastAPI: {fastapi.__version__}')"
python -c "import sqlite3; print(f'SQLite: {sqlite3.sqlite_version}')"
python -c "import whisper; print('Whisper: OK')" 2>/dev/null || echo "Whisper: Not installed"
```

### Ollama Service

```bash
# Check if Ollama is running
curl -s http://localhost:11434/api/tags | python -c "import sys,json; data=json.load(sys.stdin); print(f\"Ollama models: {[m['name'] for m in data['models']]}\")" 2>/dev/null || echo "❌ Ollama not running"

# Test model inference
curl -s http://localhost:11434/api/generate -d '{
  "model": "llama3.2",
  "prompt": "Hello",
  "stream": false
}' | python -c "import sys,json; print('✅ Ollama responding')" 2>/dev/null || echo "❌ Ollama not responding"
```

### Whisper.cpp

```bash
# Check whisper binary
ls -lh build/bin/whisper-cli 2>/dev/null && echo "✅ Whisper binary found" || echo "❌ Whisper binary not found"

# Check whisper model
ls -lh models/ggml-*.bin 2>/dev/null && echo "✅ Whisper model found" || echo "❌ Whisper model not found"
```

### Database

```bash
# Check database file
ls -lh notes.db 2>/dev/null && echo "✅ Database file exists" || echo "❌ Database not initialized"

# Check FTS5 extension
sqlite3 notes.db "SELECT * FROM pragma_compile_options WHERE compile_options LIKE '%FTS5%';" 2>/dev/null && echo "✅ FTS5 available" || echo "❌ FTS5 not available"

# Check migrations
sqlite3 notes.db "SELECT name FROM sqlite_master WHERE type='table' AND name='migrations';" 2>/dev/null && echo "✅ Migrations table exists" || echo "⚠️  Migrations table missing"

# Check sqlite-vec (optional)
python -c "from config import SQLITE_VEC_PATH; import os; print('✅ sqlite-vec configured' if os.path.exists(SQLITE_VEC_PATH) else '⚠️  sqlite-vec not found (optional)')" 2>/dev/null
```

### Configuration

```bash
# Check .env file
test -f .env && echo "✅ .env file exists" || echo "❌ .env file missing"

# Check critical env vars
python -c "
from config import VAULT_PATH, AUDIO_DIR, OLLAMA_API_URL, WHISPER_CPP_PATH
import os
print('✅ VAULT_PATH:', VAULT_PATH if os.path.exists(VAULT_PATH) else '❌ Not found')
print('✅ AUDIO_DIR:', AUDIO_DIR if os.path.exists(AUDIO_DIR) else '❌ Not found')
print('✅ OLLAMA_API_URL:', OLLAMA_API_URL)
print('✅ WHISPER_CPP_PATH:', WHISPER_CPP_PATH if os.path.exists(WHISPER_CPP_PATH) else '⚠️  Not found')
"
```

### File System Permissions

```bash
# Check directories exist and are writable
test -w vault && echo "✅ Vault writable" || echo "❌ Vault not writable"
test -w audio && echo "✅ Audio directory writable" || echo "❌ Audio directory not writable"
test -w uploads && echo "✅ Uploads directory writable" || echo "❌ Uploads directory not writable"
test -w static && echo "✅ Static directory writable" || echo "❌ Static directory not writable"
```

### Optional Services

```bash
# Discord bot (optional)
python -c "from config import DISCORD_BOT_TOKEN; print('✅ Discord token configured' if DISCORD_BOT_TOKEN else '⚠️  Discord not configured')" 2>/dev/null

# Email service (optional)
python -c "from config import EMAIL_HOST; print('✅ Email configured' if EMAIL_HOST else '⚠️  Email not configured')" 2>/dev/null
```

## Expected Output Format

```
Second Brain Dependency Check
=============================

Core System:
  ✅ Python 3.11.5
  ✅ FastAPI 0.104.1
  ✅ SQLite 3.43.2

AI Services:
  ✅ Ollama running (models: llama3.2, llama3.2:1b)
  ✅ Whisper.cpp binary found
  ✅ Whisper model: ggml-base.en.bin (148MB)

Database:
  ✅ Database initialized (125MB)
  ✅ FTS5 extension available
  ✅ Migrations applied (15 total)
  ⚠️  sqlite-vec not configured (optional)

Configuration:
  ✅ .env file configured
  ✅ Vault path: ./vault (1,234 files)
  ✅ Audio directory: ./audio (45 files)

File Permissions:
  ✅ All directories writable

Optional Services:
  ⚠️  Discord bot not configured
  ⚠️  Email service not configured

Overall Status: ✅ Ready for development
```

## Common Issues & Solutions

### Ollama Not Running
```bash
# Start Ollama service
ollama serve

# In another terminal, pull model
ollama pull llama3.2
```

### Whisper Not Found
```bash
# Build whisper.cpp
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp
make

# Download model
bash ./models/download-ggml-model.sh base.en
```

### Database Not Initialized
```bash
# Run migrations
python migrate_db.py
```

### Missing Directories
```bash
# Create required directories
mkdir -p vault audio uploads static/assets
chmod 755 vault audio uploads
```

## Automated Check Script

You can create a simple script:

```python
#!/usr/bin/env python3
"""Dependency checker for Second Brain"""

import os
import sys
from pathlib import Path

def check_deps():
    issues = []

    # Check Ollama
    import requests
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            print("✅ Ollama running")
        else:
            issues.append("Ollama not responding correctly")
    except:
        issues.append("❌ Ollama not running")

    # Check database
    if Path("notes.db").exists():
        print("✅ Database exists")
    else:
        issues.append("❌ Database not initialized")

    # Check directories
    for dir_name in ["vault", "audio", "uploads"]:
        if Path(dir_name).is_dir():
            print(f"✅ {dir_name} directory exists")
        else:
            issues.append(f"❌ {dir_name} directory missing")

    return len(issues) == 0, issues

if __name__ == "__main__":
    success, issues = check_deps()
    if not success:
        print("\n⚠️  Issues found:")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print("\n✅ All dependencies OK")
        sys.exit(0)
```
