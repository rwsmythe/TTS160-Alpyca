"""
NiceGUI-based telescope control interface.

Provides a web-based GUI for controlling and monitoring the ALPACA telescope driver.
Runs in a separate thread alongside the main ALPACA server.
"""

import threading
from nicegui import ui, app
from telescope_data import DataManager
from telescope_commands import TelescopeCommands
from telescope import TelescopeMetadata
import numpy as np

class TelescopeInterface:
    """Main telescope GUI interface using NiceGUI."""

    def __init__(self, logger, port: int = 8080, bind_address: str = '0.0.0.0',
                 theme: str = 'dark', refresh_interval: float = 1.0):
        """
        Initialize the telescope interface.

        Args:
            logger: Shared logger instance
            port: Port number for GUI server (default: 8080)
            bind_address: Address to bind GUI server (default: '0.0.0.0')
            theme: Color theme - 'dark' or 'light' (default: 'dark')
            refresh_interval: Status update interval in seconds (default: 1.0)
        """
        self.logger = logger
        self.port = port
        self.bind_address = bind_address
        self.theme = theme
        self.refresh_interval = refresh_interval
        self.data_manager = DataManager(logger)
        self.commands = TelescopeCommands(logger, self.data_manager, self.force_status_update)

        # Start GPS manager if enabled (so fix can be acquired before mount connect)
        self._start_gps_manager()

        # UI component storage for updates
        self.ui_components = {
            'health_cards': {},
            'telescope_status': {},
            'position_displays': {},
            'connection_status': {},
            'system_stats': {}
        }

    def start_gui_server(self):
        """Start the NiceGUI server in current thread."""
        self.create_interface()

        # Start NiceGUI server (browser opening handled by app.py)
        ui.run(port=self.port, host=self.bind_address, show=False, reload=False)
        
    def create_interface(self):
        """Create the main interface layout."""
        # Configure page
        ui.page_title('Alpaca Telescope Driver')

        # Apply theme
        if self.theme == 'dark':
            ui.dark_mode(True)
        else:
            ui.dark_mode(False)
        
        # Header
        with ui.header(elevated=True).style('background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)'):
            ui.label(f'{TelescopeMetadata.Name} Telescope Driver').style('font-size: 1.5rem; font-weight: 600; color: white')
            with ui.row().style('margin-left: auto'):
                server_info = self.ui_components['connection_status']['server_info'] = ui.label().style('color: white; opacity: 0.9')
        
        # Main navigation tabs
        with ui.tabs().classes('w-full') as tabs:
            dashboard_tab = ui.tab('🏠 Dashboard')
            server_tab = ui.tab('⚙️ Server Config') 
            telescope_tab = ui.tab('🔭 Telescope Config')
            status_tab = ui.tab('📊 Telescope Status')
            
        with ui.tab_panels(tabs, value=dashboard_tab).classes('w-full'):
            with ui.tab_panel(dashboard_tab):
                self.create_dashboard()
            with ui.tab_panel(server_tab):
                self.create_server_config()
            with ui.tab_panel(telescope_tab):
                self.create_telescope_config()
            with ui.tab_panel(status_tab):
                self.create_telescope_status()
        
        # Footer with stop server
        with ui.footer().style('background: #f5f5f5; border-top: 1px solid #ddd; padding: 10px'):
            ui.button('🛑 Stop Server', 
                     on_click=self.confirm_stop_server,
                     color='red')
        
        # Start update timers
        self.start_update_timers()
        
        # Initial data load
        self.update_static_data()

    def force_status_update(self):
        """Force immediate status update"""
        self.update_system_data()

    def create_dashboard(self):
        """Create dashboard tab content."""
        with ui.column().classes('w-full max-w-6xl mx-auto p-4'):
            
            # Welcome section
            with ui.card().classes('w-full mb-6').style('background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white'):
                with ui.card_section():
                    ui.label(f'Welcome to {TelescopeMetadata.Description}').style('font-size: 1.8rem; font-weight: bold')
                    ui.label('Your telescope control system is running and ready')
                    with ui.row().style('margin-top: 15px; gap: 10px; opacity: 0.9'):
                        ui.label(f'Driver Version: {TelescopeMetadata.Version}')
                        ui.label('•')
                        server_label = self.ui_components['connection_status']['dashboard_server'] = ui.label()
            
            # System health section
            ui.label('System Health').classes('text-xl font-bold mb-4').style('border-bottom: 2px solid #667eea; padding-bottom: 8px')
            with ui.row().classes('w-full gap-4 mb-6'):
                self.create_health_card('🖥️', 'Server Status', 'server_running')
                self.create_health_card('📡', 'Discovery Service', 'discovery_active')
                self.create_health_card('🔭', 'Telescope', 'telescope_connected')
                self.create_health_card('🛰️', 'GPS Fix', 'gps_fix_ready')
                self.create_health_card('⚙️', 'Configuration', 'config_valid')
            
            # System statistics
            ui.label('System Statistics').classes('text-xl font-bold mb-4').style('border-bottom: 2px solid #667eea; padding-bottom: 8px')
            with ui.row().classes('w-full gap-4'):
                self.create_stat_card('Connected Clients', 'connected_clients')
                self.create_stat_card('Total Requests', 'total_requests')
                self.create_stat_card('Memory Usage', 'memory_usage')
                self.create_stat_card('Uptime', 'uptime')
    
    def create_server_config(self):
        """Create server configuration tab."""
        with ui.column().classes('w-full max-w-4xl mx-auto p-4'):
            
            # Server status section
            ui.label('Server Status').classes('text-xl font-bold mb-4').style('border-bottom: 2px solid #667eea; padding-bottom: 8px')
            with ui.row().classes('w-full gap-4 mb-6'):
                
                # Network info card
                with ui.card().classes('flex-1'):
                    with ui.card_section():
                        ui.label('Network Information').classes('text-lg font-semibold mb-3')
                        with ui.column().classes('gap-2'):
                            self.ui_components['system_stats']['ip_addresses'] = ui.label()
                            self.ui_components['system_stats']['port'] = ui.label()
                            self.ui_components['system_stats']['discovery_status'] = ui.label()
                
                # Server info card  
                with ui.card().classes('flex-1'):
                    with ui.card_section():
                        ui.label('Server Information').classes('text-lg font-semibold mb-3')
                        with ui.column().classes('gap-2'):
                            self.ui_components['system_stats']['uptime_detail'] = ui.label()
                            self.ui_components['system_stats']['connected_clients_detail'] = ui.label()
                            self.ui_components['system_stats']['memory_detail'] = ui.label()

                # Connected client detail
                with ui.card().classes('flex-1'):
                    with ui.card_section():
                        ui.label('Connected Clients').classes('text-lg font-semibold mb-3')
                        self.ui_components['system_stats']['client_list'] = ui.list().props('dense separator')
            
            # Configuration form
            ui.label('Configuration Settings').classes('text-xl font-bold mb-4').style('border-bottom: 2px solid #667eea; padding-bottom: 8px')
            with ui.card().classes('w-full'):
                with ui.card_section():
                    with ui.row().classes('w-full gap-4'):
                        ui.button('🔄 Reload Configuration', on_click=self.reload_server_config)
                    
                    ui.separator()
                    
                    with ui.grid(columns=2).classes('w-full gap-4'):
                        # Network settings
                        self.ui_components['config_forms'] = {}
                        
                        self.ui_components['config_forms']['ip_address'] = ui.input('IP Address', placeholder='0.0.0.0')
                        self.ui_components['config_forms']['port'] = ui.number('Port', value=11111, min=1, max=65535)
                        self.ui_components['config_forms']['location'] = ui.input('Location', placeholder='Observatory location')
                        self.ui_components['config_forms']['log_level'] = ui.select(['NONE', 'INFO', 'DEBUG'], value='INFO', label='Log Level')
                        self.ui_components['config_forms']['max_size_mb'] = ui.number('Max Log Size (MB)', value=10, min=1, max=1000)
                        self.ui_components['config_forms']['num_keep_logs'] = ui.number('Number of Logs to Keep', value=5, min=1, max=50)
                                              
                    with ui.row().classes('w-full'):
                        self.ui_components['config_forms']['log_to_stdout'] = ui.checkbox('Display log in console')
                            
                    
                    ui.separator()
                    
                    with ui.row().classes('gap-2'):
                        ui.button('💾 Save Configuration', on_click=self.save_server_config, color='primary')
                        ui.button('🔄 Restart Server', on_click=self.restart_server, color='orange')
    
    def create_telescope_config(self):
        """Create telescope configuration tab."""
        with ui.column().classes('w-full max-w-4xl mx-auto p-4'):
            
            # Connection status
            ui.label('Telescope Status').classes('text-xl font-bold mb-4').style('border-bottom: 2px solid #667eea; padding-bottom: 8px')
            with ui.card().classes('w-full mb-6'):
                with ui.card_section():
                    with ui.row().classes('items-center gap-4'):
                        self.ui_components['telescope_status']['config_connection'] = ui.label()
                        self.ui_components['telescope_status']['config_device_info'] = ui.label()
            
            # Configuration form
            ui.label('Telescope Configuration').classes('text-xl font-bold mb-4').style('border-bottom: 2px solid #667eea; padding-bottom: 8px')
            with ui.card().classes('w-full'):
                with ui.card_section():
                    with ui.row().classes('w-full gap-4 mb-4'):
                        ui.button('🔄 Reload Configuration', on_click=self.reload_telescope_config)
                        ui.button('🔌 Test Connection', on_click=self.test_telescope_connection)
                    
                    ui.separator()
                    
                    # Device settings
                    ui.label('Device Settings').classes('text-lg font-semibold mb-3')
                    self.ui_components['telescope_config'] = {}
                    
                    with ui.row().classes('w-full gap-4'):
                        port_select = ui.select([], label='Device Port').classes('flex-1')
                        self.ui_components['telescope_config']['dev_port'] = port_select
                    
                    ui.separator()
                    
                    # Site information
                    with ui.row().classes('gap-4 items-start'):
                        ui.label('Site Information').classes('text-lg font-semibold mb-3')
                        with ui.grid(columns=2).classes('w-full gap-4'):
                            self.ui_components['telescope_config']['site_elevation'] = ui.number('Site Elevation (meters)', step=0.1)
                        # Read-only coordinates (for now)
                        with ui.column():
                            ui.label('Site Latitude').classes('font-medium text-sm')
                            lat_display = ui.label('Loading...').classes('p-2 bg-gray-100 rounded border')
                            self.ui_components['telescope_config']['latitude_display'] = lat_display
                        
                        with ui.column():
                            ui.label('Site Longitude').classes('font-medium text-sm')
                            lon_display = ui.label('Loading...').classes('p-2 bg-gray-100 rounded border')
                            self.ui_components['telescope_config']['longitude_display'] = lon_display
                        
                        ui.separator()
                    
                    # Driver options  
                    ui.label('Driver Options').classes('text-lg font-semibold mb-3')
                    with ui.column().classes('gap-3'):
                        self.ui_components['telescope_config']['sync_time_on_connect'] = ui.checkbox('Sync time on connect')
                        self.ui_components['telescope_config']['pulse_guide_equatorial_frame'] = ui.checkbox('Pulse guide in equatorial frame')
                        self.ui_components['telescope_config']['pulse_guide_altitude_compensation'] = ui.checkbox('Pulse guide altitude compensation (Alt-Az frame only)')
                                                                                             
                    with ui.grid(columns=2).classes('w-full gap-4'):
                        self.ui_components['telescope_config']['pulse_guide_max_compensation'] = ui.number('Max Compensation (ms)', value=1000, min=100, max=10000, step=10)
                        self.ui_components['telescope_config']['pulse_guide_compensation_buffer'] = ui.number('Compensation Buffer (ms)', value=20, min=5, max=500, step=5)
                        self.ui_components['telescope_config']['slew_settle_time'] = ui.number('Slew Settle Time (seconds)', value=1, min=0, max=30)                  
                        
                    ui.separator()
                    
                    with ui.row().classes('gap-2'):
                        ui.button('💾 Save Configuration', on_click=self.save_telescope_config, color='primary')
    
    def create_telescope_status(self):
        """Create telescope status monitoring tab."""
        with ui.column().classes('w-full max-w-6xl mx-auto p-4'):
            
            # Connection panel
            ui.label('Connection Status').classes('text-xl font-bold mb-4').style('border-bottom: 2px solid #667eea; padding-bottom: 8px')
            with ui.card().classes('w-full mb-6'):
                with ui.card_section():
                    with ui.row().classes('items-center gap-6'):
                        self.ui_components['telescope_status']['main_connection'] = ui.label()
                        self.ui_components['telescope_status']['device_details'] = ui.column()
            
            # Position information
            ui.label('Current Position').classes('text-xl font-bold mb-4').style('border-bottom: 2px solid #667eea; padding-bottom: 8px')
            with ui.row().classes('w-full gap-4 mb-6'):
                
                # Equatorial coordinates
                with ui.card().classes('flex-1'):
                    with ui.card_section():
                        ui.label('Equatorial Coordinates').classes('text-lg font-semibold mb-3 text-center')
                        with ui.column().classes('gap-2'):
                            self.ui_components['position_displays']['ra'] = ui.label().style('font-family: monospace; font-size: 1.1rem')
                            self.ui_components['position_displays']['dec'] = ui.label().style('font-family: monospace; font-size: 1.1rem')
                
                # Horizontal coordinates
                with ui.card().classes('flex-1'):
                    with ui.card_section():
                        ui.label('Horizontal Coordinates').classes('text-lg font-semibold mb-3 text-center')
                        with ui.column().classes('gap-2'):
                            self.ui_components['position_displays']['alt'] = ui.label().style('font-family: monospace; font-size: 1.1rem')
                            self.ui_components['position_displays']['az'] = ui.label().style('font-family: monospace; font-size: 1.1rem')
                
                # Mechanical position
                with ui.card().classes('flex-1'):
                    with ui.card_section():
                        ui.label('Mechanical Position').classes('text-lg font-semibold mb-3 text-center')
                        with ui.column().classes('gap-2'):
                            self.ui_components['position_displays']['ra_ticks'] = ui.label().style('font-family: monospace; font-size: 1.1rem')
                            self.ui_components['position_displays']['dec_ticks'] = ui.label().style('font-family: monospace; font-size: 1.1rem')
            
            # Mount status
            ui.label('Mount Status').classes('text-xl font-bold mb-4').style('border-bottom: 2px solid #667eea; padding-bottom: 8px')
            with ui.card().classes('w-full mb-6'):
                with ui.card_section():
                    with ui.grid(columns=3).classes('w-full gap-4'):
                        self.ui_components['telescope_status']['tracking'] = ui.label()
                        self.ui_components['telescope_status']['slewing'] = ui.label()
                        self.ui_components['telescope_status']['parked'] = ui.label()
                        self.ui_components['telescope_status']['at_home'] = ui.label()
                        self.ui_components['telescope_status']['pier_side'] = ui.label()
                        self.ui_components['telescope_status']['guide_rate'] = ui.label()

            # Alignment Matrix
            ui.label('Alignment Matrix').classes('text-xl font-bold mb-4').style('border-bottom: 2px solid #667eea; padding-bottom: 8px')
            with ui.card().classes('w-full mb-6'):
                with ui.card_section():
                    ui.label('3×3 Transformation Matrix').classes('text-lg font-semibold mb-3 text-center')
                    with ui.row().classes('gap-4 items-start'):
                        # Matrix display
                        self.ui_components['telescope_status']['alignment_matrix'] = ui.grid(columns=3).classes('gap-2 justify-center')
                        # Condition number box
                        with ui.card().classes('min-w-48'):
                            with ui.card_section():
                                ui.label('Condition Numer').classes('text-md font-semibold mb-2 text-center')
                                self.ui_components['telescope_status']['condition_number'] = ui.label().style('font-family: monospace; font-size: 1.2rem; text-align: center')

            # GPS Status
            ui.label('GPS Status').classes('text-xl font-bold mb-4').style('border-bottom: 2px solid #667eea; padding-bottom: 8px')
            with ui.card().classes('w-full mb-6'):
                with ui.card_section():
                    with ui.row().classes('w-full gap-6'):
                        # GPS state and connection
                        with ui.column().classes('gap-2'):
                            self.ui_components['telescope_status']['gps_state'] = ui.label().style('font-size: 1.1rem')
                            self.ui_components['telescope_status']['gps_port'] = ui.label().style('font-family: monospace; opacity: 0.8')
                        # Fix quality and satellites
                        with ui.column().classes('gap-2'):
                            self.ui_components['telescope_status']['gps_fix'] = ui.label().style('font-family: monospace')
                            self.ui_components['telescope_status']['gps_satellites'] = ui.label().style('font-family: monospace')
                        # Position
                        with ui.column().classes('gap-2'):
                            self.ui_components['telescope_status']['gps_latitude'] = ui.label().style('font-family: monospace')
                            self.ui_components['telescope_status']['gps_longitude'] = ui.label().style('font-family: monospace')
                        # Last update
                        with ui.column().classes('gap-2'):
                            self.ui_components['telescope_status']['gps_last_fix'] = ui.label().style('font-family: monospace; opacity: 0.8')
                            self.ui_components['telescope_status']['gps_last_push'] = ui.label().style('font-family: monospace; opacity: 0.8')
                        # Manual push control
                        with ui.column().classes('gap-2 items-center'):
                            self.ui_components['telescope_status']['gps_push_button'] = ui.button(
                                '📍 Push Location',
                                on_click=self.manual_gps_push,
                                color='primary'
                            ).classes('w-32')
                            self.ui_components['telescope_status']['gps_push_status'] = ui.label().style(
                                'font-size: 0.8rem; opacity: 0.8'
                            )

            # Control panel
            ui.label('Telescope Control').classes('text-xl font-bold mb-4').style('border-bottom: 2px solid #667eea; padding-bottom: 8px')
            with ui.row().classes('w-full gap-4 mb-6'):
                
                # Connection control
                with ui.card().classes('flex-1'):
                    with ui.card_section():
                        ui.label('Connection').classes('text-lg font-semibold mb-3 text-center')
                        self.ui_components['telescope_status']['connect_button'] = ui.button('🔌 Connect', 
                                                                                           on_click=self.toggle_telescope_connection,
                                                                                           color='green').classes('w-full')
                
                # Movement control  
                with ui.card().classes('flex-1'):
                    with ui.card_section():
                        ui.label('Movement').classes('text-lg font-semibold mb-3 text-center')
                        with ui.column().classes('gap-2'):
                            self.ui_components['telescope_status']['park_button'] = ui.button('🏠 Park', 
                                                                                            on_click=lambda: self.commands.park_telescope(),
                                                                                            color='primary').classes('w-full')
                            self.ui_components['telescope_status']['home_button'] = ui.button('🎯 Find Home', 
                                                                                            on_click=lambda: self.commands.find_home(),
                                                                                            color='secondary').classes('w-full')
                
                # Tracking control
                with ui.card().classes('flex-1'):
                    with ui.card_section():
                        ui.label('Tracking').classes('text-lg font-semibold mb-3 text-center')
                        self.ui_components['telescope_status']['tracking_button'] = ui.button('▶️ Start Tracking', 
                                                                                             on_click=self.toggle_tracking,
                                                                                             color='green').classes('w-full')
                
                # Emergency control
                with ui.card().classes('flex-1'):
                    with ui.card_section():
                        ui.label('Emergency').classes('text-lg font-semibold mb-3 text-center')
                        ui.button('🛑 Stop All Motion', 
                                 on_click=lambda: self.commands.abort_slew(),
                                 color='red').classes('w-full')
            
            # Messages area
            self.ui_components['telescope_status']['messages'] = ui.log().classes('w-full h-32')
    
    def create_health_card(self, icon, title, key):
        """Create a system health status card."""
        with ui.card().classes('flex-1'):
            with ui.card_section():
                with ui.row().classes('items-center gap-3'):
                    ui.label(icon).style('font-size: 2rem')
                    with ui.column():
                        ui.label(title).classes('font-semibold')
                        status_label = ui.label('Unknown').classes('text-sm')
                        self.ui_components['health_cards'][key] = status_label
    
    def create_stat_card(self, title, key):
        """Create a statistics display card."""
        with ui.card().classes('flex-1'):
            with ui.card_section().classes('text-center'):
                value_label = ui.label('--').classes('text-2xl font-bold text-blue-600')
                ui.label(title).classes('text-sm text-gray-600')
                self.ui_components['system_stats'][key] = value_label
    
    def start_update_timers(self):
        """Start the data update timers."""
        # High frequency updates (telescope position/status)
        ui.timer(self.refresh_interval, self.update_telescope_data)

        # Low frequency updates (system stats) - 10x slower than position updates
        ui.timer(self.refresh_interval * 10, self.update_system_data)
    
    def update_telescope_data(self):
        """Update high-frequency telescope data."""
        try:
            telescope_data = self.data_manager.get_telescope_status()
            position_data = self.data_manager.get_telescope_position()
            
            # Update connection status
            if 'main_connection' in self.ui_components['telescope_status']:
                connected = telescope_data.get('connected', False)
                status_text = '🟢 Connected' if connected else '🔴 Disconnected'
                self.ui_components['telescope_status']['main_connection'].set_text(status_text)
                
                # Update connection button
                if 'connect_button' in self.ui_components['telescope_status']:
                    btn = self.ui_components['telescope_status']['connect_button']
                    if connected:
                        if btn:
                            btn.set_text('🔌 Disconnect')
                            btn._props['color'] = 'orange'
                    else:
                        if btn:
                            btn.set_text('🔌 Connect')
                            btn._props['color'] = 'green'
            
            cond_text = "N/A"
            if 'alignment_matrix' in self.ui_components['telescope_status']:
                self.ui_components['telescope_status']['alignment_matrix'].clear()
                with self.ui_components['telescope_status']['alignment_matrix']:
                    for value in telescope_data.get('alignment_matrix',[0,0,0,0,0,0,0,0,0]):
                        ui.label(f'{value:.6f}').style('font-family: monospace; text-align: center; padding: 4px')

                alignment_matrix = np.array(telescope_data.get('alignment_matrix',[0,0,0,0,0,0,0,0,0])).reshape(3,3)
                try:
                    cond_num = np.linalg.cond(alignment_matrix)
                    if np.isinf(cond_num):
                        cond_text = "∞ (Zero Matrix)"
                    else:
                        cond_text = f'{cond_num:.2e}'
                except (np.linalg.LinAlgError, ValueError):
                    cond_text = "Error"

            self.ui_components['telescope_status']['condition_number'].set_text(cond_text)
            
            # Update position displays
            if position_data and 'ra' in self.ui_components['position_displays']:
                self.ui_components['position_displays']['ra'].set_text(f"RA: {position_data.get('ra_formatted', '--:--:--')}")
                self.ui_components['position_displays']['dec'].set_text(f"Dec: {position_data.get('dec_formatted', '--:--:--')}")
                self.ui_components['position_displays']['alt'].set_text(f"Alt: {position_data.get('altitude', 0):.4f}°")
                self.ui_components['position_displays']['az'].set_text(f"Az: {position_data.get('azimuth', 0):.4f}°")
                #self.ui_components['position_displays']['ra_ticks'].set_text(f"RA Ticks: {position_data.get('ra_ticks', '--')}")
                #self.ui_components['position_displays']['dec_ticks'].set_text(f"Dec Ticks: {position_data.get('dec_ticks', '--')}")

            
            # Update mount status
            if telescope_data and 'tracking' in self.ui_components['telescope_status']:
                tracking = telescope_data.get('tracking', False)
                slewing = telescope_data.get('is_slewing', False)
                parked = telescope_data.get('at_park', False)
                
                self.ui_components['telescope_status']['tracking'].set_text(
                    f"Tracking: {'🟢 ON' if tracking else '🔴 OFF'}")
                self.ui_components['telescope_status']['slewing'].set_text(
                    f"Slewing: {'🟢 YES' if slewing else '🔴 NO'}")
                self.ui_components['telescope_status']['parked'].set_text(
                    f"Parked: {'🟢 YES' if parked else '🔴 NO'}")
                
                # Update tracking button
                if 'tracking_button' in self.ui_components['telescope_status']:
                    btn = self.ui_components['telescope_status']['tracking_button']
                    if tracking:
                        if btn:
                            btn.set_text('⏸️ Stop Tracking')
                            btn._props['color'] = 'orange'
                    else:
                        if btn:
                            btn.set_text('▶️ Start Tracking')
                            btn._props['color'] = 'green'
                        
                # Update park button
                if 'park_button' in self.ui_components['telescope_status']:
                    btn = self.ui_components['telescope_status']['park_button']
                    if parked:
                        btn.set_text('🚀 Unpark')
                    else:
                        btn.set_text('🏠 Park')

            # Update GPS status
            self._update_gps_status()

        except Exception as e:
            if self.data_manager.telescope_cache:
                self.logger.error(f"Error updating telescope data: {e}")
    
    def update_system_data(self):
        """Update low-frequency system data."""
        try:
            system_data = self.data_manager.get_system_status()
            
            # Update health cards
            if 'server_running' in self.ui_components['health_cards']:
                self.ui_components['health_cards']['server_running'].set_text(
                    '🟢 Running' if system_data.get('server_running', True) else '🔴 Stopped')
                self.ui_components['health_cards']['discovery_active'].set_text(
                    '🟢 Active' if system_data.get('discovery_active', True) else '🔴 Inactive')
                self.ui_components['health_cards']['telescope_connected'].set_text(
                    '🟢 Connected' if system_data.get('telescope_connected', False) else '🔴 Disconnected')
                self.ui_components['health_cards']['config_valid'].set_text(
                    '🟢 Valid' if system_data.get('config_valid', True) else '🔴 Invalid')

                # Update GPS fix status
                if 'gps_fix_ready' in self.ui_components['health_cards']:
                    gps_data = self.data_manager.get_gps_status()
                    if not gps_data.get('enabled', False):
                        self.ui_components['health_cards']['gps_fix_ready'].set_text('⚫ Disabled')
                    elif gps_data.get('has_fix', False):
                        self.ui_components['health_cards']['gps_fix_ready'].set_text('🟢 Ready')
                    elif gps_data.get('state') == 'ERROR':
                        self.ui_components['health_cards']['gps_fix_ready'].set_text('🔴 Error')
                    else:
                        self.ui_components['health_cards']['gps_fix_ready'].set_text('🟡 Acquiring')

            # Update statistics
            if 'connected_clients' in self.ui_components['system_stats']:
                self.ui_components['system_stats']['connected_clients'].set_text(
                    str(system_data.get('connected_clients', 0)))
                self.ui_components['system_stats']['total_requests'].set_text(
                    str(system_data.get('total_requests', 0)))
                self.ui_components['system_stats']['memory_usage'].set_text(
                    system_data.get('memory_usage', 'Unknown'))
                self.ui_components['system_stats']['uptime'].set_text(
                    system_data.get('uptime', 'Unknown'))
                client_list = system_data.get('connected_client_list', [])
                self.ui_components['system_stats']['client_list'].clear()
                if client_list:
                    for client_dict in client_list:
                        client_id = list(client_dict.keys())[0]
                        remote_addr = client_dict[client_id]
                        with self.ui_components['system_stats']['client_list']:
                            ui.item(f'Client ID: {client_id} ({remote_addr})')

            #Update server config page details
            if 'system_stats' in self.ui_components:
                stats = self.ui_components['system_stats']
                
                # Network info
                if 'ip_addresses' in stats:
                    stats['ip_addresses'].set_text(f"IP Addresses: {', '.join(system_data.get('current_ips', ['Unknown']))}")
                if 'port' in stats:
                    stats['port'].set_text(f"Port: {self.data_manager.server_config.port}")
                if 'discovery_status' in stats:
                    active = system_data.get('discovery_active', False)
                    stats['discovery_status'].set_text(f"Discovery Status: {'Active' if active else 'Inactive'}")
                
                # Server info  
                if 'uptime_detail' in stats:
                    stats['uptime_detail'].set_text(f"Uptime: {system_data.get('uptime', 'Unknown')}")
                if 'connected_clients_detail' in stats:
                    stats['connected_clients_detail'].set_text(f"Connected Clients: {system_data.get('connected_clients', 0)}")
                if 'memory_detail' in stats:
                    stats['memory_detail'].set_text(f"Memory Usage: {system_data.get('memory_usage', 'Unknown')}")
            
        except Exception as e:
            self.logger.error(f"Error updating system data: {e}")
    
    def update_static_data(self):
        """Update static configuration data."""
        try:
            server_config = self.data_manager.get_server_config()
            telescope_config = self.data_manager.get_telescope_config()

            # Update server info displays
            server_info = f"{server_config['ip_address']}:{server_config['port']}"
            if 'server_info' in self.ui_components['connection_status']:
                self.ui_components['connection_status']['server_info'].set_text(server_info)
            if 'dashboard_server' in self.ui_components['connection_status']:
                self.ui_components['connection_status']['dashboard_server'].set_text(f"Server: {server_info}")
            
            # Update config form values
            if 'config_forms' in self.ui_components:
                for field in ['ip_address', 'port', 'location', 'log_level', 'max_size_mb', 'num_keep_logs', 'log_to_stdout']:
                    if field in self.ui_components['config_forms'] and field in server_config:
                        if field == 'log_level':
                            # Convert numeric level to string
                            level_map = {10: 'DEBUG', 20: 'INFO', 0: 'NONE'}
                            string_level = level_map.get(server_config[field], 'INFO')
                            self.ui_components['config_forms'][field].set_value(string_level)
                        else:
                            self.ui_components['config_forms'][field].set_value(server_config[field])

            # Update telescope config
            if 'telescope_config' in self.ui_components:
                tel_forms = self.ui_components['telescope_config']
                
                for key, value in telescope_config.items():
                    if key in tel_forms:
                        if key == 'dev_port':
                            # Get available ports
                            available_ports = telescope_config['available_ports']
                            
                            # Create options for dropdown (device name as both key and display)
                            port_options = [f"{port['device']} - {port['description']}" for port in available_ports]
                            
                            # Set options and value
                            tel_forms[key].set_options(port_options)
                            matching_option = next((opt for opt in port_options if opt.startswith(value)), None)
                            if matching_option:
                                tel_forms[key].set_value(matching_option)
                        elif hasattr(tel_forms[key], 'set_value'):
                            tel_forms[key].set_value(value)
                        else:
                            tel_forms[key].set_text(value)
            ui.update()

        except Exception as e:
            self.logger.error(f"Error updating static data: {e}")

    def _update_gps_status(self):
        """Update GPS status display in the telescope status tab."""
        try:
            gps_data = self.data_manager.get_gps_status()

            if 'gps_state' not in self.ui_components['telescope_status']:
                return

            if not gps_data.get('enabled', False):
                self.ui_components['telescope_status']['gps_state'].set_text('📡 GPS: Disabled')
                self.ui_components['telescope_status']['gps_port'].set_text('')
                self.ui_components['telescope_status']['gps_fix'].set_text('')
                self.ui_components['telescope_status']['gps_satellites'].set_text('')
                self.ui_components['telescope_status']['gps_latitude'].set_text('')
                self.ui_components['telescope_status']['gps_longitude'].set_text('')
                self.ui_components['telescope_status']['gps_last_fix'].set_text('')
                self.ui_components['telescope_status']['gps_last_push'].set_text('')
                return

            # State with appropriate icon
            state = gps_data.get('state', 'UNKNOWN')
            state_icons = {
                'DISABLED': '⚫',
                'DISCONNECTED': '🔴',
                'CONNECTING': '🟡',
                'CONNECTED': '🟢',
                'ACQUIRING_FIX': '🟡',
                'FIX_VALID': '🟢',
                'ERROR': '🔴'
            }
            icon = state_icons.get(state, '⚪')
            state_display = gps_data.get('state_display', state)

            # Show error message if in error state
            error_msg = gps_data.get('error_message', '')
            if state == 'ERROR' and error_msg:
                self.ui_components['telescope_status']['gps_state'].set_text(f'{icon} GPS: {error_msg}')
            else:
                self.ui_components['telescope_status']['gps_state'].set_text(f'{icon} GPS: {state_display}')

            # Port
            port = gps_data.get('port', '')
            self.ui_components['telescope_status']['gps_port'].set_text(f'Port: {port}' if port else 'Port: Not configured')

            # Fix quality
            fix_quality = gps_data.get('fix_quality', 'UNKNOWN')
            has_fix = gps_data.get('has_fix', False)
            fix_icon = '🟢' if has_fix else '🔴'
            self.ui_components['telescope_status']['gps_fix'].set_text(f'{fix_icon} Fix: {fix_quality}')

            # Satellites
            satellites = gps_data.get('satellites', 0)
            hdop = gps_data.get('hdop')
            hdop_str = f' (HDOP: {hdop:.1f})' if hdop else ''
            self.ui_components['telescope_status']['gps_satellites'].set_text(f'Satellites: {satellites}{hdop_str}')

            # Position
            lat = gps_data.get('latitude')
            lon = gps_data.get('longitude')
            if lat is not None and lon is not None:
                lat_dir = 'N' if lat >= 0 else 'S'
                lon_dir = 'E' if lon >= 0 else 'W'
                self.ui_components['telescope_status']['gps_latitude'].set_text(f'Lat: {abs(lat):.6f}° {lat_dir}')
                self.ui_components['telescope_status']['gps_longitude'].set_text(f'Lon: {abs(lon):.6f}° {lon_dir}')
            else:
                self.ui_components['telescope_status']['gps_latitude'].set_text('Lat: --')
                self.ui_components['telescope_status']['gps_longitude'].set_text('Lon: --')

            # Last fix time
            last_fix = gps_data.get('last_fix_time')
            if last_fix:
                self.ui_components['telescope_status']['gps_last_fix'].set_text(f'Last fix: {last_fix[:19]}')
            else:
                self.ui_components['telescope_status']['gps_last_fix'].set_text('Last fix: Never')

            # Last push time
            last_push = gps_data.get('last_push_time')
            if last_push:
                self.ui_components['telescope_status']['gps_last_push'].set_text(f'Last push: {last_push[:19]}')
            else:
                self.ui_components['telescope_status']['gps_last_push'].set_text('Last push: Never')

            # Update push button state
            if 'gps_push_button' in self.ui_components['telescope_status']:
                btn = self.ui_components['telescope_status']['gps_push_button']
                has_fix = gps_data.get('has_fix', False)
                telescope_connected = self.data_manager.is_telescope_connected()

                if has_fix and telescope_connected:
                    btn.enable()
                    btn._props['color'] = 'primary'
                else:
                    btn.disable()
                    btn._props['color'] = 'grey'

                # Update status hint
                if 'gps_push_status' in self.ui_components['telescope_status']:
                    if not has_fix:
                        self.ui_components['telescope_status']['gps_push_status'].set_text('Waiting for fix...')
                    elif not telescope_connected:
                        self.ui_components['telescope_status']['gps_push_status'].set_text('Connect mount first')
                    else:
                        push_count = gps_data.get('push_count', 0)
                        self.ui_components['telescope_status']['gps_push_status'].set_text(f'Pushes: {push_count}')

        except Exception as e:
            self.logger.debug(f"Error updating GPS status: {e}")

    # Event handlers
    def confirm_stop_server(self):
        """Show confirmation dialog for stopping server."""
        with ui.dialog() as dialog, ui.card():
            ui.label('Are you sure you want to stop the server?')
            with ui.card_actions():
                ui.button('Cancel', on_click=dialog.close)
                ui.button('Stop Server', on_click=lambda: (dialog.close(), self.commands.stop_server()), color='red')
        dialog.open()
    
    def toggle_telescope_connection(self):
        """Toggle telescope connection."""
        if self.data_manager.is_telescope_connected():
            self.commands.disconnect_telescope()
        else:
            self.commands.connect_telescope()
    
    def toggle_tracking(self):
        """Toggle telescope tracking."""
        if self.data_manager.is_telescope_tracking():
            self.commands.stop_tracking()
        else:
            self.commands.start_tracking()

    def manual_gps_push(self):
        """Manually push GPS location to mount."""
        try:
            import TTS160Global
            gps_mgr = TTS160Global.get_gps_manager(self.logger)

            if gps_mgr is None:
                ui.notify('GPS is disabled', type='warning')
                return

            if not gps_mgr.has_valid_fix():
                ui.notify('No valid GPS fix available', type='warning')
                return

            if not self.data_manager.is_telescope_connected():
                ui.notify('Telescope not connected', type='warning')
                return

            if gps_mgr.push_location_now():
                ui.notify('GPS location pushed to mount', type='positive')
                # Update the status label
                if 'gps_push_status' in self.ui_components['telescope_status']:
                    self.ui_components['telescope_status']['gps_push_status'].set_text('Pushed!')
            else:
                ui.notify('Failed to push GPS location', type='negative')

        except Exception as e:
            self.logger.error(f"Manual GPS push error: {e}")
            ui.notify(f'GPS push error: {e}', type='negative')

    def _start_gps_manager(self):
        """Start GPS manager at GUI startup so fix can be acquired before mount connect."""
        try:
            import TTS160Global
            gps_mgr = TTS160Global.get_gps_manager(self.logger)

            if gps_mgr is None:
                self.logger.debug("GPS disabled in configuration")
                return

            if gps_mgr.start():
                self.logger.info("GPS manager started at GUI startup")
            else:
                self.logger.warning("GPS manager failed to start")

        except Exception as e:
            self.logger.warning(f"Failed to start GPS manager: {e}")

    def reload_server_config(self):
        """Reload server configuration data."""
        self.update_static_data()
        ui.notify('Server configuration reloaded', type='info')
    
    def reload_telescope_config(self):
        """Reload telescope configuration data.""" 
        self.update_static_data()
        ui.notify('Telescope configuration reloaded', type='info')
    
    def test_telescope_connection(self):
        """Test telescope connection."""
        success = self.commands.test_connection()
        if success:
            ui.notify('Connection test successful', type='positive')
        else:
            ui.notify('Connection test failed', type='negative')
    
    def save_server_config(self):
        """Save server configuration."""
        success = self.commands.save_server_config(self.ui_components['config_forms'])
        if success:
            ui.notify('Server configuration saved', type='positive')
        else:
            ui.notify('Failed to save server configuration', type='negative')
    
    def save_telescope_config(self):
        """Save telescope configuration."""
        success = self.commands.save_telescope_config(self.ui_components['telescope_config'])
        if success:
            ui.notify('Telescope configuration saved', type='positive')
        else:
            ui.notify('Failed to save telescope configuration', type='negative')
    
    def restart_server(self):
        """Restart the server."""
        with ui.dialog() as dialog, ui.card():
            ui.label('Are you sure you want to restart the server? This will disconnect all clients.')
            with ui.card_actions():
                ui.button('Cancel', on_click=dialog.close)
                ui.button('Restart', on_click=lambda: (dialog.close(), self.commands.restart_server()), color='orange')
        dialog.open()


def start_gui_thread(logger, port=8080):
    """
    Start the telescope GUI in a separate thread.
    
    Args:
        logger: Shared logger instance
        port: Port number for GUI server
    """
    def run_gui():
        try:
            interface = TelescopeInterface(logger, port)
            interface.start_gui_server()
        except Exception as e:
            logger.error(f"GUI server error: {e}")
    
    gui_thread = threading.Thread(target=run_gui, daemon=True)
    gui_thread.start()
    logger.info(f"GUI server started on port {port}")
    return gui_thread