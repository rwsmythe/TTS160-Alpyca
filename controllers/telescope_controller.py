"""Telescope controller for TTS160 ALPACA driver management."""

import threading
import time
import app as driver_app


class TelescopeController:
    """Handles ALPACA telescope <-> gui interface functions."""
    
    def __init__(self, main_control):
        """Initialize with reference to main control.
        
        Args:
            main_control: Reference to TTS160Control instance
        """
        self.main_control = main_control
    def connect(self):
        if self.main_control.TTS160_dev:
            self.main_control.TTS160_dev.Connect()

    def disconnect(self):
        if self.main_control.TTS160_dev:
            self.main_control.TTS160_dev.Disconnect()
    
    def get_connection_count(self) -> int:
        if self.main_control.driver.driver_running and self.main_control.TTS160_dev:
            return self.main_control.TTS160_dev._serial_manager.connection_count
        else:
            return 0
        
    def save_config( self, telescope_config ):
        if self.main_control.TTS160_dev:
            for key, value in telescope_config.items():
                setattr(self.main_control.TTS160_dev._config, key, value)
            self.main_control.TTS160_dev._config.save()
    
    def load_config( self ) -> dict:

        telescope_config = {}

        telescope_config['slew_settle_time'] = ''
        telescope_config['sync_time_on_connect'] = ''
        telescope_config['pulse_guide_equatorial_frame'] = ''
        telescope_config['pulse_guide_altitude_compensation'] = ''
        telescope_config['pulse_guide_max_compensation'] = ''
        telescope_config['pulse_guide_compensation_buffer'] = ''
        telescope_config['site_elevation'] = ''
        telescope_config['dev_port'] = ''
        telescope_config['site_latitude'] = ''
        telescope_config['site_longitude'] = ''

        if self.main_control.TTS160_dev:
            self.main_control.TTS160_dev._config.reload()
            for key in telescope_config:
                telescope_config[key] = getattr(self.main_control.TTS160_dev._config, key)

        return telescope_config

    
    """
    def set_status_callback(self, callback):
        
        self.status_callback = callback
        
    def start(self):
        
        if not self.driver_running:
            print("Starting ALPACA driver...")
            self._start_driver_thread()
    
    def stop(self):
        
        if self.driver_running:
            print("Stopping ALPACA driver...")
            driver_app.shutdown_server()
            if self.driver_thread:
                self.driver_thread.join(timeout=5)
            self.driver_running = False
            if self.status_callback:
                self.status_callback("stopped")
    
    def _start_driver_thread(self):
        
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
        
        return self.driver_running
    """