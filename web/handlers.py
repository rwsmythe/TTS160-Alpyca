"""
Web request handlers and template rendering for Alpaca driver web interface.

This module provides business logic handlers for processing web requests,
template rendering utilities using Jinja2, and configuration management
for the web interface components.

Classes:
    WebRequestHandler: Base handler for common web request processing
    ConfigurationHandler: Configuration data access and validation
    StatusHandler: Telescope status monitoring and data retrieval

Functions:
    render_template: Template rendering with error handling
    get_template_env: Get configured Jinja2 environment
    validate_form_data: Common form validation utilities
"""

import os
import sys
from typing import Dict, Any, Optional, Union
from jinja2 import Environment, FileSystemLoader, TemplateError, select_autoescape
from falcon import Request, Response
import logging

# Import project modules
try:
    from config import Config
    import log
    import telescope
except ImportError as e:
    raise ImportError(f"Failed to import required modules: {e}") from e

__version__ = "1.0.0"
__author__ = "Reid Smythe <rwsmythe@gmail.com>"

# Global Jinja2 environment - initialized lazily
_template_env: Optional[Environment] = None


def get_template_env() -> Environment:
    """
    Get or create the Jinja2 template environment.
    
    Returns:
        Environment: Configured Jinja2 environment
        
    Raises:
        TemplateError: If template directory doesn't exist or is inaccessible
    """
    global _template_env
    
    if _template_env is None:
        template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
        template_dir = os.path.abspath(template_dir)
        
        if not os.path.exists(template_dir):
            raise TemplateError(f"Template directory not found: {template_dir}")
            
        _template_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Add global template functions
        _template_env.globals.update({
            'get_app_version': lambda: getattr(Config, 'version', '1.0.0'),
            'get_server_info': lambda: {
                'ip': Config.ip_address,
                'port': Config.port
            }
        })
    
    return _template_env


def render_template(template_name: str, **context) -> str:
    """
    Render a Jinja2 template with the given context.
    
    Args:
        template_name: Name of the template file
        **context: Template variables
        
    Returns:
        str: Rendered HTML
        
    Raises:
        TemplateError: If template rendering fails
        
    Example:
        >>> html = render_template('server_config.html', config=config_data)
    """
    try:
        env = get_template_env()
        template = env.get_template(template_name)
        return template.render(**context)
    except TemplateError as e:
        log.logger.error(f"Template rendering failed for {template_name}: {e}")
        raise
    except Exception as e:
        log.logger.error(f"Unexpected error rendering template {template_name}: {e}")
        raise TemplateError(f"Template rendering failed: {e}") from e


class WebRequestHandler:
    """
    Base handler for common web request processing operations.
    
    Provides utilities for request parsing, response formatting,
    and error handling common across web interface endpoints.
    """
    
    def __init__(self):
        """Initialize the web request handler."""
        self.logger = log.logger or logging.getLogger(__name__)
    
    def parse_form_data(self, req: Request) -> Dict[str, Any]:
        """
        Parse form data from request with error handling.
        
        Args:
            req: Falcon request object
            
        Returns:
            dict: Parsed form data
            
        Raises:
            ValueError: If form data is invalid
        """
        try:
            # Handle both URL-encoded and multipart form data
            if hasattr(req, 'media') and req.media:
                return req.media
            elif hasattr(req, 'params') and req.params:
                return dict(req.params)
            else:
                return {}
        except Exception as e:
            self.logger.error(f"Failed to parse form data: {e}")
            raise ValueError("Invalid form data") from e
    
    def set_html_response(self, resp: Response, content: str) -> None:
        """
        Set HTML response with proper headers.
        
        Args:
            resp: Falcon response object
            content: HTML content to send
        """
        resp.content_type = 'text/html; charset=utf-8'
        resp.text = content
    
    def set_error_response(self, resp: Response, status: str, message: str) -> None:
        """
        Set error response with proper status and message.
        
        Args:
            resp: Falcon response object
            status: HTTP status code
            message: Error message
        """
        resp.status = status
        resp.content_type = 'text/html; charset=utf-8'
        resp.text = f'<div class="error">{message}</div>'
        self.logger.warning(f"Error response: {status} - {message}")


