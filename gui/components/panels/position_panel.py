# -*- coding: utf-8 -*-
"""
Position Detail Panel

Full position information with coordinates, sidereal time, and orientation.
"""

from nicegui import ui

from ...state import (
    TelescopeState,
    format_ra,
    format_dec,
    format_sidereal_time,
)


def position_panel(state: TelescopeState) -> ui.element:
    """Position detail panel.

    Shows:
    - RA/Dec (large, primary)
    - Alt/Az
    - Local sidereal time
    - Pier side with meridian info
    - Hour angle

    Args:
        state: Telescope state instance.

    Returns:
        Panel container element.
    """
    with ui.column().classes('w-full gap-4') as container:
        # Equatorial Coordinates card
        with ui.card().classes('gui-card w-full'):
            ui.label('Equatorial Coordinates').classes('section-header')

            with ui.row().classes('w-full gap-8'):
                # Right Ascension
                with ui.column().classes('gap-1'):
                    ui.label('Right Ascension').classes('label')
                    ra_label = ui.label().classes('text-3xl font-mono font-semibold')
                    ra_label.bind_text_from(state, 'ra_hours', format_ra)

                # Declination
                with ui.column().classes('gap-1'):
                    ui.label('Declination').classes('label')
                    dec_label = ui.label().classes('text-3xl font-mono font-semibold')
                    dec_label.bind_text_from(state, 'dec_degrees', format_dec)

        # Horizontal Coordinates card
        with ui.card().classes('gui-card w-full'):
            ui.label('Horizontal Coordinates').classes('section-header')

            with ui.row().classes('w-full gap-8'):
                # Altitude
                with ui.column().classes('gap-1'):
                    ui.label('Altitude').classes('label')
                    alt_label = ui.label().classes('text-2xl font-mono')
                    alt_label.bind_text_from(
                        state, 'alt_degrees',
                        lambda d: f"{d:+.2f}°"
                    )

                    # Horizon warning
                    horizon_warn = ui.label().classes('text-sm text-warning')

                    def update_horizon():
                        if state.alt_degrees < 0:
                            horizon_warn.text = '⚠ Below horizon'
                            horizon_warn.set_visibility(True)
                        elif state.alt_degrees < 10:
                            horizon_warn.text = '⚠ Low altitude'
                            horizon_warn.set_visibility(True)
                        else:
                            horizon_warn.set_visibility(False)

                    update_horizon()

                    def on_alt_change(field, value):
                        if field == 'alt_degrees':
                            update_horizon()

                    state.add_listener(on_alt_change)

                # Azimuth
                with ui.column().classes('gap-1'):
                    ui.label('Azimuth').classes('label')
                    az_label = ui.label().classes('text-2xl font-mono')
                    az_label.bind_text_from(
                        state, 'az_degrees',
                        lambda d: f"{d:.2f}°"
                    )

                    # Cardinal direction
                    cardinal_label = ui.label().classes('text-sm text-secondary')
                    cardinal_label.bind_text_from(
                        state, 'az_degrees',
                        _azimuth_to_cardinal
                    )

        # Time and Orientation card
        with ui.card().classes('gui-card w-full'):
            ui.label('Time & Orientation').classes('section-header')

            with ui.row().classes('w-full gap-8'):
                # Local Sidereal Time
                with ui.column().classes('gap-1'):
                    ui.label('Local Sidereal Time').classes('label')
                    lst_label = ui.label().classes('text-xl font-mono')
                    lst_label.bind_text_from(
                        state, 'sidereal_time',
                        format_sidereal_time
                    )

                # Hour Angle
                with ui.column().classes('gap-1'):
                    ui.label('Hour Angle').classes('label')
                    ha_label = ui.label().classes('text-xl font-mono')

                    def calc_hour_angle():
                        ha = state.sidereal_time - state.ra_hours
                        if ha < -12:
                            ha += 24
                        elif ha > 12:
                            ha -= 24
                        sign = '+' if ha >= 0 else '-'
                        ha = abs(ha)
                        h = int(ha)
                        m = int((ha - h) * 60)
                        return f"{sign}{h:02d}h {m:02d}m"

                    def update_ha():
                        ha_label.text = calc_hour_angle()

                    update_ha()

                    def on_ha_change(field, value):
                        if field in ('sidereal_time', 'ra_hours'):
                            update_ha()

                    state.add_listener(on_ha_change)

                # Pier Side
                with ui.column().classes('gap-1'):
                    ui.label('Pier Side').classes('label')
                    with ui.row().classes('items-center gap-2'):
                        pier_icon = ui.icon('swap_horiz').classes('text-xl')
                        pier_label = ui.label().classes('text-xl')

                        def update_pier():
                            pier = state.pier_side
                            if pier == 'east':
                                pier_label.text = 'East'
                                pier_icon.classes(remove='text-warning')
                            elif pier == 'west':
                                pier_label.text = 'West'
                                pier_icon.classes(remove='text-warning')
                            else:
                                pier_label.text = 'Unknown'
                                pier_icon.classes(add='text-warning')

                        update_pier()

                        def on_pier_change(field, value):
                            if field == 'pier_side':
                                update_pier()

                        state.add_listener(on_pier_change)

    return container


def _azimuth_to_cardinal(az: float) -> str:
    """Convert azimuth to cardinal direction."""
    directions = [
        (0, 'N'), (22.5, 'NNE'), (45, 'NE'), (67.5, 'ENE'),
        (90, 'E'), (112.5, 'ESE'), (135, 'SE'), (157.5, 'SSE'),
        (180, 'S'), (202.5, 'SSW'), (225, 'SW'), (247.5, 'WSW'),
        (270, 'W'), (292.5, 'WNW'), (315, 'NW'), (337.5, 'NNW'),
        (360, 'N'),
    ]

    az = az % 360
    for i in range(len(directions) - 1):
        if az < (directions[i][0] + directions[i + 1][0]) / 2:
            return directions[i][1]

    return 'N'
