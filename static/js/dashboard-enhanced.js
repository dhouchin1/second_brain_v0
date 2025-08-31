/**
 * Dashboard Enhanced - Modern UX Improvements for Second Brain
 * Provides auto-save, character counting, enhanced audio recording,
 * improved recent notes panel, and professional interactions
 */

class DashboardEnhanced {
  constructor() {
    this.autoSaveTimeout = null;
    this.autoSaveInterval = 2000; // 2 seconds
    this.maxCharacters = 5000;
    this.warningCharacters = 4500;
    
    // Audio recording state - now handled by AudioRecorder class
    // Keeping these for compatibility but they're not actively used
    this.isRecording = false;
    this.recordingStartTime = null;
    this.recordingTimer = null;
    
    // Recent notes state
    this.originalNotesOrder = [];
    this.currentSort = { field: 'date', direction: 'desc' };
    this.searchTerm = '';
    
    this.init();
  }

  init() {
    this.setupAutoSave();
    this.setupCharacterCounter();
    this.setupFormValidation();
    this.setupEnhancedAudioRecording();
    this.setupRecentNotesEnhancements();
    this.setupAccessibility();
    this.setupKeyboardShortcuts();
    this.bindEvents();
  }

  /**
   * AUTO-SAVE FUNCTIONALITY
   */
  setupAutoSave() {
    const noteInput = document.getElementById('note');
    const tagsInput = document.getElementById('tags');
    
    if (!noteInput) return;

    // Create auto-save indicator
    this.createAutoSaveIndicator();
    
    // Set up auto-save listeners
    [noteInput, tagsInput].forEach(input => {
      if (input) {
        input.addEventListener('input', () => {
          this.scheduleAutoSave();
        });
        
        input.addEventListener('paste', () => {
          // Delay to allow paste to complete
          setTimeout(() => this.scheduleAutoSave(), 100);
        });
      }
    });

    // Load saved draft on page load
    this.loadDraft();
  }

  createAutoSaveIndicator() {
    const formContainer = document.getElementById('quickCaptureForm')?.parentElement;
    if (!formContainer) return;

    const indicator = document.createElement('div');
    indicator.id = 'autoSaveIndicator';
    indicator.className = 'auto-save-indicator';
    indicator.innerHTML = '<span id="autoSaveText">Draft saved</span>';
    
    formContainer.appendChild(indicator);
  }

  scheduleAutoSave() {
    if (this.autoSaveTimeout) {
      clearTimeout(this.autoSaveTimeout);
    }

    this.showAutoSaveStatus('saving');
    
    this.autoSaveTimeout = setTimeout(() => {
      this.saveDraft();
    }, this.autoSaveInterval);
  }

  saveDraft() {
    const noteInput = document.getElementById('note');
    const tagsInput = document.getElementById('tags');
    
    if (!noteInput) return;

    const draft = {
      note: noteInput.value,
      tags: tagsInput?.value || '',
      timestamp: new Date().toISOString()
    };

    try {
      localStorage.setItem('second_brain_draft', JSON.stringify(draft));
      this.showAutoSaveStatus('saved');
    } catch (error) {
      console.error('Failed to save draft:', error);
      this.showAutoSaveStatus('error');
    }
  }

  loadDraft() {
    try {
      const savedDraft = localStorage.getItem('second_brain_draft');
      if (!savedDraft) return;

      const draft = JSON.parse(savedDraft);
      const noteInput = document.getElementById('note');
      const tagsInput = document.getElementById('tags');
      
      // Only load draft if inputs are empty AND it's recent (within 24 hours)
      const draftAge = new Date() - new Date(draft.timestamp);
      const oneDay = 24 * 60 * 60 * 1000; // 24 hours in milliseconds
      
      if (draftAge > oneDay) {
        // Draft is too old, clear it
        localStorage.removeItem('second_brain_draft');
        return;
      }
      
      // Only load draft if inputs are completely empty
      if (noteInput && !noteInput.value.trim() && draft.note && draft.note.trim()) {
        noteInput.value = draft.note;
        this.updateCharacterCounter();
        // Show indicator that draft was loaded
        this.showAutoSaveStatus('loaded');
      }
      
      if (tagsInput && !tagsInput.value.trim() && draft.tags && draft.tags.trim()) {
        tagsInput.value = draft.tags;
      }
      
    } catch (error) {
      console.error('Failed to load draft:', error);
      // Clear corrupted draft
      localStorage.removeItem('second_brain_draft');
    }
  }

