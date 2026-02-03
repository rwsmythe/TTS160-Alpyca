"""
GPS Manager Module for TTS160 Alpaca Driver.

Provides GPS support via USB GPS dongle, parsing NMEA sentences and
pushing location updates to the TTS-160 mount firmware using the
SET_LOCATION (0x11) binary command.

Uses pynmea2 library for NMEA parsing.
"""

import logging
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional, Callable, List, Tuple, Any

import serial
import serial.tools.list_ports
import pynmea2


# =============================================================================
# Type Definitions
# =============================================================================

class GPSFixQuality(IntEnum):
    """NMEA GGA fix quality indicators."""
    INVALID = 0
    GPS_FIX = 1
    DGPS_FIX = 2
    PPS_FIX = 3
    RTK_FIXED = 4
    RTK_FLOAT = 5
    ESTIMATED = 6
    MANUAL = 7
    SIMULATION = 8


class GPSState(IntEnum):
    """GPS manager operational states."""
    DISABLED = 0
    DISCONNECTED = 1
    CONNECTING = 2
    CONNECTED = 3
    ACQUIRING_FIX = 4
    FIX_VALID = 5
    ERROR = 6


@dataclass
class GPSPosition:
    """GPS position data from NMEA sentences."""
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0
    fix_quality: GPSFixQuality = GPSFixQuality.INVALID
    satellites: int = 0
    hdop: float = 99.9
    timestamp: Optional[datetime] = None
    valid: bool = False


@dataclass
class GPSDateTime:
    """GPS date/time data from NMEA sentences."""
    utc_datetime: Optional[datetime] = None
    valid: bool = False


@dataclass
class GPSStatus:
    """Complete GPS status for UI display."""
    state: GPSState = GPSState.DISABLED
    position: GPSPosition = field(default_factory=GPSPosition)
    datetime_info: GPSDateTime = field(default_factory=GPSDateTime)
    last_update: Optional[datetime] = None
    last_push_to_mount: Optional[datetime] = None
    push_count: int = 0
    error_message: str = ""
    port: str = ""
    connected: bool = False


# =============================================================================
# GPS Manager Class
# =============================================================================

