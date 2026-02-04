# -*- coding: utf-8 -*-
"""
Main Application Layout

Primary layout structure for the TTS160 GUI.
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
)


def main_layout(
    state: TelescopeState,
    handlers: Dict[str, Callable],
    config: Any,
    on_theme_change: Callable[[str], None],
    on_disclosure_change: Callable[[int], None],
    on_config_save: Callable[[Dict[str, Any]], None],
) -> None:
    """Main application layout.

    Structure:
    ┌─────────────────────────────────────────┐
    │ Header: Title, Theme Toggle, Settings   │
    ├────────────────────┬────────────────────┤
    │                    │                    │
    │   Status Panel     │   Control Panel    │
    │   (Left, 60%)      │   (Right, 40%)     │
    │                    │                    │
    ├────────────────────┴────────────────────┤
    │ Footer: Connection, Disclosure Toggle   │
    └─────────────────────────────────────────┘

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

    with ui.column().classes('w-full min-h-screen'):
        # Header
        header(state, on_theme_change, on_settings=lambda: show_settings_dialog(
            config, state, on_theme_change, on_disclosure_change, on_config_save
        ))

        # Main content area
        with ui.row().classes('flex-grow w-full p-4 gap-4'):
            # Status panel (left, 60%)
            with ui.column().classes('w-3/5'):
                main_status_panel(state)

            # Control panel (right, 40%)
            with ui.column().classes('w-2/5'):
                control_panel(state, handlers)

        # Diagnostics panel (Layer 3)
        with ui.column().classes('w-full px-4'):
            diagnostics_panel(state, handlers.get('send_command'))

        # Footer
        footer(state, on_disclosure_change)


def header(
    state: TelescopeState,
    on_theme_change: Callable[[str], None],
    on_settings: Callable[[], None],
) -> ui.element:
    """Application header.

    Contains:
    - App title/logo
    - Theme selector (Light/Dark/Astronomy)
    - Settings button
    - Notification area

    Args:
        state: Telescope state instance.
        on_theme_change: Theme change callback.
        on_settings: Settings button callback.

    Returns:
        Header element.
    """
    with ui.header().classes('gui-header') as hdr:
        # Left: Title
        with ui.row().classes('items-center gap-2'):
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

        # Right: Version
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
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
        ui.label('Settings').classes('text-xl font-semibold mb-4')

        config_panel(
            config=config,
            on_save=on_config_save,
            on_theme_change=on_theme_change,
            on_disclosure_change=on_disclosure_change,
            state=state,
        )

        with ui.row().classes('w-full justify-end mt-4'):
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
