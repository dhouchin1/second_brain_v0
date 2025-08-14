# ──────────────────────────────────────────────────────────────────────────────
# File: README_quickstart.md
# ──────────────────────────────────────────────────────────────────────────────
# Quickstart — FTS5 + sqlite-vec search & embedded jobs

## 0) Prepare env
- Python 3.11+
- Ensure SQLite has FTS5 (most modern builds do). On macOS: the system sqlite includes FTS5.
- (Optional) Build or download **sqlite-vec** and note the `.dylib/.so` path.
- (Optional) Ollama running locally with an embeddings model (e.g., `nomic-embed-text`).

```bash
export SQLITE_DB=notes.db
# If you have sqlite-vec, set the path to the loadable extension file
export SQLITE_VEC_PATH=/absolute/path/to/sqlite-vec0.dylib   # or .so on Linux
export EMBEDDINGS_PROVIDER=ollama
export EMBEDDINGS_MODEL=nomic-embed-text
```

## 1) Run migrations + seed
```bash
python scripts/dev_seed.py
```

If the vec migration prints a warning, you’re in keyword-only mode; hybrid kicks in once sqlite-vec loads successfully.

## 2) Wire routes into FastAPI
In your `app.py` or `app/main.py`:
```python
from fastapi import FastAPI
from api.routes_search import router as search_router
from api.routes_capture import router as capture_router
from services.jobs import JobRunner

app = FastAPI()
app.include_router(search_router)
app.include_router(capture_router)

# start embedded worker
runner = JobRunner(db_path=os.getenv('SQLITE_DB','notes.db'))
@app.on_event('startup')
def _start_worker():
    runner.start(app)
```

## 3) Run the API
```bash
uvicorn app:app --reload --port 8082
```

## 4) Test it quickly
```bash
# Index a note (JSON)
curl -s localhost:8082/search/index -X POST -H 'content-type: application/json' \
  -d '{"title":"Hello World","body":"FTS5 loves SQLite","tags":"#demo"}' | jq

# Search (hybrid)
curl -s localhost:8082/search -X POST -H 'content-type: application/json' \
  -d '{"q":"sqlite","mode":"hybrid","k":10}' | jq

# Capture TEXT (Apple Shortcut compatible)
curl -s localhost:8082/capture -X POST -H 'content-type: application/json' \
  -d '{"type":"text","text":"Captured from iOS Share Sheet","tags":"#ios #capture"}' | jq

# Capture AUDIO (multipart, e.g., an .m4a recording)
curl -s -X POST 'http://localhost:8082/capture/audio' \
  -F 'file=@/path/to/recording.m4a' \
  -F 'title=Voice memo test' \
  -F 'tags=#ios #audio' | jq
```

## 5) Run tests
```bash
pytest -q tests/test_search_smoke.py
```

## 6) Try a digest
```bash
python -c "from services.jobs import JobRunner; r=JobRunner(os.getenv('SQLITE_DB','notes.db')); r.enqueue('digest',{}); print('queued')"
# The background worker will pick it up; check notes list for a new digest stub.
```

## 7) Apple Shortcuts — iOS Setup (Share Sheet)
**Text/Web Capture Shortcut**
1. Create a new Shortcut → **Add to Share Sheet** → accepts **Text**.
2. Actions:
   - **If** input is not text → use **Get Details of Safari Web Page** → **Get Article**/**Get Name** to form text.
   - **Get Contents of URL**
     - URL: `http://YOUR-LAN-IP:8082/capture`
     - Method: **POST**
     - Request Body: **JSON**
       - `type`: `text`
       - `text`: **Provided Input** (Magic Variable)
       - `tags`: e.g. `#ios #share`
     - Headers: `Content-Type: application/json`
3. Optional: Show result.

**Voice Capture Shortcut**
1. Create a new Shortcut → **Record Audio**.
2. **Get Contents of URL**
   - URL: `http://YOUR-LAN-IP:8082/capture/audio`
   - Method: **POST**
   - Request Body: **Form**
     - Add File field **file** → value = recorded audio (Magic Var from *Record Audio*)
     - Text fields: `title` and `tags` as desired
3. Run once to allow local network permissions.

> On macOS/iOS, find your LAN IP in **Settings → Wi‑Fi → (i)**. Replace `YOUR-LAN-IP` above (e.g., `http://10.0.0.87:8084`).

**Troubleshooting**
- If audio upload errors with ffmpeg: ensure `brew install ffmpeg` on the server Mac. We force 16 kHz mono WAV (pcm_s16le) which Whisper likes.
- If transcription is missing, set env vars: `WHISPER_BIN` (path to `whisper-cli`) and `WHISPER_MODEL` (e.g., `ggml-base.en.bin`). If absent, capture still works without transcript.
- If `sqlite-vec` isn’t installed, searches still work via FTS5; set `SQLITE_VEC_PATH` later to enable hybrid.
