# -*- coding: utf-8 -*-
"""
Navigation Component

Segmented button navigation for switching between functional groups.
Supports disclosure-level filtering.
"""

from typing import Callable, Dict, List, Optional
from nicegui import ui

from ..state import TelescopeState, DisclosureLevel


# Navigation group definitions
# Each group has: label, icon, minimum disclosure level
NAV_GROUPS = {
    'controls': {
        'label': 'Controls',
        'icon': 'gamepad',
        'min_level': DisclosureLevel.BASIC,
        'description': 'Slew, tracking, park controls',
    },
    'position': {
        'label': 'Position',
        'icon': 'explore',
        'min_level': DisclosureLevel.BASIC,
        'description': 'Coordinates and orientation',
    },
    'hardware': {
        'label': 'Hardware',
        'icon': 'memory',
        'min_level': DisclosureLevel.EXPANDED,
        'description': 'Mount and GPS status',
    },
    'alignment': {
        'label': 'Alignment',
        'icon': 'track_changes',
        'min_level': DisclosureLevel.EXPANDED,
        'description': 'Alignment monitor and QA',
    },
    'diagnostics': {
        'label': 'Diagnostics',
        'icon': 'bug_report',
        'min_level': DisclosureLevel.ADVANCED,
        'description': 'Logs, commands, raw data',
    },
}


def segmented_nav(
    state: TelescopeState,
    on_select: Callable[[str], None],
    initial_selection: str = 'controls',
) -> ui.element:
    """Segmented button navigation.

    Displays functional group buttons filtered by current disclosure level.
    Buttons appear/disappear as disclosure level changes.

    Args:
        state: Telescope state instance.
        on_select: Callback when a group is selected.
        initial_selection: Initially selected group ID.

    Returns:
        Navigation container element.
    """
    current_selection = {'value': initial_selection}
    buttons: Dict[str, ui.button] = {}

    # Define helper functions before they're used
    def is_group_visible(group_info: dict, level: DisclosureLevel) -> bool:
        """Check if a group should be visible at the given disclosure level."""
        min_level = group_info['min_level']
        return level.value >= min_level.value

    def select_group(group_id: str):
        """Handle group selection."""
        current_selection['value'] = group_id
        update_button_styles()
        on_select(group_id)

    def update_button_styles():
        """Update button styles based on selection."""
        for gid, btn in buttons.items():
            if gid == current_selection['value']:
                btn.classes(add='nav-segment-active')
                btn.props('color=primary')
            else:
                btn.classes(remove='nav-segment-active')
                btn.props(remove='color')

    def update_all_visibility():
        """Update all button visibility based on current disclosure level."""
        for group_id, group_info in NAV_GROUPS.items():
            btn = buttons.get(group_id)
            if btn:
                visible = is_group_visible(group_info, state.disclosure_level)
                btn.set_visibility(visible)

        # If current selection is no longer visible, select first visible
        current = current_selection['value']
        current_info = NAV_GROUPS.get(current)
        if current_info:
            if state.disclosure_level.value < current_info['min_level'].value:
                # Find first visible group
                for gid, ginfo in NAV_GROUPS.items():
                    if state.disclosure_level.value >= ginfo['min_level'].value:
                        select_group(gid)
                        break

    # Listen for disclosure level changes
    def on_disclosure_change(field, value):
        if field == 'disclosure_level':
            update_all_visibility()

    state.add_listener(on_disclosure_change)

    # Build the UI
    with ui.row().classes('nav-segmented w-full justify-center gap-0') as container:
        for group_id, group_info in NAV_GROUPS.items():
            # Create button
            btn = ui.button(
                group_info['label'],
                icon=group_info['icon'],
                on_click=lambda gid=group_id: select_group(gid),
            ).classes('nav-segment-btn')

            # Add tooltip
            btn.tooltip(group_info['description'])

            # Store reference
            buttons[group_id] = btn

            # Set initial visibility based on disclosure level
            visible = is_group_visible(group_info, state.disclosure_level)
            btn.set_visibility(visible)

    # Set initial styles
    update_button_styles()

    return container


def nav_group_content(
    group_id: str,
    state: TelescopeState,
    handlers: Dict[str, Callable],
) -> ui.element:
    """Create content for a navigation group.

    Args:
        group_id: The group ID to create content for.
        state: Telescope state instance.
        handlers: Command handlers.

    Returns:
        Content container element.
    """
    # Import panels here to avoid circular imports
    from .panels import (
        control_panel,
        diagnostics_panel,
    )
    from .status import (
        position_display,
        hardware_status,
        alignment_status,
    )
    from .panels.position_panel import position_panel
    from .panels.hardware_panel import hardware_panel
    from .panels.alignment_panel import alignment_panel

    with ui.column().classes('w-full') as container:
        if group_id == 'controls':
            control_panel(state, handlers)
        elif group_id == 'position':
            position_panel(state)
        elif group_id == 'hardware':
            hardware_panel(state)
        elif group_id == 'alignment':
            alignment_panel(state, handlers)
        elif group_id == 'diagnostics':
            diagnostics_panel(state, handlers.get('send_command'))

    return container
