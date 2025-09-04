// popup.js - Enhanced popup functionality for Second Brain extension
class SecondBrainExtension {
    constructor() {
        this.apiUrl = '';
        this.authToken = '';
        this.connectionStatus = { connected: false, queueSize: 0 };
        this.currentCapture = null;
        this.init();
    }

    async init() {
        await this.loadSettings();
        this.setupEventListeners();
        await this.checkConnection();
        await this.loadRecentCaptures();
        this.updateUI();
    }

    async loadSettings() {
        const settings = await chrome.storage.sync.get([
            'apiUrl', 
            'authToken', 
            'autoSummarize',
            'autoTags',
            'quickCaptureEnabled',
            'smartCaptureEnabled'
        ]);
        
        this.apiUrl = settings.apiUrl || 'http://localhost:8082';
        this.authToken = settings.authToken || '';
        this.settings = settings;
    }

    setupEventListeners() {
        // Enhanced capture buttons
        document.getElementById('captureSelection').addEventListener('click', () => this.captureSelection());
        document.getElementById('capturePage').addEventListener('click', () => this.capturePage());
        document.getElementById('smartCapture').addEventListener('click', () => this.performSmartCapture());
        document.getElementById('captureBookmark').addEventListener('click', () => this.captureBookmark());
        document.getElementById('saveManual').addEventListener('click', () => this.saveManualNote());
        
        // AI enhancement toggles
        document.getElementById('aiSummarize').addEventListener('change', (e) => this.toggleAIFeature('summarize', e.target.checked));
        document.getElementById('aiTags').addEventListener('change', (e) => this.toggleAIFeature('tags', e.target.checked));
        
        // Multi-selection controls
        document.getElementById('toggleMultiSelect').addEventListener('click', () => this.toggleMultiSelection());
        document.getElementById('clearMultiSelect').addEventListener('click', () => this.clearMultiSelection());
        
        // Navigation
        document.getElementById('openDashboard').addEventListener('click', () => this.openDashboard());
        document.getElementById('openSettings').addEventListener('click', () => this.openSettings());
        document.getElementById('showOfflineQueue').addEventListener('click', () => this.showOfflineQueue());
        
        // Quick actions
        document.getElementById('quickActions').addEventListener('change', (e) => this.handleQuickAction(e.target.value));
        
        // Manual note enhancements
        const manualNote = document.getElementById('manualNote');
        const manualTags = document.getElementById('manualTags');
        
        manualNote.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                this.saveManualNote();
            }
        });
        
        // Auto-suggest tags as user types
        manualNote.addEventListener('input', () => this.suggestTags());
        
        // Content preview
        document.getElementById('previewContent').addEventListener('click', () => this.previewCurrentPage());
        
        // Export options
        document.getElementById('exportCapture').addEventListener('click', () => this.exportCurrentCapture());
    }

    async checkConnection() {
        const statusEl = document.getElementById('status');
        const queueEl = document.getElementById('queueStatus');
        
        try {
            // Check API connection
            const response = await fetch(`${this.apiUrl}/health`, { 
                method: 'GET',
                timeout: 5000 
            });
            
            if (response.ok) {
                this.connectionStatus.connected = true;
                statusEl.textContent = 'Connected';
                statusEl.className = 'status-indicator connected';
            } else {
                throw new Error('Server error');
            }
        } catch (error) {
            this.connectionStatus.connected = false;
            statusEl.textContent = 'Offline';
            statusEl.className = 'status-indicator offline';
        }
        
        // Check offline queue
        try {
            const stored = await chrome.storage.local.get(['offlineQueue']);
            this.connectionStatus.queueSize = stored.offlineQueue?.length || 0;
            
            if (this.connectionStatus.queueSize > 0) {
                queueEl.textContent = `${this.connectionStatus.queueSize} queued`;
                queueEl.style.display = 'block';
            } else {
                queueEl.style.display = 'none';
            }
        } catch (error) {
            console.error('Failed to check queue status:', error);
        }
        
        this.updateConnectionUI();
    }

    updateConnectionUI() {
        const syncButton = document.getElementById('syncOffline');
        const connectionInfo = document.getElementById('connectionInfo');
        
        if (this.connectionStatus.connected) {
            connectionInfo.innerHTML = `
                <span class="connection-status connected">🟢 Online</span>
                <span class="server-info">Connected to Second Brain</span>
            `;
            
            if (this.connectionStatus.queueSize > 0) {
                syncButton.style.display = 'block';
                syncButton.onclick = () => this.syncOfflineQueue();
            } else {
                syncButton.style.display = 'none';
            }
        } else {
            connectionInfo.innerHTML = `
                <span class="connection-status offline">🔴 Offline</span>
                <span class="server-info">Captures will be queued</span>
            `;
            syncButton.style.display = 'none';
        }
    }

    async getCurrentTab() {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        return tab;
    }

    async captureSelection() {
        const tab = await this.getCurrentTab();
        this.setLoading('captureSelection', true);
        
        try {
            // Enhanced selection capture with content analysis
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: this.extractSelectionWithContext
            });

            if (result.result && result.result.text) {
                const captureData = {
                    content: result.result.text,
                    context: result.result.context,
                    analysis: result.result.analysis,
                    url: tab.url,
                    title: tab.title,
                    type: 'selection'
                };
                
                await this.saveCapture(captureData);
                this.showMessage('Selection captured successfully! 📝', 'success');
            } else {
                this.showMessage('No text selected', 'warning');
            }
        } catch (error) {
            console.error('Selection capture failed:', error);
            this.showMessage('Failed to capture selection', 'error');
        } finally {
            this.setLoading('captureSelection', false);
        }
    }

    async capturePage() {
        const tab = await this.getCurrentTab();
        this.setLoading('capturePage', true);
        
        try {
            // Enhanced page capture with readability analysis
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: this.extractPageWithAnalysis
            });

            const captureData = {
                content: result.result.content,
                analysis: result.result.analysis,
                metadata: result.result.metadata,
                url: tab.url,
                title: tab.title,
                type: 'page'
            };
            
            await this.saveCapture(captureData);
            this.showMessage('Page captured successfully! 📄', 'success');
        } catch (error) {
            console.error('Page capture failed:', error);
            this.showMessage('Failed to capture page', 'error');
        } finally {
            this.setLoading('capturePage', false);
        }
    }

    async performSmartCapture() {
        const tab = await this.getCurrentTab();
        this.setLoading('smartCapture', true);
        this.showProcessingMessage('🧠 AI analyzing content...');
        
        try {
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: this.performIntelligentExtraction
            });

            const captureData = {
                ...result.result,
                url: tab.url,
                title: tab.title,
                type: 'smart-capture',
                aiEnhanced: true
            };
            
            await this.saveCaptureWithAI(captureData);
            this.showMessage('Smart capture completed! 🤖🧠', 'success');
        } catch (error) {
            console.error('Smart capture failed:', error);
            this.showMessage('Smart capture failed', 'error');
        } finally {
            this.setLoading('smartCapture', false);
            this.hideProcessingMessage();
        }
    }

    async captureBookmark() {
        const tab = await this.getCurrentTab();
        this.setLoading('captureBookmark', true);
        
        try {
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: this.extractBookmarkData
            });

            const captureData = {
                content: `# ${result.result.title}\n\n${result.result.description}\n\n**URL**: ${result.result.url}`,
                metadata: result.result,
                url: tab.url,
                title: tab.title,
                type: 'bookmark'
            };
            
            await this.saveCapture(captureData);
            this.showMessage('Bookmark saved! 🔖', 'success');
        } catch (error) {
            console.error('Bookmark capture failed:', error);
            this.showMessage('Failed to save bookmark', 'error');
        } finally {
            this.setLoading('captureBookmark', false);
        }
    }

    async saveManualNote() {
        const noteEl = document.getElementById('manualNote');
        const tagsEl = document.getElementById('manualTags');
        const content = noteEl.value.trim();
        
        if (!content) {
            this.showMessage('Please enter a note', 'warning');
            noteEl.focus();
            return;
        }

        const tab = await this.getCurrentTab();
        this.setLoading('saveManual', true);
        
        try {
            const captureData = {
                content: content,
                tags: tagsEl.value,
                url: tab.url,
                title: tab.title,
                type: 'manual',
                timestamp: new Date().toISOString()
            };
            
            await this.saveCapture(captureData);
            
            // Clear form
            noteEl.value = '';
            tagsEl.value = '';
            
            this.showMessage('Note saved successfully! ✏️', 'success');
        } catch (error) {
            console.error('Manual note save failed:', error);
            this.showMessage('Failed to save note', 'error');
        } finally {
            this.setLoading('saveManual', false);
        }
    }

    async saveCapture(captureData) {
        const aiEnhanced = captureData.aiEnhanced || 
                          (this.settings.autoSummarize || this.settings.autoTags);
        
        const payload = {
            note: captureData.content,
            tags: this.generateTags(captureData),
            type: 'browser',
            metadata: {
                url: captureData.url,
                title: captureData.title,
                captureType: captureData.type,
                timestamp: captureData.timestamp || new Date().toISOString(),
                analysis: captureData.analysis,
                metadata: captureData.metadata,
                context: captureData.context
            }
        };
        
        if (aiEnhanced) {
            payload.aiProcessing = {
                summarize: this.settings.autoSummarize || captureData.summarize,
                generateTags: this.settings.autoTags || captureData.generateTags,
                extractKeyPoints: captureData.extractKeyPoints,
                analyzeSentiment: captureData.analyzeSentiment
            };
        }

        // Store current capture for potential export
        this.currentCapture = { ...captureData, payload };

        return this.sendToBackground(aiEnhanced ? 'saveContentWithAI' : 'saveContent', payload);
    }

    async saveCaptureWithAI(captureData) {
        const payload = {
            note: captureData.content,
            tags: captureData.tags || this.generateTags(captureData),
            type: 'browser',
            aiProcessing: {
                smartExtraction: true,
                summarize: true,
                generateTags: true,
                extractKeyPoints: true,
                analyzeSentiment: true
            },
            metadata: {
                url: captureData.url,
                title: captureData.title,
                captureType: captureData.type,
                timestamp: new Date().toISOString(),
                intelligentAnalysis: captureData.analysis,
                confidence: captureData.confidence,
                contentType: captureData.contentType
            }
        };

        this.currentCapture = { ...captureData, payload };

        return this.sendToBackground('saveContentWithAI', payload);
    }

    // Content extraction functions (run in page context)
    extractSelectionWithContext() {
        const selection = window.getSelection();
        if (selection.rangeCount === 0) return null;
        
        const range = selection.getRangeAt(0);
        const selectedText = selection.toString().trim();
        
        if (!selectedText) return null;
        
        // Get surrounding context
        const container = range.commonAncestorContainer;
        const paragraph = container.nodeType === Node.TEXT_NODE 
            ? container.parentElement 
            : container;
        
        const context = paragraph.innerText || paragraph.textContent || '';
        
        // Analyze content
        const analysis = {
            wordCount: selectedText.split(/\s+/).length,
            hasCode: /function\s*\(|class\s+\w+|\{[\s\S]*\}/.test(selectedText),
            hasLinks: selectedText.includes('http'),
            language: selectedText.length > 50 ? 'prose' : 'fragment'
        };
        
        return {
            text: selectedText,
            context: context.substring(0, 500),
            analysis: analysis,
            position: {
                x: range.getBoundingClientRect().left,
                y: range.getBoundingClientRect().top
            }
        };
    }

    extractPageWithAnalysis() {
        // Find main content
        const contentSelectors = [
            'article', 'main', '[role="main"]', '.content', '.post', 
            '.entry', '.article', '#content', '#main'
        ];
        
        let mainContent = document.body;
        let bestScore = 0;
        
        contentSelectors.forEach(selector => {
            const element = document.querySelector(selector);
            if (element) {
                const score = element.innerText?.length || 0;
                if (score > bestScore) {
                    bestScore = score;
                    mainContent = element;
                }
            }
        });
        
        // Clean content
        const clone = mainContent.cloneNode(true);
        const unwanted = clone.querySelectorAll('script, style, nav, header, footer, .ad, .sidebar, .menu, .comments');
        unwanted.forEach(el => el.remove());
        
        const text = clone.innerText.trim();
        const words = text.split(/\s+/).length;
        
        // Analysis
        const analysis = {
            wordCount: words,
            estimatedReadingTime: Math.ceil(words / 200),
            hasImages: document.querySelectorAll('img').length,
            hasCode: document.querySelectorAll('pre, code').length > 0,
            hasVideo: document.querySelectorAll('video, iframe[src*="youtube"], iframe[src*="vimeo"]').length > 0,
            readabilityScore: this.calculateReadability(text)
        };
        
        // Metadata
        const metadata = {
            description: document.querySelector('meta[name="description"]')?.content || '',
            author: document.querySelector('meta[name="author"]')?.content || '',
            publishDate: document.querySelector('meta[property="article:published_time"]')?.content || 
                         document.querySelector('meta[name="date"]')?.content || '',
            keywords: document.querySelector('meta[name="keywords"]')?.content || '',
            language: document.documentElement.lang || 'en',
            favicon: document.querySelector('link[rel="icon"]')?.href || 
                    document.querySelector('link[rel="shortcut icon"]')?.href || ''
        };
        
        return {
            content: `# ${document.title}\n\n${text}`,
            analysis: analysis,
            metadata: metadata
        };
    }

    calculateReadability(text) {
        const sentences = text.split(/[.!?]+/).length;
        const words = text.split(/\s+/).length;
        const syllables = text.match(/[aeiouAEIOU]/g)?.length || 0;
        
        if (sentences === 0 || words === 0) return 50;
        
        const avgWordsPerSentence = words / sentences;
        const avgSyllablesPerWord = syllables / words;
        
        return Math.max(0, Math.min(100, 
            206.835 - (1.015 * avgWordsPerSentence) - (84.6 * avgSyllablesPerWord)
        ));
    }

    performIntelligentExtraction() {
        // Advanced content extraction with AI-like analysis
        const extractor = {
            extractMainContent() {
                const candidates = [
                    document.querySelector('article'),
                    document.querySelector('main'),
                    document.querySelector('[role="main"]'),
                    document.querySelector('.content'),
                    document.querySelector('.post')
                ].filter(Boolean);
                
                if (candidates.length === 0) candidates.push(document.body);
                
                return candidates.reduce((best, candidate) => {
                    const score = this.scoreElement(candidate);
                    return score > (best.score || 0) ? {element: candidate, score} : best;
                }, {element: document.body, score: 0}).element;
            },
            
            scoreElement(element) {
                const textLength = element.innerText?.length || 0;
                const paragraphs = element.querySelectorAll('p').length;
                const headers = element.querySelectorAll('h1,h2,h3,h4,h5,h6').length;
                const links = element.querySelectorAll('a').length;
                
                return (textLength * 0.4) + (paragraphs * 15) + (headers * 10) - (links * 2);
            },
            
            extractKeyTopics(text) {
                const words = text.toLowerCase()
                    .replace(/[^\w\s]/g, ' ')
                    .split(/\s+/)
                    .filter(word => word.length > 3);
                
                const frequency = {};
                words.forEach(word => {
                    frequency[word] = (frequency[word] || 0) + 1;
                });
                
                return Object.entries(frequency)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 5)
                    .map(([word]) => word);
            },
            
            analyzeSentiment(text) {
                const positive = ['good', 'great', 'excellent', 'amazing', 'wonderful', 'fantastic', 'love', 'perfect'];
                const negative = ['bad', 'terrible', 'awful', 'horrible', 'hate', 'disappointing', 'worst'];
                
                const words = text.toLowerCase().split(/\s+/);
                const positiveCount = words.filter(word => positive.includes(word)).length;
                const negativeCount = words.filter(word => negative.includes(word)).length;
                
                if (positiveCount > negativeCount) return 'positive';
                if (negativeCount > positiveCount) return 'negative';
                return 'neutral';
            }
        };
        
        const mainElement = extractor.extractMainContent();
        const cleanElement = mainElement.cloneNode(true);
        
        // Remove unwanted elements
        cleanElement.querySelectorAll('script, style, nav, header, footer, aside, .sidebar, .ad, .menu, .comments').forEach(el => el.remove());
        
        const content = `# ${document.title}\n\n${cleanElement.innerText.trim()}`;
        const topics = extractor.extractKeyTopics(content);
        const sentiment = extractor.analyzeSentiment(content);
        const wordCount = content.split(/\s+/).length;
        
        return {
            content: content,
            analysis: {
                topics: topics,
                sentiment: sentiment,
                wordCount: wordCount,
                readingTime: Math.ceil(wordCount / 200),
                complexity: wordCount > 1000 ? 'high' : wordCount > 300 ? 'medium' : 'low'
            },
            tags: ['web', 'smart-capture', ...topics.slice(0, 3), sentiment].join(','),
            confidence: Math.min(1.0, 0.5 + (wordCount > 100 ? 0.2 : 0) + (topics.length > 0 ? 0.2 : 0) + (sentiment !== 'neutral' ? 0.1 : 0)),
            contentType: this.detectContentType(content)
        };
    }

    detectContentType(content) {
        if (content.match(/```|<code>/i)) return 'technical';
        if (content.match(/recipe|ingredients|cooking|instructions/i)) return 'recipe';
        if (content.match(/tutorial|how to|step by step|guide/i)) return 'tutorial';
        if (content.match(/news|breaking|report|journalist/i)) return 'news';
        if (content.match(/research|study|analysis|data/i)) return 'research';
        return 'article';
    }

    extractBookmarkData() {
        return {
            url: window.location.href,
            title: document.title,
            description: document.querySelector('meta[name="description"]')?.content || 
                        document.querySelector('meta[property="og:description"]')?.content || '',
            image: document.querySelector('meta[property="og:image"]')?.content || 
                  document.querySelector('link[rel="apple-touch-icon"]')?.href ||
                  document.querySelector('link[rel="icon"]')?.href || '',
            favicon: document.querySelector('link[rel="icon"]')?.href || 
                    document.querySelector('link[rel="shortcut icon"]')?.href || '',
            siteName: document.querySelector('meta[property="og:site_name"]')?.content || 
                     new URL(window.location.href).hostname,
            type: document.querySelector('meta[property="og:type"]')?.content || 'website'
        };
    }

    async toggleMultiSelection() {
        const tab = await this.getCurrentTab();
        await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            function: () => {
                window.postMessage({ action: 'toggleMultiSelection' }, '*');
            }
        });
        this.showMessage('Multi-selection mode toggled', 'info');
    }

    async clearMultiSelection() {
        const tab = await this.getCurrentTab();
        await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            function: () => {
                window.postMessage({ action: 'clearMultiSelection' }, '*');
            }
        });
        this.showMessage('Multi-selection cleared', 'info');
    }

    generateTags(captureData) {
        const tags = ['web', captureData.type];
        
        // Add domain tag
        try {
            const domain = new URL(captureData.url).hostname.replace('www.', '');
            tags.push(domain);
        } catch (e) {}
        
        // Add analysis-based tags
        if (captureData.analysis) {
            if (captureData.analysis.hasCode) tags.push('code');
            if (captureData.analysis.hasLinks) tags.push('links');
            if (captureData.analysis.hasImages > 0) tags.push('images');
            if (captureData.analysis.hasVideo) tags.push('video');
            if (captureData.analysis.topics) tags.push(...captureData.analysis.topics.slice(0, 3));
        }
        
        // Add manual tags if provided
        if (captureData.tags) {
            tags.push(...captureData.tags.split(',').map(t => t.trim()).filter(Boolean));
        }
        
        return [...new Set(tags)].join(',');
    }

    async suggestTags() {
        const noteText = document.getElementById('manualNote').value;
        if (noteText.length < 10) return;
        
        // Simple tag suggestion based on content
        const suggestions = [];
        
        if (noteText.match(/todo|task|reminder/i)) suggestions.push('task');
        if (noteText.match(/idea|thought|concept/i)) suggestions.push('idea');
        if (noteText.match(/quote|said|mentioned/i)) suggestions.push('quote');
        if (noteText.match(/meeting|call|discussion/i)) suggestions.push('meeting');
        if (noteText.match(/code|function|programming/i)) suggestions.push('code');
        if (noteText.match(/book|read|article/i)) suggestions.push('reading');
        
        const suggestionsEl = document.getElementById('tagSuggestions');
        if (suggestions.length > 0 && suggestionsEl) {
            suggestionsEl.innerHTML = suggestions.map(tag => 
                `<span class="tag-suggestion" onclick="this.addTag('${tag}')">${tag}</span>`
            ).join('');
            suggestionsEl.style.display = 'block';
        } else if (suggestionsEl) {
            suggestionsEl.style.display = 'none';
        }
    }

    addTag(tag) {
        const tagsEl = document.getElementById('manualTags');
        const currentTags = tagsEl.value.split(',').map(t => t.trim()).filter(Boolean);
        
        if (!currentTags.includes(tag)) {
            currentTags.push(tag);
            tagsEl.value = currentTags.join(', ');
        }
        
        document.getElementById('tagSuggestions').style.display = 'none';
    }

    async previewCurrentPage() {
        const tab = await this.getCurrentTab();
        
        try {
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: () => {
                    const preview = {
                        title: document.title,
                        url: window.location.href,
                        wordCount: document.body.innerText.split(/\s+/).length,
                        images: document.querySelectorAll('img').length,
                        links: document.querySelectorAll('a').length,
                        headings: Array.from(document.querySelectorAll('h1,h2,h3')).map(h => h.innerText).slice(0, 5)
                    };
                    return preview;
                }
            });
            
            this.showPreview(result.result);
        } catch (error) {
            this.showMessage('Failed to preview page', 'error');
        }
    }

    showPreview(preview) {
        const modal = document.createElement('div');
        modal.className = 'preview-modal';
        modal.innerHTML = `
            <div class="preview-content">
                <div class="preview-header">
                    <h3>Page Preview</h3>
                    <button class="close-preview">×</button>
                </div>
                <div class="preview-details">
                    <p><strong>Title:</strong> ${preview.title}</p>
                    <p><strong>URL:</strong> ${preview.url}</p>
                    <p><strong>Word Count:</strong> ${preview.wordCount}</p>
                    <p><strong>Images:</strong> ${preview.images}</p>
                    <p><strong>Links:</strong> ${preview.links}</p>
                    ${preview.headings.length > 0 ? `
                        <p><strong>Headings:</strong></p>
                        <ul>
                            ${preview.headings.map(h => `<li>${h}</li>`).join('')}
                        </ul>
                    ` : ''}
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        modal.querySelector('.close-preview').onclick = () => modal.remove();
        modal.onclick = (e) => {
            if (e.target === modal) modal.remove();
        };
    }

    async exportCurrentCapture() {
        if (!this.currentCapture) {
            this.showMessage('No recent capture to export', 'warning');
            return;
        }
        
        const exportData = {
            content: this.currentCapture.content,
            metadata: this.currentCapture.payload.metadata,
            timestamp: new Date().toISOString(),
            source: 'Second Brain Browser Extension'
        };
        
        const blob = new Blob([JSON.stringify(exportData, null, 2)], { 
            type: 'application/json' 
        });
        
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `second-brain-capture-${Date.now()}.json`;
        a.click();
        
        URL.revokeObjectURL(url);
        this.showMessage('Capture exported! 📁', 'success');
    }

    async handleQuickAction(action) {
        if (!action) return;
        
        switch (action) {
            case 'screenshot':
                await this.takeScreenshot();
                break;
            case 'fullPage':
                await this.captureFullPage();
                break;
            case 'visibleArea':
                await this.captureVisibleArea();
                break;
            case 'selectedArea':
                await this.captureSelectedArea();
                break;
        }
        
        // Reset dropdown
        document.getElementById('quickActions').value = '';
    }

    async takeScreenshot() {
        try {
            const tab = await this.getCurrentTab();
            const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
            
            const captureData = {
                content: `# Screenshot from ${tab.title}\n\n![Screenshot](${dataUrl})`,
                url: tab.url,
                title: tab.title,
                type: 'screenshot',
                metadata: { screenshotData: dataUrl }
            };
            
            await this.saveCapture(captureData);
            this.showMessage('Screenshot captured! 📸', 'success');
        } catch (error) {
            this.showMessage('Failed to capture screenshot', 'error');
        }
    }

    async toggleAIFeature(feature, enabled) {
        const settings = { ...this.settings };
        
        if (feature === 'summarize') {
            settings.autoSummarize = enabled;
        } else if (feature === 'tags') {
            settings.autoTags = enabled;
        }
        
        await chrome.storage.sync.set(settings);
        this.settings = settings;
        
        this.showMessage(`AI ${feature} ${enabled ? 'enabled' : 'disabled'}`, 'info');
    }

    async syncOfflineQueue() {
        this.setLoading('syncOffline', true);
        
        try {
            const response = await this.sendToBackground('syncOfflineQueue', {});
            await this.checkConnection(); // Refresh status
            this.showMessage('Offline queue synced! 🔄', 'success');
        } catch (error) {
            this.showMessage('Failed to sync queue', 'error');
        } finally {
            this.setLoading('syncOffline', false);
        }
    }

    async showOfflineQueue() {
        try {
            const stored = await chrome.storage.local.get(['offlineQueue']);
            const queue = stored.offlineQueue || [];
            
            if (queue.length === 0) {
                this.showMessage('Offline queue is empty', 'info');
                return;
            }
            
            const modal = document.createElement('div');
            modal.className = 'queue-modal';
            modal.innerHTML = `
                <div class="queue-content">
                    <div class="queue-header">
                        <h3>Offline Queue (${queue.length} items)</h3>
                        <button class="close-queue">×</button>
                    </div>
                    <div class="queue-list">
                        ${queue.map((item, index) => `
                            <div class="queue-item">
                                <div class="queue-item-content">
                                    <strong>${item.payload.metadata?.title || 'Untitled'}</strong>
                                    <small>${new Date(item.timestamp).toLocaleString()}</small>
                                </div>
                                <div class="queue-item-type">${item.payload.metadata?.captureType || 'unknown'}</div>
                            </div>
                        `).join('')}
                    </div>
                    <div class="queue-actions">
                        <button class="btn-sync-all" onclick="this.syncOfflineQueue()">Sync All</button>
                        <button class="btn-clear-queue" onclick="this.clearOfflineQueue()">Clear Queue</button>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            modal.querySelector('.close-queue').onclick = () => modal.remove();
        } catch (error) {
            this.showMessage('Failed to load queue', 'error');
        }
    }

    async clearOfflineQueue() {
        await chrome.storage.local.set({ offlineQueue: [] });
        await this.checkConnection(); // Refresh status
        document.querySelector('.queue-modal')?.remove();
        this.showMessage('Offline queue cleared', 'info');
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
            // Fail silently for recent captures
            console.error('Failed to load recent captures:', error);
        }
    }

    displayRecentCaptures(captures) {
        const listEl = document.getElementById('recentCaptures');
        
        if (!captures || captures.length === 0) {
            listEl.innerHTML = '<div class="empty-state">No recent captures</div>';
            return;
        }
        
        listEl.innerHTML = captures.map(capture => `
            <div class="capture-item">
                <div class="capture-icon">${this.getTypeIcon(capture.metadata?.captureType)}</div>
                <div class="capture-details">
                    <div class="capture-title">${capture.title || 'Untitled'}</div>
                    <div class="capture-meta">
                        <span class="capture-time">${this.formatTime(capture.timestamp)}</span>
                        <span class="capture-type">${capture.metadata?.captureType || 'unknown'}</span>
                    </div>
                </div>
                <a href="${this.apiUrl}/note/${capture.id}" target="_blank" class="capture-link">→</a>
            </div>
        `).join('');
    }

    getTypeIcon(type) {
        const icons = {
            selection: '📝',
            page: '📄',
            'smart-capture': '🧠',
            bookmark: '🔖',
            manual: '✏️',
            screenshot: '📸',
            code: '💻',
            image: '🖼️',
            video: '🎥'
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

    async sendToBackground(action, payload) {
        return new Promise((resolve, reject) => {
            chrome.runtime.sendMessage({ action, payload }, (response) => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                } else if (response?.error) {
                    reject(new Error(response.error));
                } else {
                    resolve(response);
                }
            });
        });
    }

    setLoading(buttonId, isLoading) {
        const button = document.getElementById(buttonId);
        if (!button) return;
        
        if (isLoading) {
            button.disabled = true;
            button.dataset.originalText = button.textContent;
            button.innerHTML = '<span class="loading-spinner"></span> Processing...';
        } else {
            button.disabled = false;
            button.textContent = button.dataset.originalText || button.textContent;
        }
    }

    showProcessingMessage(message) {
        const existing = document.getElementById('processing-message');
        if (existing) existing.remove();
        
        const messageEl = document.createElement('div');
        messageEl.id = 'processing-message';
        messageEl.className = 'processing-message';
        messageEl.innerHTML = `
            <div class="processing-content">
                <div class="processing-spinner"></div>
                <span>${message}</span>
            </div>
        `;
        
        document.body.appendChild(messageEl);
    }

    hideProcessingMessage() {
        const messageEl = document.getElementById('processing-message');
        if (messageEl) messageEl.remove();
    }

    showMessage(message, type = 'info') {
        const messageEl = document.getElementById('message');
        if (!messageEl) return;
        
        messageEl.textContent = message;
        messageEl.className = `message ${type}`;
        messageEl.style.display = 'block';
        
        setTimeout(() => {
            messageEl.style.display = 'none';
        }, 3000);
    }

    updateUI() {
        // Update AI toggle states
        document.getElementById('aiSummarize').checked = this.settings.autoSummarize || false;
        document.getElementById('aiTags').checked = this.settings.autoTags || false;
        
        // Show/hide features based on settings
        if (this.settings.smartCaptureEnabled !== false) {
            document.getElementById('smartCapture').style.display = 'block';
        }
        
        if (this.settings.quickCaptureEnabled !== false) {
            document.getElementById('quickActions').style.display = 'block';
        }
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