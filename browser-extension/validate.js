// validate.js - Extension validation script
// Run this in the browser console on the popup to check for issues

function validateExtension() {
    const issues = [];
    
    // Check required DOM elements
    const requiredElements = [
        'status', 'captureSelection', 'capturePage', 'captureBookmark',
        'saveManual', 'manualNote', 'manualTags', 'recentCaptures',
        'openDashboard', 'openSettings', 'messages'
    ];
    
    requiredElements.forEach(id => {
        if (!document.getElementById(id)) {
            issues.push(`Missing element: ${id}`);
        }
    });
    
    // Check chrome APIs
    if (typeof chrome === 'undefined') {
        issues.push('Chrome extension APIs not available');
    } else {
        const requiredAPIs = ['storage', 'tabs', 'scripting', 'contextMenus', 'runtime'];
        requiredAPIs.forEach(api => {
            if (!chrome[api]) {
                issues.push(`Missing Chrome API: ${api}`);
            }
        });
    }
    
    // Check classes
    try {
        new SecondBrainExtension();
        console.log('✓ SecondBrainExtension class instantiated successfully');
    } catch (error) {
        issues.push(`SecondBrainExtension error: ${error.message}`);
    }
    
    if (issues.length === 0) {
        console.log('🎉 Extension validation passed!');
        return true;
    } else {
        console.error('❌ Extension validation failed:');
        issues.forEach(issue => console.error(`  - ${issue}`));
        return false;
    }
}

// Auto-validate when loaded
if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', validateExtension);
} else {
    console.log('Run validateExtension() when popup is loaded');
}