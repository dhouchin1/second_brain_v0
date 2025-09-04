// content.js - Enhanced content script for Second Brain extension
class SecondBrainContent {
    constructor() {
        this.settings = {};
        this.offlineQueue = [];
        this.isConnected = true;
        this.init();
    }

    async init() {
        await this.loadSettings();
        this.setupSelectionHandler();
        this.setupKeyboardShortcuts();
        this.setupQuickCaptureUI();
        this.setupMultiSelection();
        this.checkConnection();
    }

    async loadSettings() {
        this.settings = await chrome.storage.sync.get([
            'apiUrl',
            'authToken',
            'autoSummarize',
            'autoTags',
            'offlineMode'
        ]);
        this.settings.apiUrl = this.settings.apiUrl || 'http://localhost:8082';
    }

    setupSelectionHandler() {
        let selectionTimeout;
        let lastSelection = '';
        
        document.addEventListener('mouseup', (e) => {
            // Skip if clicking on our UI elements
            if (e.target.closest('#second-brain-quick-capture, #second-brain-multi-selector')) {
                return;
            }
            
            clearTimeout(selectionTimeout);
            selectionTimeout = setTimeout(() => {
                this.handleSelection();
            }, 300);
        });

        document.addEventListener('keyup', (e) => {
            if (e.key === 'Escape') {
                this.hideQuickCapture();
                this.hideMultiSelector();
            }
        });

        // Enhanced selection tracking
        document.addEventListener('selectionchange', () => {
            const selection = window.getSelection();
            const selectedText = selection.toString().trim();
            
            if (selectedText !== lastSelection) {
                lastSelection = selectedText;
                if (selectedText.length > 10) {
                    this.analyzeSelection(selectedText);
                }
            }
        });
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl+Shift+S - Quick save selection
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'S') {
                e.preventDefault();
                this.quickSaveSelection();
            }
            
