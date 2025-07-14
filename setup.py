# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# setup.py - Device setup endpoints.
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

import os
import threading
import time
from falcon import Request, Response
from shr import log_request
import app
import log
import webbrowser
import TTS160Global

server_cfg = None

class ShutdownHandler:
    """Handler for graceful server shutdown"""
    
    def on_post(self, req: Request, resp: Response):
        """Initiate server shutdown sequence"""
        
        def delayed_shutdown():
            """Perform shutdown after response is sent"""
            time.sleep(1)

            # Stop discovery service
            if app._DSC:
                app._DSC.shutdown()

            # Close log handlers
            if hasattr(log, 'logger') and log.logger:
                handlers = log.logger.handlers[:]
                for handler in handlers:
                    handler.close()
                    log.logger.removeHandler(handler)

            # Exit application
            os._exit(0)

        # Start shutdown in background thread
        threading.Thread(target=delayed_shutdown, daemon=True).start()

        # Return shutdown confirmation
        resp.text = """
        <script>
        document.body.innerHTML = `
        <div style="text-align: center; padding: 40px; font-family: Arial, sans-serif;">
            <h2 style="color: #dc3545;">Server Shutdown Complete</h2>
            <p>The Alpaca telescope driver has been stopped successfully.</p>
            <p><strong>You may now safely close this browser tab.</strong></p>
        </div>
        `;
        </script>
        """


class devsetup:
    """Legacy device setup endpoint - redirects to web interface"""
    
    def __init__(self):
        self.server_cfg = TTS160Global.get_serverconfig()

    def on_get(self, req: Request, resp: Response, devnum: str):      
        # Open browser to setup page
        def open_browser():
            webbrowser.open(f'http://localhost:{self.server_cfg.setup_port}')

        threading.Thread(target=open_browser, daemon=True).start()