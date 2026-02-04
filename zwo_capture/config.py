"""
ZWO Camera Configuration Defaults

Default capture settings optimized for plate solving workflows.
These values provide a good starting point for most use cases.
"""

from typing import Dict, Any


# Default capture settings optimized for plate solving
DEFAULT_CONFIG: Dict[str, Any] = {
    'exposure_ms': 2000,      # 2 second exposure - good for most sky conditions
    'gain': 100,              # Moderate gain - balance between sensitivity and noise
    'binning': 2,             # 2x2 binning - faster readout, smaller files, sufficient for solving
    'image_type': 'RAW16',    # 16-bit for better dynamic range
    'bandwidth': 80,          # USB bandwidth percentage (leave some for other devices)
    'high_speed_mode': False, # Prioritize image quality over transfer speed
    'timeout_ms': 30000,      # 30 second timeout - allows for long exposures + overhead
}


# Image type mapping to ZWO SDK constants
# These values correspond to ASI_IMG_TYPE enum in the SDK
IMAGE_TYPES: Dict[str, int] = {
    'RAW8': 0,    # ASI_IMG_RAW8 - 8-bit raw Bayer pattern
    'RGB24': 1,   # ASI_IMG_RGB24 - 24-bit RGB (debayered)
    'RAW16': 2,   # ASI_IMG_RAW16 - 16-bit raw Bayer pattern
    'Y8': 3,      # ASI_IMG_Y8 - 8-bit luminance (mono or debayered)
}


# Reverse mapping for display purposes
IMAGE_TYPE_NAMES: Dict[int, str] = {v: k for k, v in IMAGE_TYPES.items()}


# Supported binning modes
# Most ZWO cameras support 1x1, 2x2, 3x3, 4x4 binning
# Some cameras may not support all modes - validation should check camera capabilities
SUPPORTED_BINNING = [1, 2, 3, 4]


# Control value ranges (typical, may vary by camera model)
# These are checked against actual camera capabilities at runtime
TYPICAL_RANGES: Dict[str, Dict[str, int]] = {
    'gain': {
        'min': 0,
        'max': 500,
        'default': 100,
    },
    'exposure_ms': {
        'min': 1,           # 1ms minimum (32us actual minimum varies by camera)
        'max': 3600000,     # 1 hour maximum (actual max varies by camera)
        'default': 2000,
    },
    'bandwidth': {
        'min': 40,
        'max': 100,
        'default': 80,
    },
}


def get_default_config() -> Dict[str, Any]:
    """Return a copy of the default configuration.

    Returns:
        Dict with default capture settings.
    """
    return DEFAULT_CONFIG.copy()


def validate_image_type(image_type: str) -> int:
    """Validate and convert image type string to SDK constant.

    Args:
        image_type: Image type name ('RAW8', 'RGB24', 'RAW16', 'Y8')

    Returns:
        SDK image type constant

    Raises:
        ValueError: If image_type is not recognized
    """
    image_type_upper = image_type.upper()
    if image_type_upper not in IMAGE_TYPES:
        valid_types = ', '.join(IMAGE_TYPES.keys())
        raise ValueError(f"Invalid image type '{image_type}'. Valid types: {valid_types}")
    return IMAGE_TYPES[image_type_upper]


def validate_binning(binning: int) -> int:
    """Validate binning value.

    Args:
        binning: Requested binning (1, 2, 3, or 4)

    Returns:
        Validated binning value

    Raises:
        ValueError: If binning is not supported
    """
    if binning not in SUPPORTED_BINNING:
        valid_binning = ', '.join(str(b) for b in SUPPORTED_BINNING)
        raise ValueError(f"Invalid binning {binning}. Supported values: {valid_binning}")
    return binning
