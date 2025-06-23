# File: TTS160Device.py
"""Complete TTS160 Device Hardware Implementation."""

import threading
import time
import math
import bisect
from fractions import Fraction
from datetime import datetime, timezone, timedelta
from dateutil import parser
from typing import List, Tuple, Any, Union, Optional
from logging import Logger
from concurrent.futures import ThreadPoolExecutor, Future

# AstroPy imports for coordinate transformations
from astropy.coordinates import SkyCoord, AltAz, ICRS, EarthLocation, GCRS
from astropy.time import Time
from astropy import units as u
from astropy.utils import iers

# Local imports
from tts160_types import CommandType
#from exceptions import (
#    DriverException, InvalidValueException, InvalidOperationException,
#    NotImplementedException, ParkedException, NotConnectedException
#)
from telescope import (
    TelescopeMetadata, EquatorialCoordinateType, DriveRates, PierSide,
    AlignmentModes, TelescopeAxes, GuideDirections, Rate
)

"""
AstroPy Coordinate Frame Caching Mixin

Provides efficient caching of expensive astropy coordinate frame objects
with time-to-live (TTL) expiration and timing-critical operation support.
"""
class AstropyCachingMixin:
    """
    Mixin providing cached astropy coordinate frames with TTL and timing optimization.
    
    This mixin caches expensive astropy coordinate frame objects (AltAz, GCRS) to
    improve performance during frequent coordinate transformations. Frames are cached
    with a configurable time-to-live (TTL) and automatically refreshed when expired.
    
    Special support is provided for timing-critical operations (e.g., pulse guiding)
    where cache refresh can be deferred to avoid delays during time-sensitive calculations.
    
    Dependencies (must be provided by inheriting class):
        - self._site_location: EarthLocation object for telescope site
        - self._lock: threading.RLock for thread safety
        - self._logger: Logger instance for debug/info logging
    
    Thread Safety:
        All cache operations are protected by self._lock to ensure thread-safe
        access in multi-threaded telescope control environments.
    
    Performance Characteristics:
        - Fresh frame access: ~1-5ms (cached lookup)
        - Expired frame refresh: ~50-100ms (astropy calculation)
        - Timing-critical access: ~1-5ms (uses stale cache if needed)
    
    Example:
        class TelescopeDevice(AstropyCachingMixin):
            def coordinate_conversion(self):
                # Normal usage - refreshes cache if expired
                altaz_frame = self._altaz_frame
                
            def timing_critical_operation(self):
                # Fast usage - defers refresh if needed
                refresh_needed = self._check_cache_freshness(['altaz'])
                altaz_frame = self._altaz_frame  # Uses cached (possibly stale)
                # ... perform time-critical work ...
                if refresh_needed:
                    self._refresh_expired_caches(refresh_needed)
    """
    
    # Cache configuration constants
    FRAME_CACHE_TTL: float = 10.0  # seconds
    
    def __init__(self, *args, **kwargs):
        """
        Initialize caching infrastructure.
        
        Note: This is a mixin, so it calls super().__init__() to ensure
        proper multiple inheritance initialization chain.
        """
        super().__init__(*args, **kwargs)

        try:
            iers.IERS_Auto.open()  # Trigger download attempt
        except Exception as e:
            self._logger.info(f"IERS data download failed: {e}")
            # Continue with cached/default data
        
        # Cache storage attributes will be created on-demand
        # No need to initialize them here as they're managed by properties
    
    def _get_frame_cache(self, frame_type: str, timing_critical: bool = False) -> Union[AltAz, GCRS]:
        """
        Retrieve cached coordinate frame with optional timing optimization.
        
        Returns a cached astropy coordinate frame, creating or refreshing it as needed.
        In timing-critical mode, will return stale cache rather than blocking for refresh.
        
        Args:
            frame_type: Type of frame to retrieve ('altaz' or 'gcrs')
            timing_critical: If True, use stale cache to avoid delays
            
        Returns:
            Cached astropy coordinate frame object
            
        Raises:
            ValueError: If frame_type is not supported
            AttributeError: If required dependencies not available
            
        Thread Safety:
            Method is thread-safe via self._lock protection
        """
        if not hasattr(self, '_lock'):
            raise AttributeError("AstropyCachingMixin requires self._lock from inheriting class")
        
        with self._lock:
            cache_attr = f'_{frame_type}_cache'
            time_attr = f'_{frame_type}_time'
            
            # Check if cache exists and determine freshness
            cache_exists = hasattr(self, cache_attr)
            if cache_exists:
                cache_time = getattr(self, time_attr, 0)
                is_stale = time.time() - cache_time > self.FRAME_CACHE_TTL
                
                if hasattr(self, '_logger'):
                    age_seconds = time.time() - cache_time
                    self._logger.debug(f"Frame cache '{frame_type}' age: {age_seconds:.1f}s, stale: {is_stale}")
            else:
                is_stale = True
                if hasattr(self, '_logger'):
                    self._logger.debug(f"Frame cache '{frame_type}' does not exist, creating initial cache")
            
            # Handle timing-critical operations
            if timing_critical and cache_exists:
                if is_stale:
                    if hasattr(self, '_logger'):
                        self._logger.debug(f"Timing-critical: using stale {frame_type} cache to avoid delays")
                else:
                    if hasattr(self, '_logger'):
                        self._logger.debug(f"Timing-critical: using fresh {frame_type} cache")
                return getattr(self, cache_attr)
            
            # Refresh cache if stale or non-existent
            if is_stale:
                try:
                    frame = self._create_frame(frame_type)
                    setattr(self, cache_attr, frame)
                    setattr(self, time_attr, time.time())
                    
                    if hasattr(self, '_logger'):
                        action = "refreshed" if cache_exists else "created"
                        self._logger.info(f"Frame cache '{frame_type}' {action} successfully")
                        
                except Exception as ex:
                    if hasattr(self, '_logger'):
                        self._logger.error(f"Failed to create {frame_type} frame: {ex}")
                    raise
            
            return getattr(self, cache_attr)
    
    def _create_frame(self, frame_type: str) -> Union[AltAz, GCRS]:
        """
        Create new astropy coordinate frame object.
        
        Factory method for creating fresh coordinate frame instances with current time.
        
        Args:
            frame_type: Type of frame to create ('altaz' or 'gcrs')
            
        Returns:
            New astropy coordinate frame object
            
        Raises:
            ValueError: If frame_type is not supported
            AttributeError: If required dependencies not available
        """
        current_time = Time.now()
        
        if frame_type == 'altaz':
            if not hasattr(self, '_site_location'):
                raise AttributeError("AstropyCachingMixin requires self._site_location from inheriting class")
            
            frame = AltAz(obstime=current_time, location=self._site_location)
            
            if hasattr(self, '_logger'):
                self._logger.debug(f"Created AltAz frame: time={current_time.iso}, "
                                 f"site=({self._site_location.lat.deg:.3f}°, {self._site_location.lon.deg:.3f}°)")
            
        elif frame_type == 'gcrs':
            frame = GCRS(obstime=current_time)
            
            if hasattr(self, '_logger'):
                self._logger.debug(f"Created GCRS frame: time={current_time.iso}")
        else:
            raise ValueError(f"Unsupported frame type: {frame_type}. Supported: 'altaz', 'gcrs'")
        
        return frame
    
    def _check_cache_freshness(self, frame_types: List[str]) -> List[str]:
        """
        Check which caches need refresh without triggering refresh.
        
        Examines cache timestamps to determine which frames are stale and need
        refreshing. Used by timing-critical operations to identify refresh work
        that should be deferred until after time-sensitive operations complete.
        
        Args:
            frame_types: List of frame types to check ('altaz', 'gcrs')
            
        Returns:
            List of frame types that need refresh (subset of input list)
            
        Thread Safety:
            Method is thread-safe via self._lock protection
        """
        if not hasattr(self, '_lock'):
            raise AttributeError("AstropyCachingMixin requires self._lock from inheriting class")
        
        refresh_needed = []
        
        with self._lock:
            for frame_type in frame_types:
                cache_attr = f'_{frame_type}_cache'
                time_attr = f'_{frame_type}_time'
                
                if not hasattr(self, cache_attr):
                    refresh_needed.append(frame_type)
                    if hasattr(self, '_logger'):
                        self._logger.debug(f"Cache freshness check: {frame_type} cache missing")
                else:
                    cache_time = getattr(self, time_attr, 0)
                    age = time.time() - cache_time
                    if age > self.FRAME_CACHE_TTL:
                        refresh_needed.append(frame_type)
                        if hasattr(self, '_logger'):
                            self._logger.debug(f"Cache freshness check: {frame_type} cache stale ({age:.1f}s old)")
        
        if hasattr(self, '_logger') and refresh_needed:
            self._logger.debug(f"Cache freshness check: {len(refresh_needed)} caches need refresh: {refresh_needed}")
        
        return refresh_needed
    
    def _refresh_expired_caches(self, frame_types: List[str]) -> None:
        """
        Refresh specified coordinate frame caches.
        
        Updates cached coordinate frames with current time. Typically called after
        timing-critical operations complete to refresh any caches that were stale
        but used to avoid delays.
        
        Args:
            frame_types: List of frame types to refresh ('altaz', 'gcrs')
            
        Raises:
            ValueError: If unsupported frame type specified
            AttributeError: If required dependencies not available
            
        Thread Safety:
            Method is thread-safe via self._lock protection
            
        Performance:
            This method may take 50-100ms per frame type due to astropy calculations.
            Should not be called during timing-critical operations.
        """
        if not frame_types:
            return
        
        if hasattr(self, '_logger'):
            self._logger.info(f"Refreshing {len(frame_types)} expired coordinate frame caches: {frame_types}")
        
        for frame_type in frame_types:
            try:
                # Force refresh by calling _get_frame_cache with stale cache
                self._invalidate_cache(frame_type)
                self._get_frame_cache(frame_type, timing_critical=False)
                
                if hasattr(self, '_logger'):
                    self._logger.debug(f"Successfully refreshed {frame_type} cache")
                    
            except Exception as ex:
                if hasattr(self, '_logger'):
                    self._logger.error(f"Failed to refresh {frame_type} cache: {ex}")
                # Continue trying other caches even if one fails
        
        if hasattr(self, '_logger'):
            self._logger.info("Coordinate frame cache refresh completed")
    
    def _invalidate_cache(self, frame_type: str) -> None:
        """
        Force invalidation of specific coordinate frame cache.
        
        Removes cached frame and timestamp, forcing recreation on next access.
        Used when cache needs to be updated due to configuration changes
        (e.g., site location updates) rather than just TTL expiration.
        
        Args:
            frame_type: Type of frame to invalidate ('altaz', 'gcrs')
            
        Thread Safety:
            Method is thread-safe via self._lock protection
        """
        if not hasattr(self, '_lock'):
            raise AttributeError("AstropyCachingMixin requires self._lock from inheriting class")
        
        with self._lock:
            cache_attr = f'_{frame_type}_cache'
            time_attr = f'_{frame_type}_time'
            
            if hasattr(self, cache_attr):
                delattr(self, cache_attr)
                if hasattr(self, '_logger'):
                    self._logger.debug(f"Invalidated {frame_type} cache")
            
            if hasattr(self, time_attr):
                delattr(self, time_attr)
    
    def _invalidate_all_caches(self) -> None:
        """
        Force invalidation of all coordinate frame caches.
        
        Removes all cached frames and timestamps. Useful when fundamental
        configuration changes occur (e.g., site location updates) that
        affect multiple frame types.
        
        Thread Safety:
            Method is thread-safe via self._lock protection
        """
        frame_types = ['altaz', 'gcrs']
        
        if hasattr(self, '_logger'):
            self._logger.info("Invalidating all coordinate frame caches")
        
        for frame_type in frame_types:
            self._invalidate_cache(frame_type)
        
        if hasattr(self, '_logger'):
            self._logger.debug("All coordinate frame caches invalidated")
    
    @property
    def _altaz_frame(self) -> AltAz:
        """
        Cached AltAz coordinate frame for current site and time.
        
        Returns a cached AltAz frame object, refreshing if expired (>TTL seconds old).
        This frame includes the current observation time and telescope site location,
        making it suitable for coordinate transformations to/from horizontal coordinates.
        
        Returns:
            AltAz: Cached coordinate frame object
            
        Raises:
            AttributeError: If required dependencies not available
            
        Performance:
            - Cache hit: ~1-5ms
            - Cache miss/refresh: ~50-100ms (due to astropy calculations)
        """
        return self._get_frame_cache('altaz', timing_critical=False)
    
    @property  
    def _gcrs_frame(self) -> GCRS:
        """
        Cached GCRS coordinate frame for current time.
        
        Returns a cached GCRS (Geocentric Celestial Reference System) frame object,
        refreshing if expired (>TTL seconds old). This frame represents the current
        epoch for topocentric equatorial coordinate transformations.
        
        Returns:
            GCRS: Cached coordinate frame object
            
        Raises:
            AttributeError: If required dependencies not available
            
        Performance:
            - Cache hit: ~1-5ms  
            - Cache miss/refresh: ~50-100ms (due to astropy calculations)
        """
        return self._get_frame_cache('gcrs', timing_critical=False)

class CapabilitiesMixin:
    # Capability Properties
    @property
    def CanFindHome(self) -> bool:
        """Mount can find its home position."""
        return self._CanFindHome

    @property
    def CanPark(self) -> bool:
        """Mount can be parked."""
        return self._CanPark

    @property
    def CanPulseGuide(self) -> bool:
        """Mount can be pulse guided."""
        return self._CanPulseGuide

    @property
    def CanSetPierSide(self) -> bool:
        """Mount can be force-flipped via setting SideOfPier."""
        return self._CanSetPierSide

    @property
    def CanSetTracking(self) -> bool:
        """Mount's sidereal tracking may be turned on and off."""
        return self._CanSetTracking

    @property
    def CanSlew(self) -> bool:
        """Mount can slew to equatorial coordinates (synchronous)."""
        return self._CanSlew

    @property
    def CanSlewAltAz(self) -> bool:
        """Mount can slew to alt/az coordinates (synchronous)."""
        return self._CanSlewAltAz

    @property
    def CanSlewAltAzAsync(self) -> bool:
        """Mount can slew to alt/az coordinates asynchronously."""
        return self._CanSlewAltAzAsync

    @property
    def CanSlewAsync(self) -> bool:
        """Mount can slew to equatorial coordinates asynchronously."""
        return self._CanSlewAsync
    
    def CanMoveAxis(self, axis: TelescopeAxes) -> bool:
        """
        Determine if mount can be moved about the specified axis.
        
        Args:
            axis: Telescope axis to check (Primary, Secondary, or Tertiary)
            
        Returns:
            bool: True if axis movement supported, False otherwise
            
        Raises:
            InvalidValueException: If invalid axis value specified
            NotConnectedException: If device not connected
            DriverException: If axis capability check fails
        """
        try:
            self._logger.debug(f"Checking movement capability for axis: {axis}")
            
            if axis in [TelescopeAxes.axisPrimary, TelescopeAxes.axisSecondary]:
                result = self._CanMoveAxis
                self._logger.debug(f"Axis {axis} movement capability: {result}")
                return result
            else:
                self._logger.debug(f"Axis {axis} movement not supported (tertiary axis)")
                return False
                
        except Exception as ex:
            self._logger.error(f"Failed to check axis {axis} capability: {ex}")
            raise RuntimeError(f"Axis capability check failed", ex)
    
    @property
    def CanSetDeclinationRate(self) -> bool:
        """Declination tracking rate may be offset."""
        return self._CanSetDeclinationRate

    @property
    def CanSetRightAscensionRate(self) -> bool:
        """Right Ascension tracking rate may be offset."""
        return self._CanSetRightAscensionRate

    @property
    def CanSetPark(self) -> bool:
        """Mount's park position can be set."""
        return self._CanSetPark

    @property
    def CanSetGuideRates(self) -> bool:
        """Guiding rates for PulseGuide() can be adjusted."""
        return self._CanSetGuideRates

    def AxisRates(self, axis: TelescopeAxes) -> List[Rate]:
        """
        Get angular rates at which mount may be moved about specified axis.
        
        Args:
            axis: Telescope axis for rate inquiry (Primary, Secondary, or Tertiary)
            
        Returns:
            List[Rate]: Available rate objects with min/max angular rates (deg/sec)
                    Empty list if axis movement not supported
            
        Raises:
            InvalidValueException: If invalid axis value specified
            NotConnectedException: If device not connected
            DriverException: If rate retrieval fails
        """
        try:
            if not self.Connected:
                raise ConnectionError("Not Connected")
            
            self._logger.debug(f"Retrieving available rates for axis: {axis}")
            
            if axis in [TelescopeAxes.axisPrimary, TelescopeAxes.axisSecondary]:
                rates = self._AxisRates
                self._logger.debug(f"Axis {axis} available rates: {len(rates)} rate ranges")
                for i, rate in enumerate(rates):
                    self._logger.debug(f"  Rate {i}: {rate.Minimum}-{rate.Maximum} deg/sec")
                return rates
            else:
                self._logger.debug(f"Axis {axis} movement not supported, returning empty rate list")
                return []
                
        except Exception as ex:
            self._logger.error(f"Failed to retrieve rates for axis {axis}: {ex}")
            raise RuntimeError(f"Axis rates retrieval failed", ex)
    
    @property
    def CanSync(self) -> bool:
        """Mount can be synchronized to equatorial coordinates."""
        return self._CanSync

    @property
    def CanSyncAltAz(self) -> bool:
        """Mount can be synchronized to alt/az coordinates."""
        return self._CanSyncAltAz

    @property
    def CanUnpark(self) -> bool:
        """Mount can be unparked."""
        return self._CanUnpark

    @property
    def TrackingRates(self) -> List[DriveRates]:
        """
        Return list of supported tracking rate values.
        
        Returns:
            List[DriveRates]: Available tracking rates (minimum includes sidereal)
            
        Raises:
            NotConnectedException: If device not connected
            DriverException: If tracking rates retrieval fails
        """
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        try:
            self._logger.debug("Retrieving available tracking rates")
            rates = self._DriveRates
            self._logger.debug(f"Available tracking rates: {[rate.name for rate in rates]}")
            return rates
            
        except Exception as ex:
            self._logger.error(f"Failed to retrieve tracking rates: {ex}")
            raise RuntimeError(f"Tracking rates retrieval failed", ex)

    # Static Properties  
    @property
    def Name(self) -> str:
        return self._Name
    
    @property
    def Description(self) -> str:
        return self._Description
    
    @property
    def DriverVersion(self) -> str:
        return self._DriverVersion

    @property
    def DriverInfo(self) -> List[str]:
        return List[ f"{self._DriverInfo}" ]

    @property
    def InterfaceVersion(self) -> int:
        return self.__InterfaceVersion
    
    @property
    def SupportedActions(self) -> List[str]:
        
        supported_actions: List[str] = [ "FieldRotationAngle" ]
        
        return supported_actions
    
    @property
    def AlignmentMode(self) -> AlignmentModes:
        """
        The current mount alignment mode geometry.
        
        Returns:
            AlignmentModes: Mount alignment type (Alt-Az, Polar, German Polar)
            
        Raises:
            NotImplementedException: If mount cannot report alignment mode
            NotConnectedException: If device not connected
            DriverException: If alignment mode retrieval fails
        """
        try:
            self._logger.debug("Retrieving mount alignment mode")
            alignment = AlignmentModes.algAltAz
            self._logger.debug(f"Mount alignment mode: {alignment}")
            return alignment
            
        except Exception as ex:
            self._logger.error(f"Failed to retrieve alignment mode: {ex}")
            raise RuntimeError(f"Alignment mode retrieval failed", ex)
            
