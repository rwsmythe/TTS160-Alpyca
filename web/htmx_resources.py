"""
HTMX resources for dynamic partial page updates.

This module provides Falcon resource classes that handle HTMX requests
and return partial HTML snippets for dynamic page updates without full
page reloads. These resources work with HTMX frontend components to
provide a responsive, interactive user interface.

Classes:
    ServerFormResource: Server configuration form processing and updates
    TelescopeFormResource: Telescope configuration form processing and updates
    StatusUpdateResource: Real-time telescope status updates
    ExitHandlerResource: Application shutdown handling
"""

import sys
import os
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


class ServerFormResource:
    """
    HTMX resource for server configuration form processing.
    
    Handles server configuration form submissions and returns
    partial HTML updates for validation errors, success messages,
    and form state changes.
    """
    
    def __init__(self):
        """Initialize the server form resource."""
        self.logger = log.logger
    
    def on_post(self, req: Request, resp: Response) -> None:
        """
        Handle POST request for server configuration form submission.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            form_data = web_handler.parse_form_data(req)
            
            # Validate form data
            errors = config_handler.validate_server_config(form_data)
            
            if errors:
                # Return validation errors as partial HTML
                context = {
                    'errors': errors,
                    'config': form_data,  # Preserve user input
                    'form_type': 'server'
                }
                
                html_content = render_template('htmx/form_errors.html', **context)
                web_handler.set_html_response(resp, html_content)
                
                self.logger.warning(f"Server form validation failed: {errors}")
                
            else:
                # Save configuration
                if config_handler.save_server_config(form_data):
                    # Return success message
                    context = {
                        'message': 'Server configuration saved successfully',
                        'config': config_handler.get_server_config(),
                        'form_type': 'server'
                    }
                    
                    html_content = render_template('htmx/form_success.html', **context)
                    web_handler.set_html_response(resp, html_content)
                    
                    self.logger.info("Server configuration saved via HTMX")
                    
                else:
                    # Return error message
                    context = {
                        'message': 'Failed to save server configuration',
                        'form_type': 'server'
                    }
                    
                    html_content = render_template('htmx/form_error.html', **context)
                    web_handler.set_html_response(resp, html_content)
                    
                    self.logger.error("Failed to save server configuration via HTMX")
        
        except Exception as e:
            self.logger.error(f"Error processing server form HTMX request: {e}")
            context = {
                'message': 'An unexpected error occurred',
                'form_type': 'server'
            }
            html_content = render_template('htmx/form_error.html', **context)
            web_handler.set_html_response(resp, html_content)
    
    def on_get(self, req: Request, resp: Response) -> None:
        """
        Handle GET request to refresh server configuration form.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            context = {
                'config': config_handler.get_server_config(),
                'form_type': 'server'
            }
            
            html_content = render_template('htmx/server_form.html', **context)
            web_handler.set_html_response(resp, html_content)
            
            self.logger.debug("Server form refreshed via HTMX")
            
        except Exception as e:
            self.logger.error(f"Error refreshing server form via HTMX: {e}")
            web_handler.set_error_response(resp, '500 Internal Server Error',
                                         'Failed to refresh form')


class TelescopeFormResource:
    """
    HTMX resource for telescope configuration form processing.
    
    Handles telescope configuration form submissions and returns
    partial HTML updates for validation errors, success messages,
    and form state changes.
    """
    
    def __init__(self):
        """Initialize the telescope form resource."""
        self.logger = log.logger
    
    def on_post(self, req: Request, resp: Response) -> None:
        """
        Handle POST request for telescope configuration form submission.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            form_data = web_handler.parse_form_data(req)
            
            # Validate form data
            errors = config_handler.validate_telescope_config(form_data)
            
            if errors:
                # Return validation errors as partial HTML
                context = {
                    'errors': errors,
                    'config': form_data,  # Preserve user input
                    'form_type': 'telescope'
                }
                
                html_content = render_template('htmx/form_errors.html', **context)
                web_handler.set_html_response(resp, html_content)
                
                self.logger.warning(f"Telescope form validation failed: {errors}")
                
            else:
                # Save configuration
                if config_handler.save_telescope_config(form_data):
                    # Return success message
                    context = {
                        'message': 'Telescope configuration saved successfully',
                        'config': config_handler.get_telescope_config(),
                        'form_type': 'telescope'
                    }
                    
                    html_content = render_template('htmx/form_success.html', **context)
                    web_handler.set_html_response(resp, html_content)
                    
                    self.logger.info("Telescope configuration saved via HTMX")
                    
                else:
                    # Return error message
                    context = {
                        'message': 'Failed to save telescope configuration',
                        'form_type': 'telescope'
                    }
                    
                    html_content = render_template('htmx/form_error.html', **context)
                    web_handler.set_html_response(resp, html_content)
                    
                    self.logger.error("Failed to save telescope configuration via HTMX")
        
        except Exception as e:
            self.logger.error(f"Error processing telescope form HTMX request: {e}")
            context = {
                'message': 'An unexpected error occurred',
                'form_type': 'telescope'
            }
            html_content = render_template('htmx/form_error.html', **context)
            web_handler.set_html_response(resp, html_content)
    
    def on_get(self, req: Request, resp: Response) -> None:
        """
        Handle GET request to refresh telescope configuration form.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            context = {
                'config': config_handler.get_telescope_config(),
                'form_type': 'telescope'
            }
            
            html_content = render_template('htmx/telescope_form.html', **context)
            web_handler.set_html_response(resp, html_content)
            
            self.logger.debug("Telescope form refreshed via HTMX")
            
        except Exception as e:
            self.logger.error(f"Error refreshing telescope form via HTMX: {e}")
            web_handler.set_error_response(resp, '500 Internal Server Error',
                                         'Failed to refresh form')


