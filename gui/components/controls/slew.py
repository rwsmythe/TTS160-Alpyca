# -*- coding: utf-8 -*-
"""
Slew Controls Component

Directional slew controls, speed selection, and GoTo functionality.
"""

from typing import Callable, Optional
from nicegui import ui

from ...state import TelescopeState


# Slew speed options
SLEW_SPEEDS = [
    ('Guide', 0),
    ('Center', 1),
    ('Find', 2),
    ('Max', 3),
]


def slew_controls(
    state: TelescopeState,
    on_slew_start: Callable[[str], None],
    on_slew_stop: Callable[[], None],
    on_goto: Callable[[float, float], None],
    on_speed_change: Callable[[int], None],
) -> ui.element:
    """Directional slew controls with speed selection.

    Shows:
    - N/S/E/W directional buttons (hold to slew)
    - Speed selector (Guide, Center, Find, Max)
    - Stop button (prominent)
    - GoTo input (RA/Dec)

    Args:
        state: Telescope state instance.
        on_slew_start: Callback with direction ('n', 's', 'e', 'w').
        on_slew_stop: Callback to stop slew.
        on_goto: Callback with (ra_hours, dec_degrees).
        on_speed_change: Callback with speed index (0-3).

    Returns:
        Container element with slew controls.
    """
    with ui.card().classes('gui-card w-full') as container:
        ui.label('Slew Controls').classes('section-header')

        with ui.column().classes('gap-4'):
            # Directional pad with speed selector
            with ui.row().classes('items-center gap-6'):
                # D-pad
                with ui.column().classes('items-center gap-1'):
                    # North button
                    btn_n = ui.button('N').classes('w-12 h-12')
                    btn_n.on('mousedown', lambda: on_slew_start('n'))
                    btn_n.on('mouseup', on_slew_stop)
                    btn_n.on('mouseleave', on_slew_stop)

                    # E/Stop/W row
                    with ui.row().classes('gap-1'):
                        btn_w = ui.button('W').classes('w-12 h-12')
                        btn_w.on('mousedown', lambda: on_slew_start('w'))
                        btn_w.on('mouseup', on_slew_stop)
                        btn_w.on('mouseleave', on_slew_stop)

                        # Center stop button
                        btn_stop = ui.button(icon='stop').classes(
                            'w-12 h-12 gui-button-stop'
                        )
                        btn_stop.on('click', on_slew_stop)

                        btn_e = ui.button('E').classes('w-12 h-12')
                        btn_e.on('mousedown', lambda: on_slew_start('e'))
                        btn_e.on('mouseup', on_slew_stop)
                        btn_e.on('mouseleave', on_slew_stop)

                    # South button
                    btn_s = ui.button('S').classes('w-12 h-12')
                    btn_s.on('mousedown', lambda: on_slew_start('s'))
                    btn_s.on('mouseup', on_slew_stop)
                    btn_s.on('mouseleave', on_slew_stop)

                # Speed selector (Layer 2)
                with ui.column().classes('gap-2 disclosure-2'):
                    ui.label('Speed').classes('label')
                    speed_select = ui.select(
                        options={i: name for name, i in SLEW_SPEEDS},
                        value=1,  # Default to Center
                        on_change=lambda e: on_speed_change(e.value)
                    ).classes('w-24')
                    speed_select.props('dense outlined')

            # GoTo controls (Layer 2)
            with ui.column().classes('gap-2 disclosure-2'):
                ui.separator().classes('my-2')
                ui.label('Go To Coordinates').classes('text-sm font-medium')

                # Coordinate inputs
                with ui.row().classes('gap-4'):
                    with ui.column().classes('gap-1'):
                        ui.label('RA (hours)').classes('label text-xs')
                        ra_input = ui.input(
                            placeholder='12.5 or 12h30m'
                        ).classes('w-32 gui-input')

                    with ui.column().classes('gap-1'):
                        ui.label('Dec (degrees)').classes('label text-xs')
                        dec_input = ui.input(
                            placeholder='+45.5 or +45°30\''
                        ).classes('w-32 gui-input')

                # GoTo button
                with ui.row().classes('gap-2'):
                    def do_goto():
                        try:
                            ra_text = ra_input.value.strip()
                            dec_text = dec_input.value.strip()

                            # Parse RA
                            ra = parse_ra(ra_text)
                            dec = parse_dec(dec_text)

                            if ra is not None and dec is not None:
                                on_goto(ra, dec)
                            else:
                                ui.notify('Invalid coordinates', type='warning')
                        except Exception as e:
                            ui.notify(f'Parse error: {e}', type='warning')

                    ui.button('Go To', on_click=do_goto).classes('gui-button')

            # Big stop button (always visible)
            ui.separator().classes('my-2')
            ui.button(
                'STOP ALL',
                on_click=on_slew_stop
            ).classes('w-full h-12 gui-button-stop text-lg font-bold')

    return container


