// Enhanced popup functionality for Second Brain extension with AI capabilities
class SecondBrainExtension {
    constructor() {
        this.apiUrl = '';
        this.authToken = '';
        this.connectionStatus = { connected: false, queueSize: 0 };
        this.currentCapture = null;
        this.multiSelectMode = false;
        this.selectedElements = [];
        this.recentCaptures = [];
        this.init();
    }

    async init() {
        await this.loadSettings();
        this.setupEventListeners();
        await this.checkConnection();
        await this.loadRecentCaptures();
        await this.detectPageContent();
        this.updateUI();
    }

    async loadSettings() {
        const settings = await chrome.storage.sync.get([
            'apiUrl', 
            'authToken', 
            'autoSummarize',
            'autoTags',
            'quickCaptureEnabled',
            'smartCaptureEnabled',
            'aiProcessingEnabled',
            'duplicateDetection',
            'contextPreservation'
        ]);
        
        this.apiUrl = settings.apiUrl || 'http://localhost:8082';
        this.authToken = settings.authToken || '';
        this.settings = {
            autoSummarize: settings.autoSummarize !== false,
            autoTags: settings.autoTags !== false,
            smartCaptureEnabled: settings.smartCaptureEnabled !== false,
            aiProcessingEnabled: settings.aiProcessingEnabled !== false,
            duplicateDetection: settings.duplicateDetection !== false,
            contextPreservation: settings.contextPreservation !== false,
            ...settings
        };
    }

    setupEventListeners() {
        // Instant capture buttons
        document.getElementById('instantSelection').addEventListener('click', () => this.instantCaptureSelection());
        document.getElementById('instantPage').addEventListener('click', () => this.instantCapturePage());
        document.getElementById('instantBookmark').addEventListener('click', () => this.instantBookmark());
        
        // Enhanced capture buttons
        document.getElementById('captureSelection').addEventListener('click', () => this.captureSelection());
        document.getElementById('capturePage').addEventListener('click', () => this.capturePage());
        document.getElementById('smartCapture').addEventListener('click', () => this.performSmartCapture());
        document.getElementById('captureBookmark').addEventListener('click', () => this.captureBookmark());
        document.getElementById('saveManual').addEventListener('click', () => this.saveManualNote());
        
        // AI-powered capture buttons
        document.getElementById('captureArticle').addEventListener('click', () => this.captureArticle());
        document.getElementById('captureCode').addEventListener('click', () => this.captureCode());
        document.getElementById('captureTable').addEventListener('click', () => this.captureTable());
        
        // Multi-selection controls
        document.getElementById('toggleMultiSelect').addEventListener('click', () => this.toggleMultiSelection());
        document.getElementById('clearMultiSelect').addEventListener('click', () => this.clearMultiSelection());
        document.getElementById('captureMultiSelect').addEventListener('click', () => this.captureMultiSelection());
        
        // AI enhancement toggles
        document.getElementById('aiSummarize').addEventListener('change', (e) => this.toggleAIFeature('summarize', e.target.checked));
        document.getElementById('aiTags').addEventListener('change', (e) => this.toggleAIFeature('tags', e.target.checked));
        document.getElementById('duplicateCheck').addEventListener('change', (e) => this.toggleAIFeature('duplicateCheck', e.target.checked));
        
        // Tag input with suggestions
        const tagInput = document.getElementById('manualTags');
        tagInput.addEventListener('input', (e) => this.handleTagInput(e));
        tagInput.addEventListener('keydown', (e) => this.handleTagKeydown(e));
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyboardShortcuts(e));
        
        // Navigation
        document.getElementById('openDashboard').addEventListener('click', () => this.openDashboard());
        document.getElementById('openSettings').addEventListener('click', () => this.openSettings());
        