  clearDraft() {
    localStorage.removeItem('second_brain_draft');
    this.hideAutoSaveStatus();
  }

  showAutoSaveStatus(status) {
    const indicator = document.getElementById('autoSaveIndicator');
    const text = document.getElementById('autoSaveText');
    
    if (!indicator || !text) return;

    indicator.className = 'auto-save-indicator show';
    
    switch (status) {
      case 'saving':
        indicator.classList.add('saving');
        text.textContent = 'Saving draft...';
        break;
      case 'saved':
        indicator.classList.remove('saving', 'error', 'loaded');
        text.textContent = 'Draft saved';
        // Hide after 2 seconds
        setTimeout(() => this.hideAutoSaveStatus(), 2000);
        break;
      case 'loaded':
        indicator.classList.remove('saving', 'error');
        indicator.classList.add('loaded');
        text.textContent = 'Draft restored';
        // Hide after 3 seconds
        setTimeout(() => this.hideAutoSaveStatus(), 3000);
        break;
      case 'error':
        indicator.classList.add('error');
        indicator.classList.remove('saving', 'loaded');
        text.textContent = 'Save failed';
        break;
    }
  }

  hideAutoSaveStatus() {
    const indicator = document.getElementById('autoSaveIndicator');
    if (indicator) {
      indicator.classList.remove('show');
    }
  }

  /**
   * CHARACTER COUNTER AND VALIDATION
   */
  setupCharacterCounter() {
    const noteInput = document.getElementById('note');
    if (!noteInput) return;

    // Create character counter
    const counterContainer = document.createElement('div');
    counterContainer.className = 'relative';
    
    const counter = document.createElement('div');
    counter.id = 'characterCounter';
    counter.className = 'character-counter';
    counter.textContent = '0 / ' + this.maxCharacters;
    
    noteInput.parentElement.style.position = 'relative';
    noteInput.parentElement.appendChild(counter);
    
    // Set up counter updates
    noteInput.addEventListener('input', () => {
      this.updateCharacterCounter();
    });
    
    // Initial count
    this.updateCharacterCounter();
  }

  updateCharacterCounter() {
    const noteInput = document.getElementById('note');
    const counter = document.getElementById('characterCounter');
    
    if (!noteInput || !counter) return;

    const length = noteInput.value.length;
    counter.textContent = `${length} / ${this.maxCharacters}`;
    
    // Update styling based on character count
    counter.className = 'character-counter';
    
    if (length > this.maxCharacters) {
      counter.classList.add('danger');
    } else if (length > this.warningCharacters) {
      counter.classList.add('warning');
    }
  }

  /**
   * FORM VALIDATION
   */
  setupFormValidation() {
    const form = document.getElementById('quickCaptureForm');
    if (!form) return;

    // Add enhanced classes to form inputs
    const inputs = form.querySelectorAll('input, textarea');
    inputs.forEach(input => {
      input.classList.add('form-input-enhanced');
      
      // Add validation message container
      const validationMsg = document.createElement('div');
      validationMsg.className = 'validation-message';
      validationMsg.id = input.id + '-validation';
      input.parentElement.appendChild(validationMsg);
    });

    // Don't add form submission handler - let AudioRecorder handle it
    // Just validate on input
    inputs.forEach(input => {
      input.addEventListener('input', () => {
        this.clearValidationError(input);
      });
    });
  }

  validateForm() {
    const noteInput = document.getElementById('note');
    const tagsInput = document.getElementById('tags');
    let isValid = true;

    // Clear previous validation states
    document.querySelectorAll('.form-input-enhanced').forEach(input => {
      input.classList.remove('has-error');
    });
    document.querySelectorAll('.validation-message').forEach(msg => {
      msg.classList.remove('show');
    });

    // Validate note length
    if (noteInput) {
      const noteLength = noteInput.value.length;
      if (noteLength > this.maxCharacters) {
        this.showValidationError(noteInput, `Note must be under ${this.maxCharacters} characters`);
        isValid = false;
      }
    }

    // Validate tags format (optional)
    if (tagsInput && tagsInput.value.trim()) {
      const tags = tagsInput.value.split(',').map(tag => tag.trim());
      const invalidTags = tags.filter(tag => tag.length > 50 || !/^[a-zA-Z0-9_-]+$/.test(tag));
      
      if (invalidTags.length > 0) {
        this.showValidationError(tagsInput, 'Tags must be alphanumeric, under 50 chars each');
        isValid = false;
      }
    }

    return isValid;
  }
  
