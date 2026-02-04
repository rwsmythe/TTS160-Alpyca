# -*- coding: utf-8 -*-
"""
Theme System for TTS160 GUI

Provides light, dark, and astronomy (red-only) themes with CSS generation.
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class Theme:
    """Theme color and style definitions."""

    name: str

    # Core colors
    background: str
    surface: str
    primary: str

    # Text colors
    text: str
    text_secondary: str

    # Status colors
    success: str
    warning: str
    error: str

    # UI elements
    border: str

    # Optional additional colors
    accent: str = ""
    hover: str = ""

    def __post_init__(self):
        # Set defaults for optional colors if not provided
        if not self.accent:
            object.__setattr__(self, 'accent', self.primary)
        if not self.hover:
            object.__setattr__(self, 'hover', self.surface)


# Theme definitions
THEMES: Dict[str, Theme] = {
    'light': Theme(
        name='Light',
        background='#ffffff',
        surface='#f5f5f5',
        primary='#1976d2',
        text='#212121',
        text_secondary='#757575',
        success='#4caf50',
        warning='#ff9800',
        error='#f44336',
        border='#e0e0e0',
        accent='#1565c0',
        hover='#eeeeee',
    ),
    'dark': Theme(
        name='Dark',
        background='#121212',
        surface='#1e1e1e',
        primary='#90caf9',
        text='#ffffff',
        text_secondary='#b0b0b0',
        success='#81c784',
        warning='#ffb74d',
        error='#e57373',
        border='#333333',
        accent='#64b5f6',
        hover='#2a2a2a',
    ),
    'astronomy': Theme(
        name='Astronomy',
        # All colors are red-spectrum only (>620nm wavelength equivalent)
        # This preserves night vision adaptation
        background='#0a0000',
        surface='#1a0000',
        primary='#ff3333',
        text='#ff6666',
        text_secondary='#993333',
        success='#ff4444',  # Use brightness, not hue
        warning='#ff5555',
        error='#ff2222',
        border='#330000',
        accent='#ff4040',
        hover='#220000',
    ),
}

# Default theme
DEFAULT_THEME = 'dark'


def get_theme(name: str) -> Theme:
    """Get a theme by name.

    Args:
        name: Theme name ('light', 'dark', or 'astronomy')

    Returns:
        Theme instance, or default theme if name not found.
    """
    return THEMES.get(name.lower(), THEMES[DEFAULT_THEME])


def generate_css(theme: Theme) -> str:
    """Generate CSS custom properties from theme.

    Args:
        theme: Theme to generate CSS for.

    Returns:
        CSS string with custom properties.
    """
    return f"""
:root {{
    /* Theme: {theme.name} */
    --bg-color: {theme.background};
    --surface-color: {theme.surface};
    --primary-color: {theme.primary};
    --text-color: {theme.text};
    --text-secondary: {theme.text_secondary};
    --success-color: {theme.success};
    --warning-color: {theme.warning};
    --error-color: {theme.error};
    --border-color: {theme.border};
    --accent-color: {theme.accent};
    --hover-color: {theme.hover};

    /* Typography */
    --font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    --font-mono: 'SF Mono', 'Consolas', 'Monaco', 'Courier New', monospace;

    /* Sizes */
    --text-xs: 12px;
    --text-sm: 14px;
    --text-base: 16px;
    --text-lg: 18px;
    --text-xl: 24px;

    /* Spacing */
    --spacing-xs: 4px;
    --spacing-sm: 8px;
    --spacing-md: 12px;
    --spacing-lg: 16px;
    --spacing-xl: 24px;

    /* Border radius */
    --radius-sm: 4px;
    --radius-md: 8px;
    --radius-lg: 12px;

    /* Transitions */
    --transition-fast: 150ms ease;
    --transition-normal: 250ms ease;
}}

/* Base styles */
body {{
    background-color: var(--bg-color);
    color: var(--text-color);
    font-family: var(--font-family);
    font-size: var(--text-base);
    margin: 0;
    padding: 0;
    transition: background-color var(--transition-normal), color var(--transition-normal);
}}

/* Monospace values */
.mono {{
    font-family: var(--font-mono);
}}

/* Card styling */
.gui-card {{
    background-color: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: var(--spacing-lg);
    transition: background-color var(--transition-normal), border-color var(--transition-normal);
}}

.gui-card:hover {{
    border-color: var(--primary-color);
}}

/* Value display */
.value-large {{
    font-family: var(--font-mono);
    font-size: var(--text-xl);
    font-weight: 500;
}}

.value-normal {{
    font-family: var(--font-mono);
    font-size: var(--text-base);
}}

.value-small {{
    font-family: var(--font-mono);
    font-size: var(--text-sm);
}}

