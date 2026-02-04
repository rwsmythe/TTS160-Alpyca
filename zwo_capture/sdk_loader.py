"""
ZWO SDK Loader

Platform-specific SDK library resolution and initialization.
Handles locating the appropriate SDK binary for the current platform
and architecture, with support for bundled, environment-specified,
and system-installed libraries.
"""

import ctypes.util
import logging
import os
import platform
import struct
import sys
from pathlib import Path
from typing import Optional, Tuple

from .exceptions import ZWONotAvailable

logger = logging.getLogger('zwo_capture')

# Module-level state
_sdk_initialized = False
_sdk_path: Optional[str] = None
_zwoasi_module = None


def get_platform_info() -> Tuple[str, str]:
    """Detect current platform and architecture.

    Returns:
        Tuple of (platform, architecture) where:
        - platform: 'windows', 'macos', or 'linux'
        - architecture: 'x64', 'x86', 'armv7', or 'armv8'

    Raises:
        ZWONotAvailable: If platform is not supported
    """
    system = platform.system().lower()

    if system == 'windows':
        plat = 'windows'
        # Check Python interpreter bitness (more reliable than platform.machine on Windows)
        arch = 'x64' if struct.calcsize('P') * 8 == 64 else 'x86'

    elif system == 'darwin':
        plat = 'macos'
        # macOS: Apple Silicon runs x64 code via Rosetta, so we use the same dylib
        arch = 'universal'  # Single dylib works for both

    elif system == 'linux':
        plat = 'linux'
        machine = platform.machine().lower()
        if machine in ('x86_64', 'amd64'):
            arch = 'x64'
        elif machine in ('armv7l', 'armv7'):
            arch = 'armv7'
        elif machine in ('aarch64', 'arm64', 'armv8l', 'armv8'):
            arch = 'armv8'
        elif machine in ('i386', 'i686', 'x86'):
            raise ZWONotAvailable(f"32-bit Linux (x86) is not supported by ZWO SDK")
        else:
            raise ZWONotAvailable(f"Unsupported Linux architecture: {machine}")
    else:
        raise ZWONotAvailable(f"Unsupported platform: {system}")

    logger.debug(f"Detected platform: {plat}, architecture: {arch}")
    return plat, arch


def get_bundled_sdk_path() -> Optional[str]:
    """Get path to bundled SDK library for current platform.

    Returns:
        Path to bundled SDK library, or None if not found
    """
    try:
        plat, arch = get_platform_info()
    except ZWONotAvailable:
        return None

    # Determine package directory (where this file is located)
    package_dir = Path(__file__).parent

    # Build path to SDK binary
    if plat == 'windows':
        sdk_path = package_dir / 'sdk' / 'windows' / arch / 'ASICamera2.dll'
    elif plat == 'macos':
        sdk_path = package_dir / 'sdk' / 'macos' / 'libASICamera2.dylib'
    elif plat == 'linux':
        sdk_path = package_dir / 'sdk' / 'linux' / arch / 'libASICamera2.so'
    else:
        return None

    if sdk_path.exists():
        logger.debug(f"Found bundled SDK at: {sdk_path}")
        return str(sdk_path)

    logger.debug(f"Bundled SDK not found at: {sdk_path}")
    return None


def get_env_sdk_path() -> Optional[str]:
    """Get SDK path from environment variable.

    The ZWO_ASI_LIB environment variable allows users to specify
    a custom SDK library path, overriding bundled and system libraries.

    Returns:
        Path from ZWO_ASI_LIB if set and file exists, None otherwise
    """
    env_path = os.environ.get('ZWO_ASI_LIB')
    if env_path:
        if os.path.isfile(env_path):
            logger.debug(f"Using SDK from environment: {env_path}")
            return env_path
        else:
            logger.warning(f"ZWO_ASI_LIB set but file not found: {env_path}")
    return None


def get_system_sdk_path() -> Optional[str]:
    """Attempt to find SDK in system library paths.

    Returns:
        Path to system SDK library, or None if not found
    """
    # Try to find library using ctypes
    lib_name = 'ASICamera2'

    # On Linux/macOS, ctypes.util.find_library can locate system libraries
    system = platform.system().lower()
    if system in ('linux', 'darwin'):
        found = ctypes.util.find_library(lib_name)
        if found:
            logger.debug(f"Found system SDK: {found}")
            return found

    # On Windows, check common installation paths
    if system == 'windows':
        common_paths = [
            r'C:\Program Files\ASI\ASICamera2.dll',
            r'C:\Program Files (x86)\ASI\ASICamera2.dll',
        ]
        for path in common_paths:
            if os.path.isfile(path):
                logger.debug(f"Found system SDK at: {path}")
                return path

    return None


