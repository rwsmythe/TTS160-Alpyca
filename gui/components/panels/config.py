# -*- coding: utf-8 -*-
"""
Configuration Panel

Settings interface for telescope and GUI configuration.
"""

from typing import Any, Callable, Dict, Optional
from nicegui import ui

from ...state import TelescopeState


def config_panel(
    config: Any,
    on_save: Callable[[Dict[str, Any]], None],
    on_theme_change: Callable[[str], None],
    on_disclosure_change: Callable[[int], None],
    state: Optional[TelescopeState] = None,
) -> ui.element:
    """Configuration settings panel.

    Sections:
    - Connection (serial port)
    - Site (lat/lon/elevation)
    - Alignment monitor settings
    - Camera source selection
    - GUI preferences (theme, disclosure level)

    Args:
        config: Configuration object with settings.
        on_save: Callback to save configuration changes.
        on_theme_change: Callback for theme changes.
        on_disclosure_change: Callback for disclosure level changes.
        state: Optional state for current theme/disclosure.

    Returns:
        Container element with configuration panel.
    """
    # Track pending changes
    pending_changes: Dict[str, Any] = {}

    with ui.card().classes('gui-card w-full') as container:
        ui.label('Configuration').classes('section-header')

        with ui.tabs().classes('w-full') as tabs:
            conn_tab = ui.tab('Connection')
            site_tab = ui.tab('Site')
            align_tab = ui.tab('Alignment')
            gui_tab = ui.tab('GUI')

        with ui.tab_panels(tabs, value=conn_tab).classes('w-full'):
            # Connection settings
            with ui.tab_panel(conn_tab):
                _build_connection_section(config, pending_changes)

            # Site settings
            with ui.tab_panel(site_tab):
                _build_site_section(config, pending_changes)

            # Alignment monitor settings
            with ui.tab_panel(align_tab):
                _build_alignment_section(config, pending_changes)

            # GUI settings
            with ui.tab_panel(gui_tab):
                _build_gui_section(
                    config,
                    state,
                    on_theme_change,
                    on_disclosure_change,
                    pending_changes,
                )

        # Save button
        ui.separator().classes('my-2')

        with ui.row().classes('w-full justify-end gap-2'):
            def save_changes():
                if pending_changes:
                    on_save(pending_changes)
                    pending_changes.clear()
                    ui.notify('Settings saved', type='positive')

            ui.button(
                'Save Changes',
                on_click=save_changes
            ).classes('gui-button')

    return container


def _build_connection_section(
    config: Any,
    pending: Dict[str, Any],
) -> None:
    """Build connection settings section."""
    with ui.column().classes('w-full gap-3'):
        ui.label('Serial Connection').classes('text-sm font-medium')

        # Serial port
        with ui.column().classes('gap-1'):
            ui.label('Serial Port').classes('label')
            port_input = ui.input(
                value=getattr(config, 'serial_port', 'COM1'),
                placeholder='COM1 or /dev/ttyUSB0'
            ).classes('w-full gui-input')

            def on_port_change():
                pending['serial_port'] = port_input.value

            port_input.on('change', on_port_change)

        # Baud rate (usually fixed for LX200)
        with ui.column().classes('gap-1'):
            ui.label('Baud Rate').classes('label')
            baud_select = ui.select(
                options=[9600, 19200, 38400, 57600, 115200],
                value=getattr(config, 'baud_rate', 9600),
            ).classes('w-full')

            def on_baud_change(e):
                pending['baud_rate'] = e.value

            baud_select.on('update:model-value', on_baud_change)


def _build_site_section(
    config: Any,
    pending: Dict[str, Any],
) -> None:
    """Build site location section."""
    with ui.column().classes('w-full gap-3'):
        ui.label('Observation Site').classes('text-sm font-medium')

        # Latitude
        with ui.column().classes('gap-1'):
            ui.label('Latitude (degrees, + North)').classes('label')
            lat_input = ui.number(
                value=getattr(config, 'latitude', 0.0),
                format='%.6f',
                min=-90,
                max=90,
            ).classes('w-full gui-input')

            def on_lat_change():
                pending['latitude'] = lat_input.value

            lat_input.on('change', on_lat_change)

        # Longitude
        with ui.column().classes('gap-1'):
            ui.label('Longitude (degrees, + East)').classes('label')
            lon_input = ui.number(
                value=getattr(config, 'longitude', 0.0),
                format='%.6f',
                min=-180,
                max=180,
            ).classes('w-full gui-input')

            def on_lon_change():
                pending['longitude'] = lon_input.value

            lon_input.on('change', on_lon_change)

        # Elevation
        with ui.column().classes('gap-1'):
            ui.label('Elevation (meters)').classes('label')
            elev_input = ui.number(
                value=getattr(config, 'elevation', 0.0),
                format='%.1f',
            ).classes('w-full gui-input')

            def on_elev_change():
                pending['elevation'] = elev_input.value

            elev_input.on('change', on_elev_change)


