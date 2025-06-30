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


class StaticFileHandler:
    """Handler for serving static files (CSS, JS, images, etc.)"""
    
    def on_get(self, req: Request, resp: Response, path):
        """Serve static files with security checks"""
        # Prevent path traversal
        if '..' in path or path.startswith('/'):
            resp.status = '403 Forbidden'
            return

        file_path = os.path.join('static', path)
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                resp.data = f.read()
            
            # Set MIME types
            if path.endswith('.js'):
                resp.content_type = 'application/javascript'
            elif path.endswith('.css'):
                resp.content_type = 'text/css'
            elif path.endswith('.png'):
                resp.content_type = 'image/png'
            elif path.endswith('.jpg') or path.endswith('.jpeg'):
                resp.content_type = 'image/jpeg'
            elif path.endswith('.gif'):
                resp.content_type = 'image/gif'
            elif path.endswith('.svg'):
                resp.content_type = 'image/svg+xml'
        else:
            resp.status = '404 Not Found'


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
    
    def on_get(self, req: Request, resp: Response, devnum: str):
        """Redirect to new web interface"""
        resp.content_type = 'text/html'
        log_request(req)
        resp.text = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Device Setup</title>
            <meta http-equiv="refresh" content="0; url=/">
        </head>
        <body>
            <h2>Redirecting to new web interface...</h2>
            <p><a href="/">Click here if not redirected automatically</a></p>
        </body>
        </html>
        '''