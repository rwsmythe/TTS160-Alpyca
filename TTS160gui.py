from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt

class TTS160GUI(QWidget):
    def __init__(self, start_callback=None, stop_callback=None):
        super().__init__()
        self.start_callback = start_callback
        self.stop_callback = stop_callback
        self.init_ui()
        self.connect_signals()
        
    def init_ui(self):
        self.setWindowTitle("TTS160 Controller")
        self.setMinimumSize(300, 150)
        
        layout = QVBoxLayout()
        
        # Status label
        self.status_label = QLabel("Driver Stopped")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.status_label)
        
        # Start button
        self.start_button = QPushButton("Start Driver")
        self.start_button.setEnabled(True)
        layout.addWidget(self.start_button)
        
        # Stop button
        self.stop_button = QPushButton("Stop Driver")
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)
        
        self.setLayout(layout)
        
    def connect_signals(self):
        """Connect button signals to handler methods"""
        self.start_button.clicked.connect(self.on_start_clicked)
        self.stop_button.clicked.connect(self.on_stop_clicked)
        
    def on_start_clicked(self):
        """Handle start button click"""
        if self.start_callback:
            self.start_callback()
            
    def on_stop_clicked(self):
        """Handle stop button click"""
        if self.stop_callback:
            self.stop_callback()
        
    def set_driver_running(self, running):
        """Update GUI state based on driver status"""
        if running:
            self.status_label.setText("Driver Running")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
        else:
            self.status_label.setText("Driver Stopped")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

def create_window(start_callback=None, stop_callback=None):
    window = TTS160GUI(start_callback, stop_callback)
    window.show()
    return window