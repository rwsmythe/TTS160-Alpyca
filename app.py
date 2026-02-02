# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# app.py - Application module
#
# Part of the AlpycaDevice Alpaca skeleton/template device driver
#
# Author:   Robert B. Denny <rdenny@dc3.com> (rbd)
#
# Python Compatibility: Requires Python 3.7 or later
# GitHub: https://github.com/ASCOMInitiative/AlpycaDevice
#
# -----------------------------------------------------------------------------
# MIT License
#
# Copyright (c) 2022-2024 Bob Denny
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# -----------------------------------------------------------------------------
# Edit History:
# 16-Dec-2022   rbd 0.1 Initial edit for Alpaca sample/template
# 20-Dec-2022   rbd 0.1 Correct endpoint URIs
# 21-Dec-2022   rbd 0.1 Refactor for import protection. Add configurtion.
# 22-Dec-2020   rbd 0.1 Start of logging
# 24-Dec-2022   rbd 0.1 Logging
# 25-Dec-2022   rbd 0.1 Add milliseconds to logger time stamp
# 27-Dec-2022   rbd 0.1 Post-processing logging of request only if not 200 OK
#               MIT License and module header. No multicast on device duh.
# 28-Dec-2022   rbd 0.1 Rename conf.py to config.py to avoid conflict with sphinx
# 30-Dec-2022   rbd 0.1 Device number in /setup routing template. Last chance
#               exception handler, Falcon responder uncaught exeption handler.
# 01-Jan-2023   rbd 0.1 Docstring docs
# 13-Jan-2023   rbd 0.1 More docstring docs. Fix LoggingWSGIRequestHandler,
#               log.logger needs explicit setting in main()
# 23-May-2023   rbd 0.2 GitHub Issue #3 https://github.com/BobDenny/AlpycaDevice/issues/3
#               Corect routing device number capture spelling.
# 23-May-2023   rbd 0.2 Refactoring for  multiple ASCOM device type support
#               GitHub issue #1
# 13-Sep-2024   rbd 1.0 Add support for enum classes within the responder modules
#               GitHub issue #12
# 03-Jan-2025   rbd 1.1 Clarify devices vs device types at import site. Comment only,
#               no logic changes.
#
import sys
import traceback
import inspect
import argparse
from enum import IntEnum

from waitress import serve as waitress_serve

# -- isort wants the above line to be blank --
# Controller classes (for routing)
import discovery
import exceptions
from falcon import Request, Response, App, HTTPInternalServerError
import management
import setup
import log
import webbrowser
import threading
import time
import TTS160Global
from discovery import DiscoveryResponder
from shr import set_shr_logger
from datetime import datetime

# Note: telescope_gui is imported lazily to support headless mode

##############################
# FOR EACH ASCOM DEVICE TYPE #
##############################
import telescope

# Global reference for shutdown
_httpd_server = None
_DSC = None
server_cfg = None

# Misc Variables
APP_START_TIME = datetime.now()

#--------------
API_VERSION = 1
#--------------

# Note: LoggingWSGIRequestHandler removed in favor of waitress production server
# Waitress provides its own logging and multi-threaded request handling


