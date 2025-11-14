# Apple Shortcuts - Quick Start Guide

Get your Second Brain shortcuts up and running in 5 minutes! ⚡

## Prerequisites ✅

- [ ] Second Brain server running (port 8082)
- [ ] iPhone/iPad with iOS 15+ OR Mac with macOS 12+
- [ ] Python 3.7+ installed

## 3-Step Setup

### Step 1️⃣: Generate Shortcuts (1 min)

```bash
cd apple_shortcuts/
python3 import_shortcuts.py --server-url http://localhost:8082
```

**Using a different server?** Replace localhost with your server URL:
```bash
# Remote server
python3 import_shortcuts.py --server-url https://brain.example.com

# Local network
python3 import_shortcuts.py --server-url http://192.168.1.100:8082

# ngrok tunnel
python3 import_shortcuts.py --server-url https://abc123.ngrok.io
```

### Step 2️⃣: Import Shortcuts (2 min)

#### On Mac 🖥️

```bash
cd shortcuts_bundle/
./import_all.sh
```

Click "Add Shortcut" for each one in the Shortcuts app.

#### On iPhone 📱

**Option A: AirDrop**
1. AirDrop `shortcuts_bundle/` folder to your iPhone
2. Tap each `.shortcut` file
3. Tap "Add Shortcut"

**Option B: iCloud**
1. Copy folder to iCloud Drive
2. Open Files app on iPhone
3. Tap each `.shortcut` file

### Step 3️⃣: Test (2 min)

1. Open Shortcuts app
2. Tap "Quick Thought to Second Brain"
3. Enter a test message
4. Check your Second Brain dashboard for the new note

✅ **Success!** You're ready to capture knowledge anywhere.

## First Shortcuts to Try

Start with these 3 essential shortcuts:

1. **Quick Thought** - Instant idea capture
   - Siri: "Quick thought to Second Brain"
   - Use for: Random ideas, to-dos, reminders

2. **Voice Memo** - Hands-free capture
   - Siri: "Voice note to Second Brain"
   - Use for: Driving, walking, brainstorming

3. **Web Clip** - Save articles
   - Safari share sheet → Run Shortcut
   - Use for: Research, reading lists, quotes

## Common Setup Issues

### "Untrusted Shortcut" Error

Settings → Shortcuts → Advanced → Enable "Allow Untrusted Shortcuts"

### "Could not connect to server"

- ✅ Server running? `curl http://localhost:8082/health`
- ✅ On same network? (if using localhost)
- ✅ Firewall blocking? Check port 8082

### "Authentication Required"

Log into Second Brain via Safari first (session cookies are shared)

## Next Steps

- 📖 Read [INSTRUCTIONS.md](INSTRUCTIONS.md) for detailed setup
- 🎤 Add Siri phrases to your shortcuts
- 🏠 Add shortcuts to home screen
- 🔄 Create automations for daily routines

## Need Help?

1. Check [INSTRUCTIONS.md](INSTRUCTIONS.md) - Troubleshooting section
2. Review `*_metadata.json` files for each shortcut
3. Check server logs for errors
4. Test API directly with curl (see sample_data.json)

---

**Pro Tip:** Start with just 2-3 shortcuts you'll use daily. Add more as needed!
