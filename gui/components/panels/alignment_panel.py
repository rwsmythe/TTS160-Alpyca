# -*- coding: utf-8 -*-
"""
Alignment Detail Panel

Alignment monitor status, error display, QA verification, and controls.
"""

from typing import Callable, Dict
from nicegui import ui

from ...state import (
    TelescopeState,
    AlignmentState,
    DecisionResult,
    QAStatusCode,
    format_error,
)


# State display configuration
STATE_DISPLAY = {
    AlignmentState.DISABLED: ('Disabled', 'indicator-inactive', False),
    AlignmentState.DISCONNECTED: ('Disconnected', 'indicator-inactive', False),
    AlignmentState.CONNECTING: ('Connecting...', 'indicator-warning', True),
    AlignmentState.CONNECTED: ('Connected', 'indicator-ok', False),
    AlignmentState.CAPTURING: ('Capturing', 'indicator-warning', True),
    AlignmentState.SOLVING: ('Solving', 'indicator-warning', True),
    AlignmentState.MONITORING: ('Monitoring', 'indicator-ok', True),
    AlignmentState.ERROR: ('Error', 'indicator-error', False),
}

DECISION_DISPLAY = {
    DecisionResult.NONE: 'None',
    DecisionResult.NO_ACTION: 'No action',
    DecisionResult.SYNC: 'Sync',
    DecisionResult.ALIGN: 'Align',
    DecisionResult.LOCKOUT: 'Lockout',
    DecisionResult.ERROR: 'Error',
}

QA_STATUS_DISPLAY = {
    QAStatusCode.VALID: ('Valid', 'indicator-ok', 'Quaternions match'),
    QAStatusCode.INVALID: ('Invalid', 'indicator-error', 'Calculation error'),
    QAStatusCode.STALE: ('Stale', 'indicator-warning', 'Data outdated'),
    QAStatusCode.NO_DATA: ('No Data', 'indicator-inactive', 'No firmware data'),
    QAStatusCode.SYNTHETIC: ('Synthetic', 'indicator-warning', 'Synthetic points'),
    QAStatusCode.DISABLED: ('Disabled', 'indicator-inactive', 'QA disabled'),
}