  clearValidationError(input) {
    input.classList.remove('has-error');
    const validationMsg = document.getElementById(input.id + '-validation');
    if (validationMsg) {
      validationMsg.classList.remove('show');
    }
  }

  showValidationError(input, message) {
    input.classList.add('has-error');
    const validationMsg = document.getElementById(input.id + '-validation');
    if (validationMsg) {
      validationMsg.textContent = message;
      validationMsg.classList.add('show');
    }
    
    // Add shake animation
    input.classList.add('animate-shake');
    setTimeout(() => input.classList.remove('animate-shake'), 600);
  }

  /**
   * ENHANCED AUDIO RECORDING - Simplified to work with new audio system
   */
  setupEnhancedAudioRecording() {
    // The audio recording is now handled by the AudioRecorder class in the template
    // This method just provides additional UI enhancements if needed
    this.enhanceAudioUI();
  }
  
  enhanceAudioUI() {
    // Add any additional UI enhancements for audio recording
    const audioContainer = document.querySelector('.audio-recording-container');
    if (audioContainer) {
      audioContainer.classList.add('audio-container-enhanced');
    }
  }

  /**
   * RECENT NOTES PANEL ENHANCEMENTS
   */
  setupRecentNotesEnhancements() {
    this.createRecentNotesSearchAndSort();
    this.enhanceRecentNoteItems();
    this.storeOriginalNotesOrder();
  }

  createRecentNotesSearchAndSort() {
    const recentPanel = document.getElementById('recent-panel');
    if (!recentPanel) return;

    const header = recentPanel.querySelector('h3')?.parentElement;
    if (!header) return;

    // Create search input
    const searchContainer = document.createElement('div');
    searchContainer.className = 'recent-search-container';
    searchContainer.innerHTML = `
      <input 
        type="text" 
        id="recentSearch" 
        class="recent-search-input" 
        placeholder="Search recent notes..."
        aria-label="Search recent notes"
      >
      <button 
        type="button" 
        id="recentSearchClear" 
        class="recent-search-clear" 
        style="display: none;"
        aria-label="Clear search"
      >
        <svg width="12" height="12" fill="currentColor" viewBox="0 0 16 16">
          <path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8 2.146 2.854Z"/>
        </svg>
      </button>
    `;

    // Create sort controls
    const sortContainer = document.createElement('div');
    sortContainer.className = 'recent-sort-controls';
    sortContainer.innerHTML = `
      <span class="text-xs text-slate-400">Sort by:</span>
      <button type="button" class="sort-button active" data-sort="date">
        Date <span class="sort-icon">↓</span>
      </button>
      <button type="button" class="sort-button" data-sort="title">
        Title <span class="sort-icon">↓</span>
      </button>
      <button type="button" class="sort-button" data-sort="type">
        Type <span class="sort-icon">↓</span>
      </button>
      <button type="button" class="sort-button" data-sort="pinned">
        Pinned <span class="sort-icon">↓</span>
      </button>
    `;

    // Insert after header
    header.insertAdjacentElement('afterend', searchContainer);
    searchContainer.insertAdjacentElement('afterend', sortContainer);

    this.bindRecentNotesEvents();
  }

