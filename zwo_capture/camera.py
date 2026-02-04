"""
ZWO Camera Interface

Main camera class providing a clean, minimal Python interface for
ZWO ASI camera capture operations, optimized for plate solving workflows.
"""

import logging
from typing import Any, Dict, Optional

import numpy as np

from .config import (
    DEFAULT_CONFIG,
    IMAGE_TYPES,
    IMAGE_TYPE_NAMES,
    SUPPORTED_BINNING,
    validate_binning,
    validate_image_type,
)
from .exceptions import (
    ZWOCameraError,
    ZWOConfigurationError,
    ZWONotAvailable,
    ZWOTimeoutError,
)
from .sdk_loader import get_zwoasi_module, initialize_sdk

logger = logging.getLogger('zwo_capture')


class ZWOCamera:
    """Interface for ZWO ASI camera capture.

    This class provides a clean, context-manager-compatible interface
    for capturing images from ZWO ASI cameras. It wraps the zwoasi
    library with additional validation, error handling, and convenience
    features optimized for plate solving workflows.

    Example:
        >>> from zwo_capture import ZWOCamera
        >>> with ZWOCamera(camera_id=0) as cam:
        ...     cam.configure(exposure_ms=2000, gain=100, binning=2)
        ...     image = cam.capture()
        ...     info = cam.get_camera_info()

    Attributes:
        camera_id: The camera index (0-based)
        is_open: Whether the camera is currently open
    """

    def __init__(self, camera_id: int = 0):
        """Initialize camera instance.

        Note: This does NOT open the camera. Call open() or use as context manager.

        Args:
            camera_id: Camera index (0 for first camera, 1 for second, etc.)
        """
        self._camera_id = camera_id
        self._camera = None
        self._camera_info: Dict[str, Any] = {}
        self._controls: Dict[str, Any] = {}
        self._is_open = False

        # Current configuration state
        self._current_binning = 1
        self._current_image_type = IMAGE_TYPES['RAW16']
        self._current_width = 0
        self._current_height = 0

    @property
    def camera_id(self) -> int:
        """Camera index."""
        return self._camera_id

    @property
    def is_open(self) -> bool:
        """Whether camera is currently open."""
        return self._is_open

    def open(self) -> None:
        """Open the camera for capture operations.

        This method initializes the SDK if needed and opens the camera.
        It must be called before configure() or capture().

        Raises:
            ZWONotAvailable: If SDK cannot be loaded
            ZWOCameraError: If camera cannot be opened
        """
        if self._is_open:
            return

        # Initialize SDK
        initialize_sdk()
        zwoasi = get_zwoasi_module()

        # Get number of connected cameras
        num_cameras = zwoasi.get_num_cameras()
        if num_cameras == 0:
            raise ZWOCameraError("No ZWO cameras connected")

        if self._camera_id >= num_cameras:
            raise ZWOCameraError(
                f"Camera ID {self._camera_id} not found. "
                f"Available cameras: 0-{num_cameras - 1}"
            )

        # Open camera
        try:
            self._camera = zwoasi.Camera(self._camera_id)
            self._camera_info = self._camera.get_camera_property()
            self._controls = self._camera.get_controls()
            self._is_open = True

            # Store sensor dimensions
            self._current_width = self._camera_info['MaxWidth']
            self._current_height = self._camera_info['MaxHeight']

            logger.info(
                f"Opened ZWO camera: {self._camera_info['Name']} "
                f"({self._current_width}x{self._current_height})"
            )
        except Exception as e:
            raise ZWOCameraError(f"Failed to open camera {self._camera_id}: {e}")

    def close(self) -> None:
        """Close the camera and release resources.

        This method is idempotent - calling it multiple times is safe.
        """
        if not self._is_open:
            return

        try:
            if self._camera is not None:
                self._camera.close()
                logger.info(f"Closed ZWO camera {self._camera_id}")
        except Exception as e:
            logger.warning(f"Error closing camera: {e}")
        finally:
            self._camera = None
            self._is_open = False

    def __enter__(self) -> 'ZWOCamera':
        """Context manager entry - opens camera."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - closes camera."""
        self.close()

    def configure(
        self,
        exposure_ms: int,
        gain: int,
        binning: int = 2,
        image_type: str = 'RAW16',
        bandwidth: int = 80,
        high_speed_mode: bool = False,
        **kwargs
    ) -> None:
        """Configure camera settings for capture.

        Args:
            exposure_ms: Exposure time in milliseconds
            gain: Camera gain (typically 0-500, camera-dependent)
            binning: Pixel binning (1, 2, 3, or 4)
            image_type: Image format ('RAW8', 'RGB24', 'RAW16', 'Y8')
            bandwidth: USB bandwidth percentage (40-100)
            high_speed_mode: Enable high-speed mode (reduces image quality)
            **kwargs: Additional control values to set

        Raises:
            ZWOCameraError: If camera is not open
            ZWOConfigurationError: If settings are invalid
        """
        if not self._is_open:
            raise ZWOCameraError("Camera not open. Call open() first.")

        zwoasi = get_zwoasi_module()

        # Validate parameters
        binning = validate_binning(binning)
        img_type = validate_image_type(image_type)

        # Validate exposure against camera limits
        if 'Exposure' in self._controls:
            exp_control = self._controls['Exposure']
            min_exp = exp_control['MinValue'] // 1000  # Convert us to ms
            max_exp = exp_control['MaxValue'] // 1000
            if exposure_ms < min_exp or exposure_ms > max_exp:
                raise ZWOConfigurationError(
                    f"Exposure {exposure_ms}ms out of range [{min_exp}-{max_exp}]ms"
                )

        # Validate gain against camera limits
        if 'Gain' in self._controls:
            gain_control = self._controls['Gain']
            if gain < gain_control['MinValue'] or gain > gain_control['MaxValue']:
                raise ZWOConfigurationError(
                    f"Gain {gain} out of range "
                    f"[{gain_control['MinValue']}-{gain_control['MaxValue']}]"
                )

        # Check if binning is supported
        supported_bins = self._camera_info.get('SupportedBins', [1, 2, 4])
        if binning not in supported_bins:
            raise ZWOConfigurationError(
                f"Binning {binning}x not supported. Available: {supported_bins}"
            )

        try:
            # Calculate ROI dimensions with binning
            width = self._camera_info['MaxWidth'] // binning
            height = self._camera_info['MaxHeight'] // binning

            # Set ROI format (this also sets binning and image type)
            self._camera.set_roi_format(width, height, binning, img_type)

            # Set control values
            # Exposure is in microseconds for the SDK
            self._camera.set_control_value(
                zwoasi.ASI_EXPOSURE, exposure_ms * 1000
            )
            self._camera.set_control_value(zwoasi.ASI_GAIN, gain)
            self._camera.set_control_value(zwoasi.ASI_BANDWIDTHOVERLOAD, bandwidth)
            self._camera.set_control_value(
                zwoasi.ASI_HIGH_SPEED_MODE, 1 if high_speed_mode else 0
            )

            # Apply any additional control values
            for control_name, value in kwargs.items():
                control_name_upper = control_name.upper()
                if hasattr(zwoasi, f'ASI_{control_name_upper}'):
                    control_id = getattr(zwoasi, f'ASI_{control_name_upper}')
                    self._camera.set_control_value(control_id, value)
                else:
                    logger.warning(f"Unknown control: {control_name}")

            # Store current configuration
            self._current_binning = binning
            self._current_image_type = img_type
            self._current_width = width
            self._current_height = height

            logger.debug(
                f"Configured: {exposure_ms}ms, gain={gain}, "
                f"bin={binning}, {image_type}, {width}x{height}"
            )

        except Exception as e:
            raise ZWOConfigurationError(f"Failed to configure camera: {e}")

    def capture(self, timeout_ms: Optional[int] = None) -> np.ndarray:
        """Capture a single frame.

        Args:
            timeout_ms: Timeout in milliseconds (default: 30000)

        Returns:
            NumPy array containing the captured image.
            Shape depends on binning and image type:
            - RAW8/RAW16/Y8: (height, width)
            - RGB24: (height, width, 3)

        Raises:
            ZWOCameraError: If camera is not open
            ZWOTimeoutError: If capture times out
        """
        if not self._is_open:
            raise ZWOCameraError("Camera not open. Call open() first.")

        if timeout_ms is None:
            timeout_ms = DEFAULT_CONFIG['timeout_ms']

        try:
            # Start exposure
            self._camera.start_exposure()

            # Wait for exposure to complete
            zwoasi = get_zwoasi_module()
            import time
            start_time = time.time()
            timeout_sec = timeout_ms / 1000.0

            while True:
                status = self._camera.get_exposure_status()
                if status == zwoasi.ASI_EXP_SUCCESS:
                    break
                elif status == zwoasi.ASI_EXP_FAILED:
                    raise ZWOCameraError("Exposure failed")
                elif status == zwoasi.ASI_EXP_WORKING:
                    elapsed = time.time() - start_time
                    if elapsed > timeout_sec:
                        self._camera.stop_exposure()
                        raise ZWOTimeoutError(
                            f"Capture timed out after {timeout_ms}ms"
                        )
                    time.sleep(0.01)  # 10ms polling interval
                else:
                    raise ZWOCameraError(f"Unknown exposure status: {status}")

            # Get the image data
            data = self._camera.get_data_after_exposure()

            # Reshape based on image type
            if self._current_image_type == IMAGE_TYPES['RGB24']:
                # RGB24: 3 bytes per pixel
                image = np.frombuffer(data, dtype=np.uint8)
                image = image.reshape((self._current_height, self._current_width, 3))
            elif self._current_image_type == IMAGE_TYPES['RAW16']:
                # RAW16: 2 bytes per pixel
                image = np.frombuffer(data, dtype=np.uint16)
                image = image.reshape((self._current_height, self._current_width))
            else:
                # RAW8, Y8: 1 byte per pixel
                image = np.frombuffer(data, dtype=np.uint8)
                image = image.reshape((self._current_height, self._current_width))

            logger.debug(
                f"Captured image: {image.shape}, dtype={image.dtype}"
            )
            return image

        except ZWOTimeoutError:
            raise
        except ZWOCameraError:
            raise
        except Exception as e:
            raise ZWOCameraError(f"Capture failed: {e}")

    def get_camera_info(self) -> Dict[str, Any]:
        """Get camera properties for plate solver integration.

        Returns:
            Dict containing:
            - name: Camera model name
            - pixel_size_um: Pixel size in micrometers
            - sensor_width: Full sensor width in pixels
            - sensor_height: Full sensor height in pixels
            - is_color: Whether camera has Bayer filter
            - bayer_pattern: Bayer pattern if color camera
            - bit_depth: Native bit depth
            - current_binning: Current binning setting
            - current_width: Current ROI width (after binning)
            - current_height: Current ROI height (after binning)

        Raises:
            ZWOCameraError: If camera is not open
        """
        if not self._is_open:
            raise ZWOCameraError("Camera not open. Call open() first.")

        # Bayer pattern mapping
        bayer_patterns = {
            0: 'RGGB',
            1: 'BGGR',
            2: 'GRBG',
            3: 'GBRG',
        }

        is_color = self._camera_info.get('IsColorCam', False)
        bayer_raw = self._camera_info.get('BayerPattern', 0)
        bayer_pattern = bayer_patterns.get(bayer_raw, 'Unknown') if is_color else None

        return {
            'name': self._camera_info.get('Name', 'Unknown'),
            'pixel_size_um': self._camera_info.get('PixelSize', 0.0),
            'sensor_width': self._camera_info.get('MaxWidth', 0),
            'sensor_height': self._camera_info.get('MaxHeight', 0),
            'is_color': is_color,
            'bayer_pattern': bayer_pattern,
            'bit_depth': self._camera_info.get('BitDepth', 8),
            'current_binning': self._current_binning,
            'current_width': self._current_width,
            'current_height': self._current_height,
            'image_type': IMAGE_TYPE_NAMES.get(self._current_image_type, 'Unknown'),
        }

    def get_temperature(self) -> Optional[float]:
        """Get camera sensor temperature.

        Returns:
            Temperature in Celsius, or None if not available
        """
        if not self._is_open:
            return None

        try:
            zwoasi = get_zwoasi_module()
            temp = self._camera.get_control_value(zwoasi.ASI_TEMPERATURE)
            # Temperature is returned in 0.1 degree units
            return temp[0] / 10.0
        except Exception:
            return None