class GPSManager:
    """Thread-safe GPS manager with background reading and mount updates.

    Manages GPS serial connection, parses NMEA sentences, and pushes
    location updates to the TTS-160 mount using the SET_LOCATION command.

    Thread Safety:
        All public methods are thread-safe via RLock protection.
        Background thread handles GPS reading at ~1Hz.

    Lifecycle:
        1. Create instance with config and logger
        2. Call start() to begin GPS operations
        3. Call stop() to cleanly shutdown

    Attributes:
        config: TTS160Config instance with GPS settings
        logger: Logger instance for this module
    """

    # Constants
    NMEA_SENTENCE_TIMEOUT = 5.0
    BACKGROUND_READ_RATE = 1.0
    RECONNECT_DELAY_BASE = 5.0
    RECONNECT_DELAY_MAX = 60.0

    def __init__(self, config, logger: logging.Logger):
        """Initialize GPS manager.

        Args:
            config: TTS160Config instance with GPS settings
            logger: Logger instance
        """
        self._config = config
        self._logger = logger
        self._lock = threading.RLock()

        # Serial connection
        self._serial: Optional[serial.Serial] = None
        self._detected_port: str = ""  # Actual port to use (may be autodetected)

        # State tracking
        self._state = GPSState.DISABLED
        self._position = GPSPosition()
        self._datetime_info = GPSDateTime()
        self._last_valid_sentence = 0.0
        self._last_push_time = 0.0
        self._push_count = 0
        self._error_message = ""
        self._reconnect_delay = self.RECONNECT_DELAY_BASE

        # Background thread
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Mount communication callback
        self._push_location_callback: Optional[Callable[[float, float, float, str], bool]] = None

        self._logger.debug("GPSManager initialized")

    # -------------------------------------------------------------------------
    # Public Interface
    # -------------------------------------------------------------------------

    def start(self) -> bool:
        """Start GPS operations.

        Opens serial connection and starts background reading thread.

        Returns:
            True if started successfully, False otherwise
        """
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._logger.warning("GPS already running")
                return True

            if not self._config.gps_enabled:
                self._logger.info("GPS disabled in configuration")
                self._update_state(GPSState.DISABLED)
                return False

            # Handle port configuration
            port = self._config.gps_port
            if not port:
                self._logger.warning("GPS port not configured")
                self._error_message = "GPS port not configured"
                self._update_state(GPSState.ERROR)
                return False

            # Autodetect GPS port if configured
            if port.lower() == 'auto':
                self._logger.info("Autodetecting GPS port...")
                self._update_state(GPSState.CONNECTING)
                detected_port = self._autodetect_port()
                if detected_port:
                    self._detected_port = detected_port
                    self._logger.info(f"GPS autodetected on {detected_port}")
                else:
                    self._logger.warning("GPS autodetect failed - no GPS device found")
                    self._error_message = "No GPS device found"
                    self._update_state(GPSState.ERROR)
                    return False
            else:
                self._detected_port = port

            self._stop_event.clear()
            self._reconnect_delay = self.RECONNECT_DELAY_BASE
            self._thread = threading.Thread(
                target=self._background_reader,
                name='GPSReader',
                daemon=True
            )
            self._thread.start()
            self._logger.info(f"GPS manager started on {self._detected_port}")
            return True

    def stop(self) -> None:
        """Stop GPS operations and cleanup resources."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._logger.info("Stopping GPS manager...")
                self._stop_event.set()

        # Wait outside lock to avoid deadlock
        if self._thread:
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                self._logger.warning("GPS thread did not stop gracefully")
            else:
                self._logger.info("GPS manager stopped")

        with self._lock:
            self._disconnect()
            self._thread = None
            self._update_state(GPSState.DISABLED)

    def get_status(self) -> GPSStatus:
        """Get current GPS status for UI display.

        Returns:
            GPSStatus dataclass with current state
        """
        with self._lock:
            return GPSStatus(
                state=self._state,
                position=GPSPosition(
                    latitude=self._position.latitude,
                    longitude=self._position.longitude,
                    altitude=self._position.altitude,
                    fix_quality=self._position.fix_quality,
                    satellites=self._position.satellites,
                    hdop=self._position.hdop,
                    timestamp=self._position.timestamp,
                    valid=self._position.valid
                ),
                datetime_info=GPSDateTime(
                    utc_datetime=self._datetime_info.utc_datetime,
                    valid=self._datetime_info.valid
                ),
                last_update=self._position.timestamp,
                last_push_to_mount=(
                    datetime.fromtimestamp(self._last_push_time, tz=timezone.utc)
                    if self._last_push_time else None
                ),
                push_count=self._push_count,
                error_message=self._error_message,
                port=self._detected_port or self._config.gps_port,
                connected=self._serial is not None and self._serial.is_open
            )

    def get_position(self) -> GPSPosition:
        """Get current GPS position.

        Returns:
            GPSPosition dataclass with current position
        """
        with self._lock:
            return GPSPosition(
                latitude=self._position.latitude,
                longitude=self._position.longitude,
                altitude=self._position.altitude,
                fix_quality=self._position.fix_quality,
                satellites=self._position.satellites,
                hdop=self._position.hdop,
                timestamp=self._position.timestamp,
                valid=self._position.valid
            )

    def is_connected(self) -> bool:
        """Check if GPS serial connection is active.

        Returns:
            True if serial connection is open
        """
        with self._lock:
            return self._serial is not None and self._serial.is_open

    def has_valid_fix(self) -> bool:
        """Check if GPS has valid position fix meeting quality requirements.

        Returns:
            True if fix meets configured quality thresholds
        """
        with self._lock:
            return (
                self._position.valid and
                self._position.fix_quality >= self._config.gps_min_fix_quality and
                self._position.satellites >= self._config.gps_min_satellites
            )

    def push_location_now(self) -> bool:
        """Manually trigger location push to mount.

        Returns:
            True if push succeeded, False otherwise
        """
        return self._push_location_to_mount()

    def push_on_mount_connect(self) -> tuple[bool, str]:
        """Push location when mount connects (if configured and fix available).

        Called by TTS160Device when mount connection is established.
        Only pushes if push_on_connect is enabled and GPS has valid fix.

        Returns:
            Tuple of (success, message) where:
            - success: True if location was pushed, False otherwise
            - message: Status message for logging
        """
        if not self._config.gps_push_on_connect:
            return (False, "Push on connect disabled")

        if not self.has_valid_fix():
            return (False, "No valid GPS fix available")

        if self._push_location_to_mount():
            return (True, f"GPS location pushed: {self._position.latitude:.6f}, {self._position.longitude:.6f}")
        else:
            return (False, "Failed to push GPS location")

    def set_push_callback(
        self,
        callback: Callable[[float, float, float, str], bool]
    ) -> None:
        """Set callback for pushing location to mount.

        Args:
            callback: Function(lat, lon, alt, name) -> bool
        """
        with self._lock:
            self._push_location_callback = callback

    # -------------------------------------------------------------------------
    # Background Thread
    # -------------------------------------------------------------------------

    def _background_reader(self) -> None:
        """Background thread function for reading GPS data.

        Runs at approximately 1Hz, reading and parsing NMEA sentences.
        Uses stop_event for clean shutdown.
        """
        self._logger.info("GPS background reader started")
        self._update_state(GPSState.DISCONNECTED)

        while not self._stop_event.is_set():
            try:
                # Check connection
                if not self._serial or not self._serial.is_open:
                    if not self._connect():
                        # Wait before retry with exponential backoff
                        if self._stop_event.wait(self._reconnect_delay):
                            break
                        self._reconnect_delay = min(
                            self._reconnect_delay * 1.5,
                            self.RECONNECT_DELAY_MAX
                        )
                        continue

                # Reset reconnect delay on successful connection
                self._reconnect_delay = self.RECONNECT_DELAY_BASE

                # Read and parse NMEA sentence
                sentence = self._read_nmea_sentence()
                if sentence:
                    self._process_sentence(sentence)

                # Check for signal loss
                if time.time() - self._last_valid_sentence > self.NMEA_SENTENCE_TIMEOUT:
                    self._handle_signal_loss()

                # Rate limiting
                if self._stop_event.wait(1.0 / self.BACKGROUND_READ_RATE):
                    break

            except serial.SerialException as e:
                self._logger.warning(f"GPS serial error: {e}")
                self._disconnect()
                self._update_state(GPSState.DISCONNECTED)
                self._error_message = str(e)

            except Exception as e:
                self._logger.error(f"GPS reader error: {e}")
                self._update_state(GPSState.ERROR)
                self._error_message = str(e)
                if self._stop_event.wait(2.0):
                    break

        self._logger.info("GPS background reader stopped")

    # -------------------------------------------------------------------------
    # Serial Connection Management
    # -------------------------------------------------------------------------

    def _autodetect_port(self) -> Optional[str]:
        """Scan available COM ports to find a GPS device.

        Tries each available serial port, opens it briefly, and checks
        for NMEA sentences to identify a GPS device.

        Returns:
            Port name (e.g., 'COM3') if GPS found, None otherwise
        """
        # Get list of available ports
        available_ports = serial.tools.list_ports.comports()

        if not available_ports:
            self._logger.warning("No serial ports available for GPS autodetect")
            return None

        self._logger.info(f"Scanning {len(available_ports)} ports for GPS device...")

        # Ports to skip (likely not GPS devices)
        skip_patterns = ['bluetooth', 'bt', 'modem']

        for port_info in available_ports:
            port_name = port_info.device
            port_desc = port_info.description.lower()

            # Skip bluetooth and modem ports
            if any(pattern in port_desc for pattern in skip_patterns):
                self._logger.debug(f"Skipping {port_name} ({port_info.description})")
                continue

            # Skip the mount's serial port if we know it
            mount_port = getattr(self._config, 'dev_port', '')
            if mount_port and port_name.upper() == mount_port.upper():
                self._logger.debug(f"Skipping {port_name} (mount port)")
                continue

            self._logger.debug(f"Trying {port_name} ({port_info.description})...")

            try:
                # Try to open the port and look for NMEA data
                with serial.Serial(
                    port=port_name,
                    baudrate=self._config.gps_baudrate,
                    timeout=2.0,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE
                ) as test_serial:
                    # Read for up to 3 seconds looking for NMEA
                    start_time = time.time()
                    buffer = ""

                    while time.time() - start_time < 3.0:
                        if test_serial.in_waiting > 0:
                            try:
                                data = test_serial.read(test_serial.in_waiting)
                                buffer += data.decode('ascii', errors='ignore')

                                # Check for NMEA sentence pattern
                                if '$GP' in buffer or '$GN' in buffer:
                                    # Look for complete sentence
                                    if '*' in buffer and '\n' in buffer:
                                        self._logger.info(
                                            f"GPS device found on {port_name} "
                                            f"({port_info.description})"
                                        )
                                        return port_name
                            except Exception:
                                pass

                        time.sleep(0.1)

            except serial.SerialException as e:
                self._logger.debug(f"Cannot open {port_name}: {e}")
                continue
            except Exception as e:
                self._logger.debug(f"Error testing {port_name}: {e}")
                continue

        self._logger.warning("GPS autodetect: No GPS device found on any port")
        return None

    def _connect(self) -> bool:
        """Establish GPS serial connection.

        Returns:
            True if connection established, False otherwise
        """
        with self._lock:
            if self._serial and self._serial.is_open:
                return True

            self._update_state(GPSState.CONNECTING)

            try:
                # Use detected port (may be from autodetect or config)
                port = self._detected_port or self._config.gps_port
                baudrate = self._config.gps_baudrate
                timeout = self._config.gps_read_timeout

                self._logger.info(f"Connecting to GPS on {port} at {baudrate} baud")

                self._serial = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    timeout=timeout,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE
                )

                self._update_state(GPSState.CONNECTED)
                self._error_message = ""
                self._logger.info(f"GPS connected on {port}")
                return True

            except serial.SerialException as e:
                self._logger.warning(f"GPS connection failed: {e}")
                self._error_message = str(e)
                self._update_state(GPSState.DISCONNECTED)
                return False

    def _disconnect(self) -> None:
        """Close GPS serial connection."""
        with self._lock:
            if self._serial:
                try:
                    if self._serial.is_open:
                        self._serial.close()
                        self._logger.debug("GPS serial connection closed")
                except Exception as e:
                    self._logger.warning(f"Error closing GPS serial: {e}")
                finally:
                    self._serial = None

    # -------------------------------------------------------------------------
    # NMEA Parsing
    # -------------------------------------------------------------------------

    def _read_nmea_sentence(self) -> Optional[str]:
        """Read a single NMEA sentence from serial port.

        Returns:
            NMEA sentence string or None if read failed
        """
        try:
            if not self._serial or not self._serial.is_open:
                return None

            line = self._serial.readline()
            if not line:
                return None

            # Decode and strip whitespace
            sentence = line.decode('ascii', errors='ignore').strip()

            # Validate NMEA sentence format
            if sentence.startswith('$') and '*' in sentence:
                if self._config.gps_verbose_logging:
                    self._logger.debug(f"GPS NMEA: {sentence}")
                return sentence

            return None

        except Exception as e:
            if self._config.gps_verbose_logging:
                self._logger.debug(f"NMEA read error: {e}")
            return None

    def _process_sentence(self, sentence: str) -> None:
        """Process a single NMEA sentence.

        Args:
            sentence: Raw NMEA sentence string
        """
        try:
            msg = pynmea2.parse(sentence)

            if isinstance(msg, pynmea2.types.talker.GGA):
                self._parse_gga(msg)
            elif isinstance(msg, pynmea2.types.talker.RMC):
                self._parse_rmc(msg)

            self._last_valid_sentence = time.time()

        except pynmea2.ParseError as e:
            if self._config.gps_verbose_logging:
                self._logger.debug(f"NMEA parse error: {e}")

    def _parse_gga(self, msg) -> None:
        """Parse GGA sentence for position data.

        GGA provides: latitude, longitude, altitude, fix quality, satellites, HDOP

        Args:
            msg: Parsed pynmea2 GGA message
        """
        with self._lock:
            try:
                # Extract position (pynmea2 provides as signed floats)
                if msg.latitude is not None and msg.longitude is not None:
                    self._position.latitude = float(msg.latitude)
                    self._position.longitude = float(msg.longitude)

                # Altitude (may be None)
                if msg.altitude is not None:
                    self._position.altitude = float(msg.altitude)

                # Fix quality
                gps_qual = int(msg.gps_qual) if msg.gps_qual else 0
                if 0 <= gps_qual <= 8:
                    self._position.fix_quality = GPSFixQuality(gps_qual)
                else:
                    self._position.fix_quality = GPSFixQuality.INVALID

                # Satellites
                self._position.satellites = int(msg.num_sats) if msg.num_sats else 0

                # HDOP
                if msg.horizontal_dil:
                    self._position.hdop = float(msg.horizontal_dil)

                # Update timestamp and validity
                self._position.timestamp = datetime.now(timezone.utc)
                self._position.valid = self._check_fix_validity()

                # Update state
                if self._position.valid:
                    self._update_state(GPSState.FIX_VALID)
                elif self._state != GPSState.ACQUIRING_FIX:
                    self._update_state(GPSState.ACQUIRING_FIX)

                if self._config.gps_verbose_logging:
                    self._logger.debug(
                        f"GPS GGA: {self._position.latitude:.6f}, "
                        f"{self._position.longitude:.6f}, "
                        f"alt={self._position.altitude:.1f}m, "
                        f"Q={self._position.fix_quality.name}, "
                        f"sats={self._position.satellites}, "
                        f"HDOP={self._position.hdop:.1f}"
                    )

            except Exception as e:
                self._logger.warning(f"Error parsing GGA: {e}")

    def _parse_rmc(self, msg) -> None:
        """Parse RMC sentence for date/time data.

        Args:
            msg: Parsed pynmea2 RMC message
        """
        with self._lock:
            try:
                if msg.datetime:
                    self._datetime_info.utc_datetime = msg.datetime.replace(
                        tzinfo=timezone.utc
                    )
                    self._datetime_info.valid = True

                    if self._config.gps_verbose_logging:
                        self._logger.debug(
                            f"GPS RMC: {self._datetime_info.utc_datetime.isoformat()}"
                        )

            except Exception as e:
                self._logger.warning(f"Error parsing RMC: {e}")

    def _check_fix_validity(self) -> bool:
        """Check if current fix meets validity requirements.

        Returns:
            True if fix is valid and meets configured thresholds
        """
        return (
            self._position.fix_quality >= GPSFixQuality.GPS_FIX and
            -90 <= self._position.latitude <= 90 and
            -180 <= self._position.longitude <= 180
        )

    def _handle_signal_loss(self) -> None:
        """Handle GPS signal loss condition."""
        with self._lock:
            if self._position.valid:
                self._logger.warning("GPS signal lost")
                self._position.valid = False
                self._position.fix_quality = GPSFixQuality.INVALID
                if self._state == GPSState.FIX_VALID:
                    self._update_state(GPSState.ACQUIRING_FIX)

    # -------------------------------------------------------------------------
    # Location Push
    # -------------------------------------------------------------------------

    def _push_location_to_mount(self) -> bool:
        """Push current location to mount using callback.

        Returns:
            True if push succeeded, False otherwise
        """
        with self._lock:
            if not self._position.valid:
                self._logger.warning("Cannot push invalid GPS position to mount")
                return False

            if self._push_location_callback is None:
                self._logger.warning("No mount push callback configured")
                return False

            try:
                success = self._push_location_callback(
                    self._position.latitude,
                    self._position.longitude,
                    self._position.altitude,
                    self._config.gps_location_name
                )

                if success:
                    self._last_push_time = time.time()
                    self._push_count += 1
                    self._logger.info(
                        f"GPS location pushed to mount: "
                        f"{self._position.latitude:.6f}, "
                        f"{self._position.longitude:.6f}, "
                        f"alt={self._position.altitude:.1f}m"
                    )
                else:
                    self._logger.warning("Failed to push GPS location to mount")

                return success

            except Exception as e:
                self._logger.error(f"Error pushing location to mount: {e}")
                return False

    # -------------------------------------------------------------------------
    # State Management
    # -------------------------------------------------------------------------

    def _update_state(self, new_state: GPSState) -> None:
        """Update GPS state with logging.

        Args:
            new_state: New GPS state
        """
        if self._state != new_state:
            old_state = self._state
            self._state = new_state
            self._logger.debug(f"GPS state: {old_state.name} -> {new_state.name}")
