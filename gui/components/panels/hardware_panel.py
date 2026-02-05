# -*- coding: utf-8 -*-
"""
Hardware Detail Panel

Mount hardware status, GPS information, and motor states.
"""

from nicegui import ui

from ...state import TelescopeState


def hardware_panel(state: TelescopeState) -> ui.element:
    """Hardware detail panel.

    Shows:
    - Mount status (park, home, motors)
    - GPS status with coordinates
    - Connection details

    Args:
        state: Telescope state instance.

    Returns:
        Panel container element.
    """
    with ui.column().classes('w-full gap-4') as container:
        # Mount Status card
        with ui.card().classes('gui-card w-full'):
            ui.label('Mount Status').classes('section-header')

            with ui.column().classes('gap-4'):
                # Status indicators row
                with ui.row().classes('w-full gap-8'):
                    # Park status
                    _status_block(
                        state, 'at_park',
                        'Park',
                        true_text='Parked',
                        false_text='Not Parked',
                        true_class='indicator-ok',
                        false_class='indicator-inactive',
                    )

                    # Home status
                    _status_block(
                        state, 'at_home',
                        'Home',
                        true_text='At Home',
                        false_text='Not at Home',
                        true_class='indicator-ok',
                        false_class='indicator-inactive',
                    )

                    # Motors status
                    _status_block(
                        state, 'motors_enabled',
                        'Motors',
                        true_text='Enabled',
                        false_text='Disabled',
                        true_class='indicator-ok',
                        false_class='indicator-warning',
                    )

        # GPS Status card
        with ui.card().classes('gui-card w-full'):
            ui.label('GPS Status').classes('section-header')

            # GPS enabled indicator
            with ui.row().classes('items-center gap-3 mb-4'):
                gps_ind = ui.element('span').classes('indicator indicator-lg')
                gps_label = ui.label().classes('text-lg')

                def update_gps_status():
                    gps_ind.classes(
                        remove='indicator-ok indicator-warning indicator-error indicator-inactive indicator-pulse'
                    )
                    if state.gps_fix:
                        gps_ind.classes(add='indicator-ok')
                        gps_label.text = 'GPS Fix Acquired'
                    elif state.gps_enabled:
                        gps_ind.classes(add='indicator-warning indicator-pulse')
                        gps_label.text = 'Acquiring Fix...'
                    else:
                        gps_ind.classes(add='indicator-inactive')
                        gps_label.text = 'GPS Disabled'

                update_gps_status()

                def on_gps_change(field, value):
                    if field in ('gps_enabled', 'gps_fix'):
                        update_gps_status()

                state.add_listener(on_gps_change)

            # GPS details (only shown when enabled)
            gps_details = ui.column().classes('gap-4')
            with gps_details:
                with ui.row().classes('w-full gap-8'):
                    # Latitude
                    with ui.column().classes('gap-1'):
                        ui.label('Latitude').classes('label')
                        lat_label = ui.label().classes('text-xl font-mono')
                        lat_label.bind_text_from(
                            state, 'gps_latitude',
                            lambda lat: _format_lat(lat)
                        )

                    # Longitude
                    with ui.column().classes('gap-1'):
                        ui.label('Longitude').classes('label')
                        lon_label = ui.label().classes('text-xl font-mono')
                        lon_label.bind_text_from(
                            state, 'gps_longitude',
                            lambda lon: _format_lon(lon)
                        )

                with ui.row().classes('w-full gap-8'):
                    # Altitude
                    with ui.column().classes('gap-1'):
                        ui.label('Altitude').classes('label')
                        alt_label = ui.label().classes('text-lg font-mono')
                        alt_label.bind_text_from(
                            state, 'gps_altitude',
                            lambda alt: f"{alt:.1f} m"
                        )

                    # Satellites
                    with ui.column().classes('gap-1'):
                        ui.label('Satellites').classes('label')
                        sat_row = ui.row().classes('items-center gap-2')
                        with sat_row:
                            sat_icon = ui.icon('satellite_alt').classes('text-lg')
                            sat_label = ui.label().classes('text-lg font-mono')
                            sat_label.bind_text_from(
                                state, 'gps_satellites',
                                lambda s: str(s)
                            )

            def update_details_visibility():
                gps_details.set_visibility(state.gps_enabled)

            update_details_visibility()

            def on_gps_enabled_change(field, value):
                if field == 'gps_enabled':
                    update_details_visibility()

            state.add_listener(on_gps_enabled_change)

        # Connection Details card
        with ui.card().classes('gui-card w-full'):
            ui.label('Connection').classes('section-header')

            with ui.row().classes('w-full gap-8'):
                # Connection status
                with ui.column().classes('gap-1'):
                    ui.label('Status').classes('label')
                    with ui.row().classes('items-center gap-2'):
                        conn_ind = ui.element('span').classes('indicator')
                        conn_label = ui.label().classes('text-lg')

                        def update_conn():
                            conn_ind.classes(
                                remove='indicator-ok indicator-error indicator-inactive'
                            )
                            if state.connected:
                                conn_ind.classes(add='indicator-ok')
                                conn_label.text = 'Connected'
                            elif state.connection_error:
                                conn_ind.classes(add='indicator-error')
                                conn_label.text = 'Error'
                            else:
                                conn_ind.classes(add='indicator-inactive')
                                conn_label.text = 'Disconnected'

                        update_conn()

                        def on_conn_change(field, value):
                            if field in ('connected', 'connection_error'):
                                update_conn()

                        state.add_listener(on_conn_change)

                # Serial port
                with ui.column().classes('gap-1'):
                    ui.label('Serial Port').classes('label')
                    port_label = ui.label().classes('text-lg font-mono')
                    port_label.bind_text_from(
                        state, 'serial_port',
                        lambda p: p if p else 'Not configured'
                    )

                # Last communication
                with ui.column().classes('gap-1'):
                    ui.label('Data Freshness').classes('label')
                    fresh_label = ui.label().classes('text-lg')

                    def update_freshness():
                        if state.is_stale:
                            fresh_label.text = 'Stale'
                            fresh_label.classes(add='text-warning')
                            fresh_label.classes(remove='text-success')
                        else:
                            fresh_label.text = 'Current'
                            fresh_label.classes(add='text-success')
                            fresh_label.classes(remove='text-warning')

                    update_freshness()

                    def on_fresh_change(field, value):
                        if field == 'is_stale':
                            update_freshness()

                    state.add_listener(on_fresh_change)

            # Error message (if any)
            error_container = ui.column().classes('w-full mt-2')
            with error_container:
                error_label = ui.label().classes('text-error')
                error_label.bind_text_from(
                    state, 'connection_error',
                    lambda e: e if e else ''
                )

            def update_error_visibility():
                error_container.set_visibility(bool(state.connection_error))

            update_error_visibility()

            def on_error_change(field, value):
                if field == 'connection_error':
                    update_error_visibility()

            state.add_listener(on_error_change)

    return container