def parse_arguments():
    """Parse command line arguments for operating mode and configuration.

    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description='TTS160 Alpaca Driver - ASCOM Alpaca telescope driver for TTS-160 mount',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Operating Modes:
  Default         Start with GUI, open browser automatically
  --headless      API only, no GUI (for remote/automated use)
  --gui-available Start GUI server but don't open browser

Examples:
  python app.py                    # Normal desktop use with GUI
  python app.py --headless         # Remote observatory / Raspberry Pi
  python app.py --gui-available    # Service mode, GUI accessible but no browser
  python app.py --port 5556        # Custom API port
  python app.py --gui-port 8081    # Custom GUI port
'''
    )

    # Operating mode
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--headless', '--no-gui',
        action='store_true',
        dest='headless',
        help='Run without GUI (API server only)'
    )
    mode_group.add_argument(
        '--gui-available',
        action='store_true',
        dest='gui_available',
        help='Start GUI server but do not open browser'
    )

    # Port configuration
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=None,
        help='Alpaca API port (default: from config, typically 5555)'
    )
    parser.add_argument(
        '--gui-port',
        type=int,
        default=None,
        dest='gui_port',
        help='GUI web server port (default: from config, typically 8080)'
    )

    # Network binding
    parser.add_argument(
        '--bind', '-b',
        type=str,
        default=None,
        help='Bind address (default: 0.0.0.0 for all interfaces)'
    )

    # Logging
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default=None,
        dest='log_level',
        help='Override logging level'
    )

    # Config file
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Path to config.toml file (default: ./config.toml)'
    )

    return parser.parse_args()


def start_gui_thread_lazy(logger, port: int, bind: str = '0.0.0.0',
                          theme: str = 'dark', refresh_interval: float = 1.0):
    """Start GUI in separate thread with lazy import.

    This function imports telescope_gui only when called, allowing
    headless mode to avoid loading NiceGUI dependencies entirely.

    Args:
        logger: Logger instance
        port: GUI server port
        bind: Bind address for GUI server
        theme: Color theme - 'dark' or 'light'
        refresh_interval: Status update interval in seconds

    Returns:
        threading.Thread: The GUI thread (already started)
    """
    def run_gui():
        try:
            # Import GUI modules only when needed
            from telescope_gui import TelescopeInterface
            interface = TelescopeInterface(
                logger, port, bind_address=bind,
                theme=theme, refresh_interval=refresh_interval
            )
            interface.start_gui_server()
        except Exception as e:
            logger.error(f"GUI server error: {e}")

    gui_thread = threading.Thread(target=run_gui, daemon=True)
    gui_thread.start()
    return gui_thread


#-----------------------
# Magic routing function
# ----------------------
def init_routes(app: App, devname: str, module):
    """Initialize Falcon routing from URI to responser classses

    Inspects a module and finds all classes, assuming they are Falcon
    responder classes, and calls Falcon to route the corresponding
    Alpaca URI to each responder. This is done by creating the
    URI template from the responder class name.

    Note that it is sufficient to create the controller instance
    directly from the type returned by inspect.getmembers() since
    the instance is saved within Falcon as its resource controller.
    The responder methods are called with an additional 'devno'
    parameter, containing the device number from the URI. Reject
    negative device numbers.

    Args:
        app (App): The instance of the Falcon processor app
        devname (str): The name of the device (e.g. 'rotator")
        module (module): Module object containing responder classes

    Notes:
        * The call to app.add_route() creates the single instance of the
          router class right in the call, as the second parameter.
        * The device number is extracted from the URI by using an
          **int** placeholder in the URI template, and also using
          a format converter to assure that the number is not
          negative. If it is, Falcon will send back an HTTP
          ``400 Bad Request``.

    """

    memlist = inspect.getmembers(module, inspect.isclass)
    for cname,ctype in memlist:
        # Only classes *defined* in the module and not the enum classes
        if ctype.__module__ == module.__name__ and not issubclass(ctype, IntEnum):
            app.add_route(f'/api/v{API_VERSION}/{devname}/{{devnum:int(min=0)}}/{cname.lower()}', ctype())  # type() creates instance!


def custom_excepthook(exc_type, exc_value, exc_traceback):
    """Last-chance exception handler

    Caution:
        Hook this as last-chance only after the config info
        has been initiized and the logger is set up!

    Assures that any unhandled exceptions are logged to our logfile.
    Should "never" be called since unhandled exceptions are
    theoretically caught in falcon. Well it's here so the
    exception has a chance of being logged to our file. It's
    used by :py:func:`~app.falcon_uncaught_exception_handler` to
    make sure exception info is logged instead of going to
    stdout.

    Args:
        exc_type (_type_): _description_
        exc_value (_type_): _description_
        exc_traceback (_type_): _description_

    Notes:
        * See the Python docs for `sys.excepthook() <https://docs.python.org/3/library/sys.html#sys.excepthook>`_
        * See `This StackOverflow article <https://stackoverflow.com/a/58593345/159508>`_
        * A config option provides for a full traceback to be logged.

    """
    # Do not print exception when user cancels the program
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    log.logger.error(f'An uncaught {exc_type.__name__} exception occurred:')
    log.logger.error(exc_value)

    if server_cfg.verbose_driver_exceptions and exc_traceback:
        format_exception = traceback.format_tb(exc_traceback)
        for line in format_exception:
            log.logger.error(repr(line))


def falcon_uncaught_exception_handler(req: Request, resp: Response, ex: BaseException, params):
    """Handle Uncaught Exceptions while in a Falcon Responder

        This catches unhandled exceptions within the Falcon responder,
        logging the info to our log file instead of it being lost to
        stdout. Then it logs and responds with a 500 Internal Server Error.

    """
    exc = sys.exc_info()
    custom_excepthook(exc[0], exc[1], exc[2])
    raise HTTPInternalServerError('Internal Server Error', 'Alpaca endpoint responder failed. See logfile.')

def get_uptime():
    """Get formatted uptime string"""
    uptime_delta = datetime.now() - APP_START_TIME
    days = uptime_delta.days
    hours, remainder = divmod(uptime_delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"

# ===========
# APP STARTUP
# ===========
def main():
    """Application entry point with command line argument support.

    Supports three operating modes:
    - Full GUI mode (default): Starts API server + GUI server, opens browser
    - Headless mode (--headless): API server only, no GUI dependencies loaded
    - GUI-available mode (--gui-available): Both servers, but no browser auto-open
    """
    global _DSC
    global _httpd_server
    global _gui_thread
    global server_cfg

    # Parse command line arguments
    args = parse_arguments()

    # Load configuration
    server_cfg = TTS160Global.get_serverconfig()

    # Override config with command line arguments
    if args.port is not None:
        server_cfg.port = args.port
    if args.gui_port is not None:
        server_cfg.gui_port = args.gui_port
    if args.bind is not None:
        server_cfg.ip_address = args.bind

    # Initialize logging
    logger = log.init_logging()
    log.logger = logger
    exceptions.logger = logger
    discovery.logger = logger
    set_shr_logger(logger)

    # Initialize telescope device
    telescope.start_TTS160_dev(logger)
    telescope.logger = logger

    # Last-Chance Exception Handler
    sys.excepthook = custom_excepthook

    # Alpaca Discovery Responder
    _DSC = DiscoveryResponder(server_cfg.ip_address, server_cfg.port)

    # Initialize Falcon WSGI application
    falc_app = App()
    init_routes(falc_app, 'telescope', telescope)

    # Alpaca management endpoints
    falc_app.add_route('/management/apiversions', management.apiversions())
    falc_app.add_route(f'/management/v{API_VERSION}/description', management.description())
    falc_app.add_route(f'/management/v{API_VERSION}/configureddevices', management.configureddevices())
    falc_app.add_route(f'/setup/v{API_VERSION}/telescope/{{devnum}}/setup', setup.devsetup())
    falc_app.add_route('/shutdown', setup.ShutdownHandler())

    # Install unhandled exception processor
    falc_app.add_error_handler(Exception, falcon_uncaught_exception_handler)

    # Determine operating mode
    # Priority: command line args > config file settings
    gui_enabled = not args.headless and server_cfg.gui_enabled
    auto_open_browser = (
        gui_enabled
        and not args.gui_available
        and server_cfg.gui_auto_open_browser
    )

    # Get port configuration
    gui_port = server_cfg.gui_port
    host = server_cfg.ip_address if server_cfg.ip_address else '0.0.0.0'
    port = server_cfg.port
    threads = server_cfg.threads

    # Start GUI server if enabled
    _gui_thread = None
    if gui_enabled:
        logger.info(f'==STARTUP== Starting GUI server on port {gui_port}')
        try:
            _gui_thread = start_gui_thread_lazy(
                logger, gui_port, server_cfg.gui_bind_address,
                theme=server_cfg.gui_theme,
                refresh_interval=server_cfg.gui_refresh_interval
            )
            logger.info('==STARTUP== GUI server thread started successfully')
        except Exception as e:
            logger.error(f'==STARTUP== Failed to start GUI server: {e}')
            logger.info('==STARTUP== Continuing without GUI...')
    else:
        logger.info('==STARTUP== Running in headless mode (no GUI)')

    # Log startup information
    logger.info(f'==STARTUP== Starting Alpaca API server on {host}:{port} with {threads} worker threads')
    if gui_enabled:
        logger.info(f'==STARTUP== GUI available at http://localhost:{gui_port}')
    logger.info('==STARTUP== Time stamps are UTC')

    # Open browser if configured
    if auto_open_browser and _gui_thread:
        def open_browser():
            time.sleep(1.5)  # Wait for servers to start
            webbrowser.open(f'http://localhost:{gui_port}')
        threading.Thread(target=open_browser, daemon=True).start()

    # Start Alpaca API server (blocking)
    waitress_serve(falc_app, host=host, port=port, threads=threads)

# ========================
if __name__ == '__main__':
    main()
# ========================
