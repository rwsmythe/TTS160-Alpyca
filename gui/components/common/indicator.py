# -*- coding: utf-8 -*-
"""
Status Indicator Component

LED-style status indicators with optional pulse animation.
"""

from typing import Callable, Optional
from nicegui import ui


class StatusIndicator:
    """LED-style status indicator with reactive updates."""

    def __init__(
        self,
        status: str = "inactive",
        label: Optional[str] = None,
        pulse: bool = False,
        size: str = "normal",
    ):
        """Create a status indicator.

        Args:
            status: Initial status ('ok', 'warning', 'error', 'inactive').
            label: Optional label text beside indicator.
            pulse: Enable pulse animation when active.
            size: 'small', 'normal', or 'large'.
        """
        self._status = status
        self._label_text = label
        self._pulse = pulse
        self._size = size

        self._indicator: Optional[ui.element] = None
        self._label: Optional[ui.label] = None

        self._build()

    def _build(self) -> None:
        """Build the indicator UI."""
        size_px = {'small': 8, 'normal': 12, 'large': 16}.get(self._size, 12)

        with ui.row().classes('items-center gap-2') as self._container:
            # LED indicator
            self._indicator = ui.element('span').classes(
                f'indicator indicator-{self._status}'
            ).style(f'width: {size_px}px; height: {size_px}px')

            if self._pulse and self._status not in ('inactive',):
                self._indicator.classes(add='indicator-pulse')

            # Optional label
            if self._label_text:
                self._label = ui.label(self._label_text).classes('text-sm')

    def set_status(self, status: str) -> None:
        """Update indicator status.

        Args:
            status: New status ('ok', 'warning', 'error', 'inactive').
        """
        if self._indicator is None:
            return

        # Remove old status class
        self._indicator.classes(
            remove=f'indicator-{self._status} indicator-pulse'
        )

        self._status = status

        # Add new status class
        self._indicator.classes(add=f'indicator-{status}')

        if self._pulse and status not in ('inactive',):
            self._indicator.classes(add='indicator-pulse')

    def set_label(self, text: str) -> None:
        """Update label text.

        Args:
            text: New label text.
        """
        if self._label:
            self._label.text = text

    @property
    def status(self) -> str:
        """Get current status."""
        return self._status


def indicator(
    status: str = "inactive",
    label: Optional[str] = None,
    pulse: bool = False,
    size: str = "normal",
) -> StatusIndicator:
    """Create an LED-style status indicator.

    Args:
        status: Initial status ('ok', 'warning', 'error', 'inactive').
        label: Optional label text beside indicator.
        pulse: Enable pulse animation when active.
        size: 'small', 'normal', or 'large'.

    Returns:
        StatusIndicator instance.
    """
    return StatusIndicator(status, label, pulse, size)


def connection_indicator(
    connected: bool = False,
    label: bool = True,
    bind_from: Optional[tuple] = None,
) -> ui.element:
    """Create a connection status indicator.

    Args:
        connected: Initial connection state.
        label: Show "Connected"/"Disconnected" label.
        bind_from: Optional (obj, attr) tuple for reactive binding.

    Returns:
        Container element with indicator.
    """
    status = 'ok' if connected else 'inactive'
    label_text = 'Connected' if connected else 'Disconnected'

    with ui.row().classes('items-center gap-2') as container:
        ind_element = ui.element('span').classes(f'indicator indicator-{status}')

        if label:
            label_element = ui.label(label_text)

            if bind_from:
                obj, attr = bind_from

                def update_status(is_connected):
                    if is_connected:
                        ind_element.classes(remove='indicator-inactive')
                        ind_element.classes(add='indicator-ok')
                        return 'Connected'
                    else:
                        ind_element.classes(remove='indicator-ok')
                        ind_element.classes(add='indicator-inactive')
                        return 'Disconnected'

                label_element.bind_text_from(obj, attr, update_status)

    return container


def tracking_indicator(
    tracking: bool = False,
    slewing: bool = False,
    bind_from_tracking: Optional[tuple] = None,
    bind_from_slewing: Optional[tuple] = None,
) -> ui.element:
    """Create a tracking status indicator.

    Shows:
    - Green: Tracking active
    - Yellow pulse: Slewing
    - Inactive: Not tracking

    Args:
        tracking: Initial tracking state.
        slewing: Initial slewing state.
        bind_from_tracking: Optional (obj, attr) for tracking binding.
        bind_from_slewing: Optional (obj, attr) for slewing binding.

    Returns:
        Container element with indicator.
    """
    if slewing:
        status = 'warning'
        label_text = 'Slewing'
        pulse = True
    elif tracking:
        status = 'ok'
        label_text = 'Tracking'
        pulse = False
    else:
        status = 'inactive'
        label_text = 'Idle'
        pulse = False

    with ui.row().classes('items-center gap-2') as container:
        ind_element = ui.element('span').classes(f'indicator indicator-{status}')
        if pulse:
            ind_element.classes(add='indicator-pulse')

        label_element = ui.label(label_text)

        # Binding would need custom logic to combine tracking and slewing states
        # For now, manual updates are required

    return container
