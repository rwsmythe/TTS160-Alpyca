# -*- coding: utf-8 -*-
"""
Main Application Layout

Primary layout structure for the TTS160 GUI with left navigation.
"""

from typing import Any, Callable, Dict, Optional
from nicegui import ui

from ..state import TelescopeState, DisclosureLevel
from ..themes import THEMES, get_theme, generate_css
from ..components.panels import (
    main_status_panel,
    control_panel,
    diagnostics_panel,
    config_panel,
    server_status_panel,
)


# Navigation pages
NAV_PAGES = {
    'server': {
        'label': 'Alpaca Server',
        'icon': 'dns',
    },
    'mount': {
        'label': 'TTS-160 Mount',
        'icon': 'explore',
    },
}


def main_layout(
    state: TelescopeState,
    handlers: Dict[str, Callable],
    config: Any,
    on_theme_change: Callable[[str], None],
    on_disclosure_change: Callable[[int], None],
    on_config_save: Callable[[Dict[str, Any]], None],
) -> None:
    """Main application layout with left navigation.

    Structure:
    ┌──────────────────────────────────────────────────┐
    │ Header: Title, Theme Toggle, Settings            │
    ├─────────┬────────────────────────────────────────┤
    │         │                                        │
    │  Nav    │           Content Area                 │
    │  Menu   │                                        │
    │         │                                        │
    ├─────────┴────────────────────────────────────────┤
    │ Footer: Connection, Disclosure Toggle            │
    └──────────────────────────────────────────────────┘

    Args:
        state: Telescope state instance.
        handlers: Command handler callbacks.
        config: Configuration object.
        on_theme_change: Theme change callback.
        on_disclosure_change: Disclosure level change callback.
        on_config_save: Config save callback.
    """
    # Apply initial theme
    theme = get_theme(state.current_theme)
    ui.add_css(generate_css(theme))

    # Set disclosure level class
    ui.run_javascript(f'''
        document.body.classList.add('disclosure-level-{state.disclosure_level.value}');
    ''')

    # Track current page
    current_page = {'value': 'mount'}  # Default to mount page

    # Create content containers that we'll show/hide
    content_containers = {}

    # Header
    header(state, on_theme_change, on_settings=lambda: show_settings_dialog(
        config, state, on_theme_change, on_disclosure_change, on_config_save
    ))

    # Left drawer for navigation
    with ui.left_drawer(value=True).classes('bg-surface').style(
        'background-color: var(--surface-color); border-right: 1px solid var(--border-color);'
    ) as drawer:
        drawer.props('width=200 bordered')

        ui.label('Navigation').classes('text-lg font-semibold p-4')

        with ui.column().classes('w-full'):
            nav_buttons = {}

            for page_id, page_info in NAV_PAGES.items():
                btn = ui.button(
                    page_info['label'],
                    icon=page_info['icon'],
                    on_click=lambda pid=page_id: switch_page(pid)
                ).classes('w-full justify-start').props('flat align=left')

                nav_buttons[page_id] = btn

    def switch_page(page_id: str):
        """Switch to a different page."""
        current_page['value'] = page_id

        # Update button styles
        for pid, btn in nav_buttons.items():
            if pid == page_id:
                btn.props('color=primary')
            else:
                btn.props(remove='color')

        # Show/hide content containers
        for pid, container in content_containers.items():
            if pid == page_id:
                container.set_visibility(True)
            else:
                container.set_visibility(False)

    # Main content area
    with ui.column().classes('w-full p-4'):
        # Server page content
        with ui.column().classes('w-full').bind_visibility_from(
            current_page, 'value', lambda v: v == 'server'
        ) as server_container:
            content_containers['server'] = server_container
            server_status_panel(state, config)

        # Mount page content
        with ui.column().classes('w-full').bind_visibility_from(
            current_page, 'value', lambda v: v == 'mount'
        ) as mount_container:
            content_containers['mount'] = mount_container

            # Two-column layout for mount
            with ui.row().classes('w-full gap-4'):
                # Status panel (left, 60%)
                with ui.column().classes('w-3/5'):
                    main_status_panel(state)

                # Control panel (right, 40%)
                with ui.column().classes('w-2/5'):
                    control_panel(state, handlers)

            # Diagnostics panel (Layer 3)
            with ui.column().classes('w-full mt-4'):
                diagnostics_panel(state, handlers.get('send_command'))

    # Footer
    footer(state, on_disclosure_change)

    # Set initial page styling
    switch_page('mount')


