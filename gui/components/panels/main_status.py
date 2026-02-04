# -*- coding: utf-8 -*-
"""
Main Status Panel

Combines status components with proper information hierarchy.
"""

from nicegui import ui

from ...state import TelescopeState
from ..status import (
    position_display,
    tracking_display,
    connection_status,
    hardware_status,
    alignment_status,
    slew_progress,
)


def main_status_panel(state: TelescopeState) -> ui.element:
    """Primary status panel - always visible.

    Contains Layer 1 (always visible):
    - Position display (highest priority)
    - Tracking display
    - Connection indicator

    Expandable Layer 2:
    - Hardware status
    - Alignment status

    Args:
        state: Telescope state instance.

    Returns:
        Container element with status panel.
    """
    with ui.column().classes('w-full gap-4') as container:
        # Layer 1: Primary Status (always visible)
        # Position is highest priority - largest visual presence
        position_display(state)

        # Slew progress (shown when slewing)
        slew_progress(state)

        # Tracking status
        tracking_display(state)

        # Connection status
        connection_status(state)

        # Layer 2: Secondary Status (expanded view)
        hardware_status(state)

        # Alignment monitor status
        alignment_status(state)

    return container


def compact_status_panel(state: TelescopeState) -> ui.element:
    """Compact status panel for smaller layouts.

    Single card with essential info only.

    Args:
        state: Telescope state instance.

    Returns:
        Container element.
    """
    with ui.card().classes('gui-card w-full') as container:
        with ui.column().classes('gap-2'):
            # Compact position
            with ui.row().classes('w-full justify-between'):
                # RA/Dec
                with ui.column().classes('gap-0'):
                    ui.label('RA').classes('label text-xs')
                    ra_label = ui.label().classes('mono text-sm')
                    ra_label.bind_text_from(
                        state, 'ra_hours',
                        lambda h: f"{int(h):02d}h {int((h % 1) * 60):02d}m"
                    )

                with ui.column().classes('gap-0'):
                    ui.label('Dec').classes('label text-xs')
                    dec_label = ui.label().classes('mono text-sm')
                    dec_label.bind_text_from(
                        state, 'dec_degrees',
                        lambda d: f"{'+' if d >= 0 else ''}{d:.1f}°"
                    )

                # Status indicators
                with ui.row().classes('gap-2'):
                    # Connection
                    conn_ind = ui.element('span').classes('indicator')

                    def update_conn():
                        conn_ind.classes(
                            remove='indicator-ok indicator-inactive'
                        )
                        if state.connected:
                            conn_ind.classes(add='indicator-ok')
                        else:
                            conn_ind.classes(add='indicator-inactive')

                    update_conn()

                    def on_conn_change(field, value):
                        if field == 'connected':
                            update_conn()

                    state.add_listener(on_conn_change)

                    # Tracking
                    track_ind = ui.element('span').classes('indicator')

                    def update_track():
                        track_ind.classes(
                            remove='indicator-ok indicator-warning indicator-inactive indicator-pulse'
                        )
                        if state.slewing:
                            track_ind.classes(add='indicator-warning indicator-pulse')
                        elif state.tracking_enabled:
                            track_ind.classes(add='indicator-ok')
                        else:
                            track_ind.classes(add='indicator-inactive')

                    update_track()

                    def on_track_change(field, value):
                        if field in ('slewing', 'tracking_enabled'):
                            update_track()

                    state.add_listener(on_track_change)

    return container


def status_summary_row(state: TelescopeState) -> ui.element:
    """Single-row status summary for header/footer.

    Shows key indicators in minimal space.

    Args:
        state: Telescope state instance.

    Returns:
        Row element with status indicators.
    """
    with ui.row().classes('items-center gap-4') as container:
        # Connection indicator
        with ui.row().classes('items-center gap-1'):
            conn_ind = ui.element('span').classes('indicator indicator-inactive')
            conn_label = ui.label('Disconnected').classes('text-sm')

            def update_conn():
                conn_ind.classes(
                    remove='indicator-ok indicator-inactive'
                )
                if state.connected:
                    conn_ind.classes(add='indicator-ok')
                    conn_label.text = 'Connected'
                else:
                    conn_ind.classes(add='indicator-inactive')
                    conn_label.text = 'Disconnected'

            update_conn()

            def on_conn(field, value):
                if field == 'connected':
                    update_conn()

            state.add_listener(on_conn)

        # Tracking indicator
        with ui.row().classes('items-center gap-1'):
            track_ind = ui.element('span').classes('indicator')
            track_label = ui.label().classes('text-sm')

            def update_track():
                track_ind.classes(
                    remove='indicator-ok indicator-warning indicator-inactive indicator-pulse'
                )
                if state.slewing:
                    track_ind.classes(add='indicator-warning indicator-pulse')
                    track_label.text = 'Slewing'
                elif state.tracking_enabled:
                    track_ind.classes(add='indicator-ok')
                    track_label.text = 'Tracking'
                else:
                    track_ind.classes(add='indicator-inactive')
                    track_label.text = 'Idle'

            update_track()

            def on_track(field, value):
                if field in ('slewing', 'tracking_enabled'):
                    update_track()

            state.add_listener(on_track)

        # Park indicator (only when parked)
        park_badge = ui.badge('PARKED').props('color=primary')

        def update_park():
            park_badge.set_visibility(state.at_park)

        update_park()

        def on_park(field, value):
            if field == 'at_park':
                update_park()

        state.add_listener(on_park)

    return container
