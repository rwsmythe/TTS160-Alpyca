"""TTS160 GUI Window Controller."""

from PySide6.QtWidgets import QMainWindow, QApplication
from PySide6.QtCore import QTimer
import sys

from ui_tts160gui import Ui_MainWindow


class TTS160Window(QMainWindow):
    """Main window controller for TTS160 GUI."""
    
    def __init__(self, tts160_control):
        """Initialize the window with TTS160Control instance."""
        super().__init__()
        
        # Setup UI from designer
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        # Store control instance
        self.tts160_control = tts160_control
        
        # Set up driver status callback
        self.tts160_control.driver.set_status_callback(self.on_driver_status_changed)
        
        # Initial UI state
        self.ui.pushStop.setEnabled(False)
        self.ui.labelStatus.setText("Driver Stopped")
        
        # Connect signals
        self.ui.pushStart.clicked.connect(self.on_start_clicked)
        self.ui.pushStop.clicked.connect(self.on_stop_clicked)
    
    def on_start_clicked(self):
        """Handle start button click."""
        try:
            # Immediate UI feedback
            self.ui.labelStatus.setText("Starting Driver")
            self.ui.pushStart.setEnabled(False)
            QApplication.processEvents()  # Force GUI update
            
            # Start driver (will callback when running)
            self.tts160_control.start()
        except Exception as ex:
            self.ui.labelStatus.setText(f"Start failed: {ex}")
            self.ui.pushStart.setEnabled(True)
    
    def on_stop_clicked(self):
        """Handle stop button click."""
        try:
            # Immediate UI feedback
            self.ui.labelStatus.setText("Stopping Driver")
            self.ui.pushStop.setEnabled(False)
            QApplication.processEvents()  # Force GUI update
            
            # Stop driver (will callback when stopped)
            self.tts160_control.stop()
        except Exception as ex:
            self.ui.labelStatus.setText(f"Stop failed: {ex}")
            self.ui.pushStop.setEnabled(True)
    
    def on_driver_status_changed(self, status):
        """Handle driver status updates."""
        if status == "running":
            self.ui.labelStatus.setText("Driver Running")
            self.ui.pushStart.setEnabled(False)
            self.ui.pushStop.setEnabled(True)
        elif status == "stopped":
            self.ui.labelStatus.setText("Driver Stopped")
            self.ui.pushStart.setEnabled(True)
            self.ui.pushStop.setEnabled(False)


def main():
    """Test with mock control."""
    app = QApplication(sys.argv)
    
    class MockControl:
        def __init__(self):
            self.driver = MockDriver()
        def start(self): self.driver.start()
        def stop(self): self.driver.stop()
    
    class MockDriver:
        def __init__(self):
            self.status_callback = None
        def set_status_callback(self, callback): 
            self.status_callback = callback
        def start(self): 
            print("Driver started")
            if self.status_callback: self.status_callback("running")
        def stop(self): 
            print("Driver stopped")
            if self.status_callback: self.status_callback("stopped")
    
    window = TTS160Window(MockControl())
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()