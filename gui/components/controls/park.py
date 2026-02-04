# -*- coding: utf-8 -*-
"""
Park Controls Component

Park, unpark, set park position, and home controls.
"""

from typing import Callable
from nicegui import ui

from ...state import TelescopeState


def park_controls(
    state: TelescopeState,
    on_park: Callable[[], None],
    on_unpark: Callable[[], None],
    on_set_park: Callable[[], None],
    on_home: Callable[[], None],
) -> ui.element:
    """Park and home controls.

    Shows:
    - Park / Unpark button (toggles based on state)
    - Set Park Position button
    - Find Home button

    Args:
        state: Telescope state instance.
        on_park: Callback to park telescope.
        on_unpark: Callback to unpark telescope.
        on_set_park: Callback to set current position as park.
        on_home: Callback to find home position.

    Returns:
        Container element with park controls.
    """
    with ui.card().classes('gui-card w-full') as container:
        ui.label('Park & Home').classes('section-header')

        with ui.column().classes('gap-3'):
            # Park status indicator
            with ui.row().classes('items-center gap-2'):
                park_ind = ui.element('span').classes('indicator')
                park_label = ui.label()

                def update_park_status():
                    park_ind.classes(
                        remove='indicator-ok indicator-inactive'
                    )
                    if state.at_park:
                        park_ind.classes(add='indicator-ok')
                        park_label.text = 'Parked'
                    else:
                        park_ind.classes(add='indicator-inactive')
                        park_label.text = 'Not parked'

                update_park_status()

                def on_park_change(field, value):
                    if field == 'at_park':
                        update_park_status()

                state.add_listener(on_park_change)

            # Park/Unpark button
            park_btn = ui.button().classes('w-full')

            def update_park_button():
                if state.at_park:
                    park_btn.text = 'Unpark'
                    park_btn.on('click', on_unpark, [])
                else:
                    park_btn.text = 'Park'
                    park_btn.on('click', on_park, [])

            update_park_button()

            def on_park_btn_change(field, value):
                if field == 'at_park':
                    update_park_button()

            state.add_listener(on_park_btn_change)

            # Set Park Position (Layer 2)
            with ui.row().classes('w-full disclosure-2'):
                ui.button(
                    'Set Park Position',
                    on_click=on_set_park
                ).classes('w-full').props('outline')

            # Home controls
            ui.separator().classes('my-1')

            # Home status
            with ui.row().classes('items-center gap-2'):
                home_ind = ui.element('span').classes('indicator')
                home_label = ui.label()

                def update_home_status():
                    home_ind.classes(
                        remove='indicator-ok indicator-inactive'
                    )
                    if state.at_home:
                        home_ind.classes(add='indicator-ok')
                        home_label.text = 'At home'
                    else:
                        home_ind.classes(add='indicator-inactive')
                        home_label.text = 'Not at home'

                update_home_status()

                def on_home_change(field, value):
                    if field == 'at_home':
                        update_home_status()

                state.add_listener(on_home_change)

            # Find Home button
            ui.button(
                'Find Home',
                on_click=on_home
            ).classes('w-full')

    return container


def park_button(
    state: TelescopeState,
    on_park: Callable[[], None],
    on_unpark: Callable[[], None],
) -> ui.element:
    """Standalone park/unpark button.

    Args:
        state: Telescope state instance.
        on_park: Park callback.
        on_unpark: Unpark callback.

    Returns:
        Button element.
    """
    btn = ui.button().classes('w-full')

    def update():
        btn._event_listeners.clear()  # Clear previous listeners
        if state.at_park:
            btn.text = 'Unpark'
            btn.on('click', on_unpark)
        else:
            btn.text = 'Park'
            btn.on('click', on_park)

    update()

    def on_change(field, value):
        if field == 'at_park':
            update()

    state.add_listener(on_change)

    return btn


def home_button(on_home: Callable[[], None]) -> ui.button:
    """Standalone find home button.

    Args:
        on_home: Home callback.

    Returns:
        Button element.
    """
    return ui.button('Find Home', on_click=on_home)