def directional_pad(
    on_slew_start: Callable[[str], None],
    on_slew_stop: Callable[[], None],
    size: str = "normal",
) -> ui.element:
    """Standalone directional pad.

    Args:
        on_slew_start: Callback with direction.
        on_slew_stop: Callback to stop.
        size: 'small', 'normal', or 'large'.

    Returns:
        Container element.
    """
    sizes = {
        'small': 'w-10 h-10',
        'normal': 'w-12 h-12',
        'large': 'w-16 h-16',
    }
    btn_size = sizes.get(size, 'w-12 h-12')

    with ui.column().classes('items-center gap-1') as container:
        # North
        btn_n = ui.button('N').classes(btn_size)
        btn_n.on('mousedown', lambda: on_slew_start('n'))
        btn_n.on('mouseup', on_slew_stop)
        btn_n.on('mouseleave', on_slew_stop)

        # E/Stop/W
        with ui.row().classes('gap-1'):
            btn_w = ui.button('W').classes(btn_size)
            btn_w.on('mousedown', lambda: on_slew_start('w'))
            btn_w.on('mouseup', on_slew_stop)
            btn_w.on('mouseleave', on_slew_stop)

            btn_stop = ui.button(icon='stop').classes(f'{btn_size} gui-button-stop')
            btn_stop.on('click', on_slew_stop)

            btn_e = ui.button('E').classes(btn_size)
            btn_e.on('mousedown', lambda: on_slew_start('e'))
            btn_e.on('mouseup', on_slew_stop)
            btn_e.on('mouseleave', on_slew_stop)

        # South
        btn_s = ui.button('S').classes(btn_size)
        btn_s.on('mousedown', lambda: on_slew_start('s'))
        btn_s.on('mouseup', on_slew_stop)
        btn_s.on('mouseleave', on_slew_stop)

    return container


def stop_button(on_stop: Callable[[], None], size: str = "normal") -> ui.button:
    """Prominent stop button.

    Args:
        on_stop: Stop callback.
        size: 'small', 'normal', or 'large'.

    Returns:
        Button element.
    """
    sizes = {
        'small': 'h-8 text-sm',
        'normal': 'h-10 text-base',
        'large': 'h-14 text-lg font-bold',
    }
    btn_classes = sizes.get(size, 'h-10 text-base')

    return ui.button(
        'STOP',
        on_click=on_stop
    ).classes(f'w-full {btn_classes} gui-button-stop')


# Coordinate parsing helpers
def parse_ra(text: str) -> Optional[float]:
    """Parse RA from various formats.

    Accepts:
    - Decimal hours: "12.5"
    - HMS: "12h30m", "12h 30m 45s", "12:30:45"

    Args:
        text: RA text to parse.

    Returns:
        RA in decimal hours, or None if invalid.
    """
    text = text.strip().lower()
    if not text:
        return None

    try:
        # Try decimal first
        return float(text)
    except ValueError:
        pass

    # Try HMS format
    import re

    # Pattern: 12h30m45s or 12h 30m 45s
    match = re.match(r'(\d+)h\s*(\d+)m?\s*(\d*\.?\d*)s?', text)
    if match:
        h = int(match.group(1))
        m = int(match.group(2)) if match.group(2) else 0
        s = float(match.group(3)) if match.group(3) else 0
        return h + m / 60 + s / 3600

    # Pattern: 12:30:45
    match = re.match(r'(\d+):(\d+):?(\d*\.?\d*)', text)
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        s = float(match.group(3)) if match.group(3) else 0
        return h + m / 60 + s / 3600

    return None


def parse_dec(text: str) -> Optional[float]:
    """Parse Dec from various formats.

    Accepts:
    - Decimal degrees: "+45.5", "-30.25"
    - DMS: "+45°30'", "+45d30m45s"

    Args:
        text: Dec text to parse.

    Returns:
        Dec in decimal degrees, or None if invalid.
    """
    text = text.strip().lower()
    if not text:
        return None

    # Determine sign
    sign = 1
    if text.startswith('-'):
        sign = -1
        text = text[1:]
    elif text.startswith('+'):
        text = text[1:]

    try:
        # Try decimal first
        return sign * float(text)
    except ValueError:
        pass

    # Try DMS format
    import re

    # Pattern: 45°30'45" or 45d30m45s
    match = re.match(r'(\d+)[°d]\s*(\d+)[\'m]?\s*(\d*\.?\d*)[\"s]?', text)
    if match:
        d = int(match.group(1))
        m = int(match.group(2)) if match.group(2) else 0
        s = float(match.group(3)) if match.group(3) else 0
        return sign * (d + m / 60 + s / 3600)

    return None