  bindRecentNotesEvents() {
    const searchInput = document.getElementById('recentSearch');
    const clearBtn = document.getElementById('recentSearchClear');
    const sortButtons = document.querySelectorAll('.sort-button');

    // Search functionality
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.searchTerm = e.target.value.toLowerCase();
        this.filterAndSortNotes();
        
        // Show/hide clear button
        if (clearBtn) {
          clearBtn.style.display = this.searchTerm ? 'block' : 'none';
        }
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        searchInput.value = '';
        this.searchTerm = '';
        this.filterAndSortNotes();
        clearBtn.style.display = 'none';
        searchInput.focus();
      });
    }

    // Sort functionality
    sortButtons.forEach(button => {
      button.addEventListener('click', () => {
        const field = button.dataset.sort;
        
        // Toggle direction if same field
        if (this.currentSort.field === field) {
          this.currentSort.direction = this.currentSort.direction === 'asc' ? 'desc' : 'asc';
        } else {
          this.currentSort.field = field;
          this.currentSort.direction = field === 'title' ? 'asc' : 'desc';
        }
        
        // Update UI
        sortButtons.forEach(btn => {
          btn.classList.remove('active');
          btn.classList.remove('desc');
        });
        button.classList.add('active');
        if (this.currentSort.direction === 'desc') {
          button.classList.add('desc');
        }
        
        this.filterAndSortNotes();
      });
    });
  }

  storeOriginalNotesOrder() {
    const notesList = document.querySelector('#recent-panel ul');
    if (!notesList) return;

    this.originalNotesOrder = Array.from(notesList.children).map(li => ({
      element: li,
      id: li.querySelector('.recent-pin')?.dataset.id,
      title: li.querySelector('a[href*="/detail/"]')?.textContent.trim() || '',
      type: this.getNoteType(li),
      isPinned: li.querySelector('.recent-pin')?.textContent === '★',
      timestamp: li.querySelector('.text-xs.text-slate-400')?.textContent || ''
    }));
  }

  getNoteType(noteElement) {
    const iconElement = noteElement.querySelector('span[class*="text-"]');
    if (!iconElement) return 'text';
    
    if (iconElement.textContent.includes('🎤')) return 'audio';
    if (iconElement.classList.contains('text-green-300')) return 'shortcut';
    return 'text';
  }

  filterAndSortNotes() {
    let filteredNotes = [...this.originalNotesOrder];

    // Apply search filter
    if (this.searchTerm) {
      filteredNotes = filteredNotes.filter(note => 
        note.title.toLowerCase().includes(this.searchTerm) ||
        (note.element.querySelector('.recent-pin')?.dataset.tags || '')
          .toLowerCase().includes(this.searchTerm)
      );
    }

    // Apply sort
    filteredNotes.sort((a, b) => {
      let comparison = 0;
      
      switch (this.currentSort.field) {
        case 'title':
          comparison = a.title.localeCompare(b.title);
          break;
        case 'type':
          comparison = a.type.localeCompare(b.type);
          break;
        case 'pinned':
          comparison = (b.isPinned ? 1 : 0) - (a.isPinned ? 1 : 0);
          break;
        case 'date':
        default:
          // Keep original order for date (newest first)
          comparison = this.originalNotesOrder.indexOf(a) - this.originalNotesOrder.indexOf(b);
          break;
      }
      
      return this.currentSort.direction === 'desc' ? -comparison : comparison;
    });

    // Re-render notes list
    const notesList = document.querySelector('#recent-panel ul');
    if (notesList) {
      // Clear existing notes
      notesList.innerHTML = '';
      
      // Add filtered and sorted notes
      filteredNotes.forEach(note => {
        notesList.appendChild(note.element);
        note.element.classList.add('animate-fade-in');
      });
      
      // Show empty state if no results
      if (filteredNotes.length === 0) {
        const emptyState = document.createElement('li');
        emptyState.className = 'py-6 text-center text-slate-400 text-sm';
        emptyState.textContent = this.searchTerm ? 'No matching notes found' : 'No recent notes';
        notesList.appendChild(emptyState);
      }
    }
  }

  enhanceRecentNoteItems() {
    const noteItems = document.querySelectorAll('#recent-panel li');
    noteItems.forEach(item => {
      if (item.querySelector('a[href*="/detail/"]')) {
        item.classList.add('recent-note-item');
        
        // Add enhanced type icons
        const typeIcon = item.querySelector('span[class*="text-"]');
        if (typeIcon) {
          typeIcon.classList.add('note-type-icon');
          
          if (typeIcon.textContent.includes('🎤')) {
            typeIcon.classList.add('audio-note');
          } else if (typeIcon.classList.contains('text-green-300')) {
            typeIcon.classList.add('shortcut-note');
          } else {
            typeIcon.classList.add('text-note');
          }
        }
        
        // Check if pinned
        const pinButton = item.querySelector('.recent-pin');
        if (pinButton?.textContent === '★') {
          item.classList.add('pinned');
        }
      }
    });
  }

  /**
   * ACCESSIBILITY ENHANCEMENTS
   */
  setupAccessibility() {
    // Add ARIA labels and roles
    const quickCaptureForm = document.getElementById('quickCaptureForm');
    if (quickCaptureForm) {
      quickCaptureForm.setAttribute('role', 'form');
      quickCaptureForm.setAttribute('aria-label', 'Quick note capture form');
    }

    // Add screen reader announcements for auto-save
    const autoSaveIndicator = document.getElementById('autoSaveIndicator');
    if (autoSaveIndicator) {
      autoSaveIndicator.setAttribute('role', 'status');
      autoSaveIndicator.setAttribute('aria-live', 'polite');
    }

    // Enhance record button accessibility
    const recordBtn = document.getElementById('recordBtn');
    if (recordBtn) {
      recordBtn.setAttribute('aria-describedby', 'recordStatus');
    }

    // Add focus management
    this.setupFocusManagement();
  }

  setupFocusManagement() {
    // Trap focus in inline edit dialogs
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        // Close any open inline edit dialogs
        const activeEdit = document.querySelector('.inline-edit-container:not(.hidden)');
        if (activeEdit) {
          const cancelBtn = activeEdit.querySelector('.recent-cancel');
          if (cancelBtn) cancelBtn.click();
        }
      }
    });
  }

  /**
   * KEYBOARD SHORTCUTS
   */
  setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      // Ctrl/Cmd + Enter to submit form
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        const form = document.getElementById('quickCaptureForm');
        if (form && document.activeElement && form.contains(document.activeElement)) {
          e.preventDefault();
          form.requestSubmit();
        }
      }
      
      // Ctrl/Cmd + S to save draft
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        const noteInput = document.getElementById('note');
        if (noteInput && document.activeElement === noteInput) {
          e.preventDefault();
          this.saveDraft();
        }
      }
      
      // Ctrl/Cmd + F to focus search (when in recent panel)
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        const searchInput = document.getElementById('recentSearch');
        const recentPanel = document.getElementById('recent-panel');
        if (searchInput && recentPanel && recentPanel.contains(document.activeElement)) {
          e.preventDefault();
          searchInput.focus();
        }
      }
    });
  }

  /**
   * EVENT BINDING
   */
  bindEvents() {
    // Success animations
    document.addEventListener('DOMContentLoaded', () => {
      // Check for success flash messages
      const flash = document.getElementById('flash-container');
      if (flash && flash.textContent.includes('queued')) {
        // Add success animation to the form
        const form = document.getElementById('quickCaptureForm');
        if (form) {
          form.classList.add('animate-bounce-success');
        }
      }
    });
    
    // Enhanced keyboard shortcuts for the new button layout
    this.setupEnhancedKeyboardShortcuts();
  }
  
  setupEnhancedKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      // Ctrl/Cmd + S to save text note specifically
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        const noteInput = document.getElementById('note');
        const saveTextBtn = document.getElementById('saveTextBtn');
        if (noteInput && saveTextBtn && document.activeElement === noteInput) {
          e.preventDefault();
          saveTextBtn.click();
        }
      }
    });
  }

  /**
   * UTILITY METHODS
   */
  showNotification(message, type = 'info', duration = 4000) {
    const notification = document.createElement('div');
    notification.className = `
      fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 max-w-sm 
      transition-all duration-300 transform translate-x-full
      ${type === 'success' ? 'bg-green-500 text-white' :
        type === 'error' ? 'bg-red-500 text-white' :
        type === 'warning' ? 'bg-yellow-500 text-black' :
        'bg-blue-500 text-white'}
    `;
    notification.textContent = message;
    notification.setAttribute('role', 'alert');

    document.body.appendChild(notification);

    // Animate in
    requestAnimationFrame(() => {
      notification.style.transform = 'translateX(0)';
    });

    // Auto-remove
    setTimeout(() => {
      notification.style.transform = 'translateX(100%)';
      setTimeout(() => {
        if (notification.parentNode) {
          notification.parentNode.removeChild(notification);
        }
      }, 300);
    }, duration);
  }
}

// Initialize enhanced dashboard when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    new DashboardEnhanced();
  });
} else {
  new DashboardEnhanced();
}

// Export for testing/debugging
window.DashboardEnhanced = DashboardEnhanced;