# -*- coding: utf-8 -*-
"""
Control Panel

Combines control components for telescope operations.
"""

from typing import Any, Callable, Dict
from nicegui import ui

from ...state import TelescopeState
from ..controls import (
    slew_controls,
    tracking_controls,
    park_controls,
    alignment_controls,
)


def _connection_control(
    state: TelescopeState,
    on_connect: Callable,
    on_disconnect: Callable,
    config: Any = None,
) -> ui.element:
    """Connection control card with connect/disconnect button.

    Args:
        state: Telescope state instance.
        on_connect: Connect callback.
        on_disconnect: Disconnect callback.
        config: Optional config object for connection options.

    Returns:
        Container element.
    """
    with ui.card().classes('gui-card w-full') as container:
        ui.label('Mount Connection').classes('section-header')

        with ui.row().classes('items-center justify-between w-full'):
            # Status indicator and text
            with ui.row().classes('items-center gap-2'):
                conn_ind = ui.element('span').classes('indicator')
                conn_label = ui.label()

            # Connect/Disconnect button
            conn_btn = ui.button().classes('w-32')

            def update_connection():
                conn_ind.classes(
                    remove='indicator-ok indicator-error indicator-inactive'
                )

                if state.connected:
                    conn_ind.classes(add='indicator-ok')
                    conn_label.text = 'Connected'
                    conn_btn.text = 'Disconnect'
                    conn_btn.props('color=negative')
                    conn_btn._props['icon'] = 'link_off'
                elif state.connection_error:
                    conn_ind.classes(add='indicator-error')
                    conn_label.text = 'Error'
                    conn_btn.text = 'Retry'
                    conn_btn.props(remove='color')
                    conn_btn.props('color=warning')
                    conn_btn._props['icon'] = 'refresh'
                else:
                    conn_ind.classes(add='indicator-inactive')
                    conn_label.text = 'Disconnected'
                    conn_btn.text = 'Connect'
                    conn_btn.props(remove='color')
                    conn_btn.props('color=primary')
                    conn_btn._props['icon'] = 'link'

            def on_btn_click():
                if state.connected:
                    on_disconnect()
                else:
                    on_connect()

            conn_btn.on('click', on_btn_click)
            update_connection()

            def on_change(field, value):
                if field in ('connected', 'connection_error'):
                    update_connection()

            state.add_listener(on_change)

        # Serial port info
        with ui.row().classes('items-center gap-2'):
            ui.label('Port:').classes('label text-sm')
            port_label = ui.label().classes('mono text-sm')
            port_label.bind_text_from(
                state, 'serial_port',
                lambda p: p if p else 'Not configured'
            )

        # Connection options (only show if config available)
        if config is not None:
            ui.separator().classes('my-1')

            with ui.column().classes('w-full gap-1'):
                # Sync time on connect checkbox
                sync_time_value = getattr(config, 'sync_time_on_connect', True)
                sync_time_cb = ui.checkbox(
                    'Sync time on connect',
                    value=sync_time_value,
                ).classes('text-sm')

                def on_sync_time_change(e):
                    setattr(config, 'sync_time_on_connect', e.value)

                sync_time_cb.on('update:model-value', on_sync_time_change)

                # GPS push on connect checkbox
                gps_push_value = getattr(config, 'gps_push_on_connect', False)
                gps_push_cb = ui.checkbox(
                    'Push GPS location on connect',
                    value=gps_push_value,
                ).classes('text-sm')

                def on_gps_push_change(e):
                    setattr(config, 'gps_push_on_connect', e.value)

                gps_push_cb.on('update:model-value', on_gps_push_change)

    return container