def _build_alignment_section(
    config: Any,
    pending: Dict[str, Any],
) -> None:
    """Build alignment monitor settings section."""
    with ui.column().classes('w-full gap-3'):
        ui.label('Alignment Monitor').classes('text-sm font-medium')

        # Enable/disable
        with ui.row().classes('items-center justify-between w-full'):
            ui.label('Enable Monitor')
            enabled = getattr(config, 'alignment_enabled', False)
            enable_switch = ui.switch(value=enabled)

            def on_enable_change(e):
                pending['alignment_enabled'] = e.value

            enable_switch.on('update:model-value', on_enable_change)

        # Camera source
        with ui.column().classes('gap-1'):
            ui.label('Camera Source').classes('label')
            source_select = ui.select(
                options={'alpaca': 'Alpaca', 'zwo': 'ZWO Native'},
                value=getattr(config, 'alignment_camera_source', 'alpaca'),
            ).classes('w-full')

            def on_source_change(e):
                pending['alignment_camera_source'] = e.value

            source_select.on('update:model-value', on_source_change)

        # Camera address (for Alpaca)
        with ui.column().classes('gap-1'):
            ui.label('Camera Address').classes('label')
            addr_input = ui.input(
                value=getattr(config, 'alignment_camera_address', '127.0.0.1'),
            ).classes('w-full gui-input')

            def on_addr_change():
                pending['alignment_camera_address'] = addr_input.value

            addr_input.on('change', on_addr_change)

        # Exposure time
        with ui.column().classes('gap-1'):
            ui.label('Exposure Time (seconds)').classes('label')
            exp_input = ui.number(
                value=getattr(config, 'alignment_exposure_time', 1.0),
                format='%.1f',
                min=0.1,
                max=60,
            ).classes('w-full gui-input')

            def on_exp_change():
                pending['alignment_exposure_time'] = exp_input.value

            exp_input.on('change', on_exp_change)


def _build_gui_section(
    config: Any,
    state: Optional[TelescopeState],
    on_theme_change: Callable[[str], None],
    on_disclosure_change: Callable[[int], None],
    pending: Dict[str, Any],
) -> None:
    """Build GUI preferences section."""
    with ui.column().classes('w-full gap-3'):
        ui.label('Appearance').classes('text-sm font-medium')

        # Theme
        with ui.column().classes('gap-1'):
            ui.label('Theme').classes('label')
            current_theme = state.current_theme if state else 'dark'
            theme_select = ui.select(
                options={
                    'light': 'Light',
                    'dark': 'Dark',
                    'astronomy': 'Astronomy (Red)',
                },
                value=current_theme,
                on_change=lambda e: on_theme_change(e.value)
            ).classes('w-full')

        # Disclosure level
        with ui.column().classes('gap-1'):
            ui.label('Detail Level').classes('label')
            current_level = state.disclosure_level.value if state else 1
            level_select = ui.select(
                options={
                    1: 'Basic',
                    2: 'Expanded',
                    3: 'Advanced',
                },
                value=current_level,
                on_change=lambda e: on_disclosure_change(e.value)
            ).classes('w-full')

        ui.separator().classes('my-2')

        ui.label('Behavior').classes('text-sm font-medium')

        # Auto-open browser
        with ui.row().classes('items-center justify-between w-full'):
            ui.label('Auto-open browser on startup')
            auto_open = getattr(config, 'gui_auto_open_browser', True)
            auto_switch = ui.switch(value=auto_open)

            def on_auto_change(e):
                pending['gui_auto_open_browser'] = e.value

            auto_switch.on('update:model-value', on_auto_change)

        # Refresh interval
        with ui.column().classes('gap-1'):
            ui.label('Status Refresh Interval (seconds)').classes('label')
            refresh_input = ui.number(
                value=getattr(config, 'gui_refresh_interval', 1.0),
                format='%.1f',
                min=0.5,
                max=10,
            ).classes('w-full gui-input')

            def on_refresh_change():
                pending['gui_refresh_interval'] = refresh_input.value

            refresh_input.on('change', on_refresh_change)
