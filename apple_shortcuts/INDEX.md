# Apple Shortcuts Bundle - Complete Index

## 📱 New Shortcuts (JSON Definitions)

These are the newly created, comprehensive shortcut definitions with full documentation:

### 01. Voice Memo to Second Brain
- **File:** `01_voice_memo.json`
- **Icon:** 🎤
- **Purpose:** Record and transcribe voice memos with location context
- **Permissions:** Microphone, Location
- **Siri:** "Voice note to Second Brain"
- **Features:**
  - iOS dictation integration
  - Location tracking
  - AI summarization
  - Action item extraction
  - Timestamp and device context

### 02. Photo OCR to Second Brain
- **File:** `02_photo_ocr.json`
- **Icon:** 📸
- **Purpose:** Extract text from photos using OCR
- **Permissions:** Camera, Photos, Location
- **Siri:** "Extract text to Second Brain"
- **Use Cases:**
  - Business cards
  - Whiteboards
  - Documents
  - Receipts
  - Signs and menus

### 03. Quick Thought to Second Brain
- **File:** `03_quick_thought.json`
- **Icon:** 💭
- **Purpose:** Instant capture of thoughts and ideas
- **Permissions:** Location (optional)
- **Siri:** "Quick thought to Second Brain"
- **Note Types:**
  - Thoughts
  - Ideas
  - Tasks
  - Meetings
  - Reminders
  - Random notes

### 04. Web Clip to Second Brain
- **File:** `04_web_clip.json`
- **Icon:** 🌐
- **Purpose:** Save web content from Safari
- **Permissions:** None
- **Siri:** "Clip to Second Brain"
- **Features:**
  - Safari share sheet integration
  - Selected text capture
  - Full page archiving
  - Automatic tagging

### 05. Recipe to Second Brain
- **File:** `05_recipe_saver.json`
- **Icon:** 🍳
- **Purpose:** Save structured recipes
- **Permissions:** None
- **Siri:** "Save recipe to Second Brain"
- **Captures:**
  - Recipe name
  - Ingredients list
  - Step-by-step instructions
  - Prep & cook times
  - Servings
  - Source URL

### 06. Dream Journal to Second Brain
- **File:** `06_dream_journal.json`
- **Icon:** 🌙
- **Purpose:** Log dreams with rich metadata
- **Permissions:** None
- **Siri:** "Log dream to Second Brain"
- **Tracks:**
  - Dream description
  - Emotions felt
  - Themes and symbols
  - Lucid dream status
  - Sleep quality rating
  - AI analysis

### 07. Contact Note to Second Brain
- **File:** `07_contact_note.json`
- **Icon:** 👤
- **Purpose:** Save notes about people you meet
- **Permissions:** Contacts, Location
- **Siri:** "Save contact to Second Brain"
- **Includes:**
  - Contact information
  - Meeting context
  - Location data
  - Follow-up notes

### 08. Book Logger to Second Brain
- **File:** `08_book_logger.json`
- **Icon:** 📚
- **Purpose:** Track books, movies, podcasts, etc.
- **Permissions:** None
- **Siri:** "Log book to Second Brain"
- **Media Types:**
  - Books
  - Movies
  - Podcasts
  - Articles
  - Videos
  - Audiobooks
- **Features:**
  - Star ratings
  - Personal notes
  - Genre tagging
  - Year tracking

### 09. Habit Tracker to Second Brain
- **File:** `09_habit_tracker.json`
- **Icon:** ✅
- **Purpose:** Log daily habit completions
- **Permissions:** None
- **Siri:** "Log habit to Second Brain"
- **Tracks:**
  - Habit name
  - Completion status
  - Mood
  - Difficulty rating
  - Optional notes

### 10. Quote Saver to Second Brain
- **File:** `10_quote_saver.json`
- **Icon:** 💬
- **Purpose:** Save inspiring quotes
- **Permissions:** None
- **Siri:** "Save quote to Second Brain"
- **Captures:**
  - Quote text
  - Author attribution
  - Source (book, speech, etc.)
  - Category/theme
  - Personal reflection

---

## 🛠️ Legacy Shortcuts (Pre-existing)

These shortcuts were in the directory before this session:

- `Calendar_Event_Shortcut.json` - Calendar event notes
- `Code_Snippet_Shortcut.json` - Code snippet saver
- `Contact_Shortcut.json` - Contact management
- `Dream_Journal_Shortcut.json` - Dream logging
- `Habit_Tracker_Shortcut.json` - Habit tracking
- `Photo_Text_Shortcut.json` - Photo text extraction
- `Quick_Note_Shortcut.json` - Quick notes
- `Quick_Reminder_Shortcut.json` - Reminders
- `Quote_Capture_Shortcut.json` - Quote capture
- `Travel_Journal_Shortcut.json` - Travel journaling
- `Voice_Whisper_Shortcut.json` - Voice with Whisper

**Note:** The new shortcuts (01-10) are more comprehensive and include full documentation, sample data, and enhanced features.

---

## 📄 Documentation Files

### Core Documentation
- **README.md** - Main overview and feature list
- **QUICKSTART.md** - 5-minute setup guide
- **INSTRUCTIONS.md** - Complete setup and troubleshooting guide
- **INDEX.md** - This file - complete shortcut index

### Data & Scripts
- **sample_data.json** - Test payloads for all shortcuts
- **import_shortcuts.py** - Python script to convert and import shortcuts

---

## 🎯 Recommended Setup Order

For new users, install shortcuts in this order:

1. **Quick Thought** (#03) - Simplest, great for testing
2. **Voice Memo** (#01) - Most versatile for capturing ideas
3. **Web Clip** (#04) - Essential for research
4. **Habit Tracker** (#09) - Good for daily use
5. **Quote Saver** (#10) - Build inspiration library
6. Add others based on your needs

---

## 📊 Feature Matrix

| Shortcut | Location | AI | OCR | Voice | Siri | Share Sheet |
|----------|----------|----|----|-------|------|-------------|
| Voice Memo | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ |
| Photo OCR | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| Quick Thought | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| Web Clip | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |
| Recipe | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Dream Journal | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ |
| Contact Note | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Book Logger | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Habit Tracker | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Quote Saver | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |

---

## 🔗 Quick Links

- **Setup:** [QUICKSTART.md](QUICKSTART.md)
- **Full Guide:** [INSTRUCTIONS.md](INSTRUCTIONS.md)
- **Test Data:** [sample_data.json](sample_data.json)
- **Import Script:** [import_shortcuts.py](import_shortcuts.py)
- **Backend Code:** `../services/enhanced_apple_shortcuts_service.py`

---

## 📞 Support

- **Setup Issues:** See INSTRUCTIONS.md → Troubleshooting
- **API Errors:** Check sample_data.json for correct payload format
- **Feature Requests:** Modify JSON files and regenerate
- **Server Issues:** Check `../services/enhanced_apple_shortcuts_service.py`
