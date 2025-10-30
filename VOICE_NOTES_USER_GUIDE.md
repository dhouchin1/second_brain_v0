# Voice Notes - Complete User Guide 🎤

**Last Updated:** 2025-10-30
**Status:** ✅ FIXED - Voice notes now appear immediately in dashboard

---

## Quick Start

### Recording Your First Voice Note

1. **Open Dashboard v3**
   - Navigate to: `http://localhost:8082/dashboard/v3`
   - Or click "Dashboard" in the navigation menu

2. **Click the Microphone Button** 🎤
   - Look for the red microphone icon in the bottom navigation (mobile)
   - Or in the top toolbar (desktop)

3. **Grant Microphone Permission**
   - Browser will ask for permission (first time only)
   - Click "Allow" to enable recording

4. **Start Recording**
   - Click the record button
   - You'll see a timer and recording indicator
   - Speak clearly into your microphone

5. **Stop Recording**
   - Click the stop button when done
   - Wait 2-3 seconds for upload

6. **See Your Note**
   - ✅ **NEW:** Note appears immediately in "My Notes" list
   - You'll see a toast notification: "Voice note saved! Processing transcription..."
   - Recording modal closes automatically after 2 seconds

7. **Wait for Transcription** (~30 seconds)
   - Note status: "transcribing" → "processing" → "complete"
   - Transcript appears when processing completes
   - Audio is playable immediately

---

## What You Should See

### During Recording
```
🎤 Recording...
⏱️ 00:05 (timer counting)
🔴 Red pulsing microphone icon
🌊 Waveform animation
```

### After Upload (Immediate)
```
✅ "Voice note saved! Processing transcription..."
📝 Note appears in "My Notes" list
📊 Status: "transcribing"
```

### After Processing (~30 seconds)
```
✅ Status changes to "complete"
📝 Transcript text appears
🎧 Audio player available
📄 Obsidian markdown file created
```

---

## Step-by-Step with Screenshots (Descriptions)

### Step 1: Access Voice Recording
**Desktop:**
- Click microphone icon in top toolbar
- Or use keyboard shortcut: `Ctrl+M` (if enabled)

**Mobile:**
- Tap microphone icon in bottom navigation bar
- Icon has a gradient red background

### Step 2: Recording Modal Opens
You'll see:
- Large microphone icon in center
- "Ready to record" status text
- Record button (red circle)
- Stop button (disabled, grayed out)
- Close button (X in corner)

### Step 3: Start Recording
After clicking record:
- Timer starts: `00:00` → `00:01` → `00:02`...
- Status changes to: "Recording..."
- Microphone icon pulses with red animation
- Waveform visualization appears (if available)
- Stop button becomes active (red background)

### Step 4: Stop Recording
Click the stop button:
- Timer stops
- Status changes to: "Processing..."
- Upload begins automatically
- Progress indicator may appear

### Step 5: Upload Success
When upload completes:
- ✅ Green checkmark animation
- Status: "Recording saved successfully!"
- Toast notification appears
- Modal stays open for 2 seconds
- **NEW:** Dashboard refreshes automatically

### Step 6: Modal Closes
After 2 seconds:
- Modal fades out and closes
- You're back at the dashboard
- **NEW:** Your voice note is already visible in the list!
- Note shows with title: "Audio Setup Confirmation..." (or similar)

### Step 7: View Your Note
In the notes list, you'll see:
- 🎤 Microphone icon (audio type indicator)
- Auto-generated title
- Timestamp: "Just now" or "2 minutes ago"
- Status badge: "transcribing" (orange) or "complete" (green)

### Step 8: Transcription Completes
Refresh or wait for SSE update:
- Status badge turns green: "complete"
- Click note to view full transcript
- Audio player appears in detail view
- Obsidian file available in vault

---

## Complete Voice Note Flow Timeline

