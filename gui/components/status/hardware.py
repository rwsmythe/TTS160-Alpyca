# -*- coding: utf-8 -*-
"""
Hardware Status Component

Shows park/home status, motor states, and GPS status.
"""

from nicegui import ui

from ...state import TelescopeState


def hardware_status(state: TelescopeState) -> ui.element:
    """Display hardware state.

    Shows:
    - Park/Home status
    - Motor states (when available)
    - GPS fix status (if enabled)

    This is a Layer 2 component (expanded view).

    Args:
        state: Telescope state instance.

    Returns:
        Container element with hardware status.
    """
    with ui.card().classes('gui-card w-full disclosure-2') as container:
        ui.label('Hardware').classes('section-header')

        with ui.column().classes('gap-3'):
            # Park/Home status row
            with ui.row().classes('gap-4'):
                # Park status
                with ui.row().classes('items-center gap-2'):
                    park_ind = ui.element('span').classes('indicator')
                    park_label = ui.label()

                    def update_park():
                        park_ind.classes(
                            remove='indicator-ok indicator-inactive'
                        )
                        if state.at_park:
                            park_ind.classes(add='indicator-ok')
                            park_label.text = 'Parked'
                        else:
                            park_ind.classes(add='indicator-inactive')
                            park_label.text = 'Not parked'

                    update_park()

                    def on_park_change(field, value):
                        if field == 'at_park':
                            update_park()

                    state.add_listener(on_park_change)

                # Home status
                with ui.row().classes('items-center gap-2'):
                    home_ind = ui.element('span').classes('indicator')
                    home_label = ui.label()

                    def update_home():
                        home_ind.classes(
                            remove='indicator-ok indicator-inactive'
                        )
                        if state.at_home:
                            home_ind.classes(add='indicator-ok')
                            home_label.text = 'At home'
                        else:
                            home_ind.classes(add='indicator-inactive')
                            home_label.text = 'Not at home'

                    update_home()

                    def on_home_change(field, value):
                        if field == 'at_home':
                            update_home()

                    state.add_listener(on_home_change)

            # GPS status (only shown if GPS enabled)
            gps_container = ui.column().classes('w-full')
            with gps_container:
                ui.separator().classes('my-1')
                ui.label('GPS').classes('text-sm font-medium')

                with ui.row().classes('items-center gap-4'):
                    # GPS fix indicator
                    with ui.row().classes('items-center gap-2'):
                        gps_ind = ui.element('span').classes('indicator')
                        gps_label = ui.label()

                        def update_gps():
                            gps_ind.classes(
                                remove='indicator-ok indicator-warning indicator-inactive'
                            )
                            if state.gps_fix:
                                gps_ind.classes(add='indicator-ok')
                                gps_label.text = 'Fix acquired'
                            elif state.gps_enabled:
                                gps_ind.classes(add='indicator-warning indicator-pulse')
                                gps_label.text = 'Searching...'
                            else:
                                gps_ind.classes(add='indicator-inactive')
                                gps_label.text = 'Disabled'

                        update_gps()

                        def on_gps_change(field, value):
                            if field in ('gps_enabled', 'gps_fix'):
                                update_gps()

                        state.add_listener(on_gps_change)

                    # Satellite count
                    with ui.row().classes('items-center gap-1'):
                        ui.icon('satellite_alt').classes('text-sm')
                        sat_label = ui.label().classes('mono text-sm')
                        sat_label.bind_text_from(
                            state, 'gps_satellites',
                            lambda s: str(s)
                        )

            def update_gps_visibility():
                gps_container.set_visibility(state.gps_enabled)

            update_gps_visibility()

            def on_gps_enable_change(field, value):
                if field == 'gps_enabled':
                    update_gps_visibility()

            state.add_listener(on_gps_enable_change)

    return container


def park_status_compact(state: TelescopeState) -> ui.element:
    """Compact park status for header/footer.

    Args:
        state: Telescope state instance.

    Returns:
        Container element.
    """
    with ui.row().classes('items-center gap-2') as container:
        # Only show when parked
        park_badge = ui.badge('PARKED').props('color=primary')

        def update():
            park_badge.set_visibility(state.at_park)

        update()

        def on_change(field, value):
            if field == 'at_park':
                update()

        state.add_listener(on_change)

    return container


def motors_status(state: TelescopeState) -> ui.element:
    """Motor status display (Layer 3).

    Shows individual motor states when available.

    Args:
        state: Telescope state instance.

    Returns:
        Container element.
    """
    with ui.column().classes('w-full disclosure-3') as container:
        ui.label('Motors').classes('text-sm font-medium')

        with ui.row().classes('items-center gap-2'):
            motor_ind = ui.element('span').classes('indicator')
            motor_label = ui.label()

            def update():
                motor_ind.classes(
                    remove='indicator-ok indicator-inactive'
                )
                if state.motors_enabled:
                    motor_ind.classes(add='indicator-ok')
                    motor_label.text = 'Enabled'
                else:
                    motor_ind.classes(add='indicator-inactive')
                    motor_label.text = 'Disabled'

            update()

            def on_change(field, value):
                if field == 'motors_enabled':
                    update()

            state.add_listener(on_change)

    return container