def control_panel(
    state: TelescopeState,
    handlers: Dict[str, Callable],
    config: Any = None,
) -> ui.element:
    """Main control panel.

    Combines all control components:
    - Connection controls (Layer 1)
    - Slew controls (Layer 1)
    - Tracking controls (Layer 1)
    - Park controls (Layer 1)
    - Alignment controls (Layer 2)

    Args:
        state: Telescope state instance.
        handlers: Dict of callback handlers:
            - connect: () -> None
            - disconnect: () -> None
            - slew_start: (direction: str) -> None
            - slew_stop: () -> None
            - goto: (ra: float, dec: float) -> None
            - speed_change: (speed: int) -> None
            - tracking_toggle: (enabled: bool) -> None
            - tracking_rate: (rate: str) -> None
            - park: () -> None
            - unpark: () -> None
            - set_park: () -> None
            - home: () -> None
            - sync: (ra: float, dec: float) -> None
            - measure: () -> None
            - enable_monitor: (enabled: bool) -> None
        config: Optional config object for connection options.

    Returns:
        Container element with control panel.
    """
    # Extract handlers with defaults
    def noop(*args, **kwargs):
        pass

    connect = handlers.get('connect', noop)
    disconnect = handlers.get('disconnect', noop)
    slew_start = handlers.get('slew_start', noop)
    slew_stop = handlers.get('slew_stop', noop)
    goto = handlers.get('goto', noop)
    speed_change = handlers.get('speed_change', noop)
    tracking_toggle = handlers.get('tracking_toggle', noop)
    tracking_rate = handlers.get('tracking_rate', noop)
    park = handlers.get('park', noop)
    unpark = handlers.get('unpark', noop)
    set_park = handlers.get('set_park', noop)
    home = handlers.get('home', noop)
    sync = handlers.get('sync', noop)
    measure = handlers.get('measure', noop)
    enable_monitor = handlers.get('enable_monitor', None)

    with ui.column().classes('w-full gap-4') as container:
        # Layer 1: Primary Controls
        # Connection control - fundamental action at top
        _connection_control(state, connect, disconnect, config)

        # Slew controls - most frequently used
        slew_controls(
            state=state,
            on_slew_start=slew_start,
            on_slew_stop=slew_stop,
            on_goto=goto,
            on_speed_change=speed_change,
        )

        # Tracking controls
        tracking_controls(
            state=state,
            on_toggle=tracking_toggle,
            on_rate_change=tracking_rate,
        )

        # Park controls
        park_controls(
            state=state,
            on_park=park,
            on_unpark=unpark,
            on_set_park=set_park,
            on_home=home,
        )

        # Layer 2: Alignment controls
        alignment_controls(
            state=state,
            on_sync=sync,
            on_measure=measure,
            on_enable_monitor=enable_monitor,
        )

    return container


def minimal_control_panel(
    state: TelescopeState,
    handlers: Dict[str, Callable],
) -> ui.element:
    """Minimal control panel with essential controls only.

    For compact layouts or basic operation mode.

    Args:
        state: Telescope state instance.
        handlers: Callback handlers dict.

    Returns:
        Container element.
    """
    slew_start = handlers.get('slew_start', lambda d: None)
    slew_stop = handlers.get('slew_stop', lambda: None)
    tracking_toggle = handlers.get('tracking_toggle', lambda e: None)
    park = handlers.get('park', lambda: None)
    unpark = handlers.get('unpark', lambda: None)

    with ui.card().classes('gui-card w-full') as container:
        with ui.column().classes('gap-3'):
            # Simple D-pad
            from ..controls import directional_pad
            directional_pad(slew_start, slew_stop, size='normal')

            # Tracking toggle
            with ui.row().classes('items-center justify-between w-full'):
                ui.label('Tracking')
                ui.switch(
                    value=state.tracking_enabled,
                    on_change=lambda e: tracking_toggle(e.value)
                )

            # Park button
            park_btn = ui.button().classes('w-full')

            def update_park():
                park_btn._event_listeners.clear()
                if state.at_park:
                    park_btn.text = 'Unpark'
                    park_btn.on('click', unpark)
                else:
                    park_btn.text = 'Park'
                    park_btn.on('click', park)

            update_park()

            def on_change(field, value):
                if field == 'at_park':
                    update_park()

            state.add_listener(on_change)

    return container
