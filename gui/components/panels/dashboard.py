# -*- coding: utf-8 -*-
"""
Dashboard Component

Compact summary dashboard showing key telescope info at a glance.
Always visible above the detail navigation.
"""

from nicegui import ui

from ...state import (
    TelescopeState,
    AlignmentState,
    format_ra,
    format_dec,
)


def dashboard(state: TelescopeState) -> ui.element:
    """Compact dashboard showing key status at a glance.

    Layout:
    ┌─────────────────────────────────────────────────┐
    │ [Position] │ [Tracking] │ [Status Indicators]   │
    └─────────────────────────────────────────────────┘

    Always visible, provides quick overview without
    navigating to detail panels.

    Args:
        state: Telescope state instance.

    Returns:
        Dashboard container element.
    """
    with ui.card().classes('dashboard w-full') as container:
        with ui.row().classes('w-full items-center justify-between gap-4 flex-wrap'):
            # Position section
            _position_section(state)

            # Vertical divider
            ui.element('div').classes('dashboard-divider')

            # Tracking section
            _tracking_section(state)

            # Vertical divider
            ui.element('div').classes('dashboard-divider')

            # Status indicators section
            _status_section(state)

    return container


def _position_section(state: TelescopeState) -> ui.element:
    """Position summary section."""
    with ui.column().classes('dashboard-section') as section:
        # RA/Dec row
        with ui.row().classes('items-center gap-4'):
            # RA
            with ui.row().classes('items-baseline gap-1'):
                ui.label('RA').classes('dashboard-label')
                ra_val = ui.label().classes('dashboard-value mono')
                ra_val.bind_text_from(state, 'ra_hours', format_ra)

            # Dec
            with ui.row().classes('items-baseline gap-1'):
                ui.label('Dec').classes('dashboard-label')
                dec_val = ui.label().classes('dashboard-value mono')
                dec_val.bind_text_from(state, 'dec_degrees', format_dec)

        # Alt/Az row (smaller)
        with ui.row().classes('items-center gap-3'):
            # Alt
            with ui.row().classes('items-baseline gap-1'):
                ui.label('Alt').classes('dashboard-label-sm')
                alt_val = ui.label().classes('dashboard-value-sm mono')
                alt_val.bind_text_from(
                    state, 'alt_degrees',
                    lambda d: f"{d:.1f}°"
                )

            # Az
            with ui.row().classes('items-baseline gap-1'):
                ui.label('Az').classes('dashboard-label-sm')
                az_val = ui.label().classes('dashboard-value-sm mono')
                az_val.bind_text_from(
                    state, 'az_degrees',
                    lambda d: f"{d:.1f}°"
                )

            # Pier side
            with ui.row().classes('items-baseline gap-1'):
                ui.label('Pier').classes('dashboard-label-sm')
                pier_val = ui.label().classes('dashboard-value-sm')
                pier_val.bind_text_from(
                    state, 'pier_side',
                    lambda p: p[0].upper() if p else '?'
                )

    return section


def _tracking_section(state: TelescopeState) -> ui.element:
    """Tracking status section."""
    with ui.column().classes('dashboard-section items-center') as section:
        # Status indicator with label
        with ui.row().classes('items-center gap-2'):
            track_ind = ui.element('span').classes('indicator indicator-lg')
            track_label = ui.label().classes('dashboard-status-text')

        # Tracking rate (smaller)
        rate_label = ui.label().classes('dashboard-label-sm')

        def update_tracking():
            track_ind.classes(
                remove='indicator-ok indicator-warning indicator-error indicator-inactive indicator-pulse'
            )

            if state.slewing:
                track_ind.classes(add='indicator-warning indicator-pulse')
                track_label.text = 'SLEWING'
                track_label.classes(remove='text-success text-error')
                track_label.classes(add='text-warning')
                rate_label.text = ''
            elif state.tracking_enabled:
                track_ind.classes(add='indicator-ok')
                track_label.text = 'TRACKING'
                track_label.classes(remove='text-warning text-error')
                track_label.classes(add='text-success')
                rate_label.text = state.tracking_rate.capitalize()
            else:
                track_ind.classes(add='indicator-inactive')
                track_label.text = 'IDLE'
                track_label.classes(remove='text-success text-warning')
                rate_label.text = ''

        update_tracking()

        def on_tracking_change(field, value):
            if field in ('slewing', 'tracking_enabled', 'tracking_rate'):
                update_tracking()

        state.add_listener(on_tracking_change)

    return section


