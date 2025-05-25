#This handles the global instances used by the alpaca driver/app

import threading
import TTS160Config
import TTS160Device
from logging import Logger

_lock = threading.Lock()

_config_instance = None
_device_instance = None

def get_config():
    global _config_instance
    if _config_instance is None:
        with _lock:
            if _config_instance is None: #redundant double-check after lock
                _config_instance = TTS160Config()
    return _config_instance

def get_device(logger: Logger):
    global _device_instance
    if _device_instance is None:
        with _lock:
            if _device_instance is None: #redundant double-check after lock
                _device_instance = TTS160Device(Logger)
    return _device_instance