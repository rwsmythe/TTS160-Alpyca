# -*- coding: utf-8 -*-
"""
Panel Components

Composite panels that combine multiple components.
"""

from .main_status import (
    main_status_panel,
    compact_status_panel,
    status_summary_row,
)
from .control_panel import (
    control_panel,
    minimal_control_panel,
)
from .diagnostics import (
    diagnostics_panel,
    DiagnosticsPanel,
)
from .config import (
    config_panel,
)
from .server_status import (
    server_status_panel,
    server_config_panel,
)
from .dashboard import (
    dashboard,
)
from .position_panel import (
    position_panel,
)
from .hardware_panel import (
    hardware_panel,
)
from .alignment_panel import (
    alignment_panel,
)

__all__ = [
    # Main status
    'main_status_panel',
    'compact_status_panel',
    'status_summary_row',
    # Control
    'control_panel',
    'minimal_control_panel',
    # Diagnostics
    'diagnostics_panel',
    'DiagnosticsPanel',
    # Config
    'config_panel',
    # Server
    'server_status_panel',
    'server_config_panel',
    # New layout panels
    'dashboard',
    'position_panel',
    'hardware_panel',
    'alignment_panel',
]
