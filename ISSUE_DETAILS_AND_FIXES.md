# ISSUE DETAILS & FIX LOCATIONS

## Issue #1: /api/search Method Mismatch

### Current Problem

**Frontend Code** (dashboard_v3.html, lines 2648-2670):
```javascript
const searchRequest = {
    query: query,
    mode: 'hybrid',
    limit: 20
};

// Call search API using POST with SearchRequest body
const response = await fetch('/api/search', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify(searchRequest)
});
```

**Backend Code** (app.py, lines 4573-4592):
```python
@app.get("/api/search")
async def api_search_notes(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user)
):
    """Search notes using the unified search service"""
    # ... implementation expects q and limit as query parameters
```

### Why This Is a Problem

1. Frontend sends: `POST /api/search` with JSON body containing `query`, `mode`, `limit`
2. Backend expects: `GET /api/search?q=...&limit=...` as query parameters
3. The mismatch can cause:
   - Request body to be ignored
   - 400/405 Method Not Allowed errors
   - Search to fail silently
   - Browser may auto-convert POST to GET (lossy conversion)

### Quick Fix Options

**Option A: Change Backend to POST (Recommended)**

```python
# Replace lines 4573-4592 with:
@app.post("/api/search")
async def api_search_notes(
    request_data: dict = Body(...),
    current_user: User = Depends(get_current_user)
):
    """Search notes using the unified search service"""
    try:
        q = request_data.get('query', '').strip()
        mode = request_data.get('mode', 'hybrid')
        limit = min(request_data.get('limit', 20), 100)
        
        if not q or len(q) < 1:
            raise HTTPException(status_code=400, detail="Query required")
        
        from services.search_adapter import get_search_service
        search_service = get_search_service()
        
        results = search_service.search(
            query=q,
            user_id=current_user.id,
            limit=limit,
            mode=mode
        )
        
        return results.get("results", [])
    except Exception as e:
        # Fallback to basic SQL search if unified search fails
        conn = get_conn()
        c = conn.cursor()
        # ... rest of existing implementation
```

**Option B: Change Frontend to GET (Alternative)**

Replace the search call in dashboard_v3.html (around line 2664):

```javascript
const params = new URLSearchParams({
    q: query,
    limit: 20
});

const response = await fetch(`/api/search?${params}`, {
    method: 'GET',
    headers: {
        'Content-Type': 'application/json',
    },
    credentials: 'include'
});
```

### Testing After Fix

```bash
# Test with curl
curl -X POST http://localhost:8082/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "limit": 20, "mode": "hybrid"}'

# Should return search results, not 405 Method Not Allowed
```

---

## Issue #2: Missing /api/auth/token Endpoint

### Current Problem

**Frontend Code** (dashboard_v3.html, lines 4333-4351):
```javascript
async function getAuthenticatedAudioUrl(filename) {
    try {
        // Try to get a token by making an API call that returns the access token
        const response = await fetch('/api/auth/token', {
            method: 'GET',
            credentials: 'include' // Include cookies
        });
        if (response.ok) {
            const data = await response.json();
            return `/audio/${filename}?token=${data.access_token}`;
        }
    } catch (e) {
        // Fallback to basic URL if token fetch fails
        console.warn('Could not get audio auth token, trying basic auth:', e);
    }
    // Fallback to basic URL without token
    return `/audio/${filename}`;
}
```

**Backend Code** (app.py):
- **NOT FOUND** - Endpoint doesn't exist
- Currently audio is served from `/audio/{filename}` (line 2656) without token validation
- No corresponding endpoint for `/api/auth/token`

### Why This Is a Problem

1. Frontend attempts to get authentication token for audio files
2. Backend endpoint doesn't exist, so request fails
3. Falls back to serving audio without authentication
4. Audio files can be accessed by anyone who knows the filename
5. Security vulnerability for private audio content

### Solution: Implement the Missing Endpoint

Add this to app.py after the import statements (around line 5544):

```python
@app.get("/api/auth/token")
async def get_auth_token(current_user: User = Depends(get_current_user)):
    """Generate access token for audio file authentication"""
    import secrets
    from datetime import datetime, timedelta
    
    try:
        # Generate a secure token (32 bytes of random data, hex encoded)
        token = secrets.token_hex(32)
        
        # Store token in database with expiration (1 hour)
        conn = get_conn()
        c = conn.cursor()
        
        expiration = (datetime.now() + timedelta(hours=1)).isoformat()
        c.execute("""
            INSERT INTO audio_tokens (user_id, token, expires_at, created_at)
            VALUES (?, ?, ?, datetime('now'))
        """, (current_user.id, token, expiration))
        
        conn.commit()
        conn.close()
        
        return {
            "access_token": token,
            "expires_in": 3600,  # 1 hour in seconds
            "token_type": "Bearer"
        }
    except Exception as e:
        logger.error(f"Error generating auth token: {e}")
        raise HTTPException(status_code=500, detail="Could not generate token")
```