class ConfigurationMixin:
    @property
    def SlewSettleTime(self) -> int:
        
        if not self.Connected:
            raise ConnectionError("Device not connected")

        return self._config.slew_settle_time
    
    @SlewSettleTime.setter
    def SlewSettleTime(self, value: int) -> None:
        
        if not self.Connected:
            raise ConnectionError("Device not connected")

         
        if not (0 <= value <= 30):
            raise ValueError(f"Invalid Slew Settle Time: {value}, value not saved.")

        try:        
            with self._lock:
                self._config.slew_settle_time = value

        except Exception as ex:
            raise RuntimeError("SlewSettleTime assignment failed", ex)
    
    def _update_site_location(self) -> None:
        """
        Update AstroPy site location from configuration values.
        
        Initializes the internal EarthLocation object used for coordinate transformations
        by reading latitude, longitude, and elevation from the configuration. Falls back
        to origin coordinates (0,0,0) if configuration values are invalid or missing.
        
        The site location is critical for accurate coordinate transformations between
        equatorial and horizontal coordinate systems.
        
        Side Effects:
            - Updates self._site_location with new EarthLocation instance
            - Logs successful configuration loading or fallback usage
            
        Raises:
            AttributeError: If configuration object is not properly initialized
            
        Note:
            - Missing or None config values default to 0.0
            - Invalid numeric values trigger fallback to origin coordinates
            - Does not raise exceptions for invalid coordinate values to ensure robustness
        """
        try:
            self._logger.debug("Updating site location from configuration")
            
            # Extract coordinates from configuration with safe defaults
            try:
                lat = float(self._config.site_latitude) if self._config.site_latitude else 0.0
                lon = float(self._config.site_longitude) if self._config.site_longitude else 0.0 
                elev = float(self._config.site_elevation) if self._config.site_elevation else 0.0
                
                self._logger.debug(f"Configuration values - Lat: {lat}°, Lon: {lon}°, Elev: {elev}m")
                
            except (ValueError, TypeError) as ex:
                self._logger.warning(f"Invalid coordinate values in configuration: {ex}")
                lat = lon = elev = 0.0
            
            # Validate coordinate ranges (warn but don't fail)
            if not (-90 <= lat <= 90):
                self._logger.warning(f"Latitude {lat}° outside valid range ±90°, using anyway")
            if not (-180 <= lon <= 180):
                self._logger.warning(f"Longitude {lon}° outside valid range ±180°, using anyway")
            if elev < -500:  # Below typical ocean depths
                self._logger.warning(f"Elevation {elev}m seems unusually low")
            
            # Create AstroPy EarthLocation object
            self._site_location = EarthLocation(
                lat=lat * u.deg,
                lon=lon * u.deg,
                height=elev * u.m
            )
            
            self._logger.info(f"Site location updated: {lat:.6f}°, {lon:.6f}°, {elev:.1f}m")
            
            self._invalidate_cache('altaz')

        except (ValueError, TypeError) as ex:
            # Fallback to origin coordinates for any conversion failures
            self._logger.error(f"Site location update failed, using origin coordinates: {ex}")
            self._site_location = EarthLocation(
                lat=0.0 * u.deg,
                lon=0.0 * u.deg,
                height=0.0 * u.m
            )
            self._logger.warning("Site location set to origin (0°, 0°, 0m) - coordinate transformations may be inaccurate")
            
        except AttributeError as ex:
            # Configuration object not properly initialized
            self._logger.error(f"Configuration object not available for site location: {ex}")
            raise  # Re-raise as this indicates a serious initialization problem

# Coordinate Conversion Utilities           
class CoordinateUtilsMixin:
    
    def _dms_to_degrees(self, dms_str: str) -> float:
        """
        Convert DMS (Degrees:Minutes:Seconds) string to decimal degrees.
        
        Supports LX200 coordinate formats including both standard and extended precision.
        Handles various separators and sign conventions per LX200 ICD specification.
        
        Args:
            dms_str: DMS string in formats like "+45*30'15#", "-12:34:56", "123*45"
            
        Returns:
            float: Decimal degrees, positive or negative based on input sign
            
        Raises:
            InvalidValueException: If string format is invalid or unparseable
            ValueError: If numeric conversion fails
            
        Examples:
            "+45*30'15#" -> 45.504167
            "-12:34:56" -> -12.582222
            "90*00" -> 90.0
        """
        if not isinstance(dms_str, str):
            raise TypeError(f"DMS input must be string, got {type(dms_str)}")
        
        if not dms_str.strip():
            raise ValueError("DMS string cannot be empty")
        
        try:
            
            # Clean string and extract sign
            cleaned = dms_str.rstrip('#').strip()
            self._logger.debug(f"Converting DMS string: '{dms_str}' -> '{cleaned}'")
            
            sign = -1 if cleaned.startswith('-') else 1
            cleaned = cleaned.lstrip('+-')
            
            # Split by common LX200 separators
            parts = cleaned.replace('*', ':').replace("'", ':').replace('"', ':').split(':')
            
            if len(parts) < 1 or len(parts) > 3:
                raise ValueError(f"Invalid DMS format: expected 1-3 parts, got {len(parts)}")
            
            # Convert parts to float with validation
            try:
                degrees = float(parts[0])
                minutes = float(parts[1]) if len(parts) > 1 else 0.0
                seconds = float(parts[2]) if len(parts) > 2 else 0.0
            except ValueError as ex:
                raise ValueError(f"Invalid numeric values in DMS string '{dms_str}': {ex}")
            
            # Validate ranges
            if degrees < 0:
                raise ValueError(f"Degrees component cannot be negative in '{dms_str}' (use leading sign)")
            if not (0 <= minutes < 60):
                raise ValueError(f"Minutes {minutes} outside valid range 0-59")
            if not (0 <= seconds < 60):
                raise ValueError(f"Seconds {seconds} outside valid range 0-59")
            
            result = sign * (degrees + minutes/60.0 + seconds/3600.0)
            self._logger.debug(f"DMS conversion result: {result:.6f}°")
            return result
            
        except ValueError:
            self._logger.error(f"DMS conversion failed: {dms_str}")
            raise
        except Exception as ex:
            self._logger.error(f"Unexpected error in DMS conversion '{dms_str}': {ex}")
            raise RuntimeError(f"Invalid DMS format: {dms_str}")

    def _hms_to_hours(self, hms_str: str) -> float:
        """
        Convert HMS (Hours:Minutes:Seconds) string to decimal hours.
        
        Supports LX200 time and right ascension formats per ICD specification.
        
        Args:
            hms_str: HMS string like "14:32:45#", "23:59:59", "0:0:0"
            
        Returns:
            float: Decimal hours (0.0 to 24.0)
            
        Raises:
            InvalidValueException: If string format invalid or values out of range
            
        Examples:
            "14:32:45#" -> 14.545833
            "23:59:59" -> 23.999722
            "12:30" -> 12.5
        """
        if not isinstance(hms_str, str):
            raise TypeError(f"HMS input must be string, got {type(hms_str)}")
            
        if not hms_str.strip():
            raise ValueError("HMS string cannot be empty")
        
        try:
            
            # Clean string
            cleaned = hms_str.rstrip('#').strip()
            self._logger.debug(f"Converting HMS string: '{hms_str}' -> '{cleaned}'")
            
            parts = cleaned.split(':')
            if len(parts) < 1 or len(parts) > 3:
                raise ValueError(f"Invalid HMS format: expected 1-3 parts, got {len(parts)}")
            
            try:
                hours = float(parts[0])
                minutes = float(parts[1]) if len(parts) > 1 else 0.0
                seconds = float(parts[2]) if len(parts) > 2 else 0.0
            except ValueError as ex:
                raise ValueError(f"Invalid numeric values in HMS string '{hms_str}': {ex}")
            
            # Validate ranges
            if not (0 <= hours < 24):
                raise ValueError(f"Hours {hours} outside valid range 0-23")
            if not (0 <= minutes < 60):
                raise ValueError(f"Minutes {minutes} outside valid range 0-59")
            if not (0 <= seconds < 60):
                raise ValueError(f"Seconds {seconds} outside valid range 0-59")
            
            result = hours + minutes/60.0 + seconds/3600.0
            self._logger.debug(f"HMS conversion result: {result:.6f}h")
            return result
            
        except ValueError:
            self._logger.error(f"HMS conversion failed: {hms_str}")
            raise
        except Exception as ex:
            self._logger.error(f"Unexpected error in HMS conversion '{hms_str}': {ex}")
            raise RuntimeError(f"Invalid HMS format: {hms_str}")

    def _degrees_to_dms(self, degrees: float, deg_sep: str = "*", min_sep: str = ":") -> str:
        """
        Convert decimal degrees to DMS string format.
        
        Args:
            degrees: Decimal degrees
            deg_sep: Separator after degrees (default "*" for LX200)
            min_sep: Separator after minutes (default ":" for LX200)
            
        Returns:
            str: DMS string like "+45*30:15.0"
            
        Raises:
            ValueError: If degrees is not a valid number
        """
        try:
            if not isinstance(degrees, (int, float)):
                raise ValueError(f"Degrees must be numeric, got {type(degrees)}")
            
            if math.isnan(degrees) or math.isinf(degrees):
                raise ValueError(f"Degrees cannot be NaN or infinite: {degrees}")
            
            sign = "-" if degrees < 0 else "+"
            degrees = abs(degrees)
            
            deg = int(degrees)
            minutes = (degrees - deg) * 60
            min_val = int(minutes)
            seconds = (minutes - min_val) * 60
            
            result = f"{sign}{deg:02d}{deg_sep}{min_val:02d}{min_sep}{seconds:04.1f}"
            self._logger.debug(f"Degrees {degrees:.6f}° -> DMS '{result}'")
            return result
            
        except Exception as ex:
            self._logger.error(f"Degrees to DMS conversion failed: {ex}")
            raise

    def _hours_to_hms(self, hours: float) -> str:
        """
        Convert decimal hours to HMS string format.
        
        Args:
            hours: Decimal hours
            
        Returns:
            str: HMS string like "14:32:45.0"
            
        Raises:
            ValueError: If hours is not a valid number
        """
        try:
            if not isinstance(hours, (int, float)):
                raise ValueError(f"Hours must be numeric, got {type(hours)}")
            
            if math.isnan(hours) or math.isinf(hours):
                raise ValueError(f"Hours cannot be NaN or infinite: {hours}")
            
            # Normalize to 0-24 range
            hours = hours % 24
            
            h = int(hours)
            minutes = (hours - h) * 60
            m = int(minutes)
            seconds = (minutes - m) * 60
            
            result = f"{h:02d}:{m:02d}:{seconds:04.1f}"
            self._logger.debug(f"Hours {hours:.6f}h -> HMS '{result}'")
            return result
            
        except Exception as ex:
            self._logger.error(f"Hours to HMS conversion failed: {ex}")
            raise
    
    def _altaz_to_icrs(self, azimuth: float, altitude: float) -> Tuple[float, float]:
        """
        Convert Alt/Az coordinates to J2000 ICRS RA/Dec.
        
        Args:
            azimuth: Azimuth in decimal degrees (0-360)
            altitude: Altitude in decimal degrees (-90 to +90)
            
        Returns:
            Tuple of (right_ascension_hours, declination_degrees)
            
        Raises:
            InvalidValueException: Invalid coordinate values
            DriverException: Coordinate transformation failure
        """
        try:
            # Validate inputs
            self._validate_coordinates(alt = altitude, az = azimuth)
                
            # Create AltAz coordinate at current time
            altaz_frame = self._altaz_frame
            altaz_coord = SkyCoord(
                az=azimuth * u.deg,
                alt=altitude * u.deg,
                frame=altaz_frame
            )
            
            # Transform to ICRS (J2000)
            icrs_coord = altaz_coord.transform_to(ICRS())
            
            return icrs_coord.ra.hour, icrs_coord.dec.degree
            
        except Exception as ex:
            if isinstance(ex, ValueError):
                raise
            raise RuntimeError(f"Alt/Az to ICRS conversion failed", ex)

    def _icrs_to_altaz(self, right_ascension: float, declination: float) -> Tuple[float, float]:
        """
        Convert J2000 ICRS RA/Dec to Alt/Az coordinates.
        
        Args:
            right_ascension: Right ascension in decimal hours (0-24)
            declination: Declination in decimal degrees (-90 to +90)
            
        Returns:
            Tuple of (azimuth_degrees, altitude_degrees)
            
        Raises:
            InvalidValueException: Invalid coordinate values
            DriverException: Coordinate transformation failure
        """
        try:
            # Validate inputs
            self._validate_coordinates(ra = right_ascension, dec = declination)
                
            # Create ICRS coordinate
            icrs_coord = SkyCoord(
                ra=right_ascension * u.hour,
                dec=declination * u.deg,
                frame=ICRS()
            )
            
            # Transform to AltAz at current time
            altaz_frame = self._altaz_frame
            altaz_coord = icrs_coord.transform_to(altaz_frame)
            
            # Normalize azimuth to 0-360 range
            azimuth = altaz_coord.az.degree
            if azimuth < 0:
                azimuth += 360
            elif azimuth >= 360:
                azimuth -= 360
                
            return azimuth, altaz_coord.alt.degree
            
        except Exception as ex:
            if isinstance(ex, ValueError):
                raise
            raise RuntimeError(f"ICRS to Alt/Az conversion failed", ex)

    def _altaz_to_gcrs(self, azimuth: float, altitude: float) -> Tuple[float, float]:
        """
        Convert Alt/Az coordinates to topocentric equatorial GCRS RA/Dec (current epoch).
        
        Args:
            azimuth: Azimuth in decimal degrees (0-360)
            altitude: Altitude in decimal degrees (-90 to +90)
            
        Returns:
            Tuple of (right_ascension_hours, declination_degrees)
            
        Raises:
            InvalidValueException: Invalid coordinate values
            DriverException: Coordinate transformation failure
        """
        try:
            # Validate inputs
            self._validate_coordinates(alt = altitude, az = azimuth)
                
            # Create AltAz coordinate at current time
            altaz_frame = self._altaz_frame
            altaz_coord = SkyCoord(
                az=azimuth * u.deg,
                alt=altitude * u.deg,
                frame=altaz_frame
            )
            
            # Transform to GCRS at current time (topocentric equatorial)
            gcrs_coord = altaz_coord.transform_to(self._gcrs_frame)
            
            return gcrs_coord.ra.hour, gcrs_coord.dec.degree
            
        except Exception as ex:
            if isinstance(ex, ValueError):
                raise
            raise RuntimeError(f"Alt/Az to GCRS conversion failed", ex)

    def _gcrs_to_altaz(self, right_ascension: float, declination: float) -> Tuple[float, float]:
        """
        Convert topocentric equatorial GCRS RA/Dec (current epoch) to Alt/Az coordinates.
        
        Args:
            right_ascension: Right ascension in decimal hours (0-24)
            declination: Declination in decimal degrees (-90 to +90)
            
        Returns:
            Tuple of (azimuth_degrees, altitude_degrees)
            
        Raises:
            InvalidValueException: Invalid coordinate values
            DriverException: Coordinate transformation failure
        """
        try:
            # Validate inputs
            self._validate_coordinates(ra = right_ascension, dec = declination)
                
            # Create GCRS coordinate at current time
            gcrs_coord = SkyCoord(
                ra=right_ascension * u.hour,
                dec=declination * u.deg,
                frame=self._gcrs_frame
            )
            
            # Transform to AltAz
            altaz_frame = self._altaz_frame
            altaz_coord = gcrs_coord.transform_to(altaz_frame)
            
            # Normalize azimuth to 0-360 range
            azimuth = altaz_coord.az.degree
            if azimuth < 0:
                azimuth += 360
            elif azimuth >= 360:
                azimuth -= 360
                
            return azimuth, altaz_coord.alt.degree
            
        except Exception as ex:
            if isinstance(ex, ValueError):
                raise
            raise RuntimeError(f"GCRS to Alt/Az conversion failed", ex)

    def _icrs_to_gcrs(self, right_ascension: float, declination: float) -> Tuple[float, float]:
        """
        Convert J2000 ICRS RA/Dec to topocentric equatorial GCRS RA/Dec (current epoch).
        
        Accounts for precession, nutation, and other time-dependent effects.
        
        Args:
            right_ascension: Right ascension in decimal hours (0-24)
            declination: Declination in decimal degrees (-90 to +90)
            
        Returns:
            Tuple of (right_ascension_hours, declination_degrees)
            
        Raises:
            InvalidValueException: Invalid coordinate values
            DriverException: Coordinate transformation failure
        """
        try:
            # Validate inputs
            self._validate_coordinates(ra = right_ascension, dec = declination)
                
            # Create ICRS coordinate (J2000)
            icrs_coord = SkyCoord(
                ra=right_ascension * u.hour,
                dec=declination * u.deg,
                frame=ICRS()
            )
            
            # Transform to GCRS at current time
            gcrs_coord = icrs_coord.transform_to(self._gcrs_frame)
            
            # Normalize RA to 0-24 hour range
            ra_hours = gcrs_coord.ra.hour
            if ra_hours < 0:
                ra_hours += 24
            elif ra_hours >= 24:
                ra_hours -= 24
                
            return ra_hours, gcrs_coord.dec.degree
            
        except Exception as ex:
            if isinstance(ex, ValueError):
                raise
            raise RuntimeError(f"ICRS to GCRS conversion failed", ex)

    def _gcrs_to_icrs(self, right_ascension: float, declination: float) -> Tuple[float, float]:
        """
        Convert topocentric equatorial GCRS RA/Dec (current epoch) to J2000 ICRS RA/Dec.
        
        Removes precession, nutation, and other time-dependent effects.
        
        Args:
            right_ascension: Right ascension in decimal hours (0-24)
            declination: Declination in decimal degrees (-90 to +90)
            
        Returns:
            Tuple of (right_ascension_hours, declination_degrees)
            
        Raises:
            InvalidValueException: Invalid coordinate values
            DriverException: Coordinate transformation failure
        """
        try:
            # Validate inputs
            self._validate_coordinates(ra = right_ascension, dec = declination)
                
            # Create GCRS coordinate at current time
            gcrs_coord = SkyCoord(
                ra=right_ascension * u.hour,
                dec=declination * u.deg,
                frame=self._gcrs_frame
            )
            
            # Transform to ICRS (J2000)
            icrs_coord = gcrs_coord.transform_to(ICRS())
            
            # Normalize RA to 0-24 hour range
            ra_hours = icrs_coord.ra.hour
            if ra_hours < 0:
                ra_hours += 24
            elif ra_hours >= 24:
                ra_hours -= 24
                
            return ra_hours, icrs_coord.dec.degree
            
        except Exception as ex:
            if isinstance(ex, ValueError):
                raise
            raise RuntimeError(f"GCRS to ICRS conversion failed", ex)
    
    def _calculate_sidereal_time(self, time: datetime = None) -> float:
        """
        Calculate local apparent sidereal time using AstroPy.
        
        Args:
            time: UTC datetime for calculation (defaults to current time)
            
        Returns:
            float: Local sidereal time in hours (0-24)
            
        Raises:
            DriverException: If calculation fails
            ValueError: If time parameter invalid
        """
        try:
            if time is None:
                time = datetime.now(timezone.utc)
                
            if not isinstance(time, datetime):
                raise ValueError(f"Time must be datetime object, got {type(time)}")
            
            self._logger.debug(f"Calculating sidereal time for {time}")
            
            # Convert to AstroPy Time object
            astro_time = Time(time)
            
            # Get Greenwich Mean Sidereal Time
            gmst = astro_time.sidereal_time('mean', 'greenwich').hour
            
            # Convert to local sidereal time
            longitude_hours = self._site_location.lon.degree / 15.0
            lst = (gmst + longitude_hours) % 24
            
            self._logger.debug(f"Calculated LST: {lst:.6f}h (GMST: {gmst:.6f}h, Lon: {longitude_hours:.6f}h)")
            return lst
            
        except Exception as ex:
            self._logger.error(f"Sidereal time calculation failed: {ex}")
            raise RuntimeError("Sidereal time calculation failed", ex)

    def _calculate_hour_angle(self, right_ascension: float, time: datetime = None) -> float:
        """
        Calculate hour angle for given right ascension.
        
        Args:
            right_ascension: RA in decimal hours (0-24)
            time: UTC datetime for calculation (defaults to current time)
            
        Returns:
            float: Hour angle in hours (-12 to +12)
            
        Raises:
            InvalidValueException: If RA outside valid range
            DriverException: If calculation fails
        """
        try:
            self._validate_coordinates(ra = right_ascension)
            
            self._logger.debug(f"Calculating hour angle for RA {right_ascension:.3f}h")
            
            lst = self._calculate_sidereal_time(time)
            ha = lst - right_ascension
            
            # Condition to -12 to +12 hours
            ha = self._condition_ha(ha)
            
            self._logger.debug(f"Hour angle: {ha:.3f}h (LST: {lst:.3f}h, RA: {right_ascension:.3f}h)")
            return ha
            
        except ValueError:
            self._logger.error(f"Hour angle calculation failed: invalid RA {right_ascension}")
            raise
        except Exception as ex:
            self._logger.error(f"Hour angle calculation failed: {ex}")
            raise RuntimeError("Hour angle calculation failed", ex)

    def _condition_ha(self, ha: float) -> float:
        """
        Condition hour angle to standard range -12.0 to +12.0 hours.
        
        Args:
            ha: Hour angle in hours
            
        Returns:
            float: Conditioned hour angle (-12.0 to +12.0)
            
        Raises:
            ValueError: If ha is not a valid number
        """
        try:
            if not isinstance(ha, (int, float)):
                raise ValueError(f"Hour angle must be numeric, got {type(ha)}")
            
            if math.isnan(ha) or math.isinf(ha):
                raise ValueError(f"Hour angle cannot be NaN or infinite: {ha}")
            
            # Normalize to 0-24 range first
            ha = ha % 24.0
            
            # Convert to -12 to +12 range
            if ha > 12.0:
                ha -= 24.0
            
            self._logger.debug(f"Conditioned hour angle: {ha:.6f}h")
            return ha
            
        except Exception as ex:
            self._logger.error(f"Hour angle conditioning failed: {ex}")
            raise

    def _validate_coordinates(self, ra: Optional[float] = None, dec: Optional[float] = None, 
                         alt: Optional[float] = None, az: Optional[float] = None) -> None:
        """
        Validate coordinate values against their valid ranges.
        
        Args:
            ra: Right ascension in hours (0-24), optional
            dec: Declination in degrees (-90 to +90), optional  
            alt: Altitude in degrees (-90 to +90), optional
            az: Azimuth in degrees (0-360), optional
            
        Raises:
            InvalidValueException: If any coordinate outside valid range
            TypeError: If coordinate is not numeric
        """
        try:
            if ra is not None:
                if not isinstance(ra, (int, float)) or math.isnan(ra) or math.isinf(ra):
                    raise ValueError(f"Right ascension must be valid number, got {ra}")
                if not (0 <= ra <= 24):
                    raise ValueError(f"Right ascension {ra} outside valid range 0-24 hours")
            
            if dec is not None:
                if not isinstance(dec, (int, float)) or math.isnan(dec) or math.isinf(dec):
                    raise ValueError(f"Declination must be valid number, got {dec}")
                if not (-90 <= dec <= 90):
                    raise ValueError(f"Declination {dec} outside valid range ±90 degrees")
            
            if alt is not None:
                if not isinstance(alt, (int, float)) or math.isnan(alt) or math.isinf(alt):
                    raise ValueError(f"Altitude must be valid number, got {alt}")
                if not (0 <= alt <= 90):
                    raise ValueError(f"Altitude {alt} outside valid range ±90 degrees")
            
            if az is not None:
                if not isinstance(az, (int, float)) or math.isnan(az) or math.isinf(az):
                    raise ValueError(f"Azimuth must be valid number, got {az}")
                if not (0 <= az <= 360):
                    raise ValueError(f"Azimuth {az} outside valid range 0-360 degrees")
                    
        except Exception as ex:
            self._logger.error(f"Coordinate validation failed: {ex}")
            raise

