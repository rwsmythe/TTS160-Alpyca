"""
TTS160 Cache Module

Provides cached access to telescope properties to prevent GUI blocking during
high-frequency ALPACA operations. Maintains a thread-safe cache that is updated
both by ALPACA operations and a background refresh thread.
"""

import time
import threading
from typing import Dict, Any, Optional
import TTS160Global

# Configuration constants
CACHE_STALENESS_THRESHOLD = 5.0  # seconds
BACKGROUND_UPDATE_RATE = 2.0     # Hz (updates per second)
UPDATE_INTERVAL = 1.0 / BACKGROUND_UPDATE_RATE  # 0.5 seconds

# Properties to cache (high-frequency changing properties)
CACHED_PROPERTIES = [
    # Position and movement
    'RightAscension', 'Declination',
    'Altitude', 'Azimuth', 
    'Tracking', 'Slewing', 'AtPark', 'AtHome',
    'SideOfPier', 'TargetRightAscension', 'TargetDeclination',
    
    # Time and guiding
    'UTCDate', 'SiderealTime',
    'GuideRateRightAscension', 'GuideRateDeclination',
    'IsPulseGuiding',
    
    # Site information (low frequency but hardware-dependent)
    'SiteElevation', 'SiteLatitude', 'SiteLongitude',
    
]