            // Ctrl+Shift+P - Quick save page
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'P') {
                e.preventDefault();
                this.quickSavePage();
            }

            // Ctrl+Shift+M - Multi-selection mode
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'M') {
                e.preventDefault();
                this.toggleMultiSelection();
            }

            // Ctrl+Shift+C - Smart capture with AI
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'C') {
                e.preventDefault();
                this.smartCapture();
            }
        });
    }

    setupMultiSelection() {
        this.multiSelections = [];
        this.multiSelectionMode = false;
    }

    async handleSelection() {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();
        
        if (selectedText && selectedText.length > 10) {
            const contentInfo = await this.analyzeContent(selectedText);
            this.showQuickCapture(selectedText, contentInfo);
        } else {
            this.hideQuickCapture();
        }
    }

    async analyzeContent(text) {
        // Intelligent content analysis
        const analysis = {
            type: this.detectContentType(text),
            language: this.detectLanguage(text),
            readabilityScore: this.calculateReadability(text),
            topics: this.extractTopics(text),
            entities: this.extractEntities(text),
            isCode: this.isCodeSnippet(text),
            isPDF: this.isPDFContent(),
            hasTable: this.hasTableData(text)
        };

        return analysis;
    }

    detectContentType(text) {
        if (this.isCodeSnippet(text)) return 'code';
        if (text.match(/\b(recipe|ingredients|instructions)\b/i)) return 'recipe';
        if (text.match(/\b(tutorial|how to|step by step)\b/i)) return 'tutorial';
        if (text.match(/\b(research|study|paper|journal)\b/i)) return 'research';
        if (text.match(/\b(news|breaking|report)\b/i)) return 'news';
        if (text.length > 500 && text.split('.').length > 5) return 'article';
        return 'text';
    }

    detectLanguage(text) {
        // Simple language detection based on common words
        const langPatterns = {
            javascript: /\b(function|var|let|const|if|else|for|while|return|class)\b/g,
            python: /\b(def|import|from|if|elif|else|for|while|return|class)\b/g,
            html: /<[^>]+>/g,
            css: /\{[^}]*\}/g,
            json: /^[\s]*\{[\s\S]*\}[\s]*$/
        };

        for (const [lang, pattern] of Object.entries(langPatterns)) {
            if (pattern.test(text)) return lang;
        }
        
        return 'text';
    }

    calculateReadability(text) {
        // Simple Flesch Reading Ease approximation
        const sentences = text.split(/[.!?]+/).length;
        const words = text.split(/\s+/).length;
        const syllables = text.match(/[aeiouAEIOU]/g)?.length || 0;
        
        if (sentences === 0 || words === 0) return 50;
        
        const avgWordsPerSentence = words / sentences;
        const avgSyllablesPerWord = syllables / words;
        
        const score = 206.835 - (1.015 * avgWordsPerSentence) - (84.6 * avgSyllablesPerWord);
        return Math.max(0, Math.min(100, score));
    }

    extractTopics(text) {
        const keywords = text.toLowerCase()
            .replace(/[^\w\s]/g, ' ')
            .split(/\s+/)
            .filter(word => word.length > 3)
            .reduce((acc, word) => {
                acc[word] = (acc[word] || 0) + 1;
                return acc;
            }, {});

        return Object.entries(keywords)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5)
            .map(([word]) => word);
    }

    extractEntities(text) {
        const entities = {
            urls: text.match(/https?:\/\/[^\s]+/g) || [],
            emails: text.match(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g) || [],
            dates: text.match(/\b\d{1,2}\/\d{1,2}\/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b/g) || [],
            prices: text.match(/\$\d+(?:\.\d{2})?/g) || []
        };
        
        return entities;
    }

    isCodeSnippet(text) {
        const codeIndicators = [
            /function\s*\(/,
            /class\s+\w+/,
            /import\s+\w+/,
            /var\s+\w+\s*=/,
            /let\s+\w+\s*=/,
            /const\s+\w+\s*=/,
            /<\/?\w+[^>]*>/,
            /\{\s*\w+:\s*['"][^'"]*['"],?/
        ];
        
        return codeIndicators.some(pattern => pattern.test(text));
    }

    isPDFContent() {
        return document.contentType === 'application/pdf' || 
               document.querySelector('embed[type="application/pdf"]') ||
               window.location.href.endsWith('.pdf');
    }

    hasTableData(text) {
        // Check for table-like structures
        return /\t.*\t/.test(text) || 
               text.split('\n').some(line => 
                   line.split(/\s{2,}/).length > 2
               );
    }

    async showQuickCapture(selectedText, contentInfo) {
        this.hideQuickCapture();
        
        const quickCapture = document.createElement('div');
        quickCapture.id = 'second-brain-quick-capture';
        quickCapture.innerHTML = `
            <div class="sb-tooltip ${contentInfo.type}">
                <div class="sb-tooltip-content">
                    <div class="sb-tooltip-header">
                        <div class="sb-tooltip-title">
                            ${this.getContentIcon(contentInfo.type)} Save to Second Brain
                        </div>
                        <div class="sb-content-info">
                            ${contentInfo.type.charAt(0).toUpperCase() + contentInfo.type.slice(1)}
                            ${contentInfo.readabilityScore < 30 ? '🔴' : contentInfo.readabilityScore < 60 ? '🟡' : '🟢'}
                        </div>
                    </div>
                    <div class="sb-tooltip-text">"${this.truncateText(selectedText, 80)}"</div>
                    ${contentInfo.topics.length > 0 ? `
                        <div class="sb-suggested-tags">
                            <span>Suggested tags:</span>
                            ${contentInfo.topics.slice(0, 3).map(tag => `<span class="sb-tag">${tag}</span>`).join('')}
                        </div>
                    ` : ''}
                    <div class="sb-tooltip-actions">
                        <button class="sb-btn sb-btn-primary" id="sb-save-selection">Save</button>
                        <button class="sb-btn sb-btn-secondary" id="sb-save-with-context">+ Context</button>
                        <button class="sb-btn sb-btn-ai" id="sb-save-with-ai">🧠 AI</button>
                        <button class="sb-btn sb-btn-multi" id="sb-add-to-multi">+ Multi</button>
                        <button class="sb-btn sb-btn-close" id="sb-close">✕</button>
                    </div>
                </div>
                <div class="sb-tooltip-arrow"></div>
            </div>
        `;

        document.body.appendChild(quickCapture);
        
        this.positionTooltip(quickCapture);
        this.setupQuickCaptureEvents(selectedText, contentInfo);
        
        // Auto-hide after 15 seconds
        setTimeout(() => {
            this.hideQuickCapture();
        }, 15000);
    }

    positionTooltip(quickCapture) {
        const selection = window.getSelection();
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            const rect = range.getBoundingClientRect();
            
            const tooltip = quickCapture.querySelector('.sb-tooltip');
            const tooltipRect = tooltip.getBoundingClientRect();
            
            let left = rect.left + window.scrollX;
            let top = rect.bottom + window.scrollY + 10;
            
            // Adjust if tooltip goes off-screen
            if (left + tooltipRect.width > window.innerWidth) {
                left = window.innerWidth - tooltipRect.width - 20;
            }
            if (left < 20) {
                left = 20;
            }
            if (top + tooltipRect.height > window.innerHeight + window.scrollY) {
                top = rect.top + window.scrollY - tooltipRect.height - 10;
            }
            
            tooltip.style.left = `${left}px`;
            tooltip.style.top = `${top}px`;
        }
    }

    setupQuickCaptureEvents(selectedText, contentInfo) {
        document.getElementById('sb-save-selection')?.addEventListener('click', () => {
            this.saveSelection(selectedText, false, contentInfo);
        });
        
        document.getElementById('sb-save-with-context')?.addEventListener('click', () => {
            this.saveSelection(selectedText, true, contentInfo);
        });
        
        document.getElementById('sb-save-with-ai')?.addEventListener('click', () => {
            this.saveSelectionWithAI(selectedText, contentInfo);
        });
        
        document.getElementById('sb-add-to-multi')?.addEventListener('click', () => {
            this.addToMultiSelection(selectedText, contentInfo);
        });
        
        document.getElementById('sb-close')?.addEventListener('click', () => {
            this.hideQuickCapture();
        });
    }

    getContentIcon(type) {
        const icons = {
            code: '💻',
            recipe: '👨‍🍳',
            tutorial: '📚',
            research: '🔬',
            news: '📰',
            article: '📄',
            text: '📝'
        };
        return icons[type] || '📝';
    }

    truncateText(text, maxLength) {
        return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
    }

    hideQuickCapture() {
        const quickCapture = document.getElementById('second-brain-quick-capture');
        if (quickCapture) {
            quickCapture.remove();
        }
    }

    async saveSelection(selectedText, includeContext = false, contentInfo = null) {
        this.hideQuickCapture();
        
        let content = selectedText;
        let context = {};
        
        if (includeContext) {
            context = await this.extractFullContext(selectedText);
            content = `${selectedText}\n\n---\nContext: ${context.surrounding}\n\nPage Structure: ${context.structure}`;
        }

        const payload = {
            note: content,
            tags: this.generateSmartTags(selectedText, contentInfo),
            type: 'browser',
            metadata: {
                url: window.location.href,
                title: document.title,
                captureType: includeContext ? 'selection-with-context' : 'selection',
                timestamp: new Date().toISOString(),
                selectedText: selectedText,
                contentInfo: contentInfo,
                context: context,
                pageMetadata: this.extractPageMetadata()
            }
        };

        try {
            await this.sendToBackground('saveContent', payload);
            this.showNotification('Selection saved to Second Brain! 🧠', 'success');
        } catch (error) {
            await this.handleOfflineCapture(payload);
        }
    }

    async saveSelectionWithAI(selectedText, contentInfo) {
        this.hideQuickCapture();
        this.showProcessingNotification('AI processing selection...');
        
        const payload = {
            note: selectedText,
            tags: this.generateSmartTags(selectedText, contentInfo),
            type: 'browser',
            aiProcessing: {
                summarize: true,
                generateTags: true,
                extractEntities: true,
                analyzeSentiment: true
            },
            metadata: {
                url: window.location.href,
                title: document.title,
                captureType: 'selection-ai',
                timestamp: new Date().toISOString(),
                selectedText: selectedText,
                contentInfo: contentInfo,
                pageMetadata: this.extractPageMetadata()
            }
        };

        try {
            await this.sendToBackground('saveContentWithAI', payload);
            this.showNotification('AI-enhanced capture saved! 🤖🧠', 'success');
        } catch (error) {
            await this.handleOfflineCapture(payload);
        }
    }

    addToMultiSelection(selectedText, contentInfo) {
        this.hideQuickCapture();
        
        this.multiSelections.push({
            text: selectedText,
            contentInfo: contentInfo,
            context: this.extractSelectionContext(),
            timestamp: new Date().toISOString()
        });
        
        this.showNotification(`Added to multi-selection (${this.multiSelections.length} items)`, 'info');
        this.updateMultiSelectorUI();
    }

    toggleMultiSelection() {
        this.multiSelectionMode = !this.multiSelectionMode;
        
        if (this.multiSelectionMode) {
            this.showMultiSelector();
            this.showNotification('Multi-selection mode enabled. Select multiple elements!', 'info');
        } else {
            this.hideMultiSelector();
            this.showNotification('Multi-selection mode disabled.', 'info');
        }
    }

    showMultiSelector() {
        if (document.getElementById('second-brain-multi-selector')) return;
        
        const multiSelector = document.createElement('div');
        multiSelector.id = 'second-brain-multi-selector';
        multiSelector.innerHTML = `
            <div class="sb-multi-selector">
                <div class="sb-multi-header">
                    <span>📝 Multi-Selection (${this.multiSelections.length} items)</span>
                    <div class="sb-multi-actions">
                        <button class="sb-btn-small sb-btn-primary" id="sb-save-multi">Save All</button>
                        <button class="sb-btn-small sb-btn-secondary" id="sb-clear-multi">Clear</button>
                        <button class="sb-btn-small sb-btn-close" id="sb-close-multi">✕</button>
                    </div>
                </div>
                <div class="sb-multi-list" id="sb-multi-list">
                    ${this.renderMultiSelections()}
                </div>
            </div>
        `;
        
        document.body.appendChild(multiSelector);
        this.setupMultiSelectorEvents();
    }

    renderMultiSelections() {
        if (this.multiSelections.length === 0) {
            return '<div class="sb-multi-empty">No selections yet. Start selecting content!</div>';
        }
        
        return this.multiSelections.map((selection, index) => `
            <div class="sb-multi-item" data-index="${index}">
                <div class="sb-multi-content">
                    ${this.getContentIcon(selection.contentInfo?.type || 'text')}
                    <span class="sb-multi-text">"${this.truncateText(selection.text, 50)}"</span>
                </div>
                <button class="sb-multi-remove" data-index="${index}">×</button>
            </div>
        `).join('');
    }

    updateMultiSelectorUI() {
        const listEl = document.getElementById('sb-multi-list');
        if (listEl) {
            listEl.innerHTML = this.renderMultiSelections();
        }
        
        const header = document.querySelector('#second-brain-multi-selector .sb-multi-header span');
        if (header) {
            header.textContent = `📝 Multi-Selection (${this.multiSelections.length} items)`;
        }
    }

    setupMultiSelectorEvents() {
        document.getElementById('sb-save-multi')?.addEventListener('click', () => {
            this.saveMultiSelection();
        });
        
        document.getElementById('sb-clear-multi')?.addEventListener('click', () => {
            this.clearMultiSelection();
        });
        
        document.getElementById('sb-close-multi')?.addEventListener('click', () => {
            this.hideMultiSelector();
            this.multiSelectionMode = false;
        });
        
        // Remove individual items
        document.querySelectorAll('.sb-multi-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.dataset.index);
                this.multiSelections.splice(index, 1);
                this.updateMultiSelectorUI();
            });
        });
    }

    async saveMultiSelection() {
        if (this.multiSelections.length === 0) {
            this.showNotification('No selections to save', 'warning');
            return;
        }
        
        const combinedContent = this.multiSelections.map((selection, index) => 
            `## Selection ${index + 1}\n${selection.text}\n\n`
        ).join('');
        
        const allTags = this.multiSelections.flatMap(selection => 
            this.generateSmartTags(selection.text, selection.contentInfo).split(',')
        );
        const uniqueTags = [...new Set(allTags)].filter(Boolean).join(',');
        
        const payload = {
            note: `# Multi-Selection Capture\n\n${combinedContent}`,
            tags: `multi-selection,${uniqueTags}`,
            type: 'browser',
            metadata: {
                url: window.location.href,
                title: document.title,
                captureType: 'multi-selection',
                timestamp: new Date().toISOString(),
                selectionCount: this.multiSelections.length,
                selections: this.multiSelections,
                pageMetadata: this.extractPageMetadata()
            }
        };

        try {
            await this.sendToBackground('saveContent', payload);
            this.showNotification(`Multi-selection saved (${this.multiSelections.length} items)! 🧠`, 'success');
            this.clearMultiSelection();
            this.hideMultiSelector();
        } catch (error) {
            await this.handleOfflineCapture(payload);
        }
    }

    clearMultiSelection() {
        this.multiSelections = [];
        this.updateMultiSelectorUI();
        this.showNotification('Multi-selection cleared', 'info');
    }

    hideMultiSelector() {
        const multiSelector = document.getElementById('second-brain-multi-selector');
        if (multiSelector) {
            multiSelector.remove();
        }
    }

    async smartCapture() {
        // AI-powered smart capture of the entire page
        this.showProcessingNotification('🧠 AI analyzing page content...');
        
        const intelligentContent = await this.extractIntelligentContent();
        const payload = {
            note: intelligentContent.content,
            tags: intelligentContent.tags,
            type: 'browser',
            aiProcessing: {
                smartExtraction: true,
                summarize: true,
                generateTags: true,
                extractKeyPoints: true
            },
            metadata: {
                url: window.location.href,
                title: document.title,
                captureType: 'smart-capture',
                timestamp: new Date().toISOString(),
                intelligentAnalysis: intelligentContent.analysis,
                pageMetadata: this.extractPageMetadata()
            }
        };

        try {
            await this.sendToBackground('saveContentWithAI', payload);
            this.showNotification('Smart capture completed! 🤖🧠', 'success');
        } catch (error) {
            await this.handleOfflineCapture(payload);
        }
    }

    async extractIntelligentContent() {
        const readabilityResult = this.applyReadabilityExtraction();
        const structuredData = this.extractStructuredData();
        const mediaElements = this.extractMediaElements();
        
        return {
            content: readabilityResult.content,
            tags: this.generateIntelligentTags(readabilityResult, structuredData),
            analysis: {
                readabilityScore: readabilityResult.score,
                wordCount: readabilityResult.wordCount,
                readingTime: Math.ceil(readabilityResult.wordCount / 200),
                contentType: readabilityResult.type,
                structuredData: structuredData,
                mediaCount: mediaElements.length,
                topics: this.extractTopics(readabilityResult.content)
            }
        };
    }

    applyReadabilityExtraction() {
        // Advanced readability algorithm
        const candidates = this.findContentCandidates();
        let bestCandidate = this.selectBestCandidate(candidates);
        
        if (bestCandidate) {
            bestCandidate = this.cleanContent(bestCandidate);
            const content = this.formatContent(bestCandidate);
            
            return {
                content: content,
                score: this.calculateReadability(content),
                wordCount: content.split(/\s+/).length,
                type: this.detectContentType(content)
            };
        }
        
        return {
            content: document.title + '\n\n' + document.body.innerText.substring(0, 2000),
            score: 50,
            wordCount: document.body.innerText.split(/\s+/).length,
            type: 'webpage'
        };
    }

    findContentCandidates() {
        const selectors = [
            'article',
            'main',
            '[role="main"]',
            '.content',
            '.post',
            '.entry',
            '.article',
            '#content',
            '#main',
            '.main-content'
        ];
        
        return selectors
            .map(selector => document.querySelector(selector))
            .filter(Boolean)
            .concat([document.body]);
    }

    selectBestCandidate(candidates) {
        let bestScore = 0;
        let bestCandidate = null;
        
        candidates.forEach(candidate => {
            const score = this.scoreContent(candidate);
            if (score > bestScore) {
                bestScore = score;
                bestCandidate = candidate;
            }
        });
        
        return bestCandidate;
    }

    scoreContent(element) {
        const textLength = element.innerText?.length || 0;
        const linkDensity = this.calculateLinkDensity(element);
        const paragraphCount = element.querySelectorAll('p').length;
        const headerCount = element.querySelectorAll('h1,h2,h3,h4,h5,h6').length;
        
        // Favor elements with more text, fewer links, and good structure
        return (textLength * 0.5) + 
               (paragraphCount * 10) + 
               (headerCount * 5) - 
               (linkDensity * 100);
    }

    calculateLinkDensity(element) {
        const textLength = element.innerText?.length || 1;
        const linkText = Array.from(element.querySelectorAll('a'))
            .map(a => a.innerText?.length || 0)
            .reduce((sum, len) => sum + len, 0);
        
        return linkText / textLength;
    }

    cleanContent(element) {
        const clone = element.cloneNode(true);
        
        // Remove unwanted elements
        const unwanted = clone.querySelectorAll(`
            script, style, nav, header, footer, aside,
            .ad, .advertisement, .ads, .sidebar, .menu, .navigation,
            .comments, .social, .share, .related, .recommended,
            [class*="ad"], [id*="ad"], [class*="sidebar"], [id*="sidebar"]
        `);
        
        unwanted.forEach(el => el.remove());
        
        return clone;
    }

    formatContent(element) {
        // Convert HTML structure to markdown-like format
        let content = '';
        
        // Add title
        const title = document.title;
        if (title) {
            content += `# ${title}\n\n`;
        }
        
        // Process content maintaining structure
        content += this.htmlToMarkdown(element);
        
        return content;
    }

    htmlToMarkdown(element) {
        let markdown = '';
        
        element.childNodes.forEach(node => {
            if (node.nodeType === Node.TEXT_NODE) {
                const text = node.textContent.trim();
                if (text) {
                    markdown += text + ' ';
                }
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                const tagName = node.tagName.toLowerCase();
                
                switch (tagName) {
                    case 'h1':
                        markdown += `\n# ${node.innerText}\n\n`;
                        break;
                    case 'h2':
                        markdown += `\n## ${node.innerText}\n\n`;
                        break;
                    case 'h3':
                        markdown += `\n### ${node.innerText}\n\n`;
                        break;
                    case 'h4':
                        markdown += `\n#### ${node.innerText}\n\n`;
                        break;
                    case 'p':
                        markdown += `${node.innerText}\n\n`;
                        break;
                    case 'blockquote':
                        markdown += `> ${node.innerText}\n\n`;
                        break;
                    case 'ul':
                    case 'ol':
                        const items = Array.from(node.querySelectorAll('li'));
                        items.forEach((item, index) => {
                            const prefix = tagName === 'ul' ? '- ' : `${index + 1}. `;
                            markdown += `${prefix}${item.innerText}\n`;
                        });
                        markdown += '\n';
                        break;
                    case 'code':
                    case 'pre':
                        markdown += `\`\`\`\n${node.innerText}\n\`\`\`\n\n`;
                        break;
                    case 'img':
                        const alt = node.alt || 'Image';
                        const src = node.src;
                        markdown += `![${alt}](${src})\n\n`;
                        break;
                    case 'a':
                        const href = node.href;
                        const text = node.innerText;
                        markdown += `[${text}](${href})`;
                        break;
                    default:
                        if (node.innerText) {
                            markdown += this.htmlToMarkdown(node);
                        }
                }
            }
        });
        
        return markdown;
    }

    extractStructuredData() {
        const structuredData = {};
        
        // JSON-LD
        const jsonLdScripts = document.querySelectorAll('script[type="application/ld+json"]');
        jsonLdScripts.forEach((script, index) => {
            try {
                structuredData[`jsonLd${index}`] = JSON.parse(script.textContent);
            } catch (e) {}
        });
        
        // Open Graph
        structuredData.openGraph = {};
        document.querySelectorAll('meta[property^="og:"]').forEach(meta => {
            const property = meta.getAttribute('property').replace('og:', '');
            structuredData.openGraph[property] = meta.getAttribute('content');
        });
        
        // Twitter Cards
        structuredData.twitter = {};
        document.querySelectorAll('meta[name^="twitter:"]').forEach(meta => {
            const name = meta.getAttribute('name').replace('twitter:', '');
            structuredData.twitter[name] = meta.getAttribute('content');
        });
        
        // Schema.org microdata
        structuredData.microdata = this.extractMicrodata();
        
        return structuredData;
    }

    extractMicrodata() {
        const microdata = [];
        document.querySelectorAll('[itemscope]').forEach(element => {
            const item = {
                type: element.getAttribute('itemtype'),
                properties: {}
            };
            
            element.querySelectorAll('[itemprop]').forEach(prop => {
                const name = prop.getAttribute('itemprop');
                const value = prop.getAttribute('content') || 
                              prop.getAttribute('href') || 
                              prop.innerText;
                item.properties[name] = value;
            });
            
            microdata.push(item);
        });
        
        return microdata;
    }

    extractMediaElements() {
        const media = [];
        
        // Images
        document.querySelectorAll('img').forEach(img => {
            media.push({
                type: 'image',
                src: img.src,
                alt: img.alt,
                width: img.naturalWidth,
                height: img.naturalHeight
            });
        });
        
        // Videos
        document.querySelectorAll('video').forEach(video => {
            media.push({
                type: 'video',
                src: video.src || video.querySelector('source')?.src,
                poster: video.poster,
                duration: video.duration
            });
        });
        
        // Audio
        document.querySelectorAll('audio').forEach(audio => {
            media.push({
                type: 'audio',
                src: audio.src || audio.querySelector('source')?.src,
                duration: audio.duration
            });
        });
        
        return media;
    }

    generateIntelligentTags(readabilityResult, structuredData) {
        const tags = ['web', 'smart-capture'];
        
        // Content type tags
        tags.push(readabilityResult.type);
        
        // Domain tag
        try {
            const domain = new URL(window.location.href).hostname.replace('www.', '');
            tags.push(domain);
        } catch (e) {}
        
        // Structured data tags
        if (structuredData.openGraph?.type) {
            tags.push(structuredData.openGraph.type);
        }
        
        // Topic tags
        const topics = this.extractTopics(readabilityResult.content);
        tags.push(...topics.slice(0, 5));
        
        // Reading difficulty
        if (readabilityResult.score < 30) tags.push('complex');
        else if (readabilityResult.score > 70) tags.push('easy-read');
        
        return tags.join(',');
    }

    async extractFullContext(selectedText) {
        const selection = window.getSelection();
        const context = {};
        
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            const container = range.commonAncestorContainer;
            
            // Get surrounding context
            const paragraph = container.nodeType === Node.TEXT_NODE 
                ? container.parentElement 
                : container;
            
            context.surrounding = this.getElementContext(paragraph);
            
            // Get page structure context
            context.structure = this.getPageStructure();
            
            // Get related links
            context.relatedLinks = this.getRelatedLinks(paragraph);
            
            // Get position in document
            context.position = this.getSelectionPosition(range);
        }
        
        return context;
    }

    getElementContext(element) {
        let context = element.innerText || element.textContent || '';
        
        // Expand context if too short
        let currentElement = element;
        while (context.length < 500 && currentElement.parentElement && currentElement !== document.body) {
            currentElement = currentElement.parentElement;
            const parentText = currentElement.innerText || currentElement.textContent || '';
            if (parentText.length > context.length && parentText.length < 2000) {
                context = parentText;
            }
        }
        
        return context.substring(0, 1000);
    }

    getPageStructure() {
        const headers = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'));
        return headers.map(header => ({
            level: header.tagName,
            text: header.innerText,
            id: header.id
        }));
    }

    getRelatedLinks(element) {
        const links = Array.from(element.querySelectorAll('a'))
            .concat(Array.from(element.parentElement?.querySelectorAll('a') || []))
            .slice(0, 5);
        
        return links.map(link => ({
            href: link.href,
            text: link.innerText,
            title: link.title
        }));
    }

    getSelectionPosition(range) {
        const rect = range.getBoundingClientRect();
        const totalHeight = document.documentElement.scrollHeight;
        const viewportHeight = window.innerHeight;
        const scrollTop = window.scrollY;
        
        return {
            percentageFromTop: ((scrollTop + rect.top) / totalHeight) * 100,
            viewportPosition: {
                x: rect.left,
                y: rect.top
            }
        };
    }

    extractSelectionContext() {
        const selection = window.getSelection();
        if (selection.rangeCount === 0) return {};
        
        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        
        return {
            position: {
                x: rect.left + window.scrollX,
                y: rect.top + window.scrollY
            },
            timestamp: new Date().toISOString()
        };
    }

    generateSmartTags(text, contentInfo) {
        const tags = ['web'];
        
        // Content type
        if (contentInfo?.type) {
            tags.push(contentInfo.type);
        }
        
        // Domain
        try {
            const domain = new URL(window.location.href).hostname.replace('www.', '');
            tags.push(domain);
        } catch (e) {}
        
        // Suggested topics
        if (contentInfo?.topics) {
            tags.push(...contentInfo.topics.slice(0, 3));
        }
        
        // Language detection
        if (contentInfo?.language && contentInfo.language !== 'text') {
            tags.push(contentInfo.language);
        }
        
        return tags.filter(Boolean).join(',');
    }

    extractPageMetadata() {
        return {
            url: window.location.href,
            title: document.title,
            domain: window.location.hostname,
            path: window.location.pathname,
            timestamp: new Date().toISOString(),
            viewport: {
                width: window.innerWidth,
                height: window.innerHeight
            },
            meta: {
                description: document.querySelector('meta[name="description"]')?.content || '',
                author: document.querySelector('meta[name="author"]')?.content || '',
                keywords: document.querySelector('meta[name="keywords"]')?.content || '',
                publishDate: document.querySelector('meta[property="article:published_time"]')?.content || 
                           document.querySelector('meta[name="date"]')?.content || '',
                language: document.documentElement.lang || 'en'
            },
            favicon: document.querySelector('link[rel="icon"]')?.href || 
                    document.querySelector('link[rel="shortcut icon"]')?.href || ''
        };
    }

    async quickSaveSelection() {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();
        
        if (selectedText) {
            const contentInfo = await this.analyzeContent(selectedText);
            await this.saveSelection(selectedText, false, contentInfo);
        } else {
            this.showNotification('No text selected', 'warning');
        }
    }

    async quickSavePage() {
        const intelligentContent = await this.extractIntelligentContent();
        
        const payload = {
            note: intelligentContent.content,
            tags: `web,page,quick-save,${intelligentContent.tags}`,
            type: 'browser',
            metadata: {
                url: window.location.href,
                title: document.title,
                captureType: 'page',
                timestamp: new Date().toISOString(),
                intelligentAnalysis: intelligentContent.analysis,
                pageMetadata: this.extractPageMetadata()
            }
        };

        try {
            await this.sendToBackground('saveContent', payload);
            this.showNotification('Page saved to Second Brain! 🧠', 'success');
        } catch (error) {
            await this.handleOfflineCapture(payload);
        }
    }

    async checkConnection() {
        try {
            const response = await fetch(`${this.settings.apiUrl}/health`);
            this.isConnected = response.ok;
        } catch (error) {
            this.isConnected = false;
        }
        
        this.updateConnectionStatus();
    }

    updateConnectionStatus() {
        // Visual indicator for connection status
        const existingIndicator = document.getElementById('sb-connection-indicator');
        if (existingIndicator) existingIndicator.remove();
        
        const indicator = document.createElement('div');
        indicator.id = 'sb-connection-indicator';
        indicator.className = `sb-connection-indicator ${this.isConnected ? 'connected' : 'disconnected'}`;
        indicator.innerHTML = this.isConnected ? '🟢' : '🔴';
        indicator.title = this.isConnected ? 'Connected to Second Brain' : 'Offline - captures will be queued';
        
        document.body.appendChild(indicator);
        
        // Auto-hide after 3 seconds
        setTimeout(() => {
            if (indicator.parentNode) {
                indicator.style.opacity = '0.3';
            }
        }, 3000);
    }

    async handleOfflineCapture(payload) {
        if (this.settings.offlineMode !== false) {
            this.offlineQueue.push({
                ...payload,
                queuedAt: new Date().toISOString()
            });
            
            await chrome.storage.local.set({ offlineQueue: this.offlineQueue });
            this.showNotification('Saved offline - will sync when connected 📱', 'warning');
            
            // Schedule retry
            this.scheduleRetry();
        } else {
            this.showNotification('Failed to save - check connection', 'error');
        }
    }

    scheduleRetry() {
        // Use alarm API to retry when online
        chrome.runtime.sendMessage({
            action: 'scheduleOfflineSync',
            payload: { delay: 60000 } // 1 minute
        });
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

    showNotification(message, type = 'success') {
        // Remove existing notification
        const existing = document.getElementById('second-brain-notification');
        if (existing) existing.remove();

        const notification = document.createElement('div');
        notification.id = 'second-brain-notification';
        notification.className = `sb-notification sb-notification-${type}`;
        notification.innerHTML = `
            <div class="sb-notification-content">
                <div class="sb-notification-icon">${this.getNotificationIcon(type)}</div>
                <div class="sb-notification-message">${message}</div>
                <button class="sb-notification-close" onclick="this.parentElement.parentElement.remove()">✕</button>
            </div>
        `;

        document.body.appendChild(notification);

        // Animate in
        setTimeout(() => notification.classList.add('sb-show'), 10);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.classList.remove('sb-show');
                setTimeout(() => notification.remove(), 300);
            }
        }, 5000);
    }

    showProcessingNotification(message) {
        const existing = document.getElementById('second-brain-processing');
        if (existing) existing.remove();

        const notification = document.createElement('div');
        notification.id = 'second-brain-processing';
        notification.className = 'sb-processing-notification';
        notification.innerHTML = `
            <div class="sb-processing-content">
                <div class="sb-processing-spinner"></div>
                <div class="sb-processing-message">${message}</div>
            </div>
        `;

        document.body.appendChild(notification);
        
        // Auto-remove after 30 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 30000);
    }

    hideProcessingNotification() {
        const existing = document.getElementById('second-brain-processing');
        if (existing) existing.remove();
    }

    getNotificationIcon(type) {
        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️'
        };
        return icons[type] || 'ℹ️';
    }

    setupQuickCaptureUI() {
        // This method is called during init but the UI is created dynamically
        // We just ensure we don't have any lingering UI elements
        this.hideQuickCapture();
        this.hideMultiSelector();
    }
}

// Initialize content script
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        new SecondBrainContent();
    });
} else {
    new SecondBrainContent();
}