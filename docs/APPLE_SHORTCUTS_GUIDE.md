# Apple Shortcuts Integration Guide

Complete guide to setting up and using Apple Shortcuts with your Second Brain system.

## Table of Contents

1. [Overview](#overview)
2. [Getting Started](#getting-started)
3. [Available Shortcuts](#available-shortcuts)
4. [Setup Instructions](#setup-instructions)
5. [Advanced Usage](#advanced-usage)
6. [Troubleshooting](#troubleshooting)

## Overview

Second Brain provides 15 powerful Apple Shortcuts integrations that allow you to capture information from your iPhone, iPad, or Mac instantly. All shortcuts support:

- ✅ Offline queuing (save now, sync later)
- ✅ Location tagging
- ✅ AI-powered auto-tagging
- ✅ Rich metadata preservation
- ✅ Siri voice activation
- ✅ Share Sheet integration

## Getting Started

### Prerequisites

1. **Second Brain Server**: Your Second Brain instance must be accessible via HTTPS
2. **API Access**: You need your API base URL and authentication token
3. **Shortcuts App**: Pre-installed on iOS 13+ and macOS 12+

### Quick Setup

1. Open Settings app → Shortcuts
2. Enable "Allow Running Scripts" and "Allow Sharing Large Amounts of Data"
3. Get your API details from your Second Brain dashboard
4. Download and configure shortcuts from `apple_shortcuts/` directory

## Available Shortcuts

### 1. 📝 Quick Voice Memo

Record and transcribe voice memos with location context.

**Use Cases:**
- Meeting notes while driving
- Quick ideas on the go
- Voice journaling
- Interview recordings

**Features:**
- iOS dictation for transcription
- Location auto-tagging
- AI summarization
- Action item extraction

**Siri Phrase:** "Save voice memo to Second Brain"

---

### 2. 📸 Photo OCR Capture

Take photos and extract text with OCR.

**Use Cases:**
- Business cards
- Whiteboards and presentations
- Printed documents
- Signs and menus

**Features:**
- Built-in OCR processing
- Location tagging
- Auto-categorization
- Image preservation

**Siri Phrase:** "Scan text to Second Brain"

---

### 3. 💭 Quick Thought Capture

Instantly capture thoughts and ideas.

**Use Cases:**
- Random thoughts
- Task reminders
- Shower thoughts
- Creative ideas

**Features:**
- Multiple note types (thought, task, idea, meeting)
- Auto-tagging
- Quick entry
- Minimal friction

**Siri Phrase:** "Quick note to Second Brain"

---

### 4. 🔗 Web Clip from Safari

Save web pages and articles from Safari.

**Use Cases:**
- Research articles
- Blog posts
- Documentation
- Product pages

**Features:**
- Full page extraction
- Selected text highlighting
- Metadata preservation
- Share Sheet integration

**Siri Phrase:** "Clip this page to Second Brain"

---

### 5. 📚 Reading List Saver (NEW)

Save articles from Safari Reading List.

**Use Cases:**
- Archiving reading list articles
- Long-form article collection
- Research material curation
- Permanent article storage

**Features:**
- Full article extraction
- Reading list metadata
- Auto-tagging by topic
- Offline article saving

**Endpoint:** `POST /api/shortcuts/reading-list`

**Parameters:**
```json
{
  "url": "https://example.com/article",
  "title": "Article Title",
  "preview_text": "Preview excerpt...",
  "added_date": "2024-12-15T10:30:00Z",
  "context": {
    "device": "iPhone",
    "timestamp": "2024-12-15T10:30:00Z"
  }
}
```

---

### 6. 👤 Contact Notes (NEW)

Create structured notes about people you meet.

**Use Cases:**
- Networking events
- Client meetings
- Interview notes
- Personal relationship tracking

**Features:**
- Contact information storage
- Meeting context
- Location tagging
- Follow-up reminders

**Endpoint:** `POST /api/shortcuts/contact-note`

**Parameters:**
```json
{
  "contact_name": "John Doe",
  "contact_info": {
    "phone": "+1234567890",
    "email": "john@example.com",
    "company": "Acme Corp",
    "title": "CEO"
  },
  "note_text": "Met at conference. Interested in our product.",
  "meeting_context": {
    "date": "2024-12-15",
    "topic": "Product Demo"
  },
  "location_data": {
    "latitude": 37.7749,
    "longitude": -122.4194,
    "address": "San Francisco, CA"
  }
}
```

---

### 7. 📖 Book/Media Logger (NEW)

Track books, movies, podcasts, and other media.

**Use Cases:**
- Book reviews
- Movie ratings
- Podcast notes
- YouTube video summaries

**Features:**
- Multiple media types
- Rating system (1-5 stars)
- Creator attribution
- Custom metadata (ISBN, URL, genre)

**Endpoint:** `POST /api/shortcuts/media-note`

**Parameters:**
```json
{
  "media_type": "book",
  "title": "Atomic Habits",
  "creator": "James Clear",
  "notes": "Excellent book on habit formation...",
  "rating": 5,
  "tags_custom": ["self-improvement", "productivity"],
  "metadata_extra": {
    "year": "2018",
    "genre": "Self-Help",
    "isbn": "978-0735211292"
  }
}
```

**Media Types:** `book`, `movie`, `podcast`, `article`, `video`

---

### 8. 🍳 Recipe Saver (NEW)

Save recipes with structured ingredients and instructions.

**Use Cases:**
- Recipe collection
- Meal planning
- Cooking experiments
- Family recipes

**Features:**
- Structured ingredients list
- Step-by-step instructions
- Timing information
- Servings tracking

**Endpoint:** `POST /api/shortcuts/recipe`

**Parameters:**
```json
{
  "recipe_name": "Chocolate Chip Cookies",
  "ingredients": [
    "2 cups flour",
    "1 cup butter",
    "1 cup chocolate chips"
  ],
  "instructions": [
    "Preheat oven to 350°F",
    "Mix dry ingredients",
    "Bake for 12 minutes"
  ],
  "prep_time": "15 minutes",
  "cook_time": "12 minutes",
  "servings": 24,
  "source_url": "https://example.com/recipe",
  "tags_custom": ["dessert", "cookies"]
}
```

---

### 9. 🌙 Dream Journal (NEW)

Log dreams with emotions, themes, and analysis.

**Use Cases:**
- Dream tracking
- Lucid dream journaling
- Sleep quality monitoring
- Pattern recognition

**Features:**
- Emotion tagging
- Theme identification
- Lucid dream marking
- AI dream analysis

**Endpoint:** `POST /api/shortcuts/dream-journal`

**Parameters:**
```json
{
  "dream_text": "I was flying over a city...",
  "emotions": ["excited", "anxious", "curious"],
  "themes": ["flying", "city", "exploration"],
  "lucid": true,
  "sleep_quality": 4
}
```

---

### 10. 💬 Quote Capture (NEW)

Save inspirational quotes with attribution.

**Use Cases:**
- Quote collection
- Book highlights
- Speech excerpts
- Social media quotes

**Features:**
- Author attribution
- Source tracking
- Category tagging
- Personal reflections

**Endpoint:** `POST /api/shortcuts/quote`

**Parameters:**
```json
{
  "quote_text": "The only way to do great work is to love what you do.",
  "author": "Steve Jobs",
  "source": "Stanford Commencement Speech",
  "category": "motivation",
  "reflection": "This resonates with my career journey..."
}
```

---

### 11. 💻 Code Snippet Saver (NEW)

Save code snippets with syntax highlighting.

**Use Cases:**
- Code reference library
- Solution collection
- Learning notes
- Stack Overflow saves

**Features:**
- Multi-language support
- Syntax highlighting tags
- Source URL preservation
- Description annotation

**Endpoint:** `POST /api/shortcuts/code-snippet`

**Parameters:**
```json
{
  "code": "def hello_world():\n    print('Hello, World!')",
  "language": "python",
  "description": "Basic Hello World function",
  "tags_custom": ["beginner", "tutorial"],
  "source_url": "https://github.com/example/repo"
}
```

**Supported Languages:** Python, JavaScript, TypeScript, Go, Rust, Java, C++, Swift, Ruby, PHP, etc.

---

### 12. ✈️ Travel Journal (NEW)

Rich travel logging with location and photos.

**Use Cases:**
- Travel blogging
- Trip memories
- Expense tracking
- Location history

**Features:**
- GPS coordinates
- Multiple photos
- Activity categorization
- Expense tracking
- Companion tracking

**Endpoint:** `POST /api/shortcuts/travel-journal`

**Parameters:**
```json
{
  "entry_text": "Amazing sunset at the Eiffel Tower...",
  "location_data": {
    "latitude": 48.8584,
    "longitude": 2.2945,
    "address": "Eiffel Tower, Paris, France"
  },
  "photos": ["base64_photo_1", "base64_photo_2"],
  "activity_type": "sightseeing",
  "companions": ["Alice", "Bob"],
  "expenses": {
    "amount": 50,
    "currency": "EUR"
  }
}
```

---

### 13. ✅ Habit Tracker (NEW)

Log daily habit completions and streaks.

**Use Cases:**
- Habit building
- Routine tracking
- Behavioral change
- Streak maintenance

**Features:**
- Completion tracking
- Mood logging
- Difficulty rating
- Progress notes

**Endpoint:** `POST /api/shortcuts/habit-log`

**Parameters:**
```json
{
  "habit_name": "Morning Exercise",
  "completed": true,
  "notes": "30 minutes of yoga",
  "mood": "energized",
  "difficulty": 3
}
```

---

### 14. 📁 File Uploader (NEW)

Upload files directly from Files app.

**Use Cases:**
- Document storage
- PDF archiving
- Image collection
- File organization

**Features:**
- Multi-format support
- Auto-categorization
- File metadata
- Size tracking

**Endpoint:** `POST /api/shortcuts/file-upload`

**Parameters:**
```json
{
  "file_data": "base64_encoded_file_content",
  "file_name": "document.pdf",
  "file_type": "application/pdf",
  "description": "Important contract",
  "tags_custom": ["legal", "contracts"]
}
```

**Supported Types:** PDF, Images, Audio, Video, Documents

---

### 15. 📅 Meeting Notes Starter

Pre-populate meeting notes from calendar.

**Use Cases:**
- Meeting preparation
- Agenda creation
- Follow-up tracking
- Meeting archives

**Features:**
- Calendar integration
- Template-based notes
- Attendee lists
- Action item tracking

---

## Setup Instructions

### Step 1: Get Your API Credentials

1. Log into your Second Brain dashboard
2. Navigate to Settings → API Access
3. Copy your **API Base URL** and **API Token**

Example:
- Base URL: `https://your-domain.com`
- API Token: `your-api-token-here`

### Step 2: Configure Authentication

All shortcuts require authentication. Add these to each shortcut:

**Headers:**
```
Authorization: Bearer YOUR_API_TOKEN
Content-Type: application/json
```

### Step 3: Import Shortcuts

#### Option A: Download Pre-built Shortcuts

1. Download shortcut files from `apple_shortcuts/` directory
2. Open in Shortcuts app
3. Update URL and API token
4. Test with sample data

#### Option B: Build Custom Shortcuts

Use the Shortcuts app to create custom workflows:

1. Add "Get Contents of URL" action
2. Set Method to POST
3. Set URL to endpoint (e.g., `https://your-domain.com/api/shortcuts/quote`)
4. Add Headers for authentication
5. Add Request Body with JSON
6. Add notification for success/failure

### Step 4: Enable Siri

1. Open shortcut in Shortcuts app
2. Tap (i) icon
3. Tap "Add to Siri"
4. Record custom phrase
5. Test with "Hey Siri, [your phrase]"

### Step 5: Add to Share Sheet (Optional)

1. Open shortcut
2. Tap (i) icon
3. Enable "Show in Share Sheet"
4. Select supported content types

## Advanced Usage

### Batch Processing

Save multiple items offline and sync when connected:

**Endpoint:** `POST /api/shortcuts/batch`

```json
{
  "requests": [
    {
      "type": "quote",
      "data": {
        "quote_text": "...",
        "author": "..."
      }
    },
    {
      "type": "habit_log",
      "data": {
        "habit_name": "Exercise",
        "completed": true
      }
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "total_requests": 2,
  "successful": 2,
  "failed": 0,
  "results": [...]
}
```

### Location Automation

Use iOS location triggers to auto-capture notes:

1. Create shortcut with location parameter
2. Add Automation trigger
3. Select "Arrive at Location"
4. Choose location
5. Run shortcut automatically

**Example:** Auto-log gym visits when arriving at gym.

### Scheduled Captures

Use time-based automations:

1. Create Automation
2. Select "Time of Day"
3. Set schedule (e.g., 9 PM daily)
4. Run dream journal or daily reflection

### Widget Integration

Add shortcuts to Home Screen widgets:

1. Long press Home Screen
2. Tap + to add widget
3. Select "Shortcuts"
4. Choose size and shortcuts
5. Tap anywhere on screen

## Troubleshooting

### Common Issues

#### 1. "Authentication Failed"
- Check API token is correct
- Verify Authorization header format
- Ensure token hasn't expired

#### 2. "Cannot Connect to Server"
- Check internet connection
- Verify base URL is correct
- Ensure server is running
- Check HTTPS certificate

#### 3. "Invalid Parameters"
- Review required fields
- Check JSON formatting
- Verify data types match

#### 4. "Shortcut Not Working"
- Enable "Allow Running Scripts"
- Check privacy settings
- Review shortcut actions
- Test with manual data

### Getting Help

1. **Check Logs:** View shortcut execution logs in app
2. **Test Endpoints:** Use curl or Postman to test API
3. **GitHub Issues:** Report bugs at repository
4. **Documentation:** Review API documentation

### Debug Mode

Enable detailed logging in shortcuts:

1. Add "Get Contents of URL" result to variable
2. Add "Show Result" action
3. Review response data
4. Check for error messages

## Best Practices

### 1. Naming Conventions

Use clear, consistent naming:
- ✅ "SB - Quick Note"
- ✅ "Second Brain: Voice Memo"
- ❌ "Note"
- ❌ "Shortcut 1"

### 2. Organization

Create folders for shortcuts:
- Personal
- Work
- Travel
- Learning

### 3. Error Handling

Always add error notifications:
```
If Shortcut Input has any value
  Show notification "Success!"
Otherwise
  Show notification "Error: Try again"
End If
```

### 4. Testing

Test shortcuts with:
- Valid data
- Missing fields
- Invalid formats
- Offline mode
- Different devices

### 5. Security

Protect sensitive data:
- Use secure HTTPS endpoints
- Don't share shortcuts with API tokens
- Rotate tokens periodically
- Use environment variables when possible

## API Reference

### Base URL
```
https://your-domain.com/api/shortcuts
```

### Authentication
```
Authorization: Bearer YOUR_API_TOKEN
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/voice-memo` | POST | Voice memo capture |
| `/photo-ocr` | POST | Photo OCR processing |
| `/quick-note` | POST | Quick note capture |
| `/web-clip` | POST | Web page clipping |
| `/reading-list` | POST | Reading list article |
| `/contact-note` | POST | Contact note |
| `/media-note` | POST | Media logging |
| `/recipe` | POST | Recipe saving |
| `/dream-journal` | POST | Dream logging |
| `/quote` | POST | Quote capture |
| `/code-snippet` | POST | Code snippet |
| `/travel-journal` | POST | Travel entry |
| `/habit-log` | POST | Habit tracking |
| `/file-upload` | POST | File upload |
| `/batch` | POST | Batch processing |
| `/templates` | GET | Get templates |
| `/stats` | GET | Usage statistics |
| `/health` | GET | Health check |

### Response Format

**Success:**
```json
{
  "success": true,
  "note_id": 12345,
  "title": "Note Title",
  "message": "Note saved successfully"
}
```

**Error:**
```json
{
  "success": false,
  "error": "Error message here"
}
```

## Examples

### Example 1: Morning Dream Journal

**Automation Trigger:** 7:00 AM daily

**Workflow:**
1. Show input dialog: "Describe your dreams"
2. Get current emotions from list
3. Rate sleep quality
4. Send to `/dream-journal`
5. Show success notification

### Example 2: Contact After Meeting

**Automation Trigger:** Leave work location

**Workflow:**
1. Choose from calendar events today
2. Input meeting notes
3. Get location automatically
4. Send to `/contact-note`
5. Add reminder to follow up

### Example 3: Recipe from Safari

**Share Sheet Trigger:** Safari

**Workflow:**
1. Get webpage URL and title
2. Extract text content
3. Parse ingredients and steps
4. Send to `/recipe`
5. Add to Reminders as grocery list

## Updates & Changelog

### v2.0 (Current)
- ✨ Added 10 new shortcut types
- 🚀 Batch processing support
- 📍 Enhanced location features
- 🤖 Improved AI processing
- 📊 Usage statistics endpoint

### v1.0
- 🎉 Initial release
- 5 basic shortcuts
- Core functionality

## Support

For questions, issues, or feature requests:

- **GitHub:** [Issues](https://github.com/dhouchin1/second_brain/issues)
- **Documentation:** [Full Docs](https://docs.second-brain.app)
- **Email:** support@second-brain.app

---

**Happy Capturing! 🚀**
