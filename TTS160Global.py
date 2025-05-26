# This handles the global instances used by the alpaca driver/app

import threading
from typing import Optional
from logging import Logger

# Lazy imports to avoid circular dependencies
_TTS160Config = None
_TTS160Device = None
_SerialManager = None

_lock = threading.RLock()

_config_instance = None
_device_instance = None
_serial_instance = None

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