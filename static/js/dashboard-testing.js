/**
 * Dashboard v3 Testing Framework
 * Comprehensive frontend testing, quality assurance, and error tracking
 * 
 * Features:
 * - Cross-browser compatibility testing
 * - Performance monitoring and regression detection
 * - Accessibility compliance testing
 * - Feature functionality validation
 * - Memory leak detection
 * - Error boundary and tracking
 * - Automated quality metrics
 * - Core Web Vitals monitoring
 */

class DashboardTesting {
    constructor() {
        this.testResults = new Map();
        this.performanceBaselines = new Map();
        this.errorLog = [];
        this.testSuites = new Map();
        this.runningTests = new Set();
        this.testSchedules = new Map();
        
        // Testing configuration
        this.config = {
            performanceThresholds: {
                fcp: 2000,      // First Contentful Paint
                lcp: 4000,      // Largest Contentful Paint  
                fid: 100,       // First Input Delay
                cls: 0.1,       // Cumulative Layout Shift
                memoryLimit: 100 // MB
            },
            accessibilityRules: [
                'color-contrast',
                'keyboard-navigation',
                'aria-labels', 
                'heading-hierarchy',
                'focus-indicators',
                'alt-text'
            ],
            browserTests: [
                { name: 'Chrome', userAgent: 'chrome' },
                { name: 'Firefox', userAgent: 'firefox' },
                { name: 'Safari', userAgent: 'safari' },
                { name: 'Edge', userAgent: 'edge' }
            ],
            testIntervals: {
                continuous: 30000,      // 30 seconds
                performance: 60000,     // 1 minute
                accessibility: 300000,  // 5 minutes
                memory: 10000          // 10 seconds
            }
        };

        // Test environment detection
        this.environment = {
            browser: this.detectBrowser(),
            device: this.detectDevice(),
            viewport: this.getViewportInfo(),
            capabilities: this.detectCapabilities()
        };

        // Performance monitoring
        this.performanceObservers = new Map();
        this.memoryWatcher = null;
        this.errorBoundary = null;

        // Accessibility testing
        this.a11yRules = new Map();
        this.a11yResults = [];

        // Feature testing registry
        this.featureTests = new Map();
        this.integrationTests = new Map();

        this.init();
    }

    /**
     * INITIALIZATION
     */
    async init() {
        console.log('🧪 Initializing Dashboard Testing Framework');
        
        try {
            // Setup error boundary and tracking
            this.setupErrorBoundary();
            
            // Initialize performance monitoring
            this.initPerformanceMonitoring();
            
            // Setup accessibility testing
            this.initAccessibilityTesting();
            
            // Register core feature tests
            this.registerCoreTests();
            
            // Setup browser compatibility detection
            this.initBrowserCompatibility();
            
            // Initialize memory monitoring
            this.initMemoryMonitoring();
            
            // Setup automated testing schedules
            this.setupTestSchedules();
            
            // Load and apply saved baselines
            await this.loadPerformanceBaselines();
            
            console.log('✅ Dashboard Testing Framework initialized');
            
            // Run initial test suite
            await this.runInitialTests();
            
        } catch (error) {
            console.error('❌ Testing framework initialization failed:', error);
            this.recordError('initialization', error);
        }
    }

    /**
     * ERROR BOUNDARY AND TRACKING
     */
    setupErrorBoundary() {
        // Global error handler
        window.addEventListener('error', (event) => {
            this.recordError('javascript', {
                message: event.message,
                filename: event.filename,
                lineno: event.lineno,
                colno: event.colno,
                error: event.error,
                stack: event.error?.stack,
                timestamp: Date.now(),
                url: window.location.href,
                userAgent: navigator.userAgent
            });
        });

        // Promise rejection handler
        window.addEventListener('unhandledrejection', (event) => {
            this.recordError('promise', {
                reason: event.reason,
                promise: event.promise,
                stack: event.reason?.stack,
                timestamp: Date.now(),
                url: window.location.href
            });
        });

        // Resource loading errors
        document.addEventListener('error', (event) => {
            if (event.target !== window) {
                this.recordError('resource', {
                    tagName: event.target.tagName,
                    src: event.target.src || event.target.href,
                    message: 'Resource failed to load',
                    timestamp: Date.now()
                });
            }
        }, true);

        console.log('🛡️ Error boundary established');
    }

    recordError(type, error) {
        const errorRecord = {
            id: Date.now() + Math.random(),
            type,
            error,
            environment: this.environment,
            timestamp: Date.now(),
            sessionId: this.getSessionId(),
            buildVersion: this.getBuildVersion()
        };

        this.errorLog.push(errorRecord);
        
        // Keep only last 100 errors in memory
        if (this.errorLog.length > 100) {
            this.errorLog = this.errorLog.slice(-50);
        }

        // Store in localStorage for persistence
        try {
            const storedErrors = JSON.parse(localStorage.getItem('dashboard_errors') || '[]');
            storedErrors.push(errorRecord);
            
            // Keep only last 200 errors in storage
            if (storedErrors.length > 200) {
                storedErrors.splice(0, storedErrors.length - 100);
            }
            
            localStorage.setItem('dashboard_errors', JSON.stringify(storedErrors));
        } catch (e) {
            console.warn('Could not store error in localStorage');
        }

        // Report critical errors immediately
        if (this.isCriticalError(error)) {
            this.reportCriticalError(errorRecord);
        }

        console.error(`🚨 ${type.toUpperCase()} Error recorded:`, error);
    }

    isCriticalError(error) {
        const criticalPatterns = [
            /network.*error/i,
            /failed.*to.*fetch/i,
            /authentication.*failed/i,
            /permission.*denied/i,
            /out.*of.*memory/i
        ];

        const errorMessage = typeof error === 'string' ? error : error.message || '';
        return criticalPatterns.some(pattern => pattern.test(errorMessage));
    }