```
00:00 - User clicks microphone button
00:01 - Recording modal opens
00:02 - User clicks "Start Recording"
00:02 - Browser asks for microphone permission (first time)
00:03 - User grants permission
00:03 - Recording starts, timer begins
00:08 - User speaks for 5 seconds
00:08 - User clicks "Stop Recording"
00:09 - Recording stops, processing begins
00:10 - Audio upload starts
00:11 - Upload completes (148KB webm file)
00:11 - Server creates note record immediately
00:11 - Response received: {success: true, note_id: 86}
00:11 - Success toast appears
00:11 - ✅ Dashboard refreshes automatically
00:11 - ✅ Note appears in "My Notes" list
00:13 - Modal closes automatically
00:13 - User sees note in dashboard (status: "transcribing")

--- BACKGROUND PROCESSING BEGINS ---

00:14 - Server converts webm → playback.wav (2-3 sec)
00:17 - Server converts to mono 16kHz wav (1-2 sec)
00:19 - whisper.cpp transcription starts
00:35 - Transcription completes: "That's recording. Yeah, this works."
00:36 - Ollama generates title (5-10 sec)
00:45 - Title generated: "Audio Setup Confirmation..."
00:46 - Obsidian markdown file created
00:47 - Note status updated to "complete"
00:47 - ✅ User can refresh to see transcript

TOTAL TIME: 47 seconds from click to complete
VISIBLE TO USER: Note appears at 00:11 (immediately)
```

---

## What Happens Behind the Scenes

### 1. Browser (Client Side)
```javascript
User clicks record
→ MediaRecorder API captures audio
→ Opus codec in WebM container
→ Audio chunks stored in memory
→ User clicks stop
→ Chunks combined into Blob
→ FormData with file created
→ POST to /webhook/audio
→ Response received
→ ✅ refreshDashboardData() called
→ ✅ loadAllNotes() refreshes list
→ ✅ Note appears immediately
```

### 2. Server (Backend Processing)
```python
POST /webhook/audio received
→ Save webm file to /audio/
→ Create note record in database
→ Return success response immediately
→ Queue background processing
→ --- Background Task ---
→ ffmpeg: webm → playback.wav
→ ffmpeg: wav → mono 16kHz
→ whisper.cpp transcription
→ Save transcript to .txt file
→ Update note content in database
→ Ollama: generate title
→ Update note title
→ Ollama: generate summary (optional)
→ ObsidianSync: create markdown
→ Update note status: "complete"
→ Done! (~30-40 seconds total)
```

### 3. Files Created
```
audio/
├── 2025-10-30-001132-014641-4aa85d2c3782.webm          # Original (148KB)
├── 2025-10-30-001132-014641-4aa85d2c3782.playback.wav  # For browser (1.0MB)
├── 2025-10-30-001132-014641-4aa85d2c3782.converted.wav # For whisper (195KB)
└── 2025-10-30-001132-014641-4aa85d2c3782.converted.wav.txt # Transcript (37B)

vault/
└── 2025-10-30_00-11-32_Audio_Setup_Confirmation_id86.md  # Obsidian (650B)

notes.db
└── notes table: id=86, type=audio, status=complete, audio_filename=...
```

---

## Troubleshooting

### Issue 1: "Note doesn't appear after recording"
**✅ FIXED as of 2025-10-30**

**Previous Behavior:**
- Note uploaded successfully
- But didn't appear in list without page refresh

**Fixed:**
- Now calls `loadAllNotes()` after upload
- Note appears immediately in "My Notes" section
- No manual refresh needed

**If you're still experiencing this:**
1. Hard refresh browser: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows)
2. Clear browser cache
3. Check browser console for JavaScript errors (F12)

---

### Issue 2: "Can't click record button"
**Symptoms:** Button visible but clicking does nothing

**Causes:**
- Microphone permission not granted
- Browser doesn't support MediaRecorder
- JavaScript error blocking execution

**Solution:**
```javascript
// Open browser console (F12) and check for errors
// Should see: "🎤 AudioRecorder: Starting initialization..."
// Should NOT see: "MediaRecorder not supported"

// Check microphone permission
navigator.permissions.query({name: 'microphone'})
  .then(result => console.log('Microphone permission:', result.state));
```