def get_sdk_path() -> str:
    """Resolve SDK library path using resolution order.

    Resolution order:
    1. ZWO_ASI_LIB environment variable
    2. Bundled SDK in package
    3. System-installed library

    Returns:
        Path to SDK library

    Raises:
        ZWONotAvailable: If SDK cannot be found
    """
    global _sdk_path

    if _sdk_path is not None:
        return _sdk_path

    # Try each source in order
    path = get_env_sdk_path()
    if path:
        _sdk_path = path
        return path

    path = get_bundled_sdk_path()
    if path:
        _sdk_path = path
        return path

    path = get_system_sdk_path()
    if path:
        _sdk_path = path
        return path

    # No SDK found - provide helpful error message
    plat, arch = get_platform_info()
    package_dir = Path(__file__).parent

    if plat == 'windows':
        expected = package_dir / 'sdk' / 'windows' / arch / 'ASICamera2.dll'
    elif plat == 'macos':
        expected = package_dir / 'sdk' / 'macos' / 'libASICamera2.dylib'
    else:
        expected = package_dir / 'sdk' / 'linux' / arch / 'libASICamera2.so'

    raise ZWONotAvailable(
        f"ZWO ASI SDK not found. To use ZWO cameras, either:\n"
        f"  1. Place SDK library at: {expected}\n"
        f"  2. Set ZWO_ASI_LIB environment variable to SDK path\n"
        f"  3. Install SDK in system library path\n"
        f"\n"
        f"Download SDK from: https://www.zwoastro.com/software/"
    )


def initialize_sdk() -> None:
    """Initialize the ZWO ASI SDK.

    This function must be called before any camera operations.
    It locates the SDK library and initializes the zwoasi Python module.

    Raises:
        ZWONotAvailable: If SDK cannot be loaded or initialized
    """
    global _sdk_initialized, _zwoasi_module

    if _sdk_initialized:
        return

    # Get SDK path (raises if not found)
    sdk_path = get_sdk_path()

    # Try to import zwoasi
    try:
        import zwoasi
    except ImportError as e:
        raise ZWONotAvailable(
            f"python-zwoasi library not installed. Install with: pip install zwoasi\n"
            f"Original error: {e}"
        )

    # Initialize with SDK path
    try:
        zwoasi.init(sdk_path)
        _zwoasi_module = zwoasi
        _sdk_initialized = True
        logger.info(f"ZWO SDK initialized from: {sdk_path}")
    except Exception as e:
        error_msg = str(e).lower()

        # Provide platform-specific hints
        if 'quarantine' in error_msg or 'gatekeeper' in error_msg:
            raise ZWONotAvailable(
                f"macOS Gatekeeper blocked SDK loading. Remove quarantine with:\n"
                f"  xattr -d com.apple.quarantine {sdk_path}\n"
                f"\nOriginal error: {e}"
            )
        elif 'libusb' in error_msg:
            raise ZWONotAvailable(
                f"libusb not found. Install with:\n"
                f"  Ubuntu/Debian: sudo apt install libusb-1.0-0\n"
                f"  Fedora/RHEL: sudo dnf install libusb1\n"
                f"  macOS: brew install libusb\n"
                f"\nOriginal error: {e}"
            )
        else:
            raise ZWONotAvailable(f"Failed to initialize ZWO SDK: {e}")


def get_zwoasi_module():
    """Get the initialized zwoasi module.

    Returns:
        The zwoasi module after initialization

    Raises:
        ZWONotAvailable: If SDK is not initialized
    """
    global _zwoasi_module

    if not _sdk_initialized or _zwoasi_module is None:
        initialize_sdk()

    return _zwoasi_module


def is_sdk_available() -> bool:
    """Check if ZWO SDK is available (non-throwing).

    This function attempts to locate and initialize the SDK,
    returning False if any step fails. It's suitable for
    feature detection without exception handling.

    Returns:
        True if SDK is available and initialized, False otherwise
    """
    try:
        initialize_sdk()
        return True
    except ZWONotAvailable:
        return False
    except Exception as e:
        logger.debug(f"SDK availability check failed: {e}")
        return False


def reset_sdk() -> None:
    """Reset SDK state (primarily for testing).

    This function resets the module-level state, allowing
    reinitialization. Useful for testing different SDK paths.
    """
    global _sdk_initialized, _sdk_path, _zwoasi_module

    _sdk_initialized = False
    _sdk_path = None
    _zwoasi_module = None
