# Apple Shortcuts for Second Brain - Complete Setup Guide

## 📋 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Detailed Setup Instructions](#detailed-setup-instructions)
5. [Testing Your Shortcuts](#testing-your-shortcuts)
6. [Troubleshooting](#troubleshooting)
7. [Advanced Usage](#advanced-usage)

---

## 🎯 Overview

This bundle contains 10 powerful Apple Shortcuts that transform your iPhone or Mac into a seamless Second Brain capture device. Each shortcut is pre-configured to work with your Second Brain server and includes:

- ✅ Sample data for testing
- ✅ Detailed API documentation
- ✅ Siri phrase suggestions
- ✅ Automatic tagging and AI processing

### Available Shortcuts

| # | Shortcut | Purpose | Key Features |
|---|----------|---------|--------------|
| 1 | **Voice Memo** | Record & transcribe voice notes | Location tracking, AI summarization, action item extraction |
| 2 | **Photo OCR** | Extract text from images | Business cards, whiteboards, documents, receipts |
| 3 | **Quick Thought** | Capture ideas instantly | Smart auto-tagging, multiple note types |
| 4 | **Web Clip** | Save web content | Safari share sheet integration, text selection |
| 5 | **Recipe Saver** | Store recipes | Structured ingredients & instructions |
| 6 | **Dream Journal** | Log dreams | Emotion tracking, AI analysis, lucid dream support |
| 7 | **Contact Note** | Save people notes | Meeting context, location data |
| 8 | **Book Logger** | Track media consumption | Books, movies, podcasts with ratings |
| 9 | **Habit Tracker** | Log daily habits | Completion status, mood tracking |
| 10 | **Quote Saver** | Collect quotes | Attribution, personal reflections |

---

## ⚙️ Prerequisites

### Required

- ✅ Second Brain server running (localhost:8082 or remote URL)
- ✅ macOS 12+ or iOS 15+ with Shortcuts app installed
- ✅ Python 3.7+ (for conversion script)

### Optional (for enhanced features)

- Ollama running for AI-powered summarization
- Whisper.cpp for audio transcription
- SQLite with FTS5 for search

---

## 🚀 Quick Start

### For Mac Users

```bash
# 1. Navigate to shortcuts directory
cd apple_shortcuts/

# 2. Run the conversion script
python3 import_shortcuts.py --server-url http://your-server:8082

# 3. Import all shortcuts
cd shortcuts_bundle/
./import_all.sh

# 4. Update server URLs in Shortcuts app
# Open each shortcut and replace localhost:8082 with your server URL
```

### For iPhone/iPad Users

```bash
# 1. Generate shortcuts bundle on your computer
python3 import_shortcuts.py --server-url http://your-server:8082

# 2. AirDrop the .shortcut files to your iPhone

# 3. Tap each file and select "Add Shortcut"

# 4. Configure permissions when prompted
```

---

## 📖 Detailed Setup Instructions

### Step 1: Prepare Your Server

Ensure your Second Brain server is running and accessible:

```bash
# Start the server (from Second Brain root directory)
.venv/bin/python -m uvicorn app:app --reload --port 8082

# Verify it's running
curl http://localhost:8082/health
```

**For remote access:**
- Make sure your server is accessible from your phone (same network or public URL)
- Use ngrok for temporary public URL: `ngrok http 8082`
- Or configure your router for port forwarding

### Step 2: Convert Shortcuts to Importable Format

The JSON files in this directory are human-readable definitions. Convert them to Apple's format:

```bash
# Default (localhost:8082)
python3 import_shortcuts.py

# Custom server URL
python3 import_shortcuts.py --server-url https://my-brain.example.com

# Custom input directory
python3 import_shortcuts.py --input-dir ./my_shortcuts/ --server-url http://192.168.1.100:8082
```

This creates a `shortcuts_bundle/` directory with:
- `.shortcut` files (importable)
- `_metadata.json` files (documentation)
- `README.md` (quick reference)
- `import_all.sh` (batch import script)

### Step 3: Import Shortcuts

#### macOS

**Option A: Batch Import (Recommended)**

```bash
cd shortcuts_bundle/
chmod +x import_all.sh
./import_all.sh
```

The Shortcuts app will open for each shortcut. Click "Add Shortcut" for each one.

**Option B: Manual Import**

1. Double-click any `.shortcut` file
2. Shortcuts app opens automatically
3. Click "Add Shortcut"
4. Repeat for each shortcut

#### iOS/iPadOS

**Option A: AirDrop (Easiest)**

1. AirDrop the `shortcuts_bundle/` folder from your Mac to iPhone
2. Tap each `.shortcut` file
3. Shortcuts app opens
4. Tap "Add Shortcut"
5. Allow permissions when prompted

**Option B: iCloud Drive**

1. Copy `shortcuts_bundle/` to iCloud Drive
2. Open Files app on iPhone
3. Navigate to the folder
4. Tap each `.shortcut` file to import

**Option C: Direct Download (if server is public)**

1. Host the `.shortcut` files on your server
2. Visit the URLs on your iPhone
3. Safari will prompt to open in Shortcuts

### Step 4: Configure Permissions

Each shortcut may request permissions on first run:

| Shortcut | Permissions Required |
|----------|---------------------|
| Voice Memo | Microphone, Location |
| Photo OCR | Camera, Photos, Location |
| Quick Thought | Location (optional) |
| Web Clip | None |
| Recipe Saver | None |
| Dream Journal | None |
| Contact Note | Contacts, Location |
| Book Logger | None |
| Habit Tracker | None |
| Quote Saver | None |

**Grant permissions when prompted** or go to Settings > Shortcuts > [Shortcut Name]

### Step 5: Enable Untrusted Shortcuts (iOS Only)

If you get "Untrusted Shortcut" error:

1. Go to Settings > Shortcuts
2. Tap "Advanced"
3. Enable "Allow Untrusted Shortcuts"
4. Enter your passcode
5. Confirm

### Step 6: Add to Siri (Optional)

Make shortcuts voice-activated:

1. Open Shortcuts app
2. Find your shortcut
3. Tap the `⋯` menu
4. Tap "Add to Siri"
5. Record your phrase (suggestions in metadata files)

**Suggested Siri Phrases:**

- Voice Memo: "Voice note to Second Brain"
- Photo OCR: "Extract text to Second Brain"
- Quick Thought: "Quick thought to Second Brain"
- Web Clip: "Clip to Second Brain"
- Recipe: "Save recipe to Second Brain"
- Dream: "Log dream to Second Brain"

### Step 7: Add to Home Screen (Optional)

For quick access:

1. Open shortcut in Shortcuts app
2. Tap `⋯` menu
3. Select "Add to Home Screen"
4. Customize icon and name
5. Tap "Add"

---

## 🧪 Testing Your Shortcuts

### Method 1: Use Sample Data

Each shortcut has sample data in `sample_data.json`. Test via API:

```bash
# Test voice memo endpoint
curl -X POST http://localhost:8082/api/shortcuts/voice-memo \
  -H "Content-Type: application/json" \
  -d '{
    "transcription": "Test voice note",
    "location_data": {
      "latitude": 37.7749,
      "longitude": -122.4194,
      "address": "San Francisco, CA"
    }
  }'
```

### Method 2: Run Shortcuts

1. Open Shortcuts app
2. Tap the shortcut to run
3. Follow prompts
4. Check Second Brain dashboard for new note

### Method 3: Use Siri

1. Say: "Hey Siri, [your custom phrase]"
2. Follow Siri's prompts
3. Verify note creation

### Verification Checklist

- [ ] Shortcut runs without errors
- [ ] Note appears in Second Brain dashboard
- [ ] Tags are applied correctly
- [ ] Location data captured (if applicable)
- [ ] AI processing worked (summary, title, tags)
- [ ] Siri integration works

---

## 🔧 Troubleshooting

### Common Issues

#### 1. "Could not connect to server" Error

**Symptoms:** Shortcut fails with network error

**Solutions:**
- ✅ Verify server is running: `curl http://localhost:8082/health`
- ✅ Check server URL in shortcut matches your server
- ✅ Ensure iPhone and server on same network (if using localhost)
- ✅ Try public URL with ngrok: `ngrok http 8082`
- ✅ Check firewall settings

#### 2. "Authentication Required" Error

**Symptoms:** 401 or 403 errors

**Solutions:**
- ✅ Log into Second Brain via Safari first
- ✅ Session cookies are shared between Safari and Shortcuts
- ✅ Check if authentication is enabled in your server config
- ✅ Try accessing `/login` in Safari on your iPhone

#### 3. "Shortcut Won't Import"

**Symptoms:** Can't add shortcut, "Untrusted Shortcut" message

**Solutions:**
- ✅ Settings > Shortcuts > Advanced > Allow Untrusted Shortcuts
- ✅ Ensure iOS 15+ or macOS 12+
- ✅ Try importing on Mac first, then sync via iCloud
- ✅ Regenerate shortcuts with fresh conversion

#### 4. "Permission Denied" Errors

**Symptoms:** Shortcut stops and asks for permissions

**Solutions:**
- ✅ Grant requested permissions when prompted
- ✅ Settings > Shortcuts > [Shortcut] > Privacy
- ✅ Settings > Privacy > [Permission Type] > Shortcuts
- ✅ Delete and re-import shortcut if permission stuck

#### 5. Location Not Captured

**Symptoms:** Location data missing from notes

**Solutions:**
- ✅ Enable Location Services: Settings > Privacy > Location Services
- ✅ Allow "While Using" for Shortcuts app
- ✅ Grant location permission to specific shortcut
- ✅ Check GPS signal (outdoor, clear sky view)

#### 6. Voice Transcription Fails

**Symptoms:** Voice memo saves but no transcription

**Solutions:**
- ✅ Use iOS built-in dictation instead of audio file upload
- ✅ Check Whisper.cpp is running on server
- ✅ Verify audio file format (wav, m4a, mp3)
- ✅ Check server logs for transcription errors

#### 7. Shortcuts Not Syncing to iPhone

**Symptoms:** Shortcuts added on Mac don't appear on iPhone

**Solutions:**
- ✅ Settings > [Your Name] > iCloud > Shortcuts: ON
- ✅ Wait a few minutes for sync
- ✅ Force quit and reopen Shortcuts app
- ✅ Manually import on iPhone via AirDrop

### Debug Mode

Enable verbose logging:

1. Edit shortcut in Shortcuts app
2. Add "Show Result" actions after each HTTP request
3. Run shortcut and examine output
4. Check response for error messages

### Server Logs

Check Second Brain server logs:

```bash
# If running via uvicorn
# Logs appear in terminal

# Check for errors related to shortcuts
grep "shortcuts" server.log

# View recent API calls
tail -f server.log | grep "POST /api/shortcuts"
```

---

## 🎓 Advanced Usage

### Custom Shortcuts

You can create your own shortcuts by:

1. Copying an existing JSON definition
2. Modifying the actions and parameters
3. Running the conversion script
4. Importing the new shortcut

### Automation Ideas

**Morning Routine:**
```
1. iPhone alarm goes off
2. Auto-trigger Dream Journal shortcut
3. Log habit: Morning meditation
4. Quick thought: Today's goals
```

**Meeting Workflow:**
```
1. Calendar event starts
2. Auto-create Contact Note for attendees
3. Voice memo during meeting
4. Quick thought for action items
```

**Reading Workflow:**
```
1. Highlight text in Safari
2. Share to Web Clip shortcut
3. Auto-tag with "reading"
4. Add to reading list queue
```

### Siri Shortcuts Automations

Create time-based or location-based automations:

1. Open Shortcuts app
2. Tap "Automation" tab
3. Create Personal Automation
4. Choose trigger (time, location, etc.)
5. Add your Second Brain shortcut

**Examples:**
- **8 PM Daily:** Trigger Habit Tracker for evening routine
- **Arrive Home:** Ask to log Dream Journal from night before
- **Leave Work:** Prompt for Quick Thought about the day

### API Integration

Use shortcuts as webhook targets:

```python
# Trigger shortcut via URL scheme
import webbrowser
webbrowser.open("shortcuts://run-shortcut?name=Voice%20Memo")
```

### Batch Operations

Create a "master" shortcut that runs multiple shortcuts in sequence:

1. Create new shortcut
2. Add "Run Shortcut" actions
3. Chain multiple Second Brain shortcuts
4. Example: Morning routine that logs dream, habit, and daily goals

---

## 📚 Additional Resources

### Documentation Files

- `README.md` - Quick reference in shortcuts_bundle/
- `*_metadata.json` - Detailed docs for each shortcut
- `sample_data.json` - Test payloads and examples

### Second Brain Docs

- API Documentation: Check your server at `/docs`
- Codebase: `services/enhanced_apple_shortcuts_service.py`
- Templates: `templates/shortcuts_setup.html`

### Apple Resources

- [Shortcuts User Guide](https://support.apple.com/guide/shortcuts)
- [Shortcuts Gallery](https://shortcutsgallery.com)
- [r/shortcuts](https://reddit.com/r/shortcuts) - Community support

---

## 🎉 Next Steps

Now that your shortcuts are set up:

1. ✅ **Try each shortcut** to ensure it works
2. ✅ **Customize Siri phrases** for natural voice commands
3. ✅ **Add to home screen** for quick access
4. ✅ **Create automations** for routine tasks
5. ✅ **Share with others** in your Second Brain network
6. ✅ **Build custom shortcuts** for your unique workflows

**Pro Tips:**

- Start with 2-3 shortcuts you'll use daily
- Set up Siri phrases that feel natural to you
- Review captured notes weekly to refine your setup
- Combine shortcuts with iOS automations for maximum efficiency

---

## 💡 Need Help?

- **Issues:** Check the Troubleshooting section above
- **Questions:** Review the metadata files for each shortcut
- **Bugs:** Check server logs and shortcut debug output
- **Feature Requests:** Modify the JSON definitions and regenerate

Happy capturing! 🧠✨