---

### Issue 3: "Recording starts but upload fails"
**Symptoms:** Timer counts, recording completes, but error message appears

**Causes:**
- Server not running on port 8082
- Network connection lost
- Server disk space full

**Solution:**
```bash
# 1. Check server is running
ps aux | grep uvicorn
# Should see: uvicorn app:app --reload --port 8082

# 2. Check server logs for errors
# Look at terminal where uvicorn is running

# 3. Test upload endpoint manually
curl -X POST http://localhost:8082/webhook/audio \
  -F "file=@test.webm" \
  -F "tags=test"
```

---

### Issue 4: "Upload succeeds but no transcript"
**Symptoms:** Note appears, status shows "complete", but transcript is empty

**Causes:**
- whisper.cpp not installed or not found
- Model file missing
- Audio quality too low (silence or noise)
- whisper.cpp crashed during processing

**Solution:**
```bash
# 1. Check whisper.cpp exists
ls -la ./build/bin/whisper-cli
./build/bin/whisper-cli --help

# 2. Check model exists
ls -la ./models/ggml-base.en.bin

# 3. Test transcription manually
./build/bin/whisper-cli \
  -m models/ggml-base.en.bin \
  -f audio/YOUR_FILE.converted.wav

# 4. Check transcript file
cat audio/YOUR_FILE.converted.wav.txt
```

---

### Issue 5: "Can't hear audio playback"
**Symptoms:** Transcript works but audio player doesn't play

**Causes:**
- `.playback.wav` file not created
- Browser can't decode WAV format (rare)
- Audio volume muted
- File permissions issue

**Solution:**
```bash
# 1. Check playback file exists
ls -la audio/*.playback.wav

# 2. Check file is valid WAV
file audio/YOUR_FILE.playback.wav
# Should show: WAVE audio, Microsoft PCM, 16 bit, stereo 44100 Hz

# 3. Try playing file directly
open audio/YOUR_FILE.playback.wav

# 4. Check browser console for media errors
# F12 → Console → Look for "Failed to load audio"
```

---

## Advanced Tips

### Tip 1: Recording Longer Notes
- **Recommended:** 30 seconds to 2 minutes per note
- **Maximum:** No hard limit, but longer = slower processing
- **Best Practice:** Break long recordings into 2-3 minute chunks

### Tip 2: Better Transcription Quality
- Speak clearly and at normal pace
- Reduce background noise
- Use a decent microphone (laptop mic is usually fine)
- Speak closer to mic for quieter environments
- Avoid recording in noisy locations

### Tip 3: Keyboard Shortcuts (Future)
```
Ctrl+M     - Open voice recording modal
Ctrl+R     - Start/stop recording
Esc        - Close modal without recording
Space      - Start/stop recording (when modal open)
```

### Tip 4: Mobile Best Practices
- Hold phone close but not touching mouth
- Record in portrait mode for better UI
- Use wired headphones with mic for better quality
- Airplane mode (turn off later) for less background interference

### Tip 5: Check Processing Status
```javascript
// In browser console, check note status
fetch('/api/notes/86')
  .then(r => r.json())
  .then(note => console.log('Status:', note.status));
```

---

## Technical Details

### Audio Format
- **Recording Format:** WebM with Opus codec
- **Playback Format:** WAV PCM, 16-bit stereo, 44.1kHz
- **Transcription Format:** WAV PCM, 16-bit mono, 16kHz
- **File Size:** ~150KB per minute of audio (webm)

### Transcription Engine
- **Primary:** whisper.cpp (ggml-base.en.bin model)
- **Fallback:** Vosk (if configured)
- **Language:** English (default model)
- **Accuracy:** ~90-95% for clear speech

### AI Title Generation
- **Model:** Ollama llama3.2
- **Input:** First 500 characters of transcript
- **Output:** 5-15 word descriptive title
- **Fallback:** "[No Title]" if generation fails

