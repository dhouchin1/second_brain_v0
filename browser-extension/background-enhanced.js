// Enhanced background service worker for Second Brain extension
// Handles offline functionality, command processing, and coordination between components

class SecondBrainBackground {
    constructor() {
        this.apiUrl = '';
        this.authToken = '';
        this.offlineQueue = [];
        this.isOnline = navigator.onLine;
        this.settings = {};
        this.contextMenuId = null;
        
        this.init();
    }

    async init() {
        await this.loadSettings();
        this.setupEventListeners();
        this.setupContextMenus();
        this.setupAlarms();
        this.startSyncProcess();
    }

    async loadSettings() {
        const settings = await chrome.storage.sync.get([
            'apiUrl',
            'authToken',
            'autoSummarize',
            'autoTags',
            'offlineMode',
            'syncInterval'
        ]);
        
        this.apiUrl = settings.apiUrl || 'http://localhost:8082';
        this.authToken = settings.authToken || '';
        this.settings = {
            offlineMode: settings.offlineMode !== false,
            syncInterval: settings.syncInterval || 5, // minutes
            ...settings
        };
    }

    setupEventListeners() {
        // Handle installation and updates
        chrome.runtime.onInstalled.addListener((details) => {
            this.handleInstallation(details);
        });

        // Handle messages from popup and content scripts
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            this.handleMessage(message, sender, sendResponse);
            return true; // Keep channel open for async responses
        });

        // Handle keyboard shortcuts
        chrome.commands.onCommand.addListener((command) => {
            this.handleCommand(command);
        });

        // Handle context menu clicks
        chrome.contextMenus.onClicked.addListener((info, tab) => {
            this.handleContextMenu(info, tab);
        });

        // Handle network status changes
        chrome.webNavigation.onCompleted.addListener((details) => {
            if (details.frameId === 0) { // Main frame only
                this.checkOnlineStatus();
            }
        });

        // Handle tab updates for dynamic analysis
        chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
            if (changeInfo.status === 'complete' && tab.url) {
                this.analyzeTabContent(tab);
            }
        });
    }

    async handleMessage(message, sender, sendResponse) {
        try {
            switch (message.action) {
                case 'captureContent':
                    const result = await this.captureContent(message.data, sender.tab);
                    sendResponse(result);
                    break;

                case 'checkConnection':
                    const status = await this.checkConnection();
                    sendResponse(status);
                    break;

                case 'getSettings':
                    sendResponse(this.settings);
                    break;

                case 'updateSettings':
                    await this.updateSettings(message.settings);
                    sendResponse({ success: true });
                    break;

                case 'getOfflineQueue':
                    sendResponse({ queue: this.offlineQueue });
                    break;

                case 'syncOfflineQueue':
                    const syncResult = await this.syncOfflineQueue();
                    sendResponse(syncResult);
                    break;

                case 'analyzeTab':
                    if (sender.tab) {
                        const analysis = await this.getTabAnalysis(sender.tab.id);
                        sendResponse(analysis);
                    }
                    break;

                case 'updateMultiSelectCount':
                    // Forward to popup if open
                    this.notifyPopup('multiSelectUpdate', { count: message.count });
                    break;

                default:
                    sendResponse({ error: 'Unknown action' });
            }
        } catch (error) {
            console.error('Background script error:', error);
            sendResponse({ error: error.message });
        }
    }

    async handleCommand(command) {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        
        switch (command) {
            case 'quick-capture':
                await this.executeContentScript(tab.id, 'captureSelection');
                break;
                
            case 'capture-page':
                await this.executeContentScript(tab.id, 'capturePage');
                break;
        }
    }

    async executeContentScript(tabId, action) {
        try {
            // Inject content script if not already present
            await chrome.scripting.executeScript({
                target: { tabId },
                files: ['content-enhanced.js']
            });

            // Send message to content script
            const result = await chrome.tabs.sendMessage(tabId, { action });
            
            if (result && !result.error) {
                await this.captureContent(result);
                this.showNotification('Content captured successfully!', 'success');
            } else {
                this.showNotification(result?.error || 'Capture failed', 'error');
            }
        } catch (error) {
            console.error('Content script execution failed:', error);
            this.showNotification('Capture failed: ' + error.message, 'error');
        }
    }

    setupContextMenus() {
        chrome.contextMenus.removeAll(() => {
            // Text selection context menu
            this.contextMenuId = chrome.contextMenus.create({
                id: 'second-brain-capture-selection',
                title: 'Save to Second Brain',
                contexts: ['selection'],
                documentUrlPatterns: ['http://*/*', 'https://*/*']
            });

            // Page context menu
            chrome.contextMenus.create({
                id: 'second-brain-capture-page',
                title: 'Save page to Second Brain',
                contexts: ['page'],
                documentUrlPatterns: ['http://*/*', 'https://*/*']
            });

            // Link context menu
            chrome.contextMenus.create({
                id: 'second-brain-capture-link',
                title: 'Save link to Second Brain',
                contexts: ['link'],
                documentUrlPatterns: ['http://*/*', 'https://*/*']
            });

            // Image context menu
            chrome.contextMenus.create({
                id: 'second-brain-capture-image',
                title: 'Save image to Second Brain',
                contexts: ['image'],
                documentUrlPatterns: ['http://*/*', 'https://*/*']
            });
        });
    }

    async handleContextMenu(info, tab) {
        let captureData;

        switch (info.menuItemId) {
            case 'second-brain-capture-selection':
                captureData = {
                    type: 'selection',
                    title: tab.title,
                    url: tab.url,
                    content: info.selectionText,
                    metadata: {
                        domain: new URL(tab.url).hostname,
                        timestamp: new Date().toISOString()
                    }
                };
                break;

            case 'second-brain-capture-page':
                // Trigger full page capture via content script
                await this.executeContentScript(tab.id, 'capturePage');
                return;

            case 'second-brain-capture-link':
                captureData = {
                    type: 'bookmark',
                    title: info.linkText || info.linkUrl,
                    url: info.linkUrl,
                    content: `Bookmark: ${info.linkText || info.linkUrl}`,
                    metadata: {
                        sourceUrl: tab.url,
                        sourceDomain: new URL(tab.url).hostname,
                        timestamp: new Date().toISOString()
                    }
                };
                break;

            case 'second-brain-capture-image':
                captureData = {
                    type: 'image',
                    title: tab.title + ' - Image',
                    url: tab.url,
                    content: `Image from ${tab.title}`,
                    imageUrl: info.srcUrl,
                    metadata: {
                        domain: new URL(tab.url).hostname,
                        timestamp: new Date().toISOString(),
                        imageAlt: info.altText || ''
                    }
                };
                break;
        }

        if (captureData) {
            const result = await this.captureContent(captureData, tab);
            const message = result.success ? 'Content saved successfully!' : 'Save failed: ' + result.error;
            const type = result.success ? 'success' : 'error';
            this.showNotification(message, type);
        }
    }

    async captureContent(data, tab = null) {
        // Add tab information if available
        if (tab) {
            data.sourceTab = {
                title: tab.title,
                url: tab.url,
                favIconUrl: tab.favIconUrl
            };
        }

        // Add processing options
        data.processingOptions = {
            aiSummarize: this.settings.autoSummarize,
            aiTags: this.settings.autoTags,
            timestamp: new Date().toISOString()
        };

        if (this.isOnline) {
            try {
                const result = await this.sendToAPI('/webhook/browser', data);
                
                // Store successful capture for recent items
                await this.storeRecentCapture(data, result);
                
                return result;
            } catch (error) {
                console.error('API call failed:', error);
                
                // Fall back to offline storage
                if (this.settings.offlineMode) {
                    await this.storeOffline(data);
                    return { 
                        success: true, 
                        message: 'Saved offline - will sync when connection is restored',
                        offline: true 
                    };
                }
                
                return { success: false, error: error.message };
            }
        } else if (this.settings.offlineMode) {
            await this.storeOffline(data);
            return { 
                success: true, 
                message: 'Saved offline - will sync when connection is restored',
                offline: true 
            };
        } else {
            return { success: false, error: 'No internet connection and offline mode is disabled' };
        }
    }

    async sendToAPI(endpoint, data) {
        const url = `${this.apiUrl}${endpoint}`;
        
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.authToken}`
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
    }

    async storeOffline(data) {
        data.id = Date.now() + Math.random();
        data.offlineTimestamp = new Date().toISOString();
        
        this.offlineQueue.push(data);
        
        // Store in chrome.storage for persistence
        await chrome.storage.local.set({ offlineQueue: this.offlineQueue });
        
        console.log('Stored offline:', data.title);
    }

    async loadOfflineQueue() {
        const stored = await chrome.storage.local.get(['offlineQueue']);
        this.offlineQueue = stored.offlineQueue || [];
    }

    async syncOfflineQueue() {
        if (this.offlineQueue.length === 0 || !this.isOnline) {
            return { synced: 0, failed: 0 };
        }

        let synced = 0;
        let failed = 0;
        const remainingQueue = [];

        for (const item of this.offlineQueue) {
            try {
                await this.sendToAPI('/webhook/browser', item);
                synced++;
                console.log('Synced offline item:', item.title);
            } catch (error) {
                console.error('Failed to sync item:', error);
                failed++;
                remainingQueue.push(item); // Keep for retry
            }
        }

        this.offlineQueue = remainingQueue;
        await chrome.storage.local.set({ offlineQueue: this.offlineQueue });

        if (synced > 0) {
            this.showNotification(`Synced ${synced} offline items`, 'success');
        }

        return { synced, failed };
    }

    async checkConnection() {
        try {
            const response = await fetch(`${this.apiUrl}/health`, {
                method: 'GET',
                headers: { 'Authorization': `Bearer ${this.authToken}` }
            });
            
            this.isOnline = response.ok;
            
            if (this.isOnline && this.offlineQueue.length > 0) {
                // Auto-sync when connection is restored
                setTimeout(() => this.syncOfflineQueue(), 1000);
            }
            
            return {
                connected: this.isOnline,
                apiUrl: this.apiUrl,
                queueSize: this.offlineQueue.length
            };
        } catch (error) {
            this.isOnline = false;
            return {
                connected: false,
                apiUrl: this.apiUrl,
                error: error.message,
                queueSize: this.offlineQueue.length
            };
        }
    }

    async checkOnlineStatus() {
        const wasOnline = this.isOnline;
        await this.checkConnection();
        
        // If we just came back online, sync offline queue
        if (!wasOnline && this.isOnline && this.offlineQueue.length > 0) {
            setTimeout(() => this.syncOfflineQueue(), 2000);
        }
    }

    setupAlarms() {
        // Set up periodic sync alarm
        chrome.alarms.create('sync-offline', { 
            delayInMinutes: this.settings.syncInterval,
            periodInMinutes: this.settings.syncInterval 
        });

        chrome.alarms.onAlarm.addListener((alarm) => {
            if (alarm.name === 'sync-offline') {
                this.syncOfflineQueue();
            }
        });
    }

    startSyncProcess() {
        // Load offline queue on startup
        this.loadOfflineQueue();
        
        // Check connection status
        this.checkConnection();
        
        // Set up periodic connection checks
        setInterval(() => this.checkOnlineStatus(), 30000); // Every 30 seconds
    }

    async storeRecentCapture(data, result) {
        const recentItems = await chrome.storage.local.get(['recentCaptures']);
        const recent = recentItems.recentCaptures || [];
        
        recent.unshift({
            id: result.id || Date.now(),
            title: data.title,
            type: data.type,
            url: data.url,
            timestamp: data.metadata?.timestamp || new Date().toISOString(),
            success: true
        });
        
        // Keep only last 50 items
        recent.splice(50);
        
        await chrome.storage.local.set({ recentCaptures: recent });
    }

    async analyzeTabContent(tab) {
        if (!tab.url || tab.url.startsWith('chrome://')) {
            return;
        }

        try {
            // Inject content script and analyze
            await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                files: ['content-enhanced.js']
            });

            const analysis = await chrome.tabs.sendMessage(tab.id, { 
                action: 'analyzeContent' 
            });
            
            // Store analysis for popup use
            await chrome.storage.session.set({
                [`analysis_${tab.id}`]: analysis
            });
            
        } catch (error) {
            // Silent fail - tab might not support content scripts
            console.debug('Tab analysis failed:', error.message);
        }
    }

    async getTabAnalysis(tabId) {
        const stored = await chrome.storage.session.get([`analysis_${tabId}`]);
        return stored[`analysis_${tabId}`] || null;
    }

    showNotification(message, type = 'info') {
        const iconUrl = type === 'success' ? 'icons/icon-success.png' : 
                       type === 'error' ? 'icons/icon-error.png' : 
                       'icons/icon-48.png';

        chrome.notifications.create({
            type: 'basic',
            iconUrl: iconUrl,
            title: 'Second Brain',
            message: message
        });
    }

    async notifyPopup(action, data) {
        try {
            await chrome.runtime.sendMessage({ action, data });
        } catch (error) {
            // Popup might not be open
        }
    }

    async updateSettings(newSettings) {
        this.settings = { ...this.settings, ...newSettings };
        await chrome.storage.sync.set(this.settings);
        
        // Update alarms if sync interval changed
        if (newSettings.syncInterval) {
            chrome.alarms.clear('sync-offline');
            chrome.alarms.create('sync-offline', {
                delayInMinutes: newSettings.syncInterval,
                periodInMinutes: newSettings.syncInterval
            });
        }
    }

    handleInstallation(details) {
        if (details.reason === 'install') {
            // First-time installation
            chrome.tabs.create({ 
                url: chrome.runtime.getURL('options.html') 
            });
        } else if (details.reason === 'update') {
            // Extension updated
            console.log('Second Brain extension updated to version', chrome.runtime.getManifest().version);
        }
    }
}

// Initialize background service worker
new SecondBrainBackground();