def alignment_panel(
    state: TelescopeState,
    handlers: Dict[str, Callable],
) -> ui.element:
    """Alignment detail panel.

    Shows:
    - Monitor state and camera connection
    - Pointing error (total, RA, Dec)
    - Geometry quality (determinant)
    - Decision engine status
    - QA verification (advanced)
    - Alignment controls

    Args:
        state: Telescope state instance.
        handlers: Command handlers including 'measure_now'.

    Returns:
        Panel container element.
    """
    with ui.column().classes('w-full gap-4') as container:
        # Monitor Status card
        with ui.card().classes('gui-card w-full'):
            ui.label('Alignment Monitor').classes('section-header')

            # Status row
            with ui.row().classes('items-center gap-4 mb-4'):
                state_ind = ui.element('span').classes('indicator indicator-lg')
                state_label = ui.label().classes('text-xl')

                def update_state():
                    display = STATE_DISPLAY.get(
                        state.alignment_state,
                        ('Unknown', 'indicator-inactive', False)
                    )
                    text, indicator_class, pulse = display

                    state_ind.classes(
                        remove='indicator-ok indicator-warning indicator-error indicator-inactive indicator-pulse'
                    )
                    state_ind.classes(add=indicator_class)
                    if pulse:
                        state_ind.classes(add='indicator-pulse')

                    state_label.text = text

                update_state()

                def on_state_change(field, value):
                    if field == 'alignment_state':
                        update_state()

                state.add_listener(on_state_change)

                # Camera source
                with ui.row().classes('items-center gap-1 ml-auto'):
                    ui.icon('camera').classes('text-secondary')
                    camera_label = ui.label().classes('text-secondary')
                    camera_label.bind_text_from(
                        state, 'camera_source',
                        lambda s: s.upper()
                    )

        # Pointing Error card
        with ui.card().classes('gui-card w-full'):
            ui.label('Pointing Error').classes('section-header')

            with ui.column().classes('gap-4'):
                # Total error (large)
                with ui.row().classes('items-baseline gap-2'):
                    ui.label('Total:').classes('label')
                    total_label = ui.label().classes('text-3xl font-mono font-semibold')

                    def format_and_color_error():
                        arcsec = state.alignment_error_arcsec
                        text = format_error(arcsec)
                        total_label.text = text

                        # Color class based on thresholds
                        total_label.classes(
                            remove='text-green-500 text-yellow-500 text-orange-500 text-red-500'
                        )
                        arcsec = abs(arcsec)
                        if arcsec < 30:
                            total_label.classes(add='text-green-500')
                        elif arcsec < 60:
                            total_label.classes(add='text-yellow-500')
                        elif arcsec < 120:
                            total_label.classes(add='text-orange-500')
                        else:
                            total_label.classes(add='text-red-500')

                    format_and_color_error()

                    def on_error_change(field, value):
                        if field == 'alignment_error_arcsec':
                            format_and_color_error()

                    state.add_listener(on_error_change)

                # RA/Dec breakdown
                with ui.row().classes('gap-8'):
                    with ui.row().classes('items-baseline gap-2'):
                        ui.label('RA:').classes('label')
                        ra_err = ui.label().classes('text-lg font-mono')
                        ra_err.bind_text_from(
                            state, 'alignment_error_ra',
                            lambda e: f'{e:.1f}"'
                        )

                    with ui.row().classes('items-baseline gap-2'):
                        ui.label('Dec:').classes('label')
                        dec_err = ui.label().classes('text-lg font-mono')
                        dec_err.bind_text_from(
                            state, 'alignment_error_dec',
                            lambda e: f'{e:.1f}"'
                        )

        # Geometry Quality card
        with ui.card().classes('gui-card w-full'):
            ui.label('Alignment Geometry').classes('section-header')

            with ui.row().classes('items-center gap-4'):
                # Determinant value
                with ui.column().classes('gap-1'):
                    ui.label('Geometry Quality').classes('label')
                    det_row = ui.row().classes('items-baseline gap-2')
                    with det_row:
                        det_label = ui.label().classes('text-2xl font-mono')
                        quality_label = ui.label().classes('text-lg')

                        def update_determinant():
                            det = state.geometry_determinant
                            pct = det * 100
                            det_label.text = f'{pct:.0f}%'

                            det_label.classes(
                                remove='text-green-500 text-yellow-500 text-red-500'
                            )
                            quality_label.classes(
                                remove='text-green-500 text-yellow-500 text-red-500'
                            )

                            if det >= 0.80:
                                det_label.classes(add='text-green-500')
                                quality_label.classes(add='text-green-500')
                                quality_label.text = 'Excellent'
                            elif det >= 0.60:
                                det_label.classes(add='text-green-500')
                                quality_label.classes(add='text-green-500')
                                quality_label.text = 'Good'
                            elif det >= 0.40:
                                det_label.classes(add='text-yellow-500')
                                quality_label.classes(add='text-yellow-500')
                                quality_label.text = 'Marginal'
                            else:
                                det_label.classes(add='text-red-500')
                                quality_label.classes(add='text-red-500')
                                quality_label.text = 'Poor'

                        update_determinant()

                        def on_det_change(field, value):
                            if field == 'geometry_determinant':
                                update_determinant()

                        state.add_listener(on_det_change)

        # Decision Engine card (disclosure-3)
        decision_card = ui.card().classes('gui-card w-full disclosure-3')
        with decision_card:
            ui.label('Decision Engine').classes('section-header')

            with ui.column().classes('gap-3'):
                # Last decision
                with ui.row().classes('items-center gap-4'):
                    ui.label('Last Decision:').classes('label')
                    decision_label = ui.label().classes('text-lg font-mono')
                    decision_label.bind_text_from(
                        state, 'last_decision',
                        lambda d: DECISION_DISPLAY.get(d, str(d))
                    )

                # Lockout status
                lockout_row = ui.row().classes('items-center gap-2')
                with lockout_row:
                    ui.icon('lock').classes('text-warning')
                    lockout_label = ui.label().classes('text-lg')
                    lockout_label.bind_text_from(
                        state, 'lockout_remaining_sec',
                        lambda s: f'Lockout: {s:.0f}s' if s > 0 else ''
                    )

                def update_lockout_visibility():
                    lockout_row.set_visibility(state.lockout_remaining_sec > 0)

                update_lockout_visibility()

                def on_lockout_change(field, value):
                    if field == 'lockout_remaining_sec':
                        update_lockout_visibility()

                state.add_listener(on_lockout_change)

                # Health alert
                alert_row = ui.row().classes('items-center gap-2 text-error')
                with alert_row:
                    ui.icon('warning').classes('text-xl')
                    ui.label('Alignment health alert').classes('font-semibold')

                def update_alert_visibility():
                    alert_row.set_visibility(state.health_alert)

                update_alert_visibility()

                def on_alert_change(field, value):
                    if field == 'health_alert':
                        update_alert_visibility()

                state.add_listener(on_alert_change)

        # QA Verification card (disclosure-3)
        qa_card = ui.card().classes('gui-card w-full disclosure-3')
        with qa_card:
            ui.label('QA Verification').classes('section-header')

            # QA Status
            with ui.row().classes('items-center gap-3 mb-4'):
                qa_ind = ui.element('span').classes('indicator')
                qa_label = ui.label().classes('text-lg')
                qa_tooltip = ui.label().classes('text-secondary')

                def update_qa_status():
                    display = QA_STATUS_DISPLAY.get(
                        state.qa_status,
                        ('Unknown', 'indicator-inactive', '')
                    )
                    text, indicator_class, tooltip = display

                    qa_ind.classes(
                        remove='indicator-ok indicator-warning indicator-error indicator-inactive'
                    )
                    qa_ind.classes(add=indicator_class)
                    qa_label.text = text
                    qa_tooltip.text = f'({tooltip})'

                update_qa_status()

                def on_qa_change(field, value):
                    if field == 'qa_status':
                        update_qa_status()

                state.add_listener(on_qa_change)

            # Quaternion delta
            with ui.row().classes('items-baseline gap-2 mb-2'):
                ui.label('Quaternion Delta:').classes('label')
                quat_delta = ui.label().classes('text-lg font-mono')
                quat_delta.bind_text_from(
                    state, 'qa_quaternion_delta',
                    lambda a: format_error(a)
                )

            # Synthetic points
            synth_row = ui.row().classes('items-center gap-2')
            with synth_row:
                ui.icon('auto_fix_high').classes('text-warning')
                synth_label = ui.label()
                synth_label.bind_text_from(
                    state, 'qa_synthetic_count',
                    lambda c: f'{c} synthetic point{"s" if c != 1 else ""}' if c > 0 else ''
                )

            def update_synth_visibility():
                synth_row.set_visibility(state.qa_synthetic_count > 0)

            update_synth_visibility()

            def on_synth_change(field, value):
                if field == 'qa_synthetic_count':
                    update_synth_visibility()

            state.add_listener(on_synth_change)

            # Model valid
            with ui.row().classes('items-center gap-2'):
                model_icon = ui.icon('check_circle')
                model_label = ui.label()

                def update_model_status():
                    if state.qa_model_valid:
                        model_icon.classes(remove='text-error')
                        model_icon.classes(add='text-success')
                        model_icon.text = 'check_circle'
                        model_label.text = 'Model valid'
                    else:
                        model_icon.classes(remove='text-success')
                        model_icon.classes(add='text-error')
                        model_icon.text = 'cancel'
                        model_label.text = 'Model invalid'

                update_model_status()

                def on_model_change(field, value):
                    if field == 'qa_model_valid':
                        update_model_status()

                state.add_listener(on_model_change)

        # Hide QA card if disabled
        def update_qa_visibility():
            qa_card.set_visibility(state.qa_enabled)

        update_qa_visibility()

        def on_qa_enabled_change(field, value):
            if field == 'qa_enabled':
                update_qa_visibility()

        state.add_listener(on_qa_enabled_change)

        # Controls card
        with ui.card().classes('gui-card w-full'):
            ui.label('Controls').classes('section-header')

            with ui.row().classes('gap-4'):
                # Measure Now button
                measure_handler = handlers.get('measure_now')
                measure_btn = ui.button(
                    'Measure Now',
                    icon='straighten',
                    on_click=lambda: measure_handler() if measure_handler else None,
                ).props('outline')

                def update_measure_enabled():
                    active_states = [
                        AlignmentState.CONNECTED,
                        AlignmentState.MONITORING,
                    ]
                    enabled = state.alignment_state in active_states
                    measure_btn.set_enabled(enabled)

                update_measure_enabled()

                def on_measure_state_change(field, value):
                    if field == 'alignment_state':
                        update_measure_enabled()

                state.add_listener(on_measure_state_change)

                # Sync button
                sync_handler = handlers.get('sync')
                sync_btn = ui.button(
                    'Sync',
                    icon='sync',
                    on_click=lambda: sync_handler() if sync_handler else None,
                ).props('outline')

                def update_sync_enabled():
                    sync_btn.set_enabled(state.connected and not state.slewing)

                update_sync_enabled()

                def on_sync_state_change(field, value):
                    if field in ('connected', 'slewing'):
                        update_sync_enabled()

                state.add_listener(on_sync_state_change)

    return container