    reportCriticalError(errorRecord) {
        // Send critical errors to monitoring endpoint if available
        if (typeof fetch !== 'undefined') {
            fetch('/api/errors/critical', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(errorRecord)
            }).catch(e => console.warn('Could not report critical error'));
        }
    }

    /**
     * PERFORMANCE MONITORING
     */
    initPerformanceMonitoring() {
        console.log('📊 Initializing performance monitoring');

        // Core Web Vitals monitoring
        this.setupWebVitalsMonitoring();
        
        // API performance tracking
        this.setupAPIPerformanceTracking();
        
        // Render performance monitoring
        this.setupRenderPerformanceTracking();
        
        // User interaction performance
        this.setupInteractionPerformanceTracking();
    }

    setupWebVitalsMonitoring() {
        // First Contentful Paint
        if ('PerformanceObserver' in window) {
            const fcpObserver = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (entry.name === 'first-contentful-paint') {
                        this.recordMetric('fcp', entry.startTime);
                    }
                }
            });

            try {
                fcpObserver.observe({ entryTypes: ['paint'] });
                this.performanceObservers.set('fcp', fcpObserver);
            } catch (e) {
                console.warn('FCP observer not supported');
            }

            // Largest Contentful Paint
            const lcpObserver = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                const lastEntry = entries[entries.length - 1];
                this.recordMetric('lcp', lastEntry.startTime);
            });

            try {
                lcpObserver.observe({ entryTypes: ['largest-contentful-paint'] });
                this.performanceObservers.set('lcp', lcpObserver);
            } catch (e) {
                console.warn('LCP observer not supported');
            }

            // Cumulative Layout Shift
            const clsObserver = new PerformanceObserver((list) => {
                let clsValue = 0;
                for (const entry of list.getEntries()) {
                    if (!entry.hadRecentInput) {
                        clsValue += entry.value;
                    }
                }
                this.recordMetric('cls', clsValue);
            });

            try {
                clsObserver.observe({ entryTypes: ['layout-shift'] });
                this.performanceObservers.set('cls', clsObserver);
            } catch (e) {
                console.warn('CLS observer not supported');
            }

            // First Input Delay
            const fidObserver = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    const delay = entry.processingStart - entry.startTime;
                    this.recordMetric('fid', delay);
                }
            });

            try {
                fidObserver.observe({ entryTypes: ['first-input'] });
                this.performanceObservers.set('fid', fidObserver);
            } catch (e) {
                console.warn('FID observer not supported');
            }
        }
    }

    setupAPIPerformanceTracking() {
        // Override fetch to track API performance
        const originalFetch = window.fetch;
        const self = this;

        window.fetch = function(...args) {
            const startTime = performance.now();
            const url = args[0];

            return originalFetch.apply(this, args).then(response => {
                const endTime = performance.now();
                const duration = endTime - startTime;

                self.recordAPICall(url, {
                    duration,
                    status: response.status,
                    ok: response.ok,
                    timestamp: Date.now()
                });

                return response;
            }).catch(error => {
                const endTime = performance.now();
                const duration = endTime - startTime;

                self.recordAPICall(url, {
                    duration,
                    error: error.message,
                    timestamp: Date.now()
                });

                throw error;
            });
        };
    }

    recordAPICall(url, metrics) {
        const apiCalls = JSON.parse(localStorage.getItem('api_performance') || '[]');
        
        apiCalls.push({
            url,
            metrics,
            timestamp: Date.now()
        });

        // Keep only last 100 API calls
        if (apiCalls.length > 100) {
            apiCalls.splice(0, 50);
        }

        localStorage.setItem('api_performance', JSON.stringify(apiCalls));

        // Check for slow API calls
        if (metrics.duration > 5000) {
            console.warn(`🐌 Slow API call: ${url} (${metrics.duration.toFixed(2)}ms)`);
        }
    }

    setupRenderPerformanceTracking() {
        let renderStart = performance.now();

        const trackRenderTime = () => {
            const renderEnd = performance.now();
            const renderTime = renderEnd - renderStart;
            
            this.recordMetric('render_time', renderTime);
            renderStart = renderEnd;
        };

        // Track on various events that might cause re-renders
        ['click', 'input', 'scroll', 'resize'].forEach(eventType => {
            document.addEventListener(eventType, trackRenderTime, { passive: true });
        });
    }

    setupInteractionPerformanceTracking() {
        // Track input responsiveness
        ['click', 'keydown', 'touchstart'].forEach(eventType => {
            document.addEventListener(eventType, (event) => {
                const startTime = performance.now();
                
                requestAnimationFrame(() => {
                    const responseTime = performance.now() - startTime;
                    this.recordMetric('interaction_response', responseTime);
                    
                    if (responseTime > 100) {
                        console.warn(`🐌 Slow interaction response: ${responseTime.toFixed(2)}ms`);
                    }
                });
            }, { passive: true });
        });
    }

    recordMetric(name, value) {
        const metrics = JSON.parse(localStorage.getItem('performance_metrics') || '{}');
        
        if (!metrics[name]) {
            metrics[name] = [];
        }

        metrics[name].push({
            value,
            timestamp: Date.now(),
            environment: this.environment.browser
        });

        // Keep only last 50 measurements per metric
        if (metrics[name].length > 50) {
            metrics[name] = metrics[name].slice(-25);
        }

        localStorage.setItem('performance_metrics', JSON.stringify(metrics));

        // Check against thresholds
        if (this.config.performanceThresholds[name]) {
            const threshold = this.config.performanceThresholds[name];
            if (value > threshold) {
                this.recordPerformanceRegression(name, value, threshold);
            }
        }
    }

    recordPerformanceRegression(metric, value, threshold) {
        const regression = {
            metric,
            value,
            threshold,
            timestamp: Date.now(),
            environment: this.environment
        };

        console.warn(`📉 Performance regression detected: ${metric} = ${value} (threshold: ${threshold})`);
        
        const regressions = JSON.parse(localStorage.getItem('performance_regressions') || '[]');
        regressions.push(regression);
        
        if (regressions.length > 50) {
            regressions.splice(0, 25);
        }
        
        localStorage.setItem('performance_regressions', JSON.stringify(regressions));
    }

    /**
     * ACCESSIBILITY TESTING
     */
    initAccessibilityTesting() {
        console.log('♿ Initializing accessibility testing');

        // Register accessibility rules
        this.registerA11yRules();
        
        // Setup automated accessibility scanning
        this.setupA11yScanning();
        
        // Setup keyboard navigation testing
        this.setupKeyboardNavigationTesting();
    }

    registerA11yRules() {
        // Color contrast checking
        this.a11yRules.set('color-contrast', {
            name: 'Color Contrast',
            test: () => this.testColorContrast(),
            severity: 'high'
        });

        // Keyboard navigation
        this.a11yRules.set('keyboard-navigation', {
            name: 'Keyboard Navigation',
            test: () => this.testKeyboardNavigation(),
            severity: 'high'
        });

        // ARIA labels
        this.a11yRules.set('aria-labels', {
            name: 'ARIA Labels',
            test: () => this.testAriaLabels(),
            severity: 'medium'
        });

        // Heading hierarchy
        this.a11yRules.set('heading-hierarchy', {
            name: 'Heading Hierarchy',
            test: () => this.testHeadingHierarchy(),
            severity: 'medium'
        });

        // Focus indicators
        this.a11yRules.set('focus-indicators', {
            name: 'Focus Indicators',
            test: () => this.testFocusIndicators(),
            severity: 'high'
        });

        // Alt text for images
        this.a11yRules.set('alt-text', {
            name: 'Alt Text',
            test: () => this.testAltText(),
            severity: 'high'
        });
    }

    async testColorContrast() {
        const results = [];
        const elementsToTest = document.querySelectorAll('*');

        for (const element of elementsToTest) {
            if (element.offsetWidth === 0 || element.offsetHeight === 0) continue;

            const style = window.getComputedStyle(element);
            const textColor = this.parseColor(style.color);
            const bgColor = this.parseColor(style.backgroundColor);

            if (textColor && bgColor) {
                const contrast = this.calculateContrast(textColor, bgColor);
                const fontSize = parseFloat(style.fontSize);
                const isLargeText = fontSize >= 18 || (fontSize >= 14 && style.fontWeight >= 700);
                
                const minContrast = isLargeText ? 3 : 4.5;
                
                if (contrast < minContrast) {
                    results.push({
                        element: element.tagName,
                        class: element.className,
                        contrast: contrast.toFixed(2),
                        minRequired: minContrast,
                        status: 'fail'
                    });
                }
            }
        }

        return {
            passed: results.length === 0,
            violations: results.length,
            details: results
        };
    }

    async testKeyboardNavigation() {
        const results = [];
        const focusableElements = document.querySelectorAll(
            'a[href], button, input, textarea, select, details, [tabindex]:not([tabindex="-1"])'
        );

        for (const element of focusableElements) {
            // Test if element is focusable
            element.focus();
            if (document.activeElement !== element) {
                results.push({
                    element: element.tagName,
                    class: element.className,
                    issue: 'not-focusable',
                    status: 'fail'
                });
            }

            // Test if element has visible focus indicator
            const style = window.getComputedStyle(element, ':focus');
            if (style.outline === 'none' && style.boxShadow === 'none' && style.backgroundColor === 'transparent') {
                results.push({
                    element: element.tagName,
                    class: element.className,
                    issue: 'no-focus-indicator',
                    status: 'fail'
                });
            }
        }

        return {
            passed: results.length === 0,
            violations: results.length,
            details: results
        };
    }

    async testAriaLabels() {
        const results = [];
        const elementsNeedingLabels = document.querySelectorAll(
            'input, button, select, textarea, [role="button"], [role="link"]'
        );

        elementsNeedingLabels.forEach(element => {
            const hasLabel = element.hasAttribute('aria-label') ||
                           element.hasAttribute('aria-labelledby') ||
                           element.labels?.length > 0 ||
                           element.textContent?.trim();

            if (!hasLabel) {
                results.push({
                    element: element.tagName,
                    class: element.className,
                    issue: 'missing-label',
                    status: 'fail'
                });
            }
        });

        return {
            passed: results.length === 0,
            violations: results.length,
            details: results
        };
    }

    async testHeadingHierarchy() {
        const results = [];
        const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
        let previousLevel = 0;

        headings.forEach((heading, index) => {
            const level = parseInt(heading.tagName.charAt(1));
            
            if (index === 0 && level !== 1) {
                results.push({
                    element: heading.tagName,
                    class: heading.className,
                    issue: 'first-heading-not-h1',
                    status: 'fail'
                });
            }

            if (level - previousLevel > 1) {
                results.push({
                    element: heading.tagName,
                    class: heading.className,
                    issue: 'heading-level-skipped',
                    status: 'fail'
                });
            }

            previousLevel = level;
        });

        return {
            passed: results.length === 0,
            violations: results.length,
            details: results
        };
    }

    async testFocusIndicators() {
        // This is covered in testKeyboardNavigation but kept separate for clarity
        return this.testKeyboardNavigation();
    }

    async testAltText() {
        const results = [];
        const images = document.querySelectorAll('img');

        images.forEach(img => {
            if (!img.hasAttribute('alt')) {
                results.push({
                    element: 'IMG',
                    src: img.src,
                    issue: 'missing-alt-attribute',
                    status: 'fail'
                });
            } else if (img.alt.trim() === '' && img.getAttribute('role') !== 'presentation') {
                results.push({
                    element: 'IMG',
                    src: img.src,
                    issue: 'empty-alt-text',
                    status: 'warning'
                });
            }
        });

        return {
            passed: results.length === 0,
            violations: results.length,
            details: results
        };
    }

    setupA11yScanning() {
        // Run accessibility tests periodically
        setInterval(() => {
            this.runAccessibilityTests();
        }, this.config.testIntervals.accessibility);
    }

    async runAccessibilityTests() {
        console.log('♿ Running accessibility tests...');
        
        const results = {};
        
        for (const [ruleName, rule] of this.a11yRules.entries()) {
            try {
                const result = await rule.test();
                results[ruleName] = {
                    ...result,
                    severity: rule.severity,
                    timestamp: Date.now()
                };
            } catch (error) {
                results[ruleName] = {
                    passed: false,
                    error: error.message,
                    severity: rule.severity,
                    timestamp: Date.now()
                };
            }
        }

        this.a11yResults.push(results);
        
        // Keep only last 10 test results
        if (this.a11yResults.length > 10) {
            this.a11yResults = this.a11yResults.slice(-5);
        }

        // Store results
        localStorage.setItem('accessibility_results', JSON.stringify(this.a11yResults));

        // Report violations
        const totalViolations = Object.values(results).reduce((sum, result) => 
            sum + (result.violations || 0), 0
        );

        if (totalViolations > 0) {
            console.warn(`♿ Accessibility violations found: ${totalViolations}`);
        } else {
            console.log('♿ All accessibility tests passed');
        }

        return results;
    }

    setupKeyboardNavigationTesting() {
        // Test keyboard navigation on focus changes
        let tabSequence = [];

        document.addEventListener('focusin', (event) => {
            tabSequence.push({
                element: event.target,
                timestamp: Date.now()
            });

            // Keep only last 20 focus events
            if (tabSequence.length > 20) {
                tabSequence = tabSequence.slice(-10);
            }
        });

        // Test for keyboard traps
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Tab') {
                const activeElement = document.activeElement;
                const focusableElements = Array.from(document.querySelectorAll(
                    'a[href], button, input, textarea, select, details, [tabindex]:not([tabindex="-1"])'
                ));
                
                const currentIndex = focusableElements.indexOf(activeElement);
                const expectedNext = event.shiftKey ? 
                    focusableElements[currentIndex - 1] : 
                    focusableElements[currentIndex + 1];

                setTimeout(() => {
                    if (document.activeElement !== expectedNext && expectedNext) {
                        console.warn('♿ Potential keyboard trap detected');
                    }
                }, 10);
            }
        });
    }

    /**
     * BROWSER COMPATIBILITY TESTING
     */
    initBrowserCompatibility() {
        console.log('🌐 Initializing browser compatibility testing');
        
        this.testBrowserFeatures();
        this.testCSSFeatures();
        this.testAPISupport();
    }

    testBrowserFeatures() {
        const features = {
            webGL: !!window.WebGLRenderingContext,
            webGL2: !!window.WebGL2RenderingContext,
            webWorkers: !!window.Worker,
            serviceWorker: 'serviceWorker' in navigator,
            indexedDB: !!window.indexedDB,
            localStorage: (() => {
                try {
                    localStorage.setItem('test', 'test');
                    localStorage.removeItem('test');
                    return true;
                } catch (e) {
                    return false;
                }
            })(),
            sessionStorage: (() => {
                try {
                    sessionStorage.setItem('test', 'test');
                    sessionStorage.removeItem('test');
                    return true;
                } catch (e) {
                    return false;
                }
            })(),
            geolocation: !!navigator.geolocation,
            camera: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
            pushNotifications: 'Notification' in window && 'PushManager' in window,
            backgroundSync: 'serviceWorker' in navigator && 'sync' in window.ServiceWorkerRegistration.prototype,
            webAssembly: !!window.WebAssembly,
            intersectionObserver: !!window.IntersectionObserver,
            performanceObserver: !!window.PerformanceObserver,
            resizeObserver: !!window.ResizeObserver
        };

        const unsupportedFeatures = Object.entries(features)
            .filter(([name, supported]) => !supported)
            .map(([name]) => name);

        if (unsupportedFeatures.length > 0) {
            console.warn('🌐 Unsupported browser features:', unsupportedFeatures);
        }

        // Store results
        const compatibility = {
            browser: this.environment.browser,
            features,
            unsupportedFeatures,
            timestamp: Date.now()
        };

        localStorage.setItem('browser_compatibility', JSON.stringify(compatibility));
        return compatibility;
    }

    testCSSFeatures() {
        const testElement = document.createElement('div');
        document.body.appendChild(testElement);

        const cssFeatures = {
            grid: CSS.supports('display', 'grid'),
            flexbox: CSS.supports('display', 'flex'),
            customProperties: CSS.supports('color', 'var(--test)'),
            backdropFilter: CSS.supports('backdrop-filter', 'blur(10px)'),
            aspectRatio: CSS.supports('aspect-ratio', '1/1'),
            containerQueries: CSS.supports('container-type', 'inline-size'),
            logicalProperties: CSS.supports('margin-inline-start', '1px'),
            colorScheme: CSS.supports('color-scheme', 'dark'),
            scrollBehavior: CSS.supports('scroll-behavior', 'smooth'),
            stickyPosition: CSS.supports('position', 'sticky')
        };

        document.body.removeChild(testElement);

        const unsupportedCSS = Object.entries(cssFeatures)
            .filter(([name, supported]) => !supported)
            .map(([name]) => name);

        if (unsupportedCSS.length > 0) {
            console.warn('🌐 Unsupported CSS features:', unsupportedCSS);
        }

        return cssFeatures;
    }

    testAPISupport() {
        const apis = {
            fetch: !!window.fetch,
            websockets: !!window.WebSocket,
            webRTC: !!(window.RTCPeerConnection || window.webkitRTCPeerConnection),
            clipboard: !!navigator.clipboard,
            share: !!navigator.share,
            payment: !!window.PaymentRequest,
            vibration: !!navigator.vibrate,
            battery: !!navigator.getBattery,
            networkInformation: !!(navigator.connection || navigator.mozConnection || navigator.webkitConnection),
            deviceOrientation: !!window.DeviceOrientationEvent,
            deviceMotion: !!window.DeviceMotionEvent
        };

        const unsupportedAPIs = Object.entries(apis)
            .filter(([name, supported]) => !supported)
            .map(([name]) => name);

        if (unsupportedAPIs.length > 0) {
            console.warn('🌐 Unsupported APIs:', unsupportedAPIs);
        }

        return apis;
    }

    /**
     * MEMORY LEAK DETECTION
     */
    initMemoryMonitoring() {
        console.log('🧠 Initializing memory monitoring');

        if ('memory' in performance) {
            this.memoryWatcher = setInterval(() => {
                this.checkMemoryUsage();
            }, this.config.testIntervals.memory);
        } else {
            console.warn('🧠 Memory monitoring not available');
        }
    }

    checkMemoryUsage() {
        if (!('memory' in performance)) return;

        const memory = performance.memory;
        const usedMB = memory.usedJSHeapSize / 1048576;
        const totalMB = memory.totalJSHeapSize / 1048576;
        const limitMB = memory.jsHeapSizeLimit / 1048576;

        const memoryInfo = {
            used: usedMB,
            total: totalMB,
            limit: limitMB,
            percentage: (usedMB / limitMB) * 100,
            timestamp: Date.now()
        };

        // Store memory measurements
        const memoryHistory = JSON.parse(localStorage.getItem('memory_history') || '[]');
        memoryHistory.push(memoryInfo);

        if (memoryHistory.length > 100) {
            memoryHistory.splice(0, 50);
        }

        localStorage.setItem('memory_history', JSON.stringify(memoryHistory));

        // Check for memory issues
        if (usedMB > this.config.performanceThresholds.memoryLimit) {
            this.recordMemoryLeak(memoryInfo);
        }

        // Check for rapid memory growth
        if (memoryHistory.length > 10) {
            const recent = memoryHistory.slice(-10);
            const growth = recent[recent.length - 1].used - recent[0].used;
            const timeSpan = recent[recent.length - 1].timestamp - recent[0].timestamp;
            const growthRate = growth / (timeSpan / 1000); // MB per second

            if (growthRate > 1) { // More than 1MB per second growth
                console.warn(`🧠 Rapid memory growth detected: ${growthRate.toFixed(2)} MB/s`);
            }
        }
    }

    recordMemoryLeak(memoryInfo) {
        console.warn(`🧠 High memory usage: ${memoryInfo.used.toFixed(2)}MB`);

        const leaks = JSON.parse(localStorage.getItem('memory_leaks') || '[]');
        leaks.push({
            ...memoryInfo,
            stackTrace: new Error().stack,
            url: window.location.href
        });

        if (leaks.length > 20) {
            leaks.splice(0, 10);
        }

        localStorage.setItem('memory_leaks', JSON.stringify(leaks));
    }

    /**
     * FEATURE TESTING
     */
    registerCoreTests() {
        console.log('🧪 Registering core feature tests');

        // Search functionality
        this.featureTests.set('search', {
            name: 'Search Functionality',
            test: () => this.testSearchFunctionality(),
            critical: true
        });

        // Note creation
        this.featureTests.set('note-creation', {
            name: 'Note Creation',
            test: () => this.testNoteCreation(),
            critical: true
        });

        // Navigation
        this.featureTests.set('navigation', {
            name: 'Navigation',
            test: () => this.testNavigation(),
            critical: true
        });

        // Keyboard shortcuts
        this.featureTests.set('shortcuts', {
            name: 'Keyboard Shortcuts',
            test: () => this.testKeyboardShortcuts(),
            critical: false
        });

        // Drag and drop
        this.featureTests.set('drag-drop', {
            name: 'Drag and Drop',
            test: () => this.testDragDrop(),
            critical: false
        });

        // Data persistence
        this.featureTests.set('persistence', {
            name: 'Data Persistence',
            test: () => this.testDataPersistence(),
            critical: true
        });
    }

    async testSearchFunctionality() {
        const results = [];

        try {
            // Test global search input
            const globalSearch = document.getElementById('globalSearch');
            if (!globalSearch) {
                results.push({ test: 'global-search-element', status: 'fail', message: 'Global search element not found' });
            } else {
                // Test input responsiveness
                globalSearch.focus();
                if (document.activeElement !== globalSearch) {
                    results.push({ test: 'global-search-focus', status: 'fail', message: 'Cannot focus global search' });
                } else {
                    results.push({ test: 'global-search-focus', status: 'pass' });
                }

                // Test typing (use temporary value and clean up)
                const originalValue = globalSearch.value;
                globalSearch.value = 'temp_test_value';
                const inputEvent = new Event('input', { bubbles: true });
                globalSearch.dispatchEvent(inputEvent);
                // Clean up test value immediately
                globalSearch.value = originalValue;
                results.push({ test: 'global-search-input', status: 'pass' });
            }

            // Test advanced search
            const advancedSearch = document.getElementById('advancedSearchInput');
            if (advancedSearch) {
                results.push({ test: 'advanced-search-element', status: 'pass' });
            } else {
                results.push({ test: 'advanced-search-element', status: 'fail', message: 'Advanced search element not found' });
            }

        } catch (error) {
            results.push({ test: 'search-general', status: 'error', message: error.message });
        }

        return {
            passed: results.every(r => r.status === 'pass'),
            results
        };
    }

    async testNoteCreation() {
        const results = [];

        try {
            // Test note input element
            const noteInput = document.getElementById('note');
            if (!noteInput) {
                results.push({ test: 'note-input-element', status: 'fail', message: 'Note input element not found' });
            } else {
                // Test input functionality
                noteInput.focus();
                if (document.activeElement !== noteInput) {
                    results.push({ test: 'note-input-focus', status: 'fail', message: 'Cannot focus note input' });
                } else {
                    results.push({ test: 'note-input-focus', status: 'pass' });
                }

                // Test typing
                const testContent = 'Test note content';
                noteInput.value = testContent;
                const inputEvent = new Event('input', { bubbles: true });
                noteInput.dispatchEvent(inputEvent);

                if (noteInput.value === testContent) {
                    results.push({ test: 'note-input-content', status: 'pass' });
                } else {
                    results.push({ test: 'note-input-content', status: 'fail', message: 'Note input value not set correctly' });
                }

                // Clean up
                noteInput.value = '';
            }

            // Test form submission
            const form = document.getElementById('quickCaptureForm');
            if (form) {
                results.push({ test: 'note-form-element', status: 'pass' });
            } else {
                results.push({ test: 'note-form-element', status: 'fail', message: 'Note form not found' });
            }

        } catch (error) {
            results.push({ test: 'note-creation-general', status: 'error', message: error.message });
        }

        return {
            passed: results.every(r => r.status === 'pass'),
            results
        };
    }

    async testNavigation() {
        const results = [];

        try {
            // Test view switching
            const viewElements = document.querySelectorAll('[data-view]');
            if (viewElements.length === 0) {
                results.push({ test: 'navigation-views', status: 'fail', message: 'No view elements found' });
            } else {
                results.push({ test: 'navigation-views', status: 'pass', message: `Found ${viewElements.length} views` });
            }

            // Test navigation buttons
            const navButtons = document.querySelectorAll('.nav-button, [data-nav]');
            if (navButtons.length === 0) {
                results.push({ test: 'navigation-buttons', status: 'fail', message: 'No navigation buttons found' });
            } else {
                results.push({ test: 'navigation-buttons', status: 'pass', message: `Found ${navButtons.length} nav buttons` });
            }

        } catch (error) {
            results.push({ test: 'navigation-general', status: 'error', message: error.message });
        }

        return {
            passed: results.every(r => r.status === 'pass'),
            results
        };
    }

    async testKeyboardShortcuts() {
        const results = [];

        try {
            // Test if dashboard performance system is available (handles shortcuts)
            if (window.dashboardPerformance && window.dashboardPerformance.shortcuts) {
                const shortcutCount = window.dashboardPerformance.shortcuts.size;
                results.push({ test: 'shortcuts-registered', status: 'pass', message: `${shortcutCount} shortcuts registered` });
            } else {
                results.push({ test: 'shortcuts-registered', status: 'fail', message: 'Keyboard shortcuts system not found' });
            }

        } catch (error) {
            results.push({ test: 'shortcuts-general', status: 'error', message: error.message });
        }

        return {
            passed: results.every(r => r.status === 'pass'),
            results
        };
    }

    async testDragDrop() {
        const results = [];

        try {
            // Test drop zones
            const dropZones = document.querySelectorAll('[data-drop-zone], .file-drop-zone');
            if (dropZones.length === 0) {
                results.push({ test: 'drop-zones', status: 'warning', message: 'No drop zones found' });
            } else {
                results.push({ test: 'drop-zones', status: 'pass', message: `Found ${dropZones.length} drop zones` });
            }

            // Test drag events support
            const supportsDragEvents = 'ondragstart' in document.createElement('div');
            results.push({ 
                test: 'drag-events-support', 
                status: supportsDragEvents ? 'pass' : 'fail',
                message: supportsDragEvents ? 'Drag events supported' : 'Drag events not supported'
            });

        } catch (error) {
            results.push({ test: 'drag-drop-general', status: 'error', message: error.message });
        }

        return {
            passed: results.every(r => r.status === 'pass' || r.status === 'warning'),
            results
        };
    }

    async testDataPersistence() {
        const results = [];

        try {
            // Test localStorage
            const testKey = 'dashboard_test_' + Date.now();
            const testValue = 'test_value';

            localStorage.setItem(testKey, testValue);
            const retrieved = localStorage.getItem(testKey);
            localStorage.removeItem(testKey);

            if (retrieved === testValue) {
                results.push({ test: 'localStorage', status: 'pass' });
            } else {
                results.push({ test: 'localStorage', status: 'fail', message: 'localStorage not working' });
            }

            // Test sessionStorage
            sessionStorage.setItem(testKey, testValue);
            const sessionRetrieved = sessionStorage.getItem(testKey);
            sessionStorage.removeItem(testKey);

            if (sessionRetrieved === testValue) {
                results.push({ test: 'sessionStorage', status: 'pass' });
            } else {
                results.push({ test: 'sessionStorage', status: 'fail', message: 'sessionStorage not working' });
            }

        } catch (error) {
            results.push({ test: 'data-persistence-general', status: 'error', message: error.message });
        }

        return {
            passed: results.every(r => r.status === 'pass'),
            results
        };
    }

    /**
     * TEST EXECUTION
     */
    async runInitialTests() {
        console.log('🧪 Running initial test suite...');

        const startTime = performance.now();
        const results = {};

        // Run browser compatibility tests
        results.browserCompatibility = this.testBrowserFeatures();
        results.cssFeatures = this.testCSSFeatures();
        results.apiSupport = this.testAPISupport();

        // Run accessibility tests
        results.accessibility = await this.runAccessibilityTests();

        // Run feature tests
        const featureResults = {};
        for (const [testName, testConfig] of this.featureTests.entries()) {
            try {
                featureResults[testName] = await testConfig.test();
            } catch (error) {
                featureResults[testName] = {
                    passed: false,
                    error: error.message
                };
            }
        }
        results.features = featureResults;

        const endTime = performance.now();
        const duration = endTime - startTime;

        results.meta = {
            duration,
            timestamp: Date.now(),
            environment: this.environment
        };

        // Store test results
        this.testResults.set('initial', results);
        localStorage.setItem('dashboard_test_results', JSON.stringify({
            initial: results
        }));

        console.log(`✅ Initial tests completed in ${duration.toFixed(2)}ms`);
        this.generateTestReport(results);

        return results;
    }

    async runContinuousTests() {
        console.log('🔄 Running continuous tests...');

        const results = {};

        // Run performance checks
        results.performance = this.getPerformanceSnapshot();
        
        // Run memory check
        if ('memory' in performance) {
            results.memory = {
                used: performance.memory.usedJSHeapSize / 1048576,
                total: performance.memory.totalJSHeapSize / 1048576,
                limit: performance.memory.jsHeapSizeLimit / 1048576
            };
        }

        // Store results
        const timestamp = Date.now();
        this.testResults.set(`continuous_${timestamp}`, results);

        return results;
    }

    setupTestSchedules() {
        // Continuous monitoring
        this.testSchedules.set('continuous', setInterval(() => {
            this.runContinuousTests();
        }, this.config.testIntervals.continuous));

        // Performance monitoring
        this.testSchedules.set('performance', setInterval(() => {
            this.checkPerformanceRegression();
        }, this.config.testIntervals.performance));
    }

    checkPerformanceRegression() {
        const currentMetrics = this.getPerformanceSnapshot();
        const baseline = this.performanceBaselines.get('current');

        if (!baseline) {
            this.performanceBaselines.set('current', currentMetrics);
            return;
        }

        const regressions = [];

        for (const [metric, value] of Object.entries(currentMetrics)) {
            const baselineValue = baseline[metric];
            if (baselineValue && typeof value === 'number' && typeof baselineValue === 'number') {
                const regression = ((value - baselineValue) / baselineValue) * 100;
                
                if (regression > 20) { // 20% regression threshold
                    regressions.push({
                        metric,
                        current: value,
                        baseline: baselineValue,
                        regression: regression.toFixed(2)
                    });
                }
            }
        }

        if (regressions.length > 0) {
            console.warn('📉 Performance regressions detected:', regressions);
        }
    }

    getPerformanceSnapshot() {
        const snapshot = {};

        // Get current performance metrics from localStorage
        const metrics = JSON.parse(localStorage.getItem('performance_metrics') || '{}');
        
        for (const [metricName, values] of Object.entries(metrics)) {
            if (values.length > 0) {
                const recent = values.slice(-5);
                snapshot[metricName] = recent.reduce((sum, item) => sum + item.value, 0) / recent.length;
            }
        }

        return snapshot;
    }

    async loadPerformanceBaselines() {
        try {
            const stored = localStorage.getItem('performance_baselines');
            if (stored) {
                const baselines = JSON.parse(stored);
                for (const [key, value] of Object.entries(baselines)) {
                    this.performanceBaselines.set(key, value);
                }
            }
        } catch (error) {
            console.warn('Could not load performance baselines:', error);
        }
    }

    /**
     * UTILITY METHODS
     */
    detectBrowser() {
        const userAgent = navigator.userAgent;
        
        if (userAgent.includes('Chrome') && !userAgent.includes('Edg')) {
            return 'Chrome';
        } else if (userAgent.includes('Firefox')) {
            return 'Firefox';
        } else if (userAgent.includes('Safari') && !userAgent.includes('Chrome')) {
            return 'Safari';
        } else if (userAgent.includes('Edg')) {
            return 'Edge';
        } else {
            return 'Unknown';
        }
    }

    detectDevice() {
        const userAgent = navigator.userAgent;
        
        if (/Android/i.test(userAgent)) {
            return 'Android';
        } else if (/iPhone|iPad|iPod/i.test(userAgent)) {
            return 'iOS';
        } else if (/Windows/i.test(userAgent)) {
            return 'Windows';
        } else if (/Macintosh/i.test(userAgent)) {
            return 'Mac';
        } else if (/Linux/i.test(userAgent)) {
            return 'Linux';
        } else {
            return 'Unknown';
        }
    }

    getViewportInfo() {
        return {
            width: window.innerWidth,
            height: window.innerHeight,
            ratio: window.innerWidth / window.innerHeight,
            pixelRatio: window.devicePixelRatio || 1
        };
    }

    detectCapabilities() {
        return {
            touchScreen: 'ontouchstart' in window,
            geolocation: !!navigator.geolocation,
            notifications: 'Notification' in window,
            serviceWorker: 'serviceWorker' in navigator,
            webGL: !!window.WebGLRenderingContext,
            webAssembly: !!window.WebAssembly
        };
    }

    getSessionId() {
        let sessionId = sessionStorage.getItem('dashboard_session_id');
        if (!sessionId) {
            sessionId = 'sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            sessionStorage.setItem('dashboard_session_id', sessionId);
        }
        return sessionId;
    }

    getBuildVersion() {
        // This would ideally come from a build process
        return document.querySelector('meta[name="build-version"]')?.content || 'dev';
    }

    parseColor(color) {
        // Simple RGB color parser
        const match = color.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
        if (match) {
            return {
                r: parseInt(match[1]),
                g: parseInt(match[2]),
                b: parseInt(match[3])
            };
        }
        return null;
    }

    calculateContrast(color1, color2) {
        const luminance1 = this.getLuminance(color1);
        const luminance2 = this.getLuminance(color2);
        
        const lighter = Math.max(luminance1, luminance2);
        const darker = Math.min(luminance1, luminance2);
        
        return (lighter + 0.05) / (darker + 0.05);
    }

    getLuminance(color) {
        const { r, g, b } = color;
        const rsRGB = r / 255;
        const gsRGB = g / 255;
        const bsRGB = b / 255;

        const rLinear = rsRGB <= 0.03928 ? rsRGB / 12.92 : Math.pow((rsRGB + 0.055) / 1.055, 2.4);
        const gLinear = gsRGB <= 0.03928 ? gsRGB / 12.92 : Math.pow((gsRGB + 0.055) / 1.055, 2.4);
        const bLinear = bsRGB <= 0.03928 ? bsRGB / 12.92 : Math.pow((bsRGB + 0.055) / 1.055, 2.4);

        return 0.2126 * rLinear + 0.7152 * gLinear + 0.0722 * bLinear;
    }

    generateTestReport(results) {
        console.group('📋 Dashboard Test Report');
        
        console.log('🌐 Browser:', this.environment.browser, this.environment.device);
        console.log('📱 Viewport:', `${this.environment.viewport.width}x${this.environment.viewport.height}`);
        
        if (results.features) {
            console.group('⚡ Feature Tests');
            for (const [name, result] of Object.entries(results.features)) {
                const status = result.passed ? '✅' : '❌';
                console.log(`${status} ${name}`);
                if (result.results) {
                    result.results.forEach(r => {
                        if (r.status !== 'pass') {
                            console.log(`   - ${r.test}: ${r.status} ${r.message || ''}`);
                        }
                    });
                }
            }
            console.groupEnd();
        }

        if (results.accessibility) {
            console.group('♿ Accessibility Tests');
            for (const [rule, result] of Object.entries(results.accessibility)) {
                const status = result.passed ? '✅' : '❌';
                const violations = result.violations || 0;
                console.log(`${status} ${rule}: ${violations} violations`);
            }
            console.groupEnd();
        }

        console.log('⏱️ Test Duration:', `${results.meta?.duration?.toFixed(2)}ms`);
        console.groupEnd();
    }

    /**
     * PUBLIC API
     */
    async runAllTests() {
        console.log('🧪 Running all tests...');
        
        const results = {
            performance: await this.runContinuousTests(),
            accessibility: await this.runAccessibilityTests(),
            features: {}
        };

        for (const [testName, testConfig] of this.featureTests.entries()) {
            results.features[testName] = await testConfig.test();
        }

        return results;
    }

    getTestResults() {
        return Object.fromEntries(this.testResults.entries());
    }

    getErrorLog() {
        return [...this.errorLog];
    }

    clearErrorLog() {
        this.errorLog = [];
        localStorage.removeItem('dashboard_errors');
    }

    getPerformanceReport() {
        const metrics = JSON.parse(localStorage.getItem('performance_metrics') || '{}');
        const regressions = JSON.parse(localStorage.getItem('performance_regressions') || '[]');
        const memoryHistory = JSON.parse(localStorage.getItem('memory_history') || '[]');

        return {
            metrics,
            regressions,
            memoryHistory,
            environment: this.environment
        };
    }

    getAccessibilityReport() {
        return {
            results: this.a11yResults,
            rules: Array.from(this.a11yRules.keys()),
            environment: this.environment
        };
    }

    cleanup() {
        console.log('🧹 Cleaning up testing framework');

        // Clear intervals
        for (const [name, intervalId] of this.testSchedules.entries()) {
            clearInterval(intervalId);
        }

        // Disconnect observers
        for (const [name, observer] of this.performanceObservers.entries()) {
            observer.disconnect();
        }

        if (this.memoryWatcher) {
            clearInterval(this.memoryWatcher);
        }

        console.log('✅ Testing framework cleanup completed');
    }
}

