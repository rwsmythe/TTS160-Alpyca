"""
Data management for the telescope GUI.

Handles access to global telescope and server instances, provides formatted data
for the UI, and manages update coordination between the GUI and hardware.
"""

import psutil
import socket
from datetime import datetime
import TTS160Global

# Module startup time for uptime calculation
_MODULE_START_TIME = datetime.now()


class DataManager:
    """Manages data access and formatting for the telescope GUI."""
    
    def __init__(self, logger):
        """
        Initialize data manager.
        
        Args:
            logger: Shared logger instance
        """
        self.logger = logger
        
        # Module-level globals for efficient access
        self._telescope_device = None
        self._server_config = None
        self._telescope_config = None
        self._serial_manager = None
        self._cache = None
        self._telescope_cache = None
        
        # Cache for expensive operations
        self._last_ip_check = None
        self._cached_ips = []
        
        # Server status tracking
        self._alpaca_server_running = True
        
    @property
    def telescope_device(self):
        """Get telescope device instance."""
        if self._telescope_device is None:
            self._telescope_device = TTS160Global.get_device(self.logger)
        return self._telescope_device
    
    @property
    def telescope_cache(self):
        """Get telescope device instance."""
        if self._telescope_cache is None:
            self._telescope_cache = TTS160Global.get_cache()
        return self._telescope_cache
    
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
    
    @property
    def serial_manager(self):
        """Get serial manager instance."""
        if self._serial_manager is None:
            self._serial_manager = TTS160Global.get_serial_manager(self.logger)
        return self._serial_manager
    
    # High-frequency data methods (called ~2Hz)
    
    def get_telescope_status(self):
        """
        Get current telescope status data.
        
        Returns:
            dict: Telescope status information
        """
        
        cache = None  # Initialize here
        
        try:
            cache = self.telescope_cache
            device = self.telescope_device
            
            status = {
                'connected': False,
                'name': 'Unknown',
                'tracking': False,
                'is_slewing': False,
                'at_park': False,
                'at_home': False,
                'pier_side': 'Unknown',
                'guide_rate_right_ascension': 0.0,
                'can_park': False,
                'can_set_tracking': False,
                'can_slew': False,
                'can_sync': False,
                'can_pulse_guide': False,
                'can_find_home': False,
                'utc_date': 'Unknown',
                'sidereal_time': 0.0,
                'alignment_matrix': [0,0,0,0,0,0,0,0,0]
            }
            
            if device:
                # Connection status
                if hasattr(device, 'Connected'):
                    status['connected'] = device.Connected
                
                # Basic properties
                if hasattr(device, 'Name'):
                    status['name'] = device.Name
                
                # Only query other properties if connected
                if cache and status['connected']:
                    try:
                        status['tracking'] = cache.get_property_value('Tracking', False)
                        status['is_slewing'] = cache.get_property_value('Slewing', False)
                        status['at_park'] = cache.get_property_value('AtPark', False)
                        status['at_home'] = cache.get_property_value('AtHome', False)
                        status['pier_side'] = cache.get_property_value('SideOfPier', 'Unknown')
                        status['guide_rate_right_ascension'] = cache.get_property_value('GuideRateRightAscension', 0.0)
                        status['utc_date'] = cache.get_property_value('UTCDate', 'Unknown')
                        status['sidereal_time'] = cache.get_property_value('SiderealTime', 0.0)
                        status['alignment_matrix'] = cache.get_property_value('_AlignmentMatrix', [0,0,0,0,0,0,0,0,0])
                        
                    except Exception as e:
                        self.logger.debug(f"Error reading telescope status properties: {e}")
                
                # Capabilities (static, but query here for now)
                    try:
                        if hasattr(device, 'CanPark'):
                            status['can_park'] = device.CanPark
                        
                        if hasattr(device, 'CanSetTracking'):
                            status['can_set_tracking'] = device.CanSetTracking
                        
                        if hasattr(device, 'CanSlew'):
                            status['can_slew'] = device.CanSlew
                        
                        if hasattr(device, 'CanSync'):
                            status['can_sync'] = device.CanSync
                        
                        if hasattr(device, 'CanPulseGuide'):
                            status['can_pulse_guide'] = device.CanPulseGuide
                        
                        if hasattr(device, 'CanFindHome'):
                            status['can_find_home'] = device.CanFindHome
                            
                    except Exception as e:
                        self.logger.debug(f"Error reading telescope capabilities: {e}")
            
            return status
            
        except Exception as e:
            if cache:
                self.logger.error(f"Error getting telescope status: {e}")
            return {'connected': False, 'name': 'Error'}
    
    def get_telescope_position(self):
        """
        Get current telescope position data.
        
        Returns:
            dict: Position information with formatted coordinates
        """
        try:
            device = self.telescope_device
            cache = self.telescope_cache

            position = {
                'ra_decimal': 0.0,
                'dec_decimal': 0.0,
                'ra_formatted': '--:--:--',
                'dec_formatted': '--:--:--',
                'altitude': 0.0,
                'azimuth': 0.0,
                'ra_ticks': '--',
                'dec_ticks': '--'
            }
            
            if cache and hasattr(device, 'Connected') and device.Connected:
                try:
                    # Get decimal coordinates
                    position['ra_decimal'] = cache.get_property_value('RightAscension', 0.0)
                    position['dec_decimal'] = cache.get_property_value('Declination', 0.0)
                    
                    # Format coordinates
                    ra_formatted, dec_formatted = self._format_coordinates(
                        position['ra_decimal'], position['dec_decimal'])
                    position['ra_formatted'] = ra_formatted
                    position['dec_formatted'] = dec_formatted
                    
                    # Horizontal coordinates
                    position['altitude'] = cache.get_property_value('Altitude', 0.0)
                    position['azimuth'] = cache.get_property_value('Azimuth', 0.0)
                    
                    # Mechanical position (if available)
                    # These might be custom properties specific to TTS160
                    #if hasattr(device, 'ra_ticks'):
                    #    position['ra_ticks'] = device.ra_ticks
                    
                    #if hasattr(device, 'dec_ticks'):
                    #    position['dec_ticks'] = device.dec_ticks
                        
                except Exception as e:
                    self.logger.debug(f"Error reading telescope position: {e}")
            
            return position
            
        except Exception as e:
            if cache:
                self.logger.error(f"Error getting telescope position: {e}")
            return position
    
    # Low-frequency data methods (called ~10s)
    
    def get_system_status(self):
        """
        Get system status information.
        
        Returns:
            dict: System status data
        """
        try:
            # Get uptime
            uptime_str = self._get_uptime()
            
            # Get memory usage
            memory_info = psutil.virtual_memory()
            memory_usage = f"{memory_info.percent:.1f}%"
            
            # Get telescope connection status
            telescope_connected = self.is_telescope_connected()
            
            client_count, client_list = self._get_connected_clients_count()

            status = {
                'server_running': self._is_alpaca_server_running(),
                'discovery_active': self._is_discovery_active(),
                'telescope_connected': telescope_connected,
                'config_valid': True,  # Assume valid unless we detect otherwise
                'uptime': uptime_str,
                'connected_clients': client_count,
                'connected_client_list': client_list,
                'total_requests': self._get_total_requests(),
                'memory_usage': memory_usage,
                'last_config_change': 'Unknown',
                'log_file_path': self._get_log_file_path(),
                'log_file_size': self._get_log_file_size(),
                'current_ips': self._get_current_ip_addresses()
            }
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting system status: {e}")
            return {
                'server_running': False,
                'discovery_active': False,
                'telescope_connected': False,
                'config_valid': False,
                'uptime': 'Unknown',
                'connected_clients': 0,
                'total_requests': 0,
                'memory_usage': 'Unknown'
            }

    def get_gps_status(self):
        """Get GPS status information.

        Returns:
            dict: GPS status data including state, position, fix quality,
                  satellites, and last update time. Returns None if GPS
                  is disabled or unavailable.
        """
        try:
            import TTS160Global
            gps_mgr = TTS160Global.get_gps_manager(self.logger)

            if gps_mgr is None:
                return {
                    'enabled': False,
                    'state': 'DISABLED',
                    'state_display': 'Disabled'
                }

            status = gps_mgr.get_status()
            position = status.position  # Position is nested in status

            return {
                'enabled': True,
                'state': status.state.name,
                'state_display': status.state.name.replace('_', ' ').title(),
                'connected': status.connected,
                'has_fix': position.valid if position else False,
                'fix_quality': position.fix_quality.name if position else 'UNKNOWN',
                'fix_quality_value': position.fix_quality.value if position else 0,
                'satellites': position.satellites if position else 0,
                'hdop': position.hdop if position else None,
                'latitude': position.latitude if position and position.valid else None,
                'longitude': position.longitude if position and position.valid else None,
                'altitude': position.altitude if position else None,
                'last_fix_time': position.timestamp.isoformat() if position and position.timestamp else None,
                'last_push_time': status.last_push_to_mount.isoformat() if status.last_push_to_mount else None,
                'push_count': status.push_count,
                'error_message': status.error_message,
                'port': status.port or self.telescope_config.gps_port
            }

        except Exception as e:
            self.logger.error(f"Error getting GPS status: {e}")
            return {
                'enabled': self.telescope_config.gps_enabled,
                'state': 'ERROR',
                'state_display': 'Error',
                'error_message': str(e),
                'port': self.telescope_config.gps_port,
                'satellites': 0,
                'has_fix': False,
                'fix_quality': 'UNKNOWN'
            }

    # Static data methods (called on demand)

    def get_server_config(self):
        """
        Get server configuration data.
        
        Returns:
            dict: Server configuration
        """
        try:
            
            return {
                'ip_address': self.server_config.ip_address or '127.0.0.1',
                'port': self.server_config.port,
                'location': self.server_config.location,
                'log_level': self.server_config.log_level,
                'log_to_stdout': self.server_config.log_to_stdout,
                'max_size_mb': self.server_config.max_size_mb,
                'num_keep_logs': self.server_config.num_keep_logs,
            }
            
        except Exception as e:
            self.logger.error(f"Error getting server config: {e}")
            return {}
    
    def get_telescope_config(self):
        """
        Get telescope configuration data.
        
        Returns:
            dict: Telescope configuration
        """
        try:
                       
            # Format coordinates for display
            lat = self.telescope_config.site_latitude
            lon = self.telescope_config.site_longitude
            
            lat_formatted = self._format_latitude(lat)
            lon_formatted = self._format_longitude(lon)
            
            return {
                'dev_port': self.telescope_config.dev_port,
                'site_elevation': self.telescope_config.site_elevation,
                'site_latitude': lat,
                'site_longitude': lon,
                'latitude_display': lat_formatted,
                'longitude_display': lon_formatted,
                'sync_time_on_connect': self.telescope_config.sync_time_on_connect,
                'pulse_guide_equatorial_frame': self.telescope_config.pulse_guide_equatorial_frame,
                'pulse_guide_altitude_compensation': self.telescope_config.pulse_guide_altitude_compensation,
                'pulse_guide_max_compensation': self.telescope_config.pulse_guide_max_compensation,
                'pulse_guide_compensation_buffer': self.telescope_config.pulse_guide_compensation_buffer,
                'slew_settle_time': self.telescope_config.slew_settle_time,
                'available_ports': self._get_available_ports()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting telescope config: {e}")
            return {}
    
    # Utility methods
    
    def is_telescope_connected(self):
        """Check if telescope is connected."""
        try:
            device = self.telescope_device
            if device and hasattr(device, 'Connected'):
                return device.Connected
            return False
        except Exception:
            return False
    
    def is_telescope_tracking(self):
        """Check if telescope is tracking."""
        try:
            device = self.telescope_device
            if device and hasattr(device, 'Tracking') and self.is_telescope_connected():
                return device.Tracking
            return False
        except Exception:
            return False
    
    # Private helper methods
    
    def _format_coordinates(self, ra_decimal, dec_decimal):
        """Format decimal coordinates to HMS/DMS."""
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
            
        except Exception:
            return "--:--:--", "--:--:--"
    
    def _format_latitude(self, lat_decimal):
        """Format latitude for display."""
        try:
            direction = 'N' if lat_decimal >= 0 else 'S'
            lat_abs = abs(lat_decimal)
            degrees = int(lat_abs)
            minutes = int((lat_abs - degrees) * 60)
            seconds = ((lat_abs - degrees) * 60 - minutes) * 60
            return f"{degrees}° {minutes}' {seconds:.1f}\" {direction}"
        except Exception:
            return "Unknown"
    
    def _format_longitude(self, lon_decimal):
        """Format longitude for display."""
        try:
            direction = 'E' if lon_decimal >= 0 else 'W'
            lon_abs = abs(lon_decimal)
            degrees = int(lon_abs)
            minutes = int((lon_abs - degrees) * 60)
            seconds = ((lon_abs - degrees) * 60 - minutes) * 60
            return f"{degrees}° {minutes}' {seconds:.1f}\" {direction}"
        except Exception:
            return "Unknown"
    
    def _is_discovery_active(self):
        """Check if discovery service is active."""
        try:
            # If shutdown was requested, return False
            if not self._alpaca_server_running:
                return False
                
            # Check if server object exists and is accessible
            import socket

            host = self.server_config.ip_address if self.server_config.ip_address not in ('0.0.0.0', '') else 'localhost'
            port = 32227

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            result = sock.connect_ex((host, port))
            sock.close()

            return result == 0
        except Exception:
            return False

    def _get_connected_clients_count(self):
        """Get count of connected clients."""
        try:
            return self.telescope_device._serial_manager._connection_count, self.telescope_device._serial_manager._client_list
        except Exception:
            return 0, []
    
    def _get_total_requests(self):
        """Get total request count."""
        try:
            # This would need to be implemented based on server metrics
            return 0
        except Exception:
            return 0
    
    def _get_log_file_path(self):
        """Get current log file path."""
        try:
            # Get from logging configuration
            import log
            if hasattr(log, 'logger') and log.logger:
                handlers = log.logger.handlers
                for handler in handlers:
                    if hasattr(handler, 'baseFilename'):
                        return handler.baseFilename
            return 'Unknown'
        except Exception:
            return 'Unknown'
    
    def _get_log_file_size(self):
        """Get current log file size."""
        try:
            import os
            log_path = self._get_log_file_path()
            if log_path != 'Unknown' and os.path.exists(log_path):
                size_bytes = os.path.getsize(log_path)
                if size_bytes < 1024:
                    return f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    return f"{size_bytes / 1024:.1f} KB"
                else:
                    return f"{size_bytes / (1024 * 1024):.1f} MB"
            return 'Unknown'
        except Exception:
            return 'Unknown'
    
    def _get_current_ip_addresses(self):
        """Get current IP addresses."""
        try:
            # Cache IP addresses for a few seconds to avoid frequent lookups
            now = datetime.now()
            if (self._last_ip_check is None or 
                (now - self._last_ip_check).seconds > 5):
                
                ips = []
                hostname = socket.gethostname()
                
                # Get all IP addresses
                try:
                    ip_list = socket.getaddrinfo(hostname, None)
                    for ip_info in ip_list:
                        ip = ip_info[4][0]
                        if ip not in ips and not ip.startswith('127.'):
                            ips.append(ip)
                except Exception:
                    pass
                
                # Add common interface IPs
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
                    s.close()
                    if local_ip not in ips:
                        ips.append(local_ip)
                except Exception:
                    pass
                
                self._cached_ips = ips
                self._last_ip_check = now
            
            return self._cached_ips
            
        except Exception as e:
            self.logger.debug(f"Error getting IP addresses: {e}")
            return ['Unknown']
    
    def _get_available_ports(self):
        """Get available serial ports."""
        try:
            import serial.tools.list_ports
            ports = []
            for port in serial.tools.list_ports.comports():
                ports.append({
                    'device': port.device,
                    'description': port.description or 'Unknown device'
                })
            return ports
        except Exception as e:
            self.logger.debug(f"Error getting available ports: {e}")
            return []
    
    def _get_uptime(self):
        """Get formatted uptime string."""
        try:
            uptime_delta = datetime.now() - _MODULE_START_TIME
            days = uptime_delta.days
            hours, remainder = divmod(uptime_delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
        except Exception:
            return "Unknown"
    
    def _is_alpaca_server_running(self):
        """Check if ALPACA server is running."""
        try:
            # If shutdown was requested, return False
            if not self._alpaca_server_running:
                return False
                
            # Check if server object exists and is accessible
            import socket

            host = self.server_config.ip_address if self.server_config.ip_address not in ('0.0.0.0', '') else 'localhost'
            port = self.server_config.port

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            result = sock.connect_ex((host, port))
            sock.close()

            return result == 0
        except Exception:
            return False

    def set_alpaca_server_stopping(self):
        """Mark ALPACA server as stopping."""
        self._alpaca_server_running = False
        self._discovery_server_running = False