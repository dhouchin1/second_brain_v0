/**
 * Advanced Search Interface for Second Brain
 * Works with /api/search/hybrid and /api/search/suggestions
 */

class AdvancedSearchInterface {
  constructor() {
    this.currentResults = [];
    this.searchHistory = [];
    this.filters = {
      dateRange: { start: null, end: null },
      tags: [],
      types: [],
      status: [],
      minScore: 0.1,
    };
    this.searchMode = 'hybrid';
    this.weights = { fts: 0.4, semantic: 0.6 };
    this.init();
  }

  init() {
    this.setupEventListeners();
    this.setupSearchSuggestions();
  }

  setupEventListeners() {
    const searchInput = document.getElementById('search-input');
    const searchButton = document.getElementById('search-button');

    if (searchInput) {
      searchInput.addEventListener('input', this.debounce(() => this.handleSearchInput(searchInput.value), 250));
      searchInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') this.performSearch(); });
    }
    if (searchButton) searchButton.addEventListener('click', () => this.performSearch());

    // Mode buttons
    document.querySelectorAll('[data-search-mode]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const mode = e.currentTarget.dataset.searchMode;
        this.setSearchMode(mode);
      });
    });

    // Date filters
    const startDate = document.getElementById('date-start');
    const endDate = document.getElementById('date-end');
    if (startDate) startDate.addEventListener('change', (e) => { this.filters.dateRange.start = e.target.value; });
    if (endDate) endDate.addEventListener('change', (e) => { this.filters.dateRange.end = e.target.value; });

    // Tag filter
    const tagInput = document.getElementById('tag-filter');
    if (tagInput) {
      tagInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
          const val = (e.target.value || '').trim();
          if (val) this.addTagFilter(val);
          e.target.value = '';
          e.preventDefault();
        }
      });
    }

    // Type filters
    document.querySelectorAll('[data-type-filter]').forEach(cb => {
      cb.addEventListener('change', (e) => {
        const type = e.target.dataset.typeFilter;
        if (!type) return;
        if (e.target.checked) {
          if (!this.filters.types.includes(type)) this.filters.types.push(type);
        } else {
          this.filters.types = this.filters.types.filter(t => t !== type);
        }
        this.performSearch();
      });
    });

    // Status filters
    document.querySelectorAll('[data-status-filter]').forEach(cb => {
      cb.addEventListener('change', (e) => {
        const status = e.target.dataset.statusFilter;
        if (!status) return;
        if (e.target.checked) {
          if (!this.filters.status.includes(status)) this.filters.status.push(status);
        } else {
          this.filters.status = this.filters.status.filter(s => s !== status);
        }
        this.performSearch();
      });
    });

    // Min score slider
    const minScore = document.getElementById('min-score');
    const minScoreValue = document.getElementById('min-score-value');
    if (minScore) {
      minScore.addEventListener('input', (e) => {
        const v = parseFloat(e.target.value);
        if (!isNaN(v)) {
          this.filters.minScore = v;
          if (minScoreValue) minScoreValue.textContent = v.toFixed(2);
          this.applyFilters();
        }
      });
    }
  }

  setupSearchSuggestions() {
    const searchInput = document.getElementById('search-input');
    const suggestionsContainer = document.getElementById('search-suggestions');
    if (!searchInput || !suggestionsContainer) return;

    searchInput.addEventListener('focus', () => this.showRecentSearches());
    document.addEventListener('click', (e) => {
      if (!suggestionsContainer.contains(e.target) && e.target !== searchInput) this.hideSuggestions();
    });
  }

  async handleSearchInput(query) {
    const q = (query || '').trim();
    if (q.length < 2) { this.hideSuggestions(); return; }
    try {
      const suggestions = await this.getSuggestions(q);
      this.displaySuggestions(suggestions);
    } catch (e) {
      console.warn('suggestions failed', e);
    }
  }

  async getSuggestions(query) {
    const res = await fetch(`/api/search/suggestions?q=${encodeURIComponent(query)}`, { credentials: 'same-origin' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    return data && Array.isArray(data.suggestions) ? data.suggestions : [];
  }

  async getQueryEnhancement(query) {
    try {
      const res = await fetch('/api/search/enhance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ query })
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return await res.json();
    } catch (e) {
      console.warn('Query enhancement failed:', e);
      return null;
    }
  }

  displaySuggestions(suggestions) {
    const container = document.getElementById('search-suggestions');
    if (!container) return;
    container.innerHTML = '';
    
    // Handle both old format (strings) and new format (objects)
    const normalizedSuggestions = (suggestions || []).map(s => {
      if (typeof s === 'string') {
        return { text: s, type: 'basic', icon: '🔍' };
      }
      return s;
    });

    if (!normalizedSuggestions.length) { 
      this.hideSuggestions(); 
      return; 
    }

    // Remove duplicates based on text
    const uniqueSuggestions = [];
    const seenTexts = new Set();
    for (const sugg of normalizedSuggestions) {
      if (!seenTexts.has(sugg.text.toLowerCase())) {
        seenTexts.add(sugg.text.toLowerCase());
        uniqueSuggestions.push(sugg);
      }
    }

    const ul = document.createElement('ul');
    ul.className = 'suggestions-list bg-slate-800 border border-slate-700 rounded-lg shadow-lg max-h-64 overflow-y-auto';
    
    uniqueSuggestions.forEach(suggestion => {
      const li = document.createElement('li');
      li.className = 'suggestion-item flex items-center gap-3 px-4 py-3 hover:bg-slate-700 cursor-pointer border-b border-slate-700 last:border-b-0';
      
      const icon = document.createElement('span');
      icon.className = 'text-sm';
      icon.textContent = suggestion.icon || '🔍';
      
      const content = document.createElement('div');
      content.className = 'flex-1 min-w-0';
      
      const text = document.createElement('div');
      text.className = 'text-sm text-slate-100 truncate';
      text.textContent = suggestion.text;
      content.appendChild(text);
      
      // Add additional info based on type
      if (suggestion.type === 'phrase' && suggestion.source) {
        const source = document.createElement('div');
        source.className = 'text-xs text-slate-400 truncate mt-1';
        source.textContent = `from: ${suggestion.source}`;
        content.appendChild(source);
      } else if (suggestion.type === 'popular' && suggestion.count) {
        const count = document.createElement('div');
        count.className = 'text-xs text-slate-400 mt-1';
        count.textContent = `${suggestion.count} searches`;
        content.appendChild(count);
      } else if (suggestion.type === 'semantic' && suggestion.score) {
        const score = document.createElement('div');
        score.className = 'text-xs text-slate-400 mt-1';
        score.textContent = `similarity: ${suggestion.score}`;
        content.appendChild(score);
      }
      
      const typeLabel = document.createElement('span');
      typeLabel.className = 'text-xs text-slate-500 capitalize px-2 py-1 bg-slate-900 rounded';
      typeLabel.textContent = suggestion.type || 'suggestion';
      
      li.appendChild(icon);
      li.appendChild(content);
      li.appendChild(typeLabel);
      
      li.addEventListener('click', () => {
        const input = document.getElementById('search-input');
        if (input) input.value = suggestion.text;
        this.hideSuggestions();
        this.performSearch();
      });
      
      ul.appendChild(li);
    });
    
    // Add enhancement button if we have a query
    const input = document.getElementById('search-input');
    if (input && input.value.trim().length > 2) {
      const enhanceButton = document.createElement('li');
      enhanceButton.className = 'suggestion-item flex items-center gap-3 px-4 py-3 hover:bg-indigo-700 cursor-pointer border-t-2 border-indigo-500 bg-indigo-800';
      enhanceButton.innerHTML = `
        <span class="text-sm">🧠</span>
        <div class="flex-1">
          <div class="text-sm text-white font-medium">Enhance with AI</div>
          <div class="text-xs text-indigo-200">Get smarter search suggestions</div>
        </div>
        <span class="text-xs text-indigo-300">AI</span>
      `;
      enhanceButton.addEventListener('click', () => this.showQueryEnhancement());
      ul.appendChild(enhanceButton);
    }
    
    container.appendChild(ul);
    container.classList.add('visible');
  }

  hideSuggestions() { const c = document.getElementById('search-suggestions'); if (c) c.classList.remove('visible'); }
  showRecentSearches() { if (this.searchHistory.length > 0) this.displaySuggestions(this.searchHistory.slice(-5)); }

  async showQueryEnhancement() {
    const input = document.getElementById('search-input');
    const query = input?.value?.trim();
    if (!query) return;

    this.hideSuggestions();
    const container = document.getElementById('search-suggestions');
    if (!container) return;

    // Show loading state
    container.innerHTML = `
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-lg p-4">
        <div class="flex items-center gap-3">
          <div class="animate-spin h-4 w-4 border-2 border-indigo-400 border-t-transparent rounded-full"></div>
          <div class="text-sm text-slate-300">AI is enhancing your query...</div>
        </div>
      </div>
    `;
    container.classList.add('visible');

    try {
      const enhancement = await this.getQueryEnhancement(query);
      if (!enhancement) {
        this.hideSuggestions();
        return;
      }

      this.displayQueryEnhancement(enhancement);
    } catch (e) {
      console.error('Query enhancement failed:', e);
      this.hideSuggestions();
    }
  }

  displayQueryEnhancement(enhancement) {
    const container = document.getElementById('search-suggestions');
    if (!container) return;

    const div = document.createElement('div');
    div.className = 'bg-slate-800 border border-slate-700 rounded-lg shadow-lg max-h-80 overflow-y-auto';

    let content = `
      <div class="p-4 border-b border-slate-700">
        <div class="flex items-center gap-2 mb-3">
          <span class="text-lg">🧠</span>
          <h3 class="text-sm font-semibold text-slate-100">AI Query Enhancement</h3>
          <span class="text-xs bg-indigo-600 text-white px-2 py-1 rounded">${enhancement.intent}</span>
        </div>
    `;

    // Enhanced query
    if (enhancement.enhanced_query && enhancement.enhanced_query !== document.getElementById('search-input')?.value) {
      content += `
        <div class="mb-3">
          <div class="text-xs text-slate-400 mb-1">Enhanced Query</div>
          <button class="w-full text-left bg-indigo-900 hover:bg-indigo-800 p-2 rounded border border-indigo-600 text-sm text-slate-100" 
                  data-enhanced-query="${this.escape(enhancement.enhanced_query)}">
            ${this.escape(enhancement.enhanced_query)}
          </button>
        </div>
      `;
    }

    // Spelling corrections
    if (enhancement.spelling_corrections && enhancement.spelling_corrections.length > 0) {
      content += `
        <div class="mb-3">
          <div class="text-xs text-slate-400 mb-1">Did you mean?</div>
          ${enhancement.spelling_corrections.map(correction => `
            <button class="mr-2 mb-1 bg-amber-900 hover:bg-amber-800 px-2 py-1 rounded text-xs text-amber-100" 
                    data-correction="${this.escape(correction)}">
              ${this.escape(correction)}
            </button>
          `).join('')}
        </div>
      `;
    }

    content += '</div>';

    // Alternative queries
    if (enhancement.alternative_queries && enhancement.alternative_queries.length > 0) {
      content += `
        <div class="p-4 border-b border-slate-700">
          <div class="text-xs text-slate-400 mb-2">Alternative Phrasings</div>
          <div class="space-y-1">
            ${enhancement.alternative_queries.map(alt => `
              <button class="w-full text-left bg-slate-700 hover:bg-slate-600 p-2 rounded text-sm text-slate-200" 
                      data-alternative="${this.escape(alt)}">
                ${this.escape(alt)}
              </button>
            `).join('')}
          </div>
        </div>
      `;
    }

    // Suggested tags
    if (enhancement.suggested_tags && enhancement.suggested_tags.length > 0) {
      content += `
        <div class="p-4 border-b border-slate-700">
          <div class="text-xs text-slate-400 mb-2">Related Tags</div>
          <div class="flex flex-wrap gap-1">
            ${enhancement.suggested_tags.map(tag => `
              <button class="bg-green-900 hover:bg-green-800 px-2 py-1 rounded text-xs text-green-100" 
                      data-tag="${this.escape(tag)}">
                🏷️ ${this.escape(tag)}
              </button>
            `).join('')}
          </div>
        </div>
      `;
    }

    // Expansion terms
    if (enhancement.expansion_terms && enhancement.expansion_terms.length > 0) {
      content += `
        <div class="p-4">
          <div class="text-xs text-slate-400 mb-2">Related Terms</div>
          <div class="flex flex-wrap gap-1">
            ${enhancement.expansion_terms.map(term => `
              <span class="bg-slate-700 px-2 py-1 rounded text-xs text-slate-300">
                ${this.escape(term)}
              </span>
            `).join('')}
          </div>
        </div>
      `;
    }

    div.innerHTML = content;

    // Add event listeners
    div.addEventListener('click', (e) => {
      const input = document.getElementById('search-input');
      if (!input) return;

      if (e.target.dataset.enhancedQuery) {
        input.value = e.target.dataset.enhancedQuery;
        this.hideSuggestions();
        this.performSearch();
      } else if (e.target.dataset.correction) {
        input.value = e.target.dataset.correction;
        this.hideSuggestions();
        this.performSearch();
      } else if (e.target.dataset.alternative) {
        input.value = e.target.dataset.alternative;
        this.hideSuggestions();
        this.performSearch();
      } else if (e.target.dataset.tag) {
        this.addTagFilter(e.target.dataset.tag);
        this.hideSuggestions();
      }
    });

    container.innerHTML = '';
    container.appendChild(div);
    container.classList.add('visible');
  }

  async performSearch() {
    this.hideSuggestions();
    const input = document.getElementById('search-input');
    const query = (input?.value || '').trim();
    if (!query) return;

    this.showSearchSpinner();
    try {
      const payload = {
        query,
        search_type: this.searchMode,
        fts_weight: this.weights.fts,
        semantic_weight: this.weights.semantic,
        limit: 20,
        min_fts_score: this.filters.minScore,
        min_semantic_score: this.filters.minScore,
      };
      if (this.filters.dateRange.start) payload.date_start = this.filters.dateRange.start;
      if (this.filters.dateRange.end) payload.date_end = this.filters.dateRange.end;
      if (this.filters.tags.length) payload.tags = this.filters.tags;
      if (this.filters.types.length) payload.types = this.filters.types;
      if (this.filters.status.length) payload.status = this.filters.status;

      const res = await fetch('/api/search/hybrid', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      this.currentResults = Array.isArray(data.results) ? data.results : [];
      this.saveSearchHistory(query);
      this.renderResults();
    } catch (e) {
      console.error('search failed', e);
      this.showError('Search failed. Please try again.');
    } finally {
      this.hideSearchSpinner();
    }
  }

  renderResults() {
    const container = document.getElementById('search-results');
    const metaContainer = document.getElementById('results-meta');
    const loadingContainer = document.getElementById('search-loading');
    const emptyContainer = document.getElementById('empty-state');
    
    if (!container) return;
    
    // Hide loading state
    if (loadingContainer) loadingContainer.classList.add('hidden');
    
    // Update meta info
    if (metaContainer) {
      metaContainer.textContent = this.currentResults.length > 0 
        ? `${this.currentResults.length} result${this.currentResults.length !== 1 ? 's' : ''}` 
        : '';
    }
    
    container.innerHTML = '';
    
    // Show empty state if no results
    if (!this.currentResults.length) {
      if (emptyContainer) emptyContainer.classList.remove('hidden');
      return;
    }
    
    // Hide empty state
    if (emptyContainer) emptyContainer.classList.add('hidden');
    
    // Render results
    const frag = document.createDocumentFragment();
    this.currentResults.forEach(r => {
      const div = document.createElement('div');
      div.className = 'result-card';
      div.onclick = () => {
        const id = r.note_id || r.id;
        if (id) window.location.href = `/detail/${id}`;
      };
      
      const ts = r.timestamp ? new Date((r.timestamp + '').replace(' ', 'T')).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
      }) : '';
      
      // Get note type indicator
      const typeInfo = this.getTypeInfo(r.type);
      
      div.innerHTML = `
        <div class="flex items-start justify-between mb-2">
          <h3 class="result-title flex-1">${this.escape(r.title || '(untitled)')}</h3>
          <div class="flex items-center gap-2 text-xs text-slate-400">
            <div class="flex items-center gap-1">
              <span class="w-2 h-2 rounded-full ${typeInfo.color}"></span>
              <span>${typeInfo.label}</span>
            </div>
            ${ts ? `<span class="font-mono">${ts}</span>` : ''}
          </div>
        </div>
        
        <div class="result-snippet mb-3">
          ${this.escape((r.snippet || r.summary || (r.content || '')).slice(0, 200))}${(r.snippet || r.summary || (r.content || '')).length > 200 ? '...' : ''}
        </div>
        
        <div class="flex items-center justify-between">
          <div class="result-tags">
            ${this.renderTags(r.tags || r.tag_list || '')}
          </div>
          <div class="flex items-center gap-2">
            ${typeof r.fts_score === 'number' ? `<span class="score-badge">FTS ${(r.fts_score * 100).toFixed(0)}%</span>` : ''}
            ${typeof r.semantic_score === 'number' ? `<span class="score-badge">SEM ${(r.semantic_score * 100).toFixed(0)}%</span>` : ''}
            ${typeof r.combined_score === 'number' ? `<span class="score-badge">COMB ${(r.combined_score * 100).toFixed(0)}%</span>` : ''}
          </div>
        </div>
      `;
      // If image note, inject preview block before snippet
      const isImage = !!(r && (r.type === 'image' || String(r.file_type||'').toLowerCase() === 'image' || String(r.file_mime_type||'').toLowerCase().startsWith('image/')));
      const safeUrl = r.file_url || (r.file_filename ? ('/files/' + r.file_filename) : '');
      if (isImage && safeUrl) {
        const hdr = div.querySelector('.flex.items-start.justify-between');
        const snippet = div.querySelector('.result-snippet');
        const block = document.createElement('div');
        block.className = 'mt-2 rounded overflow-hidden border border-white/10 bg-black/20';
        const img = document.createElement('img');
        img.src = safeUrl;
        img.alt = 'Image preview';
        img.style.maxHeight = '160px';
        img.style.width = '100%';
        img.style.objectFit = 'contain';
        img.style.display = 'block';
        block.appendChild(img);
        if (snippet) {
          snippet.parentNode.insertBefore(block, snippet);
        } else {
          div.appendChild(block);
        }
      }

      frag.appendChild(div);
    });
    container.appendChild(frag);
  }
  
  getTypeInfo(type) {
    const typeMap = {
      'audio': { label: 'Audio', color: 'bg-yellow-400' },
      'apple': { label: 'Shortcut', color: 'bg-green-400' },
      'meeting': { label: 'Meeting', color: 'bg-purple-400' },
      'text': { label: 'Text', color: 'bg-blue-400' }
    };
    return typeMap[type] || { label: 'Note', color: 'bg-blue-400' };
  }

  applyFilters() {
    if (!this.currentResults.length) return;
    const filtered = this.currentResults.filter(r => {
      const fts = typeof r.fts_score === 'number' ? r.fts_score : 0;
      const sem = typeof r.semantic_score === 'number' ? r.semantic_score : 0;
      return (fts >= this.filters.minScore) || (sem >= this.filters.minScore);
    });
    this.currentResults = filtered;
    this.renderResults();
  }

  addTagFilter(tag) {
    const t = (tag || '').trim();
    if (!t) return;
    if (!this.filters.tags.includes(t)) {
      this.filters.tags.push(t);
      this.renderActiveTags();
      this.performSearch();
    }
  }

  removeTagFilter(tag) {
    this.filters.tags = this.filters.tags.filter(t => t !== tag);
    this.renderActiveTags();
    this.performSearch();
  }

  renderActiveTags() {
    const container = document.getElementById('active-tag-filters');
    if (!container) return;
    container.innerHTML = '';
    this.filters.tags.forEach(t => {
      const el = document.createElement('span');
      el.className = 'active-filter-tag';
      el.innerHTML = `${this.escape(t)} <button class="remove-filter" data-tag="${this.escape(t)}">×</button>`;
      container.appendChild(el);
    });
    container.querySelectorAll('[data-tag]').forEach(btn => { btn.addEventListener('click', () => this.removeTagFilter(btn.dataset.tag)); });
  }

  setSearchMode(mode) {
    this.searchMode = mode;
    document.querySelectorAll('[data-search-mode]').forEach(el => el.classList.toggle('active', el.dataset.searchMode === mode));
    this.performSearch();
  }

  saveSearchHistory(q) { this.searchHistory.push(q); if (this.searchHistory.length > 50) this.searchHistory.shift(); }

  showSearchSpinner() { 
    const btn = document.getElementById('search-button'); 
    const loading = document.getElementById('search-loading');
    const empty = document.getElementById('empty-state');
    const results = document.getElementById('search-results');
    
    if (btn) btn.disabled = true; 
    if (loading) loading.classList.remove('hidden');
    if (empty) empty.classList.add('hidden');
    if (results) results.innerHTML = '';
  }
  
  hideSearchSpinner() { 
    const btn = document.getElementById('search-button'); 
    const loading = document.getElementById('search-loading');
    
    if (btn) btn.disabled = false; 
    if (loading) loading.classList.add('hidden');
  }
  showError(msg) { const c = document.getElementById('search-results'); if (c) c.innerHTML = `<div class="error-state">${this.escape(msg)}</div>`; }

  renderTags(tags) {
    const arr = Array.isArray(tags) ? tags : String(tags || '').split(',');
    return arr.filter(Boolean).map(t => `<span class="result-tag">${this.escape(String(t).trim())}</span>`).join(' ');
  }

  escape(s) { const div = document.createElement('div'); div.textContent = String(s ?? ''); return div.innerHTML; }

  debounce(fn, wait) {
    let t = null;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn.apply(this, args), wait); };
  }
}
