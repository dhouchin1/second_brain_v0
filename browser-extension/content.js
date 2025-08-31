// content.js - Content script for Second Brain extension
class SecondBrainContent {
    constructor() {
        this.init();
    }

    init() {
        this.setupSelectionHandler();
        this.setupKeyboardShortcuts();
        this.setupQuickCaptureUI();
    }

    setupSelectionHandler() {
        let selectionTimeout;
        
        document.addEventListener('mouseup', () => {
            clearTimeout(selectionTimeout);
            selectionTimeout = setTimeout(() => {
                this.handleSelection();
            }, 300);
        });

        document.addEventListener('keyup', (e) => {
            if (e.key === 'Escape') {
                this.hideQuickCapture();
            }
        });
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl+Shift+S - Quick save selection
            if (e.ctrlKey && e.shiftKey && e.key === 'S') {
                e.preventDefault();
                this.quickSaveSelection();
            }
            
            // Ctrl+Shift+P - Quick save page
            if (e.ctrlKey && e.shiftKey && e.key === 'P') {
                e.preventDefault();
                this.quickSavePage();
            }
        });
    }

    handleSelection() {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();
        
        if (selectedText && selectedText.length > 10) {
            this.showQuickCapture(selectedText);
        } else {
            this.hideQuickCapture();
        }
    }

    showQuickCapture(selectedText) {
        // Remove existing quick capture if any
        this.hideQuickCapture();
        
        const quickCapture = document.createElement('div');
        quickCapture.id = 'second-brain-quick-capture';
        quickCapture.innerHTML = `
            <div class="sb-tooltip">
                <div class="sb-tooltip-content">
                    <div class="sb-tooltip-title">📝 Save to Second Brain</div>
                    <div class="sb-tooltip-text">"${selectedText.substring(0, 50)}${selectedText.length > 50 ? '...' : ''}"</div>
                    <div class="sb-tooltip-actions">
                        <button class="sb-btn sb-btn-primary" id="sb-save-selection">Save</button>
                        <button class="sb-btn sb-btn-secondary" id="sb-save-with-context">+ Context</button>
                        <button class="sb-btn sb-btn-close" id="sb-close">✕</button>
                    </div>
                </div>
                <div class="sb-tooltip-arrow"></div>
            </div>
        `;

        document.body.appendChild(quickCapture);
        
        // Position the tooltip near the selection
        const selection = window.getSelection();
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            const rect = range.getBoundingClientRect();
            
            const tooltip = quickCapture.querySelector('.sb-tooltip');
            tooltip.style.left = `${rect.left + window.scrollX}px`;
            tooltip.style.top = `${rect.bottom + window.scrollY + 10}px`;
            
            // Adjust if tooltip goes off-screen
            const tooltipRect = tooltip.getBoundingClientRect();
            if (tooltipRect.right > window.innerWidth) {
                tooltip.style.left = `${window.innerWidth - tooltipRect.width - 20}px`;
            }
            if (tooltipRect.bottom > window.innerHeight + window.scrollY) {
                tooltip.style.top = `${rect.top + window.scrollY - tooltipRect.height - 10}px`;
            }
        }

        // Add event listeners
        document.getElementById('sb-save-selection').addEventListener('click', () => {
            this.saveSelection(selectedText, false);
        });
        
        document.getElementById('sb-save-with-context').addEventListener('click', () => {
            this.saveSelection(selectedText, true);
        });
        
        document.getElementById('sb-close').addEventListener('click', () => {
            this.hideQuickCapture();
        });

        // Auto-hide after 10 seconds
        setTimeout(() => {
            this.hideQuickCapture();
        }, 10000);
    }

    hideQuickCapture() {
        const quickCapture = document.getElementById('second-brain-quick-capture');
        if (quickCapture) {
            quickCapture.remove();
        }
    }

    async saveSelection(selectedText, includeContext = false) {
        this.hideQuickCapture();
        
        let content = selectedText;
        
        if (includeContext) {
            // Get surrounding context
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                const paragraph = range.commonAncestorContainer.nodeType === Node.TEXT_NODE 
                    ? range.commonAncestorContainer.parentElement 
                    : range.commonAncestorContainer;
                
                const context = this.getElementContext(paragraph);
                content = `${selectedText}\n\n---\nContext: ${context}`;
            }
        }

        const payload = {
            note: content,
            tags: 'web,selection',
            type: 'browser',
            metadata: {
                url: window.location.href,
                title: document.title,
                captureType: includeContext ? 'selection-with-context' : 'selection',
                timestamp: new Date().toISOString(),
                selectedText: selectedText
            }
        };

        try {
            await this.sendToBackground('saveContent', payload);
            this.showNotification('Selection saved to Second Brain! 🧠', 'success');
        } catch (error) {
            this.showNotification('Failed to save selection', 'error');
        }
    }

    async quickSaveSelection() {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();
        
        if (selectedText) {
            await this.saveSelection(selectedText, false);
        } else {
            this.showNotification('No text selected', 'warning');
        }
    }

    async quickSavePage() {
        const payload = {
            note: this.extractMainContent(),
            tags: 'web,page,quick-save',
            type: 'browser',
            metadata: {
                url: window.location.href,
                title: document.title,
                captureType: 'page',
                timestamp: new Date().toISOString()
            }
        };

        try {
            await this.sendToBackground('saveContent', payload);
            this.showNotification('Page saved to Second Brain! 🧠', 'success');
        } catch (error) {
            this.showNotification('Failed to save page', 'error');
        }
    }

    extractMainContent() {
        // Smart content extraction
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
            if (textLength > maxTextLength && textLength > 100) {
                maxTextLength = textLength;
                bestCandidate = candidate;
            }
        });

        if (!bestCandidate) return document.title;

        // Clean up content
        const clone = bestCandidate.cloneNode(true);
        const unwanted = clone.querySelectorAll('script, style, nav, header, footer, .ad, .advertisement, .sidebar, .menu, .comments');
        unwanted.forEach(el => el.remove());

        return clone.innerText.trim().substring(0, 5000); // Limit to 5000 chars
    }

    getElementContext(element) {
        // Get the parent paragraph or container text
        let context = element.innerText || element.textContent || '';
        
        // If context is too short, try parent elements
        let currentElement = element;
        while (context.length < 200 && currentElement.parentElement && currentElement !== document.body) {
            currentElement = currentElement.parentElement;
            const parentText = currentElement.innerText || currentElement.textContent || '';
            if (parentText.length > context.length && parentText.length < 1000) {
                context = parentText;
            }
        }
        
        return context.substring(0, 500);
    }

    async sendToBackground(action, payload) {
        return new Promise((resolve, reject) => {
            chrome.runtime.sendMessage({ action, payload }, (response) => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
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
                <div class="sb-notification-message">${message}</div>
                <button class="sb-notification-close" onclick="this.parentElement.parentElement.remove()">✕</button>
            </div>
        `;

        document.body.appendChild(notification);

        // Auto-remove after 4 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 4000);
    }

    setupQuickCaptureUI() {
        // This method is called during init but the UI is created dynamically
        // We just ensure we don't have any lingering UI elements
        this.hideQuickCapture();
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