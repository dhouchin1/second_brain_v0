/**
 * Advanced Search Enhancement for Dashboard
 * Integrates with the Advanced Search API
 * Provides saved searches, search history, and advanced query features
 */

class AdvancedSearchManager {
    constructor() {
        this.apiBase = '/api/search/advanced';
        this.currentQuery = '';
        this.savedSearches = [];
        this.searchHistory = [];
        this.init();
    }

    async init() {
        try {
            await this.loadSavedSearches();
            await this.loadSearchHistory();
            this.setupEventListeners();
            console.log('Advanced Search Manager initialized');
        } catch (error) {
            console.error('Failed to initialize advanced search:', error);
        }
    }

    setupEventListeners() {
        // Search input handler
        const searchInput = document.getElementById('advancedSearchInput');
        if (searchInput) {
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.performSearch();
                }
            });

            // Real-time suggestions
            searchInput.addEventListener('input', this.debounce((e) => {
                this.getSuggestions(e.target.value);
            }, 300));
        }
    }

    debounce(func, wait) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }

    async performSearch(query = null) {
        const searchInput = document.getElementById('advancedSearchInput');
        this.currentQuery = query || searchInput.value.trim();

        if (!this.currentQuery) {
            this.showMessage('Please enter a search query', 'error');
            return;
        }

        try {
            this.showLoading(true);

            const response = await fetch(`${this.apiBase}/query`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: this.currentQuery,
                    mode: 'hybrid',
                    limit: 50
                })
            });

            const data = await response.json();

            if (data.success) {
                this.displayResults(data.results);
                this.updateResultsCount(data.total_results, data.execution_time_ms);

                // Reload history to show latest search
                setTimeout(() => this.loadSearchHistory(), 500);
            } else {
                throw new Error('Search failed');
            }

        } catch (error) {
            console.error('Search error:', error);
            this.showMessage('Search failed. Please try again.', 'error');
        } finally {
            this.showLoading(false);
        }
    }

    displayResults(results) {
        const container = document.getElementById('searchResultsList');
        const resultsContainer = document.getElementById('searchResultsContainer');
        const noResults = document.getElementById('noResults');

        if (!results || results.length === 0) {
            resultsContainer.classList.remove('hidden');
            container.classList.add('hidden');
            noResults.classList.remove('hidden');
            return;
        }

        resultsContainer.classList.remove('hidden');
        container.classList.remove('hidden');
        noResults.classList.add('hidden');

        container.innerHTML = results.map(result => `
            <div class="glass p-4 rounded-lg hover:bg-slate-700/30 transition-colors cursor-pointer"
                 onclick="viewNote(${result.id})">
                <div class="flex items-start justify-between mb-2">
                    <h4 class="font-semibold text-slate-100 flex-1">${this.escapeHtml(result.title)}</h4>
                    <span class="text-xs text-slate-400 ml-2">${this.formatDate(result.created_at)}</span>
                </div>
                <p class="text-sm text-slate-300 line-clamp-2 mb-2">${this.escapeHtml(result.content)}</p>
                <div class="flex items-center space-x-2 text-xs">
                    ${result.tags && result.tags.length > 0 ? `
                        <div class="flex gap-1">
                            ${result.tags.slice(0, 3).map(tag => `
                                <span class="px-2 py-0.5 bg-blue-500/20 text-blue-300 rounded">${this.escapeHtml(tag)}</span>
                            `).join('')}
                            ${result.tags.length > 3 ? `<span class="text-slate-400">+${result.tags.length - 3}</span>` : ''}
                        </div>
                    ` : ''}
                    ${result.type ? `<span class="text-slate-400">• ${result.type}</span>` : ''}
                    ${result.score ? `<span class="text-slate-500">• ${(result.score * 100).toFixed(0)}% match</span>` : ''}
                </div>
            </div>
        `).join('');
    }

    updateResultsCount(count, time) {
        const countEl = document.getElementById('searchResultsCount');
        if (countEl) {
            countEl.textContent = `${count} results in ${time}ms`;
        }
    }

    async saveCurrentSearch() {
        if (!this.currentQuery) {
            this.showMessage('No search to save', 'error');
            return;
        }

        const name = prompt('Enter a name for this saved search:', this.currentQuery.substring(0, 50));
        if (!name) return;

        try {
            const response = await fetch(`${this.apiBase}/saved`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    query: this.currentQuery
                })
            });

            const data = await response.json();

            if (data.id) {
                this.showMessage('Search saved successfully', 'success');
                await this.loadSavedSearches();
            }

        } catch (error) {
            console.error('Failed to save search:', error);
            this.showMessage('Failed to save search', 'error');
        }
    }

    async loadSavedSearches() {
        try {
            const response = await fetch(`${this.apiBase}/saved`);
            const searches = await response.json();

            this.savedSearches = searches;
            this.renderSavedSearches();

        } catch (error) {
            console.error('Failed to load saved searches:', error);
        }
    }

    renderSavedSearches() {
        const container = document.getElementById('savedSearchesList');
        if (!container) return;

        if (this.savedSearches.length === 0) {
            container.innerHTML = '<p class="text-xs text-slate-400 italic">No saved searches yet</p>';
            return;
        }

        container.innerHTML = this.savedSearches.map(search => `
            <div class="flex items-center justify-between p-2 bg-slate-700/30 rounded hover:bg-slate-700/50 transition-colors">
                <button class="flex-1 text-left text-sm text-slate-200 hover:text-white"
                        onclick="advancedSearchManager.runSavedSearch('${this.escapeHtml(search.query)}')">
                    ${this.escapeHtml(search.name)}
                </button>
                <button class="ml-2 text-slate-400 hover:text-red-400"
                        onclick="advancedSearchManager.deleteSavedSearch(${search.id})">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                    </svg>
                </button>
            </div>
        `).join('');
    }

    async deleteSavedSearch(id) {
        if (!confirm('Delete this saved search?')) return;

        try {
            await fetch(`${this.apiBase}/saved/${id}`, { method: 'DELETE' });
            this.showMessage('Search deleted', 'success');
            await this.loadSavedSearches();

        } catch (error) {
            console.error('Failed to delete saved search:', error);
            this.showMessage('Failed to delete search', 'error');
        }
    }

    runSavedSearch(query) {
        const searchInput = document.getElementById('advancedSearchInput');
        if (searchInput) {
            searchInput.value = query;
        }
        this.performSearch(query);
    }

    async loadSearchHistory() {
        try {
            const response = await fetch(`${this.apiBase}/history?limit=10`);
            const history = await response.json();

            this.searchHistory = history;
            this.renderSearchHistory();

        } catch (error) {
            console.error('Failed to load search history:', error);
        }
    }

    renderSearchHistory() {
        const container = document.getElementById('searchHistoryList');
        if (!container) return;

        if (this.searchHistory.length === 0) {
            container.innerHTML = '<p class="text-xs text-slate-400 italic">No recent searches</p>';
            return;
        }

        container.innerHTML = this.searchHistory.map(item => `
            <button class="w-full text-left p-2 bg-slate-700/30 rounded hover:bg-slate-700/50 transition-colors"
                    onclick="advancedSearchManager.runSavedSearch('${this.escapeHtml(item.query)}')">
                <div class="flex items-center justify-between">
                    <span class="text-sm text-slate-200 truncate flex-1">${this.escapeHtml(item.query)}</span>
                    <span class="text-xs text-slate-400 ml-2">${item.results_count} results</span>
                </div>
                <div class="text-xs text-slate-500 mt-1">${this.formatDate(item.timestamp)}</div>
            </button>
        `).join('');
    }

    async clearSearchHistory() {
        if (!confirm('Clear all search history?')) return;

        try {
            await fetch(`${this.apiBase}/history`, { method: 'DELETE' });
            this.searchHistory = [];
            this.renderSearchHistory();
            this.showMessage('History cleared', 'success');

        } catch (error) {
            console.error('Failed to clear history:', error);
            this.showMessage('Failed to clear history', 'error');
        }
    }

    async getSuggestions(query) {
        if (!query || query.length < 2) {
            this.hideSuggestions();
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/suggestions?q=${encodeURIComponent(query)}`);
            const data = await response.json();

            if (data.suggestions && data.suggestions.length > 0) {
                this.showSuggestions(data.suggestions);
            } else {
                this.hideSuggestions();
            }

        } catch (error) {
            console.error('Failed to get suggestions:', error);
        }
    }

    showSuggestions(suggestions) {
        const container = document.getElementById('searchSuggestions');
        if (!container) return;

        container.innerHTML = suggestions.map(suggestion => `
            <button class="w-full text-left px-3 py-2 hover:bg-slate-300 transition-colors text-sm text-slate-700"
                    onclick="advancedSearchManager.selectSuggestion('${this.escapeHtml(suggestion)}')">
                ${this.escapeHtml(suggestion)}
            </button>
        `).join('');

        container.classList.remove('hidden');
    }

    hideSuggestions() {
        const container = document.getElementById('searchSuggestions');
        if (container) {
            container.classList.add('hidden');
        }
    }

    selectSuggestion(suggestion) {
        const searchInput = document.getElementById('advancedSearchInput');
        if (searchInput) {
            searchInput.value = suggestion;
        }
        this.hideSuggestions();
        this.performSearch(suggestion);
    }

    showLoading(show) {
        const resultsContainer = document.getElementById('searchResultsContainer');
        if (!resultsContainer) return;

        if (show) {
            resultsContainer.classList.remove('hidden');
            document.getElementById('searchResultsList').innerHTML = `
                <div class="text-center py-8 text-slate-400">
                    <div class="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4"></div>
                    <p>Searching...</p>
                </div>
            `;
        }
    }

    showMessage(message, type = 'info') {
        // Use existing toast notification if available
        if (typeof showToast === 'function') {
            showToast(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatDate(dateString) {
        if (!dateString) return '';
        const date = new Date(dateString);
        const now = new Date();
        const diff = now - date;

        // Less than 1 hour
        if (diff < 3600000) {
            const minutes = Math.floor(diff / 60000);
            return `${minutes}m ago`;
        }

        // Less than 1 day
        if (diff < 86400000) {
            const hours = Math.floor(diff / 3600000);
            return `${hours}h ago`;
        }

        // Less than 7 days
        if (diff < 604800000) {
            const days = Math.floor(diff / 86400000);
            return `${days}d ago`;
        }

        // Default format
        return date.toLocaleDateString();
    }
}

// Global functions for onclick handlers
function performAdvancedSearch() {
    if (window.advancedSearchManager) {
        window.advancedSearchManager.performSearch();
    }
}

function saveCurrentSearch() {
    if (window.advancedSearchManager) {
        window.advancedSearchManager.saveCurrentSearch();
    }
}

function clearSearchHistory() {
    if (window.advancedSearchManager) {
        window.advancedSearchManager.clearSearchHistory();
    }
}

function clearSearch() {
    const searchInput = document.getElementById('advancedSearchInput');
    if (searchInput) {
        searchInput.value = '';
    }

    const resultsContainer = document.getElementById('searchResultsContainer');
    if (resultsContainer) {
        resultsContainer.classList.add('hidden');
    }
}

function quickSearch(query) {
    const searchInput = document.getElementById('advancedSearchInput');
    if (searchInput) {
        searchInput.value = query;
    }
    if (window.advancedSearchManager) {
        window.advancedSearchManager.performSearch(query);
    }
}

// Initialize on DOM load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.advancedSearchManager = new AdvancedSearchManager();
    });
} else {
    window.advancedSearchManager = new AdvancedSearchManager();
}
