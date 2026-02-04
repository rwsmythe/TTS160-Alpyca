# -*- coding: utf-8 -*-
"""
Connection Status Component

Shows connection health, serial port info, and communication status.
"""

from datetime import datetime
from nicegui import ui

from ...state import TelescopeState


def connection_status(state: TelescopeState) -> ui.element:
    """Display connection health.

    Shows:
    - Connected/disconnected indicator
    - Serial port info
    - Last communication timestamp
    - Error message (if any)

    Args:
        state: Telescope state instance.

    Returns:
        Container element with connection display.
    """
    with ui.card().classes('gui-card w-full') as container:
        ui.label('Connection').classes('section-header')

        with ui.column().classes('gap-2'):
            # Main status row
            with ui.row().classes('items-center gap-3'):
                # Status indicator
                ind = ui.element('span').classes('indicator')

                # Status text
                status_label = ui.label()

                def update_connection():
                    ind.classes(
                        remove='indicator-ok indicator-error indicator-inactive'
                    )

                    if state.connected:
                        ind.classes(add='indicator-ok')
                        status_label.text = 'Connected'
                    elif state.connection_error:
                        ind.classes(add='indicator-error')
                        status_label.text = 'Error'
                    else:
                        ind.classes(add='indicator-inactive')
                        status_label.text = 'Disconnected'

                update_connection()

                def on_change(field, value):
                    if field in ('connected', 'connection_error'):
                        update_connection()

                state.add_listener(on_change)

            # Serial port (Layer 2 detail)
            with ui.row().classes('items-center gap-2 disclosure-2'):
                ui.label('Port:').classes('label')
                port_label = ui.label().classes('mono text-sm')
                port_label.bind_text_from(
                    state, 'serial_port',
                    lambda p: p if p else 'Not set'
                )

            # Last communication (Layer 2 detail)
            with ui.row().classes('items-center gap-2 disclosure-2'):
                ui.label('Last comm:').classes('label')
                comm_label = ui.label().classes('mono text-sm')

                def format_last_comm(dt):
                    if dt is None:
                        return 'Never'
                    age = (datetime.now() - dt).total_seconds()
                    if age < 60:
                        return f'{int(age)}s ago'
                    elif age < 3600:
                        return f'{int(age / 60)}m ago'
                    return dt.strftime('%H:%M:%S')

                comm_label.bind_text_from(
                    state, 'last_communication',
                    format_last_comm
                )

            # Error message (only shown when error exists)
            error_container = ui.column().classes('w-full')
            with error_container:
                error_row = ui.row().classes('items-start gap-2 text-red-500')
                with error_row:
                    ui.icon('error').classes('text-lg')
                    error_label = ui.label().classes('text-sm')
                    error_label.bind_text_from(state, 'connection_error')

            def update_error_visibility():
                if state.connection_error:
                    error_container.set_visibility(True)
                else:
                    error_container.set_visibility(False)

            update_error_visibility()

            def on_error_change(field, value):
                if field == 'connection_error':
                    update_error_visibility()

            state.add_listener(on_error_change)

    return container


def connection_indicator_compact(state: TelescopeState) -> ui.element:
    """Compact connection indicator for footer.

    Args:
        state: Telescope state instance.

    Returns:
        Container element.
    """
    with ui.row().classes('items-center gap-2') as container:
        ind = ui.element('span').classes('indicator')
        label = ui.label()

        def update():
            ind.classes(
                remove='indicator-ok indicator-error indicator-inactive'
            )

            if state.connected:
                ind.classes(add='indicator-ok')
                label.text = 'Connected'
            elif state.connection_error:
                ind.classes(add='indicator-error')
                label.text = 'Error'
            else:
                ind.classes(add='indicator-inactive')
                label.text = 'Disconnected'

        update()

        def on_change(field, value):
            if field in ('connected', 'connection_error'):
                update()

        state.add_listener(on_change)

    return container


def data_staleness_indicator(state: TelescopeState) -> ui.element:
    """Show indicator when data becomes stale.

    Args:
        state: Telescope state instance.

    Returns:
        Container element (hidden when data is fresh).
    """
    with ui.row().classes('items-center gap-2') as container:
        stale_row = ui.row().classes('items-center gap-1 text-warning')
        with stale_row:
            ui.icon('warning').classes('text-sm')
            ui.label('Data may be stale').classes('text-xs')

        def update_staleness():
            if state.is_stale:
                stale_row.set_visibility(True)
            else:
                stale_row.set_visibility(False)

        update_staleness()

        def on_change(field, value):
            if field == 'is_stale':
                update_staleness()

        state.add_listener(on_change)

    return container
