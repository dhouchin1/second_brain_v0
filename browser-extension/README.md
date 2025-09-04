# Second Brain Browser Extension

Capture web content directly to your Second Brain with AI-powered processing.

## Features

- **Quick Capture**: Right-click to save selections, pages, links, and images
- **Smart Processing**: AI summarization, tagging, and content enhancement
- **Multiple Capture Types**: Text selection, full page, bookmarks, and manual notes
- **Real-time Sync**: Instantly sync with your Second Brain server
- **Context Menus**: Right-click context menus for seamless capture
- **Keyboard Shortcuts**: 
  - `Ctrl+Shift+S` - Quick save selection
  - `Ctrl+Shift+P` - Quick save page

## Installation

### Chrome/Edge (Chromium-based browsers)

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" in the top right
3. Click "Load unpacked" and select this `browser-extension` folder
4. The Second Brain extension should now appear in your extensions

### Firefox

1. Open Firefox and navigate to `about:debugging`
2. Click "This Firefox"
3. Click "Load Temporary Add-on"
4. Select the `manifest.json` file in this folder

## Setup

1. **Install the extension** using the steps above
2. **Click the extension icon** in your browser toolbar
3. **Click "Settings"** to configure your connection
4. **Enter your Second Brain server URL** (e.g., `http://localhost:8084`)
5. **Enter your authentication token** (get this from your Second Brain dashboard)
6. **Click "Test Connection"** to verify everything works

## Usage

### Quick Capture Methods

1. **Text Selection**: Select text on any webpage, then right-click → "Save to Second Brain"
2. **Full Page**: Right-click on any page → "Save page to Second Brain"
3. **Bookmarks**: Right-click → "Save link to Second Brain"
4. **Manual Notes**: Click the extension icon and use the "Manual Note" section

### Context Menu Options

- **Save Selection**: Capture highlighted text with context
- **Save Page**: Capture the main content of the current page
- **Save Link**: Bookmark a link for later reference
- **Save Image**: Save image references with context

### Keyboard Shortcuts

- **Ctrl+Shift+S**: Quick save current selection
- **Ctrl+Shift+P**: Quick save current page

## Configuration Options

### Connection Settings
- **Server URL**: Your Second Brain server endpoint
- **Auth Token**: API authentication token from your dashboard

### Capture Settings
- **Default Tags**: Automatically add these tags to all captures
- **Auto-Enhancement**: Use AI to improve captured content
- **Notifications**: Show success/error notifications

## Permissions

The extension requires these permissions:
- **Active Tab**: To read content from the current webpage
- **Context Menus**: To add right-click capture options
- **Storage**: To save your settings and preferences
- **Scripting**: To extract content from web pages
- **Host Permissions**: To communicate with your Second Brain server

## Troubleshooting

### Connection Issues
1. Verify your Second Brain server is running
2. Check the server URL is correct (include `http://` or `https://`)
3. Ensure your auth token is valid
4. Check browser console for detailed error messages

### Capture Failures
1. Some sites block content extraction - try manual notes instead
2. Make sure you have text selected before using "Save Selection"
3. Verify your auth token has proper permissions

### Common Solutions
- **Reload the extension** in `chrome://extensions/`
- **Check server logs** for API errors
- **Clear browser cache** if experiencing weird behavior
- **Restart browser** if keyboard shortcuts stop working

## Development

### File Structure
```
browser-extension/
├── manifest.json          # Extension manifest
├── popup.html            # Main popup interface
├── popup.js              # Popup functionality
├── options.html          # Settings page
├── options.js            # Settings functionality
├── background.js         # Service worker / background script
├── content.js            # Content script for page interaction
├── content.css           # Styles for content script UI
└── icons/                # Extension icons
    └── brain.svg
```

### Building from Source
1. Clone the Second Brain repository
2. The extension source is in the `browser-extension/` directory
3. Load as unpacked extension for development
4. Make changes and reload the extension to test

## Privacy

- All data is sent directly to your self-hosted Second Brain server
- No data is shared with third parties
- Content processing happens on your server, not in the cloud
- Extension only communicates with your configured server URL

## Support

For issues, feature requests, or questions:
- GitHub: https://github.com/dhouchin1/second_brain
- Create an issue with detailed information about your problem

## Version History

### v1.0.0
- Initial release
- Basic capture functionality
- Context menu integration
- Settings page
- Real-time status updates