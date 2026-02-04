# -*- coding: utf-8 -*-
"""
Status Display Components

Components for displaying telescope status information.
"""

from .position import (
    position_display,
    compact_position_display,
    altaz_display,
)
from .tracking import (
    tracking_display,
    tracking_indicator_compact,
    slew_progress,
)
from .connection import (
    connection_status,
    connection_indicator_compact,
    data_staleness_indicator,
)
from .hardware import (
    hardware_status,
    park_status_compact,
    motors_status,
)
from .alignment import (
    alignment_status,
    alignment_indicator_compact,
)

__all__ = [
    # Position
    'position_display',
    'compact_position_display',
    'altaz_display',
    # Tracking
    'tracking_display',
    'tracking_indicator_compact',
    'slew_progress',
    # Connection
    'connection_status',
    'connection_indicator_compact',
    'data_staleness_indicator',
    # Hardware
    'hardware_status',
    'park_status_compact',
    'motors_status',
    # Alignment
    'alignment_status',
    'alignment_indicator_compact',
]