def _status_block(
    state: TelescopeState,
    field: str,
    label: str,
    true_text: str,
    false_text: str,
    true_class: str = 'indicator-ok',
    false_class: str = 'indicator-inactive',
) -> ui.element:
    """Create a status indicator block."""
    with ui.column().classes('gap-1') as block:
        ui.label(label).classes('label')
        with ui.row().classes('items-center gap-2'):
            ind = ui.element('span').classes('indicator')
            text = ui.label().classes('text-lg')

            def update():
                value = getattr(state, field)
                ind.classes(remove=f'{true_class} {false_class}')
                if value:
                    ind.classes(add=true_class)
                    text.text = true_text
                else:
                    ind.classes(add=false_class)
                    text.text = false_text

            update()

            def on_change(f, v):
                if f == field:
                    update()

            state.add_listener(on_change)

    return block


def _format_lat(lat: float) -> str:
    """Format latitude with N/S direction."""
    direction = 'N' if lat >= 0 else 'S'
    lat = abs(lat)
    deg = int(lat)
    min_val = (lat - deg) * 60
    return f"{deg}° {min_val:.3f}' {direction}"


def _format_lon(lon: float) -> str:
    """Format longitude with E/W direction."""
    direction = 'E' if lon >= 0 else 'W'
    lon = abs(lon)
    deg = int(lon)
    min_val = (lon - deg) * 60
    return f"{deg}° {min_val:.3f}' {direction}"
