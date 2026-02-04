# -*- coding: utf-8 -*-
"""
Tracking Controls Component

Tracking enable/disable and rate selection.
"""

from typing import Callable
from nicegui import ui

from ...state import TelescopeState


# Tracking rate options
TRACKING_RATES = [
    ('Sidereal', 'sidereal'),
    ('Lunar', 'lunar'),
    ('Solar', 'solar'),
    ('King', 'king'),
]


def tracking_controls(
    state: TelescopeState,
    on_toggle: Callable[[bool], None],
    on_rate_change: Callable[[str], None],
) -> ui.element:
    """Tracking enable/disable and rate selection.

    Shows:
    - Track On/Off toggle switch
    - Rate selector (Sidereal, Lunar, Solar, King)

    Args:
        state: Telescope state instance.
        on_toggle: Callback with new tracking state (True/False).
        on_rate_change: Callback with rate name.

    Returns:
        Container element with tracking controls.
    """
    with ui.card().classes('gui-card w-full') as container:
        ui.label('Tracking').classes('section-header')

        with ui.column().classes('gap-3'):
            # Main toggle row
            with ui.row().classes('items-center justify-between w-full'):
                ui.label('Tracking').classes('text-base')

                # Toggle switch
                tracking_switch = ui.switch(
                    value=state.tracking_enabled,
                    on_change=lambda e: on_toggle(e.value)
                )

                # Bind to state for updates
                def update_switch():
                    tracking_switch.value = state.tracking_enabled

                def on_state_change(field, value):
                    if field == 'tracking_enabled':
                        update_switch()

                state.add_listener(on_state_change)

            # Rate selector (Layer 2)
            with ui.column().classes('gap-2 disclosure-2'):
                ui.label('Tracking Rate').classes('label')

                rate_select = ui.select(
                    options={rate: name for name, rate in TRACKING_RATES},
                    value=state.tracking_rate,
                    on_change=lambda e: on_rate_change(e.value)
                ).classes('w-full')
                rate_select.props('dense outlined')

                # Bind to state
                def update_rate():
                    rate_select.value = state.tracking_rate

                def on_rate_state_change(field, value):
                    if field == 'tracking_rate':
                        update_rate()

                state.add_listener(on_rate_state_change)

    return container


def tracking_toggle(
    state: TelescopeState,
    on_toggle: Callable[[bool], None],
    compact: bool = False,
) -> ui.element:
    """Standalone tracking toggle.

    Args:
        state: Telescope state instance.
        on_toggle: Callback with new state.
        compact: Use compact layout.

    Returns:
        Container element.
    """
    with ui.row().classes('items-center gap-2') as container:
        if not compact:
            ui.label('Tracking').classes('text-sm')

        switch = ui.switch(
            value=state.tracking_enabled,
            on_change=lambda e: on_toggle(e.value)
        )

        if compact:
            switch.props('dense')

        def update():
            switch.value = state.tracking_enabled

        def on_change(field, value):
            if field == 'tracking_enabled':
                update()

        state.add_listener(on_change)

    return container


def rate_selector(
    state: TelescopeState,
    on_rate_change: Callable[[str], None],
) -> ui.element:
    """Standalone rate selector.

    Args:
        state: Telescope state instance.
        on_rate_change: Callback with rate name.

    Returns:
        Select element.
    """
    select = ui.select(
        options={rate: name for name, rate in TRACKING_RATES},
        value=state.tracking_rate,
        on_change=lambda e: on_rate_change(e.value)
    ).classes('w-32')
    select.props('dense outlined')

    def update():
        select.value = state.tracking_rate

    def on_change(field, value):
        if field == 'tracking_rate':
            update()

    state.add_listener(on_change)

    return select
