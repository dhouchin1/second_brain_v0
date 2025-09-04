// background.js - Enhanced service worker for Second Brain extension
class SecondBrainBackground {
    constructor() {
        this.offlineQueue = [];
        this.retryAttempts = new Map();
        this.maxRetries = 3;
        this.retryDelay = 60000; // 1 minute
        this.init();
    }

    async init() {
        this.setupContextMenus();
        this.setupMessageHandlers();
        this.setupInstallHandler();
        this.setupAlarms();
        this.setupCommandHandlers();
        this.loadOfflineQueue();
        this.setupOnlineListener();
    }

    setupContextMenus() {
        chrome.runtime.onInstalled.addListener(() => {
            // Text selection context menu
            chrome.contextMenus.create({
                id: 'saveSelection',
                title: 'Save to Second Brain',
                contexts: ['selection']
            });

            // Enhanced page context menu
            chrome.contextMenus.create({
                id: 'savePage',
                title: 'Save page to Second Brain',
                contexts: ['page']
            });

            // AI-powered capture
            chrome.contextMenus.create({
                id: 'smartCapture',
                title: '🧠 Smart AI capture',
                contexts: ['page']
            });

            // Link context menu
            chrome.contextMenus.create({
                id: 'saveLink',
                title: 'Save link to Second Brain',
                contexts: ['link']
            });

            // Image context menu with AI analysis
            chrome.contextMenus.create({
                id: 'saveImage',
                title: 'Save image to Second Brain',
                contexts: ['image']
            });

            // Video capture
            chrome.contextMenus.create({
                id: 'saveVideo',
                title: 'Save video info to Second Brain',
                contexts: ['video']
            });

            // Code snippet detection
            chrome.contextMenus.create({
                id: 'saveCode',
                title: 'Save as code snippet',
                contexts: ['selection']
            });
        });

        chrome.contextMenus.onClicked.addListener((info, tab) => {
            this.handleContextMenuClick(info, tab);
        });
    }

    async handleContextMenuClick(info, tab) {
        const settings = await chrome.storage.sync.get(['apiUrl', 'authToken']);
        const apiUrl = settings.apiUrl || 'http://localhost:8082';
        const authToken = settings.authToken || '';

        switch (info.menuItemId) {
            case 'saveSelection':
                await this.saveSelection(info, tab, apiUrl, authToken);
                break;
            case 'savePage':
                await this.savePage(tab, apiUrl, authToken);
                break;
            case 'smartCapture':
                await this.performSmartCapture(tab, apiUrl, authToken);
                break;
            case 'saveLink':
                await this.saveLink(info, tab, apiUrl, authToken);
                break;
            case 'saveImage':
                await this.saveImage(info, tab, apiUrl, authToken);
                break;
            case 'saveVideo':
                await this.saveVideo(info, tab, apiUrl, authToken);
                break;
            case 'saveCode':
                await this.saveCodeSnippet(info, tab, apiUrl, authToken);
                break;
        }
    }

    async saveSelection(info, tab, apiUrl, authToken) {
        const payload = {
            note: info.selectionText,
            tags: 'web,selection',
            type: 'browser',
            metadata: {
                url: tab.url,
                title: tab.title,
                captureType: 'selection',
                timestamp: new Date().toISOString(),
                selectionText: info.selectionText
            }
        };

        await this.sendToSecondBrainWithRetry(payload, apiUrl, authToken);
        this.showNotification('Selection saved to Second Brain!');
    }

    async saveCodeSnippet(info, tab, apiUrl, authToken) {
        const language = await this.detectLanguage(info.selectionText);
        
        const payload = {
            note: `\`\`\`${language}\n${info.selectionText}\n\`\`\``,
            tags: `web,code,${language},snippet`,
            type: 'browser',
            metadata: {
                url: tab.url,
                title: tab.title,
                captureType: 'code-snippet',
                timestamp: new Date().toISOString(),
                language: language,
                codeContent: info.selectionText
            }
        };

        await this.sendToSecondBrainWithRetry(payload, apiUrl, authToken);
        this.showNotification(`${language.charAt(0).toUpperCase() + language.slice(1)} code snippet saved! 💻`);
    }