        // Real-time updates
        this.startRealtimeUpdates();
    }

    // Instant capture methods for frictionless operation
    async instantCaptureSelection() {
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            const result = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: () => window.getSelection().toString().trim()
            });
            
            if (result[0]?.result) {
                this.showProgress('Instantly saving selection...');
                await this.processCapturedContent({
                    title: 'Selected Text',
                    content: result[0].result,
                    url: tab.url,
                    type: 'instant-selection'
                }, 'instant-selection');
                window.close(); // Auto-close popup for instant feel
            } else {
                this.showError('No text selected');
            }
        } catch (error) {
            this.showError('Failed to capture selection: ' + error.message);
        }
    }

    async instantCapturePage() {
        try {
            this.showProgress('Instantly saving page...');
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            
            // Quick page capture without heavy processing
            const payload = {
                title: tab.title,
                url: tab.url,
                content: `# ${tab.title}\n\n**URL**: ${tab.url}\n\n*Instant capture from ${new Date().toLocaleString()}*`,
                type: 'instant-page',
                timestamp: new Date().toISOString()
            };
            
            await this.processCapturedContent(payload, 'instant-page');
            window.close(); // Auto-close for speed
        } catch (error) {
            this.showError('Failed to capture page: ' + error.message);
        }
    }

    async instantBookmark() {
        try {
            this.showProgress('Creating instant bookmark...');
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            
            const payload = {
                title: `📖 ${tab.title}`,
                url: tab.url, 
                content: `# ${tab.title}\n\n**URL**: [${tab.url}](${tab.url})\n\n**Bookmarked**: ${new Date().toLocaleString()}\n\n---\n\n*Quick bookmark for later reference*`,
                type: 'instant-bookmark',
                timestamp: new Date().toISOString()
            };
            
            await this.processCapturedContent(payload, 'instant-bookmark');
            window.close(); // Auto-close for instant feel
        } catch (error) {
            this.showError('Failed to create bookmark: ' + error.message);
        }
    }

    async detectPageContent() {
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            
            // Inject content detection script
            const results = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: this.analyzePageContent
            });
            
            if (results[0]?.result) {
                this.pageAnalysis = results[0].result;
                this.updateContentSuggestions();
                this.updateInstantActions();
            }
        } catch (error) {
            console.error('Content detection failed:', error);
        }
    }

    // Content analysis function that runs in page context
    analyzePageContent() {
        const analysis = {
            hasArticle: false,
            hasCodeBlocks: false,
            hasTables: false,
            hasImages: false,
            hasSelection: false,
            contentTypes: [],
            suggestedTags: [],
            readabilityScore: 0,
            wordCount: 0
        };

        // Check for article content
        const articleSelectors = ['article', '[role="main"]', '.post', '.article', '.content'];
        const articleElement = articleSelectors.find(sel => document.querySelector(sel));
        if (articleElement) {
            analysis.hasArticle = true;
            analysis.contentTypes.push('article');
        }

        // Check for code blocks
        const codeElements = document.querySelectorAll('pre, code, .highlight, .code-block');
        if (codeElements.length > 0) {
            analysis.hasCodeBlocks = true;
            analysis.contentTypes.push('code');
        }

        // Check for tables
        const tables = document.querySelectorAll('table');
        if (tables.length > 0) {
            analysis.hasTables = true;
            analysis.contentTypes.push('table');
        }

        // Check for images
        const images = document.querySelectorAll('img');
        if (images.length > 0) {
            analysis.hasImages = true;
            analysis.contentTypes.push('images');
        }

        // Check for user selection
        const selection = window.getSelection();
        if (selection.toString().trim().length > 0) {
            analysis.hasSelection = true;
            analysis.selectedText = selection.toString();
            analysis.wordCount = selection.toString().split(/\s+/).length;
        }

        // Extract potential tags from page
        const title = document.title;
        const metaKeywords = document.querySelector('meta[name="keywords"]')?.content || '';
        const domain = window.location.hostname;
        
        analysis.suggestedTags = this.extractTags(title, metaKeywords, domain);
        
        // Calculate basic readability score
        const textContent = document.body.innerText;
        analysis.wordCount = textContent.split(/\s+/).length;
        analysis.readabilityScore = this.calculateReadability(textContent);

        return analysis;
    }

    extractTags(title, keywords, domain) {
        const tags = new Set();
        
        // Add domain-based tag
        if (domain.includes('github')) tags.add('github');
        if (domain.includes('stackoverflow')) tags.add('programming');
        if (domain.includes('medium') || domain.includes('substack')) tags.add('article');
        if (domain.includes('youtube')) tags.add('video');
        if (domain.includes('docs.') || domain.includes('documentation')) tags.add('documentation');
        
        // Extract from title
        const titleWords = title.toLowerCase()
            .replace(/[^\w\s]/g, ' ')
            .split(/\s+/)
            .filter(word => word.length > 3)
            .slice(0, 3);
        titleWords.forEach(word => tags.add(word));
        
        // Extract from keywords
        if (keywords) {
            keywords.split(',')
                .map(k => k.trim().toLowerCase())
                .filter(k => k.length > 2)
                .slice(0, 5)
                .forEach(keyword => tags.add(keyword));
        }
        
        return Array.from(tags);
    }

    calculateReadability(text) {
        // Simple readability score based on sentence and word length
        const sentences = text.split(/[.!?]+/).length;
        const words = text.split(/\s+/).length;
        const avgWordsPerSentence = words / sentences;
        
        // Score from 1-10 (10 = most readable)
        if (avgWordsPerSentence < 10) return 9;
        if (avgWordsPerSentence < 15) return 7;
        if (avgWordsPerSentence < 20) return 5;
        if (avgWordsPerSentence < 25) return 3;
        return 1;
    }

    updateContentSuggestions() {
        const suggestionsContainer = document.getElementById('contentSuggestions');
        if (!this.pageAnalysis || !suggestionsContainer) return;

        const suggestions = [];
        
        if (this.pageAnalysis.hasSelection) {
            suggestions.push({
                icon: '📝',
                text: `Selected text (${this.pageAnalysis.wordCount} words)`,
                action: () => this.captureSelection(),
                primary: true
            });
        }
        
        if (this.pageAnalysis.hasArticle) {
            suggestions.push({
                icon: '📰',
                text: 'Smart article extraction',
                action: () => this.captureArticle(),
                primary: !this.pageAnalysis.hasSelection
            });
        }
        
        if (this.pageAnalysis.hasCodeBlocks) {
            suggestions.push({
                icon: '💻',
                text: 'Code snippets detected',
                action: () => this.captureCode()
            });
        }
        
        if (this.pageAnalysis.hasTables) {
            suggestions.push({
                icon: '📊',
                text: 'Data tables found',
                action: () => this.captureTable()
            });
        }

        // Render suggestions
        suggestionsContainer.innerHTML = suggestions.map(suggestion => `
            <button class="suggestion-btn ${suggestion.primary ? 'primary' : ''}" 
                    onclick="(${suggestion.action.toString()})()">
                <span class="emoji">${suggestion.icon}</span>
                ${suggestion.text}
            </button>
        `).join('');

        // Update suggested tags
        if (this.pageAnalysis.suggestedTags.length > 0) {
            const tagSuggestions = document.getElementById('tagSuggestions');
            if (tagSuggestions) {
                tagSuggestions.innerHTML = this.pageAnalysis.suggestedTags
                    .slice(0, 5)
                    .map(tag => `<span class="tag-suggestion" onclick="addTag('${tag}')">${tag}</span>`)
                    .join('');
            }
        }
    }

    updateInstantActions() {
        const instantSelection = document.getElementById('instantSelection');
        
        if (this.pageAnalysis?.hasSelection && this.pageAnalysis.selectedText) {
            instantSelection.style.display = 'block';
            const wordCount = this.pageAnalysis.selectedText.split(' ').length;
            instantSelection.innerHTML = `<span class="emoji">📝</span> Save Selection Instantly (${wordCount} words)`;
        } else {
            instantSelection.style.display = 'none';
        }
    }

    async performSmartCapture() {
        this.showProgress('Analyzing page content...');
        
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            
            // Extract smart content based on page analysis
            const content = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: this.extractSmartContent,
                args: [this.pageAnalysis]
            });

            if (content[0]?.result) {
                await this.processCapturedContent(content[0].result, 'smart-capture');
            }
        } catch (error) {
            this.showError('Smart capture failed: ' + error.message);
        }
    }

    // Smart content extraction function
    extractSmartContent(analysis) {
        let extractedContent = {
            title: document.title,
            url: window.location.href,
            content: '',
            type: 'webpage',
            metadata: {
                domain: window.location.hostname,
                timestamp: new Date().toISOString(),
                contentTypes: analysis?.contentTypes || []
            }
        };

        // Priority order for content extraction
        if (analysis?.hasSelection) {
            // User selection takes priority
            const selection = window.getSelection();
            extractedContent.content = selection.toString();
            extractedContent.type = 'selection';
            
            // Add surrounding context
            const range = selection.getRangeAt(0);
            const container = range.commonAncestorContainer.parentElement;
            extractedContent.context = container.textContent;
            
        } else if (analysis?.hasArticle) {
            // Extract article content using readability
            const article = document.querySelector('article') || 
                           document.querySelector('[role="main"]') ||
                           document.querySelector('.post, .article, .content');
            
            if (article) {
                extractedContent.content = this.extractReadableText(article);
                extractedContent.type = 'article';
            }
            
        } else {
            // Fallback to main content area
            const mainContent = document.querySelector('main') || 
                              document.querySelector('#main') ||
                              document.querySelector('.main-content') ||
                              document.body;
            
            extractedContent.content = this.extractReadableText(mainContent);
        }

        // Extract images with alt text
        if (analysis?.hasImages) {
            const images = Array.from(document.querySelectorAll('img'))
                .filter(img => img.width > 100 && img.height > 100)
                .map(img => ({
                    src: img.src,
                    alt: img.alt,
                    title: img.title
                }));
            extractedContent.images = images.slice(0, 5);
        }

        return extractedContent;
    }

    extractReadableText(element) {
        if (!element) return '';
        
        // Remove script and style elements
        const clone = element.cloneNode(true);
        const unwanted = clone.querySelectorAll('script, style, nav, header, footer, aside, .sidebar, .ad, .advertisement');
        unwanted.forEach(el => el.remove());
        
        // Convert to readable text while preserving structure
        let text = '';
        const walker = document.createTreeWalker(
            clone,
            NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT,
            {
                acceptNode: function(node) {
                    if (node.nodeType === Node.TEXT_NODE) {
                        const text = node.textContent.trim();
                        return text.length > 0 ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
                    }
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        const tag = node.tagName.toLowerCase();
                        if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'blockquote'].includes(tag)) {
                            return NodeFilter.FILTER_ACCEPT;
                        }
                    }
                    return NodeFilter.FILTER_SKIP;
                }
            }
        );

        let node;
        while (node = walker.nextNode()) {
            if (node.nodeType === Node.TEXT_NODE) {
                text += node.textContent.trim() + ' ';
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                const tag = node.tagName.toLowerCase();
                if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(tag)) {
                    text += '\n\n## ' + node.textContent.trim() + '\n\n';
                } else if (tag === 'p') {
                    text += '\n' + node.textContent.trim() + '\n';
                } else if (tag === 'li') {
                    text += '\n- ' + node.textContent.trim();
                } else if (tag === 'blockquote') {
                    text += '\n> ' + node.textContent.trim() + '\n';
                }
            }
        }

        return text.trim();
    }

    async captureArticle() {
        this.showProgress('Extracting article content...');
        
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            
            const content = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: () => {
                    // Use readability algorithm for article extraction
                    const articleSelectors = [
                        'article',
                        '[role="main"]',
                        '.post-content',
                        '.article-content',
                        '.entry-content',
                        'main'
                    ];
                    
                    let article = null;
                    for (const selector of articleSelectors) {
                        article = document.querySelector(selector);
                        if (article) break;
                    }
                    
                    if (!article) {
                        article = document.body;
                    }
                    
                    // Clean up the content
                    const clone = article.cloneNode(true);
                    
                    // Remove unwanted elements
                    const unwanted = clone.querySelectorAll(`
                        script, style, nav, header, footer, aside,
                        .sidebar, .ad, .advertisement, .social-share,
                        .comments, .comment, .navigation, .menu,
                        .related-posts, .author-bio, .newsletter-signup
                    `);
                    unwanted.forEach(el => el.remove());
                    
                    return {
                        title: document.title,
                        url: window.location.href,
                        content: clone.innerText,
                        html: clone.innerHTML,
                        author: document.querySelector('meta[name="author"]')?.content,
                        publishDate: document.querySelector('time')?.dateTime ||
                                   document.querySelector('meta[property="article:published_time"]')?.content,
                        type: 'article'
                    };
                }
            });

            if (content[0]?.result) {
                await this.processCapturedContent(content[0].result, 'article');
            }
        } catch (error) {
            this.showError('Article capture failed: ' + error.message);
        }
    }

    async captureCode() {
        this.showProgress('Extracting code snippets...');
        
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            
            const content = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: () => {
                    const codeElements = document.querySelectorAll('pre, code, .highlight, .code-block');
                    const codeBlocks = [];
                    
                    codeElements.forEach((element, index) => {
                        if (element.textContent.trim().length > 10) {
                            codeBlocks.push({
                                index: index + 1,
                                content: element.textContent,
                                language: element.className.match(/language-(\w+)/)?.[1] || 
                                         element.dataset.language || 
                                         'text',
                                context: element.previousElementSibling?.textContent?.slice(0, 100) || ''
                            });
                        }
                    });
                    
                    return {
                        title: document.title + ' - Code Snippets',
                        url: window.location.href,
                        codeBlocks: codeBlocks,
                        totalBlocks: codeBlocks.length,
                        type: 'code'
                    };
                }
            });

            if (content[0]?.result) {
                await this.processCapturedContent(content[0].result, 'code');
            }
        } catch (error) {
            this.showError('Code capture failed: ' + error.message);
        }
    }

    async captureTable() {
        this.showProgress('Extracting table data...');
        
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            
            const content = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: () => {
                    const tables = document.querySelectorAll('table');
                    const extractedTables = [];
                    
                    tables.forEach((table, index) => {
                        const rows = Array.from(table.rows);
                        if (rows.length > 0) {
                            const headers = Array.from(rows[0].cells).map(cell => cell.textContent.trim());
                            const data = rows.slice(1).map(row => 
                                Array.from(row.cells).map(cell => cell.textContent.trim())
                            );
                            
                            extractedTables.push({
                                index: index + 1,
                                headers: headers,
                                data: data,
                                rowCount: rows.length - 1,
                                columnCount: headers.length,
                                caption: table.caption?.textContent || `Table ${index + 1}`
                            });
                        }
                    });
                    
                    return {
                        title: document.title + ' - Tables',
                        url: window.location.href,
                        tables: extractedTables,
                        totalTables: extractedTables.length,
                        type: 'table'
                    };
                }
            });

            if (content[0]?.result) {
                await this.processCapturedContent(content[0].result, 'table');
            }
        } catch (error) {
            this.showError('Table capture failed: ' + error.message);
        }
    }

    async processCapturedContent(content, captureType) {
        this.showProgress('Processing with AI...');
        
        try {
            // Prepare content for API
            let processedContent = {
                ...content,
                captureType: captureType,
                timestamp: new Date().toISOString(),
                processingOptions: {
                    aiSummarize: this.settings.autoSummarize,
                    aiTags: this.settings.autoTags,
                    duplicateCheck: this.settings.duplicateDetection,
                    contextPreservation: this.settings.contextPreservation
                }
            };

            // Add user-provided tags
            const userTags = document.getElementById('manualTags')?.value;
            if (userTags) {
                processedContent.userTags = userTags;
            }

            // Send to Second Brain API
            const response = await this.apiCall('/webhook/browser', {
                method: 'POST',
                body: JSON.stringify(processedContent)
            });

            if (response.success) {
                this.showSuccess('Content captured successfully!');
                this.trackCapture(processedContent);
                await this.loadRecentCaptures();
            } else {
                throw new Error(response.message || 'Capture failed');
            }
        } catch (error) {
            this.showError('Processing failed: ' + error.message);
        }
    }

    async apiCall(endpoint, options = {}) {
        const url = `${this.apiUrl}${endpoint}`;
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.authToken}`
            }
        };

        const response = await fetch(url, {
            ...defaultOptions,
            ...options,
            headers: {
                ...defaultOptions.headers,
                ...options.headers
            }
        });

        if (!response.ok) {
            throw new Error(`API call failed: ${response.status} ${response.statusText}`);
        }

        return await response.json();
    }

    showProgress(message) {
        const messagesDiv = document.getElementById('messages');
        messagesDiv.innerHTML = `<div class="loading">${message}</div>`;
    }

    showSuccess(message) {
        const messagesDiv = document.getElementById('messages');
        messagesDiv.innerHTML = `<div class="success">${message}</div>`;
        setTimeout(() => messagesDiv.innerHTML = '', 3000);
    }

    showError(message) {
        const messagesDiv = document.getElementById('messages');
        messagesDiv.innerHTML = `<div class="error">${message}</div>`;
    }

    async checkConnection() {
        try {
            const response = await this.apiCall('/health');
            this.connectionStatus = { connected: true, ...response };
            document.getElementById('status').innerHTML = '🟢 Connected';
            document.getElementById('status').className = 'status status-connected';
        } catch (error) {
            this.connectionStatus = { connected: false };
            document.getElementById('status').innerHTML = '🔴 Disconnected';
            document.getElementById('status').className = 'status status-disconnected';
        }
    }

    async loadRecentCaptures() {
        try {
            const captures = await this.apiCall('/api/captures/recent?limit=5');
            this.recentCaptures = captures;
            this.updateRecentCapturesUI();
        } catch (error) {
            console.error('Failed to load recent captures:', error);
        }
    }

    updateRecentCapturesUI() {
        const container = document.getElementById('recentCaptures');
        
        if (this.recentCaptures.length === 0) {
            container.innerHTML = '<div class="loading">No recent captures</div>';
            return;
        }

        container.innerHTML = this.recentCaptures.map(capture => `
            <div class="recent-item" onclick="openCapture(${capture.id})">
                <div class="recent-item-title">${capture.title || 'Untitled'}</div>
                <div class="recent-item-meta">
                    ${new Date(capture.created_at).toLocaleString()} • 
                    ${capture.type || 'note'}
                    ${capture.status === 'processing' ? ' • Processing...' : ''}
                </div>
            </div>
        `).join('');
    }

    trackCapture(content) {
        // Store capture in local storage for quick access
        const captures = JSON.parse(localStorage.getItem('recentCaptures') || '[]');
        captures.unshift({
            id: Date.now(),
            title: content.title,
            type: content.captureType,
            timestamp: content.timestamp
        });
        
        // Keep only last 20 captures
        captures.splice(20);
        localStorage.setItem('recentCaptures', JSON.stringify(captures));
    }

    startRealtimeUpdates() {
        // Poll for updates every 30 seconds
        setInterval(async () => {
            await this.checkConnection();
            if (this.connectionStatus.connected) {
                await this.loadRecentCaptures();
            }
        }, 30000);
    }

    updateUI() {
        // Update AI feature toggles
        document.getElementById('aiSummarize').checked = this.settings.autoSummarize;
        document.getElementById('aiTags').checked = this.settings.autoTags;
        document.getElementById('duplicateCheck').checked = this.settings.duplicateDetection;
        
        // Show/hide advanced features based on connection
        const advancedFeatures = document.querySelectorAll('.advanced-feature');
        advancedFeatures.forEach(element => {
            element.style.display = this.connectionStatus.connected ? 'block' : 'none';
        });
    }

    handleKeyboardShortcuts(event) {
        if (event.ctrlKey || event.metaKey) {
            switch (event.key) {
                case 'Enter':
                    event.preventDefault();
                    this.saveManualNote();
                    break;
                case 's':
                    event.preventDefault();
                    this.captureSelection();
                    break;
                case 'p':
                    event.preventDefault();
                    this.capturePage();
                    break;
            }
        }
    }

    async openDashboard() {
        await chrome.tabs.create({ url: `${this.apiUrl}/` });
    }

    async openSettings() {
        await chrome.runtime.openOptionsPage();
    }
}

// Initialize extension when popup loads
document.addEventListener('DOMContentLoaded', () => {
    window.secondBrain = new SecondBrainExtension();
});

// Global functions for inline event handlers
function addTag(tag) {
    const tagInput = document.getElementById('manualTags');
    const currentTags = tagInput.value.split(',').map(t => t.trim()).filter(t => t.length > 0);
    if (!currentTags.includes(tag)) {
        currentTags.push(tag);
        tagInput.value = currentTags.join(', ');
    }
}

function openCapture(id) {
    chrome.tabs.create({ url: `${window.secondBrain.apiUrl}/detail/${id}` });
}