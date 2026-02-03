# -*- coding: utf-8 -*-
"""
Camera Manager for Alignment Monitor.

Provides camera discovery and control via ASCOM Alpaca protocol
using the alpyca library.

Third-Party Library:
    alpyca is licensed under the MIT License by the ASCOM Initiative.
    https://github.com/ASCOMInitiative/alpyca
"""

import logging
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, List

import numpy as np

# Import alpyca for Alpaca camera control
try:
    from alpyca.camera import Camera
    from alpyca.discovery import search_ipv4
    ALPYCA_AVAILABLE = True
except ImportError:
    ALPYCA_AVAILABLE = False
    Camera = None
    search_ipv4 = None


class CameraState(IntEnum):
    """Camera connection states."""
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    EXPOSING = 3
    READING = 4
    ERROR = 5


@dataclass
class CameraInfo:
    """Camera device information."""
    name: str
    description: str
    address: str
    port: int
    device_number: int
    sensor_width: int = 0
    sensor_height: int = 0
    pixel_size_x: float = 0.0
    pixel_size_y: float = 0.0


@dataclass
class ImageData:
    """Captured image data."""
    data: np.ndarray
    width: int
    height: int
    exposure_time: float
    timestamp: float
    binning: int = 1


class CameraManager:
    """Thread-safe Alpaca camera manager.

    Provides camera discovery, connection management, and image capture
    via the ASCOM Alpaca protocol using the alpyca library.

    Thread Safety:
        All public methods are thread-safe via RLock protection.

    Attributes:
        DISCOVERY_TIMEOUT: Timeout for camera discovery in seconds.
        EXPOSURE_POLL_INTERVAL: Interval for polling exposure completion.
    """

    DISCOVERY_TIMEOUT = 5.0
    EXPOSURE_POLL_INTERVAL = 0.1

    def __init__(self, logger: logging.Logger):
        """Initialize camera manager.

        Args:
            logger: Logger instance for camera operations.
        """
        self._logger = logger
        self._lock = threading.RLock()
        self._camera: Optional[Camera] = None
        self._state = CameraState.DISCONNECTED
        self._camera_info: Optional[CameraInfo] = None
        self._error_message: str = ""

        if not ALPYCA_AVAILABLE:
            self._logger.warning(
                "alpyca library not available - camera functions disabled. "
                "Install with: pip install alpyca"
            )

    def discover_cameras(self, timeout: float = DISCOVERY_TIMEOUT) -> List[str]:
        """Discover available Alpaca servers on the network.

        Args:
            timeout: Discovery timeout in seconds.

        Returns:
            List of server addresses in 'ip:port' format.
        """
        if not ALPYCA_AVAILABLE:
            self._logger.warning("Cannot discover cameras: alpyca not available")
            return []

        try:
            self._logger.debug(f"Discovering Alpaca servers (timeout={timeout}s)...")
            servers = search_ipv4(count=2, timeout=timeout)
            self._logger.info(f"Found {len(servers)} Alpaca server(s): {servers}")
            return servers
        except Exception as e:
            self._logger.error(f"Camera discovery failed: {e}")
            return []

    def connect(
        self,
        address: str,
        port: int,
        device_number: int = 0
    ) -> bool:
        """Connect to an Alpaca camera.

        Args:
            address: Server IP address or hostname.
            port: Server port number.
            device_number: Camera device number on the server.

        Returns:
            True if connection successful, False otherwise.
        """
        if not ALPYCA_AVAILABLE:
            self._error_message = "alpyca library not available"
            return False

        with self._lock:
            if self._state == CameraState.CONNECTED:
                self._logger.debug("Already connected to camera")
                return True

            self._update_state(CameraState.CONNECTING)

            try:
                server_addr = f"{address}:{port}"
                self._logger.info(f"Connecting to camera at {server_addr}, device {device_number}")

                self._camera = Camera(server_addr, device_number)
                self._camera.Connected = True

                if not self._camera.Connected:
                    raise ConnectionError("Failed to establish connection")

                # Get camera info
                self._camera_info = CameraInfo(
                    name=self._camera.Name,
                    description=self._camera.Description,
                    address=address,
                    port=port,
                    device_number=device_number,
                    sensor_width=self._camera.CameraXSize,
                    sensor_height=self._camera.CameraYSize,
                    pixel_size_x=self._camera.PixelSizeX,
                    pixel_size_y=self._camera.PixelSizeY
                )

                self._update_state(CameraState.CONNECTED)
                self._error_message = ""
                self._logger.info(
                    f"Connected to camera: {self._camera_info.name} "
                    f"({self._camera_info.sensor_width}x{self._camera_info.sensor_height})"
                )
                return True

            except Exception as e:
                self._error_message = str(e)
                self._update_state(CameraState.ERROR)
                self._logger.error(f"Failed to connect to camera: {e}")
                self._camera = None
                self._camera_info = None
                return False

    def disconnect(self) -> None:
        """Disconnect from the camera."""
        with self._lock:
            if self._camera is not None:
                try:
                    self._camera.Connected = False
                    self._logger.info("Disconnected from camera")
                except Exception as e:
                    self._logger.warning(f"Error during disconnect: {e}")
                finally:
                    self._camera = None
                    self._camera_info = None

            self._update_state(CameraState.DISCONNECTED)

    def capture_image(
        self,
        exposure_seconds: float,
        binning: int = 1,
        timeout: float = 60.0
    ) -> Optional[ImageData]:
        """Capture a single image.

        Args:
            exposure_seconds: Exposure duration in seconds.
            binning: Camera binning factor (1, 2, or 4).
            timeout: Maximum time to wait for exposure completion.

        Returns:
            ImageData with captured image, or None if capture failed.
        """
        with self._lock:
            if not self.is_connected():
                self._logger.error("Cannot capture: camera not connected")
                return None

            try:
                # Set binning
                self._camera.BinX = binning
                self._camera.BinY = binning

                # Calculate expected image dimensions
                expected_width = self._camera.CameraXSize // binning
                expected_height = self._camera.CameraYSize // binning

                # Start exposure
                self._update_state(CameraState.EXPOSING)
                start_time = time.time()
                self._logger.debug(
                    f"Starting {exposure_seconds}s exposure (binning={binning})"
                )

                self._camera.StartExposure(exposure_seconds, True)  # Light frame

                # Wait for exposure to complete
                elapsed = 0
                while not self._camera.ImageReady:
                    time.sleep(self.EXPOSURE_POLL_INTERVAL)
                    elapsed = time.time() - start_time

                    if elapsed > timeout:
                        self._logger.error("Exposure timeout")
                        self._camera.AbortExposure()
                        self._update_state(CameraState.ERROR)
                        return None

                # Read image data
                self._update_state(CameraState.READING)
                image_array = self._camera.ImageArray

                # Convert to numpy array
                # alpyca returns nested list, need to convert
                data = np.array(image_array, dtype=np.float64)

                # Transpose if needed (alpyca returns [X, Y], we want [Y, X])
                if data.shape[0] == expected_width and data.shape[1] == expected_height:
                    data = data.T

                self._update_state(CameraState.CONNECTED)

                capture_time = time.time()
                self._logger.debug(
                    f"Image captured: {data.shape[1]}x{data.shape[0]} "
                    f"in {capture_time - start_time:.2f}s"
                )

                return ImageData(
                    data=data,
                    width=data.shape[1],
                    height=data.shape[0],
                    exposure_time=exposure_seconds,
                    timestamp=capture_time,
                    binning=binning
                )

            except Exception as e:
                self._error_message = str(e)
                self._update_state(CameraState.ERROR)
                self._logger.error(f"Image capture failed: {e}")
                return None

    def abort_exposure(self) -> bool:
        """Abort current exposure.

        Returns:
            True if abort successful, False otherwise.
        """
        with self._lock:
            if self._camera is None:
                return False

            try:
                if self._camera.CanAbortExposure:
                    self._camera.AbortExposure()
                    self._logger.info("Exposure aborted")
                    self._update_state(CameraState.CONNECTED)
                    return True
                else:
                    self._logger.warning("Camera does not support abort")
                    return False
            except Exception as e:
                self._logger.error(f"Failed to abort exposure: {e}")
                return False

    def is_connected(self) -> bool:
        """Check if camera is connected.

        Returns:
            True if connected, False otherwise.
        """
        with self._lock:
            if self._camera is None:
                return False
            try:
                return self._camera.Connected
            except Exception:
                return False

    def get_state(self) -> CameraState:
        """Get current camera state.

        Returns:
            Current CameraState.
        """
        with self._lock:
            return self._state

    def get_camera_info(self) -> Optional[CameraInfo]:
        """Get camera information.

        Returns:
            CameraInfo if connected, None otherwise.
        """
        with self._lock:
            if self._camera_info is None:
                return None
            # Return a copy
            return CameraInfo(
                name=self._camera_info.name,
                description=self._camera_info.description,
                address=self._camera_info.address,
                port=self._camera_info.port,
                device_number=self._camera_info.device_number,
                sensor_width=self._camera_info.sensor_width,
                sensor_height=self._camera_info.sensor_height,
                pixel_size_x=self._camera_info.pixel_size_x,
                pixel_size_y=self._camera_info.pixel_size_y
            )

    def get_error_message(self) -> str:
        """Get last error message.

        Returns:
            Error message string.
        """
        with self._lock:
            return self._error_message

    def _update_state(self, new_state: CameraState) -> None:
        """Update camera state with logging.

        Args:
            new_state: New camera state.
        """
        if self._state != new_state:
            old_state = self._state
            self._state = new_state
            self._logger.debug(f"Camera state: {old_state.name} -> {new_state.name}")
