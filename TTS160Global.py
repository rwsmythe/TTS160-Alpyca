# This handles the global instances used by the alpaca driver/app

import threading
from typing import Optional
from logging import Logger
import logging

# Lazy imports to avoid circular dependencies
_TTS160Config = None
_TTS160Device = None
_SerialManager = None
_ServerConfig = None
_TTS160Cache = None
_GPSManager = None
_lock = threading.RLock()

_config_instance = None
_device_instance = None
_serial_instance = None
_serverconfig_instance = None
_cache_instance = None
_gps_instance = None

def get_serverconfig():
    """Get or create the global configuration instance."""
    global _serverconfig_instance, _ServerConfig
    
    if _serverconfig_instance is None:
        with _lock:
            if _serverconfig_instance is None:
                if _ServerConfig is None:
                    import config as _ServerConfig
                _serverconfig_instance = _ServerConfig.Config()
    
    return _serverconfig_instance

def get_config():
    """Get or create the global configuration instance."""
    global _config_instance, _TTS160Config
    
    if _config_instance is None:
        with _lock:
            if _config_instance is None:
                if _TTS160Config is None:
                    import TTS160Config as _TTS160Config
                _config_instance = _TTS160Config.TTS160Config()
    
    return _config_instance

def get_device(logger: Logger):
    """Get or create the global device instance."""
    global _device_instance, _TTS160Device
    
    if _device_instance is None:
        with _lock:
            if _device_instance is None:
                if _TTS160Device is None:
                    import TTS160Device as _TTS160Device
                _device_instance = _TTS160Device.TTS160Device(logger)
    
    return _device_instance

def get_cache():
    """Get or create the global device instance."""
    global _cache_instance, _TTS160Cache
    
    if _cache_instance is None:
        with _lock:
            if _cache_instance is None:
                if _TTS160Cache is None:
                    import tts160_cache as _TTS160Cache
                logger = get_device().logger if _device_instance else logging.getLogger(__name__)
                _cache_instance = _TTS160Cache.TTS160Cache(logger)
    
    return _cache_instance

def reset_cache() -> None:
    """Reset the device instance (for cleanup)."""
    global _cache_instance
    
    with _lock:
        if _cache_instance is not None:
            try:
                _cache_instance.stop_cache_thread()
                _cache_instance = None
            except Exception:
                pass  # Ignore cleanup errors
            _cache_instance = None

def get_serial_manager(logger: Logger) -> Optional[object]:
    """Get or create the global serial manager instance."""
    global _serial_instance, _SerialManager
    
    if _serial_instance is None:
        with _lock:
            if _serial_instance is None:
                if _SerialManager is None:
                    import tts160_serial as _SerialManager
                _serial_instance = _SerialManager.SerialManager(logger)
    
    return _serial_instance

def reset_serial_manager() -> None:
    """Reset the serial manager instance (for cleanup)."""
    global _serial_instance
    
    with _lock:
        if _serial_instance is not None:
            try:
                _serial_instance.cleanup()
            except Exception:
                pass  # Ignore cleanup errors
            _serial_instance = None

def reset_device() -> None:
    """Reset the device instance (for cleanup)."""
    global _device_instance

    with _lock:
        if _device_instance is not None:
            try:
                _device_instance = None
            except Exception:
                pass  # Ignore cleanup errors
            _device_instance = None


def get_gps_manager(logger: Logger) -> Optional[object]:
    """Get or create the global GPS manager instance.

    Args:
        logger: Logger instance for GPS manager operations.

    Returns:
        GPSManager instance or None if GPS is disabled.
    """
    global _gps_instance, _GPSManager

    config = get_config()
    if not config.gps_enabled:
        return None

    if _gps_instance is None:
        with _lock:
            if _gps_instance is None:
                if _GPSManager is None:
                    import gps_manager as _GPSManager
                _gps_instance = _GPSManager.GPSManager(config, logger)

    return _gps_instance


def reset_gps_manager() -> None:
    """Reset the GPS manager instance (for cleanup)."""
    global _gps_instance

    with _lock:
        if _gps_instance is not None:
            try:
                _gps_instance.stop()
            except Exception:
                pass  # Ignore cleanup errors
            _gps_instance = None