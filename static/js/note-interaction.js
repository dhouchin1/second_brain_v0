/**
 * Advanced Note Interaction System
 * Provides professional note editing experience with auto-save, tag management, and rich interactions
 */

class NoteInteraction {
  constructor(options = {}) {
    this.noteId = options.noteId;
    this.noteTitle = options.noteTitle || '';
    this.noteContent = options.noteContent || '';
    this.noteTags = options.noteTags || '';
    this.audioFilename = options.audioFilename || null;
    
    this.isEditing = false;
    this.autoSaveTimeout = null;
    this.autoSaveDelay = 2000; // 2 seconds
    this.lastSaved = new Date();
    this.unsavedChanges = false;
    
    this.quillEditor = null;
    this.waveform = null;
    this.allTags = [];
    
    this.initialize();
  }
  
  initialize() {
    this.setupEventListeners();
    this.loadTagSuggestions();
    this.setupKeyboardShortcuts();
    this.initializeAudioPlayer();
    this.updateWordCount();
    this.startAutoSaveIndicator();
  }
  
  setupEventListeners() {
    // Edit toggle
    const editToggle = document.getElementById('editToggle');
    if (editToggle) {
      editToggle.addEventListener('click', () => this.toggleEdit());
    }
    
    // Save form
    const noteForm = document.getElementById('noteEditForm');
    if (noteForm) {
      noteForm.addEventListener('submit', (e) => this.handleSave(e));
    }
    
    // Cancel edit
    const cancelEdit = document.getElementById('cancelEdit');
    if (cancelEdit) {
      cancelEdit.addEventListener('click', () => this.cancelEdit());
    }
    
    // Delete modal
    const deleteBtn = document.getElementById('deleteBtn');
    const deleteModal = document.getElementById('deleteModal');
    const confirmDelete = document.getElementById('confirmDelete');
    const cancelDelete = document.getElementById('cancelDelete');
    
    if (deleteBtn) {
      deleteBtn.addEventListener('click', () => this.showModal('deleteModal'));
    }
    if (confirmDelete) {
      confirmDelete.addEventListener('click', () => this.deleteNote());
    }
    if (cancelDelete) {
      cancelDelete.addEventListener('click', () => this.hideModal('deleteModal'));
    }
    
    // Export modal
    const exportBtn = document.getElementById('exportBtn');
    const exportModal = document.getElementById('exportModal');
    const cancelExport = document.getElementById('cancelExport');
    
    if (exportBtn) {
      exportBtn.addEventListener('click', () => this.showModal('exportModal'));
    }
    if (cancelExport) {
      cancelExport.addEventListener('click', () => this.hideModal('exportModal'));
    }
    
    // Export options
    const exportOptions = document.querySelectorAll('.export-option');
    exportOptions.forEach(option => {
      option.addEventListener('click', (e) => {
        const format = e.currentTarget.dataset.format;
        this.exportNote(format);
        this.hideModal('exportModal');
      });
    });
    
    // Other action buttons
    const shareBtn = document.getElementById('shareBtn');
    const duplicateBtn = document.getElementById('duplicateBtn');
    const obsidianSync = document.getElementById('obsidianSync');
    const exportMarkdown = document.getElementById('exportMarkdown');
    
    if (shareBtn) {
      shareBtn.addEventListener('click', () => this.shareNote());
    }
    if (duplicateBtn) {
      duplicateBtn.addEventListener('click', () => this.duplicateNote());
    }
    if (obsidianSync) {
      obsidianSync.addEventListener('click', () => this.syncToObsidian());
    }
    if (exportMarkdown) {
      exportMarkdown.addEventListener('click', () => this.exportNote('markdown'));
    }
    
    // Tag autocomplete
    const tagInput = document.getElementById('editTags');
    if (tagInput) {
      tagInput.addEventListener('input', (e) => this.handleTagInput(e));
      tagInput.addEventListener('keydown', (e) => this.handleTagKeydown(e));
      tagInput.addEventListener('blur', () => this.hideTagSuggestions());
    }
    
    // Title input for auto-save
    const titleInput = document.getElementById('editTitle');
    if (titleInput) {
      titleInput.addEventListener('input', () => this.scheduleAutoSave());
    }
    
    // Close modals on backdrop click
    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('modal-overlay')) {
        this.hideModal(e.target.id);
      }
    });
    
    // Prevent accidental page close with unsaved changes
    window.addEventListener('beforeunload', (e) => {
      if (this.unsavedChanges && this.isEditing) {
        e.preventDefault();
        e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
        return e.returnValue;
      }
    });
  }
  
  setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      // Ctrl/Cmd + S to save
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        if (this.isEditing) {
          this.handleSave(e);
        }
      }
      
      // Ctrl/Cmd + E to toggle edit
      if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
        e.preventDefault();
        this.toggleEdit();
      }
      
      // Escape to cancel edit or close modals
      if (e.key === 'Escape') {
        const openModal = document.querySelector('.modal-overlay.show');
        if (openModal) {
          this.hideModal(openModal.id);
        } else if (this.isEditing) {
          this.cancelEdit();
        }
      }
      
      // Ctrl/Cmd + Shift + D to duplicate
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D') {
        e.preventDefault();
        this.duplicateNote();
      }
      
      // Ctrl/Cmd + Shift + E to export
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'E') {
        e.preventDefault();
        this.showModal('exportModal');
      }
    });
  }
  
  async loadTagSuggestions() {
    try {
      const response = await fetch('/api/tags');
      if (response.ok) {
        this.allTags = await response.json();
      }
    } catch (error) {
      console.error('Failed to load tag suggestions:', error);
    }
  }
  
  handleTagInput(e) {
    const input = e.target.value;
    const lastCommaIndex = input.lastIndexOf(',');
    const currentTag = input.substring(lastCommaIndex + 1).trim().toLowerCase();
    
    if (currentTag.length > 0) {
      const suggestions = this.allTags.filter(tag => 
        tag.toLowerCase().includes(currentTag) && 
        !input.toLowerCase().includes(tag.toLowerCase())
      ).slice(0, 8);
      
      this.showTagSuggestions(suggestions);
    } else {
      this.hideTagSuggestions();
    }
    
    this.scheduleAutoSave();
  }
  
  handleTagKeydown(e) {
    const suggestions = document.getElementById('tagSuggestions');
    const selectedSuggestion = suggestions.querySelector('.selected');
    
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = selectedSuggestion ? selectedSuggestion.nextElementSibling : suggestions.firstElementChild;
      if (next) {
        if (selectedSuggestion) selectedSuggestion.classList.remove('selected');
        next.classList.add('selected');
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prev = selectedSuggestion ? selectedSuggestion.previousElementSibling : suggestions.lastElementChild;
      if (prev) {
        if (selectedSuggestion) selectedSuggestion.classList.remove('selected');
        prev.classList.add('selected');
      }
    } else if (e.key === 'Enter' && selectedSuggestion) {
      e.preventDefault();
      this.selectTag(selectedSuggestion.textContent);
    } else if (e.key === 'Escape') {
      this.hideTagSuggestions();
    }
  }
  
  showTagSuggestions(suggestions) {
    const suggestionsContainer = document.getElementById('tagSuggestions');
    if (!suggestionsContainer) return;
    
    suggestionsContainer.innerHTML = suggestions.map(tag => 
      `<div class="tag-suggestion">${tag}</div>`
    ).join('');
    
    suggestionsContainer.style.display = suggestions.length > 0 ? 'block' : 'none';
    
    // Add click listeners
    suggestionsContainer.querySelectorAll('.tag-suggestion').forEach(suggestion => {
      suggestion.addEventListener('click', () => this.selectTag(suggestion.textContent));
    });
  }
  
  selectTag(tag) {
    const tagInput = document.getElementById('editTags');
    if (!tagInput) return;
    
    const currentValue = tagInput.value;
    const lastCommaIndex = currentValue.lastIndexOf(',');
    const newValue = lastCommaIndex >= 0 
      ? currentValue.substring(0, lastCommaIndex + 1) + ' ' + tag + ', '
      : tag + ', ';
    
    tagInput.value = newValue;
    this.hideTagSuggestions();
    tagInput.focus();
    this.scheduleAutoSave();
  }
  
  hideTagSuggestions() {
    const suggestions = document.getElementById('tagSuggestions');
    if (suggestions) {
      suggestions.style.display = 'none';
    }
  }
  
  initializeAudioPlayer() {
    if (!this.audioFilename) return;
    
    try {
      const waveformContainer = document.getElementById('waveform');
      if (!waveformContainer) return;
      
      // Initialize WaveSurfer
      this.waveform = WaveSurfer.create({
        container: '#waveform',
        waveColor: 'var(--color-primary-400)',
        progressColor: 'var(--color-primary-600)',
        height: 80,
        responsive: true,
        normalize: true,
        backend: 'WebAudio',
        barWidth: 2,
        barRadius: 1,
        cursorWidth: 2,
        cursorColor: 'var(--color-primary-600)'
      });
      
      // Hide loading indicator when ready
      this.waveform.on('ready', () => {
        const loading = waveformContainer.querySelector('.waveform-loading');
        if (loading) {
          loading.style.display = 'none';
        }
      });
      
      // Show error state if loading fails
      this.waveform.on('error', (error) => {
        console.error('Waveform loading error:', error);
        const loading = waveformContainer.querySelector('.waveform-loading');
        if (loading) {
          loading.innerHTML = '<span style="color: var(--color-error-500);">Failed to load audio</span>';
        }
      });
      
      this.waveform.load(`/audio/${this.audioFilename}`);
      
      // Setup audio controls
      const playPauseBtn = document.getElementById('playPauseBtn');
      const playIcon = playPauseBtn.querySelector('i');
      const playText = playPauseBtn.querySelector('span');
      
      playPauseBtn.addEventListener('click', () => {
        if (this.waveform.isPlaying()) {
          this.waveform.pause();
          playIcon.setAttribute('data-lucide', 'play');
          playText.textContent = 'Play';
        } else {
          this.waveform.play();
          playIcon.setAttribute('data-lucide', 'pause');
          playText.textContent = 'Pause';
        }
        lucide.createIcons();
      });
      
      // Playback speed control
      const speedSelect = document.getElementById('playbackSpeed');
      if (speedSelect) {
        speedSelect.addEventListener('change', (e) => {
          this.waveform.setPlaybackRate(parseFloat(e.target.value));
        });
      }
      
      // Time updates
      this.waveform.on('audioprocess', () => this.updateAudioTime());
      this.waveform.on('ready', () => {
        const duration = this.waveform.getDuration();
        document.getElementById('totalTime').textContent = this.formatTime(duration);
      });
      
    } catch (error) {
      console.error('Failed to initialize audio player:', error);
      // Fallback to basic HTML5 audio
      this.initializeFallbackAudio();
    }
  }
  
  initializeFallbackAudio() {
    const waveformContainer = document.getElementById('waveform');
    if (waveformContainer) {
      waveformContainer.innerHTML = `
        <audio controls style="width: 100%; border-radius: var(--radius-md);">
          <source src="/audio/${this.audioFilename}" type="audio/wav">
          Your browser does not support audio playback.
        </audio>
      `;
    }
  }
  
  updateAudioTime() {
    if (!this.waveform) return;
    
    const current = this.waveform.getCurrentTime();
    document.getElementById('currentTime').textContent = this.formatTime(current);
  }
  
  formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }
  
  toggleEdit() {
    if (this.isEditing) {
      this.cancelEdit();
    } else {
      this.enterEditMode();
    }
  }
  
  enterEditMode() {
    this.isEditing = true;
    document.body.className = 'min-h-screen edit-mode';
    
    // Update button text
    const editToggle = document.getElementById('editToggle');
    const editText = editToggle.querySelector('.edit-text');
    const editIcon = editToggle.querySelector('i');
    
    if (editText) editText.textContent = 'Cancel';
    if (editIcon) {
      editIcon.setAttribute('data-lucide', 'x');
      lucide.createIcons();
    }
    
    // Initialize Quill editor
    this.initializeQuillEditor();
    
    // Focus on title
    const titleInput = document.getElementById('editTitle');
    if (titleInput) {
      setTimeout(() => titleInput.focus(), 100);
    }
  }
  
  initializeQuillEditor() {
    if (this.quillEditor) {
      this.quillEditor.root.innerHTML = this.noteContent || '';
      return;
    }
    
    // Quill toolbar configuration
    const toolbarOptions = [
      [{ 'header': [1, 2, 3, false] }],
      ['bold', 'italic', 'underline', 'strike'],
      [{ 'list': 'ordered'}, { 'list': 'bullet' }],
      ['blockquote', 'code-block'],
      [{ 'color': [] }, { 'background': [] }],
      ['link'],
      ['clean']
    ];
    
    this.quillEditor = new Quill('#editor', {
      theme: 'snow',
      modules: {
        toolbar: toolbarOptions
      },
      placeholder: 'Write your note content here...'
    });
    
    // Set initial content
    this.quillEditor.root.innerHTML = this.noteContent || '';
    
    // Setup auto-save on content change
    this.quillEditor.on('text-change', () => {
      this.scheduleAutoSave();
      this.updateWordCount();
    });
  }
  
  updateWordCount() {
    const wordCountElement = document.getElementById('wordCount');
    if (!wordCountElement) return;
    
    let text = '';
    if (this.isEditing && this.quillEditor) {
      text = this.quillEditor.getText();
    } else {
      // Get text from visible content
      const contentDiv = document.querySelector('.note-content');
      if (contentDiv) {
        text = contentDiv.textContent || '';
      }
    }
    
    const wordCount = text.trim().split(/\s+/).filter(word => word.length > 0).length;
    wordCountElement.textContent = `${wordCount} words`;
  }
  
  cancelEdit() {
    if (this.unsavedChanges) {
      if (!confirm('You have unsaved changes. Are you sure you want to cancel?')) {
        return;
      }
    }
    
    this.isEditing = false;
    this.unsavedChanges = false;
    document.body.className = 'min-h-screen view-mode';
    
    // Update button text
    const editToggle = document.getElementById('editToggle');
    const editText = editToggle.querySelector('.edit-text');
    const editIcon = editToggle.querySelector('i');
    
    if (editText) editText.textContent = 'Edit';
    if (editIcon) {
      editIcon.setAttribute('data-lucide', 'edit-3');
      lucide.createIcons();
    }
    
    // Reset form values
    this.resetForm();
  }
  
  resetForm() {
    const titleInput = document.getElementById('editTitle');
    const tagsInput = document.getElementById('editTags');
    
    if (titleInput) titleInput.value = this.noteTitle;
    if (tagsInput) tagsInput.value = this.noteTags || '';
    if (this.quillEditor) {
      this.quillEditor.root.innerHTML = this.noteContent || '';
    }
  }
  
  scheduleAutoSave() {
    this.unsavedChanges = true;
    
    if (this.autoSaveTimeout) {
      clearTimeout(this.autoSaveTimeout);
    }
    
    this.autoSaveTimeout = setTimeout(() => {
      this.performAutoSave();
    }, this.autoSaveDelay);
  }
  
  async performAutoSave() {
    if (!this.isEditing || !this.unsavedChanges) return;
    
    try {
      const data = this.getCurrentFormData();
      
      const response = await fetch(`/api/notes/${this.noteId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
      
      if (response.ok) {
        this.unsavedChanges = false;
        this.lastSaved = new Date();
        this.showAutoSaveIndicator();
        this.updateLastSavedTime();
      }
    } catch (error) {
      console.error('Auto-save failed:', error);
    }
  }
  
  getCurrentFormData() {
    const titleInput = document.getElementById('editTitle');
    const tagsInput = document.getElementById('editTags');
    
    return {
      title: titleInput ? titleInput.value : this.noteTitle,
      content: this.quillEditor ? this.quillEditor.root.innerHTML : this.noteContent,
      tags: tagsInput ? tagsInput.value : this.noteTags
    };
  }
  
  async handleSave(e) {
    e.preventDefault();
    
    try {
      const data = this.getCurrentFormData();
      
      const response = await fetch(`/api/notes/${this.noteId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
      
      if (response.ok) {
        // Update stored values
        this.noteTitle = data.title;
        this.noteContent = data.content;
        this.noteTags = data.tags;
        this.unsavedChanges = false;
        this.lastSaved = new Date();
        
        // Update page display
        this.updatePageDisplay();
        this.showAutoSaveIndicator('Changes saved successfully!');
        
        // Exit edit mode
        this.isEditing = false;
        document.body.className = 'min-h-screen view-mode';
        
        // Update button
        const editToggle = document.getElementById('editToggle');
        const editText = editToggle.querySelector('.edit-text');
        const editIcon = editToggle.querySelector('i');
        
        if (editText) editText.textContent = 'Edit';
        if (editIcon) {
          editIcon.setAttribute('data-lucide', 'edit-3');
          lucide.createIcons();
        }
        
      } else {
        throw new Error('Failed to save note');
      }
    } catch (error) {
      console.error('Save failed:', error);
      alert('Failed to save note. Please try again.');
    }
  }
  
  updatePageDisplay() {
    // Update title
    const titleElement = document.getElementById('noteTitle');
    if (titleElement) {
      titleElement.textContent = this.noteTitle;
    }
    
    // Update content display (this would need server-side rendering for proper formatting)
    // For now, we'll just update word count
    this.updateWordCount();
  }
  
  showAutoSaveIndicator(message = 'Saved') {
    const indicator = document.getElementById('autoSaveIndicator');
    if (indicator) {
      indicator.querySelector('span').textContent = message;
      indicator.classList.add('show');
      
      setTimeout(() => {
        indicator.classList.remove('show');
      }, 2000);
    }
  }
  
  updateLastSavedTime() {
    const lastSavedElement = document.getElementById('lastSaved');
    if (lastSavedElement) {
      const now = new Date();
      const diff = now - this.lastSaved;
      
      if (diff < 60000) {
        lastSavedElement.textContent = 'Just now';
      } else if (diff < 3600000) {
        const minutes = Math.floor(diff / 60000);
        lastSavedElement.textContent = `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
      } else {
        lastSavedElement.textContent = this.lastSaved.toLocaleTimeString();
      }
    }
  }
  
  startAutoSaveIndicator() {
    // Update "last saved" time every minute
    setInterval(() => this.updateLastSavedTime(), 60000);
  }
  
  showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.add('show');
      // Focus first focusable element
      const focusable = modal.querySelector('button, input, textarea, select');
      if (focusable) focusable.focus();
    }
  }
  
  hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.remove('show');
    }
  }
  
  async deleteNote() {
    try {
      const response = await fetch(`/api/notes/${this.noteId}`, {
        method: 'DELETE'
      });
      
      if (response.ok) {
        // Redirect to dashboard
        window.location.href = '/';
      } else {
        throw new Error('Failed to delete note');
      }
    } catch (error) {
      console.error('Delete failed:', error);
      alert('Failed to delete note. Please try again.');
    }
    
    this.hideModal('deleteModal');
  }
  
  async exportNote(format) {
    try {
      const response = await fetch(`/api/notes/${this.noteId}/export?format=${format}`);
      
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = `${this.noteTitle || 'note'}.${format}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } else {
        throw new Error('Failed to export note');
      }
    } catch (error) {
      console.error('Export failed:', error);
      alert('Failed to export note. Please try again.');
    }
  }
  
  async shareNote() {
    if (navigator.share) {
      try {
        await navigator.share({
          title: this.noteTitle,
          text: this.noteContent,
          url: window.location.href
        });
      } catch (error) {
        console.error('Share failed:', error);
        this.fallbackShare();
      }
    } else {
      this.fallbackShare();
    }
  }
  
  fallbackShare() {
    // Copy URL to clipboard as fallback
    navigator.clipboard.writeText(window.location.href).then(() => {
      alert('Note URL copied to clipboard!');
    }).catch(() => {
      alert('Sharing not supported. Copy the URL from your browser address bar.');
    });
  }
  
  async duplicateNote() {
    try {
      const response = await fetch(`/api/notes/${this.noteId}/duplicate`, {
        method: 'POST'
      });
      
      if (response.ok) {
        const newNote = await response.json();
        window.location.href = `/detail/${newNote.id}`;
      } else {
        throw new Error('Failed to duplicate note');
      }
    } catch (error) {
      console.error('Duplicate failed:', error);
      alert('Failed to duplicate note. Please try again.');
    }
  }
  
  async syncToObsidian() {
    try {
      const response = await fetch(`/api/notes/${this.noteId}/sync-obsidian`, {
        method: 'POST'
      });
      
      if (response.ok) {
        alert('Note synced to Obsidian successfully!');
      } else {
        throw new Error('Failed to sync to Obsidian');
      }
    } catch (error) {
      console.error('Obsidian sync failed:', error);
      alert('Failed to sync to Obsidian. Please check your configuration.');
    }
  }
}

// Global initialization function
function initializeNoteInteraction(options) {
  window.noteInteraction = new NoteInteraction(options);
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = NoteInteraction;
}