# -*- coding: utf-8 -*-
"""
Tracking Status Display Component

Shows tracking state, mode, and slewing status.
"""

from nicegui import ui

from ..common import indicator
from ...state import TelescopeState


# Tracking rate display names
TRACKING_RATES = {
    'sidereal': 'Sidereal',
    'lunar': 'Lunar',
    'solar': 'Solar',
    'king': 'King',
    'custom': 'Custom',
}


def tracking_display(state: TelescopeState) -> ui.element:
    """Display tracking status.

    Shows:
    - Tracking enabled/disabled indicator (with pulse when active)
    - Current tracking rate
    - Slewing indicator (when active, overrides tracking display)

    Args:
        state: Telescope state instance.

    Returns:
        Container element with tracking display.
    """
    with ui.card().classes('gui-card w-full') as container:
        ui.label('Tracking').classes('section-header')

        with ui.column().classes('gap-2'):
            # Main status row
            with ui.row().classes('items-center gap-3'):
                # Status indicator
                status_indicator = ui.element('span').classes('indicator')

                # Status label
                status_label = ui.label()

                # Bind combined state
                def update_tracking_display():
                    slewing = state.slewing
                    tracking = state.tracking_enabled

                    # Clear previous classes
                    status_indicator.classes(
                        remove='indicator-ok indicator-warning indicator-inactive indicator-pulse'
                    )

                    if slewing:
                        status_indicator.classes(add='indicator-warning indicator-pulse')
                        status_label.text = 'Slewing'
                    elif tracking:
                        status_indicator.classes(add='indicator-ok')
                        status_label.text = 'Tracking'
                    else:
                        status_indicator.classes(add='indicator-inactive')
                        status_label.text = 'Idle'

                # Initial state
                update_tracking_display()

                # Add listeners for state changes
                def on_state_change(field, value):
                    if field in ('slewing', 'tracking_enabled'):
                        update_tracking_display()

                state.add_listener(on_state_change)

            # Rate display (Layer 2 detail)
            with ui.row().classes('items-center gap-2 disclosure-2'):
                ui.label('Rate:').classes('label')
                rate_label = ui.label().classes('mono')
                rate_label.bind_text_from(
                    state, 'tracking_rate',
                    lambda r: TRACKING_RATES.get(r, r.capitalize())
                )

    return container


def tracking_indicator_compact(state: TelescopeState) -> ui.element:
    """Compact tracking indicator for header/footer.

    Single indicator with label showing current state.

    Args:
        state: Telescope state instance.

    Returns:
        Container element.
    """
    with ui.row().classes('items-center gap-2') as container:
        # Indicator
        ind = ui.element('span').classes('indicator indicator-inactive')

        # Label
        label = ui.label('Idle')

        def update():
            ind.classes(
                remove='indicator-ok indicator-warning indicator-inactive indicator-pulse'
            )

            if state.slewing:
                ind.classes(add='indicator-warning indicator-pulse')
                label.text = 'Slewing'
            elif state.tracking_enabled:
                ind.classes(add='indicator-ok')
                label.text = 'Tracking'
            else:
                ind.classes(add='indicator-inactive')
                label.text = 'Idle'

        update()

        def on_change(field, value):
            if field in ('slewing', 'tracking_enabled'):
                update()

        state.add_listener(on_change)

    return container


def slew_progress(state: TelescopeState) -> ui.element:
    """Slew progress display.

    Shows progress bar and target info when slewing.
    Hidden when not slewing.

    Args:
        state: Telescope state instance.

    Returns:
        Container element.
    """
    with ui.column().classes('w-full') as container:
        # This element is shown/hidden based on slewing state
        progress_container = ui.column().classes('w-full gap-1')

        with progress_container:
            with ui.row().classes('items-center gap-2'):
                ui.label('Slewing to target...').classes('text-sm')
                ui.spinner(size='sm')

            # Progress bar (indeterminate since we don't know exact progress)
            ui.linear_progress(indeterminate=True).props('instant-feedback')

        def update_visibility():
            if state.slewing:
                progress_container.set_visibility(True)
            else:
                progress_container.set_visibility(False)

        update_visibility()

        def on_change(field, value):
            if field == 'slewing':
                update_visibility()

        state.add_listener(on_change)

    return container
