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


def control_panel(
    state: TelescopeState,
    handlers: Dict[str, Callable],
) -> ui.element:
    """Main control panel.

    Combines all control components:
    - Slew controls (Layer 1)
    - Tracking controls (Layer 1)
    - Park controls (Layer 1)
    - Alignment controls (Layer 2)

    Args:
        state: Telescope state instance.
        handlers: Dict of callback handlers:
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

    Returns:
        Container element with control panel.
    """
    # Extract handlers with defaults
    def noop(*args, **kwargs):
        pass

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
