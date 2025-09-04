// Enhanced content script for Second Brain extension
// Provides intelligent page analysis, multi-selection, and advanced capture capabilities

class SecondBrainContentAnalyzer {
    constructor() {
        this.selectedElements = new Set();
        this.multiSelectMode = false;
        this.highlightStyle = null;
        this.observers = [];
        this.init();
    }

    init() {
        this.injectStyles();
        this.setupMessageListener();
        this.setupSelectionTracking();
        this.analyzePageContent();
    }

    injectStyles() {
        if (document.getElementById('second-brain-styles')) return;

        const style = document.createElement('style');
        style.id = 'second-brain-styles';
        style.textContent = `
            .second-brain-highlight {
                background: rgba(59, 130, 246, 0.2) !important;
                border: 2px solid #3b82f6 !important;
                border-radius: 4px !important;
                box-shadow: 0 0 8px rgba(59, 130, 246, 0.3) !important;
                position: relative !important;
            }

            .second-brain-selected {
                background: rgba(34, 197, 94, 0.3) !important;
                border: 2px solid #22c55e !important;
                box-shadow: 0 0 8px rgba(34, 197, 94, 0.4) !important;
            }

            .second-brain-tooltip {
                position: absolute;
                top: -30px;
                left: 0;
                background: #1f2937;
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                font-family: system-ui, -apple-system, sans-serif;
                z-index: 10000;
                pointer-events: none;
                white-space: nowrap;
            }

            .second-brain-capture-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                z-index: 9999;
                display: none;
                justify-content: center;
                align-items: center;
            }

            .second-brain-capture-dialog {
                background: white;
                padding: 24px;
                border-radius: 12px;
                box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
                max-width: 400px;
                width: 90%;
            }

            .second-brain-progress {
                display: flex;
                align-items: center;
                gap: 12px;
                color: #374151;
            }

            .second-brain-spinner {
                width: 20px;
                height: 20px;
                border: 2px solid #e5e7eb;
                border-top: 2px solid #3b82f6;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }

            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        `;
        document.head.appendChild(style);
    }