/* Labels */
.label {{
    color: var(--text-secondary);
    font-size: var(--text-sm);
    font-weight: 400;
}}

/* Status indicators */
.indicator {{
    display: inline-block;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    transition: background-color var(--transition-fast);
}}

.indicator-ok {{
    background-color: var(--success-color);
    box-shadow: 0 0 6px var(--success-color);
}}

.indicator-warning {{
    background-color: var(--warning-color);
    box-shadow: 0 0 6px var(--warning-color);
}}

.indicator-error {{
    background-color: var(--error-color);
    box-shadow: 0 0 6px var(--error-color);
}}

.indicator-inactive {{
    background-color: var(--text-secondary);
    opacity: 0.5;
}}

/* Pulse animation for active indicators */
@keyframes pulse {{
    0% {{ opacity: 1; }}
    50% {{ opacity: 0.5; }}
    100% {{ opacity: 1; }}
}}

.indicator-pulse {{
    animation: pulse 2s infinite;
}}

/* Button styles */
.gui-button {{
    background-color: var(--primary-color);
    color: var(--bg-color);
    border: none;
    border-radius: var(--radius-sm);
    padding: var(--spacing-sm) var(--spacing-lg);
    font-size: var(--text-sm);
    cursor: pointer;
    transition: background-color var(--transition-fast), transform var(--transition-fast);
}}

.gui-button:hover {{
    filter: brightness(1.1);
}}

.gui-button:active {{
    transform: scale(0.98);
}}

.gui-button-stop {{
    background-color: var(--error-color);
    font-weight: 600;
}}

/* Input styles */
.gui-input {{
    background-color: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    color: var(--text-color);
    padding: var(--spacing-sm);
    font-family: var(--font-mono);
    transition: border-color var(--transition-fast);
}}

.gui-input:focus {{
    border-color: var(--primary-color);
    outline: none;
}}

/* Notification styles */
.notification {{
    padding: var(--spacing-md);
    border-radius: var(--radius-md);
    margin-bottom: var(--spacing-sm);
}}

.notification-info {{
    background-color: var(--primary-color);
    color: var(--bg-color);
}}

.notification-warning {{
    background-color: var(--warning-color);
    color: var(--bg-color);
}}

.notification-error {{
    background-color: var(--error-color);
    color: #ffffff;
}}

/* Section headers */
.section-header {{
    font-size: var(--text-lg);
    font-weight: 500;
    margin-bottom: var(--spacing-md);
    color: var(--text-color);
}}

/* Disclosure levels */
.disclosure-2, .disclosure-3 {{
    display: none;
}}

.disclosure-level-2 .disclosure-2 {{
    display: block;
}}

.disclosure-level-3 .disclosure-2,
.disclosure-level-3 .disclosure-3 {{
    display: block;
}}

/* Header */
.gui-header {{
    background-color: var(--surface-color);
    border-bottom: 1px solid var(--border-color);
    padding: var(--spacing-md) var(--spacing-lg);
    display: flex;
    justify-content: space-between;
    align-items: center;
}}

/* Footer */
.gui-footer {{
    background-color: var(--surface-color);
    border-top: 1px solid var(--border-color);
    padding: var(--spacing-sm) var(--spacing-lg);
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: var(--text-sm);
}}

/* ============================================ */
/* NiceGUI / Quasar Component Overrides         */
/* ============================================ */

/* Force text color on all elements */
.nicegui-content,
.nicegui-content * {{
    color: var(--text-color);
}}

/* Quasar card */
.q-card {{
    background-color: var(--surface-color) !important;
    color: var(--text-color) !important;
}}

/* Quasar labels and text */
.q-field__label,
.q-field__native,
.q-field__prefix,
.q-field__suffix,
.q-select__dropdown-icon {{
    color: var(--text-color) !important;
}}

/* Quasar input fields */
.q-field--outlined .q-field__control {{
    background-color: var(--surface-color) !important;
}}

.q-field--outlined .q-field__control:before {{
    border-color: var(--border-color) !important;
}}

.q-field--outlined .q-field__control:hover:before {{
    border-color: var(--primary-color) !important;
}}

.q-field--focused .q-field__control:after {{
    border-color: var(--primary-color) !important;
}}

/* Quasar select dropdown */
.q-menu {{
    background-color: var(--surface-color) !important;
}}

.q-item {{
    color: var(--text-color) !important;
}}

.q-item--active,
.q-item:hover {{
    background-color: var(--hover-color) !important;
}}

/* Quasar buttons */
.q-btn {{
    color: var(--text-color) !important;
}}

.q-btn--flat {{
    color: var(--text-color) !important;
}}

.q-btn--outline {{
    border-color: var(--border-color) !important;
    color: var(--text-color) !important;
}}

