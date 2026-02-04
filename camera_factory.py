# -*- coding: utf-8 -*-
"""
Camera Factory

Factory function for creating camera sources based on configuration.
Provides a clean abstraction for camera source selection.
"""

import logging
from typing import Optional

from camera_source import CameraSource
from alpaca_camera import AlpacaCameraSource
from zwo_camera_source import ZWOCameraSource


def create_camera_source(
    config,
    logger: logging.Logger
) -> Optional[CameraSource]:
    """Create a camera source based on configuration.

    Factory function that instantiates the appropriate camera source
    implementation based on the alignment_camera_source configuration.

    Args:
        config: TTS160Config instance with camera settings.
        logger: Logger instance for camera operations.

    Returns:
        CameraSource instance (AlpacaCameraSource or ZWOCameraSource),
        or None if configuration is invalid.

    Configuration Keys:
        alignment_camera_source: 'alpaca' or 'zwo'

        For Alpaca:
            alignment_camera_address: Server IP address
            alignment_camera_port: Server port
            alignment_camera_device: Device number

        For ZWO:
            zwo_camera_id: Camera index
            zwo_gain: Gain setting
            zwo_image_type: Image format
    """
    source_type = getattr(config, 'alignment_camera_source', 'alpaca').lower()

    if source_type == 'zwo':
        # Check if ZWO is available
        if not ZWOCameraSource.is_available():
            logger.warning(
                "ZWO camera source requested but not available. "
                "Check that ZWO SDK is installed. Falling back to Alpaca."
            )
            source_type = 'alpaca'

    if source_type == 'zwo':
        logger.info("Creating ZWO camera source")
        return ZWOCameraSource(
            logger=logger,
            camera_id=getattr(config, 'zwo_camera_id', 0),
            gain=getattr(config, 'zwo_gain', 100),
            image_type=getattr(config, 'zwo_image_type', 'RAW16')
        )

    elif source_type == 'alpaca':
        # Check if Alpaca is available
        if not AlpacaCameraSource.is_available():
            logger.error(
                "Alpaca camera source requested but alpyca library not available. "
                "Install with: pip install alpyca"
            )
            return None

        logger.info("Creating Alpaca camera source")
        return AlpacaCameraSource(
            logger=logger,
            address=getattr(config, 'alignment_camera_address', '127.0.0.1'),
            port=getattr(config, 'alignment_camera_port', 11111),
            device_number=getattr(config, 'alignment_camera_device', 0)
        )

    else:
        logger.error(f"Unknown camera source type: {source_type}")
        return None


def get_available_sources() -> dict:
    """Get available camera source types.

    Returns:
        Dict mapping source type to availability:
        {
            'alpaca': True/False,
            'zwo': True/False
        }
    """
    return {
        'alpaca': AlpacaCameraSource.is_available(),
        'zwo': ZWOCameraSource.is_available(),
    }


def get_source_description(source_type: str) -> str:
    """Get human-readable description of a camera source type.

    Args:
        source_type: 'alpaca' or 'zwo'

    Returns:
        Description string.
    """
    descriptions = {
        'alpaca': 'ASCOM Alpaca Protocol (via alpyca)',
        'zwo': 'Native ZWO ASI (direct SDK)',
    }
    return descriptions.get(source_type.lower(), 'Unknown')
