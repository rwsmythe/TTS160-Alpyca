# -*- coding: utf-8 -*-
"""
Alpaca Server Status Panel

Shows server information: IP, port, status, and connections.
"""

import socket
from typing import Any, List, Optional, Tuple
from nicegui import ui

from ...state import TelescopeState


def get_local_ip_addresses() -> List[Tuple[str, str]]:
    """Get all local IP addresses.

    Returns:
        List of (interface_name, ip_address) tuples.
    """
    addresses = [('localhost', '127.0.0.1')]

    try:
        # Get hostname
        hostname = socket.gethostname()

        # Get all addresses for the hostname
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ['127.0.0.1', '0.0.0.0'] and not ip.startswith('127.'):
                addresses.append((hostname, ip))
    except Exception:
        pass

    # Also try getting addresses from all interfaces
    try:
        # Create a UDP socket to determine the default route IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            # Doesn't need to be reachable
            s.connect(('10.254.254.254', 1))
            ip = s.getsockname()[0]
            if ip not in [addr[1] for addr in addresses]:
                addresses.append(('default', ip))
        except Exception:
            pass
        finally:
            s.close()
    except Exception:
        pass

    return addresses


def server_status_panel(state: TelescopeState, config: Any) -> ui.element:
    """Display Alpaca server status information.

    Shows:
    - Server IP address and port
    - Server status (running/stopped)
    - Active client connections
    - Uptime
    - API version

    Args:
        state: Telescope state instance.
        config: Server configuration object.

    Returns:
        Container element with server status.
    """
    with ui.column().classes('w-full gap-4') as container:
        # Server Information Card
        with ui.card().classes('w-full'):
            ui.label('Server Information').classes('text-lg font-semibold mb-3')

            with ui.column().classes('gap-2'):
                # Status indicator
                with ui.row().classes('items-center gap-3'):
                    status_indicator = ui.element('span').classes('indicator indicator-ok')
                    ui.label('Server Running').classes('font-medium')

                ui.separator()

                # Get network addresses
                api_port = getattr(config, 'port', 5555)
                gui_port = getattr(config, 'gui_port', 8080)
                addresses = get_local_ip_addresses()

                # Server addresses section
                ui.label('Server Addresses').classes('text-sm font-medium mt-2')
                with ui.column().classes('gap-1 ml-2'):
                    for name, ip in addresses:
                        with ui.row().classes('items-center gap-2'):
                            ui.element('span').classes('indicator indicator-ok')
                            ui.label(f'{ip}').classes('mono')
                            if name != ip and name != 'default':
                                ui.label(f'({name})').classes('text-secondary text-xs')

                ui.separator()

                # Port configuration
                with ui.grid(columns=2).classes('w-full gap-2'):
                    ui.label('API Port:').classes('text-secondary')
                    ui.label(str(api_port)).classes('mono')

                    ui.label('GUI Port:').classes('text-secondary')
                    ui.label(str(gui_port)).classes('mono')

                    ui.label('Worker Threads:').classes('text-secondary')
                    ui.label(str(getattr(config, 'threads', 4))).classes('mono')

        # API Information Card
        with ui.card().classes('w-full'):
            ui.label('API Information').classes('text-lg font-semibold mb-3')

            with ui.grid(columns=2).classes('w-full gap-2'):
                ui.label('Protocol:').classes('text-secondary')
                ui.label('ASCOM Alpaca').classes('mono')

                ui.label('API Version:').classes('text-secondary')
                ui.label('v1').classes('mono')

                ui.label('Device Type:').classes('text-secondary')
                ui.label('Telescope').classes('mono')

                ui.label('Device Number:').classes('text-secondary')
                ui.label('0').classes('mono')

        # Endpoints Card (Expanded detail)
        with ui.card().classes('w-full disclosure-2'):
            ui.label('API Endpoints').classes('text-lg font-semibold mb-3')

            base_url = f"http://localhost:{getattr(config, 'port', 5555)}"

            with ui.column().classes('gap-1'):
                ui.label('Management:').classes('text-secondary text-sm')
                with ui.row().classes('gap-2 ml-4'):
                    ui.label(f'{base_url}/management/apiversions').classes('mono text-sm')

                ui.label('Telescope API:').classes('text-secondary text-sm mt-2')
                with ui.row().classes('gap-2 ml-4'):
                    ui.label(f'{base_url}/api/v1/telescope/0/...').classes('mono text-sm')

                ui.label('Discovery:').classes('text-secondary text-sm mt-2')
                with ui.row().classes('gap-2 ml-4'):
                    ui.label('UDP port 32227').classes('mono text-sm')

        # Connection Log Card (Advanced detail)
        with ui.card().classes('w-full disclosure-3'):
            ui.label('Recent Connections').classes('text-lg font-semibold mb-3')

            ui.label('Connection logging not yet implemented').classes('text-secondary italic')

    return container


def server_config_panel(config: Any, on_save: Any) -> ui.element:
    """Server configuration editing panel.

    Args:
        config: Server configuration object.
        on_save: Callback when config is saved.

    Returns:
        Container element with config form.
    """
    with ui.card().classes('w-full') as container:
        ui.label('Server Configuration').classes('text-lg font-semibold mb-3')

        with ui.column().classes('gap-3 w-full'):
            # Port configuration
            with ui.row().classes('items-center gap-4'):
                ui.label('API Port:').classes('w-24')
                port_input = ui.number(
                    value=getattr(config, 'port', 5555),
                    min=1024,
                    max=65535
                ).classes('w-32')

            with ui.row().classes('items-center gap-4'):
                ui.label('GUI Port:').classes('w-24')
                gui_port_input = ui.number(
                    value=getattr(config, 'gui_port', 8080),
                    min=1024,
                    max=65535
                ).classes('w-32')

            with ui.row().classes('items-center gap-4'):
                ui.label('Threads:').classes('w-24')
                threads_input = ui.number(
                    value=getattr(config, 'threads', 4),
                    min=1,
                    max=16
                ).classes('w-32')

            ui.separator()

            ui.label('Note: Changes require server restart').classes('text-secondary text-sm italic')

            with ui.row().classes('justify-end mt-2'):
                ui.button('Save', on_click=lambda: on_save({
                    'port': int(port_input.value),
                    'gui_port': int(gui_port_input.value),
                    'threads': int(threads_input.value),
                })).props('color=primary')

    return container