def header(
    state: TelescopeState,
    on_theme_change: Callable[[str], None],
    on_settings: Callable[[], None],
) -> ui.element:
    """Application header.

    Contains:
    - Menu toggle button
    - App title/logo
    - Theme selector (Light/Dark/Astronomy)
    - Settings button

    Args:
        state: Telescope state instance.
        on_theme_change: Theme change callback.
        on_settings: Settings button callback.

    Returns:
        Header element.
    """
    with ui.header().classes('gui-header') as hdr:
        # Left: Menu toggle and Title
        with ui.row().classes('items-center gap-2'):
            ui.button(icon='menu', on_click=lambda: ui.left_drawer.toggle()).props('flat round')
            ui.icon('rocket_launch').classes('text-2xl')
            ui.label('TTS-160 Telescope Control').classes('text-xl font-semibold')

        # Right: Controls
        with ui.row().classes('items-center gap-4'):
            # Theme selector
            theme_select = ui.select(
                options={
                    'light': 'Light',
                    'dark': 'Dark',
                    'astronomy': 'Astronomy',
                },
                value=state.current_theme,
                on_change=lambda e: on_theme_change(e.value)
            ).classes('w-32')
            theme_select.props('dense outlined')

            # Settings button
            ui.button(
                icon='settings',
                on_click=on_settings
            ).props('flat round')

    return hdr


def footer(
    state: TelescopeState,
    on_disclosure_change: Callable[[int], None],
) -> ui.element:
    """Application footer.

    Contains:
    - Connection status summary
    - Disclosure level toggle (1/2/3)
    - Version info

    Args:
        state: Telescope state instance.
        on_disclosure_change: Disclosure level change callback.

    Returns:
        Footer element.
    """
    with ui.footer().classes('gui-footer') as ftr:
        # Left: Connection status
        with ui.row().classes('items-center gap-2'):
            conn_ind = ui.element('span').classes('indicator')
            conn_label = ui.label()

            def update_connection():
                conn_ind.classes(
                    remove='indicator-ok indicator-error indicator-inactive'
                )
                if state.connected:
                    conn_ind.classes(add='indicator-ok')
                    conn_label.text = 'Connected'
                elif state.connection_error:
                    conn_ind.classes(add='indicator-error')
                    conn_label.text = 'Error'
                else:
                    conn_ind.classes(add='indicator-inactive')
                    conn_label.text = 'Disconnected'

            update_connection()

            def on_conn_change(field, value):
                if field in ('connected', 'connection_error'):
                    update_connection()

            state.add_listener(on_conn_change)

            # Serial port
            port_label = ui.label().classes('text-xs text-secondary')
            port_label.bind_text_from(state, 'serial_port')

        # Center: Disclosure level
        with ui.row().classes('items-center gap-2'):
            ui.label('Detail:').classes('text-sm')

            def make_level_btn(level: int) -> ui.button:
                level_names = {1: 'Basic', 2: 'Expanded', 3: 'Advanced'}

                def set_level():
                    on_disclosure_change(level)
                    # Update button states
                    update_level_buttons()

                btn = ui.button(
                    level_names[level],
                    on_click=set_level
                ).props('flat dense')

                return btn

            level_btns = [make_level_btn(i) for i in [1, 2, 3]]

            def update_level_buttons():
                current = state.disclosure_level.value
                for i, btn in enumerate(level_btns, 1):
                    if i == current:
                        btn.props('color=primary')
                    else:
                        btn.props(remove='color')

            update_level_buttons()

            def on_level_change(field, value):
                if field == 'disclosure_level':
                    update_level_buttons()

            state.add_listener(on_level_change)

        # Right: Peripheral status indicators
        with ui.row().classes('items-center gap-4'):
            # GPS indicator with tooltip
            with ui.row().classes('items-center gap-1') as gps_container:
                gps_ind = ui.element('span').classes('indicator')
                ui.label('GPS').classes('text-xs')

                # Tooltip element for GPS coordinates
                gps_tooltip = ui.tooltip('')

                def update_gps():
                    gps_ind.classes(
                        remove='indicator-ok indicator-warning indicator-error indicator-inactive'
                    )
                    if state.gps_fix:
                        # Green: connected with fix
                        gps_ind.classes(add='indicator-ok')
                        # Update tooltip with coordinates
                        lat = state.gps_latitude
                        lon = state.gps_longitude
                        alt = state.gps_altitude
                        sats = state.gps_satellites
                        lat_dir = 'N' if lat >= 0 else 'S'
                        lon_dir = 'E' if lon >= 0 else 'W'
                        gps_tooltip.text = (
                            f"{abs(lat):.6f}° {lat_dir}, {abs(lon):.6f}° {lon_dir}\n"
                            f"Alt: {alt:.1f}m, Sats: {sats}"
                        )
                    elif state.gps_enabled:
                        # Yellow: connected without fix
                        gps_ind.classes(add='indicator-warning')
                        gps_tooltip.text = f"Acquiring fix... ({state.gps_satellites} satellites)"
                    else:
                        # Red: not connected
                        gps_ind.classes(add='indicator-error')
                        gps_tooltip.text = "GPS not connected"

                update_gps()

                def on_gps_change(field, value):
                    if field in ('gps_enabled', 'gps_fix', 'gps_latitude',
                                 'gps_longitude', 'gps_altitude', 'gps_satellites'):
                        update_gps()

                state.add_listener(on_gps_change)

            # Camera indicator (alignment monitor camera)
            with ui.row().classes('items-center gap-1'):
                cam_ind = ui.element('span').classes('indicator')
                ui.label('Camera').classes('text-xs')

                def update_camera():
                    from ..state import AlignmentState
                    cam_ind.classes(
                        remove='indicator-ok indicator-error indicator-inactive'
                    )
                    # Camera is connected if alignment state is beyond DISCONNECTED
                    connected_states = [
                        AlignmentState.CONNECTED,
                        AlignmentState.CAPTURING,
                        AlignmentState.SOLVING,
                        AlignmentState.MONITORING,
                    ]
                    if state.alignment_state in connected_states:
                        # Green: connected
                        cam_ind.classes(add='indicator-ok')
                    else:
                        # Red: not connected
                        cam_ind.classes(add='indicator-error')

                update_camera()

                def on_camera_change(field, value):
                    if field == 'alignment_state':
                        update_camera()

                state.add_listener(on_camera_change)

            # Version
            ui.label('v0.1.0').classes('text-xs text-secondary')

    return ftr