class TTS160Device(AstropyCachingMixin, CapabilitiesMixin, ConfigurationMixin, CoordinateUtilsMixin):
    """Complete TTS160 Hardware Implementation with ASCOM compliance."""
    
    # Hardware constants
    ENCODER_TICKS_PRIMARY_AXIS = 13033502.0
    ENCODER_TICKS_SECONDARY_AXIS = 13146621.0
    HOME_POSITION_TOLERANCE_ALT = 2.0
    HOME_POSITION_TOLERANCE_AZ = 5.0
    MAX_ALTITUDE_FOR_COMPENSATION = 89.0

    def __init__(self, logger: Logger) -> None:
        """
        Initialize the TTS160 Device Hardware Implementation.
        
        Creates a new TTS160Device instance with ASCOM-compliant telescope interface.
        Initializes all internal state variables, communication interfaces, and 
        hardware-specific constants required for mount operation.
        
        Args:
            logger (Logger): Python logger instance for recording device operations
                and debugging information. Must be a valid logging.Logger instance.
        
        Raises:
            TypeError: If logger is not a valid Logger instance
            DriverException: If global configuration or serial manager initialization fails
            ImportError: If required TTS160Global module cannot be imported
        
        Note:
            - Device is initialized in disconnected state
            - Site location defaults to (0,0,0) if configuration unavailable
            - Thread pool uses 10 workers for asynchronous operations
            - All ASCOM capability flags are set per TTS160 hardware specifications
            - Coordinate frame caching initialized for performance optimization
        """
        # Input validation
        if not isinstance(logger, Logger):
            raise TypeError(f"logger must be a Logger instance, got {type(logger)}")
        
        self._logger = logger
        self._logger.info("Initializing TTS160Device instance")
        
        try:
            # Thread safety and async execution setup
            self._lock = threading.RLock()
            self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="TTS160")
            self._logger.debug("Thread pool and locking initialized")
            
            # Initialize mixin chain (must occur after _lock and _logger setup)
            super().__init__()
            self._logger.debug("Mixin initialization chain completed")

            # Global configuration and serial manager setup
            self._setup_global_objects()
            
            # Connection state initialization
            self._Connecting = False
            self._Connected = False
            self._logger.debug("Connection state initialized to disconnected")
            
            # Static device metadata (ASCOM required properties)
            self._Name = TelescopeMetadata.Name
            self._DriverVersion = TelescopeMetadata.Version
            self._DriverInfo = TelescopeMetadata.Info
            self._InterfaceVersion = TelescopeMetadata.InterfaceVersion
            self._Description = TelescopeMetadata.Description
            self._logger.debug(f"Device metadata: {self._Name} v{self._DriverVersion}")
            
            # ASCOM capability flags (read-only, hardware-specific)
            self._initialize_capability_flags()
            
            # Mount operational state
            self._initialize_mount_state()
            
            # Target coordinate state
            #self._initialize_target_state()
            
            # Site location for coordinate transformations
            self._site_location = None
            try:
                self._update_site_location()
                self._logger.debug("Site location initialized from configuration")
            except Exception as ex:
                self._logger.warning(f"Site location initialization failed, using defaults: {ex}")
            
            # Hardware-specific constants and operational parameters
            self._initialize_hardware_constants()
            
            self._logger.info("TTS160Device initialization completed successfully")
            
        except Exception as ex:
            self._logger.error(f"TTS160Device initialization failed: {ex}")
            # Cleanup any partially initialized resources
            self._cleanup_initialization()
            raise
    
    def _setup_global_objects(self) -> None:
        """
        Initialize global configuration and serial manager objects.
        
        Loads the global configuration and instantiates the serial manager required
        for telescope communication. These objects are shared across the application
        and provide core functionality for device operation.
        
        This method must be called after _lock and _logger initialization since
        the caching mixin and other components depend on these global objects.
        
        Side Effects:
            - Sets self._config with application configuration
            - Sets self._serial_manager with communication interface
            - Logs successful initialization or detailed error information
        
        Raises:
            DriverException: If TTS160Global module unavailable or initialization fails
            ImportError: If required TTS160Global module cannot be imported
            
        Note:
            Global objects are shared across application instances and provide
            centralized configuration and communication management.
        """
        try:
            self._logger.debug("Loading TTS160Global module")
            import TTS160Global
            
            # Initialize configuration object
            try:
                self._logger.debug("Retrieving global configuration")
                self._config = TTS160Global.get_config()
                self._logger.info("Global configuration loaded successfully")
            except Exception as ex:
                self._logger.error(f"Failed to load global configuration: {ex}")
                raise RuntimeError("Configuration initialization failed", ex)
            
            # Initialize serial manager
            try:
                self._logger.debug("Instantiating serial manager")
                self._serial_manager = TTS160Global.get_serial_manager(self._logger)
                self._logger.info("Serial manager instantiated successfully")
            except Exception as ex:
                self._logger.error(f"Serial manager instantiation failed: {ex}")
                raise RuntimeError("Serial manager initialization failed", ex)
            
            # Verify global objects are properly initialized
            if self._config is None:
                raise RuntimeError("Configuration object is None after initialization")
            
            if self._serial_manager is None:
                raise RuntimeError("Serial manager is None after initialization")
            
            self._logger.debug("Global objects validation completed successfully")
            
        except ImportError as ex:
            self._logger.error(f"TTS160Global module import failed: {ex}")
            raise RuntimeError("TTS160Global module unavailable", ex)
            
        except Exception as ex:
            # Wrap unexpected exceptions
            self._logger.error(f"Unexpected error during global objects setup: {ex}")
            raise RuntimeError("Global objects setup failed", ex)

    def _initialize_capability_flags(self) -> None:
        """Initialize ASCOM capability flags per TTS160 hardware specifications."""
        self._CanFindHome = True
        self._CanMoveAxis = True
        self._CanPark = True
        self._CanPulseGuide = True
        self._CanSetDeclinationRate = True
        self._CanSetGuideRates = True
        self._CanSetPark = False
        self._CanSetPierSide = False
        self._CanSetRightAscensionRate = True
        self._CanSetTracking = True
        self._CanSlew = False
        self._CanSlewAltAz = False
        self._CanSlewAltAzAsync = True
        self._CanSlewAsync = True
        self._CanSync = True
        self._CanSyncAltAz = True
        self._CanUnpark = False
        self._logger.debug("ASCOM capability flags initialized")

    def _initialize_mount_state(self) -> None:
        """Initialize mount operational state variables."""
        self._slew_in_progress = None
        self._is_parked = False
        self._is_at_home = False
        self._tracking = False
        self._goto_in_progress = False
        self._slewing_hold = False
        self._rightascensionrate = 0.0
        self._declinationrate = 0.0
        self._logger.debug("Mount state variables initialized")

    def _initialize_hardware_constants(self) -> None:
        """Initialize TTS160-specific hardware constants and operational parameters."""
        # Axis rate specifications
        self._AxisRates = [Rate(0.0, 3.5)]
        self._DriveRates = [DriveRates.driveSidereal, DriveRates.driveLunar, DriveRates.driveSolar]
        
        # MoveAxis calculation constants
        self._TICKS_PER_DEGREE = {
            TelescopeAxes.axisPrimary: self.ENCODER_TICKS_PRIMARY_AXIS / 360.0,    # H axis
            TelescopeAxes.axisSecondary: self.ENCODER_TICKS_SECONDARY_AXIS / 360.0   # E axis
        }
        self._TICKS_PER_PULSE = 7.0
        self._CLOCK_FREQ = 57600
        self._MAX_RATE = max(rate.Maximum for rate in self._AxisRates)
        
        # LX200 command mappings for axis control
        self._AXIS_COMMANDS = {
            TelescopeAxes.axisPrimary: {
                'stop': ':Qe#', 'pos': ':*Me', 'neg': ':*Mw', 'name': 'Primary'
            },
            TelescopeAxes.axisSecondary: {
                'stop': ':Qn#', 'pos': ':*Mn', 'neg': ':*Ms', 'name': 'Secondary'
            }
        }
        
        self._sync_wait_time = 0.5

        self._logger.debug("Hardware constants and command mappings initialized")

    def _cleanup_initialization(self) -> None:
        """Clean up any partially initialized resources on initialization failure."""
        try:
            if hasattr(self, '_executor') and self._executor:
                self._executor.shutdown(wait=False)
                self._logger.debug("Thread pool executor shutdown during cleanup")
        except Exception as ex:
            self._logger.warning(f"Error during initialization cleanup: {ex}")
        
        try:
            if hasattr(self, '_serial_manager') and self._serial_manager:
                self._serial_manager.cleanup()
                self._logger.debug("Serial manager cleanup during initialization failure")
        except Exception as ex:
            self._logger.warning(f"Error cleaning up serial manager: {ex}")

    #Cached variables
    @property
    def _site_location(self):
        if not hasattr(self, '_site_location_cache'):
            with self._lock:
                # Double-check pattern
                if not hasattr(self, '_site_location_cache'):
                    self._site_location_cache = EarthLocation(
                        lat=self._config.site_latitude * u.deg,
                        lon=self._config.site_longitude * u.deg, 
                        height=self._config.site_elevation * u.m
                    )
        return self._site_location_cache
    
    @_site_location.setter
    def _site_location(self, value):
        with self._lock:
            self._site_location_cache = value

    def __del__(self) -> None:
        """
        Clean up TTS160Device resources during garbage collection.
        
        Ensures proper shutdown of thread pools and serial connections when the
        device instance is being destroyed. This prevents resource leaks and
        ensures clean disconnection from hardware.
        
        Note:
            - Called automatically during garbage collection
            - Should not raise exceptions to avoid issues during interpreter shutdown
            - Logging may not be available during late-stage garbage collection
        """
        try:
            # Safely log cleanup attempt if logger is still available
            if hasattr(self, '_logger') and self._logger:
                self._logger.debug("TTS160Device cleanup initiated during garbage collection")
        except (AttributeError, ReferenceError):
            # Logger may be unavailable during shutdown - continue cleanup silently
            pass
        
        # Clean up thread pool executor
        try:
            if hasattr(self, '_executor') and self._executor:
                self._executor.shutdown(wait=True)
                if hasattr(self, '_logger') and self._logger:
                    self._logger.debug("Thread pool executor shutdown completed")
        except (AttributeError, ReferenceError, RuntimeError) as ex:
            # Expected during interpreter shutdown - log if possible, otherwise continue
            try:
                if hasattr(self, '_logger') and self._logger:
                    self._logger.warning(f"Thread pool shutdown warning during cleanup: {ex}")
            except:
                pass
        
        # Clean up serial manager connection
        try:
            if hasattr(self, '_serial_manager') and self._serial_manager:
                self._serial_manager.cleanup()
                if hasattr(self, '_logger') and self._logger:
                    self._logger.debug("Serial manager cleanup completed")
        except (AttributeError, ReferenceError, RuntimeError) as ex:
            # Expected during interpreter shutdown - log if possible, otherwise continue
            try:
                if hasattr(self, '_logger') and self._logger:
                    self._logger.warning(f"Serial manager cleanup warning: {ex}")
            except:
                pass
        
        try:
            if hasattr(self, '_logger') and self._logger:
                self._logger.debug("TTS160Device cleanup completed successfully")
        except:
            # Final logging attempt - ignore all errors during shutdown
            pass

    # Connection Management
    def Connect(self) -> None:
        """
        Connect to the TTS160 mount asynchronously.
        
        Initiates non-blocking connection to mount hardware following ASCOM Platform 7
        semantics with shared connection reference counting.
        
        Connection States:
            - Already connected: Increments reference count, returns immediately
            - Connection in progress: Increments reference count, returns immediately  
            - Disconnected: Starts async connection, sets Connecting=True
        
        Raises:
            DriverException: Connection initialization fails or resources unavailable
            AttributeError: Required configuration/serial manager not initialized
            RuntimeError: Thread pool shutdown or unavailable
            
        Note:
            Monitor completion via Connecting property transitioning False→True→False
        """
        # Validate prerequisites
        if not hasattr(self, '_config') or self._config is None:
            self._logger.error("Connect failed: Configuration not initialized")
            raise RuntimeError("Configuration not available for connection")
        
        if not hasattr(self, '_serial_manager') or self._serial_manager is None:
            self._logger.error("Connect failed: Serial manager not initialized, trying to reinitialize.") 
            raise RuntimeError("Serial manager not available for connection")
        
        if not hasattr(self, '_executor') or self._executor is None:
            self._logger.error("Connect failed: Thread executor not initialized")
            raise RuntimeError("Thread executor not available for connection")
        
        with self._lock:
            # Handle already connected (ASCOM shared connection pattern)
            if self._Connected:
                self._serial_manager.connection_count += 1
                self._logger.info(f"Already connected, reference count: {self._serial_manager.connection_count}")
                return
            
            # Handle connection in progress
            if self._Connecting:
                self._serial_manager.connection_count += 1
                self._logger.info(f"Connection already in progress, reference count: {self._serial_manager.connection_count}")
                return

            # Start new connection
            with self._lock:
                self._Connecting = True
                self._Connected = False
            self._logger.info("Starting asynchronous TTS160 mount connection")
            
        try:
            # Reload configuration (continue on failure)
            try:
                self._config.reload()
                self._logger.debug("Configuration reloaded successfully")
            except Exception as ex:
                self._logger.warning(f"Configuration reload failed, using existing values: {ex}")
            
            # Submit connection task to thread pool
            try:
                self._executor.submit(self._perform_mount_connection)
                self._logger.debug("Connection task submitted to thread pool")
            except RuntimeError as ex:
                with self._lock:
                    self._Connecting = False
                self._logger.error("Thread pool unavailable for connection")
                raise RuntimeError("Thread pool shutdown, cannot connect", ex)
            
            self._logger.info("Async connection process initiated successfully")

        #except DriverException:
        #    with self._lock:
        #        self._Connecting = False
        #    raise
            
        except (AttributeError, RuntimeError) as ex:
            with self._lock:
                self._Connecting = False
            self._logger.error(f"Connection setup failed: {ex}")
            raise RuntimeError("Connection initialization failed", ex)
            
        except Exception as ex:
            with self._lock:
                self._Connecting = False
            self._logger.error(f"Unexpected connection error: {ex}")
            raise RuntimeError("Unexpected connection failure", ex)

    def _perform_mount_connection(self) -> None:
        """
        Perform synchronous mount connection in background thread.
        
        Handles physical serial connection, mount initialization, and state updates.
        Called asynchronously by Connect() via thread pool executor.
        
        Side Effects:
            - Establishes serial communication with mount
            - Updates connection state flags
            - Initializes mount hardware and settings
            
        Raises:
            DriverException: If connection or initialization fails
            ImportError: If TTS160Global module unavailable
            SerialException: If serial communication fails
        """
        try:
            self._logger.debug("Beginning mount connection procedure")
            
            # Ensure serial manager is available
            try:
                import TTS160Global
                if not self._serial_manager:
                    self._serial_manager = TTS160Global.get_serial_manager(self._logger)
                    self._logger.debug("Serial manager reinitialized")
            except ImportError as ex:
                self._logger.error("TTS160Global module import failed during connection")
                raise RuntimeError("TTS160Global module unavailable", ex)

            # Establish serial connection
            try:
                self._serial_manager.connect(self._config.dev_port)
                self._logger.info(f"Serial connection established on {self._config.dev_port}")
            except Exception as ex:
                self._logger.error(f"Serial connection failed on {self._config.dev_port}: {ex}")
                raise RuntimeError(f"Serial connection failed", ex)
            
            # Initialize mount hardware and settings
            self._initialize_connected_mount()
            
            # Update connection state
            with self._lock:
                self._Connected = True
                self._Connecting = False
                
            self._logger.info("TTS160 mount connection completed successfully")
            
        except Exception as ex:
            # Cleanup and wrap unexpected exceptions
            with self._lock:
                self._Connecting = False
                self._Connected = False
            self._logger.error(f"Mount connection failed with unexpected error: {ex}")
            raise RuntimeError("Mount connection failed", ex)

    def _initialize_connected_mount(self) -> None:
        """
        Initialize mount after successful connection.
        
        Retrieves mount information, synchronizes site coordinates, warm-starts cache, optionally
        syncs time, and resets operational state variables.
        
        Raises:
            DriverException: If mount initialization fails
            SerialException: If communication with mount fails
            ValueError: If mount returns invalid coordinate data
        """
        try:
            self._logger.debug("Initializing connected mount")
            
            # Retrieve and log mount identification
            try:
                mount_name = self._send_command(":GVP#", CommandType.STRING).rstrip('#')
                firmware = self._send_command(":GVN#", CommandType.STRING).rstrip('#')
                firmware_date = self._send_command(":GVD#", CommandType.STRING).rstrip('#')
                
                self._logger.info(f"Connected to mount: {mount_name}")
                self._logger.info(f"Firmware version: {firmware} ({firmware_date})")
            except Exception as ex:
                raise RuntimeError(f"Failed to retrieve mount identification", ex)
            
            # Update site coordinates from mount
            self._sync_site_coordinates_from_mount()
            
            # Sync mount time if configured (continue on failure)
            if self._config.sync_time_on_connect:
                try:
                    self.UTCDate = datetime.now(timezone.utc)
                    self._logger.info("Mount time synchronized with system clock")
                    mnttime = self.UTCDate
                    self._logger.debug(f"Computer time: {datetime.now(timezone.utc)}")
                    self._logger.debug(f"Mount time: {mnttime}")
                except Exception as ex:
                    self._logger.warning(f"Time synchronization failed: {ex}")
            
            self._logger.info("Mount initialization completed successfully")
            
            self._logger.debug("Warming up coordinate frame caches")
            _ = self._altaz_frame  # Triggers cache creation
            _ = self._gcrs_frame   # Triggers cache creation  
            self._logger.info("Coordinate frame caches warmed up successfully")

        except Exception as ex:
            self._logger.error(f"Mount initialization failed: {ex}")
            raise RuntimeError("Mount initialization failed", ex)

    def _sync_site_coordinates_from_mount(self) -> None:
        """
        Synchronize site coordinates from mount to configuration.
        
        Retrieves latitude and longitude from mount hardware and updates both
        the configuration object and AstroPy site location for coordinate transformations.
        
        Side Effects:
            - Updates self._config.site_latitude and site_longitude
            - Updates self._site_location EarthLocation object
            - Saves updated configuration to persistent storage
            
        Raises:
            DriverException: If coordinate retrieval or parsing fails
            ValueError: If mount returns invalid coordinate format
            
        Note:
            - Mount longitude is converted from East-positive to West-negative convention
            - Elevation is preserved from existing configuration
            - Coordinate precision is logged to 6 decimal places
        """
        try:
            self._logger.debug("Synchronizing site coordinates from mount")
            
            # Get latitude from mount (extended precision format)
            #try:
            #    lat_result = self._send_command(":*Gt#", CommandType.STRING)
            #    latitude = self._dms_to_degrees(lat_result)
            #    self._logger.debug(f"Retrieved latitude from mount: {latitude:.6f}°")
            #except Exception as ex:
            #    raise DriverException(0x500, f"Failed to retrieve latitude from mount: {ex}")
            
            # Get longitude from mount (extended precision format)
            #try:
            #    lon_result = self._send_command(":*Gg#", CommandType.STRING)
            #    # Convert from mount's East-positive to standard West-negative convention
            #    longitude = -1 * self._dms_to_degrees(lon_result)
            #    self._logger.debug(f"Retrieved longitude from mount: {longitude:.6f}°")
            #except Exception as ex:
            #    raise DriverException(0x500, f"Failed to retrieve longitude from mount: {ex}")

            #Get site from mount:
            try:
                latitude = self.SiteLatitude
                longitude = self.SiteLongitude
            except Exception as ex:
                raise RuntimeError(f"Failed to retrieve site coordinates from mount", ex)
            
            # Update configuration and site location
            with self._lock:
                try:
                    # Update configuration object
                    self._config.site_latitude = latitude
                    self._config.site_longitude = longitude
                    self._config.save()
                    self._logger.debug("Site coordinates saved to configuration")
                    
                    # Update AstroPy location for coordinate transformations
                    elevation = float(self._config.site_elevation) if self._config.site_elevation else 0.0
                    self._site_location = EarthLocation(
                        lat=latitude * u.deg,
                        lon=longitude * u.deg,
                        height=elevation * u.m
                    )
                    self._logger.debug("AstroPy site location updated")
                    
                except Exception as ex:
                    raise RuntimeError(f"Failed to update site location objects", ex)
            
            self._logger.info(f"Site coordinates synchronized: {latitude:.6f}°, {longitude:.6f}°, {elevation:.1f}m")
            
            self._invalidate_cache('altaz')
            
        except Exception as ex:
            self._logger.warning(f"Site coordinate synchronization failed: {ex}")
            raise RuntimeError("Failed to synchronize site coordinates from mount", ex)
    
    def Disconnect(self) -> None:
        """
        Disconnect from the TTS160 mount using ASCOM shared connection semantics.
        
        Decrements connection reference count and only performs physical disconnection
        when the last client disconnects. Follows ASCOM Platform 7 connection pattern
        where multiple clients can share a single hardware connection.
        
        Disconnection States:
            - Not connected: Returns immediately (safe to call)
            - Multiple clients: Decrements reference count, maintains connection
            - Last client: Performs physical disconnect and resource cleanup
        
        Side Effects:
            - Decrements serial manager connection count
            - Saves configuration to persistent storage (last client only)
            - Closes serial communication (last client only)
            - Sets Connected=False (last client only)
            - Temporarily sets Connecting=True during disconnection process
            
        Raises:
            DriverException: If disconnection process fails
            
        Note:
            - Safe to call multiple times or when already disconnected
            - Connecting property indicates disconnection in progress
            - Does not raise exceptions for cleanup failures to ensure disconnection completes
        """
        with self._lock:
            
            # Safe to disconnect when not connected
            if not self._Connected:
                self._logger.debug("Disconnect called when already disconnected")
                return

            # Validate serial manager state
            if not hasattr(self, '_serial_manager') or not self._serial_manager:
                self._logger.warning("Disconnect called with no serial manager, resetting connection state")
                self._Connected = False
                return

            # Handle shared connection - decrement reference count
            if self._serial_manager.connection_count > 1:
                self._serial_manager.connection_count -= 1
                self._logger.info(f"Decremented connection reference count to {self._serial_manager.connection_count}")
                return

            # Last client disconnecting - perform physical disconnect
            self._Connecting = True  # Indicate disconnection in progress
            self._logger.info("Beginning physical mount disconnection (last client)")

        try:

            self._logger.info("Aborting any slew in progress")
            #self._executor.shutdown(wait=True)
            self._send_command(":Q#", CommandType.BLIND)
            #time.sleep(1)
            # Save configuration before disconnecting
            try:
                if self._config:
                    self._config.save()
                    self._logger.debug("Configuration saved before disconnect")
            except Exception as ex:
                self._logger.warning(f"Configuration save failed during disconnect: {ex}")
            
            # Check connection state before attempting disconnect
            was_connected = False
            try:
                was_connected = self._serial_manager.is_connected
            except Exception as ex:
                self._logger.warning(f"Could not check serial connection state: {ex}")
            
            # Perform physical disconnection
            try:
                if was_connected:
                    self._serial_manager.disconnect()
                    self._logger.debug("Serial manager disconnect completed")
            except Exception as ex:
                self._logger.error(f"Serial manager disconnect failed: {ex}")
                # Continue with cleanup despite serial disconnect failure
            
            ## Clear serial manager reference -> Handled in the __del__ method
            #try:
            #    self._serial_manager = None
            #    self._logger.debug("Serial manager reference cleared")
            #except Exception as ex:
            #    self._logger.warning(f"Error clearing serial manager reference: {ex}")
            
            # Update connection state
            with self._lock:
                self._Connected = False
                
            self._logger.info("TTS160 mount disconnected successfully")
            
        except Exception as ex:
            # Log error but ensure disconnection state is set
            self._logger.error(f"Unexpected error during disconnect: {ex}")
            with self._lock:
                self._Connected = False
            raise RuntimeError("Disconnect completed with errors", ex)
            
        finally:
            # Always reset connecting state
            with self._lock:
                self._Connecting = False

    def CommandBlind(self, command: str, raw: bool = False) -> None:
        """
        Transmit arbitrary string to device without waiting for response.
        
        DEPRECATED: This method is deprecated in ASCOM and not supported by TTS160.
        Use device-specific methods or Action() for custom functionality.
        
        Args:
            command: Literal command string to transmit
            raw: If True, transmit as-is; if False, add protocol framing
            
        Raises:
            NotImplementedException: Always raised - method not supported
            
        Note:
            This method is deprecated per ASCOM standards and will likely
            result in NotImplementedException for all modern devices.
        """
        self._logger.warning(f"CommandBlind called with deprecated method: command='{command}', raw={raw}")
        raise NotImplementedError("CommandBlind is deprecated and not supported by TTS160")


    def CommandBool(self, command: str, raw: bool = False) -> bool:
        """
        Transmit arbitrary string to device and wait for boolean response.
        
        DEPRECATED: This method is deprecated in ASCOM and not supported by TTS160.
        Use device-specific methods or Action() for custom functionality.
        
        Args:
            command: Literal command string to transmit
            raw: If True, transmit as-is; if False, add protocol framing
            
        Returns:
            bool: Boolean response from device (never returns due to exception)
            
        Raises:
            NotImplementedException: Always raised - method not supported
            
        Note:
            This method is deprecated per ASCOM standards and will likely
            result in NotImplementedException for all modern devices.
        """
        self._logger.warning(f"CommandBool called with deprecated method: command='{command}', raw={raw}")
        raise NotImplementedError("CommandBool is deprecated and not supported by TTS160")


    def CommandString(self, command: str, raw: bool = False) -> str:
        """
        Transmit arbitrary string to device and wait for string response.
        
        DEPRECATED: This method is deprecated in ASCOM and not supported by TTS160.
        Use device-specific methods or Action() for custom functionality.
        
        Args:
            command: Literal command string to transmit
            raw: If True, transmit as-is; if False, add protocol framing
            
        Returns:
            str: String response from device (never returns due to exception)
            
        Raises:
            NotImplementedException: Always raised - method not supported
            
        Note:
            This method is deprecated per ASCOM standards and will likely
            result in NotImplementedException for all modern devices.
        """
        self._logger.warning(f"CommandString called with deprecated method: command='{command}', raw={raw}")
        raise NotImplementedError("CommandString is deprecated and not supported by TTS160")


    def _send_command(self, command: str, command_type: CommandType) -> str:
        """
        Send LX200-compatible command to mount and return response.
        
        Core communication method for all mount interactions. Validates connection
        state, sends command via serial manager, and handles communication errors.
        
        Args:
            command: LX200-format command string (should end with '#')
            command_type: Expected response type (STRING, BOOL, BLIND)
            
        Returns:
            str: Response from mount, format depends on command_type
            
        Raises:
            DriverException: If device not connected or communication fails
            ValueError: If command or command_type invalid
            SerialException: If serial communication error occurs
            
        Note:
            - All LX200 commands should be terminated with '#' character
            - Response format varies by command per LX200 ICD specification
            - Communication timeouts handled by serial manager
        """
        # Input validation
        if not isinstance(command, str):
            self._logger.error(f"Invalid command type: {type(command)}, expected str")
            raise ValueError(f"Command must be string, got {type(command)}")
        
        if not command:
            self._logger.error("Empty command string provided")
            raise ValueError("Command cannot be empty")
        
        if not isinstance(command_type, CommandType):
            self._logger.error(f"Invalid command_type: {type(command_type)}, expected CommandType")
            raise ValueError(f"command_type must be CommandType enum, got {type(command_type)}")
        
        # Log command execution (sanitize for logging)
        safe_command = command.replace('\r', '\\r').replace('\n', '\\n')
        self._logger.debug(f"Sending command: '{safe_command}' (type: {command_type.name})")
        
        # Connection state validation - Include checking for connecting to allow for commands at connectiong
        # before setting Connected to True
        if not self._Connected and not self._Connecting:
            self._logger.error(f"Command '{safe_command}' attempted while disconnected")
            raise ConnectionError("Device not connected - cannot send command")
        
        # Serial manager validation
        if not hasattr(self, '_serial_manager') or not self._serial_manager:
            self._logger.error("Serial manager not available for command execution")
            raise RuntimeError("Serial manager not initialized")
        
        try:
            # Execute command via serial manager
            response = self._serial_manager.send_command(command, command_type)
            
            # Log successful execution
            if command_type == CommandType.BLIND:
                self._logger.debug(f"Command '{safe_command}' executed successfully (no response)")
            else:
                # Sanitize response for logging
                safe_response = str(response).replace('\r', '\\r').replace('\n', '\\n')
                self._logger.debug(f"Command '{safe_command}' response: '{safe_response}'")
            
            return response
            
        except Exception as ex:
            # Wrap unexpected exceptions with context
            self._logger.error(f"Communication error executing command '{safe_command}': {ex}")
            raise RuntimeError(f"Command execution failed: {command}", ex)
        
   
    def _altaz_to_radec(self, azimuth: float, altitude: float) -> Tuple[float, float]:
        """
        Convert Alt/Az coordinates to RA/Dec in mount's equatorial system.
        
        Uses mount's EquatorialSystem property to determine target coordinate system
        (ICRS/J2000 vs topocentric/current epoch).
        
        Args:
            azimuth: Azimuth in decimal degrees (0-360)
            altitude: Altitude in decimal degrees (-90 to +90)
        
        Returns:
            Tuple[float, float]: (right_ascension_hours, declination_degrees)
            
        Raises:
            InvalidValueException: Invalid coordinate values
            DriverException: Coordinate transformation failure
        """
        try:
            self._logger.debug(f"Converting Alt/Az to RA/Dec: Az={azimuth:.3f}°, Alt={altitude:.3f}°")
            
            # Route to appropriate conversion based on mount's equatorial system
            if self.EquatorialSystem == EquatorialCoordinateType.equTopocentric:
                result = self._altaz_to_gcrs(azimuth, altitude)
                self._logger.debug(f"Used topocentric conversion: RA={result[0]:.3f}h, Dec={result[1]:.3f}°")
            else:
                result = self._altaz_to_icrs(azimuth, altitude)
                self._logger.debug(f"Used ICRS conversion: RA={result[0]:.3f}h, Dec={result[1]:.3f}°")
            
            return result
            
        except ValueError:
            self._logger.error(f"Alt/Az to RA/Dec conversion failed: Az={azimuth}°, Alt={altitude}°")
            raise
        except Exception as ex:
            self._logger.error(f"Unexpected error in Alt/Az conversion: {ex}")
            raise RuntimeError("Coordinate conversion failed", ex)


    def _radec_to_altaz(self, right_ascension: float, declination: float) -> Tuple[float, float]:
        """
        Convert RA/Dec coordinates to Alt/Az in mount's equatorial system.
        
        Uses mount's EquatorialSystem property to determine source coordinate system.
        
        Args:
            right_ascension: RA in decimal hours (0-24)
            declination: Declination in decimal degrees (-90 to +90)
        
        Returns:
            Tuple[float, float]: (azimuth_degrees, altitude_degrees)
            
        Raises:
            InvalidValueException: Invalid coordinate values
            DriverException: Coordinate transformation failure
        """
        try:
            self._logger.debug(f"Converting RA/Dec to Alt/Az: RA={right_ascension:.3f}h, Dec={declination:.3f}°")
            
            # Route to appropriate conversion based on mount's equatorial system
            if self.EquatorialSystem == EquatorialCoordinateType.equTopocentric:
                result = self._gcrs_to_altaz(right_ascension, declination)
                self._logger.debug(f"Used topocentric conversion: Az={result[0]:.3f}°, Alt={result[1]:.3f}°")
            else:
                result = self._icrs_to_altaz(right_ascension, declination)
                self._logger.debug(f"Used ICRS conversion: Az={result[0]:.3f}°, Alt={result[1]:.3f}°")
            
            return result
            
        except ValueError:
            self._logger.error(f"RA/Dec to Alt/Az conversion failed: RA={right_ascension}h, Dec={declination}°")
            raise
        except Exception as ex:
            self._logger.error(f"Unexpected error in RA/Dec conversion: {ex}")
            raise RuntimeError("Coordinate conversion failed", ex)
    
    # Connection Properties
    @property
    def Connected(self) -> bool:
        """ASCOM Connected property."""
        try:
            with self._lock:
                self._logger.debug(f"Reporting Connected as: {self._Connected}")
                return self._Connected
        except Exception as ex:
            raise RuntimeError("Reading Connected property failed", ex)
        
    @Connected.setter  
    def Connected(self, value: bool) -> None:
        """ASCOM Connected property setter."""
        self._logger.debug(f"Set Connected {value}, deprecated connection method, simulating sync methods")
        try:
            if value:
                self.Connect()
                #simulate synchronous execution
                while not self._Connected:
                    time.sleep(0.1)
            else:
                self.Disconnect()
        except Exception as ex:
            raise RuntimeError(f"Setting Connected to: {value} failed", ex)
    
    @property
    def Connecting(self) -> bool:
        """ASCOM Connecting property."""
        try:
            with self._lock:
                self._logger.debug(f"Reporting Connecting as: {self._Connected}")
                return self._Connecting
        except Exception as ex:
            raise RuntimeError("Reading Connecting property failed", ex)
        
    # Mount Actions
    def Action(self, action_name: str, *parameters: Any) -> str:
        """Invokes the specified device-specific custom action."""
        self._logger.info(f"Action: {action_name}; Parameters: {parameters}")
        
        if not self.Connected:
            raise ConnectionError("Device not connected")

        try:
            action_name = action_name.lower()
            
            if action_name == "fieldrotationangle":
                self._logger.info("FieldRotationAngle - Retrieving")
                result = self._send_command(":ra#", CommandType.STRING)
                self._logger.info(f"FieldRotationAngle - Retrieved: {result}")
                return result
            
            raise NotImplementedError(f"Action '{action_name}' is not implemented")
            
        except Exception as ex:
            self._logger.error(f"Action error: {ex}")
            raise


    # Mount Position Properties

    @property
    def Altitude(self) -> float:
        """
        Current altitude in degrees above horizon.
        
        Returns mount's current altitude using LX200 extended precision command.
        Response is in radians and converted to degrees per ASCOM standard.
        
        Returns:
            float: Altitude in degrees (-90 to +90, positive above horizon)
            
        Raises:
            NotConnectedException: If device not connected
            DriverException: If command fails or mount communication error
        """
        if not self._Connected:
            raise ConnectionError("Device not connected")
        
        try:
            self._logger.debug("Retrieving current altitude from mount")
            result = self._send_command(":*GA#", CommandType.STRING).rstrip('#')
            altitude_deg = float(result) * (180 / math.pi)  # Convert radians to degrees
            self._logger.debug(f"Current altitude: {altitude_deg:.3f}°")
            return altitude_deg
        except Exception as ex:
            self._logger.error(f"Failed to retrieve altitude: {ex}, retrying")
            try:
                self._serial_manager.clear_buffers()
                self._logger.debug("Retrieving current altitude from mount")
                result = self._send_command(":*GA#", CommandType.STRING).rstrip('#')
                altitude_deg = float(result) * (180 / math.pi)  # Convert radians to degrees
                self._logger.debug(f"Current altitude: {altitude_deg:.3f}°")
                return altitude_deg
            except Exception as ex:
                self._logger.error(f"Retry failed to retrieve altitude: {ex}")
                raise RuntimeError("Failed to get altitude", ex)


    @property
    def Azimuth(self) -> float:
        """
        Current azimuth in degrees (North-referenced, positive East).
        
        Returns mount's current azimuth using LX200 extended precision command.
        Response is in radians and converted to degrees per ASCOM standard.
        
        Returns:
            float: Azimuth in degrees (0-360, North=0°, East=90°)
            
        Raises:
            NotConnectedException: If device not connected
            DriverException: If command fails or mount communication error
        """
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        try:
            self._logger.debug("Retrieving current azimuth from mount")
            result = self._send_command(":*GZ#", CommandType.STRING).rstrip('#')
            azimuth_deg = float(result) * (180 / math.pi)  # Convert radians to degrees
            self._logger.debug(f"Current azimuth: {azimuth_deg:.3f}°")
            return azimuth_deg
        except Exception as ex:
            self._logger.error(f"Failed to retrieve azimuth: {ex}")
            try:
                self._serial_manager.clear_buffers()
                self._logger.debug("Retrieving current azimuth from mount")
                result = self._send_command(":*GZ#", CommandType.STRING).rstrip('#')
                azimuth_deg = float(result) * (180 / math.pi)  # Convert radians to degrees
                self._logger.debug(f"Current azimuth: {azimuth_deg:.3f}°")
                return azimuth_deg
            except Exception as ex:
                self._logger.error(f"Retry failed to retrieve azimuth: {ex}")
            raise RuntimeError("Failed to get azimuth", ex)


    @property
    def Declination(self) -> float:
        """
        Current declination in degrees in mount's equatorial system.
        
        Returns mount's current declination using LX200 extended precision command.
        Coordinate system matches mount's EquatorialSystem property.
        
        Returns:
            float: Declination in degrees (-90 to +90, positive North)
            
        Raises:
            NotConnectedException: If device not connected
            DriverException: If command fails or mount communication error
        """
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        try:
            self._logger.debug("Retrieving current declination from mount")
            result = self._send_command(":*GD#", CommandType.STRING).rstrip('#')
            declination_deg = float(result) * (180 / math.pi)  # Convert radians to degrees
            self._logger.debug(f"Current declination: {declination_deg:.3f}°")
            return declination_deg
        except Exception as ex:
            self._logger.error(f"Failed to retrieve declination: {ex}")
            raise RuntimeError("Failed to get declination", ex)


    @property
    def RightAscension(self) -> float:
        """
        Current right ascension in hours in mount's equatorial system.
        
        Returns mount's current RA using LX200 extended precision command.
        Coordinate system matches mount's EquatorialSystem property.
        
        Returns:
            float: Right ascension in hours (0-24)
            
        Raises:
            NotConnectedException: If device not connected
            DriverException: If command fails or mount communication error
        """
        if not self._Connected:
            raise ConnectionError("Device not connected")
        
        try:
            self._logger.debug("Retrieving current right ascension from mount")
            result = self._send_command(":*GR#", CommandType.STRING).rstrip('#')
            ra = float(result) * (180 / math.pi) / 15  # Convert radians to hours
            ra = ra % 24  # Normalize to 0-24 hours
            self._logger.debug(f"Current right ascension: {ra:.3f}h")
            return ra
        except Exception as ex:
            self._logger.error(f"Failed to retrieve right ascension: {ex}")
            raise RuntimeError("Failed to get right ascension", ex)


    @property
    def SiderealTime(self) -> float:
        """
        Local apparent sidereal time in hours.
        
        Gets sidereal time from mount and converts to local sidereal time
        using site longitude. Required for pointing calculations.
        
        Returns:
            float: Local sidereal time in hours (0-24)
            
        Raises:
            NotConnectedException: If device not connected
            DriverException: If command fails or mount communication error
        """
        if not self._Connected and not self._Connecting:
            raise ConnectionError("Device not connected")
        
        try:
            self._logger.debug("Retrieving sidereal time from mount")
            # Get GMST from mount
            result = self._send_command(":GS#", CommandType.STRING).rstrip('#')
            gmst = self._hms_to_hours(result)
            
            # Convert to local sidereal time
            longitude_hours = self._site_location.lon.degree / 15.0
            lst = (gmst + longitude_hours) % 24
            
            self._logger.debug(f"Sidereal time - GMST: {gmst:.3f}h, LST: {lst:.3f}h")
            return lst
        except Exception as ex:
            self._logger.error(f"Failed to retrieve sidereal time: {ex}")
            raise RuntimeError("Failed to get sidereal time", ex)


    def DestinationSideOfPier(self, ra: float, dec: float) -> PierSide:
        """
        Predict pointing state after slewing to given coordinates.
        
        Calculates which side of pier (East/West) the mount will be on
        after slewing to specified coordinates. Used for GEM flip management.
        
        Args:
            ra: Right ascension in hours (0-24)
            dec: Declination in degrees (-90 to +90)
            
        Returns:
            PierSide: Predicted pier side (pierEast, pierWest, or pierUnknown)
            
        Raises:
            InvalidValueException: If coordinates outside valid ranges
            DriverException: If pier side calculation fails
        """
        try:
            # Input validation            
            self._validate_coordinates(ra = ra, dec = dec)

            self._logger.debug(f"Calculating destination pier side for RA {ra:.3f}h, Dec {dec:.3f}°")
            
            pier_side = self._calculate_side_of_pier(ra)
            self._logger.debug(f"Destination pier side: {pier_side}")
            return pier_side
            
        except ValueError:
            self._logger.error(f"Invalid coordinates for pier side calculation: RA={ra}, Dec={dec}")
            raise
        except Exception as ex:
            self._logger.error(f"Pier side calculation failed: {ex}")
            raise RuntimeError("Failed to calculate destination pier side", ex)

    # Site and Telescope Properties
    @property
    def ApertureArea(self) -> float:
        raise NotImplementedError("ApertureArea not implemented")
    
    @property
    def ApertureDiameter(self) -> float:
        raise NotImplementedError("ApertureDiameter not implemented")

    @property
    def DoesRefraction(self) -> bool:
        raise NotImplementedError("Get DoesRefraction is not implemented")
    
    @DoesRefraction.setter
    def DoesRefraction(self, value: bool ) -> None:
        raise NotImplementedError("Set DoesRefraction is not implemented")

    @property
    def FocalLength(self) -> float:
        raise NotImplementedError()

    @property  
    def SiteLatitude(self) -> float:
        """
        Site latitude in degrees (geodetic, WGS84, positive North).
        
        Retrieves current latitude from mount using extended precision format
        and updates internal configuration and site location objects.
        
        Returns:
            float: Latitude in degrees (-90 to +90)
            
        Raises:
            NotConnectedException: If device not connected
            DriverException: If retrieval or parsing fails
        """
        if not self._Connected and not self._Connecting:
            raise ConnectionError("Device not connected")
        
        try:
            self._logger.debug("Retrieving site latitude from mount")
            command = ":*Gt#"
            latitude = self._send_command(command, CommandType.STRING).rstrip("#")
            latitude_deg = self._dms_to_degrees(latitude)

            # Update site location and configuration
            self._site_location = EarthLocation(
                lat=latitude_deg * u.deg,
                lon=self._site_location.lon,
                height=self._site_location.height
            )
            self._config.site_latitude = latitude_deg

            self._logger.info(f"Site latitude: {latitude_deg:.6f}°")
            return latitude_deg
        except Exception as ex:
            self._logger.error(f"Failed to retrieve site latitude: {ex}")
            raise RuntimeError(f"Get latitude failed", ex)
    
    #TODO: I don't think this was implemented in the ASCOM driver, verify.
    @SiteLatitude.setter
    def SiteLatitude(self, value: float) -> None:
        raise NotImplementedError()
    
    @property
    def SiteLongitude(self) -> float:
        """
        Site longitude in degrees (geodetic, WGS84, positive East).
        
        Retrieves current longitude from mount using extended precision format.
        Mount reports East-negative, converts to standard East-positive convention.
        
        Returns:
            float: Longitude in degrees (-180 to +180, positive East)
            
        Raises:
            NotConnectedException: If device not connected
            DriverException: If retrieval or parsing fails  
        """
        if not self._Connected and not self._Connecting:
            raise ConnectionError("Device not connected")
        
        try:
            self._logger.debug("Retrieving site longitude from mount")
            command = ":*Gg#"
            longitude = self._send_command(command, CommandType.STRING).rstrip("#")
            longitude_deg = -1 * self._dms_to_degrees(longitude)  # Convert East-negative to East-positive

            # Update site location and configuration
            self._site_location = EarthLocation(
                lat=self._site_location.lat,
                lon=longitude_deg * u.deg,
                height=self._site_location.height
            )
            self._config.site_longitude = longitude_deg

            self._logger.info(f"Site longitude: {longitude_deg:.6f}°")
            return longitude_deg
        except Exception as ex:
            self._logger.error(f"Failed to retrieve site longitude: {ex}")
            raise RuntimeError(f"Get longitude failed", ex)
    
    #TODO: I don't think this was implemented in the ASCOM driver, verify
    @SiteLongitude.setter  
    def SiteLongitude(self, value: float) -> None:
        raise NotImplementedError()
    
    @property
    def SiteElevation(self) -> float:
        """Site elevation in meters."""
        return self._site_location.height.value
    
    #TODO: Ibid.  If I do want this implemented, it needs to feed back to the configuration object
    @SiteElevation.setter
    def SiteElevation(self, value: float) -> None:
        raise NotImplementedError()
    
    # Mount State Properties
    @property
    def AtHome(self) -> bool:
        """True if mount is at home position."""
        if not self.Connected:
            raise ConnectionError("Mount not connected")
        
        try:
            with self._lock:
                return self._is_at_home
        except Exception as ex:
            raise RuntimeError("Failed to retrieve AtHome", ex)
    
    @AtHome.setter
    def AtHome(self, value: bool) -> None:
        """True if mount is at home position."""
        with self._lock:
            self._is_at_home = value

    @property
    def AtPark(self) -> bool:
        """True if mount is parked."""

        if not self._Connected:
            raise ConnectionError("Mount not connected")
    
        try:
            with self._lock:
                self._is_parked = self._send_command(":*Pq#", CommandType.BOOL)
                self._logger.debug(f"Returning self._is_parked as: {self._is_parked}.  It is a {type(self._is_parked)}")
                return self._is_parked
        except Exception as ex:
            raise RuntimeError("Failed to retrieve AtPark", ex)

    @property
    def DeviceState(self) -> List[dict]:
        """
        List of key-value pairs representing operational properties of the device.
        
        Returns comprehensive state information for monitoring and diagnostic purposes.
        Each dictionary contains 'name' and 'value' keys representing device parameters.
        
        Returns:
            List[dict]: Device state parameters with current values and timestamp
            
        Raises:
            DriverException: If device state retrieval fails
        """
        try:
            self._logger.debug("Assembling device state information")
            
            device_state: List[dict] = [
                {"name": "Altitude", "value": self.Altitude},
                {"name": "AtHome", "value": self.AtHome},
                {"name": "AtPark", "value": self.AtPark},
                {"name": "Azimuth", "value": self.Azimuth},
                {"name": "Declination", "value": self.Declination},
                {"name": "IsPulseGuiding", "value": self.IsPulseGuiding},
                {"name": "RightAscension", "value": self.RightAscension},
                {"name": "SideOfPier", "value": self.SideOfPier},
                {"name": "SiderealTime", "value": self.SiderealTime},
                {"name": "Slewing", "value": self.Slewing},
                {"name": "Tracking", "value": self.Tracking},
                {"name": "UTCDate", "value": self.UTCDate},
                {"name": "TimeStamp", "value": datetime.now}
            ]
            
            self._logger.debug(f"Device state assembled with {len(device_state)} parameters")
            return device_state

        except Exception as ex:
                self._logger.error(f"Failed to assemble device state: {ex}")
                raise RuntimeError(f"Device state retrieval failed", ex)

    @property
    def EquatorialSystem(self) -> EquatorialCoordinateType:
        """Which Equatorial Type does the mount use"""
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        try:
            self._logger.info("Querying current epoch")
            result = self._send_command(":*E#", CommandType.BOOL)
            if result:
                self._logger.info(f"Retrieved {result}, indicating Topocentric Equatorial")
                return EquatorialCoordinateType.equTopocentric
            else:
                self._logger.info(f"Retrieved {result}, indicating J2000")
                return EquatorialCoordinateType.equJ2000
        except Exception as ex:
            raise RuntimeError("Get EatuatorialSystem failed", ex)
    
    @property
    def GuideRateDeclination(self) -> float:   
        """
        The current declination rate offset (deg/sec) for guiding.
        
        Returns:
            float: Guide rate in degrees per second for declination axis
            
        Raises:
            InvalidValueException: If invalid guide rate retrieved
            NotImplementedException: If guide rates cannot be read
            NotConnectedException: If device not connected
            DriverException: If guide rate retrieval fails
        """
        try:
            self._logger.debug("Retrieving declination guide rate")
            rate_index = int(self._send_command(":*gRG#", CommandType.STRING).rstrip('#'))
            
            guide_rates = {
                0: 1.0 / 3600.0,
                1: 3.0 / 3600.0,
                2: 5.0 / 3600.0,
                3: 10.0 / 3600.0,
                4: 20.0 / 3600.0
            }
            
            rate = guide_rates.get(rate_index, 0)
            self._logger.debug(f"Declination guide rate: {rate:.6f} deg/sec (index {rate_index})")
            return rate
            
        except Exception as ex:
            self._logger.error(f"Failed to retrieve declination guide rate: {ex}")
            raise RuntimeError(f"Guide rate retrieval failed", ex)

    @GuideRateDeclination.setter
    def GuideRateDeclination(self, value: float) -> None:
        """
        Set the current declination rate offset (deg/sec) for guiding.
        
        Args:
            value: Guide rate in degrees per second
            
        Raises:
            InvalidValueException: If invalid guide rate specified
            NotImplementedException: If guide rates cannot be set
            NotConnectedException: If device not connected
            DriverException: If guide rate setting fails
        """
        try:
            self._logger.info(f"Setting declination guide rate to: {value:.6f} deg/sec")
            
            value_arcsec = value * 3600
            thresholds = [1.5, 4.0, 7.5, 15.0]
            rate_index = bisect.bisect_left(thresholds, value_arcsec)
            
            self._logger.debug(f"Guide rate {value:.6f} deg/sec maps to index {rate_index}")
            self._send_command(f":*gRS{rate_index}#", CommandType.BLIND)
            
            self._logger.info(f"Declination guide rate successfully set to index {rate_index}")
            
        except Exception as ex:
            self._logger.error(f"Failed to set declination guide rate {value}: {ex}")
            raise RuntimeError(f"Guide rate setting failed", ex)

    @property
    def GuideRateRightAscension(self) -> float:
        """
        The current right ascension rate offset (deg/sec) for guiding.
        
        Returns:
            float: Guide rate in degrees per second for right ascension axis
            
        Raises:
            InvalidValueException: If invalid guide rate retrieved
            NotImplementedException: If guide rates cannot be read
            NotConnectedException: If device not connected
            DriverException: If guide rate retrieval fails
        """
        try:
            self._logger.debug("Retrieving right ascension guide rate")
            rate_index = int(self._send_command(":*gRG#", CommandType.STRING).rstrip('#'))
            
            guide_rates = {
                0: 1.0 / 3600.0,
                1: 3.0 / 3600.0,
                2: 5.0 / 3600.0,
                3: 10.0 / 3600.0,
                4: 20.0 / 3600.0
            }
            
            rate = guide_rates.get(rate_index, 0)
            self._logger.debug(f"Right ascension guide rate: {rate:.6f} deg/sec (index {rate_index})")
            return rate
            
        except Exception as ex:
            self._logger.error(f"Failed to retrieve right ascension guide rate: {ex}")
            raise RuntimeError(f"Guide rate retrieval failed", ex)

    @GuideRateRightAscension.setter
    def GuideRateRightAscension(self, value: float) -> None:
        """
        Set the current right ascension rate offset (deg/sec) for guiding.
        
        Args:
            value: Guide rate in degrees per second
            
        Raises:
            InvalidValueException: If invalid guide rate specified
            NotImplementedException: If guide rates cannot be set
            NotConnectedException: If device not connected
            DriverException: If guide rate setting fails
        """
        try:
            self._logger.info(f"Setting right ascension guide rate to: {value:.6f} deg/sec")
            
            value_arcsec = value * 3600
            thresholds = [1.5, 4.0, 7.5, 15.0]
            rate_index = bisect.bisect_left(thresholds, value_arcsec)
            
            self._logger.debug(f"Guide rate {value:.6f} deg/sec maps to index {rate_index}")
            self._send_command(f":*gRS{rate_index}#", CommandType.BLIND)
            
            self._logger.info(f"Right ascension guide rate successfully set to index {rate_index}")
            
        except Exception as ex:
            self._logger.error(f"Failed to set right ascension guide rate {value}: {ex}")
            raise RuntimeError(f"Guide rate setting failed", ex)

    def _calculate_side_of_pier(self, right_ascension: float) -> PierSide:
        """
        Calculate which side of pier telescope should be on for given RA.
        
        Determines pier side based on hour angle. Positive hour angles
        (object west of meridian) use East pier side, negative hour angles
        (object east of meridian) use West pier side.
        
        Args:
            right_ascension: Right ascension in decimal hours (0-24)
            
        Returns:
            PierSide: pierEast if HA > 0, pierWest if HA <= 0
            
        Raises:
            DriverException: If sidereal time calculation fails
            InvalidValueException: If RA outside valid range (0-24 hours)
        """
        try:
            self._logger.debug(f"Calculating pier side for RA {right_ascension:.3f}h")
            self._validate_coordinates(ra = right_ascension)
            
            # Calculate hour angle
            sidereal_time = self.SiderealTime
            hour_angle = self._condition_ha(sidereal_time - right_ascension)
            
            # Determine pier side based on hour angle
            pier_side = PierSide.pierEast if hour_angle > 0 else PierSide.pierWest
            
            self._logger.debug(f"RA {right_ascension:.3f}h, LST {sidereal_time:.3f}h, HA {hour_angle:.3f}h -> {pier_side.name}")
            return pier_side
            
        except ValueError:
            self._logger.error(f"Invalid RA for pier side calculation: {right_ascension}")
            raise
        except Exception as ex:
            self._logger.error(f"Pier side calculation failed for RA {right_ascension}: {ex}")
            raise RuntimeError("Pier side calculation failed", ex)

    @property
    def SideOfPier(self) -> PierSide:
        """Calculates and returns SideofPier"""
        return self._calculate_side_of_pier(self.RightAscension)

    @property
    def Slewing(self) -> bool:
        """True if mount is slewing."""
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        try:
            
            #Atomic Snapshot provides protection
            slew_future = self._slew_in_progress
            return (slew_future and not slew_future.done()) or self._slewing_hold
                
        except Exception as ex:
            raise RuntimeError(f"Error checking slewing status", ex)
    
    @property
    def Tracking(self) -> bool:
        """True if mount is tracking."""
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        try:
            result = self._send_command(":GW#", CommandType.STRING)
            return result[1] == 'T' if len(result) > 1 else False
        except Exception as ex:
            raise RuntimeError(0x500, "Failed to get tracking state", ex)
    
    @Tracking.setter
    def Tracking(self, value: bool) -> None:
        """Set tracking state."""
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        if self.Slewing:
            raise RuntimeError("Cannot change tracking while slewing")
        
        if self.AtPark:
            raise RuntimeError("Cannot change tracking state while parked")

        try:
            command = ":T1#" if value else ":T0#" 
            self._send_command(command, CommandType.BLIND)
            with self._lock:
                self._tracking = value
        except Exception as ex:
            raise RuntimeError("Failed to set tracking", ex)
    
    @property
    def TrackingRate(self) -> DriveRates:
        """
        The current sidereal tracking rate of the mount.
        
        Returns:
            DriveRates: Current tracking rate (Sidereal, Lunar, Solar, King)
            
        Raises:
            InvalidValueException: If mount returns unknown tracking rate
            NotConnectedException: If device not connected
            DriverException: If tracking rate retrieval fails
        """
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        try:
            self._logger.debug("Retrieving current tracking rate from mount")
            command = ":*TRG#"
            result = int(self._send_command(command, CommandType.STRING).rstrip("#"))
            
            if result == 0:
                rate = DriveRates.driveSidereal
            elif result == 1:
                rate = DriveRates.driveLunar
            elif result == 2:
                rate = DriveRates.driveSolar
            else:
                self._logger.error(f"Unknown tracking rate value from mount: {result}")
                raise RuntimeError(f"TrackingRate get failed due to unknown value received: {result}")
            
            self._logger.debug(f"Current tracking rate: {rate.name}")
            return rate
            
        except Exception as ex:
            self._logger.error(f"Failed to retrieve tracking rate: {ex}")
            raise RuntimeError(f"Unknown error", ex)

    @TrackingRate.setter
    def TrackingRate(self, rate: DriveRates) -> None:
        """
        Set the current sidereal tracking rate of the mount.
        
        Args:
            rate: Desired tracking rate (Sidereal, Lunar, Solar)
            
        Raises:
            InvalidValueException: If unsupported tracking rate specified
            NotConnectedException: If device not connected
            DriverException: If tracking rate setting fails
        """
        if not self.Connected:
            raise ConnectionError("Device not connected")

        try:
            rate = DriveRates(rate)
        except ValueError:
            raise ValueError(f"Invalid tracking rate: {rate}")
        
        # Check if supported
        if rate not in [DriveRates.driveSidereal, DriveRates.driveLunar, DriveRates.driveSolar]:
            raise ValueError(f"Unsupported tracking rate: {rate}")
        
        try:
            self._logger.info(f"Setting tracking rate to: {rate.name}")
            if rate == DriveRates.driveSidereal:
                command = ":TQ#"
            elif rate == DriveRates.driveLunar:
                command = ":TL#"
            elif rate == DriveRates.driveSolar:
                command = ":TS#"
            else:
                raise ValueError(f"Unsupported tracking rate: {rate}")
            
            self._send_command(command, CommandType.BLIND)
            self._logger.info(f"Tracking rate successfully set to: {rate.name}")

        except Exception as ex:
            self._logger.error(f"Failed to set tracking rate to {rate.name}: {ex}")
            raise RuntimeError(f"Set Tracking Rate Failed", ex)


    @property
    def RightAscensionRate(self) -> float:
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        if self.TrackingRate != DriveRates.driveSidereal:
            return 0.0

        try:
            result = self._send_command(":*RR#",CommandType.STRING).rstrip('#')
            rar = float(result) * 0.9972695677  #convert from UTC seconds to sidereal seconds
            return rar
        except Exception as ex:
            raise RuntimeError(f"Get RightAscensionRate failed", ex)

    @RightAscensionRate.setter
    def RightAscensionRate(self, value: float) -> None:
        """
        Set the right ascension tracking rate.
        
        Args:
            value: RA rate in seconds/second (will be corrected for sidereal time)
            
        Raises:
            ConnectionError: If device not connected
            RuntimeError: If tracking rate not sidereal, rate out of range, or command fails
            
        Note:
            Rate is automatically corrected by sidereal factor (1.00273791) and
            validated against firmware limits (±99.9999999999 sec/sec after correction).
        """
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        if self.TrackingRate != DriveRates.driveSidereal:
            raise RuntimeError("Unable to set RightAscensionRate when TrackingRate is not Sidereal")
        
        # Apply sidereal time correction factor
        corrected_ra_rate = value * 1.00273791  # Convert to RA seconds per UTC second
        
        # Validate corrected rate against firmware limits
        if abs(corrected_ra_rate) > 99.9999:
            raise RuntimeError(f"RA rate {corrected_ra_rate:.10f} sec/sec exceeds firmware limit ±99.9999999999 sec/sec")
        
        self._logger.info(f"Setting RA rate: input={value:.10f} sec/sec, corrected={corrected_ra_rate:.10f} sec/sec")
        
        try:           
            # Format command: :*SRCXX.XXXXXXXXXX# 
            # where XX.XXXX = RA rate, C is Sign
            # Signs (+ or -) are included in the formatted numbers (2 digits before decimal)
            command = f":*SR{corrected_ra_rate:+014.10f}#"
            
            self._logger.debug(f"Transmitting RA rate command: {command}")
            
            # Send command to firmware (blind command - no response expected)
            self._send_command(command, CommandType.BLIND)
            
            # Update state under lock protection for thread safety
            with self._lock:
                self._rightascensionrate = corrected_ra_rate
                self._rightascensionrate_set = (corrected_ra_rate != 0)
            
            self._logger.info(f"RA rate configured successfully: RA={corrected_ra_rate:.10f} sec/sec")
            
        except Exception as ex:
            error_msg = f"Failed to set RA rate {corrected_ra_rate:.10f} sec/sec"
            self._logger.error(f"{error_msg}: {ex}")
            raise RuntimeError(error_msg) from ex

    @property
    def DeclinationRate(self) -> float:
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        if self.TrackingRate != DriveRates.driveSidereal:
            return 0.0

        try:
            result = self._send_command(":*RD#",CommandType.STRING).rstrip('#')
            decr = float(result)
            return decr
        except Exception as ex:
            raise RuntimeError(f"Get DeclinationRate failed", ex)
    
    
    @DeclinationRate.setter
    def DeclinationRate(self, value: float) -> None:
        """
        Set the declination tracking rate.
        
        Args:
            value: Dec rate in arcsec/second (no sidereal correction needed)
            
        Raises:
            ConnectionError: If device not connected
            RuntimeError: If tracking rate not sidereal, rate out of range, or command fails
            
        Note:
            Rate is validated against firmware limits (±99.9999999999 arcsec/sec).
        """
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        if self.TrackingRate != DriveRates.driveSidereal:
            raise RuntimeError("Unable to set DeclinationRate when TrackingRate is not Sidereal")
        
        # Validate rate against firmware limits (no sidereal correction needed)
        if abs(value) > 99.9999999999:
            raise RuntimeError(f"Dec rate {value:.10f} arcsec/sec exceeds firmware limit ±99.9999999999 arcsec/sec")
        
        self._logger.info(f"Setting Dec rate: {value:.10f} arcsec/sec")
        
        try:
            
            # Format command: :*SDXX.XXXXXXXXXX# 
            # where XX.XXXXXXXXXX = Dec rate, C = Sign
            # Signs (+ or -) are included in the formatted numbers (2 digits before decimal)
            command = f":*SD{value:+014.10f}#"
            
            self._logger.debug(f"Transmitting Dec rate command: {command}")
            
            # Send command to firmware (blind command - no response expected)
            self._send_command(command, CommandType.BLIND)
            
            # Update state under lock protection for thread safety
            with self._lock:
                self._declinationrate = value
                self._declinationrate_set = (value != 0)
            
            self._logger.info(f"Dec rate configured successfully: Dec={value:.10f} arcsec/sec")
            
        except Exception as ex:
            error_msg = f"Failed to set Dec rate {value:.10f} arcsec/sec"
            self._logger.error(f"{error_msg}: {ex}")
            raise RuntimeError(error_msg) from ex

    @property
    def IsPulseGuiding(self) -> bool:
        """
        True if the mount is currently executing a PulseGuide() command.
        
        This property indicates whether any pulse guide operation is active on either
        the North/South or East/West axis. It automatically stops expired pulse guides
        and cleans up monitoring resources.
        
        Returns:
            bool: True if pulse guiding is active on any axis, False otherwise
            
        Raises:
            DriverException: If an error occurs checking pulse guide status
            
        Note:
            A pulse guide command may be so short that this property reads False
            immediately after calling PulseGuide(). This indicates successful
            completion, not failure.
        """
        try:
            with self._lock:
                # Return False if monitoring infrastructure doesn't exist
                if not hasattr(self, '_pulse_guide_monitor') or not self._pulse_guide_monitor:
                    return False
                
                current_time = datetime.now()
                active_pulses = []
                
                # Check each axis for active pulse guides
                for axis in ['ns', 'ew']:
                    if self._is_axis_pulse_active(axis, current_time):
                        active_pulses.append(axis)
                        
                return len(active_pulses) > 0
                
        except Exception as ex:
            raise RuntimeError(f"Failed to check pulse guide status", ex)


    def _is_axis_pulse_active(self, axis: str, current_time: datetime) -> bool:
        """
        Check if pulse guide is active on specified axis and stop if expired.
        
        Args:
            axis: Axis identifier ('ns' or 'ew')
            current_time: Current timestamp for duration calculation
            
        Returns:
            bool: True if pulse guide is still active on this axis
            
        Raises:
            Exception: Propagates any timing or threading errors
        """
        with self._lock:
            monitor = self._pulse_guide_monitor.get(axis)
            
            # No monitor or monitor completed
            if not monitor or monitor.done():
                return False
            
            # Get axis-specific timing attributes
            start_attr = f'_pulse_guide_{axis}_start'
            duration_attr = f'_pulse_guide_{axis}_duration'
            stop_event_attr = f'_stop_pulse_{axis}'
            
            try:
                start_time = getattr(self, start_attr)
                duration_ms = getattr(self, duration_attr)
                stop_event = getattr(self, stop_event_attr)
                
                # Calculate elapsed time in seconds
                elapsed_seconds = (current_time - start_time).total_seconds()
                duration_seconds = duration_ms / 1000.0
                
                # Stop pulse if duration exceeded
                if elapsed_seconds >= duration_seconds:
                    stop_event.set()
                    return False
                    
                return True
                
            except (AttributeError, TypeError, ValueError) as ex:
                # Attribute access or timing calculation error - consider pulse inactive
                self._logger.warning(f"Pulse guide timing error for {axis} axis: {ex}")
                return False
        
    # Target Properties
    @property
    def TargetDeclination(self) -> float:
        """Target declination in degrees."""
        #TODO: Don't need to worry about this, get rid of this internal variables
        #if not self._target_declination_set:
        #    raise RuntimeError("Target declination not set")
        #else:
        
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        try:
            command = ":*Gd#"
            declination_rad = float(self._send_command(command, CommandType.STRING).rstrip("#"))
            declination_deg = declination_rad * 180 / math.pi
            return declination_deg
        except Exception as ex:
            self._logger.info(f"Failed to get TargetDeclination: {ex}")
            raise RuntimeError("Failed to get TargetDeclination", ex)
    
    @TargetDeclination.setter
    def TargetDeclination(self, value: float) -> None:
        """Set target declination."""
            
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        try:
            self._validate_coordinates(dec = value)
        except:
            raise

        try:
            # Send to mount
            self._logger.debug(f"Set Target Declination - Received: {value}")
            dms_str = self._degrees_to_dms(value)
            self._logger.debug(f"Set Target Declination - Conversion: {dms_str}")
            #TODO: Verify that this is what C# driver is doing.  Assuming negative unless a + in front?!
            #sign = "+" if value >= 0 else "-"
            #command = f":Sd{sign}{dms_str}#"
            
            command = f":Sd{dms_str}#"  #_degrees_to_dms returns a signed string already

            result = self._send_command(command, CommandType.BOOL)
            if not result:
                raise RuntimeError(f"Mount rejected target declination assignment: {value}")
            
            # Update state
            #with self._lock:
            #    self._target_declination_set = True
            #    if self._target_right_ascension_set:
            #        self._is_target_set = True
                
        except Exception as ex:
            raise RuntimeError(f"Failed to set target declination {value}", ex)
    
    @property
    def TargetRightAscension(self) -> float:
        """Target right ascension in hours.""" 
        #if not self._target_right_ascension_set:
        #    raise InvalidOperationException("Target Right Ascension not set")
        #else:
        
        if not self.Connected:
            raise ConnectionError("Device not connected")

        try:
            command = ":*Gr#"
            right_ascension_rad = float(self._send_command(command, CommandType.STRING).rstrip("#"))
            right_ascension_hr = (right_ascension_rad * 180 / math.pi * 24 / 360) % 24
            return right_ascension_hr
        except Exception as ex:
            self._logger.info(f"Failed to get TargetRightAscension: {ex}")
            raise RuntimeError("Failed to get TargetRightAscension", ex)
    
    @TargetRightAscension.setter
    def TargetRightAscension(self, value: float) -> None:
        """Set target right ascension."""
        if not self.Connected:
            raise ConnectionError("Device not connected")
        
        try:
            self._validate_coordinates(ra = value)
        except:
            raise
        
        try:
            # Send to mount
            hms_str = self._hours_to_hms(value)
            command = f":Sr{hms_str}#"
            
            result = self._send_command(command, CommandType.BOOL)
            if not result:
                raise RuntimeError(f"Mount rejected target right ascension assignment: {value}")
            
            # Update state
            #with self._lock:
            #    self._target_right_ascension_set = True
            #    if self._target_declination_set:
            #        self._is_target_set = True
                
        except Exception as ex:
            raise RuntimeError(f"Failed to set target right ascension {value}", ex)
    
    # Operation Methods
    def AbortSlew(self) -> None:
        """Abort any current slewing."""
        try:
            
            #TODO: Look how to verify monitor threads are appropriately closed
            self._logger.info("Abort command initiated")
            self._goto_in_progress = False
            self._send_command(":Q#", CommandType.BLIND)
            
        except Exception as ex:
            raise RuntimeError("AbortSlew failed", ex)
    
    def FindHome(self):
        """
        Locates the telescope's home position (asynchronous).
        
        Uses cached coordinate frames for efficient Alt/Az to equatorial transformations
        during home position calculations and reachability testing.
        
        Raises:
            InvalidOperationException: Mount parked, slewing, or home below horizon
            DriverException: Command execution or coordinate transformation failure
        """
        # State validation
        if not self.Connected:
            raise ConnectionError("Not connected to device")
        
        if self.AtPark:
            raise RuntimeError("Cannot FindHome: the mount is parked.")

        if self.Slewing:
            raise RuntimeError("Cannot FindHome: the mount is slewing.")

        self._logger.info("Moving to Home")

        try:        
            if self.AtHome:
                self._logger.info("Mount is already at Home")
                return

            # Get park position from mount
            park_status = self._send_command(":*PG#", CommandType.STRING)
            park_type = int(park_status[0])
            park_az = float(park_status[1:8])
            park_alt = float(park_status[8:14])

            self._logger.info(f"Home position: type={park_type}, Az={park_az:.2f} deg, Alt={park_alt:.2f} deg")

            # Get cached coordinate frames for transformations
            altaz_frame = self._get_frame_cache('altaz', timing_critical=False)
            gcrs_frame = self._get_frame_cache('gcrs', timing_critical=False)
            
            if park_type == 1 and int(park_alt) > 0:
                # Use stored park position if above horizon
                success = self._attempt_home_slew(park_az, park_alt, gcrs_frame, altaz_frame)
                if success:
                    return
                raise RuntimeError("Home position is below horizon, check mount alignment")        
            else:
                # Search for reachable position at same azimuth
                self._logger.debug("Searching for reachable home position above horizon")
                for target_alt in range(10):
                    self._logger.debug(f"Testing home position at Az={park_az:.2f} deg, Alt={target_alt} deg")
                    success = self._attempt_home_slew(park_az, target_alt, gcrs_frame, altaz_frame)
                    if success:
                        return
                
                raise RuntimeError("Home position is below horizon, check mount alignment")
            
        except Exception as ex:
            self._logger.error(f"FindHome error: {ex}")
            raise

    def _attempt_home_slew(self, az: float, alt: float, gcrs_frame, altaz_frame) -> bool:
        """
        Attempt to slew to home position at specified Alt/Az coordinates.
        
        Args:
            az: Azimuth in degrees
            alt: Altitude in degrees  
            gcrs_frame: Cached GCRS coordinate frame
            altaz_frame: Cached AltAz coordinate frame
            
        Returns:
            bool: True if slew started successfully, False otherwise
        """
        try:
            # Create AltAz coordinate using cached frame
            altaz_coord = SkyCoord(
                az=az * u.deg, 
                alt=alt * u.deg,
                frame=altaz_frame
            )
            
            # Convert to GCRS using cached frame
            gcrs_coord = altaz_coord.transform_to(gcrs_frame)
            
            self._logger.debug(f"Converted to equatorial: RA={gcrs_coord.ra.hour:.6f}h, Dec={gcrs_coord.dec.deg:.6f} deg")

            self.TargetDeclination = gcrs_coord.dec.deg
            self.TargetRightAscension = gcrs_coord.ra.hour

            # Try to slew - returns False if target is reachable (slew starts)
            if not bool(int(self._send_command(":MS#", CommandType.STRING))):
                with self._lock:
                    self._slewing_hold = True  # Allows immediate return of slewing property being true
                self._slew_in_progress = self._executor.submit(self._slew_status_monitor)
                self._executor.submit(self._home_arrival_monitor, az, alt)
                self._logger.info(f"Started slew to home position: Az={az:.2f} deg, Alt={alt:.2f} deg")
                self._goto_in_progress = True
                return True
                
            return False
            
        except Exception as ex:
            self._logger.debug(f"Home slew attempt failed at Az={az:.2f} deg, Alt={alt:.2f} deg: {ex}")
            return False
    
    def _slew_status_monitor(self) -> None:
        """
        Monitor mount slewing status until completion.
        
        Continuously polls mount hardware using LX200 distance command to detect
        when slewing stops. Applies settle time for goto operations only.
        
        Raises:
            DriverException: If status monitoring fails or mount communication error
        """
        try:
            # Poll hardware until slewing stops
            with self._lock:
                self._slewing_hold = False #with the monitor running, slewing will be True, so remove the hold

            while True:
                try:
                    status = self._send_command(":D#", CommandType.STRING)
                    if status != "|#":
                        break
                    time.sleep(0.1)  # 100ms polling interval
                except Exception as ex:
                    self._logger.error(f"Error polling slew status: {ex}")
                    raise RuntimeError(f"Slew status monitoring failed", ex)
            
            # Apply settle time only for goto operations
            if self._goto_in_progress:
                settle_time = self._config.slew_settle_time
                if settle_time > 0:
                    self._logger.info(f"Applying slew settle time: {settle_time}s")
                    time.sleep(settle_time)
                self._goto_in_progress = False
                self._logger.info("Slew operation completed")

        except Exception as ex:
            self._logger.error(f"Unexpected error in slew monitoring: {ex}")
            raise RuntimeError(f"Slew status monitoring error", ex)

    def _home_arrival_monitor(self, target_azimuth: float, target_altitude: float) -> None:
        """
        Monitor home arrival and verify position accuracy.
        
        Waits for slewing to complete then validates mount reached home position
        within acceptable tolerances (±2° altitude, ±5° azimuth from target).
        
        Args:
            target_azimuth: Expected azimuth at home position
            target_altitude: Expected altitude at home position
            
        Raises:
            DriverException: If home verification fails or position inaccurate
        """
        try:
            # Wait for slewing to complete
        
            self._logger.debug(f"Home Arrival Monitored - Started")

            while self.Slewing:
                time.sleep(0.01)
            
            self._logger.debug(f"Home Arrival Monitor - Slewing Complete, setting slewing override, verifying arrival")

            with self._lock:
                self._slewing_hold = True #Hold slewing true during slow verification operation

            # Verify home position
            current_alt = self.Altitude
            current_az = self.Azimuth
            
            altitude_error = abs(current_alt - target_altitude)
            azimuth_error = abs(target_azimuth - current_az)  #need to check for azimuth wraparound case!
            
            if altitude_error < self.HOME_POSITION_TOLERANCE_ALT and azimuth_error < self.HOME_POSITION_TOLERANCE_AZ:
                self.AtHome = True
                self._logger.info(f"Arrived at home: Alt={current_alt:.1f}°, Az={current_az:.1f}°")
                with self._lock:
                    self._slewing_hold = False
            else:
                error_msg = f"Home position verification failed - Alt: {current_alt:.1f}°, Az: {current_az:.1f}°"
                self._logger.error(error_msg)
                with self._lock:
                    self._slewing_hold = False
                raise RuntimeError(error_msg)
            
            self.Tracking = False

        except Exception as ex:
            self._logger.error(f"Home arrival monitoring failed: {ex}")
            with self._lock:
                    self._slewing_hold = False
            raise RuntimeError(f"Home arrival monitoring error", ex)
    
    def MoveAxis(self, axis: TelescopeAxes, rate: float) -> None:
        """
        Move telescope axis at specified rate using extended firmware commands.
        
        Converts rate to timing pulses using fraction-based precision control.
        Sends LX200-compatible movement commands with 4-digit numerator/denominator.
        
        Args:
            axis: TelescopeAxes.axisPrimary (0) or TelescopeAxes.axisSecondary (1)
            rate: Movement rate in degrees/second (-3.5 to +3.5)
            
        Raises:
            InvalidOperationException: If mount is parked or goto in progress
            InvalidValueException: If rate exceeds limits or invalid axis
            DriverException: For other errors
        """
        
                    
        # Validation checks
        if self._is_parked:
            raise RuntimeError("Cannot move axis: mount is parked")
        
        if abs(rate) > self._MAX_RATE:
            raise ValueError(f"Rate {rate} exceeds limit ±{self._MAX_RATE} deg/sec")
        
        if axis not in self._AXIS_COMMANDS:
            raise ValueError(f"Invalid axis: {axis}")

        if self._goto_in_progress:
            raise RuntimeError("Cannot execute MoveAxis while Goto is in progress")

        try:
            self._logger.debug(f"MoveAxis called: axis={axis}, rate={rate}")

            # Handle stop case (rate == 0)
            if rate == 0:
                self._logger.info(f"Stopping {self._AXIS_COMMANDS[axis]['name']} Axis")
                self._send_command(self._AXIS_COMMANDS[axis]['stop'], CommandType.BLIND)
                return

            # Calculate timing parameters
            abs_rate = abs(rate)
            time_to_pulse = (self._CLOCK_FREQ * self._TICKS_PER_PULSE) / (abs_rate * self._TICKS_PER_DEGREE[axis])
            
            self._logger.debug(f"TTP: ({self._CLOCK_FREQ} * {self._TICKS_PER_PULSE}) / ({abs_rate} * {self._TICKS_PER_DEGREE[axis]}) = {time_to_pulse}")
            
            # Convert 1/TTP to fraction (matching C# RealToFraction behavior)
            inverse_ttp = 1.0 / time_to_pulse
            frac = Fraction(inverse_ttp).limit_denominator(99999)
            num, den = frac.numerator, frac.denominator
            
            self._logger.debug(f"Initial fraction: {num}/{den} = {num/den:.6f}")
            
            # Scale to fit 4-digit hardware constraints (matching C# logic)
            if den < 4999:
                # Scale up denominator toward 4999
                mult = 4999 // den
                num *= mult
                den *= mult
                self._logger.debug(f"Scaled up by {mult}: {num}/{den}")
            elif den > 9999:
                # Scale down to fit 4-digit limit
                mult = math.ceil(den / 9999)
                original_ratio = num / den
                den = round(den / mult)
                num = round(original_ratio * den)
                self._logger.debug(f"Scaled down by {mult}: {num}/{den}")
            
            # Handle edge case where scaling results in zero numerator
            if num == 0:
                den = 9999
                self._logger.debug("Numerator became 0, setting den=9999")
            
            # Ensure 4-digit limits
            num = min(abs(num), 9999)
            den = min(den, 9999)
            
            result_rate = num / den if den != 0 else 0
            self._logger.info(f"MoveAxis - Num: {num}; Den: {den}; Result: {result_rate:.6f}")
            
            # Build and send command
            cmd_base = (self._AXIS_COMMANDS[axis]['pos'] if rate > 0 
                    else self._AXIS_COMMANDS[axis]['neg'])
            command = f"{cmd_base}{num:04d}{den:04d}#"
            
            self._logger.info(f"Sending Command: {command}")
            self._send_command(command, CommandType.BLIND)
            
            # Update movement state
            if self._slew_in_progress is None or self._slew_in_progress.done():
                self._slew_in_progress = self._executor.submit(self._slew_status_monitor)
            self._is_at_home = False
   
        except Exception as ex:
            self._logger.error(f"MoveAxis error: {ex}")
            raise RuntimeError(f"MoveAxis Error", ex)

    def SyncToAltAz(self, azimuth: float, altitude: float) -> None:
        """
        Synchronize mount position to given Alt/Az coordinates.
        
        Args:
            azimuth: Target azimuth in degrees (0-360, North=0°, East=90°)
            altitude: Target altitude in degrees (0-90, positive above horizon)
            
        Raises:
            NotConnectedException: If device not connected
            ParkedException: If mount is parked
            InvalidValueException: If coordinates outside valid ranges
            DriverException: If coordinate conversion or sync fails
        """
        if not self._Connected:
            raise ConnectionError("Device not connected")
        
        if self.AtPark:
            raise RuntimeError("Cannot sync while parked")
        
        # Validate coordinate ranges
        try:
            self._validate_coordinates(alt = altitude, az = azimuth)
        except:
            raise
        
        try:
            self._logger.info(f"Syncing to Alt/Az: {azimuth:.3f}°, {altitude:.3f}°")
            
            # Convert to equatorial coordinates
            right_ascension, declination = self._altaz_to_radec(azimuth, altitude)
            
            # Perform equatorial sync
            self.SyncToCoordinates(right_ascension, declination)
            
        except Exception as ex:
            self._logger.error(f"Alt/Az sync failed: {ex}")
            raise RuntimeError(f"Sync to Alt/Az failed", ex)

    def SyncToCoordinates(self, right_ascension: float, declination: float) -> None:
        """
        Synchronize mount position to given equatorial coordinates.
        
        Args:
            right_ascension: Target RA in hours (0-24)
            declination: Target declination in degrees (-90 to +90)
            
        Raises:
            NotConnectedException: If device not connected
            ParkedException: If mount is parked
            InvalidValueException: If coordinates outside valid ranges
            DriverException: If sync operation fails
        """
        if not self._Connected:
            raise ConnectionError("Device not connected")
        
        if self.AtPark:
            raise RuntimeError("Cannot sync while parked")
        
        # Validate coordinate ranges
        try:
            self._validate_coordinates(ra = right_ascension, dec = declination)
        except:
            raise
        
        try:
            self._logger.info(f"Syncing to RA {right_ascension:.3f}h, Dec {declination:.3f}°")
            
            # Set target coordinates
            self.TargetRightAscension = right_ascension
            self.TargetDeclination = declination
            
            # Execute sync command (basic sync, not auto-align)
            sync_result = self._send_command(":CM#", CommandType.STRING)
            
            # Apply sync settling time per LX200 specification
            time.sleep(self._sync_wait_time)
            
            self._logger.info("Coordinate sync completed")
            
        except Exception as ex:
            self._logger.error(f"Coordinate sync failed: {ex}")
            raise RuntimeError(f"Synchronization failed", ex)

    def SyncToTarget(self) -> None:
        """
        Synchronize mount position to current target coordinates.
        
        Raises:
            NotConnectedException: If device not connected
            ParkedException: If mount is parked
            InvalidOperationException: If target coordinates not set
            DriverException: If sync operation fails
        """
        if not self._Connected:
            raise ConnectionError("Device not connected")
        
        if self.AtPark:
            raise RuntimeError("Cannot sync while parked")
        
        try:
            self._logger.info("Syncing to target coordinates")
            
            # Execute sync command (basic sync, not auto-align)
            sync_result = self._send_command(":CM#", CommandType.STRING)
            
            # Apply sync settling time per LX200 specification
            time.sleep(self._sync_wait_time)
            
            self._logger.info("Target sync completed")
            
        except Exception as ex:
            self._logger.error(f"Target sync failed: {ex}")
            raise RuntimeError(f"Target synchronization failed", ex)


    def SlewToAltAz(self, azimuth: float, altitude: float) -> None:
        """Slew to given altaz coordinates (synchronous)."""
        raise NotImplementedError()
    
    def SlewToAltAzAsync(self, azimuth: float, altitude: float) -> None:
        """
        Start asynchronous slew to Alt/Az coordinates.
        
        Args:
            azimuth: Target azimuth in degrees (0-360, North=0°, East=90°)
            altitude: Target altitude in degrees (0-90, positive above horizon)
            
        Raises:
            NotConnectedException: If device not connected
            InvalidOperationException: If already slewing or tracking enabled
            ParkedException: If mount is parked
            InvalidValueException: If coordinates outside valid ranges
            DriverException: If coordinate conversion or slew initiation fails
        """
        if not self._Connected:
            raise ConnectionError("Device not connected")
        
        if self.Slewing:
            raise RuntimeError("Cannot start slew while already slewing")
        
        if self.Tracking:
            raise RuntimeError("Cannot slew to Alt/Az while tracking enabled")
        
        if self.AtPark:
            raise RuntimeError("Cannot slew while parked")
        
        # Validate coordinate ranges
        self._validate_coordinates(alt = altitude, az = azimuth)
        
        try:
            self._logger.info(f"Starting slew to Alt/Az: {azimuth:.3f}°, {altitude:.3f}°")
            
            # Convert to equatorial coordinates
            right_ascension, declination = self._altaz_to_radec(azimuth, altitude)
            
            # Execute equatorial slew
            self.SlewToCoordinatesAsync(right_ascension, declination)
            
        except Exception as ex:
            self._logger.error(f"Alt/Az async slew failed: {ex}")
            raise RuntimeError(f"Alt/Az slew initiation failed", ex)

    def SlewToCoordinates(self, rightAscension: float, declination: float) -> None:
        """Slew to given equatorial coordinates (synchronous)."""
        raise NotImplementedError()
    
    def SlewToCoordinatesAsync(self, right_ascension: float, declination: float) -> None:
        """
        Start asynchronous slew to equatorial coordinates.
        
        Args:
            right_ascension: Target RA in hours (0-24)
            declination: Target declination in degrees (-90 to +90)
            
        Raises:
            NotConnectedException: If device not connected
            InvalidOperationException: If already slewing
            InvalidValueException: If coordinates outside valid ranges
            DriverException: If target setting or slew initiation fails
        """
        if not self._Connected:
            raise ConnectionError("Device not connected")
        
        if self.AtPark:
            raise RuntimeError("Cannot SlewToCoordinatesAsync while parked")

        if self.Slewing:
            raise RuntimeError("Cannot start slew while already slewing")
        
        try:
            self._validate_coordinates(ra = right_ascension, dec = declination)
        except:
            raise
        
        try:
            self._logger.info(f"Starting slew to RA {right_ascension:.3f}h, Dec {declination:.3f}°")
            
            # Set target coordinates (includes validation)
            self.TargetRightAscension = right_ascension  
            self.TargetDeclination = declination
            
            self.SlewToTargetAsync()
            
        except Exception as ex:
            self._logger.error(f"Coordinate async slew failed: {ex}")
            raise RuntimeError(0x500, f"Coordinate slew initiation failed: {ex}")
    
    def SlewToTarget(self) -> None:
        """Slew to current target coordinates (synchronous)."""
        raise NotImplementedError()        

    
    def SlewToTargetAsync(self) -> None:
        """
        Start asynchronous slew to current target coordinates.
        
        Raises:
            NotConnectedException: If device not connected
            InvalidOperationException: If target not set or already slewing
            ParkedException: If mount is parked
            DriverException: If slew command fails or target below horizon
        """
        if not self._Connected:
            raise ConnectionError("Device not connected")
        
        #if not self._is_target_set:
        #    raise RuntimeError("Target coordinates not set")
        
        if self.Slewing:
            raise RuntimeError("Cannot start slew while already slewing")
        
        if self.AtPark:
            raise RuntimeError("Cannot slew while parked")
        
        try:
            with self._lock:
                self._logger.info("Starting slew to target coordinates")
                
                # Send slew command
                result = self._send_command(":MS#", CommandType.STRING)
                
                # Parse LX200 slew response
                if result.startswith("1"):
                    raise RuntimeError("Target object below horizon")
                elif result.startswith("2"):
                    raise RuntimeError("Target object below higher limit")
                elif not result.startswith("0"):
                    raise RuntimeError(f"Unexpected slew response: {result}")
                
                # Set up movement monitoring
                self._goto_in_progress = True
                self._slew_in_progress = self._executor.submit(self._slew_status_monitor)
                self.AtHome = False
                
                self._logger.info("Target slew initiated successfully")
                
        except Exception as ex:
            self._logger.error(f"Unexpected target slew error: {ex}")
            raise RuntimeError(f"Target slew initiation failed", ex)
    
    def PulseGuide(self, direction: GuideDirections, duration: int) -> None:
        """
        Pulse guide in specified direction for given duration.
        
        Implements timing-critical coordinate frame caching to minimize delays during
        pulse guide operations when using equatorial frame conversion.
        
        Args:
            direction: Guide direction (North/South/East/West)
            duration: Duration in milliseconds (0-9999)
            
        Raises:
            InvalidValueException: Invalid direction or duration
            InvalidOperationException: Mount parked, slewing, or axis conflict
            DriverException: Command execution or conversion failure
        """
        # Input validation
        try:
            direction = GuideDirections(direction)
        except:
            raise ValueError(f"Invalid guide direction: {direction}")
        
        if not isinstance(direction, GuideDirections):
            raise ValueError(f"Invalid guide direction: {direction}")
        if not 0 <= duration <= 9999:
            raise ValueError(f"Duration {duration} outside valid range 0-9999 msec")
        
        # State validation
        if self._is_parked:
            raise RuntimeError("Cannot move axis: mount is parked")
        if self.Slewing:
            raise RuntimeError("Cannot pulse guide while slewing")

        with self._lock:
            
            self._logger.debug("Pulseguide - Checking for pulseguide conflicts")
            # Check for axis conflicts
            if not self._config.pulse_guide_equatorial_frame: #equatorial frame guiding will use both axes for each guide
                self._check_pulse_guide_conflicts(direction)
            self._logger.debug("Pulseguide - No conflicts found, initializing monitors as necessary")

            # Initialize monitoring infrastructure if needed
            self._initialize_pulse_guide_monitoring()
            self._logger.debug("Pulse guide monitors initialized")

            try:
                # Cache management for timing-critical operations
                cache_refresh_needed = []
                if self._config.pulse_guide_equatorial_frame:
                    # Check cache freshness before timing-critical conversion
                    cache_refresh_needed = self._check_cache_freshness(['altaz', 'gcrs'])
                    if cache_refresh_needed:
                        self._logger.debug(f"Deferring cache refresh for timing-critical pulse guide: {cache_refresh_needed}")
                
                # Determine pulse parameters based on configuration
                if self._config.pulse_guide_equatorial_frame:
                    self._logger.info(f"PulseGuide - Converting {direction} for {duration} msec to the equatorial frame.")
                    ns_dir, ns_dur, ew_dir, ew_dur, additional_refresh = self._convert_equatorial_pulse(
                        direction, duration, timing_critical=True
                    )
                    # Merge any additional refresh needs from conversion
                    if additional_refresh:
                        cache_refresh_needed.extend(additional_refresh)
                        cache_refresh_needed = list(set(cache_refresh_needed))  # Remove duplicates
                    self._logger.info(f"PulseGuide Equatorial results: {ns_dir} for {ns_dur} msec; {ew_dir} for {ew_dur} msec")
                else:
                    ns_dir, ns_dur, ew_dir, ew_dur = self._get_standard_pulse_params(direction, duration)
                
                # Execute pulse guide commands
                self._logger.debug("PulseGuide - Commencing")
                self._execute_pulse_guide(ns_dir, ns_dur, ew_dir, ew_dur, duration)
                
                # Refresh stale caches after timing-critical operation completes
                if cache_refresh_needed:
                    try:
                        self._logger.debug("Refreshing coordinate frame caches after pulse guide completion")
                        self._refresh_expired_caches(cache_refresh_needed)
                    except Exception as ex:
                        # Cache refresh failure shouldn't fail the pulse guide
                        self._logger.debug(f"Post-pulse cache refresh failed: {ex}")
                
            except Exception as ex:
                raise RuntimeError("Pulse guide failed", ex)


    def _check_pulse_guide_conflicts(self, direction: GuideDirections) -> None:
        """Check for active pulse guide conflicts on the same axis."""
        if not hasattr(self, '_pulse_guide_monitor'):
            return
            
        if direction in [GuideDirections.guideNorth, GuideDirections.guideSouth]:
            monitor = self._pulse_guide_monitor.get('ns')
            if monitor and not monitor.done():
                raise RuntimeError("North/South pulse guide already active")
        else:  # East/West
            monitor = self._pulse_guide_monitor.get('ew')
            if monitor and not monitor.done():
                raise RuntimeError("East/West pulse guide already active")


    def _initialize_pulse_guide_monitoring(self) -> None:
        """Initialize pulse guide monitoring infrastructure."""
        if not hasattr(self, '_pulse_guide_monitor'):
            self._stop_pulse_ns = threading.Event()
            self._stop_pulse_ew = threading.Event() 
            self._pulse_guide_monitor = {'ns': None, 'ew': None}


    def _get_standard_pulse_params(self, direction: GuideDirections, duration: int) -> Tuple[GuideDirections, int, GuideDirections, int]:
        """
        Get pulse parameters for standard (non-equatorial) mode.
        
        Returns:
            Tuple of (ns_direction, ns_duration, ew_direction, ew_duration)
        """
        ns_dir = GuideDirections.guideNorth
        ns_dur = 0
        ew_dir = GuideDirections.guideEast  
        ew_dur = 0
        
        if direction == GuideDirections.guideNorth:
            ns_dir = GuideDirections.guideNorth
            ns_dur = duration
        elif direction == GuideDirections.guideSouth:
            ns_dir = GuideDirections.guideSouth
            ns_dur = duration
        elif direction == GuideDirections.guideEast:
            ew_dir = GuideDirections.guideEast
            ew_dur = duration
        elif direction == GuideDirections.guideWest:
            ew_dir = GuideDirections.guideWest
            ew_dur = duration
        
        # Apply altitude compensation for East/West in standard mode
        if (self._config.pulse_guide_altitude_compensation and 
            direction in [GuideDirections.guideEast, GuideDirections.guideWest]):
            ew_dur = self._apply_altitude_compensation(ew_dur)

        return ns_dir, ns_dur, ew_dir, ew_dur


    def _convert_equatorial_pulse(self, direction: GuideDirections, duration: int, timing_critical: bool = False) -> Tuple[GuideDirections, int, GuideDirections, int, List[str]]:
        """
        Convert equatorial pulse guide command to alt/az pulse parameters.
        
        Transforms the requested RA/Dec motion into corresponding Alt/Az motions
        using cached coordinate transformation frames for optimal performance.
        
        Args:
            direction: Requested guide direction in equatorial frame
            duration: Requested duration in milliseconds
            timing_critical: If True, use potentially stale cache to avoid delays
            
        Returns:
            Tuple of (ns_direction, ns_duration, ew_direction, ew_duration, cache_refresh_needed)
            
        Raises:
            DriverException: Coordinate transformation failure
        """
        try:
            # Convert duration to seconds and get guide rate
            duration_sec = duration / 1000.0
            guide_rate = self.GuideRateDeclination  # deg/sec
            
            self._logger.debug(f"Converting equatorial pulse: {direction} for {duration}ms (rate={guide_rate:.6f}°/s)")

            # Calculate RA/Dec deltas based on equatorial direction
            delta_ra = 0.0  # degrees
            delta_dec = 0.0  # degrees
            
            if direction == GuideDirections.guideNorth:
                delta_dec = duration_sec * guide_rate
            elif direction == GuideDirections.guideSouth:
                delta_dec = -duration_sec * guide_rate
            elif direction == GuideDirections.guideEast:
                delta_ra = duration_sec * guide_rate
            elif direction == GuideDirections.guideWest:
                delta_ra = -duration_sec * guide_rate
            
            self._logger.debug(f"Computed deltas: RA={delta_ra:.6f}°, Dec={delta_dec:.6f}°")

            # Get current telescope position
            current_ra = self.RightAscension  # hours
            current_dec = self.Declination    # degrees
            
            # Calculate final equatorial position
            final_ra = current_ra + delta_ra / 15.0  # convert degrees to hours
            final_dec = current_dec + delta_dec
            
            self._logger.debug(f"Position transformation: ({current_ra:.6f}h, {current_dec:.6f}°) → ({final_ra:.6f}h, {final_dec:.6f}°)")

            # Get cached coordinate frames (potentially stale if timing_critical)
            cache_refresh_needed = []
            if timing_critical:
                cache_refresh_needed = self._check_cache_freshness(['gcrs', 'altaz'])
                if cache_refresh_needed:
                    self._logger.debug(f"Using potentially stale cache for timing-critical operation: {cache_refresh_needed}")
            
            gcrs_frame = self._get_frame_cache('gcrs', timing_critical=timing_critical)
            altaz_frame = self._get_frame_cache('altaz', timing_critical=timing_critical)

            # Transform current and final positions to AltAz using cached frames
            current_gcrs = SkyCoord(
                ra=current_ra * u.hour,
                dec=current_dec * u.deg,
                frame=gcrs_frame
            )
            current_altaz = current_gcrs.transform_to(altaz_frame)
            self._logger.debug(f"Current AltAz: Az={current_altaz.az.deg:.6f}°, Alt={current_altaz.alt.deg:.6f}°")

            final_gcrs = SkyCoord(
                ra=final_ra * u.hour,
                dec=final_dec * u.deg,
                frame=gcrs_frame
            )
            final_altaz = final_gcrs.transform_to(altaz_frame)
            self._logger.debug(f"Final AltAz: Az={final_altaz.az.deg:.6f}°, Alt={final_altaz.alt.deg:.6f}°")

            # Calculate Alt/Az deltas
            delta_alt = final_altaz.alt.deg - current_altaz.alt.deg
            delta_az = final_altaz.az.deg - current_altaz.az.deg
            
            # Handle azimuth wrap-around (choose shortest path)
            if delta_az > 180:
                delta_az -= 360
            elif delta_az < -180:
                delta_az += 360
                
            # Convert deltas to pulse durations
            ns_dur = abs(round(delta_alt / guide_rate * 1000))
            ew_dur = abs(round(delta_az / guide_rate * 1000))
            
            # Determine mount directions based on delta signs
            ns_dir = GuideDirections.guideSouth if delta_alt >= 0 else GuideDirections.guideNorth
            ew_dir = GuideDirections.guideEast if delta_az >= 0 else GuideDirections.guideWest
            
            self._logger.info(f"Converted to AltAz pulses: {ns_dir} {ns_dur}ms, {ew_dir} {ew_dur}ms")
            
            return ns_dir, ns_dur, ew_dir, ew_dur, cache_refresh_needed
            
        except Exception as ex:
            raise RuntimeError(f"Equatorial pulse conversion failed", ex)


    def _apply_altitude_compensation(self, duration: int) -> int:
        """
        Apply altitude compensation to East/West pulse duration.
        
        Compensates for the cosine effect where East/West motion appears
        slower at higher altitudes due to coordinate geometry.
        
        Args:
            duration: Original duration in milliseconds
            
        Returns:
            Compensated duration in milliseconds
            
        Raises:
            DriverException: Compensation calculation failure
        """
        try:
            alt = self.Altitude
            max_alt = self.MAX_ALTITUDE_FOR_COMPENSATION  # Prevent divide by zero near zenith
            
            if alt > max_alt:
                alt = max_alt
                
            alt_rad = math.radians(alt)
            compensated_duration = round(duration / math.cos(alt_rad))
            
            # Apply compensation limits to prevent excessive durations
            max_comp = self._config.pulse_guide_max_compensation
            buffer = self._config.pulse_guide_compensation_buffer
            
            if compensated_duration > (duration + max_comp):
                compensated_duration = duration + max_comp - buffer
                
            return max(0, compensated_duration)
            
        except Exception as ex:
            raise RuntimeError(f"Altitude compensation failed", ex)


    def _execute_pulse_guide(self, ns_dir: GuideDirections, ns_dur: int, 
                            ew_dir: GuideDirections, ew_dur: int, original_duration: int) -> None:
        """
        Execute pulse guide commands and start monitoring threads.
        
        Args:
            ns_dir: North/South direction
            ns_dur: North/South duration in milliseconds  
            ew_dir: East/West direction
            ew_dur: East/West duration in milliseconds
            original_duration: Original requested duration for synchronous mode
            
        Raises:
            DriverException: Command execution failure
        """
        # Hardware command mappings - standard mode (physically correct)
        command_map = {
            GuideDirections.guideEast: ":Mge{:04d}#",
            GuideDirections.guideWest: ":Mgw{:04d}#", 
            GuideDirections.guideNorth: ":Mgs{:04d}#",  # Note: North uses 's'
            GuideDirections.guideSouth: ":Mgn{:04d}#"   # Note: South uses 'n'
        }
        
        # For equatorial mode, swap East/West commands to match GuideDirections semantics
        if self._config.pulse_guide_equatorial_frame:
            command_map[GuideDirections.guideEast] = ":Mgw{:04d}#"  # Swapped
            command_map[GuideDirections.guideWest] = ":Mge{:04d}#"  # Swapped
        
        monitors_started = []
        
        try:
            # Execute North/South command if needed
            if ns_dur > 0:
                command = command_map[ns_dir].format(ns_dur)
                self._send_command(command, CommandType.BLIND)
                
                # Start NS monitoring
                self._pulse_guide_ns_duration = ns_dur
                self._pulse_guide_ns_start = datetime.now()
                self._stop_pulse_ns.clear()
                self._pulse_guide_monitor['ns'] = self._executor.submit(self._pulse_guide_monitor_ns)
                monitors_started.append('ns')
            
            # Execute East/West command if needed  
            if ew_dur > 0:
                command = command_map[ew_dir].format(ew_dur)
                self._send_command(command, CommandType.BLIND)
                
                # Start EW monitoring
                self._pulse_guide_ew_duration = ew_dur
                self._pulse_guide_ew_start = datetime.now()
                self._stop_pulse_ew.clear()
                self._pulse_guide_monitor['ew'] = self._executor.submit(self._pulse_guide_monitor_ew)
                monitors_started.append('ew')

            # Alpaca methods cannot be synchronous or a timeout error could result    
            # Handle synchronous mode
            #if self._config.pulse_guide_duration_synchronous:
            #    time.sleep(original_duration / 1000.0)
            #    # Signal monitors to stop
            #    if 'ns' in monitors_started:
            #        self._stop_pulse_ns.set()
            #    if 'ew' in monitors_started:
            #        self._stop_pulse_ew.set()
                    
        except Exception as ex:
            # Cleanup any started monitors on failure
            self._cleanup_failed_pulse_guide(monitors_started)
            raise RuntimeError(f"Pulse guide execution failed", ex)


    def _cleanup_failed_pulse_guide(self, monitors_started: list) -> None:
        """Clean up pulse guide monitors after execution failure."""
        for axis in monitors_started:
            if axis == 'ns':
                self._stop_pulse_ns.set()
                if self._pulse_guide_monitor['ns']:
                    self._pulse_guide_monitor['ns'].cancel()
                    self._pulse_guide_monitor['ns'] = None
            else:  # ew
                self._stop_pulse_ew.set()
                if self._pulse_guide_monitor['ew']:
                    self._pulse_guide_monitor['ew'].cancel()
                    self._pulse_guide_monitor['ew'] = None


    def _pulse_guide_monitor_ns(self) -> None:
        """Monitor North/South pulse guide duration."""
        try:
               
            start_time = self._pulse_guide_ns_start
            duration_ms = self._pulse_guide_ns_duration
            
            while not self._stop_pulse_ns.wait(0.05):
                if (datetime.now() - start_time).total_seconds() >= (duration_ms / 1000.0):
                    break
                    
        except Exception as ex:
            self._logger.error(f"Pulse guide NS monitor error: {ex}")
        finally:
            with self._lock:
                self._pulse_guide_monitor['ns'] = None


    def _pulse_guide_monitor_ew(self) -> None:
        """Monitor East/West pulse guide duration."""
        try:
                
            start_time = self._pulse_guide_ew_start
            duration_ms = self._pulse_guide_ew_duration
            
            while not self._stop_pulse_ew.wait(0.05):
                if (datetime.now() - start_time).total_seconds() >= (duration_ms / 1000.0):
                    break
                    
        except Exception as ex:
            self._logger.error(f"Pulse guide EW monitor error: {ex}")
        finally:
            with self._lock:
                self._pulse_guide_monitor['ew'] = None

    def _park_arrival_monitor(self) -> None:
        """
        Monitor park arrival to set parked flag.
        
        Waits for slewing to complete then sets park flag
        
        Args:
            None
            
        Raises:
            DriverException: If park arrival fails
        """
        try:
            # Wait for slewing to complete
            while self.Slewing:
                time.sleep(0.5)
            
            #Once the slew is stopped, query the mount until the parked flag is set
            #This prevents a gap after the slew while the mount is completeing 
            #its park routine
            with self._lock:
                while not self._is_parked:
                    self.AtPark
                    time.sleep(0.5)
                
        except Exception as ex:
            self._logger.error(f"Park monitoring failed: {ex}")
            raise RuntimeError(f"Park monitoring error", ex)
           

    def Park(self) -> None:
        """
        Park the mount at its designated park position.
        
        Raises:
            NotConnectedException: If device not connected
            InvalidOperationException: If already parked
            DriverException: If park initiation fails
        """
        if not self._Connected:
            raise ConnectionError("Device not connected")
        
        if self.AtPark:
            self._logger.info("Mount already parked")
            raise RuntimeError("Mount is already parked")
        
        try:
            self._logger.info("Parking mount")
            self._send_command(":hP#", CommandType.BLIND)           
            self._executor.submit(self._park_arrival_monitor)
            self._slew_in_progress = self._executor.submit(self._slew_status_monitor)

            self._logger.info("Mount initiated park successfully")
            
        except Exception as ex:
            self._logger.error(f"Park operation failed: {ex}")
            raise RuntimeError("Park failed", ex)
    
    def SetPark(self) -> None:
        """
        Set mount's park position to current position.
        
        Raises:
            NotConnectedException: If device not connected
            DriverException: If park position setting fails
        """
        if not self._Connected:
            raise ConnectionError("Device not connected")
        
        try:
            park_alt = round(self.Altitude, 3)
            park_az = round(self.Azimuth, 3)
            
            self._logger.info(f"Setting park position: Alt={park_alt:.3f}°, Az={park_az:.3f}°")
            
            # Update configuration
            self._config.park_location = True
            self._config.park_location_altitude = park_alt
            self._config.park_location_azimuth = park_az
            
            # Send to mount (format: DDD.ddd for azimuth, DD.ddd for altitude)
            command = f":*PS1{park_az:07.3f}{park_alt:06.3f}#"
            self._send_command(command, CommandType.BLIND)
            self._config.save()
            
            self._logger.info("Park position set successfully")
            
        except Exception as ex:
            self._logger.error(f"SetPark failed: {ex}")
            raise RuntimeError(f"SetPark failed", ex)
    
    def Unpark(self) -> None:
        """Unpark Mount."""
        raise NotImplementedError()    

    # UTC Date Property
    @property
    def UTCDate(self) -> datetime:
        """
        Mount's UTC date and time.
        
        Returns:
            datetime: Current UTC date/time from mount
            
        Raises:
            NotConnectedException: If device not connected
            DriverException: If date/time retrieval fails
        """
        if not self._Connected and not self._Connecting:
            raise ConnectionError("Device not connected")
        
        try:
            # Get local date and time from mount
            local_date = self._send_command(":GC#", CommandType.STRING)
            local_time = self._send_command(":GL#", CommandType.STRING) 
            utc_offset = self._send_command(":GG#", CommandType.STRING)
            
            # Parse date (MM/DD/YY format)
            month, day, year = map(int, local_date.rstrip('#').split('/'))
            year += 2000  # Convert 2-digit year
            
            # Parse time (HH:MM:SS format)
            hour, minute, second = map(int, local_time.rstrip('#').split(':'))
            
            # Parse UTC offset
            offset_hours = float(utc_offset.rstrip('#'))
            
            # Create local datetime and convert to UTC
            local_dt = datetime(year, month, day, hour, minute, second)
            utc_dt = local_dt + timedelta(hours=offset_hours)
            
            utc = utc_dt.replace(tzinfo=timezone.utc)
            self._logger.info(f"Mount UTC time: {utc}")
            self._logger.debug(f"Mount UTC time as ISO 8601 string: {utc.isoformat().replace('+00:00', 'Z')}")

            return utc.isoformat().replace('+00:00', 'Z')
            
        except Exception as ex:
            self._logger.error(f"Failed to get UTC date: {ex}")
            raise RuntimeError("Failed to get UTC date", ex)


    @UTCDate.setter
    def UTCDate(self, value: Union[datetime, str]) -> None:
        """
        Set mount's UTC date and time.
        
        Args:
            value: UTC datetime to set
            
        Raises:
            NotConnectedException: If device not connected
            InvalidValueException: If invalid datetime provided
            DriverException: If date/time setting fails
        """
        if not self._Connected and not self._Connecting:
            raise ConnectionError("Device not connected")
    
        if isinstance(value, str):
            try:
                value = parser.isoparse(value)
            except ValueError:
                raise ValueError(f"Invalid ISO 8601 format: {value}")
        elif not isinstance(value, datetime):
            raise TypeError(f"Error: {value} is not a datetime object or string.")
            # Use datetime directly

        try:
            # Get UTC offset from mount
            utc_offset = self._send_command(":GG#", CommandType.STRING)
            offset_hours = float(utc_offset.rstrip('#'))
            
            # Convert UTC to local time
            self._logger.debug(f"Set UTCDate - Passed Value: {value}; offset Hours {offset_hours}")
            local_dt = value - timedelta(hours=offset_hours)
            
            self._logger.info(f"Setting mount time to: {local_dt}")

            # Set date (MM/dd/yy format)
            date_str = local_dt.strftime("%m/%d/%y")
            date_response = self._send_command(f":SC{date_str}#", CommandType.STRING)
            if not (date_response.rstrip('#') == '1'):
                raise RuntimeError(f"Invalid date: {date_str}")
            
            # Set time (HH:mm:ss format)
            time_str = local_dt.strftime("%H:%M:%S")
            time_response = self._send_command(f":SL{time_str}#", CommandType.STRING)
            if not (time_response.rstrip('#') == '1'):
                raise RuntimeError(f"Invalid time: {time_str}")
            
            # Firmware bug workaround - throwaway SiderealTime call
            _ = self.SiderealTime
            
            self._invalidate_all_caches()

            self._logger.info("Mount time set successfully")
            
        except (ConnectionError, ValueError):
            raise
        except Exception as ex:
            self._logger.error(f"Failed to set UTC date: {ex}")
            raise RuntimeError("Failed to set UTC date", ex)

