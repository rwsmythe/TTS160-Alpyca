# -*- coding: utf-8 -*-
"""
Camera Source Abstraction

Abstract interface for camera sources used by the alignment monitor.
Allows switching between Alpaca and ZWO native cameras via configuration.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np


@dataclass
class CaptureResult:
    """Result of a camera capture operation.

    Attributes:
        image: Captured image as NumPy array (height x width)
        width: Image width in pixels
        height: Image height in pixels
        exposure_time: Actual exposure time in seconds
        binning: Binning factor used
        camera_info: Camera-specific information dict
    """
    image: np.ndarray
    width: int
    height: int
    exposure_time: float
    binning: int
    camera_info: Dict[str, Any]


class CameraSource(ABC):
    """Abstract base class for camera sources.

    This interface defines the contract for camera sources used by
    the alignment monitor. Implementations must be thread-safe.

    Concrete implementations:
    - AlpacaCameraSource: Alpaca protocol cameras via alpyca
    - ZWOCameraSource: Native ZWO ASI cameras via zwoasi
    """

    def __init__(self, logger: logging.Logger):
        """Initialize camera source.

        Args:
            logger: Logger instance for camera operations.
        """
        self._logger = logger

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to camera.

        Returns:
            True if connection successful, False otherwise.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Release camera resources.

        This method should be idempotent - calling multiple times is safe.
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if camera is currently connected.

        Returns:
            True if connected and ready for capture, False otherwise.
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """Get camera information for plate solver.

        Returns:
            Dict with camera properties:
            - name: Camera model/identifier
            - pixel_size_um: Pixel size in micrometers
            - sensor_width: Full sensor width in pixels
            - sensor_height: Full sensor height in pixels
            - current_width: Current image width (after binning)
            - current_height: Current image height (after binning)
        """
        pass

    @abstractmethod
    def get_error_message(self) -> str:
        """Get last error message.

        Returns:
            Error message string, empty if no error.
        """
        pass

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Get camera source type identifier.

        Returns:
            Source type string: 'alpaca' or 'zwo'
        """
        pass

    @staticmethod
    def is_available() -> bool:
        """Check if this camera source type is available.

        Returns:
            True if the required libraries are available, False otherwise.

        Note:
            This is a static method that can be called without instantiation.
            Subclasses should override this to check their specific dependencies.
        """
        return False
