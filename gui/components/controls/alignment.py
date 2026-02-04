# -*- coding: utf-8 -*-
"""
Alignment Controls Component

Sync and alignment monitor controls.
"""

from typing import Callable, Optional
from nicegui import ui

from ...state import TelescopeState, AlignmentState


def alignment_controls(
    state: TelescopeState,
    on_sync: Callable[[float, float], None],
    on_measure: Callable[[], None],
    on_enable_monitor: Optional[Callable[[bool], None]] = None,
) -> ui.element:
    """Alignment operations.

    Shows:
    - Sync to coordinates input
    - Manual measure button (trigger plate solve)
    - Alignment monitor enable/disable (Layer 2)
    - Camera source indicator

    Args:
        state: Telescope state instance.
        on_sync: Callback with (ra_hours, dec_degrees) for sync.
        on_measure: Callback to trigger manual measurement.
        on_enable_monitor: Optional callback to enable/disable monitor.

    Returns:
        Container element with alignment controls.
    """
    with ui.card().classes('gui-card w-full disclosure-2') as container:
        ui.label('Alignment').classes('section-header')

        with ui.column().classes('gap-3'):
            # Sync controls
            ui.label('Sync to Coordinates').classes('text-sm font-medium')

            with ui.row().classes('gap-4'):
                with ui.column().classes('gap-1'):
                    ui.label('RA (hours)').classes('label text-xs')
                    ra_input = ui.input(
                        placeholder='12.5'
                    ).classes('w-28 gui-input')

                with ui.column().classes('gap-1'):
                    ui.label('Dec (degrees)').classes('label text-xs')
                    dec_input = ui.input(
                        placeholder='+45.5'
                    ).classes('w-28 gui-input')

            def do_sync():
                try:
                    ra = float(ra_input.value)
                    dec = float(dec_input.value)
                    on_sync(ra, dec)
                    ui.notify('Sync command sent', type='positive')
                except ValueError:
                    ui.notify('Invalid coordinates', type='warning')

            ui.button('Sync', on_click=do_sync).classes('gui-button')

            # Alignment monitor section
            ui.separator().classes('my-2')
            ui.label('Alignment Monitor').classes('text-sm font-medium')

            # Monitor status
            with ui.row().classes('items-center gap-2'):
                monitor_ind = ui.element('span').classes('indicator')
                monitor_label = ui.label()

                def update_monitor_status():
                    monitor_ind.classes(
                        remove='indicator-ok indicator-warning indicator-inactive indicator-pulse'
                    )

                    if state.alignment_state == AlignmentState.DISABLED:
                        monitor_ind.classes(add='indicator-inactive')
                        monitor_label.text = 'Disabled'
                    elif state.alignment_state == AlignmentState.MONITORING:
                        monitor_ind.classes(add='indicator-ok indicator-pulse')
                        monitor_label.text = 'Monitoring'
                    elif state.alignment_state in (
                        AlignmentState.CAPTURING,
                        AlignmentState.SOLVING,
                    ):
                        monitor_ind.classes(add='indicator-warning indicator-pulse')
                        monitor_label.text = 'Working...'
                    elif state.alignment_state == AlignmentState.ERROR:
                        monitor_ind.classes(add='indicator-error')
                        monitor_label.text = 'Error'
                    else:
                        monitor_ind.classes(add='indicator-warning')
                        monitor_label.text = state.alignment_state.value.capitalize()

                update_monitor_status()

                def on_monitor_change(field, value):
                    if field == 'alignment_state':
                        update_monitor_status()

                state.add_listener(on_monitor_change)

            # Manual measure button
            measure_btn = ui.button(
                'Measure Now',
                on_click=on_measure
            ).classes('w-full')

            # Disable when not in appropriate state
            def update_measure_btn():
                can_measure = state.alignment_state in (
                    AlignmentState.CONNECTED,
                    AlignmentState.MONITORING,
                )
                if can_measure:
                    measure_btn.enable()
                else:
                    measure_btn.disable()

            update_measure_btn()

            def on_measure_state_change(field, value):
                if field == 'alignment_state':
                    update_measure_btn()

            state.add_listener(on_measure_state_change)

            # Enable/disable toggle (Layer 3)
            if on_enable_monitor:
                with ui.row().classes('items-center justify-between w-full disclosure-3'):
                    ui.label('Enable Monitor').classes('text-sm')

                    enable_switch = ui.switch(
                        value=state.alignment_state != AlignmentState.DISABLED,
                        on_change=lambda e: on_enable_monitor(e.value)
                    )

            # Camera source info
            with ui.row().classes('items-center gap-2'):
                ui.label('Camera:').classes('label')
                camera_label = ui.label().classes('mono text-sm')
                camera_label.bind_text_from(
                    state, 'camera_source',
                    lambda s: s.upper()
                )

    return container


def sync_button(
    on_sync: Callable[[], None],
    label: str = "Sync",
) -> ui.button:
    """Standalone sync button.

    Uses current mount position for sync (assumes user has centered on known star).

    Args:
        on_sync: Sync callback.
        label: Button label.

    Returns:
        Button element.
    """
    return ui.button(label, on_click=on_sync).classes('gui-button')


def measure_now_button(
    state: TelescopeState,
    on_measure: Callable[[], None],
) -> ui.element:
    """Standalone measure now button.

    Args:
        state: Telescope state instance.
        on_measure: Measure callback.

    Returns:
        Button element.
    """
    btn = ui.button('Measure Now', on_click=on_measure)

    def update():
        can_measure = state.alignment_state in (
            AlignmentState.CONNECTED,
            AlignmentState.MONITORING,
        )
        if can_measure:
            btn.enable()
        else:
            btn.disable()

    update()

    def on_change(field, value):
        if field == 'alignment_state':
            update()

    state.add_listener(on_change)

    return btn
