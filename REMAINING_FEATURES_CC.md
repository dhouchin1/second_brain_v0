# Remaining Features for Claude Code Web

This document contains individual, self-contained prompts for each remaining feature. Copy and paste each prompt into Claude Code on the Web with this GitHub repository selected.

---

## Feature #9: Note Templates

**Copy this entire section into Claude Code:**

```
I need to implement a Note Templates system for the Second Brain app. This feature should allow users to quickly create notes from pre-defined templates.

REQUIREMENTS:
1. Add a "Templates" button in the quick note modal
2. Create 5-7 useful templates (meeting notes, daily journal, project plan, book notes, etc.)
3. Template selector UI with preview
4. When selected, pre-fill the note creation form with template content
5. Save last used template preference in localStorage

IMPLEMENTATION DETAILS:

1. Location: templates/dashboard_v3.html
2. Add templates button to quick note modal (search for "showQuickNoteModal")
3. Create template data structure:
```javascript
const noteTemplates = {
    meeting: {
        name: "Meeting Notes",
        icon: "👥",
        content: "# Meeting Notes\n\n**Date:** {{date}}\n**Attendees:** \n**Topic:** \n\n## Agenda\n- \n\n## Discussion\n\n## Action Items\n- [ ] \n\n## Next Steps\n"
    },
    daily: {
        name: "Daily Journal",
        icon: "📔",
        content: "# Daily Journal - {{date}}\n\n## Morning\n**Mood:** \n**Goals for today:**\n- \n\n## Evening\n**Accomplished:**\n- \n\n**Grateful for:**\n- \n\n**Tomorrow:**\n- "
    },
    project: {
        name: "Project Plan",
        icon: "🎯",
        content: "# Project: {{title}}\n\n## Overview\n**Goal:** \n**Timeline:** \n**Status:** Planning\n\n## Objectives\n- \n\n## Milestones\n1. \n\n## Resources Needed\n- \n\n## Risks & Challenges\n- "
    },
    book: {
        name: "Book Notes",
        icon: "📚",
        content: "# Book Notes: {{title}}\n\n**Author:** \n**Genre:** \n**Rating:** ⭐⭐⭐⭐⭐\n\n## Summary\n\n## Key Takeaways\n- \n\n## Favorite Quotes\n> \n\n## My Thoughts\n"
    },
    todo: {
        name: "Task List",
        icon: "✅",
        content: "# Tasks - {{date}}\n\n## High Priority\n- [ ] \n\n## Medium Priority\n- [ ] \n\n## Low Priority\n- [ ] \n\n## Completed\n- [x] "
    }
};
```

4. Add template selector UI in quick note modal
5. Add "showTemplates()" function to display template picker
6. Add "applyTemplate(templateKey)" function to populate form
7. Replace {{date}} and {{title}} placeholders with actual values
8. Add keyboard shortcut Ctrl+T for templates

ACCEPTANCE CRITERIA:
- Templates button appears in quick note modal
- Clicking shows template picker with icons
- Selecting template fills the note content
- Date/title placeholders are replaced
- Last used template is remembered
- Ctrl+T opens template picker

FILE TO MODIFY: templates/dashboard_v3.html
SEARCH FOR: "showQuickNoteModal" and add templates UI there
ADD AFTER: The quick note content textarea

Test by creating a note with each template and verify content is pre-filled correctly.
```

---

## Feature #10: Favorites/Starred Notes

**Copy this entire section into Claude Code:**

```
I need to implement a Favorites/Starred Notes feature for the Second Brain app. Users should be able to mark important notes as favorites and filter by them.

REQUIREMENTS:
1. Add star button to note cards and note details modal
2. Add "is_favorite" field to database (migration not required, use note metadata)
3. Toggle favorite status with visual feedback
4. Add "Favorites" filter to notes view
5. Show favorite count in stats
6. Persist favorite status to database

IMPLEMENTATION DETAILS:

1. Location: templates/dashboard_v3.html

2. Add star button to note details modal header (line ~8047):
```html
<button id="favoriteNoteBtn" class="p-2 text-slate-400 hover:text-yellow-400 hover:bg-slate-800 rounded-lg transition-all" title="Favorite note">
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"></path>
    </svg>
