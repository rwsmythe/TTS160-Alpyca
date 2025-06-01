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

# Local imports
from tts160_types import CommandType
from exceptions import (
    DriverException, InvalidValueException, InvalidOperationException,
    NotImplementedException, ParkedException, NotConnectedException
)
from telescope import (
    TelescopeMetadata, EquatorialCoordinateType, DriveRates, PierSide,
    AlignmentModes, TelescopeAxes, GuideDirections, Rate
)

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
    
    def CanMoveAxis(self, axis) -> bool:
        
        if axis in [TelescopeAxes.axisPrimary, TelescopeAxes.axisSecondary]:
            return self._CanMoveAxis
        else:
            return False
    
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
        """Get available rates for specified axis."""
        if axis in [TelescopeAxes.axisPrimary, TelescopeAxes.axisSecondary]:  # Primary and secondary axes
            return self._AxisRates
        else:
            return []
    
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
        """Get available tracking rates."""
        return self._DriveRates

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
    def DriverInfo(self) -> str:
        return self._DriverInfo

    @property
    def InterfaceVersion(self) -> int:
        return self.__InterfaceVersion
    
    @property
    def SupportedActions(self) -> List[str]:
        
        supported_actions: List[str] = [ "FieldRotationAngle" ]
        
        return supported_actions
    
    @property
    def AlignmentMode(self) -> AlignmentModes:
        return AlignmentModes.algAltAz

class ConfigurationMixin:
    @property
    def SlewSettleTime(self) -> int:
        return self._config.slew_settle_time
    
    @SlewSettleTime.setter
    def SlewSettleTime(self, value: int) -> None:
        
        try:
            if not 0 <= value <= 30:
                raise InvalidValueException(f"Invalid Slew Settle Time: {value}, value not saved.")
            
            with self._lock:
                self._config.slew_settle_time = value
        except Exception as ex:
            raise DriverException(0x500,ex)
    
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
    