// Initialize testing framework when explicitly enabled
// Enable via any of the following:
//  - URL query param: ?debug_testing=1
//  - LocalStorage flag: localStorage.setItem('enable_dashboard_testing', 'true')
//  - Global flag: window.SecondBrain?.debug?.testing === true
(() => {
    try {
        const params = new URLSearchParams(window.location.search || '');
        const enabledViaQuery = params.get('debug_testing') === '1' || params.get('testing') === '1';
        const enabledViaLocalStorage = (localStorage.getItem('enable_dashboard_testing') || '').toLowerCase() === 'true';
        const enabledViaGlobal = !!(window.SecondBrain && window.SecondBrain.debug && window.SecondBrain.debug.testing === true);
        const testingEnabled = enabledViaQuery || enabledViaLocalStorage || enabledViaGlobal;

        if (!testingEnabled) {
            // Do not start the testing harness by default in normal usage
            console.log('🧪 Dashboard testing disabled (enable with ?debug_testing=1 or localStorage flag)');
            return;
        }

        const start = () => {
            window.dashboardTesting = new DashboardTesting();
        };

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', start);
        } else {
            start();
        }
    } catch (e) {
        console.warn('Dashboard testing bootstrap skipped due to error:', e);
    }
})();

// Export for debugging and manual testing
window.DashboardTesting = DashboardTesting;
