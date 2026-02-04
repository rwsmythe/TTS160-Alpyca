# -*- coding: utf-8 -*-
"""
Value Display Component

Numeric and text value display with labels and consistent styling.
"""

from typing import Any, Callable, Optional, Union
from nicegui import ui


def value_display(
    label: str,
    value: Union[str, float, int] = "",
    unit: Optional[str] = None,
    format_spec: str = ".2f",
    monospace: bool = True,
    size: str = "normal",
    bind_from: Optional[tuple] = None,
) -> ui.element:
    """Display a labeled value with consistent styling.

    Args:
        label: Description text above/beside the value.
        value: The value to display (static if bind_from not provided).
        unit: Optional unit suffix (e.g., "°", "arcsec").
        format_spec: Python format specification for numeric values.
        monospace: Use monospace font for value.
        size: "small", "normal", or "large".
        bind_from: Optional (obj, attr, converter) tuple for reactive binding.

    Returns:
        Container element with label and value.
    """
    # Size classes
    size_classes = {
        'small': 'value-small',
        'normal': 'value-normal',
        'large': 'value-large',
    }
    value_class = size_classes.get(size, 'value-normal')

    if monospace:
        value_class += ' mono'

    with ui.column().classes('gap-0') as container:
        # Label
        ui.label(label).classes('label')

        # Value row
        with ui.row().classes('items-baseline gap-1'):
            if bind_from:
                obj, attr = bind_from[:2]
                converter = bind_from[2] if len(bind_from) > 2 else None

                value_label = ui.label().classes(value_class)

                if converter:
                    value_label.bind_text_from(obj, attr, converter)
                else:
                    # Default converter based on format_spec
                    def default_converter(v):
                        if isinstance(v, (int, float)):
                            return format(v, format_spec)
                        return str(v)
                    value_label.bind_text_from(obj, attr, default_converter)
            else:
                # Static value
                if isinstance(value, (int, float)):
                    display_value = format(value, format_spec)
                else:
                    display_value = str(value)
                ui.label(display_value).classes(value_class)

            # Unit suffix
            if unit:
                ui.label(unit).classes('label')

    return container


def coordinate_display(
    label: str,
    value_hours_or_deg: float = 0.0,
    is_ra: bool = True,
    bind_from: Optional[tuple] = None,
) -> ui.element:
    """Display a coordinate (RA in HMS or Dec in DMS).

    Args:
        label: Coordinate label (e.g., "RA", "Dec").
        value_hours_or_deg: Value in hours (RA) or degrees (Dec).
        is_ra: True for RA (hours), False for Dec (degrees).
        bind_from: Optional (obj, attr) tuple for reactive binding.

    Returns:
        Container element with formatted coordinate.
    """
    def format_ra(hours: float) -> str:
        h = int(hours)
        m = int((hours - h) * 60)
        s = ((hours - h) * 60 - m) * 60
        return f"{h:02d}h {m:02d}m {s:04.1f}s"

    def format_dec(degrees: float) -> str:
        sign = "+" if degrees >= 0 else "-"
        degrees = abs(degrees)
        d = int(degrees)
        m = int((degrees - d) * 60)
        s = ((degrees - d) * 60 - m) * 60
        return f"{sign}{d:02d}° {m:02d}' {s:04.1f}\""

    converter = format_ra if is_ra else format_dec

    with ui.column().classes('gap-0') as container:
        ui.label(label).classes('label')

        value_label = ui.label().classes('value-large mono')

        if bind_from:
            obj, attr = bind_from
            value_label.bind_text_from(obj, attr, converter)
        else:
            value_label.text = converter(value_hours_or_deg)

    return container


def angle_display(
    label: str,
    value_degrees: float = 0.0,
    precision: int = 1,
    bind_from: Optional[tuple] = None,
) -> ui.element:
    """Display an angle in degrees.

    Args:
        label: Angle label (e.g., "Alt", "Az").
        value_degrees: Value in degrees.
        precision: Decimal places.
        bind_from: Optional (obj, attr) tuple for reactive binding.

    Returns:
        Container element with angle display.
    """
    def format_angle(deg: float) -> str:
        return f"{deg:.{precision}f}°"

    with ui.column().classes('gap-0') as container:
        ui.label(label).classes('label')

        value_label = ui.label().classes('value-normal mono')

        if bind_from:
            obj, attr = bind_from
            value_label.bind_text_from(obj, attr, format_angle)
        else:
            value_label.text = format_angle(value_degrees)

    return container


def error_display(
    label: str,
    value_arcsec: float = 0.0,
    thresholds: tuple = (30, 60, 120),
    bind_from: Optional[tuple] = None,
) -> ui.element:
    """Display pointing error with color coding.

    Args:
        label: Error label.
        value_arcsec: Error value in arcseconds.
        thresholds: (good, warning, error) thresholds in arcsec.
        bind_from: Optional (obj, attr) tuple for reactive binding.

    Returns:
        Container element with color-coded error display.
    """
    good_thresh, warn_thresh, error_thresh = thresholds

    def format_error(arcsec: float) -> str:
        if abs(arcsec) >= 60:
            return f"{arcsec / 60:.1f}'"
        return f'{arcsec:.1f}"'

    def get_color_class(arcsec: float) -> str:
        arcsec = abs(arcsec)
        if arcsec < good_thresh:
            return 'text-green-500'
        elif arcsec < warn_thresh:
            return 'text-yellow-500'
        elif arcsec < error_thresh:
            return 'text-orange-500'
        return 'text-red-500'

    with ui.column().classes('gap-0') as container:
        ui.label(label).classes('label')

        value_label = ui.label().classes('value-normal mono')

        if bind_from:
            obj, attr = bind_from

            def update_error(arcsec):
                value_label.text = format_error(arcsec)
                # Update color class
                value_label.classes(replace=get_color_class(arcsec))

            # Initial update
            update_error(getattr(obj, attr))

            # Bind for updates (text only, color needs manual update)
            value_label.bind_text_from(obj, attr, format_error)
        else:
            value_label.text = format_error(value_arcsec)
            value_label.classes(add=get_color_class(value_arcsec))

    return container
