# -*- coding: utf-8 -*-
"""
Diagnostics Panel

Layer 3 advanced information for debugging and development.
"""

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from nicegui import ui

from ...state import TelescopeState


class LogEntry:
    """Log entry for display."""

    def __init__(
        self,
        timestamp: datetime,
        level: str,
        message: str,
        source: str = "",
    ):
        self.timestamp = timestamp
        self.level = level
        self.message = message
        self.source = source


class DiagnosticsPanel:
    """Advanced diagnostics panel with log viewer and raw data."""

    def __init__(
        self,
        state: TelescopeState,
        on_command: Optional[Callable[[str], None]] = None,
    ):
        """Initialize diagnostics panel.

        Args:
            state: Telescope state instance.
            on_command: Optional callback for manual command input.
        """
        self._state = state
        self._on_command = on_command
        self._logs: List[LogEntry] = []
        self._command_history: List[str] = []
        self._max_logs = 500
        self._filter_level = 'DEBUG'

        self._container: Optional[ui.element] = None
        self._log_container: Optional[ui.element] = None

    def build(self) -> ui.element:
        """Build the diagnostics panel UI.

        Returns:
            Container element.
        """
        with ui.card().classes('gui-card w-full disclosure-3') as self._container:
            ui.label('Diagnostics').classes('section-header')

            with ui.tabs().classes('w-full') as tabs:
                log_tab = ui.tab('Logs')
                commands_tab = ui.tab('Commands')
                raw_tab = ui.tab('Raw Data')
                perf_tab = ui.tab('Performance')

            with ui.tab_panels(tabs, value=log_tab).classes('w-full'):
                # Logs tab
                with ui.tab_panel(log_tab):
                    self._build_log_viewer()

                # Commands tab
                with ui.tab_panel(commands_tab):
                    self._build_command_panel()

                # Raw data tab
                with ui.tab_panel(raw_tab):
                    self._build_raw_data_panel()

                # Performance tab
                with ui.tab_panel(perf_tab):
                    self._build_performance_panel()

        return self._container

    def _build_log_viewer(self) -> None:
        """Build log viewer section."""
        with ui.column().classes('w-full gap-2'):
            # Filter controls
            with ui.row().classes('items-center gap-2'):
                ui.label('Level:').classes('label')
                level_select = ui.select(
                    options=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                    value=self._filter_level,
                    on_change=lambda e: self._set_filter(e.value)
                ).classes('w-24').props('dense')

                ui.button(
                    'Clear',
                    on_click=self._clear_logs
                ).classes('ml-auto').props('flat dense')

            # Log display
            with ui.scroll_area().classes('w-full h-64 bg-surface') as self._log_container:
                with ui.column().classes('w-full gap-0'):
                    for entry in self._logs[-100:]:  # Show last 100
                        self._render_log_entry(entry)

    def _build_command_panel(self) -> None:
        """Build command input panel."""
        with ui.column().classes('w-full gap-2'):
            ui.label('Manual Command').classes('label')
            ui.label(
                'Send raw LX200 commands to the mount'
            ).classes('text-xs text-secondary')

            with ui.row().classes('w-full gap-2'):
                cmd_input = ui.input(
                    placeholder=':GR#'
                ).classes('flex-grow gui-input mono')

                def send_cmd():
                    if self._on_command and cmd_input.value:
                        self._on_command(cmd_input.value)
                        self._command_history.append(cmd_input.value)
                        cmd_input.value = ''

                ui.button('Send', on_click=send_cmd).props('dense')

            # Command history
            ui.label('History').classes('label mt-2')
            with ui.scroll_area().classes('w-full h-32 bg-surface'):
                with ui.column().classes('w-full gap-0'):
                    for cmd in reversed(self._command_history[-20:]):
                        with ui.row().classes('w-full items-center'):
                            ui.label(cmd).classes('mono text-xs')

    def _build_raw_data_panel(self) -> None:
        """Build raw data display."""
        with ui.column().classes('w-full gap-2'):
            ui.label('State Data').classes('label')

            # JSON-like display of current state
            with ui.scroll_area().classes('w-full h-64 bg-surface'):
                state_display = ui.code(
                    language='json'
                ).classes('w-full')

                def update_state_display():
                    data = {
                        'connected': self._state.connected,
                        'position': {
                            'ra_hours': self._state.ra_hours,
                            'dec_degrees': self._state.dec_degrees,
                            'alt_degrees': self._state.alt_degrees,
                            'az_degrees': self._state.az_degrees,
                        },
                        'tracking': {
                            'enabled': self._state.tracking_enabled,
                            'rate': self._state.tracking_rate,
                            'slewing': self._state.slewing,
                        },
                        'hardware': {
                            'at_park': self._state.at_park,
                            'at_home': self._state.at_home,
                        },
                        'alignment': {
                            'state': self._state.alignment_state.value,
                            'error_arcsec': self._state.alignment_error_arcsec,
                            'determinant': self._state.geometry_determinant,
                        },
                    }
                    import json
                    state_display.content = json.dumps(data, indent=2)

                update_state_display()

                # Refresh button
                ui.button(
                    'Refresh',
                    on_click=update_state_display
                ).classes('mt-2').props('flat dense')

    def _build_performance_panel(self) -> None:
        """Build performance metrics panel."""
        with ui.column().classes('w-full gap-2'):
            ui.label('Performance Metrics').classes('label')

            # Placeholder for performance data
            with ui.grid(columns=2).classes('w-full gap-2'):
                # Update rate
                with ui.column().classes('gap-0'):
                    ui.label('Update Rate').classes('label text-xs')
                    ui.label('-- Hz').classes('mono')

                # Latency
                with ui.column().classes('gap-0'):
                    ui.label('Avg Latency').classes('label text-xs')
                    ui.label('-- ms').classes('mono')

                # Cache hits
                with ui.column().classes('gap-0'):
                    ui.label('Cache Hits').classes('label text-xs')
                    ui.label('--%').classes('mono')

                # Errors
                with ui.column().classes('gap-0'):
                    ui.label('Errors').classes('label text-xs')
                    ui.label('0').classes('mono')

    def _render_log_entry(self, entry: LogEntry) -> None:
        """Render a single log entry."""
        level_colors = {
            'DEBUG': 'text-secondary',
            'INFO': 'text-primary',
            'WARNING': 'text-warning',
            'ERROR': 'text-error',
        }
        color = level_colors.get(entry.level, '')

        with ui.row().classes(f'w-full gap-2 {color}'):
            ui.label(
                entry.timestamp.strftime('%H:%M:%S.%f')[:-3]
            ).classes('mono text-xs w-20')
            ui.label(entry.level).classes('text-xs w-12')
            ui.label(entry.message).classes('text-xs flex-grow')

    def add_log(
        self,
        level: str,
        message: str,
        source: str = "",
    ) -> None:
        """Add a log entry.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR).
            message: Log message.
            source: Optional source identifier.
        """
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=message,
            source=source,
        )
        self._logs.append(entry)

        # Trim if too many
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs:]

    def _set_filter(self, level: str) -> None:
        """Set log filter level."""
        self._filter_level = level

    def _clear_logs(self) -> None:
        """Clear log entries."""
        self._logs.clear()


def diagnostics_panel(
    state: TelescopeState,
    on_command: Optional[Callable[[str], None]] = None,
) -> ui.element:
    """Create diagnostics panel.

    Args:
        state: Telescope state instance.
        on_command: Optional manual command callback.

    Returns:
        Container element.
    """
    panel = DiagnosticsPanel(state, on_command)
    return panel.build()