class StatusUpdateResource:
    """
    HTMX resource for real-time telescope status updates.
    
    Provides periodic status updates for the telescope monitoring
    interface using HTMX polling or server-sent events.
    """
    
    def __init__(self):
        """Initialize the status update resource."""
        self.logger = log.logger
    
    def on_get(self, req: Request, resp: Response) -> None:
        """
        Handle GET request for telescope status update.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            telescope_status = status_handler.get_telescope_status()
            
            # Add formatted coordinates if available
            if ('right_ascension' in telescope_status and 
                'declination' in telescope_status and
                not telescope_status.get('error')):
                
                coordinates = status_handler.format_coordinates(
                    telescope_status['right_ascension'],
                    telescope_status['declination']
                )
                telescope_status.update(coordinates)
            
            context = {
                'status': telescope_status,
                'timestamp': telescope_status.get('utc_date', 'Unknown'),
                'refresh_interval': 2000  # 2 seconds
            }
            
            html_content = render_template('htmx/status_update.html', **context)
            web_handler.set_html_response(resp, html_content)
            
            self.logger.debug("Status update provided via HTMX")
            
        except Exception as e:
            self.logger.error(f"Error providing status update via HTMX: {e}")
            context = {
                'status': {'error': 'Failed to retrieve telescope status'},
                'timestamp': 'Unknown',
                'refresh_interval': 5000  # Slower refresh on error
            }
            html_content = render_template('htmx/status_update.html', **context)
            web_handler.set_html_response(resp, html_content)
    
    def on_post(self, req: Request, resp: Response) -> None:
        """
        Handle POST request for telescope control actions.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            form_data = web_handler.parse_form_data(req)
            action = form_data.get('action', '').lower()
            
            # Handle different telescope actions
            if action == 'park':
                # Implement park command
                success = self._handle_park_command()
                message = 'Park command sent successfully' if success else 'Failed to send park command'
                
            elif action == 'unpark':
                # Implement unpark command
                success = self._handle_unpark_command()
                message = 'Unpark command sent successfully' if success else 'Failed to send unpark command'
                
            elif action == 'stop':
                # Implement stop command
                success = self._handle_stop_command()
                message = 'Stop command sent successfully' if success else 'Failed to send stop command'
                
            elif action == 'find_home':
                # Implement find home command
                success = self._handle_find_home_command()
                message = 'Find home command sent successfully' if success else 'Failed to send find home command'
                
            else:
                success = False
                message = f'Unknown action: {action}'
            
            # Return command result
            context = {
                'message': message,
                'success': success,
                'action': action
            }
            
            html_content = render_template('htmx/command_result.html', **context)
            web_handler.set_html_response(resp, html_content)
            
            self.logger.info(f"Telescope command '{action}' executed via HTMX: {message}")
            
        except Exception as e:
            self.logger.error(f"Error executing telescope command via HTMX: {e}")
            context = {
                'message': 'An error occurred while executing the command',
                'success': False,
                'action': form_data.get('action', 'unknown') if 'form_data' in locals() else 'unknown'
            }
            html_content = render_template('htmx/command_result.html', **context)
            web_handler.set_html_response(resp, html_content)
    
    def _handle_park_command(self) -> bool:
        """
        Handle telescope park command.
        
        Returns:
            bool: True if command succeeded
        """
        try:
            # Implementation depends on your telescope module
            # Example: telescope.park()
            self.logger.info("Park command executed")
            return True
        except Exception as e:
            self.logger.error(f"Park command failed: {e}")
            return False
    
    def _handle_unpark_command(self) -> bool:
        """
        Handle telescope unpark command.
        
        Returns:
            bool: True if command succeeded
        """
        try:
            # Implementation depends on your telescope module
            # Example: telescope.unpark()
            self.logger.info("Unpark command executed")
            return True
        except Exception as e:
            self.logger.error(f"Unpark command failed: {e}")
            return False
    
    def _handle_stop_command(self) -> bool:
        """
        Handle telescope stop command.
        
        Returns:
            bool: True if command succeeded
        """
        try:
            # Implementation depends on your telescope module
            # Example: telescope.abort_slew()
            self.logger.info("Stop command executed")
            return True
        except Exception as e:
            self.logger.error(f"Stop command failed: {e}")
            return False
    
    def _handle_find_home_command(self) -> bool:
        """
        Handle telescope find home command.
        
        Returns:
            bool: True if command succeeded
        """
        try:
            # Implementation depends on your telescope module
            # Example: telescope.find_home()
            self.logger.info("Find home command executed")
            return True
        except Exception as e:
            self.logger.error(f"Find home command failed: {e}")
            return False