class CoordinateUtilsMixin:
     # Coordinate Conversion Utilities
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
        try:
            if not isinstance(dms_str, str):
                raise InvalidValueException(f"DMS input must be string, got {type(dms_str)}")
            
            if not dms_str.strip():
                raise InvalidValueException("DMS string cannot be empty")
            
            # Clean string and extract sign
            cleaned = dms_str.rstrip('#').strip()
            self._logger.debug(f"Converting DMS string: '{dms_str}' -> '{cleaned}'")
            
            sign = -1 if cleaned.startswith('-') else 1
            cleaned = cleaned.lstrip('+-')
            
            # Split by common LX200 separators
            parts = cleaned.replace('*', ':').replace("'", ':').replace('"', ':').split(':')
            
            if len(parts) < 1 or len(parts) > 3:
                raise InvalidValueException(f"Invalid DMS format: expected 1-3 parts, got {len(parts)}")
            
            # Convert parts to float with validation
            try:
                degrees = float(parts[0])
                minutes = float(parts[1]) if len(parts) > 1 else 0.0
                seconds = float(parts[2]) if len(parts) > 2 else 0.0
            except ValueError as ex:
                raise InvalidValueException(f"Invalid numeric values in DMS string '{dms_str}': {ex}")
            
            # Validate ranges
            if degrees < 0:
                raise InvalidValueException(f"Degrees component cannot be negative in '{dms_str}' (use leading sign)")
            if not (0 <= minutes < 60):
                raise InvalidValueException(f"Minutes {minutes} outside valid range 0-59")
            if not (0 <= seconds < 60):
                raise InvalidValueException(f"Seconds {seconds} outside valid range 0-59")
            
            result = sign * (degrees + minutes/60.0 + seconds/3600.0)
            self._logger.debug(f"DMS conversion result: {result:.6f}°")
            return result
            
        except InvalidValueException:
            self._logger.error(f"DMS conversion failed: {dms_str}")
            raise
        except Exception as ex:
            self._logger.error(f"Unexpected error in DMS conversion '{dms_str}': {ex}")
            raise InvalidValueException(f"Invalid DMS format: {dms_str}")

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
        try:
            if not isinstance(hms_str, str):
                raise InvalidValueException(f"HMS input must be string, got {type(hms_str)}")
            
            if not hms_str.strip():
                raise InvalidValueException("HMS string cannot be empty")
            
            # Clean string
            cleaned = hms_str.rstrip('#').strip()
            self._logger.debug(f"Converting HMS string: '{hms_str}' -> '{cleaned}'")
            
            parts = cleaned.split(':')
            if len(parts) < 1 or len(parts) > 3:
                raise InvalidValueException(f"Invalid HMS format: expected 1-3 parts, got {len(parts)}")
            
            try:
                hours = float(parts[0])
                minutes = float(parts[1]) if len(parts) > 1 else 0.0
                seconds = float(parts[2]) if len(parts) > 2 else 0.0
            except ValueError as ex:
                raise InvalidValueException(f"Invalid numeric values in HMS string '{hms_str}': {ex}")
            
            # Validate ranges
            if not (0 <= hours < 24):
                raise InvalidValueException(f"Hours {hours} outside valid range 0-23")
            if not (0 <= minutes < 60):
                raise InvalidValueException(f"Minutes {minutes} outside valid range 0-59")
            if not (0 <= seconds < 60):
                raise InvalidValueException(f"Seconds {seconds} outside valid range 0-59")
            
            result = hours + minutes/60.0 + seconds/3600.0
            self._logger.debug(f"HMS conversion result: {result:.6f}h")
            return result
            
        except InvalidValueException:
            self._logger.error(f"HMS conversion failed: {hms_str}")
            raise
        except Exception as ex:
            self._logger.error(f"Unexpected error in HMS conversion '{hms_str}': {ex}")
            raise InvalidValueException(f"Invalid HMS format: {hms_str}")

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
            current_time = Time.now()
            altaz_frame = AltAz(obstime=current_time, location=self._site_location)
            altaz_coord = SkyCoord(
                az=azimuth * u.deg,
                alt=altitude * u.deg,
                frame=altaz_frame
            )
            
            # Transform to ICRS (J2000)
            icrs_coord = altaz_coord.transform_to(ICRS())
            
            return icrs_coord.ra.hour, icrs_coord.dec.degree
            
        except Exception as ex:
            if isinstance(ex, InvalidValueException):
                raise
            raise DriverException(0x500, f"Alt/Az to ICRS conversion failed: {ex}")

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
            current_time = Time.now()
            altaz_frame = AltAz(obstime=current_time, location=self._site_location)
            altaz_coord = icrs_coord.transform_to(altaz_frame)
            
            # Normalize azimuth to 0-360 range
            azimuth = altaz_coord.az.degree
            if azimuth < 0:
                azimuth += 360
            elif azimuth >= 360:
                azimuth -= 360
                
            return azimuth, altaz_coord.alt.degree
            
        except Exception as ex:
            if isinstance(ex, InvalidValueException):
                raise
            raise DriverException(0x500, f"ICRS to Alt/Az conversion failed: {ex}")

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
            current_time = Time.now()
            altaz_frame = AltAz(obstime=current_time, location=self._site_location)
            altaz_coord = SkyCoord(
                az=azimuth * u.deg,
                alt=altitude * u.deg,
                frame=altaz_frame
            )
            
            # Transform to GCRS at current time (topocentric equatorial)
            gcrs_coord = altaz_coord.transform_to(GCRS(obstime=current_time))
            
            return gcrs_coord.ra.hour, gcrs_coord.dec.degree
            
        except Exception as ex:
            if isinstance(ex, InvalidValueException):
                raise
            raise DriverException(0x500, f"Alt/Az to GCRS conversion failed: {ex}")

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
            current_time = Time.now()
            gcrs_coord = SkyCoord(
                ra=right_ascension * u.hour,
                dec=declination * u.deg,
                frame=GCRS(obstime=current_time)
            )
            
            # Transform to AltAz
            altaz_frame = AltAz(obstime=current_time, location=self._site_location)
            altaz_coord = gcrs_coord.transform_to(altaz_frame)
            
            # Normalize azimuth to 0-360 range
            azimuth = altaz_coord.az.degree
            if azimuth < 0:
                azimuth += 360
            elif azimuth >= 360:
                azimuth -= 360
                
            return azimuth, altaz_coord.alt.degree
            
        except Exception as ex:
            if isinstance(ex, InvalidValueException):
                raise
            raise DriverException(0x500, f"GCRS to Alt/Az conversion failed: {ex}")

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
            current_time = Time.now()
            gcrs_coord = icrs_coord.transform_to(GCRS(obstime=current_time))
            
            # Normalize RA to 0-24 hour range
            ra_hours = gcrs_coord.ra.hour
            if ra_hours < 0:
                ra_hours += 24
            elif ra_hours >= 24:
                ra_hours -= 24
                
            return ra_hours, gcrs_coord.dec.degree
            
        except Exception as ex:
            if isinstance(ex, InvalidValueException):
                raise
            raise DriverException(0x500, f"ICRS to GCRS conversion failed: {ex}")

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
            current_time = Time.now()
            gcrs_coord = SkyCoord(
                ra=right_ascension * u.hour,
                dec=declination * u.deg,
                frame=GCRS(obstime=current_time)
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
            if isinstance(ex, InvalidValueException):
                raise
            raise DriverException(0x500, f"GCRS to ICRS conversion failed: {ex}")
    
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
            raise DriverException(0x500, "Sidereal time calculation failed", ex)

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
            
        except InvalidValueException:
            self._logger.error(f"Hour angle calculation failed: invalid RA {right_ascension}")
            raise
        except Exception as ex:
            self._logger.error(f"Hour angle calculation failed: {ex}")
            raise DriverException(0x500, "Hour angle calculation failed", ex)

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
                    raise InvalidValueException(f"Right ascension must be valid number, got {ra}")
                if not (0 <= ra <= 24):
                    raise InvalidValueException(f"Right ascension {ra} outside valid range 0-24 hours")
            
            if dec is not None:
                if not isinstance(dec, (int, float)) or math.isnan(dec) or math.isinf(dec):
                    raise InvalidValueException(f"Declination must be valid number, got {dec}")
                if not (-90 <= dec <= 90):
                    raise InvalidValueException(f"Declination {dec} outside valid range ±90 degrees")
            
            if alt is not None:
                if not isinstance(alt, (int, float)) or math.isnan(alt) or math.isinf(alt):
                    raise InvalidValueException(f"Altitude must be valid number, got {alt}")
                if not (0 <= alt <= 90):
                    raise InvalidValueException(f"Altitude {alt} outside valid range ±90 degrees")
            
            if az is not None:
                if not isinstance(az, (int, float)) or math.isnan(az) or math.isinf(az):
                    raise InvalidValueException(f"Azimuth must be valid number, got {az}")
                if not (0 <= az <= 360):
                    raise InvalidValueException(f"Azimuth {az} outside valid range 0-360 degrees")
                    
        except Exception as ex:
            self._logger.error(f"Coordinate validation failed: {ex}")
            raise

class TTS160Device(CapabilitiesMixin, ConfigurationMixin, CoordinateUtilsMixin):
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
            self._initialize_target_state()
            
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
        
        import TTS160Global
        
        try:
            self._config = TTS160Global.get_config()
            self._serial_manager = TTS160Global.get_serial_manager(self._logger)
        except ImportError as ex:
            raise DriverException(0x500, "TTS160Global module unavailable", ex)
        except Exception as ex:
                self._logger.error(f"Failed to load global configuration: {ex}")
                raise DriverException(0x500, "Configuration initialization failed", ex)
        
        # Serial manager initialization
        self._serial_manager = None
        try:
            self._logger.info("Instantiating serial manager")
            self._serial_manager = TTS160Global.get_serial_manager(self._logger)
            self._logger.debug("Serial manager instantiated successfully")
        except Exception as ex:
            self._logger.error(f"Serial manager instantiation failed: {ex}")
            raise DriverException(0x500, "Serial manager initialization failed", ex)

    def _initialize_capability_flags(self) -> None:
        """Initialize ASCOM capability flags per TTS160 hardware specifications."""
        self._CanFindHome = True
        self._CanMoveAxis = True
        self._CanPark = True
        self._CanPulseGuide = True
        self._CanSetDeclinationRate = False
        self._CanSetGuideRates = True
        self._CanSetPark = False
        self._CanSetPierSide = False
        self._CanSetRightAscensionRate = False
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
        self._logger.debug("Mount state variables initialized")

    def _initialize_target_state(self) -> None:
        """Initialize target coordinate state tracking."""
        self._is_target_set = False
        self._target_right_ascension_set = False
        self._target_declination_set = False
        self._logger.debug("Target state variables initialized")

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
        self._MAX_RATE = max(rate.maximum for rate in self._AxisRates)
        
        # LX200 command mappings for axis control
        self._AXIS_COMMANDS = {
            TelescopeAxes.axisPrimary: {
                'stop': ':Qe#', 'pos': ':*Me', 'neg': ':*Mw', 'name': 'Primary'
            },
            TelescopeAxes.axisSecondary: {
                'stop': ':Qn#', 'pos': ':*Mn', 'neg': ':*Ms', 'name': 'Secondary'
            }
        }
        
        self._sync_wait_time = 0.2

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

    #Cached vriables
    @property
    def _site_location(self):
        if not hasattr(self, '_site_location_cache'):
            self._site_location_cache = EarthLocation(
                lat=self._config.site_latitude * u.deg,
                lon=self._config.site_longitude * u.deg, 
                height=self._config.site_elevation * u.m
            )
        return self._site_location_cache

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
            raise DriverException(0x500, "Configuration not available for connection")
        
        if not hasattr(self, '_serial_manager') or self._serial_manager is None:
            self._logger.error("Connect failed: Serial manager not initialized") 
            raise DriverException(0x500, "Serial manager not available for connection")
        
        if not hasattr(self, '_executor') or self._executor is None:
            self._logger.error("Connect failed: Thread executor not initialized")
            raise DriverException(0x500, "Thread executor not available for connection")
        
        with self._lock:
            # Handle already connected (ASCOM shared connection pattern)
            if self._Connected:
                self._serial_manager.connection_count += 1
                self._logger.info(f"Already connected, reference count: {self._serial_manager.connection_count}")
                return
            
            # Handle connection in progress
            if self._Connecting:
                self._serial_manager.connection_count += 1
                self._logger.info(f"Connection in progress, reference count: {self._serial_manager.connection_count}")
                return

            # Start new connection
            self._Connecting = True
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
                raise DriverException(0x500, "Thread pool shutdown, cannot connect", ex)
            
            self._logger.info("Async connection process initiated successfully")

        except DriverException:
            with self._lock:
                self._Connecting = False
            raise
            
        except (AttributeError, RuntimeError) as ex:
            with self._lock:
                self._Connecting = False
            self._logger.error(f"Connection setup failed: {ex}")
            raise DriverException(0x500, "Connection initialization failed", ex)
            
        except Exception as ex:
            with self._lock:
                self._Connecting = False
            self._logger.error(f"Unexpected connection error: {ex}")
            raise DriverException(0x500, "Unexpected connection failure", ex)


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
                raise DriverException(0x500, "TTS160Global module unavailable", ex)

            # Establish serial connection
            try:
                self._serial_manager.connect(self._config.dev_port)
                self._logger.info(f"Serial connection established on {self._config.dev_port}")
            except Exception as ex:
                self._logger.error(f"Serial connection failed on {self._config.dev_port}: {ex}")
                raise DriverException(0x500, f"Serial connection failed: {ex}", ex)
            
            # Initialize mount hardware and settings
            self._initialize_connected_mount()
            
            # Update connection state
            with self._lock:
                self._Connected = True
                self._Connecting = False
                
            self._logger.info("TTS160 mount connection completed successfully")
            
        except DriverException:
            # Cleanup and re-raise
            with self._lock:
                self._Connecting = False
                self._Connected = False
            raise
            
        except Exception as ex:
            # Cleanup and wrap unexpected exceptions
            with self._lock:
                self._Connecting = False
                self._Connected = False
            self._logger.error(f"Mount connection failed with unexpected error: {ex}")
            raise DriverException(0x500, "Mount connection failed", ex)


    def _initialize_connected_mount(self) -> None:
        """
        Initialize mount after successful connection.
        
        Retrieves mount information, synchronizes site coordinates, optionally
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
                raise DriverException(0x500, f"Failed to retrieve mount identification: {ex}")
            
            # Update site coordinates from mount
            self._sync_site_coordinates_from_mount()
            
            # Sync mount time if configured (continue on failure)
            if self._config.sync_time_on_connect:
                try:
                    self.UTCDate = datetime.now(timezone.utc)
                    self._logger.info("Mount time synchronized with system clock")
                except Exception as ex:
                    self._logger.warning(f"Time synchronization failed: {ex}")
            
            self._logger.info("Mount initialization completed successfully")
            
        except Exception as ex:
            self._logger.error(f"Mount initialization failed: {ex}")
            raise DriverException(0x500, "Mount initialization failed", ex)


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
                raise DriverException(0x500, f"Failed to retrieve site coordinates from mount: {ex}")
            
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
                    raise DriverException(0x500, f"Failed to update site location objects: {ex}")
            
            self._logger.info(f"Site coordinates synchronized: {latitude:.6f}°, {longitude:.6f}°, {elevation:.1f}m")
            
        except DriverException:
            raise
            
        except Exception as ex:
            self._logger.warning(f"Site coordinate synchronization failed: {ex}")
            raise DriverException(0x500, "Failed to synchronize site coordinates from mount", ex)
    
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
            
            # Clear serial manager reference
            try:
                self._serial_manager = None
                self._logger.debug("Serial manager reference cleared")
            except Exception as ex:
                self._logger.warning(f"Error clearing serial manager reference: {ex}")
            
            # Update connection state
            with self._lock:
                self._Connected = False
                
            self._logger.info("TTS160 mount disconnected successfully")
            
        except Exception as ex:
            # Log error but ensure disconnection state is set
            self._logger.error(f"Unexpected error during disconnect: {ex}")
            with self._lock:
                self._Connected = False
            raise DriverException(0x500, "Disconnect completed with errors", ex)
            
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
        raise NotImplementedException("CommandBlind is deprecated and not supported by TTS160")


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
        raise NotImplementedException("CommandBool is deprecated and not supported by TTS160")


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
        raise NotImplementedException("CommandString is deprecated and not supported by TTS160")


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
        
        # Connection state validation
        if not self._Connected:
            self._logger.error(f"Command '{safe_command}' attempted while disconnected")
            raise NotConnectedException("Device not connected - cannot send command")
        
        # Serial manager validation
        if not hasattr(self, '_serial_manager') or not self._serial_manager:
            self._logger.error("Serial manager not available for command execution")
            raise DriverException(0x500, "Serial manager not initialized")
        
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
            
        except DriverException:
            # Re-raise DriverExceptions as-is
            self._logger.error(f"DriverException executing command '{safe_command}'")
            raise
            
        except Exception as ex:
            # Wrap unexpected exceptions with context
            self._logger.error(f"Communication error executing command '{safe_command}': {ex}")
            raise DriverException(0x555, f"Command execution failed: {command}", ex)
        
   
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
            
        except (InvalidValueException, DriverException):
            self._logger.error(f"Alt/Az to RA/Dec conversion failed: Az={azimuth}°, Alt={altitude}°")
            raise
        except Exception as ex:
            self._logger.error(f"Unexpected error in Alt/Az conversion: {ex}")
            raise DriverException(0x500, "Coordinate conversion failed", ex)


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
            
        except (InvalidValueException, DriverException):
            self._logger.error(f"RA/Dec to Alt/Az conversion failed: RA={right_ascension}h, Dec={declination}°")
            raise
        except Exception as ex:
            self._logger.error(f"Unexpected error in RA/Dec conversion: {ex}")
            raise DriverException(0x500, "Coordinate conversion failed", ex)
    
    # Connection Properties
    @property
    def Connected(self) -> bool:
        """ASCOM Connected property."""
        with self._lock:
            return self._Connected
    
    @Connected.setter  
    def Connected(self, value: bool) -> None:
        """ASCOM Connected property setter."""
        if value:
            self.Connect()
        else:
            self.Disconnect()
    
    @property
    def Connecting(self) -> bool:
        """ASCOM Connecting property."""
        with self._lock:
            return self._Connecting
    
    # Mount Actions
    def Action(self, action_name: str, *parameters: Any) -> str:
        """Invokes the specified device-specific custom action."""
        self._logger.info(f"Action: {action_name}; Parameters: {parameters}")
        
        try:
            action_name = action_name.lower()
            
            if action_name == "fieldrotationangle":
                self._logger.info("FieldRotationAngle - Retrieving")
                result = self._send_command(":ra#", CommandType.STRING)
                self._logger.info(f"FieldRotationAngle - Retrieved: {result}")
                return result
            
            raise NotImplementedException(f"Action '{action_name}' is not implemented")
            
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
            raise NotConnectedException("Device not connected")
        
        try:
            self._logger.debug("Retrieving current altitude from mount")
            result = self._send_command(":*GA#", CommandType.STRING).rstrip('#')
            altitude_deg = float(result) * (180 / math.pi)  # Convert radians to degrees
            self._logger.debug(f"Current altitude: {altitude_deg:.3f}°")
            return altitude_deg
        except Exception as ex:
            self._logger.error(f"Failed to retrieve altitude: {ex}")
            raise DriverException(0x500, "Failed to get altitude", ex)


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
        if not self._Connected:
            raise NotConnectedException("Device not connected")
        
        try:
            self._logger.debug("Retrieving current azimuth from mount")
            result = self._send_command(":*GZ#", CommandType.STRING).rstrip('#')
            azimuth_deg = float(result) * (180 / math.pi)  # Convert radians to degrees
            self._logger.debug(f"Current azimuth: {azimuth_deg:.3f}°")
            return azimuth_deg
        except Exception as ex:
            self._logger.error(f"Failed to retrieve azimuth: {ex}")
            raise DriverException(0x500, "Failed to get azimuth", ex)


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
        if not self._Connected:
            raise NotConnectedException("Device not connected")
        
        try:
            self._logger.debug("Retrieving current declination from mount")
            result = self._send_command(":*GD#", CommandType.STRING).rstrip('#')
            declination_deg = float(result) * (180 / math.pi)  # Convert radians to degrees
            self._logger.debug(f"Current declination: {declination_deg:.3f}°")
            return declination_deg
        except Exception as ex:
            self._logger.error(f"Failed to retrieve declination: {ex}")
            raise DriverException(0x500, "Failed to get declination", ex)


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
            raise NotConnectedException("Device not connected")
        
        try:
            self._logger.debug("Retrieving current right ascension from mount")
            result = self._send_command(":*GR#", CommandType.STRING).rstrip('#')
            ra = float(result) * (180 / math.pi) / 15  # Convert radians to hours
            ra = ra % 24  # Normalize to 0-24 hours
            self._logger.debug(f"Current right ascension: {ra:.3f}h")
            return ra
        except Exception as ex:
            self._logger.error(f"Failed to retrieve right ascension: {ex}")
            raise DriverException(0x500, "Failed to get right ascension", ex)


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
        if not self._Connected:
            raise NotConnectedException("Device not connected")
        
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
            raise DriverException(0x500, "Failed to get sidereal time", ex)


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
            
        except InvalidValueException:
            self._logger.error(f"Invalid coordinates for pier side calculation: RA={ra}, Dec={dec}")
            raise
        except Exception as ex:
            self._logger.error(f"Pier side calculation failed: {ex}")
            raise DriverException(0x500, "Failed to calculate destination pier side", ex)

    # Site and Telescope Properties
    @property
    def ApertureArea(self) -> float:
        raise NotImplementedException()
    
    @ApertureArea.setter
    def ApertureArea(self, value: float) -> None:
        raise NotImplementedException()
    
    @property
    def ApertureDiameter(self) -> float:
        raise NotImplementedException()
    
    @ApertureDiameter.setter
    def ApertureDiameter(self, value: float) -> None:
        raise NotImplementedException()

    @property
    def DoesRefraction(self) -> bool:
        raise NotImplementedException()

    @property
    def FocalLength(self) -> float:
        raise NotImplementedException()
    
    @FocalLength.setter
    def FocalLength(self, value: float) -> None:
        raise NotImplementedException()

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
        if not self._Connected:
            raise NotConnectedException("Device not connected")
        
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
            raise DriverException(0x500, f"Get latitude failed: {ex}")
    
    #TODO: I don't think this was implemented in the ASCOM driver, verify.
    @SiteLatitude.setter
    def SiteLatitude(self, value: float) -> None:
        raise NotImplementedException()
    
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
        if not self._Connected:
            raise NotConnectedException("Device not connected")
        
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
            raise DriverException(0x500, f"Get longitude failed: {ex}")
    
    #TODO: I don't think this was implemented in the ASCOM driver, verify
    @SiteLongitude.setter  
    def SiteLongitude(self, value: float) -> None:
        raise NotImplementedException()
    
    @property
    def SiteElevation(self) -> float:
        """Site elevation in meters."""
        return self._site_location.height.value
    
    #TODO: Ibid.  If I do want this implemented, it needs to feed back to the configuration object
    @SiteElevation.setter
    def SiteElevation(self, value: float) -> None:
        raise NotImplementedException()
    
    # Mount State Properties
    @property
    def AtHome(self) -> bool:
        """True if mount is at home position."""
        with self._lock:
            return self._is_at_home
    
    @AtHome.setter
    def AtHome(self, value: bool) -> None:
        """True if mount is at home position."""
        with self._lock:
            self._is_at_home = value

    @property
    def AtPark(self) -> bool:
        """True if mount is parked."""
        with self._lock:
            return self._is_parked
    
    @AtPark.setter
    def AtPark(self, value: bool) -> None:
        """Set parked state."""
        with self._lock:
            self._is_parked = value

    @property
    def DeviceState(self) -> List[dict]:
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
        
        return device_state

    @property
    def EquatorialSystem(self) -> EquatorialCoordinateType:
        """Which Equatorial Type does the mount use"""
        self._logger.info("Querying current epoch")
        result = self._send_command(":*E#", CommandType.BOOL)
        if result:
            self._logger.info(f"Retrieved {result}, indicating Topocentric Equatorial")
            return EquatorialCoordinateType.equTopocentric
        else:
            self._logger.info(f"Retrieved {result}, indicating J2000")
            return EquatorialCoordinateType.equJ2000
    
    @property
    def GuideRateDeclination(self) -> float:
        rate = int(self._send_command(":*gRG#", CommandType.STRING).rstrip('#'))
        guide_rates = {
            0: 1.0 / 3600.0,
            1: 3.0 / 3600.0,
            2: 5.0 / 3600.0,
            3: 10.0 / 3600.0,
            4: 20.0 / 3600.0
        }
        return guide_rates.get(rate, 0)
    
    @GuideRateDeclination.setter
    def GuideRateDeclination(self, value: float) -> None:
        value *= 3600
        #TODO: Determine correct exception to raise
        #if value < 0:
        #    raise ValueError(f"{value / 3600} is less than 0")

        thresholds = [1.5, 4.0, 7.5, 15.0]
        val = bisect.bisect_left(thresholds, value)

        self._send_command(f":*gRS{val}#", CommandType.BLIND)

    @property
    def GuideRateRightAscension(self) -> float:
        rate = int(self._send_command(":*gRG#", CommandType.STRING).rstrip('#'))
        guide_rates = {
            0: 1.0 / 3600.0,
            1: 3.0 / 3600.0,
            2: 5.0 / 3600.0,
            3: 10.0 / 3600.0,
            4: 20.0 / 3600.0
        }
        return guide_rates.get(rate, 0)

    @GuideRateRightAscension.setter
    def GuideRateRightAscension(self, value: float) -> None:
        value *= 3600
        #TODO: Determine correct exception to raise
        #if value < 0:
        #    raise ValueError(f"{value / 3600} is less than 0")

        thresholds = [1.5, 4.0, 7.5, 15.0]
        val = bisect.bisect_left(thresholds, value)

        self._send_command(f":*gRS{val}#", CommandType.BLIND)

    def _calculate_side_of_pier(self, right_ascension: float) -> PierSide:
        """
        Calculate which side of pier telescope should be on for given RA.
        
        Determines pier side based on hour angle. Positive hour angles
        (object west of meridian) use East pier side, negative hour angles
        (object east of meridian) use West pier side.
        
        Args:
            right_ascension: RA in hours (0-24)
            
        Returns:
            PierSide: pierEast if HA > 0, pierWest if HA <= 0
            
        Raises:
            DriverException: If sidereal time calculation fails
            InvalidValueException: If RA outside valid range
        """
        try:
            self._validate_coordinates(ra = right_ascension)
            
            self._logger.debug(f"Calculating pier side for RA {right_ascension:.3f}h")
            
            # Calculate hour angle
            hour_angle = self._condition_ha(self.SiderealTime - right_ascension)
            
            # Determine pier side based on hour angle
            pier_side = PierSide.pierEast if hour_angle > 0 else PierSide.pierWest
            
            self._logger.debug(f"Hour angle: {hour_angle:.3f}h, Pier side: {pier_side}")
            return pier_side
            
        except InvalidValueException:
            self._logger.error(f"Invalid RA for pier side calculation: {right_ascension}")
            raise
        except Exception as ex:
            self._logger.error(f"Pier side calculation failed for RA {right_ascension}: {ex}")
            raise DriverException(0x500, "Pier side calculation failed", ex)

    @property
    def SideOfPier(self) -> PierSide:
        """Calculates and returns SideofPier"""
        return self._calculate_side_of_pier(self.RightAscension)

    @property
    def Slewing(self) -> bool:
        """True if mount is slewing."""
        try:
            
            slew_future = self._slew_in_progress
            return slew_future and not slew_future.done()                    
                
        except Exception as ex:
            raise DriverException(0x500, f"Error checking slewing status: {ex}")
    
    @property
    def Tracking(self) -> bool:
        """True if mount is tracking."""
        try:
            result = self._send_command(":GW#", CommandType.STRING)
            return result[1] == 'T' if len(result) > 1 else False
        except Exception as ex:
            raise DriverException(0x500, "Failed to get tracking state", ex)
    
    @Tracking.setter
    def Tracking(self, value: bool) -> None:
        """Set tracking state."""
        if self.Slewing:
            raise InvalidOperationException("Cannot change tracking while slewing")
        
        if self.AtPark:
            raise InvalidOperationException("Cannot change tracking state while parked")

        try:
            command = ":T1#" if value else ":T0#" 
            self._send_command(command, CommandType.BLIND)
            with self._lock:
                self._tracking = value
        except Exception as ex:
            raise DriverException(0x500, "Failed to set tracking", ex)
    
    @property
    def TrackingRate(self) -> DriveRates:

        try:
            command = ":*TRG#"
            result = int(self._send_command(command, CommandType.STRING).rstrip("#"))
            if result == 0:
                return DriveRates.driveSidereal
            elif result == 1:
                return DriveRates.driveLunar
            elif result == 2:
                return DriveRates.driveSolar
            else:
                raise DriverException(0x500,f"TrackingRate get failed due to unknown value received: {result}")
        except Exception as ex:
            raise DriverException(0x500, f"Unknown error: {ex}")
        
    @TrackingRate.setter
    def TrackingRate(self, rate: DriveRates) -> None:

        try:
            if rate == DriveRates.driveSidereal:
                command = ":TQ#"
            elif rate == DriveRates.driveLunar:
                command = ":TL#"
            elif rate == DriveRates.driveSolar:
                command = ":TS#"
            else:
                raise InvalidValueException(f"Unknown rate provided: {rate}.")
            
            self._send_command(command, CommandType.BLIND)

        except Exception as ex:
            raise DriverException(0x500,f"Set Tracking Rate Failed: {ex}")


    @property
    def RightAscensionRate(self) -> float:
        raise NotImplementedException()
    
    @RightAscensionRate.setter
    def RightAscensionRate(self, value: float) -> None:
        raise NotImplementedException()
    
    @property
    def DeclinationRate(self) -> float:
        raise NotImplementedException()
    
    @DeclinationRate.setter
    def DeclinationRate(self, value: float) -> None:
        raise NotImplementedException()        

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
            raise DriverException(0x500, f"Failed to check pulse guide status: {ex}")


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
        if not self._target_declination_set:
            raise InvalidOperationException("Target declination not set")
        else:
            command = ":*Gd#"
            declination_rad = float(self._send_command(command, CommandType.STRING).rstrip("#"))
            declination_deg = declination_rad * 180 / math.pi
            return declination_deg
    
    @TargetDeclination.setter
    def TargetDeclination(self, value: float) -> None:
        """Set target declination."""
        if not -90 <= value <= 90:
            raise InvalidValueException(f"Invalid declination: {value}")
        
        try:
            # Send to mount
            dms_str = self._degrees_to_dms(abs(value))
            #TODO: Verify that this is what C# driver is doing.  Assuming negative unless a + in front?!
            sign = "+" if value >= 0 else "-"
            command = f":Sd{sign}{dms_str}#"
            
            result = self._send_command(command, CommandType.BOOL)
            if not result:
                raise InvalidValueException(f"Mount rejected target declination assignment: {value}")
            
            # Update state
            with self._lock:
                self._target_declination_set = True
                if self._target_right_ascension_set:
                    self._is_target_set = True
                
        except Exception as ex:
            raise DriverException(0x500, f"Failed to set target declination {value}", ex)
    
    @property
    def TargetRightAscension(self) -> float:
        """Target right ascension in hours.""" 
        if not self._target_right_ascension_set:
            raise InvalidOperationException("Target Right Ascension not set")
        else:
            command = ":*Gr#"
            right_ascension_rad = float(self._send_command(command, CommandType.STRING).rstrip("#"))
            right_ascension_deg = right_ascension_rad * 180 / math.pi
            return right_ascension_deg
    
    @TargetRightAscension.setter
    def TargetRightAscension(self, value: float) -> None:
        """Set target right ascension."""
        if not 0 <= value <= 24:
            raise InvalidValueException(f"Invalid right ascension: {value}")
        
        try:
            # Send to mount
            hms_str = self._hours_to_hms(value)
            command = f":Sr{hms_str}#"
            
            result = self._send_command(command, CommandType.BOOL)
            if not result:
                raise InvalidValueException(f"Mount rejected target right ascension assignment: {value}")
            
            # Update state
            with self._lock:
                self._target_right_ascension_set = True
                if self._target_declination_set:
                    self._is_target_set = True
                
        except Exception as ex:
            raise DriverException(0x500, f"Failed to set target right ascension {value}", ex)
    
    # Operation Methods
    def AbortSlew(self) -> None:
        """Abort any current slewing."""
        try:
            
            self._goto_in_progress = False
            self._send_command(":Q#", CommandType.BLIND)
            
        except Exception as ex:
            raise DriverException(0x500, "Failed to abort slew", ex)
    
    def FindHome(self):
        """Locates the telescope's home position (asynchronous)"""
        self._logger.info("Moving to Home")
        
        try:
            
            if self._is_parked:
                raise InvalidOperationException("The requested operation cannot be undertaken at this time: the mount is parked.")

            if self.Slewing:
                raise InvalidOperationException("The requested operation cannot be undertaken at this time: the mount is slewing.")
            
            if self.AtHome:
                self._logger.info("Mount is already at Home")
                return

            park_status = self._send_command(":*PG#", CommandType.STRING)

            park_type = int(park_status[0])
            park_az = float(park_status[1:8])
            park_alt = float(park_status[8:14])

            #TODO: pull park alt and az and use those rather than 180/0    
            #home_az = 180
            current_time = Time.now()
            
            if park_type == 1 and int(park_alt) > 0:
                altaz_coord = AltAz(
                    az=park_az * u.deg, 
                    alt=park_alt * u.deg,
                    obstime=current_time,
                    location=self._site_location
                )
                
                # Convert to GCRS with current epoch (JNow)
                gcrs_coord = altaz_coord.transform_to(GCRS(obstime=current_time))
                self.TargetDeclination = gcrs_coord.dec.deg
                self.TargetRightAscension = gcrs_coord.ra.hour
                
                # Try to slew - returns False if target is reachable (slew does not start)
                if not bool(int(self._send_command(":MS#", CommandType.STRING))):
                    self._executor.submit(self._home_arrival_monitor, target_alt)
                    self._slew_in_progress = self._executor.submit(self._slew_status_monitor)
                    self._goto_in_progress = True
                    return
            
                raise InvalidOperationException("Home position is below horizon, check mount alignment")        
            else:
                # Try altitudes 0-9 degrees to find position above horizon
                for target_alt in range(10):
                    altaz_coord = AltAz(
                        az=park_az * u.deg, 
                        alt=target_alt * u.deg,
                        obstime=current_time,
                        location=self._site_location
                    )
                    
                    # Convert to GCRS with current epoch (JNow)
                    gcrs_coord = altaz_coord.transform_to(GCRS(obstime=current_time))
                    self.TargetDeclination = gcrs_coord.dec.deg
                    self.TargetRightAscension = gcrs_coord.ra.hour
                    
                    # Try to slew - returns False if target is reachable (slew does not start)
                    if not bool(int(self._send_command(":MS#", CommandType.STRING))):
                        self._executor.submit(self._home_arrival_monitor, target_alt)
                        self._slew_in_progress = self._executor.submit(self._slew_status_monitor)
                        self._goto_in_progress = True
                        return
                
                raise InvalidOperationException("Home position is below horizon, check mount alignment")
            
        except Exception as ex:
            self._logger.error(f"FindHome error: {ex}")
            raise
    
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
            while True:
                try:
                    status = self._send_command(":D#", CommandType.STRING)
                    if status != "|#":
                        break
                    time.sleep(0.1)  # 100ms polling interval
                except Exception as ex:
                    self._logger.error(f"Error polling slew status: {ex}")
                    raise DriverException(0x502, f"Slew status monitoring failed: {ex}")
            
            # Apply settle time only for goto operations
            if self._goto_in_progress:
                settle_time = self._config.slew_settle_time
                if settle_time > 0:
                    self._logger.info(f"Applying slew settle time: {settle_time}s")
                    time.sleep(settle_time)
                self._goto_in_progress = False
                self._logger.info("Slew operation completed")
            
        except DriverException:
            raise
        except Exception as ex:
            self._logger.error(f"Unexpected error in slew monitoring: {ex}")
            raise DriverException(0x502, f"Slew status monitoring error: {ex}")

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
            while self.Slewing:
                time.sleep(0.5)
            
            # Verify home position
            current_alt = self.Altitude
            current_az = self.Azimuth
            
            altitude_error = abs(current_alt - target_altitude)
            azimuth_error = abs(target_azimuth - current_az)  #need to check for azimuth wraparound case!
            
            if altitude_error < self.HOME_POSITION_TOLERANCE_ALT and azimuth_error < self.HOME_POSITION_TOLERANCE_AZ:
                self.AtHome = True
                self._logger.info(f"Arrived at home: Alt={current_alt:.1f}°, Az={current_az:.1f}°")
            else:
                error_msg = f"Home position verification failed - Alt: {current_alt:.1f}°, Az: {current_az:.1f}°"
                self._logger.error(error_msg)
                raise DriverException(0x500, error_msg)
                
        except Exception as ex:
            self._logger.error(f"Home arrival monitoring failed: {ex}")
            if not isinstance(ex, DriverException):
                raise DriverException(0x500, f"Home arrival monitoring error: {ex}")
            raise
    
    def MoveAxis(self, axis: TelescopeAxes, rate: float) -> None:
        """Move telescope axis at specified rate."""
        
        try:

            if self._is_parked:
                raise InvalidOperationException("Cannot move axis: mount is parked")
            
            if abs(rate) > self._MAX_RATE:
                raise InvalidValueException(f"Rate {rate} exceeds limit ±{self._MAX_RATE} deg/sec")
            
            if axis not in self._AXIS_COMMANDS:
                raise InvalidValueException(f"Invalid axis: {axis}")

            if self._goto_in_progress:
                raise InvalidOperationException("Cannot execute MoveAxis while Goto is in progress.")

            # Calculate timing parameters
            if rate == 0:
                time_to_pulse = 1.0
            else:
                time_to_pulse = (self._CLOCK_FREQ * self._TICKS_PER_PULSE) / (abs(rate) * self._TICKS_PER_DEGREE[axis])
            
            # Convert to fraction and scale
            frac = Fraction(time_to_pulse).limit_denominator(9999)
            num, den = frac.numerator, frac.denominator
            
            if den < 4999:
                mult = 4999 // den
                num *= mult
                den *= mult
            
            if num == 0:
                den = 9999

            self._logger.info(f"MoveAxis - Num: {num}; Den: {den}; Result: {num / den}")
            
            # Execute command
            cmds = self._AXIS_COMMANDS[axis]
            
            if rate == 0:
                self._logger.info(f"Stopping {cmds['name']} Axis")
                self._send_command(cmds['stop'], CommandType.BLIND)
            else:
                cmd_base = cmds['pos'] if rate > 0 else cmds['neg']
                command = f"{cmd_base}{abs(num):04d}{abs(den):04d}#"
                self._logger.info(f"Sending Command: {command}")
                self._send_command(command, CommandType.BLIND)
                
                # Set up the slew status monitor if one does not exist (this immediately makes slewing be true)
                if self._slew_in_progress is None or self._slew_in_progress.done():
                    self._slew_in_progress = self._executor.submit(self._slew_status_monitor)
                self._is_at_home = False
                
        except Exception as ex:
            raise DriverException(0x503, f"MoveAxis Error: {ex}")

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
            raise NotConnectedException("Device not connected")
        
        if self.AtPark:
            raise ParkedException("Cannot sync while parked")
        
        # Validate coordinate ranges
        self._validate_coordinates(alt = altitude, az = azimuth)
        
        try:
            self._logger.info(f"Syncing to Alt/Az: {azimuth:.3f}°, {altitude:.3f}°")
            
            # Convert to equatorial coordinates
            right_ascension, declination = self._altaz_to_radec(azimuth, altitude)
            
            # Perform equatorial sync
            self.SyncToCoordinates(right_ascension, declination)
            
        except (ParkedException, InvalidValueException, NotConnectedException):
            raise
        except Exception as ex:
            self._logger.error(f"Alt/Az sync failed: {ex}")
            raise DriverException(0x500, f"Sync to Alt/Az failed: {ex}")

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
            raise NotConnectedException("Device not connected")
        
        if self.AtPark:
            raise ParkedException("Cannot sync while parked")
        
        # Validate coordinate ranges
        self._validate_coordinates(ra = right_ascension, dec = declination)
        
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
            
        except (ParkedException, InvalidValueException, NotConnectedException):
            raise
        except Exception as ex:
            self._logger.error(f"Coordinate sync failed: {ex}")
            raise DriverException(0x500, f"Synchronization failed: {ex}")

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
            raise NotConnectedException("Device not connected")
        
        if self.AtPark:
            raise ParkedException("Cannot sync while parked")
        
        if not self._is_target_set:
            raise InvalidOperationException("Target coordinates not set")
        
        try:
            self._logger.info("Syncing to target coordinates")
            
            # Execute sync command (basic sync, not auto-align)
            sync_result = self._send_command(":CM#", CommandType.STRING)
            
            # Apply sync settling time per LX200 specification
            time.sleep(self._sync_wait_time)
            
            self._logger.info("Target sync completed")
            
        except (ParkedException, InvalidOperationException, NotConnectedException):
            raise
        except Exception as ex:
            self._logger.error(f"Target sync failed: {ex}")
            raise DriverException(0x500, f"Target synchronization failed: {ex}")


    def SlewToAltAz(self, azimuth: float, altitude: float) -> None:
        """Slew to given altaz coordinates (synchronous)."""
        raise NotImplementedException()
    
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
            raise NotConnectedException("Device not connected")
        
        if self.Slewing:
            raise InvalidOperationException("Cannot start slew while already slewing")
        
        if self.Tracking:
            raise InvalidOperationException("Cannot slew to Alt/Az while tracking enabled")
        
        if self.AtPark:
            raise ParkedException("Cannot slew while parked")
        
        # Validate coordinate ranges
        self._validate_coordinates(alt = altitude, az = azimuth)
        
        try:
            self._logger.info(f"Starting slew to Alt/Az: {azimuth:.3f}°, {altitude:.3f}°")
            
            # Convert to equatorial coordinates
            right_ascension, declination = self._altaz_to_radec(azimuth, altitude)
            
            # Execute equatorial slew
            self.SlewToCoordinatesAsync(right_ascension, declination)
            
        except (NotConnectedException, InvalidOperationException, ParkedException, InvalidValueException):
            raise
        except Exception as ex:
            self._logger.error(f"Alt/Az async slew failed: {ex}")
            raise DriverException(0x500, f"Alt/Az slew initiation failed: {ex}")

    def SlewToCoordinates(self, rightAscension: float, declination: float) -> None:
        """Slew to given equatorial coordinates (synchronous)."""
        raise NotImplementedException()
    
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
            raise NotConnectedException("Device not connected")
        
        if self.Slewing:
            raise InvalidOperationException("Cannot start slew while already slewing")
        
        try:
            self._logger.info(f"Starting slew to RA {right_ascension:.3f}h, Dec {declination:.3f}°")
            
            # Set target coordinates (includes validation)
            self.TargetRightAscension = right_ascension  
            self.TargetDeclination = declination
            
            # Execute target slew
            self.SlewToTargetAsync()
            
        except (NotConnectedException, InvalidValueException):
            raise
        except Exception as ex:
            self._logger.error(f"Coordinate async slew failed: {ex}")
            raise DriverException(0x500, f"Coordinate slew initiation failed: {ex}")
    
    def SlewToTarget(self) -> None:
        """Slew to current target coordinates (synchronous)."""
        raise NotImplementedException()        

    
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
            raise NotConnectedException("Device not connected")
        
        if not self._is_target_set:
            raise InvalidOperationException("Target coordinates not set")
        
        if self.Slewing:
            raise InvalidOperationException("Cannot start slew while already slewing")
        
        if self.AtPark:
            raise ParkedException("Cannot slew while parked")
        
        try:
            with self._lock:
                self._logger.info("Starting slew to target coordinates")
                
                # Send slew command
                result = self._send_command(":MS#", CommandType.STRING)
                
                # Parse LX200 slew response
                if result.startswith("1"):
                    raise DriverException(0x500, "Target object below horizon")
                elif result.startswith("2"):
                    raise DriverException(0x500, "Target object below higher limit")
                elif not result.startswith("0"):
                    raise DriverException(0x500, f"Unexpected slew response: {result}")
                
                # Set up movement monitoring
                self._goto_in_progress = True
                self._slew_in_progress = self._executor.submit(self._slew_status_monitor)
                self.AtHome = False
                
                self._logger.info("Target slew initiated successfully")
                
        except (NotConnectedException, InvalidOperationException, ParkedException):
            raise
        except DriverException as ex:
            self._logger.error(f"Target slew failed: {ex}")
            raise
        except Exception as ex:
            self._logger.error(f"Unexpected target slew error: {ex}")
            raise DriverException(0x500, f"Target slew initiation failed: {ex}")
    
    def PulseGuide(self, direction: GuideDirections, duration: int) -> None:
        """
        Pulse guide in specified direction for given duration.
        
        Args:
            direction: Guide direction (North/South/East/West)
            duration: Duration in milliseconds (0-9999)
            
        Raises:
            InvalidValueException: Invalid direction or duration
            InvalidOperationException: Mount parked, slewing, or axis conflict
            DriverException: Command execution or conversion failure
        """
        # Input validation
        if not isinstance(direction, GuideDirections):
            raise InvalidValueException(f"Invalid guide direction: {direction}")
        if not 0 <= duration <= 9999:
            raise InvalidValueException(f"Duration {duration} outside valid range 0-9999ms")
        
        with self._lock:
            # State validation
            if self._is_parked:
                raise InvalidOperationException("Cannot move axis: mount is parked")
            if self.Slewing:
                raise InvalidOperationException("Cannot pulse guide while slewing")
                
            # Check for axis conflicts
            self._check_pulse_guide_conflicts(direction)
            
            # Initialize monitoring infrastructure if needed
            self._initialize_pulse_guide_monitoring()
            
            try:
                # Determine pulse parameters based on configuration
                if self._config.pulse_guide_equatorial_frame:
                    ns_dir, ns_dur, ew_dir, ew_dur = self._convert_equatorial_pulse(direction, duration)
                else:
                    ns_dir, ns_dur, ew_dir, ew_dur = self._get_standard_pulse_params(direction, duration)
                
                # Execute pulse guide commands
                self._execute_pulse_guide(ns_dir, ns_dur, ew_dir, ew_dur, duration)
                
            except Exception as ex:
                if isinstance(ex, (InvalidValueException, InvalidOperationException)):
                    raise
                raise DriverException(0x500, "Pulse guide failed", ex)


    def _check_pulse_guide_conflicts(self, direction: GuideDirections) -> None:
        """Check for active pulse guide conflicts on the same axis."""
        if not hasattr(self, '_pulse_guide_monitor'):
            return
            
        if direction in [GuideDirections.guideNorth, GuideDirections.guideSouth]:
            monitor = self._pulse_guide_monitor.get('ns')
            if monitor and not monitor.done():
                raise InvalidOperationException("North/South pulse guide already active")
        else:  # East/West
            monitor = self._pulse_guide_monitor.get('ew')
            if monitor and not monitor.done():
                raise InvalidOperationException("East/West pulse guide already active")


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


    def _convert_equatorial_pulse(self, direction: GuideDirections, duration: int) -> Tuple[GuideDirections, int, GuideDirections, int]:
        """
        Convert equatorial pulse guide command to alt/az pulse parameters.
        
        Transforms the requested RA/Dec motion into corresponding Alt/Az motions
        using coordinate transformations.
        
        Args:
            direction: Requested guide direction in equatorial frame
            duration: Requested duration in milliseconds
            
        Returns:
            Tuple of (ns_direction, ns_duration, ew_direction, ew_duration)
            
        Raises:
            DriverException: Coordinate transformation failure
        """
        try:
            # Convert duration to seconds and get guide rate
            duration_sec = duration / 1000.0
            guide_rate = self.GuideRateDeclination  # deg/sec
            
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
                
            # Get current telescope position
            current_time = Time.now()
            current_ra = self.RightAscension  # hours
            current_dec = self.Declination    # degrees
            
            # Calculate final equatorial position
            final_ra = current_ra + delta_ra / 15.0  # convert degrees to hours
            final_dec = current_dec + delta_dec
            
            # Transform current position to AltAz
            current_gcrs = GCRS(
                ra=current_ra * u.hour,
                dec=current_dec * u.deg,
                obstime=current_time
            )
            current_altaz = current_gcrs.transform_to(AltAz(
                obstime=current_time,
                location=self._site_location
            ))
            
            # Transform final position to AltAz
            final_gcrs = GCRS(
                ra=final_ra * u.hour,
                dec=final_dec * u.deg,
                obstime=current_time
            )
            final_altaz = final_gcrs.transform_to(AltAz(
                obstime=current_time,
                location=self._site_location
            ))
            
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
            
            return ns_dir, ns_dur, ew_dir, ew_dur
            
        except Exception as ex:
            raise DriverException(0x500, f"Equatorial pulse conversion failed: {ex}")


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
            raise DriverException(0x500, f"Altitude compensation failed: {ex}")


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
            raise DriverException(0x500, f"Pulse guide execution failed: {ex}")


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
            
            with self._lock:
                self._is_parked = True
                
        except Exception as ex:
            self._logger.error(f"Park monitoring failed: {ex}")
            if not isinstance(ex, DriverException):
                raise DriverException(0x500, f"Park monitoring error: {ex}")
            raise

    def Park(self) -> None:
        """
        Park the mount at its designated park position.
        
        Raises:
            NotConnectedException: If device not connected
            InvalidOperationException: If already parked
            DriverException: If park initiation fails
        """
        if not self._Connected:
            raise NotConnectedException("Device not connected")
        
        if self.AtPark:
            self._logger.info("Mount already parked")
            return
        
        try:
            self._logger.info("Parking mount")
            self._send_command(":hP#", CommandType.BLIND)           
            self._executor.submit(self._park_arrival_monitor)
            self._slew_in_progress = self._executor.submit(self._slew_status_monitor)

            self._logger.info("Mount initiated park successfully")
            
        except Exception as ex:
            self._logger.error(f"Park operation failed: {ex}")
            raise DriverException(0x500, "Park failed", ex)
    
    def SetPark(self) -> None:
        """
        Set mount's park position to current position.
        
        Raises:
            NotConnectedException: If device not connected
            DriverException: If park position setting fails
        """
        if not self._Connected:
            raise NotConnectedException("Device not connected")
        
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
            raise DriverException(0x500, f"SetPark failed: {ex}")
    
    def Unpark(self) -> None:
        """Unpark Mount."""
        raise NotImplementedException()    

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
        if not self._Connected:
            raise NotConnectedException("Device not connected")
        
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
            
            return utc_dt.replace(tzinfo=timezone.utc)
            
        except Exception as ex:
            self._logger.error(f"Failed to get UTC date: {ex}")
            raise DriverException(0x500, "Failed to get UTC date", ex)


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
        if not self._Connected:
            raise NotConnectedException("Device not connected")
        
        if not isinstance(value, datetime):
            raise InvalidValueException(f"UTCDate must be datetime object, got {type(value)}")
        
        if isinstance(value, str):
            try:
                value = parser.isoparse(value)
            except ValueError:
                raise InvalidValueException(f"Invalid ISO 8601 format: {value}")
        elif not isinstance(value, datetime):
            raise InvalidValueException(f"Error: {value} is not a datetime object or string.")
            # Use datetime directly

        try:
            # Get UTC offset from mount
            utc_offset = self._send_command(":GG#", CommandType.STRING)
            offset_hours = float(utc_offset.rstrip('#'))
            
            # Convert UTC to local time
            local_dt = value - timedelta(hours=offset_hours)
            
            self._logger.info(f"Setting mount time to: {value}")

            # Set date (MM/dd/yy format)
            date_str = local_dt.strftime("%m/%d/%y")
            date_response = self._send_command(f":SC{date_str}#", CommandType.STRING)
            if not (date_response.rstrip('#') == '1'):
                raise DriverException(0x501, f"Invalid date: {date_str}")
            
            # Set time (HH:mm:ss format)
            time_str = local_dt.strftime("%H:%M:%S")
            time_response = self._send_command(f":SL{time_str}#", CommandType.STRING)
            if not (time_response.rstrip('#') == '1'):
                raise DriverException(0x501, f"Invalid time: {time_str}")
            
            # Firmware bug workaround - throwaway SiderealTime call
            _ = self.SiderealTime
            
            self._logger.info("Mount time set successfully")
            
        except (NotConnectedException, InvalidValueException):
            raise
        except Exception as ex:
            self._logger.error(f"Failed to set UTC date: {ex}")
            raise DriverException(0x500, "Failed to set UTC date", ex)

