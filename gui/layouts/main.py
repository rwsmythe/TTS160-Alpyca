# -*- coding: utf-8 -*-
"""
Main Application Layout

Primary layout structure for the TTS160 GUI with dashboard and detail navigation.
"""

from typing import Any, Callable, Dict, Optional
from nicegui import ui

from ..state import TelescopeState, DisclosureLevel, AlignmentState
from ..themes import THEMES, get_theme, generate_css
from ..components.panels import (
    main_status_panel,
    control_panel,
    diagnostics_panel,
    config_panel,
    server_status_panel,
    dashboard,
    position_panel,
    hardware_panel,
    alignment_panel,
)
from ..components.navigation import segmented_nav, NAV_GROUPS


# Top-level navigation pages
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
    """Main application layout with dashboard and detail navigation.

    Structure:
    ┌──────────────────────────────────────────────────┐
    │ Header: Title, Theme Toggle, Settings            │
    ├─────────┬────────────────────────────────────────┤
    │         │ Dashboard (compact summary)            │
    │  Nav    ├────────────────────────────────────────┤
    │  Menu   │ [Controls][Position][Hardware][...]    │
    │         ├────────────────────────────────────────┤
    │         │ Detail Panel (selected group)          │
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

    # Track current page and group
    current_page = {'value': 'mount'}
    current_group = {'value': 'controls'}

    # Create content containers
    content_containers = {}
    detail_containers = {}

    # Store drawer reference for toggle
    drawer_ref = {'drawer': None}

    def toggle_drawer():
        if drawer_ref['drawer']:
            drawer_ref['drawer'].toggle()

    # Header
    header(state, on_theme_change,
           on_settings=lambda: show_settings_dialog(
               config, state, on_theme_change, on_disclosure_change, on_config_save
           ),
           on_toggle_drawer=toggle_drawer)

    # Left drawer for top-level navigation
    with ui.left_drawer(value=True).classes('bg-surface').style(
        'background-color: var(--surface-color); border-right: 1px solid var(--border-color);'
    ) as drawer:
        drawer_ref['drawer'] = drawer
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

    def switch_detail_group(group_id: str):
        """Switch to a different detail group."""
        current_group['value'] = group_id

        # Show/hide detail containers
        for gid, container in detail_containers.items():
            if gid == group_id:
                container.set_visibility(True)
                container.classes(add='detail-panel-enter')
            else:
                container.set_visibility(False)
                container.classes(remove='detail-panel-enter')

    # Main content area
    with ui.column().classes('w-full p-4'):
        # Server page content
        with ui.column().classes('w-full').bind_visibility_from(
            current_page, 'value', lambda v: v == 'server'
        ) as server_container:
            content_containers['server'] = server_container
            server_status_panel(state, config)

        # Mount page content with new layout
        with ui.column().classes('w-full').bind_visibility_from(
            current_page, 'value', lambda v: v == 'mount'
        ) as mount_container:
            content_containers['mount'] = mount_container

            # Dashboard (always visible, compact summary)
            dashboard(state)

            # Segmented navigation for detail groups
            segmented_nav(state, on_select=switch_detail_group)

            # Detail panel container
            with ui.column().classes('detail-panel w-full'):
                # Controls panel
                with ui.column().classes('w-full').bind_visibility_from(
                    current_group, 'value', lambda v: v == 'controls'
                ) as controls_container:
                    detail_containers['controls'] = controls_container
                    control_panel(state, handlers, config)

                # Position panel
                with ui.column().classes('w-full').bind_visibility_from(
                    current_group, 'value', lambda v: v == 'position'
                ) as position_container:
                    detail_containers['position'] = position_container
                    position_panel(state)

                # Hardware panel
                with ui.column().classes('w-full').bind_visibility_from(
                    current_group, 'value', lambda v: v == 'hardware'
                ) as hardware_container:
                    detail_containers['hardware'] = hardware_container
                    hardware_panel(state)

                # Alignment panel
                with ui.column().classes('w-full').bind_visibility_from(
                    current_group, 'value', lambda v: v == 'alignment'
                ) as alignment_container:
                    detail_containers['alignment'] = alignment_container
                    alignment_panel(state, handlers)

                # Diagnostics panel
                with ui.column().classes('w-full').bind_visibility_from(
                    current_group, 'value', lambda v: v == 'diagnostics'
                ) as diag_container:
                    detail_containers['diagnostics'] = diag_container
                    diagnostics_panel(state, handlers.get('send_command'))

    # Footer
    footer(state, on_disclosure_change)

    # Set initial page styling
    switch_page('mount')


def header(
    state: TelescopeState,
    on_theme_change: Callable[[str], None],
    on_settings: Callable[[], None],
    on_toggle_drawer: Callable[[], None] = None,
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
        on_toggle_drawer: Callback to toggle navigation drawer.

    Returns:
        Header element.
    """
    # Pre-create dialogs so they exist before menu items are clicked
    restart_dialog = ui.dialog()
    stop_dialog = ui.dialog()

    def _do_restart():
        """Perform shutdown then restart via exec."""
        import sys
        import os
        restart_dialog.close()
        ui.notify('Restarting server...', type='warning')

        def perform_restart():
            python = sys.executable
            args = sys.argv[:]
            if sys.platform == 'win32':
                import subprocess
                subprocess.Popen([python] + args,
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                os._exit(0)
            else:
                os.execv(python, [python] + args)

        ui.timer(0.5, perform_restart, once=True)

    def _do_stop():
        """Perform graceful shutdown with forced termination fallback."""
        import os
        import threading
        stop_dialog.close()
        ui.notify('Stopping server (graceful shutdown)...', type='warning')

        def force_exit():
            import time
            time.sleep(5)
            os._exit(0)

        force_thread = threading.Thread(target=force_exit, daemon=True)
        force_thread.start()

        def graceful_shutdown():
            try:
                from nicegui import app
                app.shutdown()
            except Exception:
                pass
            os._exit(0)

        ui.timer(0.3, graceful_shutdown, once=True)

    # Build restart dialog content
    with restart_dialog, ui.card():
        ui.label('Restart Server?').classes('text-lg font-semibold')
        ui.label(
            'The server will shutdown and restart automatically.'
        ).classes('text-sm text-secondary')
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=restart_dialog.close).props('flat')
            ui.button('Restart', on_click=_do_restart, color='warning')

    # Build stop dialog content
    with stop_dialog, ui.card():
        ui.label('Stop Server?').classes('text-lg font-semibold')
        ui.label(
            'This will terminate the server. A graceful shutdown will be '
            'attempted first, with forced termination after 5 seconds.'
        ).classes('text-sm text-secondary')
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=stop_dialog.close).props('flat')
            ui.button('Stop Server', on_click=_do_stop, color='negative')

    with ui.header().classes('gui-header') as hdr:
        # Left: Menu button and Title
        with ui.row().classes('items-center gap-2'):
            # Hamburger menu with options
            with ui.button(icon='menu').props('flat round') as menu_btn:
                with ui.menu() as menu:
                    ui.menu_item(
                        'Toggle Navigation',
                        on_click=on_toggle_drawer if on_toggle_drawer else lambda: None
                    ).props('icon=view_sidebar')

                    ui.separator()

                    ui.menu_item(
                        'Restart Server',
                        on_click=restart_dialog.open
                    ).props('icon=refresh')

                    ui.menu_item(
                        'Stop Server',
                        on_click=stop_dialog.open
                    ).classes('text-negative').props('icon=power_settings_new')

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
