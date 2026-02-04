# -*- coding: utf-8 -*-
"""
TTS160 Alpaca Driver GUI Package

Modern, user-centric interface with light, dark, and astronomy modes.
Implements progressive disclosure and real-time updates.

Usage:
    from gui import create_app, run_app

    gui = create_app(config, device, logger)
    run_app(gui, host='0.0.0.0', port=8080)
"""

from .app import create_app, run_app, TelescopeGUI
from .themes import THEMES, get_theme, apply_theme, Theme
from .state import (
    TelescopeState,
    create_state,
    DisclosureLevel,
    AlignmentState,
    DecisionResult,
)
from .services import DataService, AlignmentDataService

__all__ = [
    # Application
    'create_app',
    'run_app',
    'TelescopeGUI',
    # Themes
    'THEMES',
    'Theme',
    'get_theme',
    'apply_theme',
    # State
    'TelescopeState',
    'create_state',
    'DisclosureLevel',
    'AlignmentState',
    'DecisionResult',
    # Services
    'DataService',
    'AlignmentDataService',
]

__version__ = '0.1.0'
