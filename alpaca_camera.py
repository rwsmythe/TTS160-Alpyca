# -*- coding: utf-8 -*-
"""
Alpaca Camera Source

Camera source implementation for ASCOM Alpaca protocol cameras.
Wraps the existing CameraManager for use with the camera source abstraction.
"""

import logging
from typing import Any, Dict, Optional

from camera_source import CameraSource, CaptureResult

# Import the existing camera manager
from camera_manager import CameraManager, ALPYCA_AVAILABLE


class AlpacaCameraSource(CameraSource):
    """Alpaca protocol camera source.

    Uses the alpyca library to communicate with ASCOM Alpaca cameras.
    This wraps the existing CameraManager implementation.

    Configuration:
        Requires address, port, and device_number to be set before connecting.
    """

    def __init__(
        self,
        logger: logging.Logger,
        address: str = "127.0.0.1",
        port: int = 11111,
        device_number: int = 0
    ):
        """Initialize Alpaca camera source.

        Args:
            logger: Logger instance for camera operations.
            address: Alpaca server IP address or hostname.
            port: Alpaca server port number.
            device_number: Camera device number on the server.
        """
        super().__init__(logger)
        self._address = address
        self._port = port
        self._device_number = device_number
        self._manager = CameraManager(logger)
        self._error_message = ""

    @property
    def source_type(self) -> str:
        """Get camera source type identifier."""
        return "alpaca"

    @staticmethod
    def is_available() -> bool:
        """Check if Alpaca camera support is available."""
        return ALPYCA_AVAILABLE

    def connect(self) -> bool:
        """Establish connection to Alpaca camera.

        Returns:
            True if connection successful, False otherwise.
        """
        if not ALPYCA_AVAILABLE:
            self._error_message = "alpyca library not available"
            return False

        success = self._manager.connect(
            self._address,
            self._port,
            self._device_number
        )

        if not success:
            self._error_message = self._manager.get_error_message()

        return success

    def disconnect(self) -> None:
        """Disconnect from camera."""
        self._manager.disconnect()

    def is_connected(self) -> bool:
        """Check if camera is connected."""
        return self._manager.is_connected()

    def capture(
        self,
        exposure_sec: float,
        binning: int = 2
    ) -> Optional[CaptureResult]:
        """Capture a single image.

        Args:
            exposure_sec: Exposure time in seconds.
            binning: Pixel binning factor (1, 2, or 4).

        Returns:
            CaptureResult with captured image, or None if capture failed.
        """
        image_data = self._manager.capture_image(
            exposure_seconds=exposure_sec,
            binning=binning
        )

        if image_data is None:
            self._error_message = self._manager.get_error_message()
            return None

        camera_info = self._manager.get_camera_info()
        info_dict = {}
        if camera_info:
            info_dict = {
                'name': camera_info.name,
                'pixel_size_um': camera_info.pixel_size_x,  # Assume square pixels
                'sensor_width': camera_info.sensor_width,
                'sensor_height': camera_info.sensor_height,
                'current_width': image_data.width,
                'current_height': image_data.height,
            }

        return CaptureResult(
            image=image_data.data,
            width=image_data.width,
            height=image_data.height,
            exposure_time=image_data.exposure_time,
            binning=image_data.binning,
            camera_info=info_dict
        )

    def get_info(self) -> Dict[str, Any]:
        """Get camera information.

        Returns:
            Dict with camera properties.
        """
        camera_info = self._manager.get_camera_info()
        if camera_info is None:
            return {
                'name': 'Not connected',
                'pixel_size_um': 0.0,
                'sensor_width': 0,
                'sensor_height': 0,
                'current_width': 0,
                'current_height': 0,
            }

        return {
            'name': camera_info.name,
            'pixel_size_um': camera_info.pixel_size_x,
            'sensor_width': camera_info.sensor_width,
            'sensor_height': camera_info.sensor_height,
            'current_width': camera_info.sensor_width,  # Updated after capture
            'current_height': camera_info.sensor_height,
        }

    def get_error_message(self) -> str:
        """Get last error message."""
        return self._error_message or self._manager.get_error_message()

    def set_server(self, address: str, port: int, device_number: int = 0) -> None:
        """Update server connection parameters.

        Args:
            address: Alpaca server IP address or hostname.
            port: Alpaca server port number.
            device_number: Camera device number on the server.

        Note:
            Must disconnect and reconnect for changes to take effect.
        """
        self._address = address
        self._port = port
        self._device_number = device_number