</button>
```

3. Add JavaScript functions:
```javascript
// Initialize favorite button
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('favoriteNoteBtn')?.addEventListener('click', toggleFavorite);
});

async function toggleFavorite() {
    if (!currentEditingNote) return;

    const isFavorite = currentEditingNote.is_favorite || false;
    const newFavoriteStatus = !isFavorite;

    try {
        const response = await fetch(`/api/notes/${currentEditingNote.id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({
                title: currentEditingNote.title,
                content: currentEditingNote.content || currentEditingNote.body,
                tags: currentEditingNote.tags,
                is_favorite: newFavoriteStatus
            })
        });

        if (response.ok) {
            currentEditingNote.is_favorite = newFavoriteStatus;
            updateFavoriteButton();
            showToast(newFavoriteStatus ? 'Added to favorites' : 'Removed from favorites', 'success', 2000);
            refreshDashboardData();
        }
    } catch (error) {
        showToast('Failed to update favorite status', 'error', 3000);
    }
}

function updateFavoriteButton() {
    const btn = document.getElementById('favoriteNoteBtn');
    if (!btn || !currentEditingNote) return;

    const svg = btn.querySelector('svg');
    if (currentEditingNote.is_favorite) {
        svg.setAttribute('fill', 'currentColor');
        btn.classList.add('text-yellow-400');
        btn.classList.remove('text-slate-400');
    } else {
        svg.setAttribute('fill', 'none');
        btn.classList.remove('text-yellow-400');
        btn.classList.add('text-slate-400');
    }
}
```

4. Add favorites filter to notes view filters (line ~1140):
```html
<button id="filter-favorite" onclick="filterNotes('favorite')" class="px-3 py-1.5 text-xs font-medium rounded-lg transition-all note-filter-tab border-transparent text-slate-400">
    <span class="bg-slate-800 text-slate-300 px-2 py-0.5 rounded text-xs" id="favCount">0</span>
    Favorites
</button>
```

5. Update filterNotes function to handle 'favorite' type
6. Call updateFavoriteButton() in populateNoteDetails()

BACKEND NOTE:
The backend PUT /api/notes/{id} endpoint already supports updating arbitrary fields, so is_favorite will be stored automatically if passed.

ACCEPTANCE CRITERIA:
- Star button appears in note modal
- Clicking toggles favorite status (filled/unfilled star)
- Favorites filter shows only favorited notes
- Favorite count updates in stats
- Star state persists after refresh
- Visual feedback (toast) on toggle

FILE TO MODIFY: templates/dashboard_v3.html
SEARCH FOR: "archiveNoteBtn" to add favoriteNoteBtn nearby

Test by favoriting 3-5 notes and filtering by favorites.
```

---

## Feature #11: Markdown Preview

**Copy this entire section into Claude Code:**

```
I need to implement a Markdown Preview feature for the Second Brain app. When editing notes with markdown content, users should be able to preview the rendered markdown.

REQUIREMENTS:
1. Add "Preview" tab to note editing interface
2. Toggle between "Edit" and "Preview" modes
3. Render markdown to HTML (use marked.js library)
4. Support common markdown: headers, lists, code blocks, links, images
5. Split-screen option (edit + preview side-by-side)

IMPLEMENTATION DETAILS:

1. Location: templates/dashboard_v3.html

2. Add marked.js library to head section:
```html
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
```

3. In enterEditMode() function, add preview toggle buttons after the content textarea:
```html
<div class="mt-2 flex items-center space-x-2">
    <button type="button" id="editTab" class="px-3 py-1 text-xs bg-blue-600 text-white rounded" onclick="showEditTab()">Edit</button>
    <button type="button" id="previewTab" class="px-3 py-1 text-xs bg-slate-700 text-slate-300 rounded" onclick="showPreviewTab()">Preview</button>
    <button type="button" id="splitTab" class="px-3 py-1 text-xs bg-slate-700 text-slate-300 rounded" onclick="showSplitView()">Split</button>
</div>
<div id="markdownPreview" class="hidden mt-3 p-4 bg-slate-700 rounded-lg prose prose-invert max-w-none"></div>
```

4. Add JavaScript functions:
```javascript
let previewMode = 'edit'; // 'edit', 'preview', 'split'

function showEditTab() {
    previewMode = 'edit';
    document.getElementById('editContentInput').classList.remove('hidden');
    document.getElementById('markdownPreview').classList.add('hidden');
    document.getElementById('editTab').classList.add('bg-blue-600', 'text-white');
    document.getElementById('editTab').classList.remove('bg-slate-700', 'text-slate-300');
    document.getElementById('previewTab').classList.remove('bg-blue-600', 'text-white');
    document.getElementById('previewTab').classList.add('bg-slate-700', 'text-slate-300');
    document.getElementById('splitTab').classList.remove('bg-blue-600', 'text-white');
    document.getElementById('splitTab').classList.add('bg-slate-700', 'text-slate-300');
}

function showPreviewTab() {
    previewMode = 'preview';
    updateMarkdownPreview();
    document.getElementById('editContentInput').classList.add('hidden');
    document.getElementById('markdownPreview').classList.remove('hidden');
    document.getElementById('previewTab').classList.add('bg-blue-600', 'text-white');
    document.getElementById('previewTab').classList.remove('bg-slate-700', 'text-slate-300');
    document.getElementById('editTab').classList.remove('bg-blue-600', 'text-white');
    document.getElementById('editTab').classList.add('bg-slate-700', 'text-slate-300');
    document.getElementById('splitTab').classList.remove('bg-blue-600', 'text-white');
    document.getElementById('splitTab').classList.add('bg-slate-700', 'text-slate-300');
}

function showSplitView() {
    previewMode = 'split';
    updateMarkdownPreview();
    document.getElementById('editContentInput').classList.remove('hidden');
    document.getElementById('markdownPreview').classList.remove('hidden');
    document.getElementById('splitTab').classList.add('bg-blue-600', 'text-white');
    document.getElementById('splitTab').classList.remove('bg-slate-700', 'text-slate-300');
    document.getElementById('editTab').classList.remove('bg-blue-600', 'text-white');
    document.getElementById('editTab').classList.add('bg-slate-700', 'text-slate-300');
    document.getElementById('previewTab').classList.remove('bg-blue-600', 'text-white');
    document.getElementById('previewTab').classList.add('bg-slate-700', 'text-slate-300');
}

function updateMarkdownPreview() {
    const textarea = document.getElementById('editContentInput');
    const preview = document.getElementById('markdownPreview');
    if (!textarea || !preview) return;

    const markdownText = textarea.value;
    const html = marked.parse(markdownText);
    preview.innerHTML = html;
}

// Update preview on typing (debounced)
let previewDebounceTimer;
document.addEventListener('input', (e) => {
    if (e.target.id === 'editContentInput' && previewMode !== 'edit') {
        clearTimeout(previewDebounceTimer);
        previewDebounceTimer = setTimeout(updateMarkdownPreview, 300);
    }
});
```

5. Add Tailwind prose styles for markdown rendering (already in project)

ACCEPTANCE CRITERIA:
- Preview button appears when editing notes
- Switching to Preview shows rendered markdown
- Headers, lists, bold, italic, code blocks render correctly
- Split view shows edit and preview side-by-side
- Preview updates as you type (with debounce)
- Tab switching works smoothly

FILE TO MODIFY: templates/dashboard_v3.html
ADD LIBRARY: marked.js CDN link in <head>
SEARCH FOR: "editContentInput" to add preview UI

Test by editing a note with markdown and toggling between Edit/Preview/Split views.
```

---

## Feature #12: Drag & Drop File Upload

**Copy this entire section into Claude Code:**

```
I need to implement Drag & Drop File Upload for the Second Brain app. Users should be able to drag files from their desktop directly into the dashboard to create notes.

REQUIREMENTS:
1. Add drag-and-drop zone overlay when dragging files over window
2. Support multiple file types: images, PDFs, audio, text files
3. Visual feedback during drag (highlight drop zone)
4. Upload progress indicator
5. Handle multiple files at once
6. Create notes automatically from dropped files

IMPLEMENTATION DETAILS:

1. Location: templates/dashboard_v3.html

2. Add drop zone overlay HTML (add after main content div, around line ~1200):
```html
<!-- Drag & Drop Overlay -->
<div id="dropZoneOverlay" class="fixed inset-0 bg-blue-900 bg-opacity-90 backdrop-blur-sm z-50 hidden flex items-center justify-center">
    <div class="text-center text-white">
        <svg class="w-24 h-24 mx-auto mb-4 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
        </svg>
        <h2 class="text-3xl font-bold mb-2">Drop files to upload</h2>
        <p class="text-lg text-blue-200">Images, PDFs, Audio, and Text files supported</p>
    </div>
</div>
```

3. Add JavaScript for drag and drop handling:
```javascript
// Drag and Drop File Upload
document.addEventListener('DOMContentLoaded', () => {
    initializeDragAndDrop();
});

function initializeDragAndDrop() {
    const dropZone = document.getElementById('dropZoneOverlay');
    let dragCounter = 0;

    // Prevent default drag behaviors
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        document.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    // Show drop zone when dragging files over window
    document.addEventListener('dragenter', (e) => {
        dragCounter++;
        if (e.dataTransfer.types.includes('Files')) {
            dropZone.classList.remove('hidden');
        }
    });

    document.addEventListener('dragleave', (e) => {
        dragCounter--;
        if (dragCounter === 0) {
            dropZone.classList.add('hidden');
        }
    });

    // Handle file drop
    document.addEventListener('drop', async (e) => {
        dragCounter = 0;
        dropZone.classList.add('hidden');

        const files = Array.from(e.dataTransfer.files);
        if (files.length === 0) return;

        console.log('Files dropped:', files);
        showToast(`Uploading ${files.length} file(s)...`, 'info', 3000);

        // Upload files one by one
        for (const file of files) {
            await uploadDroppedFile(file);
        }

        showToast(`Successfully uploaded ${files.length} file(s)`, 'success', 3000);
        refreshDashboardData();
    });
}

async function uploadDroppedFile(file) {
    const formData = new FormData();

    // Determine file type and use appropriate endpoint
    if (file.type.startsWith('audio/')) {
        formData.append('file', file);
        formData.append('tags', 'dropped, audio');

        const response = await fetch('/webhook/audio', {
            method: 'POST',
            credentials: 'include',
            body: formData
        });

        return response.ok;
    } else if (file.type.startsWith('image/')) {
        formData.append('file', file);
        formData.append('content', `Image: ${file.name}`);
        formData.append('tags', 'dropped, image');

        const response = await fetch('/capture', {
            method: 'POST',
            credentials: 'include',
            body: formData
        });

        return response.ok;
    } else if (file.type === 'application/pdf') {
        formData.append('file', file);
        formData.append('content', `PDF: ${file.name}`);
        formData.append('tags', 'dropped, pdf');

        const response = await fetch('/capture', {
            method: 'POST',
            credentials: 'include',
            body: formData
        });

        return response.ok;
    } else if (file.type.startsWith('text/')) {
        // Read text file content
        const text = await file.text();

        const response = await fetch('/api/notes', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({
                title: file.name,
                content: text,
                tags: 'dropped, text'
            })
        });

        return response.ok;
    } else {
        console.warn('Unsupported file type:', file.type);
        return false;
    }
}
```

ACCEPTANCE CRITERIA:
- Dragging files over window shows blue overlay
- Drop zone has clear visual feedback
- Supported file types upload successfully
- Multiple files can be dropped at once
- Progress toast shows during upload
- Success toast after completion
- Dashboard refreshes to show new notes
- Unsupported files are skipped with warning

FILE TO MODIFY: templates/dashboard_v3.html
ADD HTML: Drop zone overlay after main content
ADD JS: Drag and drop event handlers

Test by dragging: an image, a PDF, an audio file, and a text file onto the dashboard.
```

---

## Feature #13: Note Duplication

**Copy this entire section into Claude Code:**

```
I need to implement a Note Duplication feature for the Second Brain app. Users should be able to quickly duplicate existing notes.

REQUIREMENTS:
1. Add "Duplicate" button to note details modal
2. Create copy with "(Copy)" suffix in title
3. Preserve all content, tags, and metadata
4. Open duplicated note immediately
5. Show success toast with link to new note
6. Add to quick actions menu

IMPLEMENTATION DETAILS:

1. Location: templates/dashboard_v3.html

2. Add duplicate button to note modal header (after export button, line ~8059):
```html
<button id="duplicateNoteBtn" class="p-2 text-slate-400 hover:text-purple-400 hover:bg-slate-800 rounded-lg transition-all" title="Duplicate note">
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
    </svg>
</button>
```

3. Add JavaScript function:
```javascript
// Initialize duplicate button
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('duplicateNoteBtn')?.addEventListener('click', duplicateCurrentNote);
});

async function duplicateCurrentNote() {
    if (!currentEditingNote) {
        showToast('No note selected', 'error', 2000);
        return;
    }

    try {
        console.log('Duplicating note:', currentEditingNote.id);

        // Create new note with same content
        const duplicateData = {
            title: `${currentEditingNote.title || 'Untitled'} (Copy)`,
            content: currentEditingNote.content || currentEditingNote.body || '',
            tags: currentEditingNote.tags || ''
        };

        // Show loading state
        showToast('Duplicating note...', 'info', 2000);

        const response = await fetch('/api/notes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify(duplicateData)
        });

        if (!response.ok) {
            throw new Error(`Failed to duplicate note: ${response.status}`);
        }

        const newNote = await response.json();
        console.log('Note duplicated successfully:', newNote);

        // Close current note modal
        closeNoteDetails();

        // Refresh dashboard
        await refreshDashboardData();

        // Show success message with option to open new note
        showToast('Note duplicated successfully!', 'success', 3000);

        // Open the new note after a brief delay
        setTimeout(() => {
            if (newNote.id) {
                openNoteDetails(newNote.id);
            }
        }, 500);

    } catch (error) {
        console.error('Error duplicating note:', error);
        showToast(`Failed to duplicate note: ${error.message}`, 'error', 5000);
    }
}

// Keyboard shortcut: Ctrl+D to duplicate
// Add to keyboard shortcuts handler:
// if ((event.ctrlKey || event.metaKey) && event.key === 'd' && !isTyping) {
//     event.preventDefault();
//     const noteModal = document.getElementById('noteDetailsModal');
//     if (noteModal && !noteModal.classList.contains('hidden') && currentEditingNote) {
//         duplicateCurrentNote();
//     }
//     return;
// }
```

4. Add Ctrl+D keyboard shortcut in global keyboard shortcuts section (line ~4596):
Add this case:
```javascript
// Ctrl/Cmd + D - Duplicate current note (when viewing)
if ((event.ctrlKey || event.metaKey) && event.key === 'd' && !isTyping) {
    event.preventDefault();
    const noteModal = document.getElementById('noteDetailsModal');
    if (noteModal && !noteModal.classList.contains('hidden') && currentEditingNote) {
        duplicateCurrentNote();
    }
    return;
}
```

ACCEPTANCE CRITERIA:
- Duplicate button appears in note modal
- Clicking creates copy with "(Copy)" suffix
- All content is preserved exactly
- Tags are copied
- New note opens automatically
- Success toast appears
- Ctrl+D keyboard shortcut works
- Dashboard refreshes to show new note

FILE TO MODIFY: templates/dashboard_v3.html
SEARCH FOR: "exportNoteBtn" to add duplicateNoteBtn nearby
SEARCH FOR: "Ctrl/Cmd + Delete" to add Ctrl+D shortcut

Test by duplicating notes with content, tags, and various types.
```

---

## Feature #14: Quick Stats Dashboard Widget

**Copy this entire section into Claude Code:**

```
I need to implement a Quick Stats Dashboard Widget for the Second Brain app. This should show key metrics at a glance in a compact widget.

REQUIREMENTS:
1. Add collapsible stats widget to main dashboard
2. Show: Total notes, notes this week, most used tag, average per day
3. Mini sparkline chart for note creation trend
4. Color-coded progress bars
5. Click to expand/collapse
6. Persist expanded state

IMPLEMENTATION DETAILS:

1. Location: templates/dashboard_v3.html

2. Add quick stats widget HTML (insert in main content area, around line ~1000):
```html
<!-- Quick Stats Widget -->
<div id="quickStatsWidget" class="mb-4 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl shadow-lg overflow-hidden">
    <div class="p-4 cursor-pointer" onclick="toggleQuickStats()">
        <div class="flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="bg-white bg-opacity-20 rounded-lg p-2">
                    <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
                    </svg>
                </div>
                <div class="text-white">
                    <h3 class="font-bold text-lg">Quick Stats</h3>
                    <p class="text-sm text-blue-100" id="quickStatsSubtext">Your knowledge at a glance</p>
                </div>
            </div>
            <svg id="quickStatsChevron" class="w-5 h-5 text-white transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
            </svg>
        </div>
    </div>

    <div id="quickStatsContent" class="px-4 pb-4 space-y-3">
        <!-- Total Notes -->
        <div class="bg-white bg-opacity-10 rounded-lg p-3">
            <div class="flex items-center justify-between mb-2">
                <span class="text-blue-100 text-sm">Total Notes</span>
                <span class="text-white font-bold text-xl" id="qsTotalNotes">0</span>
            </div>
            <div class="w-full bg-white bg-opacity-20 rounded-full h-2">
                <div id="qsTotalNotesBar" class="bg-white h-2 rounded-full transition-all" style="width: 0%"></div>
            </div>
        </div>

        <!-- This Week -->
        <div class="bg-white bg-opacity-10 rounded-lg p-3">
            <div class="flex items-center justify-between mb-2">
                <span class="text-blue-100 text-sm">This Week</span>
                <span class="text-white font-bold text-xl" id="qsThisWeek">0</span>
            </div>
            <div class="w-full bg-white bg-opacity-20 rounded-full h-2">
                <div id="qsThisWeekBar" class="bg-green-400 h-2 rounded-full transition-all" style="width: 0%"></div>
            </div>
        </div>

        <!-- Top Tag -->
        <div class="bg-white bg-opacity-10 rounded-lg p-3">
            <div class="flex items-center justify-between">
                <span class="text-blue-100 text-sm">Most Used Tag</span>
                <span class="text-white font-semibold" id="qsTopTag">-</span>
            </div>
        </div>

        <!-- Average per Day -->
        <div class="bg-white bg-opacity-10 rounded-lg p-3">
            <div class="flex items-center justify-between">
                <span class="text-blue-100 text-sm">Avg per Day</span>
                <span class="text-white font-bold text-xl" id="qsAvgPerDay">0</span>
            </div>
        </div>
    </div>
</div>
```

3. Add JavaScript functions:
```javascript
// Quick Stats Widget
let quickStatsExpanded = localStorage.getItem('quickStatsExpanded') !== 'false';

document.addEventListener('DOMContentLoaded', () => {
    initializeQuickStats();
    loadQuickStats();
});

function initializeQuickStats() {
    const content = document.getElementById('quickStatsContent');
    const chevron = document.getElementById('quickStatsChevron');

    if (quickStatsExpanded) {
        content.classList.remove('hidden');
        chevron.style.transform = 'rotate(180deg)';
    } else {
        content.classList.add('hidden');
        chevron.style.transform = 'rotate(0deg)';
    }
}

function toggleQuickStats() {
    quickStatsExpanded = !quickStatsExpanded;
    localStorage.setItem('quickStatsExpanded', quickStatsExpanded);

    const content = document.getElementById('quickStatsContent');
    const chevron = document.getElementById('quickStatsChevron');

    if (quickStatsExpanded) {
        content.classList.remove('hidden');
        chevron.style.transform = 'rotate(180deg)';
    } else {
        content.classList.add('hidden');
        chevron.style.transform = 'rotate(0deg)';
    }
}

async function loadQuickStats() {
    try {
        // Use existing analytics endpoint
        const response = await fetch('/api/analytics', {
            credentials: 'include'
        });

        if (!response.ok) return;

        const data = await response.json();

        // Update stats
        document.getElementById('qsTotalNotes').textContent = data.total_notes || 0;
        document.getElementById('qsThisWeek').textContent = data.this_week || 0;
        document.getElementById('qsAvgPerDay').textContent = (data.avg_notes_per_day || 0).toFixed(1);

        // Top tag
        if (data.popular_tags && data.popular_tags.length > 0) {
            document.getElementById('qsTopTag').textContent = data.popular_tags[0].tag;
        }

        // Progress bars (example: max 100 notes for total, 20 for week)
        const totalPercent = Math.min((data.total_notes / 100) * 100, 100);
        const weekPercent = Math.min((data.this_week / 20) * 100, 100);

        document.getElementById('qsTotalNotesBar').style.width = totalPercent + '%';
        document.getElementById('qsThisWeekBar').style.width = weekPercent + '%';

        // Update subtext
        const subtext = `${data.this_week || 0} notes this week`;
        document.getElementById('quickStatsSubtext').textContent = subtext;

    } catch (error) {
        console.error('Error loading quick stats:', error);
    }
}

// Refresh quick stats when dashboard refreshes
// Add to refreshDashboardData(): loadQuickStats();
```

4. Update refreshDashboardData() to include loadQuickStats()

ACCEPTANCE CRITERIA:
- Widget appears at top of dashboard
- Shows total notes, weekly count, top tag, avg per day
- Click to expand/collapse
- Expanded state persists across sessions
- Progress bars animate on load
- Stats update when dashboard refreshes
- Gradient background looks professional

FILE TO MODIFY: templates/dashboard_v3.html
ADD HTML: Quick stats widget in main content area
ADD JS: Quick stats functions
UPDATE: refreshDashboardData() to call loadQuickStats()

Test by viewing dashboard, collapsing/expanding widget, and refreshing page.
```

---

## Feature #15-25: Additional Features

Due to length constraints, here are abbreviated prompts for the remaining features. Each follows the same structure as above.

### Feature #15: Copy Note Link/ID
```
Add a "Copy Link" button to note modal that copies note URL to clipboard. Use Clipboard API. Show toast on copy. Add Ctrl+Shift+C shortcut.
```

### Feature #16: Character/Word Counter
```
Add live character and word counter to note editing textarea. Show "X characters, Y words" below textarea. Update on input with debounce.
```

### Feature #17: Auto-save Draft
```
Auto-save note content to localStorage every 30 seconds while editing. Restore draft on reload. Show "Draft saved" indicator. Clear on successful save.
```

### Feature #18: Pin Notes to Top
```
Add pin button to notes. Pinned notes appear first in list with pin icon. Store in note metadata. Toggle pin with button click.
```

### Feature #19: Note Version History
```
Store version snapshots when saving notes. Add "History" button to view previous versions. Show diff comparison. Restore previous version option.
```

### Feature #20: Color Labels/Categories
```
Add color picker to note modal. Assign colors (red, blue, green, yellow, purple). Show colored dot on note cards. Filter by color.
```

### Feature #21: Quick Actions Menu
```
Add context menu on right-click for notes. Show: Edit, Duplicate, Archive, Delete, Export, Star. Position menu at cursor. Close on click away.
```

### Feature #22: Batch Tag Editor
```
Enhanced bulk tag UI with tag picker. Show current tags across selected notes. Add/remove tags with checkboxes. Apply changes in batch.
```

### Feature #23: Export All Notes
```
Add "Export All" button in settings. Choose format (JSON, CSV, Markdown ZIP). Generate download with all notes. Show progress bar.
```

### Feature #24: Markdown Live Preview Toolbar
```
Add formatting toolbar above textarea: Bold, Italic, Link, Code, List buttons. Insert markdown syntax at cursor. Preview updates live.
```

### Feature #25: Note Search Within Note
```
Add Ctrl+F when viewing note to search within content. Highlight matches. Next/Previous buttons. Match counter.
```

---

## Implementation Tips

For each feature:
1. Read the entire prompt carefully
2. Check the file locations mentioned
3. Follow the code patterns shown
4. Test thoroughly after implementation
5. Commit with descriptive message

All features build on existing code and follow established patterns in the codebase.
