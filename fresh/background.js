// background.js - Service worker for context menus and background tasks

class SecondBrainBackground {
    constructor() {
        this.init();
    }

    init() {
        this.setupContextMenus();
        this.setupMessageHandlers();
        this.setupInstallHandler();
    }

    setupContextMenus() {
        chrome.runtime.onInstalled.addListener(() => {
            // Text selection context menu
            chrome.contextMenus.create({
                id: 'saveSelection',
                title: 'Save to Second Brain',
                contexts: ['selection']
            });

            // Page context menu
            chrome.contextMenus.create({
                id: 'savePage',
                title: 'Save page to Second Brain',
                contexts: ['page']
            });

            // Link context menu
            chrome.contextMenus.create({
                id: 'saveLink',
                title: 'Save link to Second Brain',
                contexts: ['link']
            });

            // Image context menu
            chrome.contextMenus.create({
                id: 'saveImage',
                title: 'Save image to Second Brain',
                contexts: ['image']
            });
        });

        chrome.contextMenus.onClicked.addListener((info, tab) => {
            this.handleContextMenuClick(info, tab);
        });
    }

    async handleContextMenuClick(info, tab) {
        const settings = await chrome.storage.sync.get(['apiUrl', 'authToken']);
        const apiUrl = settings.apiUrl || 'http://localhost:8084';
        const authToken = settings.authToken || '';

        switch (info.menuItemId) {
            case 'saveSelection':
                await this.saveSelection(info, tab, apiUrl, authToken);
                break;
            case 'savePage':
                await this.savePage(tab, apiUrl, authToken);
                break;
            case 'saveLink':
                await this.saveLink(info, tab, apiUrl, authToken);
                break;
            case 'saveImage':
                await this.saveImage(info, tab, apiUrl, authToken);
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
                timestamp: new Date().toISOString()
            }
        };

        await this.sendToSecondBrain(payload, apiUrl, authToken);
        this.showNotification('Selection saved to Second Brain!');
    }

    async savePage(tab, apiUrl, authToken) {
        try {
            // Extract page content
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                function: () => {
                    // Smart content extraction
                    const extractMainContent = () => {
                        // Try to find main content areas
                        const candidates = [
                            document.querySelector('main'),
                            document.querySelector('article'),
                            document.querySelector('.content'),
                            document.querySelector('.post'),
                            document.querySelector('.entry'),
                            document.querySelector('#content'),
                            document.body
                        ].filter(Boolean);

                        let bestCandidate = candidates[0];
                        let maxTextLength = 0;

                        candidates.forEach(candidate => {
                            const textLength = candidate.innerText.length;
                            if (textLength > maxTextLength) {
                                maxTextLength = textLength;
                                bestCandidate = candidate;
                            }
                        });

                        return bestCandidate;
                    };

                    const mainContent = extractMainContent();
                    
                    // Clean up content
                    const clone = mainContent.cloneNode(true);
                    const unwanted = clone.querySelectorAll('script, style, nav, header, footer, .ad, .advertisement, .sidebar, .menu');
                    unwanted.forEach(el => el.remove());

                    return {
                        text: clone.innerText.trim(),
                        html: clone.innerHTML,
                        url: window.location.href,
                        title: document.title,
                        meta: {
                            description: document.querySelector('meta[name="description"]')?.content || '',
                            author: document.querySelector('meta[name="author"]')?.content || '',
                            publishDate: document.querySelector('meta[property="article:published_time"]')?.content || '',
                            keywords: document.querySelector('meta[name="keywords"]')?.content || ''
                        }
                    };
                }
            });

            const payload = {
                note: result.result.text,
                tags: this.generatePageTags(result.result),
                type: 'browser',
                metadata: {
                    url: result.result.url,
                    title: result.result.title,
                    captureType: 'page',
                    html: result.result.html,
                    meta: result.result.meta,
                    timestamp: new Date().toISOString()
                }
            };

            await this.sendToSecondBrain(payload, apiUrl, authToken);
            this.showNotification('Page saved to Second Brain!');
        } catch (error) {
            this.showNotification('Failed to save page', 'error');
        }
    }

    async saveLink(info, tab, apiUrl, authToken) {
        const payload = {
            note: `Link: ${info.linkUrl}\n\nContext: ${info.selectionText || 'No context'}`,
            tags: 'web,link',
            type: 'browser',
            metadata: {
                url: info.linkUrl,
                sourceUrl: tab.url,
                title: info.linkUrl,
                captureType: 'link',
                timestamp: new Date().toISOString()
            }
        };

        await this.sendToSecondBrain(payload, apiUrl, authToken);
        this.showNotification('Link saved to Second Brain!');
    }

    async saveImage(info, tab, apiUrl, authToken) {
        const payload = {
            note: `Image: ${info.srcUrl}\n\nFrom: ${tab.title}`,
            tags: 'web,image',
            type: 'browser',
            metadata: {
                url: tab.url,
                title: tab.title,
                imageUrl: info.srcUrl,
                captureType: 'image',
                timestamp: new Date().toISOString()
            }
        };

        await this.sendToSecondBrain(payload, apiUrl, authToken);
        this.showNotification('Image saved to Second Brain!');
    }

    generatePageTags(pageData) {
        const tags = ['web', 'page'];
        
        // Add domain
        try {
            const domain = new URL(pageData.url).hostname.replace('www.', '');
            tags.push(domain);
        } catch (e) {}

        // Add keywords if available
        if (pageData.meta.keywords) {
            const keywords = pageData.meta.keywords.split(',')
                .map(k => k.trim().toLowerCase())
                .filter(k => k.length > 2 && k.length < 20)
                .slice(0, 3);
            tags.push(...keywords);
        }

        // Smart content-based tags
        const content = pageData.text.toLowerCase();
        const smartTags = [];
        
        if (content.includes('tutorial') || content.includes('how to')) smartTags.push('tutorial');
        if (content.includes('recipe') || content.includes('ingredients')) smartTags.push('recipe');
        if (content.includes('research') || content.includes('study')) smartTags.push('research');
        if (content.includes('news') || content.includes('breaking')) smartTags.push('news');
        if (content.includes('blog') || content.includes('opinion')) smartTags.push('blog');
        
        tags.push(...smartTags);

        return tags.join(',');
    }

    async sendToSecondBrain(payload, apiUrl, authToken) {
        try {
            const response = await fetch(`${apiUrl}/webhook/browser`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${authToken}`
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('Failed to send to Second Brain:', error);
            throw error;
        }
    }

    showNotification(message, type = 'success') {
        chrome.notifications.create({
            type: 'basic',
            iconUrl: 'icons/brain-48.png',
            title: 'Second Brain',
            message: message
        });
    }

    setupMessageHandlers() {
        chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
            if (request.action === 'captureTab') {
                this.captureCurrentTab(sender.tab).then(sendResponse);
                return true; // Async response
            }
        });
    }

    setupInstallHandler() {
        chrome.runtime.onInstalled.addListener((details) => {
            if (details.reason === 'install') {
                // Open options page on first install
                chrome.runtime.openOptionsPage();
            }
        });
    }

    async captureCurrentTab(tab) {
        const settings = await chrome.storage.sync.get(['apiUrl', 'authToken']);
        return this.savePage(tab, settings.apiUrl, settings.authToken);
    }
}

// Initialize background service
new SecondBrainBackground();