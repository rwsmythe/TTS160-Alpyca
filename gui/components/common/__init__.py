# -*- coding: utf-8 -*-
"""
Common GUI Components

Shared, reusable components used throughout the GUI.
"""

from .card import card, card_section, info_row
from .value_display import (
    value_display,
    coordinate_display,
    angle_display,
    error_display,
)
from .indicator import (
    indicator,
    StatusIndicator,
    connection_indicator,
    tracking_indicator,
)
from .notification import (
    notify,
    notify_info,
    notify_success,
    notify_warning,
    notify_error,
    notify_critical,
    NotificationManager,
)

__all__ = [
    # Card
    'card',
    'card_section',
    'info_row',
    # Value display
    'value_display',
    'coordinate_display',
    'angle_display',
    'error_display',
    # Indicators
    'indicator',
    'StatusIndicator',
    'connection_indicator',
    'tracking_indicator',
    # Notifications
    'notify',
    'notify_info',
    'notify_success',
    'notify_warning',
    'notify_error',
    'notify_critical',
    'NotificationManager',
]