def show_settings_dialog(
    config: Any,
    state: TelescopeState,
    on_theme_change: Callable[[str], None],
    on_disclosure_change: Callable[[int], None],
    on_config_save: Callable[[Dict[str, Any]], None],
) -> None:
    """Show settings dialog.

    Args:
        config: Configuration object.
        state: Telescope state.
        on_theme_change: Theme change callback.
        on_disclosure_change: Disclosure change callback.
        on_config_save: Config save callback.
    """
    with ui.dialog().props('persistent maximized=false') as dialog:
        with ui.card().classes('w-full').style('max-width: 700px; max-height: 85vh;'):
            with ui.row().classes('w-full justify-between items-center mb-4'):
                ui.label('Settings').classes('text-xl font-semibold')
                ui.button(icon='close', on_click=dialog.close).props('flat round dense')

            with ui.scroll_area().classes('w-full').style('max-height: calc(85vh - 120px);'):
                config_panel(
                    config=config,
                    on_save=on_config_save,
                    on_theme_change=on_theme_change,
                    on_disclosure_change=on_disclosure_change,
                    state=state,
                )

            with ui.row().classes('w-full justify-end mt-4 pt-2').style(
                'border-top: 1px solid var(--border-color);'
            ):
                ui.button('Close', on_click=dialog.close).props('flat')

    dialog.open()


def two_column_layout(
    left_content: Callable[[], None],
    right_content: Callable[[], None],
    left_width: str = "60%",
    right_width: str = "40%",
) -> ui.element:
    """Two-column layout helper.

    Args:
        left_content: Function to build left column content.
        right_content: Function to build right column content.
        left_width: CSS width for left column.
        right_width: CSS width for right column.

    Returns:
        Row container element.
    """
    with ui.row().classes('w-full gap-4') as container:
        with ui.column().style(f'width: {left_width}'):
            left_content()

        with ui.column().style(f'width: {right_width}'):
            right_content()

    return container
