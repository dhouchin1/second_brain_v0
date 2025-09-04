// options.js - Settings page functionality
class SecondBrainOptions {
    constructor() {
        this.init();
    }

    async init() {
        await this.loadSettings();
        this.setupEventListeners();
        await this.testConnection();
    }

    async loadSettings() {
        const settings = await chrome.storage.sync.get([
            'apiUrl', 
            'authToken', 
            'defaultTags', 
            'autoCapture', 
            'showNotifications'
        ]);

        document.getElementById('apiUrl').value = settings.apiUrl || 'http://localhost:8084';
        document.getElementById('authToken').value = settings.authToken || '';
        document.getElementById('defaultTags').value = settings.defaultTags || '';
        document.getElementById('autoCapture').checked = settings.autoCapture !== false;
        document.getElementById('showNotifications').checked = settings.showNotifications !== false;
    }

    setupEventListeners() {
        const form = document.getElementById('settingsForm');
        form.addEventListener('submit', (e) => this.saveSettings(e));

        document.getElementById('testConnection').addEventListener('click', () => this.testConnection());
        
        // Auto-test connection when URL or token changes
        document.getElementById('apiUrl').addEventListener('blur', () => this.testConnection());
        document.getElementById('authToken').addEventListener('blur', () => this.testConnection());
        
        // Save settings on change for checkboxes and other inputs
        ['defaultTags', 'autoCapture', 'showNotifications'].forEach(id => {
            const element = document.getElementById(id);
            element.addEventListener('change', () => this.saveSettingsQuick());
        });
    }

    async saveSettings(e) {
        if (e) e.preventDefault();
        
        const settings = {
            apiUrl: document.getElementById('apiUrl').value.trim() || 'http://localhost:8084',
            authToken: document.getElementById('authToken').value.trim(),
            defaultTags: document.getElementById('defaultTags').value.trim(),
            autoCapture: document.getElementById('autoCapture').checked,
            showNotifications: document.getElementById('showNotifications').checked
        };

        try {
            await chrome.storage.sync.set(settings);
            this.showMessage('Settings saved successfully!', 'success');
            await this.testConnection();
        } catch (error) {
            this.showMessage('Failed to save settings: ' + error.message, 'error');
        }
    }

    async saveSettingsQuick() {
        // Quick save without showing message (for auto-save scenarios)
        const settings = {
            defaultTags: document.getElementById('defaultTags').value.trim(),
            autoCapture: document.getElementById('autoCapture').checked,
            showNotifications: document.getElementById('showNotifications').checked
        };

        await chrome.storage.sync.set(settings);
    }

    async testConnection() {
        const statusEl = document.getElementById('connectionStatus');
        const apiUrl = document.getElementById('apiUrl').value.trim() || 'http://localhost:8084';
        const authToken = document.getElementById('authToken').value.trim();

        statusEl.innerHTML = '<span class="status-indicator status-checking"></span>Testing connection...';

        try {
            // Test basic health endpoint
            const healthResponse = await fetch(`${apiUrl}/health`, {
                method: 'GET',
                timeout: 5000
            });

            if (!healthResponse.ok) {
                throw new Error(`Server responded with ${healthResponse.status}`);
            }

            // Test auth if token provided
            let authStatus = 'No authentication';
            if (authToken) {
                try {
                    const authResponse = await fetch(`${apiUrl}/api/analytics`, {
                        method: 'GET',
                        headers: {
                            'Authorization': `Bearer ${authToken}`,
                            'Content-Type': 'application/json'
                        },
                        timeout: 5000
                    });

                    if (authResponse.ok) {
                        authStatus = 'Authenticated successfully';
                    } else if (authResponse.status === 401) {
                        authStatus = 'Invalid authentication token';
                    } else {
                        authStatus = `Auth error: ${authResponse.status}`;
                    }
                } catch (authError) {
                    authStatus = 'Could not verify authentication';
                }
            }

            const serverData = await healthResponse.json();
            statusEl.innerHTML = `
                <span class="status-indicator status-connected"></span>
                <div>
                    <div><strong>Connected successfully!</strong></div>
                    <div style="font-size: 13px; color: #6b7280; margin-top: 4px;">
                        Server: ${apiUrl}<br>
                        Auth: ${authStatus}<br>
                        Tables: ${serverData.tables ? serverData.tables.length : 'Unknown'}
                    </div>
                </div>
            `;
        } catch (error) {
            console.error('Connection test failed:', error);
            statusEl.innerHTML = `
                <span class="status-indicator status-disconnected"></span>
                <div>
                    <div><strong>Connection failed</strong></div>
                    <div style="font-size: 13px; color: #6b7280; margin-top: 4px;">
                        ${error.message || 'Unable to connect to Second Brain server'}
                    </div>
                </div>
            `;
        }
    }

    showMessage(message, type = 'success') {
        const messagesContainer = document.getElementById('messages');
        
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type}`;
        alertDiv.textContent = message;
        
        messagesContainer.appendChild(alertDiv);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.parentNode.removeChild(alertDiv);
            }
        }, 5000);
        
        // Scroll to top to show message
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new SecondBrainOptions();
});