class ExitHandlerResource:
    """
    HTMX resource for application shutdown handling.
    
    Provides graceful shutdown functionality accessible from
    the web interface navigation panel.
    """
    
    def __init__(self):
        """Initialize the exit handler resource."""
        self.logger = log.logger
    
    def on_post(self, req: Request, resp: Response) -> None:
        """
        Handle POST request for application shutdown.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            form_data = web_handler.parse_form_data(req)
            confirm = form_data.get('confirm', '').lower()
            
            if confirm == 'yes':
                # Return shutdown confirmation message
                context = {
                    'message': 'Shutting down Alpaca driver...',
                    'confirmed': True
                }
                
                html_content = render_template('htmx/shutdown_confirmation.html', **context)
                web_handler.set_html_response(resp, html_content)
                
                self.logger.info("Shutdown request received via HTMX - initiating shutdown")
                
                # Schedule shutdown after response is sent
                import threading
                def delayed_shutdown():
                    import time
                    time.sleep(2)  # Give time for response to be sent
                    self._perform_shutdown()
                
                shutdown_thread = threading.Thread(target=delayed_shutdown, daemon=True)
                shutdown_thread.start()
                
            else:
                # Return cancellation message
                context = {
                    'message': 'Shutdown cancelled',
                    'confirmed': False
                }
                
                html_content = render_template('htmx/shutdown_confirmation.html', **context)
                web_handler.set_html_response(resp, html_content)
                
                self.logger.info("Shutdown request cancelled via HTMX")
        
        except Exception as e:
            self.logger.error(f"Error handling shutdown request via HTMX: {e}")
            context = {
                'message': 'Error processing shutdown request',
                'confirmed': False
            }
            html_content = render_template('htmx/shutdown_confirmation.html', **context)
            web_handler.set_html_response(resp, html_content)
    
    def on_get(self, req: Request, resp: Response) -> None:
        """
        Handle GET request for shutdown confirmation dialog.
        
        Args:
            req: Falcon request object
            resp: Falcon response object
        """
        try:
            context = {
                'show_confirmation': True
            }
            
            html_content = render_template('htmx/shutdown_dialog.html', **context)
            web_handler.set_html_response(resp, html_content)
            
            self.logger.debug("Shutdown dialog displayed via HTMX")
            
        except Exception as e:
            self.logger.error(f"Error displaying shutdown dialog via HTMX: {e}")
            web_handler.set_error_response(resp, '500 Internal Server Error',
                                         'Failed to display shutdown dialog')
    
    def _perform_shutdown(self) -> None:
        """
        Perform application shutdown.
        
        Note:
            This method will need to be customized based on your
            specific shutdown requirements and global server reference.
        """
        try:
            self.logger.info("Performing application shutdown...")
            
            # Stop discovery responder if running
            # global _DSC
            # if _DSC:
            #     _DSC.stop()
            
            # Shutdown HTTP server
            # global _httpd_server
            # if _httpd_server:
            #     _httpd_server.shutdown()
            
            # Exit the application
            os._exit(0)
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            # Force exit on error
            os._exit(1)


__all__ = [
    'ServerFormResource',
    'TelescopeFormResource',
    'StatusUpdateResource',
    'ExitHandlerResource'
]