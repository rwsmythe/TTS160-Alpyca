"""
Web interface package for Alpaca driver management.

This package provides a web-based interface for configuring and monitoring
an Alpaca-compatible telescope driver using Falcon WSGI framework and HTMX
for dynamic updates.

Modules:
    resources: Main web page resource classes for full page requests
    htmx_resources: HTMX-specific resource classes for partial page updates
    handlers: Business logic handlers for processing web requests

Example:
    >>> from web import DashboardResource, ServerConfigResource
    >>> app.add_route('/', DashboardResource())
    >>> app.add_route('/server-config', ServerConfigResource())
"""

from typing import List

__version__ = "1.0.0"
__author__ = "Reid Smythe <rwsmythe@gmail.com>"

# Import main page resources
try:
    from .resources import (
        DashboardResource,
        ServerConfigResource,
        TelescopeConfigResource,
        TelescopeStatusResource,
    )
except ImportError as e:
    raise ImportError(f"Failed to import web resources: {e}") from e

# Import HTMX partial update resources  
try:
    from .htmx_resources import (
        ServerFormResource,
        TelescopeFormResource,
        StatusUpdateResource,
        ExitHandlerResource,
    )
except ImportError as e:
    raise ImportError(f"Failed to import HTMX resources: {e}") from e

# Import utility handlers (optional)
try:
    from .handlers import (
        WebRequestHandler,
        ConfigurationHandler,
        StatusHandler,
    )
    _HANDLERS_AVAILABLE = True
except ImportError:
    # Handlers are optional for basic functionality
    WebRequestHandler = None
    ConfigurationHandler = None  
    StatusHandler = None
    _HANDLERS_AVAILABLE = False

# Define public API - conditionally include handlers if available
__all__: List[str] = [
    # Main page resources
    "DashboardResource",
    "ServerConfigResource", 
    "TelescopeConfigResource",
    "TelescopeStatusResource",
    # HTMX resources
    "ServerFormResource",
    "TelescopeFormResource", 
    "StatusUpdateResource",
    "ExitHandlerResource",
    # Package metadata
    "__version__",
    "__author__",
]

# Add handlers to public API if available
if _HANDLERS_AVAILABLE:
    __all__.extend([
        "WebRequestHandler",
        "ConfigurationHandler", 
        "StatusHandler",
    ])


def get_all_resource_classes() -> dict:
    """
    Get all available web resource classes as a mapping of route patterns.
    
    Returns:
        dict: Mapping of route patterns to resource classes (not instances)
        
    Example:
        >>> resource_classes = get_all_resource_classes()
        >>> for route, resource_cls in resource_classes.items():
        ...     app.add_route(route, resource_cls())
    """
    return {
        # Main pages
        '/': DashboardResource,
        '/server-config': ServerConfigResource,
        '/telescope-config': TelescopeConfigResource, 
        '/telescope-status': TelescopeStatusResource,
        
        # HTMX endpoints
        '/htmx/server-form': ServerFormResource,
        '/htmx/telescope-form': TelescopeFormResource,
        '/htmx/status-update': StatusUpdateResource,
        '/htmx/exit': ExitHandlerResource,
    }


def get_main_resource_classes() -> dict:
    """
    Get only main page resource classes (excluding HTMX endpoints).
    
    Returns:
        dict: Mapping of main page routes to resource classes
    """
    return {
        '/': DashboardResource,
        '/server-config': ServerConfigResource,
        '/telescope-config': TelescopeConfigResource,
        '/telescope-status': TelescopeStatusResource,
    }


def get_htmx_resource_classes() -> dict:
    """
    Get only HTMX partial update resource classes.
    
    Returns:
        dict: Mapping of HTMX routes to resource classes
    """
    return {
        '/htmx/server-form': ServerFormResource,
        '/htmx/telescope-form': TelescopeFormResource, 
        '/htmx/status-update': StatusUpdateResource,
        '/htmx/exit': ExitHandlerResource,
    }


def register_all_routes(app) -> None:
    """
    Convenience function to register all routes with a Falcon app.
    
    Args:
        app: Falcon application instance
        
    Raises:
        AttributeError: If app doesn't have add_route method
        
    Example:
        >>> import falcon
        >>> from web import register_all_routes
        >>> app = falcon.App()
        >>> register_all_routes(app)
    """
    if not hasattr(app, 'add_route'):
        raise AttributeError("app must be a Falcon application with add_route method")
    
    for route, resource_cls in get_all_resource_classes().items():
        app.add_route(route, resource_cls())