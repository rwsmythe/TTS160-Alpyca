"""
ZWO Camera Capture Module

A clean, minimal Python interface for ZWO ASI camera capture,
optimized for plate solving workflows in the TTS160 Alpaca Driver.

Example usage:
    >>> from zwo_capture import ZWOCamera, is_available, list_cameras
    >>>
    >>> # Check if ZWO support is available
    >>> if is_available():
    ...     cameras = list_cameras()
    ...     print(f"Found {len(cameras)} camera(s)")
    ...
    ...     # Capture image for plate solving
    ...     with ZWOCamera(camera_id=0) as cam:
    ...         cam.configure(exposure_ms=2000, gain=100, binning=2)
    ...         image = cam.capture()
    ...         info = cam.get_camera_info()
"""

import logging
from typing import Any, Dict, List

from .camera import ZWOCamera
from .exceptions import (
    ZWOCameraError,
    ZWOConfigurationError,
    ZWOError,
    ZWONotAvailable,
    ZWOTimeoutError,
)
from .sdk_loader import get_zwoasi_module, initialize_sdk, is_sdk_available

logger = logging.getLogger('zwo_capture')


def is_available() -> bool:
    """Check if ZWO camera support is available.

    This is a non-throwing function suitable for feature detection.
    It checks if the SDK can be loaded, but does NOT check for
    connected cameras.

    Returns:
        True if SDK is available and initialized, False otherwise

    Example:
        >>> if is_available():
        ...     cameras = list_cameras()
        ... else:
        ...     print("ZWO camera support not available")
    """
    return is_sdk_available()


def list_cameras() -> List[Dict[str, Any]]:
    """List all connected ZWO cameras.

    Returns:
        List of dicts containing camera information:
        - id: Camera index (use this for ZWOCamera constructor)
        - name: Camera model name
        - serial: Serial number (if available)

        Returns empty list if no cameras are connected.

    Raises:
        ZWONotAvailable: If SDK cannot be loaded

    Example:
        >>> cameras = list_cameras()
        >>> for cam in cameras:
        ...     print(f"{cam['id']}: {cam['name']}")
    """
    # This will raise ZWONotAvailable if SDK can't be loaded
    initialize_sdk()
    zwoasi = get_zwoasi_module()

    num_cameras = zwoasi.get_num_cameras()
    if num_cameras == 0:
        return []

    cameras = []
    for i in range(num_cameras):
        try:
            # Get camera info without fully opening it
            info = zwoasi.get_camera_property(i)
            cameras.append({
                'id': i,
                'name': info.get('Name', f'Camera {i}'),
                'serial': info.get('SerialNumber', ''),
            })
        except Exception as e:
            logger.warning(f"Failed to get info for camera {i}: {e}")
            cameras.append({
                'id': i,
                'name': f'Camera {i}',
                'serial': '',
            })

    return cameras


def get_camera_count() -> int:
    """Get the number of connected ZWO cameras.

    Returns:
        Number of connected cameras, or 0 if SDK not available

    This is a convenience function that doesn't raise exceptions.
    """
    try:
        initialize_sdk()
        zwoasi = get_zwoasi_module()
        return zwoasi.get_num_cameras()
    except Exception:
        return 0


__all__ = [
    # Main camera class
    'ZWOCamera',

    # Utility functions
    'is_available',
    'list_cameras',
    'get_camera_count',

    # Exceptions
    'ZWOError',
    'ZWONotAvailable',
    'ZWOCameraError',
    'ZWOTimeoutError',
    'ZWOConfigurationError',
]

__version__ = '1.0.0'