.q-btn--unelevated {{
    background-color: var(--primary-color) !important;
    color: var(--bg-color) !important;
}}

/* Quasar header */
.q-header {{
    background-color: var(--surface-color) !important;
    color: var(--text-color) !important;
    border-bottom: 1px solid var(--border-color);
}}

/* Quasar footer */
.q-footer {{
    background-color: var(--surface-color) !important;
    color: var(--text-color) !important;
    border-top: 1px solid var(--border-color);
}}

/* Quasar page container */
.q-page {{
    background-color: var(--bg-color) !important;
}}

/* Quasar dialog */
.q-dialog__inner {{
    background-color: transparent !important;
}}

.q-dialog__inner > .q-card {{
    background-color: var(--surface-color) !important;
    color: var(--text-color) !important;
    max-height: 90vh !important;
    overflow: auto;
}}

/* Ensure dialog doesn't go fullscreen */
.q-dialog__inner--minimized {{
    padding: 24px !important;
}}

/* Quasar expansion panels */
.q-expansion-item {{
    background-color: var(--surface-color) !important;
}}

.q-expansion-item__container {{
    background-color: var(--surface-color) !important;
}}

.q-expansion-item .q-item {{
    background-color: var(--surface-color) !important;
    color: var(--text-color) !important;
}}

.q-expansion-item .q-item__label {{
    color: var(--text-color) !important;
}}

.q-expansion-item__content {{
    background-color: var(--surface-color) !important;
    color: var(--text-color) !important;
}}

/* Quasar tab panels */
.q-tab-panels {{
    background-color: var(--surface-color) !important;
}}

.q-tab-panel {{
    background-color: var(--surface-color) !important;
    color: var(--text-color) !important;
}}

/* Quasar switch */
.q-toggle__inner {{
    color: var(--text-secondary) !important;
}}

.q-toggle__inner--truthy {{
    color: var(--primary-color) !important;
}}

/* Quasar number input */
.q-field__native {{
    color: var(--text-color) !important;
}}

/* Quasar separator */
.q-separator {{
    background-color: var(--border-color) !important;
}}

/* Left drawer */
.q-drawer {{
    background-color: var(--surface-color) !important;
    color: var(--text-color) !important;
}}

.q-drawer .q-item {{
    color: var(--text-color) !important;
}}

/* Page background */
.q-page-container {{
    background-color: var(--bg-color) !important;
}}

/* NiceGUI disconnect overlay */
.nicegui-reconnecting,
.nicegui-disconnected {{
    background-color: rgba(0, 0, 0, 0.85) !important;
    color: var(--text-color) !important;
}}

.nicegui-reconnecting *,
.nicegui-disconnected * {{
    color: var(--text-color) !important;
}}

/* Fallback for any disconnect/error overlays */
[class*="disconnect"],
[class*="reconnect"] {{
    background-color: rgba(0, 0, 0, 0.85) !important;
    color: #ffffff !important;
}}

[class*="disconnect"] *,
[class*="reconnect"] * {{
    color: #ffffff !important;
}}

/* Quasar tabs */
.q-tab {{
    color: var(--text-secondary) !important;
}}

.q-tab--active {{
    color: var(--primary-color) !important;
}}

.q-tabs__content {{
    border-bottom: 1px solid var(--border-color);
}}

/* Quasar table */
.q-table {{
    background-color: var(--surface-color) !important;
    color: var(--text-color) !important;
}}

.q-table th {{
    color: var(--text-secondary) !important;
}}

/* Quasar spinner */
.q-spinner {{
    color: var(--primary-color) !important;
}}

/* Secondary text color class */
.text-secondary {{
    color: var(--text-secondary) !important;
}}

/* Fix labels in NiceGUI */
.q-field__bottom {{
    color: var(--text-secondary) !important;
}}

/* Icon colors */
.q-icon {{
    color: var(--text-color) !important;
}}

/* Links */
a {{
    color: var(--primary-color);
}}

a:hover {{
    color: var(--accent-color);
}}
"""


def apply_theme(ui, theme_name: str) -> None:
    """Apply theme to NiceGUI interface.

    Args:
        ui: NiceGUI ui module.
        theme_name: Theme name to apply.
    """
    theme = get_theme(theme_name)
    css = generate_css(theme)
    ui.add_css(css)


# Astronomy mode validation
def is_red_spectrum(hex_color: str) -> bool:
    """Check if a hex color is within the red spectrum.

    For night vision preservation, colors should be primarily red
    with minimal green and blue components.

    Args:
        hex_color: Hex color string (e.g., '#ff3333')

    Returns:
        True if color is predominantly red.
    """
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return False

    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    # Red should dominate; green and blue should be minimal
    return r > g and r > b and g < 40 and b < 40