### Processing Time
- **Upload:** 1-2 seconds (depends on file size)
- **Conversion:** 3-5 seconds (ffmpeg)
- **Transcription:** 10-30 seconds (depends on length)
- **AI Processing:** 5-15 seconds (Ollama)
- **Total:** 20-50 seconds average

---

## Obsidian Integration

### Markdown File Structure
```markdown
---
id: 86
title: Audio Setup Confirmation for Upcoming Project Discussion
type: audio
status: complete
tags: [voice-note audio]
created: '2025-10-30 00:11:45'
file_filename: 2025-10-30-001132-014641-4aa85d2c3782.webm
file_size: 148217
---

## Summary
Conversation summary not provided

## Full Content
That's recording. Yeah, this works.

![[audio/2025-10-30-001132-014641-4aa85d2c3782.converted.wav]]
```

### Opening in Obsidian
1. **Location:** `vault/2025-10-30_00-11-32_Audio_Setup_Confirmation_id86.md`
2. **Audio Playback:** Click the embedded `![[audio/...]]` link
3. **Transcription:** Visible in "Full Content" section
4. **Metadata:** Available in YAML frontmatter

### Syncing with Obsidian
- Files created automatically after transcription
- Audio files copied to `vault/audio/` directory
- Markdown follows Obsidian best practices
- YAML frontmatter for metadata
- Embedded audio for in-app playback

---

## API Reference (For Developers)

### Upload Endpoint
```bash
POST /webhook/audio
Content-Type: multipart/form-data

Parameters:
  file: File (required) - WebM audio file
  tags: string (optional) - Comma-separated tags
  user_id: int (optional) - User ID (default: 1)

Response:
{
  "success": true,
  "note_id": 86,
  "filename": "2025-10-30-001132-014641-4aa85d2c3782.webm",
  "message": "Audio uploaded successfully"
}

Error Response:
{
  "success": false,
  "error": "File upload failed"
}
```

### Get Note Status
```bash
GET /api/notes/{note_id}

Response:
{
  "id": 86,
  "title": "Audio Setup Confirmation...",
  "type": "audio",
  "status": "complete",
  "content": "That's recording. Yeah, this works.",
  "audio_filename": "2025-10-30-001132-014641-4aa85d2c3782.converted.wav",
  "created_at": "2025-10-30 00:11:32",
  "tags": "voice-note audio"
}
```

---

## Changelog

### 2025-10-30 - Voice Note Visibility Fix ✅
**Problem:** Voice notes uploaded but didn't appear in dashboard
**Solution:** Added `loadAllNotes()` to dashboard refresh
**Impact:** Notes now appear immediately after recording
**Commit:** `92f27c1` on `feature/frontend-ux-improvements`

### Previous Versions
- Initial voice recording implementation
- WebM → WAV conversion
- whisper.cpp integration
- Obsidian markdown generation
- Real-time status updates (SSE)

---

## FAQ

**Q: How long can my recording be?**
A: Technically unlimited, but recommended 30 seconds to 2 minutes for best experience.

**Q: Can I delete a voice note?**
A: Yes, click the note and use the delete button (or implement bulk delete).

**Q: Can I edit the transcript?**
A: Yes, click the note to view details and edit the transcript manually.

**Q: Does it work offline?**
A: Recording and upload require internet. Transcription happens server-side.

**Q: Can I use it on mobile?**
A: Yes! Works great on iOS Safari and Android Chrome.

**Q: What languages are supported?**
A: Currently English only (ggml-base.en.bin model). More languages coming soon.

**Q: Can I use external microphone?**
A: Yes, browser will use your system's default audio input device.

**Q: Is audio stored permanently?**
A: Yes, audio files are kept in `/audio/` directory indefinitely.

---

## Support

**Need Help?**
1. Check this guide first
2. Review VOICE_NOTES_STATUS.md for technical details
3. Check browser console for errors (F12)
4. Review server logs where uvicorn is running
5. Create GitHub issue with details

**Working Perfectly?** 🎉
- Start recording your thoughts!
- Try different note lengths
- Experiment with different topics
- Share feedback for improvements

---

**Happy Recording! 🎤✨**
