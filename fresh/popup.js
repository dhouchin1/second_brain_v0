// popup.js - Main popup functionality
class SecondBrainExtension {
    constructor() {
        this.apiUrl = '';
        this.authToken = '';
        this.init();
    }

    async init() {
        await this.loadSettings();
        this.setupEventListeners();
        await this.checkConnection();
        await this.loadRecentCaptures();
    }

    async loadSettings() {
        const settings = await chrome.storage.sync.get(['apiUrl', 'authToken']);
        this.apiUrl = settings.apiUrl || 'http://localhost:8084';
        this.authToken = settings.authToken || '';
    }

    setupEventListeners() {
        // Capture buttons
        document.getElementById('captureSelection').addEventListener('click', () => this.captureSelection());
        document.getElementById('capturePage').addEventListener('click', () => this.capturePage());
        document.getElementById('captureBookmark').addEventListener('click', () => this.captureBookmark());
        document.getElementById('saveManual').addEventListener('click', () => this.saveManualNote());
        
        // Navigation
        document.getElementById('openDashboard').addEventListener('click', () => this.openDashboard());
        document.getElementById('openSettings').addEventListener('click', () => this.openSettings());
        
        // Enter key for manual note
        document.getElementById('manualNote').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                this.saveManualNote();
            }
        });
    }

    async checkConnection() {
        const statusEl = document.getElementById('status');
        try {
            const response = await fetch(`${this.apiUrl}/health`);
            if (response.ok) {
                statusEl.textContent = 'Connected';
                statusEl.className = 'text-xs px-2 py-1 rounded-full bg-green-100 text-green-800';
            } else {
                throw new Error('Server error');
            }
        } catch (error) {
            statusEl.textContent = 'Disconnected';
            statusEl.className = 'text-xs px-2 py-1 rounded-full bg-red-100 text-red-800';
        }
    }

    async getCurrentTab() {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        return tab;
    }

    async captureSelection() {
        const tab = await this.getCurrentTab();
        
        try {
            // Inject content script to get selected text
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: () => {
                    const selection = window.getSelection();
                    if (selection.rangeCount > 0) {
                        const range = selection.getRangeAt(0);
                        const container = document.createElement('div');
                        container.appendChild(range.cloneContents());
                        return {
                            text: selection.toString(),
                            html: container.innerHTML,
                            url: window.location.href,
                            title: document.title
                        };
                    }
                    return null;
                }
            });

            if (result.result && result.result.text) {
                await this.saveToSecondBrain({
                    content: result.result.text,
                    html: result.result.html,
                    url: result.result.url,
                    title: result.result.title,
                    type: 'selection'
                });
            } else {
                this.showMessage('No text selected', 'warning');
            }
        } catch (error) {
            this.showMessage('Failed to capture selection', 'error');
        }
    }

    async capturePage() {
        const tab = await this.getCurrentTab();
        
        try {
            // Extract page content
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: () => {
                    // Remove script tags and other noise
                    const content = document.cloneNode(true);
                    const scripts = content.querySelectorAll('script, style, nav, header, footer, .ad, .advertisement');
                    scripts.forEach(el => el.remove());
                    
                    // Extract main content
                    const main = content.querySelector('main, article, .content, .post, .entry') || content.body;
                    
                    return {
                        text: main.innerText.trim(),
                        html: main.innerHTML,
                        url: window.location.href,
                        title: document.title,
                        meta: {
                            description: document.querySelector('meta[name="description"]')?.content || '',
                            author: document.querySelector('meta[name="author"]')?.content || '',
                            publishDate: document.querySelector('meta[property="article:published_time"]')?.content || ''
                        }
                    };
                }
            });

            await this.saveToSecondBrain({
                content: result.result.text,
                html: result.result.html,
                url: result.result.url,
                title: result.result.title,
                meta: result.result.meta,
                type: 'page'
            });
        } catch (error) {
            this.showMessage('Failed to capture page', 'error');
        }
    }

    async captureBookmark() {
        const tab = await this.getCurrentTab();
        
        try {
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: () => ({
                    url: window.location.href,
                    title: document.title,
                    description: document.querySelector('meta[name="description"]')?.content || '',
                    favicon: document.querySelector('link[rel="icon"]')?.href || 
                            document.querySelector('link[rel="shortcut icon"]')?.href || ''
                })
            });

            await this.saveToSecondBrain({
                content: `Bookmarked: ${result.result.title}\n\n${result.result.description}`,
                url: result.result.url,
                title: result.result.title,
                favicon: result.result.favicon,
                type: 'bookmark'
            });
        } catch (error) {
            this.showMessage('Failed to save bookmark', 'error');
        }
    }

    async saveManualNote() {
        const noteEl = document.getElementById('manualNote');
        const tagsEl = document.getElementById('manualTags');
        const content = noteEl.value.trim();
        
        if (!content) {
            this.showMessage('Please enter a note', 'warning');
            return;
        }

        const tab = await this.getCurrentTab();
        
        try {
            await this.saveToSecondBrain({
                content: content,
                tags: tagsEl.value,
                url: tab.url,
                title: tab.title,
                type: 'manual'
            });
            
            // Clear form
            noteEl.value = '';
            tagsEl.value = '';
        } catch (error) {
            this.showMessage('Failed to save note', 'error');
        }
    }

    async saveToSecondBrain(data) {
        this.showLoading(true);
        
        try {
            // Prepare payload
            const payload = {
                note: data.content,
                tags: this.generateTags(data),
                type: 'browser',
                metadata: {
                    url: data.url,
                    title: data.title,
                    captureType: data.type,
                    html: data.html,
                    meta: data.meta,
                    favicon: data.favicon,
                    timestamp: new Date().toISOString()
                }
            };

            const response = await fetch(`${this.apiUrl}/webhook/browser`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.authToken}`
                },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                this.showMessage('Saved to Second Brain!', 'success');
                await this.loadRecentCaptures();
            } else {
                throw new Error(`Server error: ${response.status}`);
            }
        } catch (error) {
            console.error('Save error:', error);
            this.showMessage('Failed to save. Check connection.', 'error');
        } finally {
            this.showLoading(false);
        }
    }

    generateTags(data) {
        const tags = [];
        
        // Add capture type
        tags.push('web', data.type);
        
        // Extract domain
        if (data.url) {
            try {
                const domain = new URL(data.url).hostname.replace('www.', '');
                tags.push(domain);
            } catch (e) {}
        }
        
        // Add manual tags if provided
        if (data.tags) {
            tags.push(...data.tags.split(',').map(t => t.trim()).filter(Boolean));
        }
        
        return tags.join(',');
    }

    async loadRecentCaptures() {
        try {
            const response = await fetch(`${this.apiUrl}/api/captures/recent?limit=3&type=browser`, {
                headers: {
                    'Authorization': `Bearer ${this.authToken}`
                }
            });
            
            if (response.ok) {
                const captures = await response.json();
                this.displayRecentCaptures(captures);
            }
        } catch (error) {
            console.error('Failed to load recent captures:', error);
        }
    }

    displayRecentCaptures(captures) {
        const listEl = document.getElementById('recentList');
        
        if (!captures.length) {
            listEl.innerHTML = '<div class="text-gray-500 text-xs">No recent captures</div>';
            return;
        }
        
        listEl.innerHTML = captures.map(capture => `
            <div class="flex items-center gap-2 p-2 bg-gray-50 rounded text-xs">
                <span>${this.getTypeIcon(capture.metadata?.captureType)}</span>
                <div class="flex-1 min-w-0">
                    <div class="truncate font-medium">${capture.title || 'Untitled'}</div>
                    <div class="text-gray-500 truncate">${this.formatTime(capture.timestamp)}</div>
                </div>
                <a href="${this.apiUrl}/detail/${capture.id}" target="_blank" 
                   class="text-indigo-600 hover:text-indigo-800">→</a>
            </div>
        `).join('');
    }

    getTypeIcon(type) {
        const icons = {
            selection: '📝',
            page: '📄',
            bookmark: '🔖',
            manual: '✏️'
        };
        return icons[type] || '📄';
    }

    formatTime(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diff = (now - date) / 1000 / 60; // minutes
        
        if (diff < 1) return 'Just now';
        if (diff < 60) return `${Math.floor(diff)}m ago`;
        if (diff < 1440) return `${Math.floor(diff / 60)}h ago`;
        return date.toLocaleDateString();
    }

    showLoading(show) {
        const overlay = document.getElementById('loadingOverlay');
        overlay.classList.toggle('hidden', !show);
    }

    showMessage(message, type = 'info') {
        // Simple toast notification
        const toast = document.createElement('div');
        toast.className = `fixed top-4 right-4 p-3 rounded shadow-lg z-50 ${
            type === 'success' ? 'bg-green-500 text-white' :
            type === 'error' ? 'bg-red-500 text-white' :
            type === 'warning' ? 'bg-yellow-500 text-black' :
            'bg-blue-500 text-white'
        }`;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    openDashboard() {
        chrome.tabs.create({ url: this.apiUrl });
    }

    openSettings() {
        chrome.runtime.openOptionsPage();
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new SecondBrainExtension();
});