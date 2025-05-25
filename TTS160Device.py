import threading
import time
import uuid
from typing import Set, Optional, List
from datetime import datetime, timezone
from logging import Logger
from contextlib import contextmanager

import serial
from config import Config
import telescope


class Rate:
    """Represents a rate range for telescope movement."""
    
    def __init__(self, minimum: float, maximum: float) -> None:
        self.Minimum = float(minimum)
        self.Maximum = float(maximum)


class TTS160Device:
    """TTS160 Hardware Class
    
    Hardware implementation of TTS160 Alpaca driver.
    Handles translation between hardware and Alpaca driver calls.
    """

    def __init__(self, logger: Logger) -> None:
        self._lock = threading.Lock()
        self._logger = logger
        self._connecting = False
        self._connected_instances: Set[str] = set()
        
        # Initialize serial connection
        self._serial = self._create_serial_connection()
        
        # Hardware state
        self._dev_firmware = False
        self.alignment_mode = telescope.AlignmentModes.algAltAz

        #Initialize ASCOM 'Can' variables
        self.CanFindHome = False
        self.CanPark = True
        self.CanPulseGuide = True
        self.CanSetDeclinationRate = False
        self.CanSetGuideRates = True
        self.CanSetPark = False
        self.CanSetPierSide = False
        self.CanSetRightAscensionRate = False
        self.CanSetTracking = True
        self.CanSlew = True
        self.CanSlewAltAz = True
        self.CanSlewAltAzAsync = True
        self.CanSlewAsync = True
        self.CanSync = True
        self.CanSyncAltAz = True
        self.CanUnpark = False

        #Initialize other variables
        self.AlignmentMode = telescope.AlignmentModes.algAltAz
        self.Altitude = 0.
        self.ApertureArea = 0.
        self.ApertureDiameter = 0.
        self.AtHome = False
        self.AtPark = False
        self.Azimuth = 0.
        self.Connected = False
        self.Connecting = False
        self.Declination = 0.
        self.DeclinationRate = 0.
        self.Description = telescope.TelescopeMetadata.Description
        #self.DeviceState = []  #This list is developed within telescope.py, no need to maintain a persistant state
        self.DoesRefraction = False
        self.DriverInfo = "Alpaca Driver for TTS160.  Driver created by Reid Smythe.\nSource may be used and modified with attribution."
        self.DriverVersion = "356.1"
        self.EquatorialSystem = telescope.EquatorialCoordinateType.equTopocentric
        self.FocalLength = 0.
        self.GuideRateDeclination = 1.      #Verify default value
        self.GuideRateRightAscension = 1.   #Verify default value
        self.InterfaceVersion = 4
        self.IsPulseGuiding = False
        self.Name = telescope.TelescopeMetadata.Name
        self.RightAscension = 0.
        self.RightAscensionRate = 0.
        self.SideOfPier = telescope.PierSide.pierEast
        self.SiderialTime = 0.
        self.SiteElevation = Config.SiteElevation
        self.SiteLatitude = Config.SiteLatitude
        self.SiteLongitude = Config.SiteLongitude
        self.SlewSettleTime = Config.SlewSettleTime
        self.Slewing = False
        self.SupportedActions = ["FieldRotationAngle"]
        self.TargetDeclination = 0.
        self.TargetRightAscension = 0.
        self.Tracking = False
        self.TrackingRate = telescope.DriveRates.driveSidereal
        self.TrackingRates = [telescope.DriveRates.driveSidereal, telescope.DriveRates.driveLunar, telescope.DriveRates.driveSolar]
        self.UTCDate = datetime.now(timezone.utc)

    def _create_serial_connection(self) -> serial.Serial:
        """Create and configure serial connection."""
        ser = serial.Serial()
        ser.baudrate = 9600
        ser.bytesize = serial.EIGHTBITS
        ser.parity = serial.PARITY_NONE
        ser.stopbits = serial.STOPBITS_ONE
        ser.port = Config.dev_port
        ser.timeout = 2
        return ser

    def connect(self, unique_id: Optional[str] = None) -> None:
        """Asynchronously connect to the device."""
        if unique_id is None:
            unique_id = str(uuid.uuid4())
            
        self._logger.info(f"Connect called with ID: {unique_id}")
        
        with self._lock:
            if unique_id in self._connected_instances:
                self._logger.info("Already connected, ignoring request")
                return
                
            self._connecting = True
        
        # Start background connection task
        def connect_task():
            try:
                self._set_connected(unique_id, True)
            except Exception as ex:
                self._logger.error(f"Connect task failed: {ex}")
                raise
            finally:
                with self._lock:
                    self._connecting = False
                    
        thread = threading.Thread(target=connect_task, daemon=True)
        thread.start()

    def disconnect(self, unique_id: Optional[str] = None) -> None:
        """Asynchronously disconnect from the device."""
        if unique_id is None:
            # For backward compatibility, disconnect all if no ID provided
            unique_id = next(iter(self._connected_instances), None)
            if unique_id is None:
                self._logger.info("No connections to disconnect")
                return
            
        self._logger.info(f"Disconnect called with ID: {unique_id}")
        
        with self._lock:
            if unique_id not in self._connected_instances:
                self._logger.info("Already disconnected, ignoring request")
                return
                
            self._connecting = True
        
        def disconnect_task():
            try:
                self._set_connected(unique_id, False)
            except Exception as ex:
                self._logger.error(f"Disconnect task failed: {ex}")
                raise
            finally:
                with self._lock:
                    self._connecting = False
                    
        thread = threading.Thread(target=disconnect_task, daemon=True)
        thread.start()

    def _set_connected(self, unique_id: str, new_state: bool) -> None:
        """Synchronously connect/disconnect implementation."""
        with self._lock:
            if new_state:  # Connecting
                if unique_id in self._connected_instances:
                    return
                    
                # First connection - initialize hardware
                if not self._connected_instances:
                    self._initialize_hardware()
                    
                self._connected_instances.add(unique_id)
                self._logger.info(f"Connected instance {unique_id}")
                
            else:  # Disconnecting
                if unique_id not in self._connected_instances:
                    return
                    
                self._connected_instances.discard(unique_id)
                self._logger.info(f"Disconnected instance {unique_id}")
                
                # Last connection - disconnect hardware
                if not self._connected_instances:
                    self._disconnect_hardware()

    def _initialize_hardware(self) -> None:
        """Initialize hardware connection and setup."""
        try:
            self._logger.info(f"Connecting to {self._serial.port}")
            self._serial.open()
            
            # Get mount information
            mount_name = self._send_command(":GVP#", expect_response=True).rstrip('#')
            firmware = self._send_command(":GVN#", expect_response=True).rstrip('#')
            
            self._logger.info(f"Connected to {mount_name}")
            self._logger.info(f"Firmware: {firmware}")
            
            # Check for advanced firmware
            self._check_firmware_version(firmware)
                
        except Exception as ex:
            self._logger.error(f"Hardware initialization failed: {ex}")
            self._cleanup_connection()
            raise

    def _check_firmware_version(self, firmware: str) -> None:
        """Check firmware version and set capabilities."""
        try:
            fw_num = int(firmware[:3])
            self._dev_firmware = fw_num >= 355
            status = "Advanced" if self._dev_firmware else "Standard"
            self._logger.info(f"{status} firmware detected (version {fw_num})")
        except (ValueError, IndexError):
            self._dev_firmware = False
            self._logger.warning(f"Could not parse firmware version: {firmware}")

    def _disconnect_hardware(self) -> None:
        """Disconnect from hardware."""
        self._cleanup_connection()
        self._logger.info("Hardware disconnected")

    def _cleanup_connection(self) -> None:
        """Clean up serial connection."""
        try:
            if self._serial.is_open:
                self._serial.close()
        except Exception as ex:
            self._logger.warning(f"Error closing serial connection: {ex}")

    def _send_command(self, command: str, expect_response: bool = True, 
                     timeout: Optional[float] = None) -> str:
        """Send command to mount and optionally wait for response."""
        if not self._serial.is_open:
            raise ConnectionError("Serial port not open")
            
        try:
            self._serial.write(command.encode('ascii'))
            
            if expect_response:
                old_timeout = self._serial.timeout
                if timeout is not None:
                    self._serial.timeout = timeout
                    
                try:
                    response = self._serial.read_until(b'#').decode('ascii')
                    return response
                finally:
                    self._serial.timeout = old_timeout
                    
            return ""
            
        except (serial.SerialException, UnicodeDecodeError) as ex:
            self._logger.error(f"Command '{command}' failed: {ex}")
            raise

    @property
    def is_connected(self) -> bool:
        """Check if device is connected."""
        with self._lock:
            return self._serial.is_open and bool(self._connected_instances)

    @property
    def is_connecting(self) -> bool:
        """Check if device is in process of connecting/disconnecting."""
        with self._lock:
            return self._connecting

    def axis_rates(self, axis: int) -> List[Rate]:
        """Get available rates for the specified axis."""
        if axis in [0, 1]:  # Primary and secondary axes
            return [Rate(0.0, 3.0)]
        elif axis == 2:  # Tertiary axis not available
            return []
        else:
            raise ValueError(f"Invalid axis: {axis}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self._cleanup_connection()