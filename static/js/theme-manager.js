/**
 * Theme Manager for Second Brain
 * Handles theme switching, customization, and persistence
 * Version: 1.0.0
 */

class ThemeManager {
  constructor() {
    this.currentTheme = 'default';
    this.availableThemes = [];
    this.customColors = null;
    this.apiBase = '/api/themes';
    this.init();
  }

  async init() {
    try {
      // Load available themes
      await this.loadAvailableThemes();

      // Load user's current theme
      await this.loadUserTheme();

      // Setup event listeners
      this.setupEventListeners();

      // Apply theme immediately
      this.applyTheme(this.currentTheme, this.customColors);
    } catch (error) {
      console.error('Failed to initialize theme manager:', error);
      // Fallback to default theme
      this.applyTheme('default');
    }
  }

  async loadAvailableThemes() {
    try {
      const response = await fetch(`${this.apiBase}/`);
      if (response.ok) {
        this.availableThemes = await response.json();
        console.log(`Loaded ${this.availableThemes.length} themes`);
      }
    } catch (error) {
      console.error('Failed to load themes:', error);
    }
  }

  async loadUserTheme() {
    try {
      const response = await fetch(`${this.apiBase}/user/current`);
      if (response.ok) {
        const data = await response.json();
        this.currentTheme = data.theme_id;
        this.customColors = data.custom_colors;
      }
    } catch (error) {
      console.error('Failed to load user theme:', error);
    }
  }

