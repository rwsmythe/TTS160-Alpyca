# -*- coding: utf-8 -*-
"""
ZWO Camera Source

Camera source implementation for native ZWO ASI cameras.
Uses the zwo_capture package for direct camera control.
"""

import logging
import threading
from typing import Any, Dict, Optional

from camera_source import CameraSource, CaptureResult

# Try to import zwo_capture package
try:
    from zwo_capture import (
        ZWOCamera,
        is_available as zwo_is_available,
        ZWOError,
        ZWONotAvailable,
        ZWOCameraError,
        ZWOTimeoutError,
    )
    ZWO_AVAILABLE = True
except ImportError:
    ZWO_AVAILABLE = False
    ZWOCamera = None
    zwo_is_available = lambda: False
    ZWOError = Exception
    ZWONotAvailable = Exception
    ZWOCameraError = Exception
    ZWOTimeoutError = Exception


class ZWOCameraSource(CameraSource):
    """Native ZWO ASI camera source.

    Provides direct control of ZWO ASI cameras via the zwo_capture package.
    This bypasses the Alpaca protocol for potentially better performance
    and simpler setup when using ZWO cameras.

    Configuration:
        Uses camera_id (0-based index) to select camera.
        Capture settings (exposure, gain, binning, image_type) configurable.
    """

    def __init__(
        self,
        logger: logging.Logger,
        camera_id: int = 0,
        gain: int = 100,
        image_type: str = 'RAW16'
    ):
        """Initialize ZWO camera source.

        Args:
            logger: Logger instance for camera operations.
            camera_id: Camera index (0 for first camera).
            gain: Camera gain setting (typically 0-500).
            image_type: Image format ('RAW8', 'RAW16', 'RGB24', 'Y8').
        """
        super().__init__(logger)
        self._camera_id = camera_id
        self._gain = gain
        self._image_type = image_type
        self._camera: Optional[ZWOCamera] = None
        self._lock = threading.RLock()
        self._error_message = ""
        self._last_info: Dict[str, Any] = {}

    @property
    def source_type(self) -> str:
        """Get camera source type identifier."""
        return "zwo"

    @staticmethod
    def is_available() -> bool:
        """Check if ZWO camera support is available."""
        if not ZWO_AVAILABLE:
            return False
        return zwo_is_available()

    def connect(self) -> bool:
        """Establish connection to ZWO camera.

        Returns:
            True if connection successful, False otherwise.
        """
        if not ZWO_AVAILABLE:
            self._error_message = "zwo_capture module not available"
            return False

        with self._lock:
            if self._camera is not None and self._camera.is_open:
                self._logger.debug("Already connected to ZWO camera")
                return True

            try:
                self._camera = ZWOCamera(camera_id=self._camera_id)
                self._camera.open()
                self._last_info = self._camera.get_camera_info()
                self._error_message = ""
                self._logger.info(
                    f"Connected to ZWO camera: {self._last_info.get('name', 'Unknown')}"
                )
                return True

            except ZWONotAvailable as e:
                self._error_message = str(e)
                self._logger.warning(f"ZWO camera not available: {e}")
                self._camera = None
                return False

            except ZWOCameraError as e:
                self._error_message = str(e)
                self._logger.error(f"Failed to connect to ZWO camera: {e}")
                self._camera = None
                return False

            except Exception as e:
                self._error_message = str(e)
                self._logger.error(f"Unexpected error connecting to ZWO camera: {e}")
                self._camera = None
                return False

    def disconnect(self) -> None:
        """Disconnect from camera."""
        with self._lock:
            if self._camera is not None:
                try:
                    self._camera.close()
                    self._logger.info("Disconnected from ZWO camera")
                except Exception as e:
                    self._logger.warning(f"Error during ZWO disconnect: {e}")
                finally:
                    self._camera = None

    def is_connected(self) -> bool:
        """Check if camera is connected."""
        with self._lock:
            return self._camera is not None and self._camera.is_open

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
        with self._lock:
            if not self.is_connected():
                self._error_message = "Camera not connected"
                return None

            try:
                # Convert exposure to milliseconds
                exposure_ms = int(exposure_sec * 1000)

                # Configure camera
                self._camera.configure(
                    exposure_ms=exposure_ms,
                    gain=self._gain,
                    binning=binning,
                    image_type=self._image_type
                )

                # Calculate timeout (exposure + 30s overhead)
                timeout_ms = exposure_ms + 30000

                # Capture image
                image = self._camera.capture(timeout_ms=timeout_ms)

                # Get updated camera info
                self._last_info = self._camera.get_camera_info()

                self._logger.debug(
                    f"ZWO capture: {image.shape}, exposure={exposure_sec}s, bin={binning}"
                )

                return CaptureResult(
                    image=image,
                    width=self._last_info['current_width'],
                    height=self._last_info['current_height'],
                    exposure_time=exposure_sec,
                    binning=binning,
                    camera_info=self._last_info.copy()
                )

            except ZWOTimeoutError as e:
                self._error_message = f"Capture timeout: {e}"
                self._logger.error(self._error_message)
                return None

            except ZWOCameraError as e:
                self._error_message = f"Capture failed: {e}"
                self._logger.error(self._error_message)
                return None

            except Exception as e:
                self._error_message = f"Unexpected capture error: {e}"
                self._logger.error(self._error_message)
                return None

    def get_info(self) -> Dict[str, Any]:
        """Get camera information.

        Returns:
            Dict with camera properties.
        """
        with self._lock:
            if self._camera is not None and self._camera.is_open:
                try:
                    self._last_info = self._camera.get_camera_info()
                except Exception:
                    pass  # Use cached info

            if not self._last_info:
                return {
                    'name': 'Not connected',
                    'pixel_size_um': 0.0,
                    'sensor_width': 0,
                    'sensor_height': 0,
                    'current_width': 0,
                    'current_height': 0,
                }

            return {
                'name': self._last_info.get('name', 'Unknown'),
                'pixel_size_um': self._last_info.get('pixel_size_um', 0.0),
                'sensor_width': self._last_info.get('sensor_width', 0),
                'sensor_height': self._last_info.get('sensor_height', 0),
                'current_width': self._last_info.get('current_width', 0),
                'current_height': self._last_info.get('current_height', 0),
                'is_color': self._last_info.get('is_color', False),
                'bayer_pattern': self._last_info.get('bayer_pattern'),
                'bit_depth': self._last_info.get('bit_depth', 8),
            }

    def get_error_message(self) -> str:
        """Get last error message."""
        return self._error_message

    def set_gain(self, gain: int) -> None:
        """Update gain setting.

        Args:
            gain: New gain value (typically 0-500).

        Note:
            Takes effect on next capture.
        """
        self._gain = gain

    def set_image_type(self, image_type: str) -> None:
        """Update image type setting.

        Args:
            image_type: Image format ('RAW8', 'RAW16', 'RGB24', 'Y8').

        Note:
            Takes effect on next capture.
        """
        self._image_type = image_type

    def get_temperature(self) -> Optional[float]:
        """Get camera sensor temperature.

        Returns:
            Temperature in Celsius, or None if not available.
        """
        with self._lock:
            if self._camera is not None and self._camera.is_open:
                try:
                    return self._camera.get_temperature()
                except Exception:
                    pass
            return None