class TTS160Cache:
    """Thread-safe cache for telescope properties."""
    
    def __init__(self, logger):
        """Initialize cache.
        
        Args:
            logger: Logger instance for error reporting
        """
        self.logger = logger
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._device = None
        
    def start_cache_thread(self):
        """Start the background cache update thread."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                self.logger.warning("Cache thread already running")
                return
                
            try:
                self._device = TTS160Global.get_device(self.logger)
                if not self._device:
                    self.logger.error("Failed to get device instance for cache")
                    return
                    
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._background_update, 
                    name='TTS160Cache', 
                    daemon=True
                )
                self._thread.start()
                self.logger.info("TTS160 cache thread started")
                
            except Exception as e:
                self.logger.error(f"Failed to start cache thread: {e}")
    
    def stop_cache_thread(self):
        """Stop the background cache update thread."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                self.logger.info("Stopping cache thread...")
                self._stop_event.set()
                self._thread.join(timeout=3.0)
                
                if self._thread.is_alive():
                    self.logger.warning("Cache thread did not stop gracefully")
                else:
                    self.logger.info("TTS160 cache thread stopped")
                    
            self._thread = None
            self._device = None
    
    def update_property(self, property_name: str, value: Any):
        """Update a cached property value (called by ALPACA operations).
        
        Args:
            property_name: Name of the telescope property
            value: Current value of the property
        """
        if not isinstance(property_name, str) or property_name not in CACHED_PROPERTIES:
            return
            
        with self._lock:
            self._cache[property_name] = {
                'value': value,
                'timestamp': time.time(),
                'error': None
            }
            
        self.logger.debug(f"Cache updated by ALPACA: {property_name} = {value}")
    
    def get_property(self, property_name: str) -> Optional[Dict[str, Any]]:
        """Get cached property entry.
        
        Args:
            property_name: Name of the telescope property
            
        Returns:
            Dictionary with 'value', 'timestamp', and 'error' keys
            Returns None if property not in cache
        """
        with self._lock:
            return self._cache.get(property_name)
    
    def get_property_value(self, property_name: str, default=None):
        """Get just the value of a cached property.
        
        Args:
            property_name: Name of the telescope property
            default: Default value if property not cached or has error
            
        Returns:
            Property value or default
        """
        entry = self.get_property(property_name)
        if entry and entry.get('error') is None:
            return entry['value']
        return default
    
    def is_property_stale(self, property_name: str) -> bool:
        """Check if a cached property is stale.
        
        Args:
            property_name: Name of the telescope property
            
        Returns:
            True if property is stale or not cached
        """
        entry = self.get_property(property_name)
        if not entry:
            return True
        
        age = time.time() - entry['timestamp']
        return age > CACHE_STALENESS_THRESHOLD
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Get overall cache status for debugging.
        
        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            total_props = len(CACHED_PROPERTIES)
            cached_props = len(self._cache)
            stale_props = sum(1 for prop in CACHED_PROPERTIES 
                            if self.is_property_stale(prop))
            error_props = sum(1 for entry in self._cache.values() 
                            if entry.get('error') is not None)
            
            connected = False
            try:
                connected = self._device.Connected if self._device else False
            except Exception:
                pass
            
            return {
                'total_properties': total_props,
                'cached_properties': cached_props,
                'stale_properties': stale_props,
                'error_properties': error_props,
                'thread_running': self._thread and self._thread.is_alive(),
                'connected': connected
            }
    
    def clear_cache(self):
        """Clear all cached values."""
        with self._lock:
            self._cache.clear()
            self.logger.info("Cache cleared")
    
    def _background_update(self):
        """Background thread function to update stale cache entries."""
        self.logger.info("TTS160 cache background update thread started")
        
        property_index = 0
        last_update_time = time.time()
        
        while not self._stop_event.is_set():
            try:
                current_time = time.time()
                
                # Check if device is still connected
                if not self._is_device_connected():
                    self.logger.info("Device disconnected, stopping cache thread")
                    break
                
                # Rate limiting - ensure we don't update too frequently
                time_since_last = current_time - last_update_time
                if time_since_last < UPDATE_INTERVAL:
                    sleep_time = UPDATE_INTERVAL - time_since_last
                    if self._stop_event.wait(sleep_time):
                        break
                    continue
                
                # Get next property to check (round-robin)
                if property_index >= len(CACHED_PROPERTIES):
                    property_index = 0
                
                property_name = CACHED_PROPERTIES[property_index]
                property_index += 1
                
                # Update if stale
                if self.is_property_stale(property_name):
                    self._update_single_property(property_name)
                
                last_update_time = time.time()
                
            except Exception as e:
                self.logger.error(f"Error in cache background update: {e}")
                # Wait longer on error to avoid spam
                if self._stop_event.wait(2.0):
                    break
        
        self.logger.info("TTS160 cache background update thread stopped")
    
    def _is_device_connected(self) -> bool:
        """Check if device is connected safely.
        
        Returns:
            True if device is connected, False otherwise
        """
        try:
            return self._device and self._device.Connected
        except Exception as e:
            self.logger.debug(f"Error checking device connection: {e}")
            return False
    
    def _update_single_property(self, property_name: str):
        """Update a single property from the device.
        
        Args:
            property_name: Name of the telescope property to update
        """
        if not self._is_device_connected():
            return
            
        try:
            # Verify property exists on device
            if not hasattr(self._device, property_name):
                self.logger.warning(f"Property {property_name} not found on device")
                return
            
            # Get current value from device
            value = getattr(self._device, property_name)
            
            with self._lock:
                self._cache[property_name] = {
                    'value': value,
                    'timestamp': time.time(),
                    'error': None
                }
            
            self.logger.debug(f"Cache background update: {property_name} = {value}")
                
        except Exception as e:
            self.logger.debug(f"Error updating {property_name}: {e}")
            
            with self._lock:
                # Preserve old value if it exists, update error and timestamp
                if property_name in self._cache:
                    self._cache[property_name]['error'] = str(e)
                    self._cache[property_name]['timestamp'] = time.time()
                else:
                    # No previous value, create entry with error
                    self._cache[property_name] = {
                        'value': None,
                        'timestamp': time.time(),
                        'error': str(e)
                    }


def start_cache_thread():
    """Start the cache background thread.
    
    This is intended to be called from the Connect method in TTS160Device.
    """
    import TTS160Global
    cache = TTS160Global.get_cache()
    cache.start_cache_thread()


def stop_cache_thread():
    """Stop the cache background thread.
    
    This is intended to be called from the Disconnect method in TTS160Device.
    """
    import TTS160Global
    cache = TTS160Global.get_cache()
    if cache:
        cache.stop_cache_thread()


def update_cache_property(property_name: str, value: Any):
    """Update a cached property value (convenience function for ALPACA operations).
    
    Args:
        property_name: Name of the telescope property
        value: Current value of the property
    """
    import TTS160Global
    cache = TTS160Global.get_cache()
    if cache:
        cache.update_property(property_name, value)


def get_cached_property_value(property_name: str, default=None):
    """Get cached property value (convenience function for GUI).
    
    Args:
        property_name: Name of the telescope property
        default: Default value if property not cached or has error
        
    Returns:
        Property value or default
    """
    import TTS160Global
    cache = TTS160Global.get_cache()
    if cache:
        return cache.get_property_value(property_name, default)
    return default