### Create Supporting Database Table

Add to db/migrations/003_auth_tokens.sql (create if doesn't exist):

```sql
-- Audio and API authentication tokens
CREATE TABLE IF NOT EXISTS audio_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    used BOOLEAN DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_audio_tokens_user_id ON audio_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_audio_tokens_token ON audio_tokens(token);
CREATE INDEX IF NOT EXISTS idx_audio_tokens_expires_at ON audio_tokens(expires_at);
```

### Update Audio Serving Endpoint

Modify `/audio/{filename}` endpoint (app.py, line 2656) to validate tokens:

```python
@app.get("/audio/{filename}")
async def serve_audio(filename: str, token: str = None, current_user: User = None):
    """Serve audio files with optional token-based authentication"""
    import os
    from pathlib import Path
    
    try:
        # Sanitize filename to prevent path traversal
        filename = Path(filename).name
        audio_path = Path(AUDIO_DIR) / filename
        
        if not audio_path.exists():
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        # Validate token if provided
        if token:
            conn = get_conn()
            c = conn.cursor()
            
            row = c.execute("""
                SELECT user_id, expires_at FROM audio_tokens 
                WHERE token = ? AND used = 0
            """, (token,)).fetchone()
            
            conn.close()
            
            if not row:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            
            user_id, expires_at = row
            if datetime.fromisoformat(expires_at) < datetime.now():
                raise HTTPException(status_code=401, detail="Token expired")
        
        # Serve the file
        return FileResponse(
            audio_path,
            media_type="audio/mpeg",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving audio: {e}")
        raise HTTPException(status_code=500, detail="Error serving audio file")
```

### Testing After Fix

```bash
# 1. Get auth token
TOKEN=$(curl -X GET http://localhost:8082/api/auth/token \
  -H "Cookie: session=YOUR_SESSION_COOKIE" \
  | jq -r '.access_token')

# 2. Use token to access audio
curl -X GET "http://localhost:8082/audio/sample.mp3?token=${TOKEN}"

# Should return 200 with audio data, not 401
```

---

## Files That Need Changes

### File 1: `/Users/dhouchin/mvp-setup/second_brain/app.py`

**Change 1:** Line 4573 (Search endpoint)
- FROM: `@app.get("/api/search")`
- TO: `@app.post("/api/search")`
- Update parameter handling to use request body

**Change 2:** Add after line 5543
- ADD: New `@app.get("/api/auth/token")` endpoint

**Change 3:** Line 2656 (Audio serving)
- UPDATE: Add token validation logic

### File 2: `/Users/dhouchin/mvp-setup/second_brain/db/migrations/003_auth_tokens.sql`

**Add:** New migration file (create if doesn't exist)
- Create `audio_tokens` table
- Add necessary indexes

### File 3: `/Users/dhouchin/mvp-setup/second_brain/templates/dashboard_v3.html` (Optional)

**No changes required** - Frontend code is correct
- Only needs backend endpoints to be fixed

---

## Verification Checklist

After making changes:

- [ ] `/api/search` accepts POST requests with JSON body
- [ ] `/api/search` returns results matching query
- [ ] `/api/auth/token` returns valid token
- [ ] Token has correct expiration time
- [ ] Audio serving validates token if provided
- [ ] Expired tokens are rejected
- [ ] Audio files cannot be accessed without token
- [ ] All existing tests still pass
- [ ] No console errors when using search
- [ ] No console errors when playing audio

---

## Implementation Timeline

**Step 1 (15 minutes):** Fix /api/search method
- Change @app.get to @app.post
- Update parameter parsing
- Test with curl

**Step 2 (30 minutes):** Implement /api/auth/token
- Create new endpoint
- Create database migration
- Test token generation

**Step 3 (30 minutes):** Update audio serving
- Add token validation
- Add expiration checking
- Test with and without token

**Step 4 (15 minutes):** Browser testing
- Test search functionality
- Test audio playback
- Check browser console for errors

**Total Time:** ~90 minutes
