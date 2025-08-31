/**
 * Real-time Status Updates for Second Brain
 * Handles Server-Sent Events (SSE) for live processing status
 */

class RealtimeStatusManager {
    constructor() {
        this.activeStreams = new Map(); // note_id -> EventSource
        this.progressElements = new Map(); // note_id -> DOM elements
        this.failCounts = new Map(); // note_id -> consecutive SSE failures
        this.init();
    }

    init() {
        this.setupProgressElements();
        this.setupQueueMonitor();
    }

    /**
     * Start monitoring a specific note's processing status
     */
    monitorNote(noteId, options = {}) {
        const {
            progressContainer = null,
            onProgress = null,
            onComplete = null,
            onError = null
        } = options;

        // Close existing stream if any
        this.stopMonitoring(noteId);

        // Create progress UI if container provided
        if (progressContainer) {
            this.createProgressBar(noteId, progressContainer);
        }

        // Build SSE URL with signed token if available to avoid header-based auth
        const baseUrl = `/api/status/stream/${noteId}`;
        const url = (window.SSE_TOKEN && typeof window.SSE_TOKEN === 'string')
            ? `${baseUrl}?token=${encodeURIComponent(window.SSE_TOKEN)}`
            : baseUrl;

        // Start SSE stream (credentials used for same-origin cookies; token handles cross-origin)
        const eventSource = new EventSource(url, {
            withCredentials: true
        });
        this.activeStreams.set(noteId, eventSource);

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleStatusUpdate(noteId, data);

                // Call custom handlers
                if (onProgress && !data.completed) {
                    onProgress(data);
                }
                if (onComplete && data.completed) {
                    onComplete(data);
                }
            } catch (error) {
                console.error('Error parsing SSE data:', error);
                if (onError) onError(error);
            }
        };

        eventSource.onerror = async (error) => {
            console.error('SSE error for note', noteId, error);
            
            // Check if it's an authentication error (401)
            if (eventSource.readyState === EventSource.CLOSED) {
                const fails = (this.failCounts.get(noteId) || 0) + 1;
                this.failCounts.set(noteId, fails);
                console.log('SSE connection closed for note', noteId, `(fail #${fails})`);
                // Try to refresh SSE token and reconnect once
                try {
                    const resp = await fetch('/api/sse-token', { credentials: 'same-origin' });
                    if (resp.ok) {
                        const data = await resp.json();
                        if (data && data.token) {
                            window.SSE_TOKEN = data.token;
                            console.log('Refreshed SSE token; reconnecting stream for note', noteId);
                            // Stop if too many failures to avoid spam
                            if (fails >= 5) {
                                console.warn('Stopping SSE retries for note', noteId, 'after multiple failures');
                                this.stopMonitoring(noteId);
                                if (onError) onError(error);
                                return;
                            }
                            // Reconnect
                            setTimeout(() => this.monitorNote(noteId, options), 500);
                            return;
                        }
                    }
                } catch (e) { /* ignore */ }
                this.stopMonitoring(noteId);
                if (onError) onError(error);
            }
        };

        return eventSource;
    }

    /**
     * Stop monitoring a note
     */
    stopMonitoring(noteId) {
        const eventSource = this.activeStreams.get(noteId);
        if (eventSource) {
            eventSource.close();
            this.activeStreams.delete(noteId);
        }

        // Clean up progress elements
        this.removeProgressBar(noteId);
    }

    /**
     * Handle status updates from SSE
     */
    handleStatusUpdate(noteId, data) {
        console.log('Status update for note', noteId, data);

        // Update progress bar
        this.updateProgressBar(noteId, data);

        // Update dashboard if note exists
        this.updateDashboardNote(noteId, data);

        // Show notifications for key events
        this.showStatusNotification(noteId, data);

        // Auto-cleanup completed notes
        if (data.completed) {
            setTimeout(() => {
                this.stopMonitoring(noteId);
                this.removeProgressBar(noteId);
            }, 5000); // Keep progress visible for 5 seconds
        }
    }

    /**
     * Create progress bar UI
     */
    createProgressBar(noteId, container) {
        const progressId = `progress-${noteId}`;
        const existingProgress = document.getElementById(progressId);
        
        if (existingProgress) {
            existingProgress.remove();
        }

        const progressHTML = `
            <div id="${progressId}" class="progress-container mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-sm font-medium text-blue-900">Processing Note...</span>
                    <button onclick="realtimeStatus.stopMonitoring(${noteId})" class="text-blue-600 hover:text-blue-800">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                        </svg>
                    </button>
                </div>
                
                <div class="progress-bar-container bg-gray-200 rounded-full h-2 mb-2">
                    <div class="progress-bar bg-blue-600 h-2 rounded-full transition-all duration-500" style="width: 0%"></div>
                </div>
                
                <div class="flex items-center justify-between">
                    <span class="progress-stage text-xs text-gray-600">Starting...</span>
                    <span class="progress-percent text-xs text-gray-600">0%</span>
                </div>
                
                <div class="progress-message text-xs text-gray-500 mt-1"></div>
            </div>
        `;

        if (typeof container === 'string') {
            container = document.getElementById(container) || document.querySelector(container);
        }
        
        if (container) {
            container.insertAdjacentHTML('afterbegin', progressHTML);
            this.progressElements.set(noteId, document.getElementById(progressId));
        }
    }

    /**
     * Update progress bar
     */
    updateProgressBar(noteId, data) {
        const progressContainer = this.progressElements.get(noteId);
        if (!progressContainer) return;

        const progressBar = progressContainer.querySelector('.progress-bar');
        const stageElement = progressContainer.querySelector('.progress-stage');
        const percentElement = progressContainer.querySelector('.progress-percent');
        const messageElement = progressContainer.querySelector('.progress-message');

        if (progressBar) {
            const progress = Math.max(0, Math.min(100, data.progress || 0));
            progressBar.style.width = `${progress}%`;
            
            // Update colors based on status
            if (data.stage === 'error') {
                progressBar.className = 'progress-bar bg-red-600 h-2 rounded-full transition-all duration-500';
                progressContainer.className = progressContainer.className.replace('bg-blue-50 border-blue-200', 'bg-red-50 border-red-200');
            } else if (data.completed && data.success) {
                progressBar.className = 'progress-bar bg-green-600 h-2 rounded-full transition-all duration-500';
                progressContainer.className = progressContainer.className.replace('bg-blue-50 border-blue-200', 'bg-green-50 border-green-200');
            }
        }

        if (stageElement) {
            stageElement.textContent = this.formatStage(data.stage);
        }

        if (percentElement) {
            percentElement.textContent = `${data.progress || 0}%`;
        }

        if (messageElement && data.message) {
            messageElement.textContent = data.message;
        }
    }

    /**
     * Remove progress bar
     */
    removeProgressBar(noteId) {
        const progressContainer = this.progressElements.get(noteId);
        if (progressContainer) {
            progressContainer.remove();
            this.progressElements.delete(noteId);
        }
    }

    /**
     * Format stage names for display
     */
    formatStage(stage) {
        const stageMap = {
            'starting': 'Starting...',
            'transcribing': 'Transcribing Audio',
            'generating_title': 'Generating Title',
            'ai_processing': 'AI Analysis',
            'finalizing': 'Finalizing',
            'complete': 'Complete',
            'error': 'Error'
        };
        return stageMap[stage] || stage;
    }

    /**
     * Update note in dashboard
     */
    updateDashboardNote(noteId, data) {
        const noteElement = document.querySelector(`[data-note-id="${noteId}"]`);
        if (!noteElement) return;

        // Update status indicator
        const statusIndicator = noteElement.querySelector('.note-status');
        if (statusIndicator) {
            if (data.completed) {
                if (data.success) {
                    statusIndicator.innerHTML = '<span class="text-green-600">✓ Complete</span>';
                } else {
                    statusIndicator.innerHTML = '<span class="text-red-600">✗ Error</span>';
                }
            } else {
                statusIndicator.innerHTML = `<span class="text-blue-600">⏳ ${this.formatStage(data.stage)} (${data.progress}%)</span>`;
            }
        }

        // Update title if processing generated one
        if (data.completed && data.success) {
            // Refresh the page or update content dynamically
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        }
    }

    /**
     * Show status notifications
     */
    showStatusNotification(noteId, data) {
        // Only show notifications for key events
        if (data.stage === 'complete' && data.success) {
            this.showToast('Note processing complete! 🎉', 'success');
        } else if (data.stage === 'error') {
            this.showToast(`Processing failed: ${data.message}`, 'error');
        }
    }

    /**
     * Show toast notification
     */
    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 max-w-sm transition-all duration-300 transform translate-x-full ${
            type === 'success' ? 'bg-green-500 text-white' :
            type === 'error' ? 'bg-red-500 text-white' :
            type === 'warning' ? 'bg-yellow-500 text-black' :
            'bg-blue-500 text-white'
        }`;
        toast.textContent = message;

        document.body.appendChild(toast);

        // Animate in
        setTimeout(() => {
            toast.style.transform = 'translateX(0)';
        }, 100);

        // Auto-remove after 4 seconds
        setTimeout(() => {
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 4000);
    }

    /**
     * Setup automatic progress detection for existing elements
     */
    setupProgressElements() {
        // Look for notes with pending or processing status on page load
        document.querySelectorAll('[data-note-status="pending"], [data-note-status*="processing"]').forEach(element => {
            const noteId = element.dataset.noteId;
            const status = element.dataset.noteStatus;
            
            if (noteId && status !== 'complete') {
                console.log('Starting monitoring for note', noteId, 'with status', status);
                // Start monitoring with minimal UI
                this.monitorNote(parseInt(noteId), {
                    onComplete: () => {
                        // Refresh the page when processing completes
                        setTimeout(() => window.location.reload(), 1000);
                    },
                    onError: (error) => {
                        console.log('Stopping monitoring for note', noteId, 'due to error');
                        this.stopMonitoring(parseInt(noteId));
                    }
                });
            }
        });
    }

    /**
     * Monitor processing queue
     */
    async setupQueueMonitor() {
        // Check for processing queue visibility elements
        const queueContainer = document.getElementById('processing-queue');
        if (!queueContainer) return;

        // Refresh queue every 30 seconds (reduced from 5s for performance)
        const timer = setInterval(async () => {
            try {
                // Prefer legacy cookie-based endpoint which returns 200 in more cases
                let res = await fetch('/api/queue/status', { credentials: 'same-origin' });
                if (res.status === 401) {
                    // Fallback to token-based status endpoint
                    const token = (window.SSE_TOKEN && typeof window.SSE_TOKEN === 'string') ? `?token=${encodeURIComponent(window.SSE_TOKEN)}` : '';
                    res = await fetch(`/api/status/queue${token}`, { credentials: 'same-origin' });
                }
                if (res.status === 401) {
                    console.warn('Queue polling unauthorized — stopping interval');
                    clearInterval(timer);
                    return;
                }
                const data = await res.json();
                this.updateQueueDisplay(data);
                
                // Stop polling if queue is empty for performance
                if (data && data.total_pending === 0) {
                    console.log('Queue empty - reducing polling frequency');
                    clearInterval(timer);
                    // Start a slower check every 2 minutes for new items
                    setTimeout(() => this.setupQueueMonitor(), 120000);
                }
            } catch (error) {
                console.error('Error fetching queue status:', error);
            }
        }, 30000); // Reduced from 5s to 30s to reduce server load
    }

    /**
     * Update processing queue display
     */
    updateQueueDisplay(queueData) {
        const queueContainer = document.getElementById('processing-queue');
        if (!queueContainer) return;

        if (queueData.total_pending === 0) {
            queueContainer.innerHTML = '<div class="text-gray-500 text-sm">No items processing</div>';
            return;
        }

        const queueHTML = queueData.queue.map(item => `
            <div class="flex items-center justify-between p-2 bg-gray-50 rounded text-sm">
                <div class="flex-1 min-w-0">
                    <div class="truncate font-medium">${item.title || 'Untitled'}</div>
                    <div class="text-gray-500 text-xs">${this.formatStage(item.stage)} (${item.progress}%)</div>
                </div>
                <div class="ml-2">
                    <div class="w-12 bg-gray-200 rounded-full h-1">
                        <div class="bg-blue-600 h-1 rounded-full" style="width: ${item.progress}%"></div>
                    </div>
                </div>
            </div>
        `).join('');

        queueContainer.innerHTML = `
            <div class="mb-2 text-sm font-medium">Processing Queue (${queueData.total_pending})</div>
            <div class="space-y-2">${queueHTML}</div>
        `;
    }

    /**
     * Cleanup all streams (call on page unload)
     */
    cleanup() {
        this.activeStreams.forEach((eventSource, noteId) => {
            eventSource.close();
        });
        this.activeStreams.clear();
        this.progressElements.clear();
    }
}

// Global instance
const realtimeStatus = new RealtimeStatusManager();

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    realtimeStatus.cleanup();
});

// Export for use in other scripts
window.realtimeStatus = realtimeStatus;