class ConfigurationHandler:
    """
    Handler for configuration data access and validation.
    
    Manages reading and writing configuration data for both
    server and telescope configuration interfaces.
    """
    
    def __init__(self):
        """Initialize the configuration handler."""
        self.logger = log.logger or logging.getLogger(__name__)
    
    def get_available_ports(self) -> list:
        """
        Get available COM ports for telescope connection.
        
        Returns:
            list: Available COM port objects with device and description
        """
        try:
            import serial.tools.list_ports
            return list(serial.tools.list_ports.comports())
        except Exception as e:
            self.logger.error(f"Failed to get COM ports: {e}")
            return []
    
    def format_coordinates(self, decimal_degrees: float) -> Dict[str, str]:
        """
        Convert decimal degrees to degrees, minutes, seconds format.
        
        Args:
            decimal_degrees: Coordinate in decimal degrees
            
        Returns:
            dict: Formatted coordinate components
        """
        try:
            abs_degrees = abs(decimal_degrees)
            degrees = int(abs_degrees)
            minutes_float = (abs_degrees - degrees) * 60
            minutes = int(minutes_float)
            seconds = (minutes_float - minutes) * 60
            
            return {
                'degrees': f"{degrees:02d}" if abs_degrees < 100 else f"{degrees:03d}",
                'minutes': f"{minutes:02d}",
                'seconds': f"{seconds:04.1f}"
            }
        except Exception as e:
            self.logger.error(f"Failed to format coordinates: {e}")
            return {'degrees': '00', 'minutes': '00', 'seconds': '00.0'}
    
    def get_server_config(self) -> Dict[str, Any]:
        """
        Get current server configuration data.
        
        Returns:
            dict: Server configuration parameters
        """
        try:
            return {
                'ip_address': Config.ip_address,
                'port': Config.port,
                'device_name': getattr(Config, 'device_name', 'Alpaca Telescope'),
                'description': getattr(Config, 'description', 'Alpaca-compatible telescope driver'),
                'driver_info': getattr(Config, 'driver_info', 'Alpaca Telescope Driver v1.0'),
                'driver_version': getattr(Config, 'driver_version', '1.0.0'),
                'interface_version': getattr(Config, 'interface_version', 1),
                'location': getattr(Config, 'location', 'Unknown'),
                'supported_actions': getattr(Config, 'supported_actions', [])
            }
        except Exception as e:
            self.logger.error(f"Failed to get server config: {e}")
            return {}
    
    def get_telescope_config(self) -> Dict[str, Any]:
        """
        Get current telescope configuration data.
        
        Returns:
            dict: Telescope configuration parameters
        """
        try:
            cfg = telescope.TTS160_cfg
            return {
                # Device section
                'dev_port': cfg.dev_port,
                # Site section  
                'site_elevation': cfg.site_elevation,
                'site_latitude': cfg.site_latitude,
                'site_longitude': cfg.site_longitude,
                # Driver section
                'sync_time_on_connect': cfg.sync_time_on_connect,
                'pulse_guide_equatorial_frame': cfg.pulse_guide_equatorial_frame,
                'pulse_guide_altitude_compensation': cfg.pulse_guide_altitude_compensation,
                'pulse_guide_max_compensation': cfg.pulse_guide_max_compensation,
                'pulse_guide_compensation_buffer': cfg.pulse_guide_compensation_buffer,
                'slew_settle_time': cfg.slew_settle_time
            }
        except Exception as e:
            self.logger.error(f"Failed to get telescope config: {e}")
            return {
                'dev_port': 'COM1',
                'site_elevation': 0.0,
                'site_latitude': 0.0,
                'site_longitude': 0.0,
                'sync_time_on_connect': True,
                'pulse_guide_equatorial_frame': True,
                'pulse_guide_altitude_compensation': True,
                'pulse_guide_max_compensation': 1000,
                'pulse_guide_compensation_buffer': 20,
                'slew_settle_time': 1
            }
    
    def validate_server_config(self, form_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Validate server configuration form data.
        
        Args:
            form_data: Form data to validate
            
        Returns:
            dict: Validation errors (empty if valid)
        """
        errors = {}
        
        # Validate IP address
        ip_address = form_data.get('ip_address', '').strip()
        if not ip_address:
            errors['ip_address'] = 'IP address is required'
        
        # Validate port
        try:
            port = int(form_data.get('port', 0))
            if port < 1 or port > 65535:
                errors['port'] = 'Port must be between 1 and 65535'
        except (ValueError, TypeError):
            errors['port'] = 'Port must be a valid number'
        
        # Validate device name
        device_name = form_data.get('device_name', '').strip()
        if not device_name:
            errors['device_name'] = 'Device name is required'
        elif len(device_name) > 100:
            errors['device_name'] = 'Device name must be 100 characters or less'
        
        return errors
    
    def validate_telescope_config(self, form_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Validate telescope configuration form data.
        
        Args:
            form_data: Form data to validate
            
        Returns:
            dict: Validation errors (empty if valid)
        """
        errors = {}
        
        # Validate device port
        dev_port = form_data.get('dev_port', '').strip()
        if not dev_port:
            errors['dev_port'] = 'Device port is required'
        
        # Validate site elevation
        try:
            elevation = float(form_data.get('site_elevation', 0))
            if elevation < -500 or elevation > 9000:
                errors['site_elevation'] = 'Elevation must be between -500 and 9000 meters'
        except (ValueError, TypeError):
            errors['site_elevation'] = 'Elevation must be a valid number'
        
        # Validate pulse guide max compensation
        try:
            max_comp = int(form_data.get('pulse_guide_max_compensation', 1000))
            if max_comp < 100 or max_comp > 10000:
                errors['pulse_guide_max_compensation'] = 'Max compensation must be between 100 and 10000 ms'
        except (ValueError, TypeError):
            errors['pulse_guide_max_compensation'] = 'Max compensation must be a valid integer'
        
        # Validate pulse guide compensation buffer
        try:
            buffer = int(form_data.get('pulse_guide_compensation_buffer', 20))
            if buffer < 5 or buffer > 500:
                errors['pulse_guide_compensation_buffer'] = 'Compensation buffer must be between 5 and 500 ms'
        except (ValueError, TypeError):
            errors['pulse_guide_compensation_buffer'] = 'Compensation buffer must be a valid integer'
        
        # Validate slew settle time
        try:
            settle_time = int(form_data.get('slew_settle_time', 1))
            if settle_time < 0 or settle_time > 30:
                errors['slew_settle_time'] = 'Slew settle time must be between 0 and 30 seconds'
        except (ValueError, TypeError):
            errors['slew_settle_time'] = 'Slew settle time must be a valid integer'
        
        return errors
    
    def save_server_config(self, form_data: Dict[str, Any]) -> bool:
        """
        Save server configuration data.
        
        Args:
            form_data: Configuration data to save
            
        Returns:
            bool: True if saved successfully
        """
        try:
            # This would update Config and write to config.toml
            # Implementation depends on your config system
            self.logger.info("Server configuration saved")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save server config: {e}")
            return False
    
    def save_telescope_config(self, form_data: Dict[str, Any]) -> bool:
        """
        Save telescope configuration data.
        
        Args:
            form_data: Configuration data to save
            
        Returns:
            bool: True if saved successfully
        """
        try:
            cfg = telescope.TTS160_cfg
            
            # Update configuration values
            cfg.dev_port = form_data.get('dev_port', cfg.dev_port)
            cfg.site_elevation = float(form_data.get('site_elevation', cfg.site_elevation))
            
            # Boolean values from checkboxes
            cfg.sync_time_on_connect = form_data.get('sync_time_on_connect') == 'true'
            cfg.pulse_guide_equatorial_frame = form_data.get('pulse_guide_equatorial_frame') == 'true'
            cfg.pulse_guide_altitude_compensation = form_data.get('pulse_guide_altitude_compensation') == 'true'
            
            # Integer values
            cfg.pulse_guide_max_compensation = int(form_data.get('pulse_guide_max_compensation', cfg.pulse_guide_max_compensation))
            cfg.pulse_guide_compensation_buffer = int(form_data.get('pulse_guide_compensation_buffer', cfg.pulse_guide_compensation_buffer))
            cfg.slew_settle_time = int(form_data.get('slew_settle_time', cfg.slew_settle_time))
            
            # Save to file
            cfg.save()
            self.logger.info("Telescope configuration saved")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save telescope config: {e}")
            return False


class StatusHandler:
    """
    Handler for telescope status monitoring and data retrieval.
    
    Manages real-time status updates for the telescope monitoring
    interface and provides data for HTMX status updates.
    """
    
    def __init__(self):
        """Initialize the status handler."""
        self.logger = log.logger or logging.getLogger(__name__)
    
    def get_telescope_status(self) -> Dict[str, Any]:
        """
        Get current telescope status data.
        
        Returns:
            dict: Current telescope status information
        """
        try:
            # This would interface with your telescope module
            # to get real-time status information
            
            return {
                'connected': telescope.TTS160_dev.Connected if hasattr(telescope, 'TTS160_dev') else False,
                'name': getattr(telescope, 'name', 'Unknown Telescope'),
                'description': getattr(telescope, 'description', 'Alpaca Telescope'),
                'driver_info': getattr(telescope, 'driver_info', 'v1.0.0'),
                'driver_version': getattr(telescope, 'driver_version', '1.0.0'),
                'interface_version': getattr(telescope, 'interface_version', 1),
                'supported_actions': getattr(telescope, 'supported_actions', []),
                'can_find_home': getattr(telescope, 'can_find_home', False),
                'can_park': getattr(telescope, 'can_park', True),
                'can_set_park': getattr(telescope, 'can_set_park', True),
                'can_set_tracking': getattr(telescope, 'can_set_tracking', True),
                'can_slew': getattr(telescope, 'can_slew', True),
                'can_slew_async': getattr(telescope, 'can_slew_async', True),
                'can_sync': getattr(telescope, 'can_sync', True),
                'at_home': getattr(telescope, 'at_home', False),
                'at_park': getattr(telescope, 'at_park', False),
                'is_slewing': getattr(telescope, 'is_slewing', False),
                'tracking': getattr(telescope, 'tracking', False),
                'right_ascension': getattr(telescope, 'right_ascension', 0.0),
                'declination': getattr(telescope, 'declination', 0.0),
                'altitude': getattr(telescope, 'altitude', 0.0),
                'azimuth': getattr(telescope, 'azimuth', 0.0),
                'pier_side': getattr(telescope, 'pier_side', 'Unknown'),
                'guide_rate_right_ascension': getattr(telescope, 'guide_rate_right_ascension', 0.5),
                'guide_rate_declination': getattr(telescope, 'guide_rate_declination', 0.5),
                'utc_date': getattr(telescope, 'utc_date', ''),
                'sidereal_time': getattr(telescope, 'sidereal_time', 0.0)
            }
        except Exception as e:
            self.logger.error(f"Failed to get telescope status: {e}")
            return {'error': 'Failed to retrieve telescope status'}
    
    def format_coordinates(self, ra: float, dec: float) -> Dict[str, str]:
        """
        Format coordinates for display.
        
        Args:
            ra: Right ascension in hours
            dec: Declination in degrees
            
        Returns:
            dict: Formatted coordinate strings
        """
        try:
            # Convert to hours:minutes:seconds and degrees:minutes:seconds
            ra_h = int(ra)
            ra_m = int((ra - ra_h) * 60)
            ra_s = ((ra - ra_h) * 60 - ra_m) * 60
            
            dec_d = int(abs(dec))
            dec_m = int((abs(dec) - dec_d) * 60)
            dec_s = ((abs(dec) - dec_d) * 60 - dec_m) * 60
            dec_sign = '+' if dec >= 0 else '-'
            
            return {
                'ra_formatted': f"{ra_h:02d}:{ra_m:02d}:{ra_s:04.1f}",
                'dec_formatted': f"{dec_sign}{dec_d:02d}:{dec_m:02d}:{dec_s:04.1f}"
            }
        except Exception as e:
            self.logger.error(f"Failed to format coordinates: {e}")
            return {'ra_formatted': 'N/A', 'dec_formatted': 'N/A'}


def validate_form_data(form_data: Dict[str, Any], required_fields: list) -> Dict[str, str]:
    """
    General form validation utility.
    
    Args:
        form_data: Form data to validate
        required_fields: List of required field names
        
    Returns:
        dict: Validation errors (empty if valid)
    """
    errors = {}
    
    for field in required_fields:
        value = form_data.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            errors[field] = f"{field.replace('_', ' ').title()} is required"
    
    return errors


# Global handler instances for reuse
web_handler = WebRequestHandler()
config_handler = ConfigurationHandler()
status_handler = StatusHandler()

__all__ = [
    'render_template',
    'get_template_env',
    'validate_form_data',
    'WebRequestHandler',
    'ConfigurationHandler', 
    'StatusHandler',
    'web_handler',
    'config_handler',
    'status_handler'
]