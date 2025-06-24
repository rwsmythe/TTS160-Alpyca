"""TTS160 GUI Window Controller."""

from PySide6.QtWidgets import QMainWindow, QApplication
from PySide6.QtCore import QTimer
import sys
from config import Config
import serial.tools.list_ports
from ui_tts160gui import Ui_MainWindow
from tts160_types import CommandType


class TTS160Window(QMainWindow):
    """Main window controller for TTS160 GUI."""
    
    def __init__(self, main_control):
        """Initialize the window with TTS160Control instance."""
        super().__init__()
        
        # Setup UI from designer
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        # Store control instance
        self.main_control = main_control
        
        # Set up driver status callback
        self.main_control.driver.set_status_callback(self.on_driver_status_changed)
        
        # Initial UI state
        self.ui.pushStop.setEnabled(False)
        self.ui.labelStatus.setText("Driver Stopped")

        # Read configuration
        self.ui.plainTextEditPort.setPlainText(f"{Config.port}")

        self.ui.plainTextEditCustomIP.setPlainText(f"{Config.ip_address}")
        if Config.ip_address == '':
            self.ui.checkBoxCustomIP.setChecked(False)
            self.ui.plainTextEditCustomIP.setEnabled(False)
        else:
            self.ui.checkBoxCustomIP.setChecked(True)
            self.ui.plainTextEditCustomIP.setEnabled(True)

        # Connect signals
        self.ui.pushStart.clicked.connect(self.on_start_clicked)
        self.ui.pushStop.clicked.connect(self.on_stop_clicked)
        self.ui.pushButtonConnect.clicked.connect(self.on_connect_clicked)
        self.ui.pushButtonDisconnect.clicked.connect(self.on_disconnect_clicked)
        self.ui.pushButtonSaveConfig.clicked.connect(self.on_save_config_clicked)
        self.ui.pushButtonReloadConfig.clicked.connect(self.on_reload_config_clicked)

        #establish auto-refresh
        self.timer = QTimer()
        self.timer.timeout.connect(self.state_refresh)
        self.timer.start(500)

        # Items to disable/enable for config protection
        self.config_items = []
        self.config_items = ["checkBoxSyncTime", "checkBoxPulseGuideEq",
                        "checkBoxPulseGuideAltComp", "plainTextEditSiteLat",
                        "plainTextEditSiteLong", "plainTextEditSiteAltitude",
                        "plainTextEditSiteAltitude", "plainTextEditSlewSettleTime",
                        "plainTextEditPulseGuideMaxComp", "plainTextEditPulseGuideCompBuffer",
                        "comboBoxComPort", "pushButtonSaveConfig"]

    def populate_com_ports(self):
        self.ui.comboBoxComPort.clear()
        self.port_data = {}  # Store device->description mapping
        
        # Get saved port from config
        saved_port = self.telescope_config['dev_port']
        
        ports = serial.tools.list_ports.comports()
        selected_index = 0
        
        for i, port in enumerate(ports):
            display_text = f"{port.device} - {port.description}"
            self.ui.comboBoxComPort.addItem(display_text)
            self.port_data[display_text] = port.device
            
            # Auto-select saved port
            if port.device == saved_port:
                selected_index = i
    
        if ports:
            self.ui.comboBoxComPort.setCurrentIndex(selected_index)
        else:
            self.ui.comboBoxComPort.addItem("No COM ports found")

    def load_telescope_config(self):

        self.telescope_config = self.main_control.telescope.load_config()
        
        if self.telescope_config:

            self.ui.checkBoxSyncTime.setChecked(self.telescope_config['sync_time_on_connect'])
            self.ui.checkBoxPulseGuideEq.setChecked(self.telescope_config['pulse_guide_equatorial_frame'])
            self.ui.checkBoxPulseGuideAltComp.setChecked(self.telescope_config['pulse_guide_altitude_compensation'])
            self.ui.plainTextEditSiteLat.setPlainText(f"{self.telescope_config['site_latitude']:.10f}")
            self.ui.plainTextEditSiteLong.setPlainText(f"{self.telescope_config['site_longitude']:.10f}")
            self.ui.plainTextEditSiteAltitude.setPlainText(f"{self.telescope_config['site_elevation']:.10f}")
            self.ui.plainTextEditSlewSettleTime.setPlainText(f"{self.telescope_config['slew_settle_time']}")
            self.ui.plainTextEditPulseGuideMaxComp.setPlainText(f"{self.telescope_config['pulse_guide_max_compensation']}")
            self.ui.plainTextEditPulseGuideCompBuffer.setPlainText(f"{self.telescope_config['pulse_guide_compensation_buffer']}")

    def on_reload_config_clicked(self):

        self.load_telescope_config()
        self.populate_com_ports()

    def on_save_config_clicked(self):

        self.telescope_config = {}
        self.telescope_config['slew_settle_time'] = int(self.ui.plainTextEditSlewSettleTime.toPlainText())
        self.telescope_config['sync_time_on_connect'] = self.ui.checkBoxSyncTime.isChecked()
        self.telescope_config['pulse_guide_equatorial_frame'] = self.ui.checkBoxPulseGuideEq.isChecked()
        self.telescope_config['pulse_guide_altitude_compensation'] = self.ui.checkBoxPulseGuideAltComp.isChecked()
        self.telescope_config['pulse_guide_max_compensation'] = int(self.ui.plainTextEditPulseGuideMaxComp.toPlainText())
        self.telescope_config['pulse_guide_compensation_buffer'] = int(self.ui.plainTextEditPulseGuideCompBuffer.toPlainText())
        self.telescope_config['site_elevation'] = float(self.ui.plainTextEditSiteAltitude.toPlainText())
        self.telescope_config['dev_port'] = self.get_selected_port()

        self.main_control.telescope.save_config( self.telescope_config )

    def state_refresh(self):
        count  = self.main_control.telescope.get_connection_count()
        self.ui.labelConnectionCount.setText(f"{count}")
        if self.main_control.driver.driver_running:
            if count == 0:
                self.ui.pushButtonConnect.setEnabled(True)
                self.ui.pushButtonDisconnect.setEnabled(False)
                enabled = True
            else:
                self.ui.pushButtonConnect.setEnabled(False)
                self.ui.pushButtonDisconnect.setEnabled(True)
                enabled = False
                #data = self.main_control.TTS160_dev._serial_manager.send_command(':*!G T17,18,1,2,30,M1#', CommandType.AUTO)
                #self.ui.labelRA.setText(f"{data[0]}")
                #self.ui.labelDec.setText(f"{data[1]}")
                #self.ui.labelH.setText(f"{data[2]}")
                #self.ui.labelH_2.setText(f"{data[3]}")
                #data = self.main_control.TTS160_dev._serial_manager.send_command(':*!0#', CommandType.AUTO)
                #self.ui.labelRA.setText(f"{data['h_ticks']}")
                #self.ui.labelDec.setText(f"{data['e_ticks']}")
                #self.ui.labelH.setText(f"{data['alt']}")
                #self.ui.labelH_2.setText(f"{data['az']}")
        else:
            self.ui.pushButtonConnect.setEnabled(False)
            self.ui.pushButtonDisconnect.setEnabled(False)
            enabled = True

        for item in self.config_items:
            widget = getattr(self.ui, item)
            widget.setEnabled(enabled)

    def on_start_clicked(self):
        """Handle start button click."""
        try:
            # Immediate UI feedback
            self.ui.labelStatus.setText("Starting Driver")
            self.ui.pushStart.setEnabled(False)
            QApplication.processEvents()  # Force GUI update
            
            # Start driver (will callback when running)
            self.main_control.start()
            # Populate serial communication ports and select previous port
            self.load_telescope_config()
            self.populate_com_ports()

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
            self.main_control.stop()
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

    def on_connect_clicked(self):
        buff = self.main_control.telescope.get_connection_count()
        
        if  buff == 0:
            self.main_control.telescope.connect()
            self.ui.pushButtonConnect.setEnabled(False)

    def on_disconnect_clicked(self):
        if self.main_control.telescope.get_connection_count():
            self.main_control.telescope.disconnect()
            self.ui.pushButtonDisconnect.setEnabled(False)

    def get_selected_port(self):
        """Returns just the port.device string for saving"""
        current_text = self.ui.comboBoxComPort.currentText()
        return self.port_data.get(current_text, current_text)

    #def save_selected_port(self):
    #    port_device = self.get_selected_port_device()
    #    self.main_control.get_config().serial_port = port_device
    #    self.main_control.get_config().save()

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