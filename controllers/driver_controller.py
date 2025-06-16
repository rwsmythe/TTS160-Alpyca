"""Driver controller for TTS160 ALPACA driver management."""

import threading
import time
import app as driver_app


class DriverController:
    """Handles ALPACA driver start/stop operations."""
    
    def __init__(self, main_control):
        """Initialize with reference to main control.
        
        Args:
            main_control: Reference to TTS160Control instance
        """
        self.main_control = main_control
        self.driver_thread = None
        self.driver_running = False
        self.status_callback = None
        
    def set_status_callback(self, callback):
        """Set callback for status updates."""
        self.status_callback = callback
        
    def start(self):
        """Start the ALPACA driver if not already running."""
        if not self.driver_running:
            print("Starting ALPACA driver...")
            self._start_driver_thread()
    
    def stop(self):
        """Stop the ALPACA driver if running."""
        if self.driver_running:
            print("Stopping ALPACA driver...")
            driver_app.shutdown_server()
            if self.driver_thread:
                self.driver_thread.join(timeout=5)
            self.driver_running = False
            if self.status_callback:
                self.status_callback("stopped")
    
    def _start_driver_thread(self):
        """Start driver in background thread."""
        def driver_worker():
            try:
                self.driver_running = True
                if self.status_callback:
                    self.status_callback("running")
                driver_app.main()
            except Exception as e:
                print(f"Driver error: {e}")
            finally:
                self.driver_running = False
                if self.status_callback:
                    self.status_callback("stopped")
                
        self.driver_thread = threading.Thread(target=driver_worker, daemon=True)
        self.driver_thread.start()
        time.sleep(2)  # Allow startup time
    
    @property
    def is_running(self):
        """Check if driver is currently running."""
        return self.driver_running