def _status_section(state: TelescopeState) -> ui.element:
    """Status indicators section."""
    with ui.row().classes('dashboard-section items-center gap-4') as section:
        # Connection indicator
        with ui.column().classes('items-center gap-0'):
            conn_ind = ui.element('span').classes('indicator')
            ui.label('Mount').classes('dashboard-indicator-label')

            def update_connection():
                conn_ind.classes(
                    remove='indicator-ok indicator-error indicator-inactive'
                )
                if state.connected:
                    conn_ind.classes(add='indicator-ok')
                elif state.connection_error:
                    conn_ind.classes(add='indicator-error')
                else:
                    conn_ind.classes(add='indicator-inactive')

            update_connection()

            def on_conn_change(field, value):
                if field in ('connected', 'connection_error'):
                    update_connection()

            state.add_listener(on_conn_change)

        # Park indicator
        with ui.column().classes('items-center gap-0'):
            park_ind = ui.element('span').classes('indicator')
            ui.label('Park').classes('dashboard-indicator-label')

            def update_park():
                park_ind.classes(
                    remove='indicator-ok indicator-warning indicator-inactive'
                )
                if state.at_park:
                    park_ind.classes(add='indicator-ok')
                elif state.at_home:
                    park_ind.classes(add='indicator-warning')
                else:
                    park_ind.classes(add='indicator-inactive')

            update_park()

            def on_park_change(field, value):
                if field in ('at_park', 'at_home'):
                    update_park()

            state.add_listener(on_park_change)

        # GPS indicator
        with ui.column().classes('items-center gap-0'):
            gps_ind = ui.element('span').classes('indicator')
            ui.label('GPS').classes('dashboard-indicator-label')

            def update_gps():
                gps_ind.classes(
                    remove='indicator-ok indicator-warning indicator-error indicator-inactive'
                )
                if state.gps_fix:
                    gps_ind.classes(add='indicator-ok')
                elif state.gps_enabled:
                    gps_ind.classes(add='indicator-warning')
                else:
                    gps_ind.classes(add='indicator-inactive')

            update_gps()

            def on_gps_change(field, value):
                if field in ('gps_enabled', 'gps_fix'):
                    update_gps()

            state.add_listener(on_gps_change)

        # Alignment indicator (only in expanded+ mode)
        align_container = ui.column().classes('items-center gap-0 disclosure-2')
        with align_container:
            align_ind = ui.element('span').classes('indicator')
            ui.label('Align').classes('dashboard-indicator-label')

            def update_alignment():
                align_ind.classes(
                    remove='indicator-ok indicator-warning indicator-error indicator-inactive indicator-pulse'
                )
                monitoring_states = [
                    AlignmentState.MONITORING,
                    AlignmentState.CAPTURING,
                    AlignmentState.SOLVING,
                ]
                if state.alignment_state in monitoring_states:
                    # Check error level
                    if state.alignment_error_arcsec < 60:
                        align_ind.classes(add='indicator-ok')
                    elif state.alignment_error_arcsec < 120:
                        align_ind.classes(add='indicator-warning')
                    else:
                        align_ind.classes(add='indicator-error')

                    if state.alignment_state in [AlignmentState.CAPTURING, AlignmentState.SOLVING]:
                        align_ind.classes(add='indicator-pulse')
                elif state.alignment_state == AlignmentState.CONNECTED:
                    align_ind.classes(add='indicator-ok')
                elif state.alignment_state == AlignmentState.ERROR:
                    align_ind.classes(add='indicator-error')
                else:
                    align_ind.classes(add='indicator-inactive')

            update_alignment()

            def on_align_change(field, value):
                if field in ('alignment_state', 'alignment_error_arcsec'):
                    update_alignment()

            state.add_listener(on_align_change)

    return section
