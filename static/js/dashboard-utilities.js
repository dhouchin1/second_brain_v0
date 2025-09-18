/**
 * Consolidated Dashboard Utilities
 * Common functions used across multiple dashboard modules
 */

class DashboardUtilities {
    constructor() {
        this.toastContainer = null;
        this.init();
    }

    init() {
        this.createToastContainer();
    }

    /**
     * Unified Toast Notification System
     */
    createToastContainer() {
        if (!this.toastContainer) {
            this.toastContainer = document.createElement('div');
            this.toastContainer.id = 'toast-container';
            this.toastContainer.className = 'fixed top-4 right-4 z-50 space-y-2';
            document.body.appendChild(this.toastContainer);
        }
    }

    showToast(message, type = 'info', duration = 3000) {
        const toast = document.createElement('div');
        const colors = {
            success: 'bg-green-500',
            error: 'bg-red-500', 
            warning: 'bg-yellow-500',
            info: 'bg-blue-500'
        };
        
        toast.className = `
            ${colors[type] || colors.info} text-white px-4 py-2 rounded-lg shadow-lg
            transform transition-all duration-300 translate-x-full opacity-0
            max-w-sm
        `;
        toast.textContent = message;
        
        this.toastContainer.appendChild(toast);
        
        // Animate in
        setTimeout(() => {
            toast.classList.remove('translate-x-full', 'opacity-0');
        }, 100);
        
        // Auto remove
        setTimeout(() => {
            toast.classList.add('translate-x-full', 'opacity-0');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    /**
     * Common Loading States
     */
    showLoading(element, text = 'Loading...') {
        element.innerHTML = `
            <div class="flex items-center justify-center p-4">
                <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500 mr-2"></div>
                <span>${text}</span>
            </div>
        `;
    }

    /**
     * Common Error Handling
     */
    handleError(error, context = 'Operation') {
        console.error(`${context} failed:`, error);
        this.showToast(`${context} failed. Please try again.`, 'error');
    }

    /**
     * Debounce utility
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
}

// Global utilities instance
window.dashboardUtils = new DashboardUtilities();
