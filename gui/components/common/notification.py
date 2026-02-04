# -*- coding: utf-8 -*-
"""
Notification Component

Toast notifications with severity levels and optional actions.
"""

from typing import Callable, Optional
from nicegui import ui


# Severity configuration
SEVERITY_CONFIG = {
    'info': {
        'icon': 'info',
        'color': 'primary',
        'duration': 3000,
    },
    'success': {
        'icon': 'check_circle',
        'color': 'positive',
        'duration': 3000,
    },
    'warning': {
        'icon': 'warning',
        'color': 'warning',
        'duration': 5000,
    },
    'error': {
        'icon': 'error',
        'color': 'negative',
        'duration': 8000,
    },
    'critical': {
        'icon': 'report',
        'color': 'negative',
        'duration': None,  # Persistent
    },
}


def notify(
    message: str,
    severity: str = "info",
    duration: Optional[int] = None,
    action: Optional[Callable] = None,
    action_label: str = "Dismiss",
    position: str = "top-right",
) -> None:
    """Show a notification toast.

    Args:
        message: Notification text.
        severity: 'info', 'success', 'warning', 'error', or 'critical'.
        duration: Auto-dismiss time in ms. None for persistent.
                  If not specified, uses severity default.
        action: Optional callback for action button.
        action_label: Label for action button.
        position: Toast position ('top-right', 'top', 'bottom', etc.).
    """
    config = SEVERITY_CONFIG.get(severity, SEVERITY_CONFIG['info'])

    # Use provided duration or default from severity
    if duration is None:
        duration = config['duration']

    # Build notification options
    options = {
        'type': config['color'],
        'position': position,
        'timeout': duration if duration else 0,
        'closeBtn': duration is None,  # Show close for persistent
    }

    if action:
        options['actions'] = [{
            'label': action_label,
            'color': 'white',
            'handler': action,
        }]

    # Show notification
    ui.notify(
        message,
        type=config['color'],
        position=position,
        timeout=duration if duration else 0,
        close_button=duration is None,
    )


def notify_info(message: str, duration: int = 3000) -> None:
    """Show an info notification.

    Args:
        message: Notification text.
        duration: Auto-dismiss time in ms.
    """
    notify(message, severity='info', duration=duration)


def notify_success(message: str, duration: int = 3000) -> None:
    """Show a success notification.

    Args:
        message: Notification text.
        duration: Auto-dismiss time in ms.
    """
    notify(message, severity='success', duration=duration)


def notify_warning(message: str, duration: int = 5000) -> None:
    """Show a warning notification.

    Args:
        message: Notification text.
        duration: Auto-dismiss time in ms.
    """
    notify(message, severity='warning', duration=duration)


def notify_error(message: str, duration: int = 8000) -> None:
    """Show an error notification.

    Args:
        message: Notification text.
        duration: Auto-dismiss time in ms.
    """
    notify(message, severity='error', duration=duration)


def notify_critical(
    message: str,
    action: Optional[Callable] = None,
    action_label: str = "Dismiss",
) -> None:
    """Show a critical/persistent notification.

    Args:
        message: Notification text.
        action: Optional action callback.
        action_label: Action button label.
    """
    notify(
        message,
        severity='critical',
        duration=None,
        action=action,
        action_label=action_label,
    )


class NotificationManager:
    """Manager for coordinating notifications across the application."""

    def __init__(self, max_visible: int = 5):
        """Initialize notification manager.

        Args:
            max_visible: Maximum concurrent notifications.
        """
        self._max_visible = max_visible
        self._active_count = 0

    def info(self, message: str) -> None:
        """Show info notification."""
        notify_info(message)

    def success(self, message: str) -> None:
        """Show success notification."""
        notify_success(message)

    def warning(self, message: str) -> None:
        """Show warning notification."""
        notify_warning(message)

    def error(self, message: str) -> None:
        """Show error notification."""
        notify_error(message)

    def critical(self, message: str, action: Optional[Callable] = None) -> None:
        """Show critical notification."""
        notify_critical(message, action)

    def connection_lost(self) -> None:
        """Show connection lost notification."""
        notify_error("Connection to telescope lost", duration=None)

    def connection_restored(self) -> None:
        """Show connection restored notification."""
        notify_success("Connection restored")

    def slew_complete(self, target: str = "") -> None:
        """Show slew complete notification."""
        msg = f"Slew to {target} complete" if target else "Slew complete"
        notify_success(msg)

    def slew_failed(self, reason: str = "") -> None:
        """Show slew failed notification."""
        msg = f"Slew failed: {reason}" if reason else "Slew failed"
        notify_error(msg)

    def alignment_alert(self, error_arcsec: float) -> None:
        """Show alignment health alert."""
        notify_warning(
            f"Alignment degradation detected: {error_arcsec:.0f}\" error",
            duration=None,
        )
