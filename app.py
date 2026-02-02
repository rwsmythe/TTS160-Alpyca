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
#from config import Config
from discovery import DiscoveryResponder
from shr import set_shr_logger
from datetime import datetime

from telescope_gui import start_gui_thread

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
    """ Global variables """
    
    global _DSC
    global _httpd_server
    global _gui_thread
    global server_cfg

    """ Application startup"""

    server_cfg = TTS160Global.get_serverconfig()
    logger = log.init_logging()
    # Share this logger throughout
    log.logger = logger
    exceptions.logger = logger
    telescope.start_TTS160_dev(logger) #return telescope object for use
    discovery.logger = logger
    set_shr_logger(logger)

    #########################
    # FOR EACH ASCOM DEVICE #
    #########################
    telescope.logger = logger

    # -----------------------------
    # Last-Chance Exception Handler
    # -----------------------------
    sys.excepthook = custom_excepthook

    # ---------
    # DISCOVERY
    # ---------
    _DSC = DiscoveryResponder(server_cfg.ip_address, server_cfg.port)

    # ----------------------------------
    # MAIN HTTP/REST API ENGINE (FALCON)
    # ----------------------------------
    # falcon.App instances are callable WSGI apps
    falc_app = App()
    #
    # Initialize routes for each endpoint the magic way
    #
    #########################
    # FOR EACH ASCOM DEVICE #
    #########################
    init_routes(falc_app, 'telescope', telescope)
    #
    # Initialize routes for Alpaca support endpoints
    falc_app.add_route('/management/apiversions', management.apiversions())
    falc_app.add_route(f'/management/v{API_VERSION}/description', management.description())
    falc_app.add_route(f'/management/v{API_VERSION}/configureddevices', management.configureddevices())
    falc_app.add_route(f'/setup/v{API_VERSION}/telescope/{{devnum}}/setup', setup.devsetup())
    falc_app.add_route('/shutdown', setup.ShutdownHandler())

    #
    # Install the unhandled exception processor. See above,
    #
    falc_app.add_error_handler(Exception, falcon_uncaught_exception_handler)

    # ------------------
    # SERVER APPLICATION
    # ------------------
    # Using waitress production WSGI server with multi-threading support
    gui_port = server_cfg.setup_port
    logger.info(f'==STARTUP== Starting GUI server on port {gui_port}')
    try:
        _gui_thread = start_gui_thread(logger, gui_port)
        logger.info(f'==STARTUP== GUI server thread started successfully')
    except Exception as e:
        logger.error(f'==STARTUP== Failed to start GUI server: {e}')
        logger.info('==STARTUP== Continuing without GUI...')
        _gui_thread = None

    # Determine host binding
    host = server_cfg.ip_address if server_cfg.ip_address else '0.0.0.0'
    port = server_cfg.port
    threads = server_cfg.threads

    logger.info(f'==STARTUP== Starting Alpaca API server on {host}:{port} with {threads} worker threads')
    logger.info(f'==STARTUP== GUI available at http://localhost:{gui_port}. Time stamps are UTC.')

    # Open browser to setup page
    def open_browser():
        time.sleep(1)  # Wait for server startup
        if _gui_thread:
            webbrowser.open(f'http://localhost:{gui_port}')
        else:
            # Fallback to original setup page
            webbrowser.open(f'http://localhost:{port}/')

    threading.Thread(target=open_browser, daemon=True).start()

    # Serve using waitress with configurable thread pool
    # waitress handles concurrent requests properly unlike wsgiref
    waitress_serve(falc_app, host=host, port=port, threads=threads)

# ========================
if __name__ == '__main__':
    main()
# ========================
