# Apple Shortcuts for Second Brain

This directory contains pre-configured Apple Shortcuts for iOS, iPadOS, and macOS.

## Quick Start

1. **Download shortcuts** from this directory
2. **Import** into the Shortcuts app
3. **Configure** your API URL and token
4. **Test** with sample data
5. **Activate** Siri phrases

## Available Shortcuts (15 Total)

### Core Shortcuts
- ✅ `Quick_Note_Shortcut.json` - Quick note capture
- ✅ `Voice_Whisper_Shortcut.json` - Voice memos
- ✅ `Photo_Text_Shortcut.json` - Photo OCR
- ✅ `Quick_Reminder_Shortcut.json` - Quick reminders
- ✅ `Calendar_Event_Shortcut.json` - Calendar integration
- ✅ `Contact_Shortcut.json` - Contact notes

### New Advanced Shortcuts (v2.0)
- 🆕 `Dream_Journal_Shortcut.json` - Morning dream logging
- 🆕 `Quote_Capture_Shortcut.json` - Quote collection
- 🆕 `Code_Snippet_Shortcut.json` - Developer snippets
- 🆕 `Habit_Tracker_Shortcut.json` - Daily habit tracking
- 🆕 `Travel_Journal_Shortcut.json` - Travel experiences

### Additional Shortcuts (Available via API)
- Reading List Saver
- Contact Notes
- Book/Media Logger
- Recipe Saver

## Setup Instructions

### 1. Get API Credentials

Log into your Second Brain dashboard:
```
Settings → API Access → Generate Token
```

You'll need:
- **Base URL**: `https://your-domain.com`
- **API Token**: `your-api-token-here`

### 2. Configure Shortcuts

For each shortcut:

1. Open the `.json` file
2. Replace placeholders:
   - `YOUR_DOMAIN` → your actual domain
   - `YOUR_API_TOKEN` → your API token
3. Import into Shortcuts app
4. Test with sample data

### 3. Enable Features

**Siri Integration:**
1. Open shortcut → tap (i) icon
2. Tap "Add to Siri"
3. Record your custom phrase

**Share Sheet:**
1. Open shortcut → tap (i) icon
2. Enable "Show in Share Sheet"
3. Select content types

**Home Screen Widget:**
1. Long press Home Screen
2. Tap + → Shortcuts widget
3. Select your shortcuts

## Configuration Template

All shortcuts follow this format:

```json
{
  "type": "web_request",
  "method": "POST",
  "url": "https://YOUR_DOMAIN.com/api/shortcuts/[endpoint]",
  "headers": {
    "Authorization": "Bearer YOUR_API_TOKEN",
    "Content-Type": "application/json"
  },
  "body": {
    "...": "data"
  }
}
```

## Endpoints Reference

| Shortcut | Endpoint | Method |
|----------|----------|--------|
| Voice Memo | `/voice-memo` | POST |
| Photo OCR | `/photo-ocr` | POST |
| Quick Note | `/quick-note` | POST |
| Web Clip | `/web-clip` | POST |
| Reading List | `/reading-list` | POST |
| Contact Note | `/contact-note` | POST |
| Media Note | `/media-note` | POST |
| Recipe | `/recipe` | POST |
| Dream Journal | `/dream-journal` | POST |
| Quote | `/quote` | POST |
| Code Snippet | `/code-snippet` | POST |
| Travel Journal | `/travel-journal` | POST |
| Habit Log | `/habit-log` | POST |
| File Upload | `/file-upload` | POST |

## Customization Tips

### Add Custom Fields

Extend shortcuts with additional fields:

```json
{
  "custom_field": "your_value",
  "tags_custom": ["tag1", "tag2"],
  "metadata_extra": {
    "key": "value"
  }
}
```

### Create Automations

**Time-based:**
- Daily dream journal at 7 AM
- Evening habit check at 9 PM
- Weekly review on Sundays

**Location-based:**
- Auto-log gym visits
- Travel journal at airports
- Contact notes at office

**Event-based:**
- Meeting notes after calendar events
- Reading list saves before bed
- Quote captures while reading

## Troubleshooting

### Common Issues

**"Cannot Connect"**
- Check internet connection
- Verify URL is correct
- Ensure HTTPS is configured

**"Authentication Failed"**
- Verify API token
- Check Authorization header
- Regenerate token if expired

**"Invalid Request"**
- Review required fields
- Check JSON formatting
- Validate data types

### Testing

Test shortcuts with curl:

```bash
curl -X POST https://your-domain.com/api/shortcuts/quote \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "quote_text": "Test quote",
    "author": "Test Author"
  }'
```

Expected response:
```json
{
  "success": true,
  "note_id": 123,
  "title": "Quote by Test Author",
  "message": "Quote saved successfully"
}
```

## Advanced Usage

### Batch Processing

Save multiple items offline:

```json
{
  "requests": [
    {"type": "quote", "data": {...}},
    {"type": "habit_log", "data": {...}}
  ]
}
```

Endpoint: `POST /api/shortcuts/batch`

### Offline Mode

Shortcuts automatically queue when offline:
1. Data saved to device
2. Synced when connection restored
3. Notifications on completion

## Best Practices

1. **Naming**: Use clear, consistent names
2. **Organization**: Group by category
3. **Testing**: Test before daily use
4. **Security**: Don't share shortcuts with tokens
5. **Updates**: Keep shortcuts updated

## Support

For help:
- 📖 [Full Documentation](../docs/APPLE_SHORTCUTS_GUIDE.md)
- 🐛 [Report Issues](https://github.com/dhouchin1/second_brain/issues)
- 💬 [Community Discord](#)

## Version History

### v2.0 (Current)
- ✨ Added 10 new shortcut types
- 🚀 Batch processing support
- 📍 Enhanced location features
- 🤖 AI-powered analysis

### v1.0
- 🎉 Initial release
- 6 core shortcuts
- Basic functionality

---

**Happy Capturing! 🚀**

Made with ❤️ for Second Brain users
