# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# TTS160Control.py - Main controller module
#
# Orchestrates the TTS160 ALPACA driver and GUI interface
#
# -----------------------------------------------------------------------------

import sys
from PySide6.QtWidgets import QApplication
from tts160_window import TTS160Window
from controllers.driver_controller import DriverController

class TTS160Control:
    """Main controller class for TTS160 system"""
    
    def __init__(self):
        self.qt_app = None
        self.gui_window = None
        
        # Initialize feature controllers
        self.driver = DriverController(self)
        
    def start(self):
        """Start the driver - called by GUI"""
        self.driver.start()
                
    def stop(self):
        """Stop the driver - called by GUI"""
        self.driver.stop()
        
    def start_gui(self):
        """Start the GUI in the main thread"""
        # Create and show the GUI window
        self.gui_window = TTS160Window(self)
        self.gui_window.show()
        
        # Run the Qt event loop (blocking)
        return self.qt_app.exec()
        
    def shutdown(self):
        """Clean shutdown of both components"""
        # Stop driver if running
        self.driver.stop()
        
        if self.qt_app:
            self.qt_app.quit()
            self.qt_app = None
            
    def run(self):
        """Main execution method"""
        try:
            print("Starting TTS160 Control System...")
            
            # Create QApplication first (or get existing one)
            if not QApplication.instance():
                self.qt_app = QApplication(sys.argv)
            else:
                self.qt_app = QApplication.instance()
            
            print("Starting GUI...")
            
            # Start GUI (blocking call) - driver will start via button click
            self.start_gui()
            
            print("GUI closed. Shutting down...")
            return 0
            
        except KeyboardInterrupt:
            print("\nShutdown requested...")
            return 0
        except Exception as e:
            print(f"System error: {e}")
            return 1
        finally:
            self.shutdown()

def main():
    """Entry point"""
    controller = TTS160Control()
    sys.exit(controller.run())

if __name__ == '__main__':
    main()