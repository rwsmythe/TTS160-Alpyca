"""
Main web page resources for Alpaca driver web interface.

This module provides Falcon resource classes for serving complete HTML pages
in the web interface. Each resource handles GET/POST requests for full page
loads and renders complete HTML responses using Jinja2 templates.

Classes:
    DashboardResource: Main dashboard/home page
    ServerConfigResource: Server configuration page
    TelescopeConfigResource: Telescope configuration page  
    TelescopeStatusResource: Telescope status monitoring page
"""

from typing import Dict, Any
from falcon import Request, Response

# Import handlers for business logic
try:
    from .handlers import (
        render_template, 
        web_handler, 
        config_handler, 
        status_handler,
        validate_form_data
    )
    import log
except ImportError as e:
    raise ImportError(f"Failed to import required modules: {e}") from e

__version__ = "1.0.0"
__author__ = "Reid Smythe <rwsmythe@gmail.com>"


class DashboardResource:
    """
    Main dashboard/home page resource.
    
    Serves the primary navigation page with overview information
    and links to configuration and status pages.
    """
    
    def __init__(self):
        """Initialize the dashboard resource."""
        self.logger = log.logger
    
    def on_get(self, req: Request, resp: Response) -> None:
        """
        Handle GET request for dashboard page.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            # Get overview data for dashboard
            context = {
                'status': {'driver_version': '1.0.0', 'server_running': True, 'discovery_active': True},    #dummy status TODO: replace later with actual status
                'page_title': 'Alpaca Telescope Driver',
                'current_page': 'dashboard',
                'server_config': config_handler.get_server_config(),
                'telescope_status': status_handler.get_telescope_status(),
                'navigation_items': [
                    {'name': 'Server Configuration', 'url': '/server-config', 'active': False},
                    {'name': 'Telescope Configuration', 'url': '/telescope-config', 'active': False},
                    {'name': 'Telescope Status', 'url': '/telescope-status', 'active': False}
                ]
            }
            
            html_content = render_template('dashboard.html', **context)
            web_handler.set_html_response(resp, html_content)
            
            self.logger.info("Dashboard page served successfully")
            
        except Exception as e:
            self.logger.error(f"Error serving dashboard page: {e}")
            web_handler.set_error_response(resp, '500 Internal Server Error', 
                                         'Failed to load dashboard page')


class ServerConfigResource:
    """
    Server configuration page resource.
    
    Handles display and updates of server configuration settings
    including IP address, port, device information, and capabilities.
    """
    
    def __init__(self):
        """Initialize the server configuration resource."""
        self.logger = log.logger
    
    def on_get(self, req: Request, resp: Response) -> None:
        """
        Handle GET request for server configuration page.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            context = {
                'page_title': 'Server Configuration',
                'current_page': 'server_config',
                'config': config_handler.get_server_config(),
                'status': status_handler.get_telescope_status(),
                'errors': {},
                'navigation_items': [
                    {'name': 'Dashboard', 'url': '/', 'active': False},
                    {'name': 'Server Configuration', 'url': '/server-config', 'active': True},
                    {'name': 'Telescope Configuration', 'url': '/telescope-config', 'active': False},
                    {'name': 'Telescope Status', 'url': '/telescope-status', 'active': False}
                ]
            }
            
            html_content = render_template('server_config.html', **context)
            web_handler.set_html_response(resp, html_content)
            
            self.logger.info("Server configuration page served successfully")
            
        except Exception as e:
            self.logger.error(f"Error serving server configuration page: {e}")
            web_handler.set_error_response(resp, '500 Internal Server Error',
                                         'Failed to load server configuration page')
    
    def on_post(self, req: Request, resp: Response) -> None:
        """
        Handle POST request for server configuration updates.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            form_data = web_handler.parse_form_data(req)
            
            # Validate form data
            errors = config_handler.validate_server_config(form_data)
            
            if errors:
                # Re-render page with errors
                context = {
                    'page_title': 'Server Configuration',
                    'current_page': 'server_config',
                    'config': form_data,  # Use submitted data to preserve user input
                    'errors': errors,
                    'navigation_items': [
                        {'name': 'Dashboard', 'url': '/', 'active': False},
                        {'name': 'Server Configuration', 'url': '/server-config', 'active': True},
                        {'name': 'Telescope Configuration', 'url': '/telescope-config', 'active': False},
                        {'name': 'Telescope Status', 'url': '/telescope-status', 'active': False}
                    ]
                }
                
                html_content = render_template('server_config.html', **context)
                web_handler.set_html_response(resp, html_content)
                
                self.logger.warning(f"Server configuration validation failed: {errors}")
                
            else:
                # Save configuration
                if config_handler.save_server_config(form_data):
                    # Redirect to success page or back to form with success message
                    context = {
                        'page_title': 'Server Configuration',
                        'current_page': 'server_config',
                        'config': config_handler.get_server_config(),
                        'success_message': 'Server configuration saved successfully',
                        'navigation_items': [
                            {'name': 'Dashboard', 'url': '/', 'active': False},
                            {'name': 'Server Configuration', 'url': '/server-config', 'active': True},
                            {'name': 'Telescope Configuration', 'url': '/telescope-config', 'active': False},
                            {'name': 'Telescope Status', 'url': '/telescope-status', 'active': False}
                        ]
                    }
                    
                    html_content = render_template('server_config.html', **context)
                    web_handler.set_html_response(resp, html_content)
                    
                    self.logger.info("Server configuration saved successfully")
                    
                else:
                    # Save failed
                    context = {
                        'page_title': 'Server Configuration',
                        'current_page': 'server_config',
                        'config': form_data,
                        'error_message': 'Failed to save server configuration',
                        'navigation_items': [
                            {'name': 'Dashboard', 'url': '/', 'active': False},
                            {'name': 'Server Configuration', 'url': '/server-config', 'active': True},
                            {'name': 'Telescope Configuration', 'url': '/telescope-config', 'active': False},
                            {'name': 'Telescope Status', 'url': '/telescope-status', 'active': False}
                        ]
                    }
                    
                    html_content = render_template('server_config.html', **context)
                    web_handler.set_html_response(resp, html_content)
                    
                    self.logger.error("Failed to save server configuration")
        
        except Exception as e:
            self.logger.error(f"Error processing server configuration POST: {e}")
            web_handler.set_error_response(resp, '500 Internal Server Error',
                                         'Failed to process configuration update')


class TelescopeConfigResource:
    """
    Telescope configuration page resource.
    
    Handles display and updates of telescope-specific configuration settings
    including mount type, capabilities, and operational parameters.
    """
    
    def __init__(self):
        """Initialize the telescope configuration resource."""
        self.logger = log.logger
    
    def on_get(self, req: Request, resp: Response) -> None:
        """
        Handle GET request for telescope configuration page.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            context = {
                'page_title': 'Telescope Configuration',
                'current_page': 'telescope_config',
                'config': config_handler.get_telescope_config(),
                'navigation_items': [
                    {'name': 'Dashboard', 'url': '/', 'active': False},
                    {'name': 'Server Configuration', 'url': '/server-config', 'active': False},
                    {'name': 'Telescope Configuration', 'url': '/telescope-config', 'active': True},
                    {'name': 'Telescope Status', 'url': '/telescope-status', 'active': False}
                ]
            }
            
            html_content = render_template('telescope_config.html', **context)
            web_handler.set_html_response(resp, html_content)
            
            self.logger.info("Telescope configuration page served successfully")
            
        except Exception as e:
            self.logger.error(f"Error serving telescope configuration page: {e}")
            web_handler.set_error_response(resp, '500 Internal Server Error',
                                         'Failed to load telescope configuration page')
    
    def on_post(self, req: Request, resp: Response) -> None:
        """
        Handle POST request for telescope configuration updates.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            form_data = web_handler.parse_form_data(req)
            
            # Validate form data
            errors = config_handler.validate_telescope_config(form_data)
            
            if errors:
                # Re-render page with errors
                context = {
                    'page_title': 'Telescope Configuration',
                    'current_page': 'telescope_config',
                    'config': form_data,  # Use submitted data to preserve user input
                    'errors': errors,
                    'navigation_items': [
                        {'name': 'Dashboard', 'url': '/', 'active': False},
                        {'name': 'Server Configuration', 'url': '/server-config', 'active': False},
                        {'name': 'Telescope Configuration', 'url': '/telescope-config', 'active': True},
                        {'name': 'Telescope Status', 'url': '/telescope-status', 'active': False}
                    ]
                }
                
                html_content = render_template('telescope_config.html', **context)
                web_handler.set_html_response(resp, html_content)
                
                self.logger.warning(f"Telescope configuration validation failed: {errors}")
                
            else:
                # Save configuration
                if config_handler.save_telescope_config(form_data):
                    # Success
                    context = {
                        'page_title': 'Telescope Configuration',
                        'current_page': 'telescope_config',
                        'config': config_handler.get_telescope_config(),
                        'success_message': 'Telescope configuration saved successfully',
                        'navigation_items': [
                            {'name': 'Dashboard', 'url': '/', 'active': False},
                            {'name': 'Server Configuration', 'url': '/server-config', 'active': False},
                            {'name': 'Telescope Configuration', 'url': '/telescope-config', 'active': True},
                            {'name': 'Telescope Status', 'url': '/telescope-status', 'active': False}
                        ]
                    }
                    
                    html_content = render_template('telescope_config.html', **context)
                    web_handler.set_html_response(resp, html_content)
                    
                    self.logger.info("Telescope configuration saved successfully")
                    
                else:
                    # Save failed
                    context = {
                        'page_title': 'Telescope Configuration',
                        'current_page': 'telescope_config',
                        'config': form_data,
                        'error_message': 'Failed to save telescope configuration',
                        'navigation_items': [
                            {'name': 'Dashboard', 'url': '/', 'active': False},
                            {'name': 'Server Configuration', 'url': '/server-config', 'active': False},
                            {'name': 'Telescope Configuration', 'url': '/telescope-config', 'active': True},
                            {'name': 'Telescope Status', 'url': '/telescope-status', 'active': False}
                        ]
                    }
                    
                    html_content = render_template('telescope_config.html', **context)
                    web_handler.set_html_response(resp, html_content)
                    
                    self.logger.error("Failed to save telescope configuration")
        
        except Exception as e:
            self.logger.error(f"Error processing telescope configuration POST: {e}")
            web_handler.set_error_response(resp, '500 Internal Server Error',
                                         'Failed to process configuration update')


class TelescopeStatusResource:
    """
    Telescope status monitoring page resource.
    
    Provides real-time monitoring interface for telescope status,
    coordinates, and operational state with auto-updating displays.
    """
    
    def __init__(self):
        """Initialize the telescope status resource."""
        self.logger = log.logger
    
    def on_get(self, req: Request, resp: Response) -> None:
        """
        Handle GET request for telescope status page.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            telescope_status = status_handler.get_telescope_status()
            
            # Add formatted coordinates if available
            if 'right_ascension' in telescope_status and 'declination' in telescope_status:
                coordinates = status_handler.format_coordinates(
                    telescope_status['right_ascension'],
                    telescope_status['declination']
                )
                telescope_status.update(coordinates)
            
            context = {
                'page_title': 'Telescope Status',
                'current_page': 'telescope_status',
                'status': telescope_status,
                'refresh_interval': 2000,  # 2 seconds for auto-refresh
                'navigation_items': [
                    {'name': 'Dashboard', 'url': '/', 'active': False},
                    {'name': 'Server Configuration', 'url': '/server-config', 'active': False},
                    {'name': 'Telescope Configuration', 'url': '/telescope-config', 'active': False},
                    {'name': 'Telescope Status', 'url': '/telescope-status', 'active': True}
                ]
            }
            
            html_content = render_template('telescope_status.html', **context)
            web_handler.set_html_response(resp, html_content)
            
            self.logger.info("Telescope status page served successfully")
            
        except Exception as e:
            self.logger.error(f"Error serving telescope status page: {e}")
            web_handler.set_error_response(resp, '500 Internal Server Error',
                                         'Failed to load telescope status page')


__all__ = [
    'DashboardResource',
    'ServerConfigResource',
    'TelescopeConfigResource',
    'TelescopeStatusResource'
]