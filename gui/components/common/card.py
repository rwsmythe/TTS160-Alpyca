# -*- coding: utf-8 -*-
"""
Card Component

Styled container with consistent appearance across themes.
"""

from typing import Optional
from nicegui import ui


def card(
    title: Optional[str] = None,
    collapsible: bool = False,
    level: int = 1,
    classes: str = "",
) -> ui.card:
    """Create a themed card container.

    Args:
        title: Optional card header text.
        collapsible: Allow collapse/expand toggle.
        level: Disclosure level (1=always visible, 2=expanded, 3=advanced).
        classes: Additional CSS classes.

    Returns:
        NiceGUI card element.
    """
    # Determine disclosure class
    disclosure_class = ""
    if level == 2:
        disclosure_class = "disclosure-2"
    elif level == 3:
        disclosure_class = "disclosure-3"

    card_classes = f"gui-card {disclosure_class} {classes}".strip()

    with ui.card().classes(card_classes) as container:
        if title:
            if collapsible:
                with ui.expansion(title).classes('w-full') as expansion:
                    expansion.props('dense')
                    # Content goes inside expansion
                    pass
            else:
                ui.label(title).classes('section-header')

    return container


def card_section(title: str, level: int = 1) -> ui.column:
    """Create a section within a card.

    Args:
        title: Section header text.
        level: Disclosure level.

    Returns:
        NiceGUI column for section content.
    """
    disclosure_class = ""
    if level == 2:
        disclosure_class = "disclosure-2"
    elif level == 3:
        disclosure_class = "disclosure-3"

    with ui.column().classes(f'w-full {disclosure_class}') as section:
        ui.label(title).classes('text-sm font-medium text-secondary mb-2')

    return section


def info_row(label: str, classes: str = "") -> ui.row:
    """Create a row for displaying info with label-value pairs.

    Args:
        label: Optional prefix label.
        classes: Additional CSS classes.

    Returns:
        NiceGUI row element.
    """
    return ui.row().classes(f'w-full justify-between items-center {classes}')
