"""
Telescope command handlers for the NiceGUI interface.

Handles all device operations, configuration changes, and system commands.
Provides a clean interface between the UI and the underlying telescope systems.
"""

import sys
import os
import serial.tools.list_ports
import TTS160Global
from nicegui import ui

class TelescopeCommands:
    """Handles all telescope and system commands from the GUI."""
    
    def __init__(self, logger, data_manager=None, update_callback=None):
        """
        Initialize command handler.
        
        Args:
            logger: Shared logger instance
            data_manager: DataManager instance for status updates (optional)
            update_callback: Allow for forced UI update
        """
        self.logger = logger
        self.data_manager = data_manager
        self._telescope_device = None
        self._server_config = None
        self._telescope_config = None
        self.update_callback = update_callback

    @property
    def telescope_device(self):
        """Get telescope device instance."""
        if self._telescope_device is None:
            self._telescope_device = TTS160Global.get_device(self.logger)
        return self._telescope_device
    
    @property
    def server_config(self):
        """Get server configuration instance."""
        if self._server_config is None:
            self._server_config = TTS160Global.get_serverconfig()
        return self._server_config
    
    @property
    def telescope_config(self):
        """Get telescope configuration instance."""
        if self._telescope_config is None:
            self._telescope_config = TTS160Global.get_config()
        return self._telescope_config
    
    # Telescope Control Commands
    
    def connect_telescope(self):
        """Connect to the telescope."""
        try:
            if hasattr(self.telescope_device, 'Connected'):
                self.telescope_device.Connected = True
                self.logger.info("Telescope connection established")
                return True
            else:
                self.logger.warning("Telescope device does not support connection control")
                return False
        except Exception as e:
            self.logger.error(f"Failed to connect to telescope: {e}")
            return False
    
    def disconnect_telescope(self):
        """Disconnect from the telescope."""
        try:
            if hasattr(self.telescope_device, 'Connected'):
                self.telescope_device.Connected = False
                self.logger.info("Telescope disconnected")
                return True
            else:
                self.logger.warning("Telescope device does not support connection control")
                return False
        except Exception as e:
            self.logger.error(f"Failed to disconnect from telescope: {e}")
            return False
    
    def park_telescope(self):
        """Park the telescope."""
        try:
            if hasattr(self.telescope_device, 'Park'):
                self.telescope_device.Park()
                self.logger.info("Telescope park command sent")
                return True
            else:
                self.logger.warning("Telescope does not support parking")
                return False
        except Exception as e:
            self.logger.error(f"Failed to park telescope: {e}")
            return False
    
    def unpark_telescope(self):
        """Unpark the telescope."""
        try:
            if hasattr(self.telescope_device, 'Unpark'):
                self.telescope_device.Unpark()
                self.logger.info("Telescope unpark command sent")
                return True
            else:
                self.logger.warning("Telescope does not support unparking")
                return False
        except Exception as e:
            self.logger.error(f"Failed to unpark telescope: {e}")
            return False
    
    def find_home(self):
        """Send telescope to home position."""
        try:
            if hasattr(self.telescope_device, 'FindHome'):
                self.telescope_device.FindHome()
                self.logger.info("Telescope find home command sent")
                return True
            else:
                self.logger.warning("Telescope does not support find home")
                return False
        except Exception as e:
            self.logger.error(f"Failed to send find home command: {e}")
            return False
    
    def start_tracking(self):
        """Start telescope tracking."""
        try:
            if hasattr(self.telescope_device, 'Tracking'):
                self.telescope_device.Tracking = True
                self.logger.info("Telescope tracking started")
                return True
            else:
                self.logger.warning("Telescope does not support tracking control")
                return False
        except Exception as e:
            self.logger.error(f"Failed to start tracking: {e}")
            return False
    
    def stop_tracking(self):
        """Stop telescope tracking."""
        try:
            if hasattr(self.telescope_device, 'Tracking'):
                self.telescope_device.Tracking = False
                self.logger.info("Telescope tracking stopped")
                return True
            else:
                self.logger.warning("Telescope does not support tracking control")
                return False
        except Exception as e:
            self.logger.error(f"Failed to stop tracking: {e}")
            return False
    
    def abort_slew(self):
        """Abort all telescope motion."""
        try:
            if hasattr(self.telescope_device, 'AbortSlew'):
                self.telescope_device.AbortSlew()
                self.logger.info("Telescope abort slew command sent")
                return True
            else:
                self.logger.warning("Telescope does not support abort slew")
                return False
        except Exception as e:
            self.logger.error(f"Failed to abort slew: {e}")
            return False
    
    def test_connection(self):
        """Test telescope connection."""
        try:
            # Try to read a simple property to test connection
            if hasattr(self.telescope_device, 'Connected'):
                connected = self.telescope_device.Connected
                self.logger.info(f"Connection test: telescope {'connected' if connected else 'disconnected'}")
                return True
            else:
                # Try to access a basic property
                if hasattr(self.telescope_device, 'Name'):
                    name = self.telescope_device.Name
                    self.logger.info(f"Connection test successful - telescope name: {name}")
                    return True
                else:
                    self.logger.warning("Cannot test connection - no suitable properties available")
                    return False
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False
    
    # Configuration Commands
    
    def save_server_config(self, config_data):
        """
        Save server configuration.
        
        Args:
            config_data: Dictionary containing configuration values
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Update server configuration
            if hasattr(self.server_config, 'ip_address') and 'ip_address' in config_data:
                self.server_config.ip_address = config_data['ip_address']
            
            if hasattr(self.server_config, 'port') and 'port' in config_data:
                self.server_config.port = int(config_data['port'])
            
            if hasattr(self.server_config, 'location') and 'location' in config_data:
                self.server_config.location = config_data['location']
            
            if hasattr(self.server_config, 'log_level') and 'log_level' in config_data:
                self.server_config.log_level = config_data['log_level']
            
            if hasattr(self.server_config, 'log_to_stdout') and 'log_to_stdout' in config_data:
                self.server_config.log_to_stdout = config_data['log_to_stdout']
            
            if hasattr(self.server_config, 'max_size_mb') and 'max_size_mb' in config_data:
                self.server_config.max_size_mb = int(config_data['max_size_mb'])
            
            if hasattr(self.server_config, 'num_keep_logs') and 'num_keep_logs' in config_data:
                self.server_config.num_keep_logs = int(config_data['num_keep_logs'])
            
            # Save configuration to file if method exists
            if hasattr(self.server_config, 'save'):
                self.server_config.save()
            
            self.logger.info("Server configuration saved successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save server configuration: {e}")
            return False
    
    def save_telescope_config(self, config_data):
        """
        Save telescope configuration.
        
        Args:
            config_data: Dictionary containing configuration values
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Update telescope configuration
            if hasattr(self.telescope_config, 'dev_port') and 'dev_port' in config_data:
                self.telescope_config.dev_port = config_data['dev_port']
            
            if hasattr(self.telescope_config, 'site_elevation') and 'site_elevation' in config_data:
                self.telescope_config.site_elevation = float(config_data['site_elevation'])
            
            if hasattr(self.telescope_config, 'sync_time_on_connect') and 'sync_time_on_connect' in config_data:
                self.telescope_config.sync_time_on_connect = config_data['sync_time_on_connect']
            
            if hasattr(self.telescope_config, 'pulse_guide_equatorial_frame') and 'pulse_guide_equatorial_frame' in config_data:
                self.telescope_config.pulse_guide_equatorial_frame = config_data['pulse_guide_equatorial_frame']
            
            if hasattr(self.telescope_config, 'pulse_guide_altitude_compensation') and 'pulse_guide_altitude_compensation' in config_data:
                self.telescope_config.pulse_guide_altitude_compensation = config_data['pulse_guide_altitude_compensation']
            
            if hasattr(self.telescope_config, 'pulse_guide_max_compensation') and 'pulse_guide_max_compensation' in config_data:
                self.telescope_config.pulse_guide_max_compensation = int(config_data['pulse_guide_max_compensation'])
            
            if hasattr(self.telescope_config, 'pulse_guide_compensation_buffer') and 'pulse_guide_compensation_buffer' in config_data:
                self.telescope_config.pulse_guide_compensation_buffer = int(config_data['pulse_guide_compensation_buffer'])
            
            if hasattr(self.telescope_config, 'slew_settle_time') and 'slew_settle_time' in config_data:
                self.telescope_config.slew_settle_time = int(config_data['slew_settle_time'])
            
            # Save configuration to file if method exists
            if hasattr(self.telescope_config, 'save'):
                self.telescope_config.save()
            
            self.logger.info("Telescope configuration saved successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save telescope configuration: {e}")
            return False
    
    # System Commands
    
    def stop_server(self):
        """Stop the ALPACA server."""
        try:
            self.logger.info("Server stop requested from GUI")
            
            # Mark server as stopping for status display
            if self.data_manager:
                self.data_manager.set_alpaca_server_stopping()

            if self.update_callback:
                self.update_callback()

            def shutdown_sequence():
                """Run shutdown in separate thread to avoid async issues."""
                import app
                import os
                import time
                
                # Small delay to let UI respond
                time.sleep(0.5)
                
                # Stop discovery service
                if hasattr(app, '_DSC') and app._DSC:
                    self.logger.info("Shutting down discovery service...")
                    try:
                        app._DSC.stop()
                    except Exception as e:
                        self.logger.warning(f"Error stopping discovery service: {e}")
                
                # Clean up logging
                try:
                    import logging
                    logging.shutdown()
                except Exception as e:
                    self.logger.warning(f"Error during logging shutdown: {e}")
                    
                self.logger.info("Graceful shutdown complete - terminating process")
                os._exit(0)
            
            # Run shutdown in separate thread
            import threading
            shutdown_thread = threading.Thread(target=shutdown_sequence, daemon=True)
            shutdown_thread.start()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop server: {e}")
            return False
    
    def restart_server(self):
        """Restart the ALPACA server."""
        try:
            self.logger.info("Server restart requested from GUI")
            
            # For now, just log the request - actual restart would require
            # more complex process management
            self.logger.warning("Server restart not yet implemented")
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to restart server: {e}")
            return False
    
    # Utility Methods
    
    def get_available_ports(self):
        """
        Get list of available serial ports.
        
        Returns:
            list: List of dictionaries with 'device' and 'description' keys
        """
        try:
            ports = []
            for port in serial.tools.list_ports.comports():
                ports.append({
                    'device': port.device,
                    'description': port.description or 'Unknown device'
                })
            
            self.logger.debug(f"Found {len(ports)} available serial ports")
            return ports
            
        except Exception as e:
            self.logger.error(f"Failed to enumerate serial ports: {e}")
            return []
    
    def format_coordinates(self, ra_decimal, dec_decimal):
        """
        Format decimal coordinates to HMS/DMS format.
        
        Args:
            ra_decimal: Right Ascension in decimal hours
            dec_decimal: Declination in decimal degrees
            
        Returns:
            tuple: (ra_formatted, dec_formatted)
        """
        try:
            # Format RA as HH:MM:SS
            ra_hours = int(ra_decimal)
            ra_minutes = int((ra_decimal - ra_hours) * 60)
            ra_seconds = ((ra_decimal - ra_hours) * 60 - ra_minutes) * 60
            ra_formatted = f"{ra_hours:02d}:{ra_minutes:02d}:{ra_seconds:05.2f}"
            
            # Format Dec as DD:MM:SS
            dec_sign = '+' if dec_decimal >= 0 else '-'
            dec_decimal = abs(dec_decimal)
            dec_degrees = int(dec_decimal)
            dec_minutes = int((dec_decimal - dec_degrees) * 60)
            dec_seconds = ((dec_decimal - dec_degrees) * 60 - dec_minutes) * 60
            dec_formatted = f"{dec_sign}{dec_degrees:02d}:{dec_minutes:02d}:{dec_seconds:05.2f}"
            
            return ra_formatted, dec_formatted
            
        except Exception as e:
            self.logger.error(f"Failed to format coordinates: {e}")
            return "--:--:--", "--:--:--"
    
    def validate_ip_address(self, ip_string):
        """
        Validate IP address format.
        
        Args:
            ip_string: IP address string to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            parts = ip_string.split('.')
            if len(parts) != 4:
                return False
            
            for part in parts:
                if not part.isdigit():
                    return False
                num = int(part)
                if num < 0 or num > 255:
                    return False
            
            return True
            
        except Exception:
            return False
    
    def validate_port_number(self, port):
        """
        Validate port number.
        
        Args:
            port: Port number to validate (int or string)
            
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            port_num = int(port)
            return 1 <= port_num <= 65535
        except (ValueError, TypeError):
            return False