    setupMessageListener() {
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            switch (message.action) {
                case 'captureSelection':
                    this.captureSelection().then(sendResponse);
                    return true;
                
                case 'capturePage':
                    this.capturePage().then(sendResponse);
                    return true;
                
                case 'captureArticle':
                    this.captureArticle().then(sendResponse);
                    return true;
                
                case 'captureCode':
                    this.captureCode().then(sendResponse);
                    return true;
                
                case 'captureTable':
                    this.captureTable().then(sendResponse);
                    return true;
                
                case 'analyzeContent':
                    this.analyzePageContent().then(sendResponse);
                    return true;
                
                case 'toggleMultiSelect':
                    this.toggleMultiSelectMode();
                    sendResponse({ multiSelectMode: this.multiSelectMode });
                    return true;
                
                case 'clearMultiSelect':
                    this.clearMultiSelection();
                    sendResponse({ cleared: true });
                    return true;
                
                case 'captureMultiSelect':
                    this.captureMultiSelection().then(sendResponse);
                    return true;
                
                default:
                    sendResponse({ error: 'Unknown action' });
            }
        });
    }

    setupSelectionTracking() {
        // Track text selection changes
        document.addEventListener('selectionchange', () => {
            const selection = window.getSelection();
            if (selection.toString().trim().length > 0) {
                this.lastSelection = {
                    text: selection.toString(),
                    range: selection.getRangeAt(0).cloneRange(),
                    timestamp: Date.now()
                };
            }
        });

        // Track mouse hover for multi-select mode
        document.addEventListener('mouseover', (e) => {
            if (!this.multiSelectMode) return;
            
            const element = e.target;
            if (this.isSelectableElement(element) && !this.selectedElements.has(element)) {
                element.classList.add('second-brain-highlight');
            }
        });

        document.addEventListener('mouseout', (e) => {
            if (!this.multiSelectMode) return;
            
            const element = e.target;
            if (!this.selectedElements.has(element)) {
                element.classList.remove('second-brain-highlight');
            }
        });

        // Handle element selection in multi-select mode
        document.addEventListener('click', (e) => {
            if (!this.multiSelectMode) return;
            
            e.preventDefault();
            e.stopPropagation();
            
            const element = e.target;
            if (this.isSelectableElement(element)) {
                this.toggleElementSelection(element);
            }
        }, true);
    }

    async analyzePageContent() {
        const analysis = {
            title: document.title,
            url: window.location.href,
            domain: window.location.hostname,
            timestamp: new Date().toISOString(),
            hasSelection: false,
            hasArticle: false,
            hasCodeBlocks: false,
            hasTables: false,
            hasImages: false,
            contentTypes: [],
            suggestedTags: [],
            readabilityScore: 0,
            wordCount: 0,
            mainContent: null
        };

        // Check for user selection
        const selection = window.getSelection();
        if (selection.toString().trim().length > 0) {
            analysis.hasSelection = true;
            analysis.selectedText = selection.toString();
            analysis.wordCount = selection.toString().split(/\s+/).length;
        }

        // Detect article content
        const articleSelectors = [
            'article',
            '[role="main"]', 
            '.post-content',
            '.article-content',
            '.entry-content',
            '.content',
            'main'
        ];
        
        for (const selector of articleSelectors) {
            const element = document.querySelector(selector);
            if (element && this.getTextContent(element).length > 500) {
                analysis.hasArticle = true;
                analysis.mainContent = this.extractStructuredContent(element);
                analysis.contentTypes.push('article');
                break;
            }
        }

        // Detect code blocks
        const codeElements = document.querySelectorAll('pre, code[class*="language-"], .highlight, .code-block');
        if (codeElements.length > 0) {
            analysis.hasCodeBlocks = true;
            analysis.contentTypes.push('code');
            analysis.codeBlocks = Array.from(codeElements)
                .filter(el => el.textContent.trim().length > 20)
                .slice(0, 10)
                .map((el, index) => ({
                    index: index + 1,
                    content: el.textContent.trim(),
                    language: this.detectCodeLanguage(el),
                    lines: el.textContent.split('\n').length
                }));
        }

        // Detect tables
        const tables = document.querySelectorAll('table');
        if (tables.length > 0) {
            analysis.hasTables = true;
            analysis.contentTypes.push('table');
            analysis.tables = Array.from(tables)
                .filter(table => table.rows.length > 1)
                .slice(0, 5)
                .map((table, index) => ({
                    index: index + 1,
                    rows: table.rows.length,
                    columns: table.rows[0]?.cells.length || 0,
                    caption: table.caption?.textContent || null
                }));
        }

        // Detect images
        const images = document.querySelectorAll('img');
        const meaningfulImages = Array.from(images).filter(img => 
            img.width > 100 && 
            img.height > 100 && 
            !img.src.includes('data:image') &&
            !img.alt?.toLowerCase().includes('icon')
        );
        
        if (meaningfulImages.length > 0) {
            analysis.hasImages = true;
            analysis.contentTypes.push('images');
            analysis.images = meaningfulImages.slice(0, 10).map(img => ({
                src: img.src,
                alt: img.alt || '',
                width: img.width,
                height: img.height
            }));
        }

        // Generate suggested tags
        analysis.suggestedTags = this.generateSmartTags(analysis);

        // Calculate readability score
        const textContent = analysis.mainContent?.text || document.body.textContent;
        analysis.readabilityScore = this.calculateReadabilityScore(textContent);
        analysis.wordCount = textContent.split(/\s+/).length;

        return analysis;
    }

    generateSmartTags(analysis) {
        const tags = new Set();
        
        // Domain-based tags
        const domainTags = {
            'github.com': ['github', 'code', 'development'],
            'stackoverflow.com': ['programming', 'q&a', 'development'],
            'medium.com': ['article', 'blog'],
            'dev.to': ['programming', 'article'],
            'youtube.com': ['video', 'media'],
            'wikipedia.org': ['reference', 'encyclopedia'],
            'docs.': ['documentation', 'reference'],
            'blog.': ['blog', 'article']
        };

        for (const [domain, domainTagList] of Object.entries(domainTags)) {
            if (analysis.domain.includes(domain)) {
                domainTagList.forEach(tag => tags.add(tag));
                break;
            }
        }

        // Content-based tags
        if (analysis.hasCodeBlocks) tags.add('programming');
        if (analysis.hasTables) tags.add('data');
        if (analysis.hasImages) tags.add('visual');
        if (analysis.contentTypes.includes('article')) tags.add('reading');

        // Extract keywords from title
        const titleWords = analysis.title.toLowerCase()
            .replace(/[^\w\s]/g, ' ')
            .split(/\s+/)
            .filter(word => word.length > 3 && !this.isStopWord(word))
            .slice(0, 3);
        titleWords.forEach(word => tags.add(word));

        // Tech-specific tags based on content
        const techKeywords = {
            'javascript': ['js', 'frontend'],
            'python': ['python', 'backend'],
            'react': ['react', 'frontend'],
            'vue': ['vue', 'frontend'],
            'docker': ['docker', 'devops'],
            'kubernetes': ['k8s', 'devops'],
            'machine learning': ['ml', 'ai'],
            'artificial intelligence': ['ai', 'ml']
        };

        const pageText = document.body.textContent.toLowerCase();
        for (const [keyword, keywordTags] of Object.entries(techKeywords)) {
            if (pageText.includes(keyword)) {
                keywordTags.forEach(tag => tags.add(tag));
            }
        }

        return Array.from(tags).slice(0, 8);
    }

    isStopWord(word) {
        const stopWords = ['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her', 'was', 'one', 'our', 'had', 'day', 'get', 'use', 'man', 'new', 'now', 'way', 'may', 'say'];
        return stopWords.includes(word.toLowerCase());
    }

    calculateReadabilityScore(text) {
        if (!text || text.length < 100) return 5;
        
        const sentences = text.split(/[.!?]+/).filter(s => s.trim().length > 0);
        const words = text.split(/\s+/);
        const syllables = this.countSyllables(text);
        
        // Flesch Reading Ease Score (simplified)
        const avgSentenceLength = words.length / sentences.length;
        const avgSyllablesPerWord = syllables / words.length;
        
        const score = 206.835 - (1.015 * avgSentenceLength) - (84.6 * avgSyllablesPerWord);
        
        // Convert to 1-10 scale (10 = most readable)
        if (score >= 80) return 9;
        if (score >= 70) return 8;
        if (score >= 60) return 7;
        if (score >= 50) return 6;
        if (score >= 40) return 5;
        if (score >= 30) return 4;
        if (score >= 20) return 3;
        return 2;
    }

    countSyllables(text) {
        // Simplified syllable counting
        return text.toLowerCase()
            .replace(/[^a-z]/g, '')
            .replace(/[aeiouy]{2,}/g, 'a')
            .replace(/[^aeiouy]/g, '')
            .length || 1;
    }

    detectCodeLanguage(element) {
        // Try to detect language from class names
        const className = element.className;
        const langMatch = className.match(/(?:lang|language)-(\w+)/);
        if (langMatch) return langMatch[1];
        
        // Try to detect from content patterns
        const content = element.textContent;
        if (content.includes('function ') || content.includes('const ') || content.includes('=>')) {
            return 'javascript';
        }
        if (content.includes('def ') || content.includes('import ')) {
            return 'python';
        }
        if (content.includes('public class') || content.includes('System.out')) {
            return 'java';
        }
        if (content.includes('#include') || content.includes('int main')) {
            return 'cpp';
        }
        
        return 'text';
    }

    async captureSelection() {
        const selection = window.getSelection();
        if (!selection.toString().trim()) {
            return { error: 'No text selected' };
        }

        this.showCaptureProgress('Capturing selection...');

        const range = selection.getRangeAt(0);
        const container = range.commonAncestorContainer.parentElement;
        
        const captureData = {
            type: 'selection',
            title: document.title,
            url: window.location.href,
            content: selection.toString(),
            context: this.getContextAroundSelection(range),
            metadata: {
                domain: window.location.hostname,
                timestamp: new Date().toISOString(),
                wordCount: selection.toString().split(/\s+/).length
            }
        };

        this.hideCaptureProgress();
        return captureData;
    }

    async captureArticle() {
        this.showCaptureProgress('Extracting article...');

        const articleElement = this.findMainArticle();
        if (!articleElement) {
            this.hideCaptureProgress();
            return { error: 'No article content found' };
        }

        const captureData = {
            type: 'article',
            title: document.title,
            url: window.location.href,
            content: this.extractStructuredContent(articleElement),
            metadata: {
                domain: window.location.hostname,
                timestamp: new Date().toISOString(),
                author: this.extractAuthor(),
                publishDate: this.extractPublishDate(),
                readabilityScore: this.calculateReadabilityScore(articleElement.textContent)
            }
        };

        this.hideCaptureProgress();
        return captureData;
    }

    findMainArticle() {
        const selectors = [
            'article',
            '[role="main"]',
            '.post-content',
            '.article-content', 
            '.entry-content',
            'main .content',
            '.main-content'
        ];
        
        for (const selector of selectors) {
            const element = document.querySelector(selector);
            if (element && this.getTextContent(element).length > 500) {
                return element;
            }
        }
        
        return null;
    }

    extractStructuredContent(element) {
        const clone = element.cloneNode(true);
        
        // Remove unwanted elements
        const unwantedSelectors = [
            'script', 'style', 'nav', 'header', 'footer', 'aside',
            '.sidebar', '.ad', '.advertisement', '.social-share',
            '.comments', '.comment', '.navigation', '.menu'
        ];
        
        unwantedSelectors.forEach(selector => {
            clone.querySelectorAll(selector).forEach(el => el.remove());
        });

        // Convert to structured text with markdown-like formatting
        let text = '';
        const walker = document.createTreeWalker(
            clone,
            NodeFilter.SHOW_ELEMENT,
            {
                acceptNode: (node) => {
                    const tagName = node.tagName.toLowerCase();
                    if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'blockquote', 'pre', 'code'].includes(tagName)) {
                        return NodeFilter.FILTER_ACCEPT;
                    }
                    return NodeFilter.FILTER_SKIP;
                }
            }
        );

        let node;
        while (node = walker.nextNode()) {
            const tagName = node.tagName.toLowerCase();
            const textContent = node.textContent.trim();
            
            if (!textContent) continue;
            
            switch (tagName) {
                case 'h1':
                    text += `\n# ${textContent}\n\n`;
                    break;
                case 'h2':
                    text += `\n## ${textContent}\n\n`;
                    break;
                case 'h3':
                    text += `\n### ${textContent}\n\n`;
                    break;
                case 'h4':
                case 'h5':
                case 'h6':
                    text += `\n#### ${textContent}\n\n`;
                    break;
                case 'p':
                    text += `${textContent}\n\n`;
                    break;
                case 'li':
                    text += `- ${textContent}\n`;
                    break;
                case 'blockquote':
                    text += `> ${textContent}\n\n`;
                    break;
                case 'pre':
                case 'code':
                    text += `\`\`\`\n${textContent}\n\`\`\`\n\n`;
                    break;
            }
        }

        return {
            text: text.trim(),
            html: clone.innerHTML,
            wordCount: text.split(/\s+/).length
        };
    }

    getTextContent(element) {
        return element.textContent || element.innerText || '';
    }

    extractAuthor() {
        const selectors = [
            'meta[name="author"]',
            '.author',
            '.byline',
            '[rel="author"]'
        ];
        
        for (const selector of selectors) {
            const element = document.querySelector(selector);
            if (element) {
                return element.content || element.textContent || element.href;
            }
        }
        
        return null;
    }

    extractPublishDate() {
        const selectors = [
            'meta[property="article:published_time"]',
            'meta[name="date"]',
            'time[datetime]',
            '.publish-date',
            '.date'
        ];
        
        for (const selector of selectors) {
            const element = document.querySelector(selector);
            if (element) {
                return element.content || element.getAttribute('datetime') || element.textContent;
            }
        }
        
        return null;
    }

    showCaptureProgress(message) {
        let overlay = document.getElementById('second-brain-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'second-brain-overlay';
            overlay.className = 'second-brain-capture-overlay';
            overlay.innerHTML = `
                <div class="second-brain-capture-dialog">
                    <div class="second-brain-progress">
                        <div class="second-brain-spinner"></div>
                        <span id="progress-message">${message}</span>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
        }
        
        document.getElementById('progress-message').textContent = message;
        overlay.style.display = 'flex';
    }

    hideCaptureProgress() {
        const overlay = document.getElementById('second-brain-overlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }

    getContextAroundSelection(range) {
        const container = range.commonAncestorContainer.parentElement;
        const containerText = container.textContent;
        const selectedText = range.toString();
        const startIndex = containerText.indexOf(selectedText);
        
        if (startIndex === -1) return '';
        
        const contextStart = Math.max(0, startIndex - 100);
        const contextEnd = Math.min(containerText.length, startIndex + selectedText.length + 100);
        
        return containerText.slice(contextStart, contextEnd);
    }

    // Multi-selection functionality
    toggleMultiSelectMode() {
        this.multiSelectMode = !this.multiSelectMode;
        
        if (!this.multiSelectMode) {
            this.clearMultiSelection();
        }
        
        document.body.style.cursor = this.multiSelectMode ? 'crosshair' : 'default';
        
        // Show visual indicator
        if (this.multiSelectMode) {
            this.showMultiSelectIndicator();
        } else {
            this.hideMultiSelectIndicator();
        }
    }

    isSelectableElement(element) {
        const selectableTypes = ['P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'LI', 'BLOCKQUOTE', 'PRE', 'TABLE', 'IMG'];
        return selectableTypes.includes(element.tagName) && 
               element.textContent.trim().length > 10;
    }

    toggleElementSelection(element) {
        if (this.selectedElements.has(element)) {
            this.selectedElements.delete(element);
            element.classList.remove('second-brain-selected');
        } else {
            this.selectedElements.add(element);
            element.classList.add('second-brain-selected');
        }
        
        this.updateMultiSelectCount();
    }

    clearMultiSelection() {
        this.selectedElements.forEach(element => {
            element.classList.remove('second-brain-selected', 'second-brain-highlight');
        });
        this.selectedElements.clear();
        this.updateMultiSelectCount();
    }

    updateMultiSelectCount() {
        chrome.runtime.sendMessage({
            action: 'updateMultiSelectCount',
            count: this.selectedElements.size
        });
    }

    async captureMultiSelection() {
        if (this.selectedElements.size === 0) {
            return { error: 'No elements selected' };
        }

        this.showCaptureProgress('Capturing selected elements...');

        const elements = Array.from(this.selectedElements);
        const content = elements.map((element, index) => {
            const tagName = element.tagName.toLowerCase();
            const text = element.textContent.trim();
            
            if (tagName.startsWith('h')) {
                return `## ${text}`;
            } else if (tagName === 'li') {
                return `- ${text}`;
            } else if (tagName === 'blockquote') {
                return `> ${text}`;
            } else if (tagName === 'pre') {
                return `\`\`\`\n${text}\n\`\`\``;
            } else {
                return text;
            }
        }).join('\n\n');

        const captureData = {
            type: 'multi-selection',
            title: document.title + ' - Selected Elements',
            url: window.location.href,
            content: content,
            metadata: {
                domain: window.location.hostname,
                timestamp: new Date().toISOString(),
                elementsCount: elements.length,
                elementTypes: [...new Set(elements.map(el => el.tagName.toLowerCase()))]
            }
        };

        this.clearMultiSelection();
        this.toggleMultiSelectMode(); // Exit multi-select mode
        this.hideCaptureProgress();
        
        return captureData;
    }

    showMultiSelectIndicator() {
        if (document.getElementById('multi-select-indicator')) return;
        
        const indicator = document.createElement('div');
        indicator.id = 'multi-select-indicator';
        indicator.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #3b82f6;
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
            font-family: system-ui, -apple-system, sans-serif;
            z-index: 10000;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        `;
        indicator.textContent = 'Multi-select mode: Click elements to select';
        document.body.appendChild(indicator);
    }

    hideMultiSelectIndicator() {
        const indicator = document.getElementById('multi-select-indicator');
        if (indicator) {
            indicator.remove();
        }
    }
}

// Initialize content analyzer when page loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        new SecondBrainContentAnalyzer();
    });
} else {
    new SecondBrainContentAnalyzer();
}