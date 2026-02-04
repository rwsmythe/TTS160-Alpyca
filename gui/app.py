# -*- coding: utf-8 -*-
"""
TTS160 GUI Application

Main NiceGUI application setup and routing.
"""

import logging
from typing import Any, Callable, Dict, Optional

from nicegui import ui, app

from .themes import THEMES, get_theme, generate_css, DEFAULT_THEME
from .state import TelescopeState, create_state, DisclosureLevel
from .layouts import main_layout
from .components.panels import main_status_panel, control_panel, diagnostics_panel
from .services import DataService, AlignmentDataService


class TelescopeGUI:
    """Main GUI application class.

    Manages the NiceGUI application lifecycle, theme switching,
    and coordinates between components and services.
    """

    def __init__(
        self,
        config: Any,
        device: Any,
        logger: logging.Logger,
        alignment_monitor: Any = None,
    ):
        """Initialize GUI application.

        Args:
            config: TTS160Config instance.
            device: TTS160Device instance.
            logger: Logger for GUI operations.
            alignment_monitor: Optional AlignmentMonitor instance.
        """
        self._config = config
        self._device = device
        self._logger = logger
        self._alignment_monitor = alignment_monitor
        self._state = create_state()

        # Services
        self._data_service: Optional[DataService] = None
        self._alignment_service: Optional[AlignmentDataService] = None

        # Command handlers
        self._handlers: Dict[str, Callable] = {}

        # Initialize theme from config
        theme_name = getattr(config, 'gui_theme', DEFAULT_THEME)
        self._state.update(current_theme=theme_name)

        # Set up command handlers
        self._setup_handlers()

        self._logger.info(f"TelescopeGUI initialized with theme: {theme_name}")

    @property
    def state(self) -> TelescopeState:
        """Get the application state."""
        return self._state

    @property
    def handlers(self) -> Dict[str, Callable]:
        """Get command handlers dict."""
        return self._handlers

    def _setup_handlers(self) -> None:
        """Set up default command handlers."""
        self._handlers = {
            'slew_start': self._handle_slew_start,
            'slew_stop': self._handle_slew_stop,
            'goto': self._handle_goto,
            'speed_change': self._handle_speed_change,
            'tracking_toggle': self._handle_tracking_toggle,
            'tracking_rate': self._handle_tracking_rate,
            'park': self._handle_park,
            'unpark': self._handle_unpark,
            'set_park': self._handle_set_park,
            'home': self._handle_home,
            'sync': self._handle_sync,
            'measure': self._handle_measure,
            'enable_monitor': self._handle_enable_monitor,
            'send_command': self._handle_send_command,
        }

    def _handle_slew_start(self, direction: str) -> None:
        """Handle slew start command."""
        if self._data_service:
            self._data_service.queue_command('slew_start', direction=direction)

    def _handle_slew_stop(self) -> None:
        """Handle slew stop command."""
        if self._data_service:
            self._data_service.queue_command('slew_stop')

    def _handle_goto(self, ra: float, dec: float) -> None:
        """Handle goto command."""
        if self._data_service:
            self._data_service.queue_command('goto', ra=ra, dec=dec)

    def _handle_speed_change(self, speed: int) -> None:
        """Handle speed change command."""
        # Store speed for next slew
        pass

    def _handle_tracking_toggle(self, enabled: bool) -> None:
        """Handle tracking toggle command."""
        if self._data_service:
            self._data_service.queue_command('tracking_toggle', enabled=enabled)

    def _handle_tracking_rate(self, rate: str) -> None:
        """Handle tracking rate change command."""
        # Rate change implementation
        pass

    def _handle_park(self) -> None:
        """Handle park command."""
        if self._data_service:
            self._data_service.queue_command('park')

    def _handle_unpark(self) -> None:
        """Handle unpark command."""
        if self._data_service:
            self._data_service.queue_command('unpark')

    def _handle_set_park(self) -> None:
        """Handle set park position command."""
        pass

    def _handle_home(self) -> None:
        """Handle find home command."""
        if self._data_service:
            self._data_service.queue_command('home')

    def _handle_sync(self, ra: float, dec: float) -> None:
        """Handle sync command."""
        if self._data_service:
            self._data_service.queue_command('sync', ra=ra, dec=dec)

    def _handle_measure(self) -> None:
        """Handle manual measurement command."""
        if self._alignment_monitor and hasattr(self._alignment_monitor, 'measure_now'):
            self._alignment_monitor.measure_now()

    def _handle_enable_monitor(self, enabled: bool) -> None:
        """Handle alignment monitor enable/disable."""
        pass

    def _handle_send_command(self, command: str) -> None:
        """Handle raw command send."""
        self._logger.info(f"Raw command: {command}")

    def register_handler(self, name: str, handler: Callable) -> None:
        """Register a command handler.

        Args:
            name: Handler identifier.
            handler: Callback function.
        """
        self._handlers[name] = handler

    def get_handler(self, name: str) -> Optional[Callable]:
        """Get a registered handler.

        Args:
            name: Handler identifier.

        Returns:
            Handler function or None.
        """
        return self._handlers.get(name)

    def set_theme(self, theme_name: str) -> None:
        """Switch to a different theme.

        Args:
            theme_name: Theme name ('light', 'dark', 'astronomy').
        """
        if theme_name not in THEMES:
            self._logger.warning(f"Unknown theme: {theme_name}")
            return

        self._state.update(current_theme=theme_name)
        self._logger.info(f"Theme changed to: {theme_name}")

        # Apply theme CSS dynamically
        theme = get_theme(theme_name)
        css = generate_css(theme)
        ui.run_javascript(f'''
            const style = document.getElementById('dynamic-theme') || document.createElement('style');
            style.id = 'dynamic-theme';
            style.textContent = `{css}`;
            if (!style.parentNode) document.head.appendChild(style);
        ''')

    def set_disclosure_level(self, level: int) -> None:
        """Set progressive disclosure level.

        Args:
            level: 1 (basic), 2 (expanded), or 3 (advanced).
        """
        try:
            disclosure = DisclosureLevel(level)
            self._state.update(disclosure_level=disclosure)

            # Update body class for CSS-based disclosure
            ui.run_javascript(f'''
                document.body.classList.remove('disclosure-level-1', 'disclosure-level-2', 'disclosure-level-3');
                document.body.classList.add('disclosure-level-{level}');
            ''')

            self._logger.debug(f"Disclosure level set to: {level}")
        except ValueError:
            self._logger.warning(f"Invalid disclosure level: {level}")

    def save_config(self, changes: Dict[str, Any]) -> None:
        """Save configuration changes.

        Args:
            changes: Dict of changed config values.
        """
        for key, value in changes.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
        self._logger.info(f"Config saved: {list(changes.keys())}")

    def start_services(self) -> None:
        """Start background services."""
        # Start data service
        self._data_service = DataService(
            state=self._state,
            device=self._device,
            config=self._config,
            logger=self._logger,
        )
        self._data_service.start()

        # Start alignment data service if monitor available
        if self._alignment_monitor:
            self._alignment_service = AlignmentDataService(
                state=self._state,
                alignment_monitor=self._alignment_monitor,
                logger=self._logger,
            )
            self._alignment_service.start()

    def stop_services(self) -> None:
        """Stop background services."""
        if self._data_service:
            self._data_service.stop()
            self._data_service = None

        if self._alignment_service:
            self._alignment_service.stop()
            self._alignment_service = None

    def build_ui(self) -> None:
        """Build the main UI layout.

        This is called by NiceGUI to construct the page.
        """
        # Use the main layout with all components
        main_layout(
            state=self._state,
            handlers=self._handlers,
            config=self._config,
            on_theme_change=self.set_theme,
            on_disclosure_change=self.set_disclosure_level,
            on_config_save=self.save_config,
        )


def create_app(
    config: Any,
    device: Any,
    logger: logging.Logger,
    alignment_monitor: Any = None,
    title: str = "TTS-160 Telescope Control",
) -> TelescopeGUI:
    """Create the GUI application.

    Args:
        config: TTS160Config instance.
        device: TTS160Device instance.
        logger: Logger for GUI operations.
        alignment_monitor: Optional AlignmentMonitor instance.
        title: Window/page title.

    Returns:
        TelescopeGUI instance ready to run.
    """
    gui = TelescopeGUI(config, device, logger, alignment_monitor)

    @ui.page('/')
    def main_page():
        ui.page_title(title)
        gui.build_ui()

    # Start services when app starts
    app.on_startup(gui.start_services)
    app.on_shutdown(gui.stop_services)

    return gui


def run_app(
    gui: TelescopeGUI,
    host: str = '0.0.0.0',
    port: int = 8080,
    reload: bool = False,
) -> None:
    """Run the GUI application.

    Args:
        gui: TelescopeGUI instance.
        host: Bind address.
        port: Port number.
        reload: Enable auto-reload for development.
    """
    ui.run(
        host=host,
        port=port,
        reload=reload,
        title="TTS-160 Telescope Control",
        favicon='🔭',
    )