  async setTheme(themeId, customColors = null) {
    try {
      const response = await fetch(`${this.apiBase}/user/set`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          theme_id: themeId,
          custom_colors: customColors
        })
      });

      if (response.ok) {
        const data = await response.json();
        this.currentTheme = themeId;
        this.customColors = customColors;
        this.applyTheme(themeId, customColors);

        this.showNotification(`Theme changed to "${this.getThemeName(themeId)}"`, 'success');
        return true;
      } else {
        throw new Error('Failed to set theme');
      }
    } catch (error) {
      console.error('Failed to set theme:', error);
      this.showNotification('Failed to change theme', 'error');
      return false;
    }
  }

  applyTheme(themeId, customColors = null) {
    // Set theme attribute on document root
    document.documentElement.setAttribute('data-theme', themeId);

    // Apply custom colors if provided
    if (customColors) {
      this.applyCustomColors(customColors);
    } else {
      this.clearCustomColors();
    }

    // Store in localStorage for quick access
    localStorage.setItem('sb-theme', themeId);
    if (customColors) {
      localStorage.setItem('sb-theme-custom', JSON.stringify(customColors));
    } else {
      localStorage.removeItem('sb-theme-custom');
    }

    // Dispatch theme change event
    const event = new CustomEvent('themeChanged', {
      detail: { themeId, customColors }
    });
    document.dispatchEvent(event);
  }

  applyCustomColors(colors) {
    const root = document.documentElement;
    Object.entries(colors).forEach(([key, value]) => {
      const cssVar = `--sb-${key.replace(/_/g, '-')}`;
      root.style.setProperty(cssVar, value);
    });
  }

  clearCustomColors() {
    const root = document.documentElement;
    // Remove custom color overrides
    const customProps = Array.from(root.style).filter(prop => prop.startsWith('--sb-'));
    customProps.forEach(prop => {
      root.style.removeProperty(prop);
    });
  }

  async resetTheme() {
    try {
      const response = await fetch(`${this.apiBase}/user/reset`, {
        method: 'DELETE'
      });

      if (response.ok) {
        this.currentTheme = 'default';
        this.customColors = null;
        this.applyTheme('default');
        this.showNotification('Theme reset to default', 'success');
        return true;
      }
    } catch (error) {
      console.error('Failed to reset theme:', error);
      this.showNotification('Failed to reset theme', 'error');
      return false;
    }
  }

  async customizeThemeColors(colors) {
    try {
      const response = await fetch(`${this.apiBase}/user/customize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(colors)
      });

      if (response.ok) {
        const data = await response.json();
        this.customColors = data.colors;
        this.applyCustomColors(data.colors);
        this.showNotification('Theme customized', 'success');
        return true;
      }
    } catch (error) {
      console.error('Failed to customize theme:', error);
      this.showNotification('Failed to customize theme', 'error');
      return false;
    }
  }

  getThemeName(themeId) {
    const theme = this.availableThemes.find(t => t.id === themeId);
    return theme ? theme.name : themeId;
  }

  getThemeInfo(themeId) {
    return this.availableThemes.find(t => t.id === themeId);
  }

  setupEventListeners() {
    // Listen for theme selector changes
    document.addEventListener('themeSelect', (e) => {
      this.setTheme(e.detail.themeId);
    });

    // Listen for custom color changes
    document.addEventListener('themeCustomize', (e) => {
      this.customizeThemeColors(e.detail.colors);
    });

    // Auto-detect system theme preference changes
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (this.currentTheme === 'auto') {
          this.applyTheme(e.matches ? 'dark' : 'default');
        }
      });
    }
  }

  showNotification(message, type = 'info') {
    // Use existing notification system if available
    if (typeof showToast === 'function') {
      showToast(message, type);
    } else {
      console.log(`[${type.toUpperCase()}] ${message}`);
    }
  }

  // Public API for other components
  getCurrentTheme() {
    return {
      id: this.currentTheme,
      info: this.getThemeInfo(this.currentTheme),
      customColors: this.customColors
    };
  }

  getAvailableThemes() {
    return this.availableThemes;
  }
}

// ============================================
// Theme Picker UI Component
// ============================================

class ThemePicker {
  constructor(containerSelector, themeManager) {
    this.container = document.querySelector(containerSelector);
    this.themeManager = themeManager;

    if (this.container) {
      this.render();
    }
  }

  render() {
    const themes = this.themeManager.getAvailableThemes();
    const currentTheme = this.themeManager.getCurrentTheme();

    const html = `
      <div class="theme-picker">
        <div class="theme-picker-header">
          <h3 class="text-lg font-semibold text-primary">Choose Theme</h3>
          <p class="text-sm text-secondary">Select a theme that suits your style</p>
        </div>

        <div class="theme-grid">
          ${themes.map(theme => this.renderThemeCard(theme, currentTheme.id)).join('')}
        </div>

        <div class="theme-customization" id="theme-customization">
          <h4 class="text-md font-semibold text-primary mb-4">Customize Colors</h4>
          <div class="color-pickers">
            ${this.renderColorPicker('primary', 'Primary Color')}
            ${this.renderColorPicker('secondary', 'Secondary Color')}
            ${this.renderColorPicker('accent', 'Accent Color')}
            ${this.renderColorPicker('background_primary', 'Background')}
            ${this.renderColorPicker('text_primary', 'Text Color')}
          </div>
          <div class="flex gap-2 mt-4">
            <button class="btn-primary" id="apply-custom-colors">Apply Custom Colors</button>
            <button class="btn-secondary" id="reset-custom-colors">Reset Colors</button>
          </div>
        </div>
      </div>
    `;

    this.container.innerHTML = html;
    this.attachEventListeners();
  }

  renderThemeCard(theme, currentThemeId) {
    const isActive = theme.id === currentThemeId;
    const colors = theme.colors || {};

    return `
      <div class="theme-card ${isActive ? 'active' : ''}" data-theme-id="${theme.id}">
        <div class="theme-preview" style="background: ${colors.bg_primary || '#ffffff'};">
          <div class="preview-bar" style="background: ${colors.primary || '#3b82f6'};"></div>
          <div class="preview-content">
            <div class="preview-text" style="color: ${colors.text_primary || '#111827'};">
              ${theme.name}
            </div>
          </div>
        </div>
        <div class="theme-info">
          <h4 class="theme-name">${theme.name}</h4>
          <p class="theme-description">${theme.description}</p>
          ${theme.is_dark ? '<span class="badge badge-dark">Dark</span>' : '<span class="badge badge-light">Light</span>'}
        </div>
        ${isActive ? '<div class="theme-active-badge">✓ Active</div>' : ''}
      </div>
    `;
  }

  renderColorPicker(id, label) {
    return `
      <div class="color-picker-group">
        <label for="color-${id}" class="text-sm font-medium text-secondary">${label}</label>
        <div class="color-picker-input">
          <input type="color" id="color-${id}" name="${id}" class="color-input">
          <input type="text" id="color-${id}-text" class="text-input" placeholder="#000000">
        </div>
      </div>
    `;
  }

  attachEventListeners() {
    // Theme card click
    this.container.querySelectorAll('.theme-card').forEach(card => {
      card.addEventListener('click', () => {
        const themeId = card.dataset.themeId;
        document.dispatchEvent(new CustomEvent('themeSelect', {
          detail: { themeId }
        }));
        this.render(); // Re-render to show active state
      });
    });

    // Color picker sync
    const colorInputs = this.container.querySelectorAll('.color-input');
    colorInputs.forEach(input => {
      const textInput = this.container.querySelector(`#${input.id}-text`);

      input.addEventListener('input', (e) => {
        textInput.value = e.target.value;
      });

      textInput.addEventListener('input', (e) => {
        if (/^#[0-9A-F]{6}$/i.test(e.target.value)) {
          input.value = e.target.value;
        }
      });
    });

    // Apply custom colors
    const applyBtn = this.container.querySelector('#apply-custom-colors');
    if (applyBtn) {
      applyBtn.addEventListener('click', () => {
        const colors = {};
        colorInputs.forEach(input => {
          const name = input.name;
          const value = input.value;
          if (value) {
            colors[name] = value;
          }
        });

        document.dispatchEvent(new CustomEvent('themeCustomize', {
          detail: { colors }
        }));
      });
    }

    // Reset colors
    const resetBtn = this.container.querySelector('#reset-custom-colors');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        this.themeManager.resetTheme().then(() => {
          this.render();
        });
      });
    }
  }
}

// ============================================
// Initialize Theme Manager
// ============================================

// Auto-initialize on page load
let themeManager;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    themeManager = new ThemeManager();
  });
} else {
  themeManager = new ThemeManager();
}

// Export for use in other scripts
window.ThemeManager = ThemeManager;
window.ThemePicker = ThemePicker;
window.themeManager = themeManager;
