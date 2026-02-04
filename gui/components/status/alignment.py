# -*- coding: utf-8 -*-
"""
Alignment Status Component

Shows alignment monitor status, errors, and geometry quality.
"""

from nicegui import ui

from ...state import TelescopeState, AlignmentState, DecisionResult, format_error


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

# Decision result display
DECISION_DISPLAY = {
    DecisionResult.NONE: 'None',
    DecisionResult.NO_ACTION: 'No action',
    DecisionResult.SYNC: 'Sync',
    DecisionResult.ALIGN: 'Align',
    DecisionResult.LOCKOUT: 'Lockout',
    DecisionResult.ERROR: 'Error',
}


def alignment_status(state: TelescopeState) -> ui.element:
    """Display alignment monitor status.

    Layer 2 shows:
    - Current state with indicator
    - Total error (color-coded)
    - Geometry quality (determinant)

    Layer 3 adds:
    - Detailed RA/Dec error breakdown
    - Last decision result
    - Lockout status
    - Health alert indicator

    Args:
        state: Telescope state instance.

    Returns:
        Container element with alignment status.
    """
    with ui.card().classes('gui-card w-full disclosure-2') as container:
        ui.label('Alignment Monitor').classes('section-header')

        with ui.column().classes('gap-3'):
            # State indicator row
            with ui.row().classes('items-center gap-3'):
                state_ind = ui.element('span').classes('indicator')
                state_label = ui.label()

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

            # Error display
            with ui.column().classes('gap-1'):
                ui.label('Pointing Error').classes('label')

                with ui.row().classes('items-baseline gap-2'):
                    error_label = ui.label().classes('value-large mono')

                    def format_and_color_error(arcsec):
                        # Format
                        if abs(arcsec) >= 60:
                            text = f"{arcsec / 60:.1f}'"
                        else:
                            text = f'{arcsec:.1f}"'

                        # Color class based on thresholds
                        arcsec = abs(arcsec)
                        if arcsec < 30:
                            color = 'text-green-500'
                        elif arcsec < 60:
                            color = 'text-yellow-500'
                        elif arcsec < 120:
                            color = 'text-orange-500'
                        else:
                            color = 'text-red-500'

                        return text

                    error_label.bind_text_from(
                        state, 'alignment_error_arcsec',
                        format_and_color_error
                    )

                # RA/Dec breakdown (Layer 3)
                with ui.row().classes('gap-4 disclosure-3'):
                    with ui.row().classes('items-baseline gap-1'):
                        ui.label('RA:').classes('label text-xs')
                        ra_err = ui.label().classes('mono text-sm')
                        ra_err.bind_text_from(
                            state, 'alignment_error_ra',
                            lambda e: f'{e:.1f}"'
                        )

                    with ui.row().classes('items-baseline gap-1'):
                        ui.label('Dec:').classes('label text-xs')
                        dec_err = ui.label().classes('mono text-sm')
                        dec_err.bind_text_from(
                            state, 'alignment_error_dec',
                            lambda e: f'{e:.1f}"'
                        )

            # Geometry determinant
            with ui.column().classes('gap-1'):
                ui.label('Geometry Quality').classes('label')

                with ui.row().classes('items-center gap-2'):
                    det_label = ui.label().classes('value-normal mono')

                    def format_determinant(det):
                        # Format as percentage
                        pct = det * 100
                        return f'{pct:.0f}%'

                    det_label.bind_text_from(
                        state, 'geometry_determinant',
                        format_determinant
                    )

                    # Quality indicator
                    det_quality = ui.label().classes('text-sm')

                    def get_quality_text(det):
                        if det >= 0.80:
                            return 'Excellent'
                        elif det >= 0.60:
                            return 'Good'
                        elif det >= 0.40:
                            return 'Marginal'
                        else:
                            return 'Poor'

                    det_quality.bind_text_from(
                        state, 'geometry_determinant',
                        get_quality_text
                    )

            # Layer 3: Decision and lockout info
            with ui.column().classes('gap-2 disclosure-3'):
                ui.separator().classes('my-1')

                # Last decision
                with ui.row().classes('items-center gap-2'):
                    ui.label('Last decision:').classes('label')
                    decision_label = ui.label().classes('mono text-sm')
                    decision_label.bind_text_from(
                        state, 'last_decision',
                        lambda d: DECISION_DISPLAY.get(d, str(d))
                    )

                # Lockout status
                lockout_row = ui.row().classes('items-center gap-2')
                with lockout_row:
                    ui.icon('lock').classes('text-sm text-warning')
                    lockout_label = ui.label().classes('text-sm')
                    lockout_label.bind_text_from(
                        state, 'lockout_remaining_sec',
                        lambda s: f'Lockout: {s:.0f}s remaining' if s > 0 else ''
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
                    ui.icon('warning').classes('text-lg')
                    ui.label('Alignment health alert').classes('font-medium')

                def update_alert_visibility():
                    alert_row.set_visibility(state.health_alert)

                update_alert_visibility()

                def on_alert_change(field, value):
                    if field == 'health_alert':
                        update_alert_visibility()

                state.add_listener(on_alert_change)

            # Camera source info
            with ui.row().classes('items-center gap-2'):
                ui.label('Camera:').classes('label')
                camera_label = ui.label().classes('mono text-sm')
                camera_label.bind_text_from(
                    state, 'camera_source',
                    lambda s: s.upper()
                )

    return container


def alignment_indicator_compact(state: TelescopeState) -> ui.element:
    """Compact alignment indicator for header/footer.

    Shows error value with color coding.

    Args:
        state: Telescope state instance.

    Returns:
        Container element.
    """
    with ui.row().classes('items-center gap-2') as container:
        # Only show when alignment is active
        with ui.row().classes('items-center gap-1') as row:
            ui.icon('straighten').classes('text-sm')
            error_label = ui.label().classes('mono text-sm')

            def format_compact(arcsec):
                if abs(arcsec) >= 60:
                    return f"{arcsec / 60:.1f}'"
                return f'{arcsec:.0f}"'

            error_label.bind_text_from(
                state, 'alignment_error_arcsec',
                format_compact
            )

        def update_visibility():
            monitoring_states = (
                AlignmentState.MONITORING,
                AlignmentState.CAPTURING,
                AlignmentState.SOLVING,
            )
            row.set_visibility(state.alignment_state in monitoring_states)

        update_visibility()

        def on_change(field, value):
            if field == 'alignment_state':
                update_visibility()

        state.add_listener(on_change)

    return container