    async savePage(tab, apiUrl, authToken) {
        try {
            // Enhanced page extraction with AI analysis
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: this.extractPageContentAdvanced
            });

            const payload = {
                note: result.result.content,
                tags: this.generateAdvancedPageTags(result.result),
                type: 'browser',
                metadata: {
                    url: result.result.url,
                    title: result.result.title,
                    captureType: 'page',
                    timestamp: new Date().toISOString(),
                    pageAnalysis: result.result.analysis,
                    structuredData: result.result.structuredData,
                    readabilityScore: result.result.readabilityScore,
                    wordCount: result.result.wordCount,
                    estimatedReadingTime: result.result.estimatedReadingTime
                }
            };

            await this.sendToSecondBrainWithRetry(payload, apiUrl, authToken);
            this.showNotification('Page saved to Second Brain!');
        } catch (error) {
            console.error('Failed to save page:', error);
            this.showNotification('Failed to save page', 'error');
        }
    }

    async performSmartCapture(tab, apiUrl, authToken) {
        this.showNotification('🧠 AI analyzing page content...', 'info');

        try {
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: this.extractIntelligentPageContent
            });

            const payload = {
                note: result.result.content,
                tags: result.result.tags,
                type: 'browser',
                aiProcessing: {
                    smartExtraction: true,
                    summarize: true,
                    generateTags: true,
                    extractKeyPoints: true,
                    analyzeSentiment: true
                },
                metadata: {
                    url: result.result.url,
                    title: result.result.title,
                    captureType: 'smart-capture',
                    timestamp: new Date().toISOString(),
                    intelligentAnalysis: result.result.analysis,
                    confidence: result.result.confidence,
                    contentType: result.result.contentType
                }
            };

            await this.sendToSecondBrainWithRetry(payload, apiUrl, authToken, 'saveContentWithAI');
            this.showNotification('Smart capture completed! 🤖🧠');
        } catch (error) {
            console.error('Smart capture failed:', error);
            this.showNotification('Smart capture failed', 'error');
        }
    }

    async saveLink(info, tab, apiUrl, authToken) {
        // Enhanced link saving with preview extraction
        try {
            const linkPreview = await this.extractLinkPreview(info.linkUrl);
            
            const payload = {
                note: `# ${linkPreview.title || info.linkUrl}\n\n${linkPreview.description || ''}\n\n**URL**: ${info.linkUrl}\n\n**Context**: ${info.selectionText || 'No context'}`,
                tags: `web,link,${this.generateDomainTag(info.linkUrl)}`,
                type: 'browser',
                metadata: {
                    url: info.linkUrl,
                    sourceUrl: tab.url,
                    title: linkPreview.title || info.linkUrl,
                    captureType: 'link',
                    timestamp: new Date().toISOString(),
                    linkPreview: linkPreview,
                    context: info.selectionText
                }
            };

            await this.sendToSecondBrainWithRetry(payload, apiUrl, authToken);
            this.showNotification('Link saved to Second Brain!');
        } catch (error) {
            // Fallback to simple link save
            await this.saveSimpleLink(info, tab, apiUrl, authToken);
        }
    }

    async saveSimpleLink(info, tab, apiUrl, authToken) {
        const payload = {
            note: `Link: ${info.linkUrl}\n\nContext: ${info.selectionText || 'No context'}`,
            tags: `web,link,${this.generateDomainTag(info.linkUrl)}`,
            type: 'browser',
            metadata: {
                url: info.linkUrl,
                sourceUrl: tab.url,
                title: info.linkUrl,
                captureType: 'link',
                timestamp: new Date().toISOString()
            }
        };

        await this.sendToSecondBrainWithRetry(payload, apiUrl, authToken);
        this.showNotification('Link saved to Second Brain!');
    }

    async saveImage(info, tab, apiUrl, authToken) {
        try {
            const imageAnalysis = await this.analyzeImage(info.srcUrl);
            
            const payload = {
                note: `# Image from ${tab.title}\n\n![Image](${info.srcUrl})\n\n**Alt text**: ${imageAnalysis.alt || 'None'}\n\n**Analysis**: ${imageAnalysis.description || 'Visual content captured from web page'}`,
                tags: `web,image,visual,${this.generateDomainTag(tab.url)}`,
                type: 'browser',
                metadata: {
                    url: tab.url,
                    title: tab.title,
                    imageUrl: info.srcUrl,
                    captureType: 'image',
                    timestamp: new Date().toISOString(),
                    imageAnalysis: imageAnalysis
                }
            };

            await this.sendToSecondBrainWithRetry(payload, apiUrl, authToken);
            this.showNotification('Image saved to Second Brain! 📸');
        } catch (error) {
            console.error('Failed to save image:', error);
            this.showNotification('Failed to save image', 'error');
        }
    }

    async saveVideo(info, tab, apiUrl, authToken) {
        const payload = {
            note: `# Video from ${tab.title}\n\n**Video URL**: ${info.srcUrl}\n\n**Source Page**: ${tab.url}`,
            tags: `web,video,media,${this.generateDomainTag(tab.url)}`,
            type: 'browser',
            metadata: {
                url: tab.url,
                title: tab.title,
                videoUrl: info.srcUrl,
                captureType: 'video',
                timestamp: new Date().toISOString()
            }
        };

        await this.sendToSecondBrainWithRetry(payload, apiUrl, authToken);
        this.showNotification('Video info saved to Second Brain! 🎥');
    }

    // Content extraction functions that run in page context
    extractPageContentAdvanced() {
        const analyzer = {
            findMainContent() {
                const selectors = [
                    'article', 'main', '[role="main"]', '.content', '.post', 
                    '.entry', '.article', '#content', '#main', '.main-content'
                ];
                
                const candidates = selectors
                    .map(sel => document.querySelector(sel))
                    .filter(Boolean)
                    .concat([document.body]);
                
                return candidates.reduce((best, candidate) => {
                    const score = this.scoreElement(candidate);
                    return score > (best.score || 0) ? {element: candidate, score} : best;
                }, {}).element;
            },

            scoreElement(element) {
                const textLength = element.innerText?.length || 0;
                const linkDensity = this.calculateLinkDensity(element);
                const paragraphCount = element.querySelectorAll('p').length;
                const headerCount = element.querySelectorAll('h1,h2,h3,h4,h5,h6').length;
                
                return (textLength * 0.5) + (paragraphCount * 10) + (headerCount * 5) - (linkDensity * 100);
            },

            calculateLinkDensity(element) {
                const textLength = element.innerText?.length || 1;
                const linkText = Array.from(element.querySelectorAll('a'))
                    .reduce((sum, a) => sum + (a.innerText?.length || 0), 0);
                return linkText / textLength;
            },

            cleanContent(element) {
                const clone = element.cloneNode(true);
                const unwanted = clone.querySelectorAll(`
                    script, style, nav, header, footer, aside,
                    .ad, .advertisement, .ads, .sidebar, .menu, .navigation,
                    .comments, .social, .share, .related, .recommended,
                    [class*="ad"], [id*="ad"], [class*="sidebar"], [id*="sidebar"]
                `);
                unwanted.forEach(el => el.remove());
                return clone;
            },

            extractStructuredData() {
                const data = {};
                
                // JSON-LD
                document.querySelectorAll('script[type="application/ld+json"]').forEach((script, i) => {
                    try {
                        data[`jsonLd${i}`] = JSON.parse(script.textContent);
                    } catch (e) {}
                });
                
                // Open Graph
                data.openGraph = {};
                document.querySelectorAll('meta[property^="og:"]').forEach(meta => {
                    const prop = meta.getAttribute('property').replace('og:', '');
                    data.openGraph[prop] = meta.getAttribute('content');
                });
                
                return data;
            },

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
        };

        const mainContent = analyzer.findMainContent();
        const cleanContent = analyzer.cleanContent(mainContent);
        const text = cleanContent.innerText.trim();
        const structuredData = analyzer.extractStructuredData();
        const readabilityScore = analyzer.calculateReadability(text);
        const wordCount = text.split(/\s+/).length;

        return {
            content: `# ${document.title}\n\n${text}`,
            url: window.location.href,
            title: document.title,
            analysis: {
                mainContentFound: !!mainContent,
                contentQuality: readabilityScore > 60 ? 'high' : readabilityScore > 30 ? 'medium' : 'low'
            },
            structuredData: structuredData,
            readabilityScore: readabilityScore,
            wordCount: wordCount,
            estimatedReadingTime: Math.ceil(wordCount / 200)
        };
    }

    extractIntelligentPageContent() {
        const extractor = {
            performAdvancedExtraction() {
                const contentElement = this.findBestContentElement();
                const cleanElement = this.cleanElement(contentElement);
                const content = this.convertToMarkdown(cleanElement);
                const analysis = this.analyzeContent(content);
                
                return {
                    content: content,
                    analysis: analysis,
                    tags: this.generateSmartTags(analysis),
                    confidence: this.calculateConfidence(analysis),
                    contentType: this.detectContentType(content)
                };
            },

            findBestContentElement() {
                const candidates = [
                    document.querySelector('article'),
                    document.querySelector('main'),
                    document.querySelector('[role="main"]'),
                    document.querySelector('.content'),
                    document.querySelector('.post'),
                    document.body
                ].filter(Boolean);

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

            cleanElement(element) {
                const clone = element.cloneNode(true);
                const selectors = [
                    'script', 'style', 'nav', 'header', 'footer', 'aside',
                    '.sidebar', '.menu', '.ad', '.advertisement', '.comments',
                    '[class*="sidebar"]', '[id*="sidebar"]', '[class*="ad"]'
                ];
                
                selectors.forEach(selector => {
                    clone.querySelectorAll(selector).forEach(el => el.remove());
                });
                
                return clone;
            },

            convertToMarkdown(element) {
                let markdown = `# ${document.title}\n\n`;
                markdown += this.processNode(element);
                return markdown;
            },

            processNode(node) {
                let result = '';
                
                node.childNodes.forEach(child => {
                    if (child.nodeType === Node.TEXT_NODE) {
                        const text = child.textContent.trim();
                        if (text) result += text + ' ';
                    } else if (child.nodeType === Node.ELEMENT_NODE) {
                        const tag = child.tagName.toLowerCase();
                        
                        switch (tag) {
                            case 'h1': result += `\n# ${child.innerText}\n\n`; break;
                            case 'h2': result += `\n## ${child.innerText}\n\n`; break;
                            case 'h3': result += `\n### ${child.innerText}\n\n`; break;
                            case 'h4': result += `\n#### ${child.innerText}\n\n`; break;
                            case 'p': result += `${child.innerText}\n\n`; break;
                            case 'blockquote': result += `> ${child.innerText}\n\n`; break;
                            case 'code':
                            case 'pre': result += `\`\`\`\n${child.innerText}\n\`\`\`\n\n`; break;
                            default: result += this.processNode(child);
                        }
                    }
                });
                
                return result;
            },

            analyzeContent(content) {
                return {
                    wordCount: content.split(/\s+/).length,
                    readingTime: Math.ceil(content.split(/\s+/).length / 200),
                    topics: this.extractTopics(content),
                    sentiment: this.analyzeSentiment(content),
                    complexity: this.assessComplexity(content)
                };
            },

            extractTopics(content) {
                const words = content.toLowerCase().match(/\b\w{4,}\b/g) || [];
                const frequency = {};
                
                words.forEach(word => {
                    frequency[word] = (frequency[word] || 0) + 1;
                });
                
                return Object.entries(frequency)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 5)
                    .map(([word]) => word);
            },

            analyzeSentiment(content) {
                const positiveWords = ['good', 'great', 'excellent', 'amazing', 'wonderful', 'fantastic'];
                const negativeWords = ['bad', 'terrible', 'awful', 'horrible', 'disappointing'];
                
                const words = content.toLowerCase().split(/\s+/);
                const positive = words.filter(word => positiveWords.includes(word)).length;
                const negative = words.filter(word => negativeWords.includes(word)).length;
                
                return positive > negative ? 'positive' : negative > positive ? 'negative' : 'neutral';
            },

            assessComplexity(content) {
                const sentences = content.split(/[.!?]+/).length;
                const words = content.split(/\s+/).length;
                const avgWordsPerSentence = words / sentences;
                
                return avgWordsPerSentence > 20 ? 'high' : avgWordsPerSentence > 15 ? 'medium' : 'low';
            },

            generateSmartTags(analysis) {
                const tags = ['web', 'smart-capture'];
                
                // Add domain
                try {
                    const domain = new URL(window.location.href).hostname.replace('www.', '');
                    tags.push(domain);
                } catch (e) {}
                
                // Add content-based tags
                tags.push(...analysis.topics.slice(0, 3));
                tags.push(analysis.sentiment);
                tags.push(`complexity-${analysis.complexity}`);
                
                return tags.join(',');
            },

            calculateConfidence(analysis) {
                let confidence = 0.5;
                
                if (analysis.wordCount > 100) confidence += 0.2;
                if (analysis.topics.length > 0) confidence += 0.2;
                if (analysis.sentiment !== 'neutral') confidence += 0.1;
                
                return Math.min(1.0, confidence);
            },

            detectContentType(content) {
                if (content.match(/```/)) return 'technical';
                if (content.match(/recipe|ingredients|cooking/i)) return 'recipe';
                if (content.match(/tutorial|how to|guide/i)) return 'tutorial';
                if (content.match(/news|breaking|report/i)) return 'news';
                return 'article';
            }
        };

        const result = extractor.performAdvancedExtraction();
        
        return {
            ...result,
            url: window.location.href,
            title: document.title
        };
    }

    // Utility functions
    async detectLanguage(code) {
        const patterns = {
            javascript: /\b(function|var|let|const|if|else|for|while|return|class|import|export)\b/g,
            python: /\b(def|import|from|if|elif|else|for|while|return|class|try|except)\b/g,
            java: /\b(public|private|protected|class|interface|extends|implements|import|package)\b/g,
            html: /<\/?[a-z][\s\S]*>/i,
            css: /\{[\s\S]*?\}/,
            json: /^\s*[\{\[]/,
            sql: /\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b/i
        };

        for (const [lang, pattern] of Object.entries(patterns)) {
            if (pattern.test(code)) return lang;
        }
        
        return 'text';
    }

    async extractLinkPreview(url) {
        try {
            // This would typically involve fetching the URL and parsing meta tags
            // For now, return basic info
            return {
                title: url,
                description: 'Link captured from web page',
                domain: new URL(url).hostname
            };
        } catch (e) {
            return { title: url, description: '', domain: '' };
        }
    }

    async analyzeImage(imageUrl) {
        try {
            // Basic image analysis - in a real implementation, this could use AI services
            return {
                alt: 'Image content',
                description: 'Visual content captured from web page',
                url: imageUrl,
                type: this.getImageType(imageUrl)
            };
        } catch (e) {
            return { alt: '', description: '', url: imageUrl };
        }
    }

    getImageType(url) {
        const ext = url.split('.').pop().toLowerCase();
        const types = {
            'jpg': 'JPEG Image',
            'jpeg': 'JPEG Image', 
            'png': 'PNG Image',
            'gif': 'GIF Image',
            'svg': 'SVG Vector',
            'webp': 'WebP Image'
        };
        return types[ext] || 'Image';
    }

    generateAdvancedPageTags(pageData) {
        const tags = ['web', 'page'];
        
        // Domain tag
        try {
            const domain = new URL(pageData.url).hostname.replace('www.', '');
            tags.push(domain);
        } catch (e) {}
        
        // Content quality tags
        if (pageData.readabilityScore > 70) tags.push('easy-read');
        else if (pageData.readabilityScore < 30) tags.push('complex');
        
        // Reading time tags
        if (pageData.estimatedReadingTime < 2) tags.push('quick-read');
        else if (pageData.estimatedReadingTime > 10) tags.push('long-read');
        
        // Structured data tags
        if (pageData.structuredData.openGraph?.type) {
            tags.push(pageData.structuredData.openGraph.type);
        }
        
        return tags.join(',');
    }

    generateDomainTag(url) {
        try {
            return new URL(url).hostname.replace('www.', '');
        } catch (e) {
            return 'unknown-domain';
        }
    }

    async sendToSecondBrainWithRetry(payload, apiUrl, authToken, endpoint = 'saveContent') {
        const maxRetries = 3;
        let lastError;
        
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                await this.sendToSecondBrain(payload, apiUrl, authToken, endpoint);
                return; // Success
            } catch (error) {
                lastError = error;
                
                if (attempt < maxRetries) {
                    await new Promise(resolve => setTimeout(resolve, attempt * 1000));
                }
            }
        }
        
        // All retries failed, add to offline queue
        await this.addToOfflineQueue({
            payload,
            apiUrl,
            authToken,
            endpoint,
            timestamp: new Date().toISOString()
        });
        
        this.showNotification('Saved offline - will sync when connected 📱', 'warning');
    }

    async sendToSecondBrain(payload, apiUrl, authToken, endpoint = 'saveContent') {
        const endpointMap = {
            'saveContent': '/webhook/browser',
            'saveContentWithAI': '/api/ai/capture'
        };
        
        const url = `${apiUrl}${endpointMap[endpoint] || endpointMap.saveContent}`;
        
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
    }

    async addToOfflineQueue(item) {
        this.offlineQueue.push(item);
        await chrome.storage.local.set({ offlineQueue: this.offlineQueue });
    }

    async loadOfflineQueue() {
        const stored = await chrome.storage.local.get(['offlineQueue']);
        this.offlineQueue = stored.offlineQueue || [];
    }

    async processOfflineQueue() {
        if (this.offlineQueue.length === 0) return;
        
        const itemsToProcess = [...this.offlineQueue];
        let processedCount = 0;
        
        for (const item of itemsToProcess) {
            try {
                await this.sendToSecondBrain(
                    item.payload,
                    item.apiUrl,
                    item.authToken,
                    item.endpoint
                );
                
                // Remove from queue on success
                const index = this.offlineQueue.indexOf(item);
                if (index > -1) {
                    this.offlineQueue.splice(index, 1);
                    processedCount++;
                }
            } catch (error) {
                console.error('Failed to process offline item:', error);
            }
        }
        
        if (processedCount > 0) {
            await chrome.storage.local.set({ offlineQueue: this.offlineQueue });
            this.showNotification(`Synced ${processedCount} offline captures! 🔄`);
        }
    }

    setupOnlineListener() {
        // Listen for online status changes
        chrome.webRequest.onCompleted.addListener(
            () => {
                // Check if we can reach our API
                this.checkConnectionAndSync();
            },
            { urls: ["<all_urls>"] }
        );
    }

    async checkConnectionAndSync() {
        try {
            const settings = await chrome.storage.sync.get(['apiUrl']);
            const apiUrl = settings.apiUrl || 'http://localhost:8082';
            
            const response = await fetch(`${apiUrl}/health`);
            if (response.ok && this.offlineQueue.length > 0) {
                await this.processOfflineQueue();
            }
        } catch (error) {
            // Still offline or unreachable
        }
    }

    setupCommandHandlers() {
        chrome.commands.onCommand.addListener((command) => {
            switch (command) {
                case 'quick-capture':
                    this.performQuickCapture();
                    break;
                case 'capture-page':
                    this.performPageCapture();
                    break;
            }
        });
    }

    async performQuickCapture() {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        await this.captureSelection(tab);
    }

    async performPageCapture() {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const settings = await chrome.storage.sync.get(['apiUrl', 'authToken']);
        await this.savePage(tab, settings.apiUrl, settings.authToken);
    }

    async captureSelection(tab) {
        try {
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: () => {
                    const selection = window.getSelection();
                    return selection.toString().trim();
                }
            });

            if (result.result) {
                const settings = await chrome.storage.sync.get(['apiUrl', 'authToken']);
                await this.saveSelection(
                    { selectionText: result.result },
                    tab,
                    settings.apiUrl,
                    settings.authToken
                );
            } else {
                this.showNotification('No text selected', 'warning');
            }
        } catch (error) {
            this.showNotification('Failed to capture selection', 'error');
        }
    }

    setupAlarms() {
        // Schedule periodic offline sync attempts
        chrome.alarms.create('syncOfflineQueue', { periodInMinutes: 5 });
        
        chrome.alarms.onAlarm.addListener((alarm) => {
            if (alarm.name === 'syncOfflineQueue') {
                this.checkConnectionAndSync();
            }
        });
    }

    setupMessageHandlers() {
        chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
            switch (request.action) {
                case 'saveContent':
                    this.handleSaveContent(request.payload, sender.tab, sendResponse);
                    return true; // Keep channel open for async response
                    
                case 'saveContentWithAI':
                    this.handleSaveContentWithAI(request.payload, sender.tab, sendResponse);
                    return true;
                    
                case 'scheduleOfflineSync':
                    this.scheduleOfflineSync(request.payload);
                    sendResponse({ success: true });
                    break;
                    
                case 'getConnectionStatus':
                    this.getConnectionStatus(sendResponse);
                    return true;
            }
        });
    }

    async handleSaveContent(payload, tab, sendResponse) {
        try {
            const settings = await chrome.storage.sync.get(['apiUrl', 'authToken']);
            await this.sendToSecondBrainWithRetry(
                payload,
                settings.apiUrl || 'http://localhost:8082',
                settings.authToken || ''
            );
            sendResponse({ success: true });
        } catch (error) {
            sendResponse({ success: false, error: error.message });
        }
    }

    async handleSaveContentWithAI(payload, tab, sendResponse) {
        try {
            const settings = await chrome.storage.sync.get(['apiUrl', 'authToken']);
            await this.sendToSecondBrainWithRetry(
                payload,
                settings.apiUrl || 'http://localhost:8082',
                settings.authToken || '',
                'saveContentWithAI'
            );
            sendResponse({ success: true });
        } catch (error) {
            sendResponse({ success: false, error: error.message });
        }
    }

    scheduleOfflineSync(config) {
        // Schedule a retry attempt
        chrome.alarms.create('retryOfflineSync', { 
            delayInMinutes: Math.max(1, (config.delay || 60000) / 60000)
        });
    }

    async getConnectionStatus(sendResponse) {
        try {
            const settings = await chrome.storage.sync.get(['apiUrl']);
            const response = await fetch(`${settings.apiUrl || 'http://localhost:8082'}/health`);
            sendResponse({ 
                connected: response.ok,
                queueSize: this.offlineQueue.length 
            });
        } catch (error) {
            sendResponse({ 
                connected: false, 
                queueSize: this.offlineQueue.length 
            });
        }
    }

    setupInstallHandler() {
        chrome.runtime.onInstalled.addListener((details) => {
            if (details.reason === 'install') {
                chrome.runtime.openOptionsPage();
            }
        });
    }

    showNotification(message, type = 'success') {
        const iconMap = {
            success: 'icons/brain-48.png',
            error: 'icons/brain-48.png',
            warning: 'icons/brain-48.png',
            info: 'icons/brain-48.png'
        };

        chrome.notifications.create({
            type: 'basic',
            iconUrl: iconMap[type] || iconMap.success,
            title: 'Second Brain',
            message: message
        });
    }
}

// Initialize background service
new SecondBrainBackground();