# -*- coding: utf-8 -*-
"""
Position Display Component

Primary status display showing telescope position coordinates.
"""

from typing import Optional
from nicegui import ui

from ..common import card, coordinate_display, angle_display, value_display
from ...state import TelescopeState, format_ra, format_dec, format_sidereal_time


def position_display(state: TelescopeState) -> ui.element:
    """Display current telescope position.

    Shows:
    - RA/Dec in HMS/DMS format (primary)
    - Alt/Az in degrees (secondary)
    - Local sidereal time
    - Pier side indicator

    Updates at 1-2 Hz for smooth perception.

    Args:
        state: Telescope state instance.

    Returns:
        Container element with position displays.
    """
    with ui.card().classes('gui-card w-full') as container:
        ui.label('Position').classes('section-header')

        # Main coordinate grid
        with ui.grid(columns=2).classes('w-full gap-4'):
            # RA/Dec column
            with ui.column().classes('gap-2'):
                # Right Ascension
                with ui.column().classes('gap-0'):
                    ui.label('RA').classes('label')
                    ra_label = ui.label().classes('value-large mono')
                    ra_label.bind_text_from(state, 'ra_hours', format_ra)

                # Declination
                with ui.column().classes('gap-0'):
                    ui.label('Dec').classes('label')
                    dec_label = ui.label().classes('value-large mono')
                    dec_label.bind_text_from(state, 'dec_degrees', format_dec)

            # Alt/Az column
            with ui.column().classes('gap-2'):
                # Altitude
                with ui.column().classes('gap-0'):
                    ui.label('Alt').classes('label')
                    alt_label = ui.label().classes('value-normal mono')
                    alt_label.bind_text_from(
                        state, 'alt_degrees',
                        lambda d: f"{d:.1f}°"
                    )

                # Azimuth
                with ui.column().classes('gap-0'):
                    ui.label('Az').classes('label')
                    az_label = ui.label().classes('value-normal mono')
                    az_label.bind_text_from(
                        state, 'az_degrees',
                        lambda d: f"{d:.1f}°"
                    )

        # Separator
        ui.separator().classes('my-2')

        # Secondary info row
        with ui.row().classes('w-full justify-between items-center'):
            # Sidereal time
            with ui.column().classes('gap-0'):
                ui.label('LST').classes('label')
                lst_label = ui.label().classes('value-small mono')
                lst_label.bind_text_from(
                    state, 'sidereal_time',
                    format_sidereal_time
                )

            # Pier side
            with ui.column().classes('gap-0'):
                ui.label('Pier').classes('label')
                pier_label = ui.label().classes('value-small mono')
                pier_label.bind_text_from(
                    state, 'pier_side',
                    lambda p: p.capitalize() if p else 'Unknown'
                )

    return container


def compact_position_display(state: TelescopeState) -> ui.element:
    """Compact position display for smaller spaces.

    Shows RA/Dec in a single row with minimal styling.

    Args:
        state: Telescope state instance.

    Returns:
        Container element with compact display.
    """
    with ui.row().classes('items-center gap-4') as container:
        # RA
        with ui.row().classes('items-baseline gap-1'):
            ui.label('RA').classes('label')
            ra_label = ui.label().classes('mono')
            ra_label.bind_text_from(state, 'ra_hours', format_ra)

        # Dec
        with ui.row().classes('items-baseline gap-1'):
            ui.label('Dec').classes('label')
            dec_label = ui.label().classes('mono')
            dec_label.bind_text_from(state, 'dec_degrees', format_dec)

    return container


def altaz_display(state: TelescopeState) -> ui.element:
    """Alt/Az only display.

    Args:
        state: Telescope state instance.

    Returns:
        Container element.
    """
    with ui.row().classes('items-center gap-4') as container:
        # Altitude
        with ui.row().classes('items-baseline gap-1'):
            ui.label('Alt').classes('label')
            alt_label = ui.label().classes('mono')
            alt_label.bind_text_from(
                state, 'alt_degrees',
                lambda d: f"{d:.1f}°"
            )

        # Azimuth
        with ui.row().classes('items-baseline gap-1'):
            ui.label('Az').classes('label')
            az_label = ui.label().classes('mono')
            az_label.bind_text_from(
                state, 'az_degrees',
                lambda d: f"{d:.1f}°"
            )

    return container
