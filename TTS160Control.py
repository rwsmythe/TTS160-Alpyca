# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# TTS160Control.py - Main controller module
#
# Orchestrates the TTS160 ALPACA driver and GUI interface
#
# -----------------------------------------------------------------------------

import sys
import argparse
import signal
import time
from PySide6.QtWidgets import QApplication
from tts160_window import TTS160Window
from controllers.driver_controller import DriverController
from controllers.telescope_controller import TelescopeController
import TTS160Global

class TTS160Control:
    """Main controller class for TTS160 system"""
    
    def __init__(self):
        self.qt_app = None
        self.gui_window = None
        self.running = False
        
        # Initialize feature controllers
        self.driver = DriverController(self)
        self.telescope = TelescopeController(self)
        self.TTS160_dev = None
               
    def get_config(self):
        """Get the TTS160 config instance"""
        return TTS160Global.get_config()
    
    def start(self):
        """Start the driver - called by GUI or nogui mode"""
        self.driver.start()
        import log
        self.TTS160_dev = TTS160Global.get_device(log.logger)
                
    def stop(self):
        """Stop the driver - called by GUI or nogui mode"""
        self.driver.stop()
        self.TTS160_dev = TTS160Global.reset_device()
        self.TTS160_dev = None # This should initiate GC process for the global object
        
    def start_gui(self):
        """Start the GUI in the main thread"""
        # Create and show the GUI window
        self.gui_window = TTS160Window(self)
        self.gui_window.show()
        
        # Run the Qt event loop (blocking)
        return self.qt_app.exec()
        
    def shutdown(self):
        """Clean shutdown of both components"""
        self.running = False
        
        # Stop driver if running
        self.driver.stop()
        self.TTS160_dev = TTS160Global.reset_device()
        self.TTS160_dev = None # This should initiate GC process for the global object
        
        if self.qt_app:
            self.qt_app.quit()
            self.qt_app = None
            
    def signal_handler(self, signum, frame):
        """Handle shutdown signals in nogui mode"""
        print(f"\nReceived signal {signum}. Shutting down...")
        self.shutdown()
            
    def run_nogui(self):
        """Run in headless mode without GUI"""
        try:
            print("Starting TTS160 Control System (No GUI mode)...")
            
            # Set up signal handlers for clean shutdown
            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)
            
            # Start the driver immediately
            print("Starting driver...")
            self.start()
            self.running = True
            
            print("Driver started. Press Ctrl+C to stop.")
            
            # Keep running until shutdown
            while self.running:
                time.sleep(1)
                
            print("Driver stopped.")
            return 0
            
        except KeyboardInterrupt:
            print("\nShutdown requested...")
            return 0
        except Exception as e:
            print(f"System error: {e}")
            return 1
        finally:
            self.shutdown()
        
    def run(self):
        """Main execution method with GUI"""
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
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='TTS160 Telescope Control System')
    parser.add_argument('-nogui', action='store_true', 
                       help='Run without GUI (headless mode)')
    
    args = parser.parse_args()
    
    controller = TTS160Control()
    
    if args.nogui:
        sys.exit(controller.run_nogui())
    else:
        sys.exit(controller.run())

if __name__ == '__main__':
    main()