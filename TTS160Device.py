# File: TTS160Device.py
"""Complete TTS160 Device Hardware Implementation."""

import threading
import time
import math
import bisect
from fractions import Fraction
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
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
    NotImplementedException, ParkedException
)
from telescope import (
    TelescopeMetadata, EquatorialCoordinateType, DriveRates, PierSide,
    AlignmentModes, TelescopeAxes, GuideDirections, Rate
)

class TTS160Device:
    """Complete TTS160 Hardware Implementation with ASCOM compliance."""
    
    # Constants from C# implementation
    MOVEAXIS_WAIT_TIME = 2.0  # seconds
    SYNC_WAIT_TIME = 0.2      # seconds
    
    def __init__(self, logger: Logger):
        self._logger = logger
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers = 2)

        # Import here to avoid circular imports
        import TTS160Global
        self._config = TTS160Global.get_config()
        self._serial_manager = None

        self._logger.info("Instantiating serial manager")
        self._serial_manager = TTS160Global.get_serial_manager(self._logger)

        # Connection state
        self._Connecting = False
        self._Connected = False


        #Static Data
        self._Name = TelescopeMetadata.Name
        self._DriverVersion = TelescopeMetadata.Version
        self._Description = TelescopeMetadata.Description

        #ASCOM 'Can' Variables (Readonly, will not change)
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

        # Mount state with thread safety
        self._slew_in_progress = None
        #self._is_slewing = False
        #self._is_slewing_to_target = False
        self._is_pulse_guiding = False
        #self._moving_primary = False
        #self._moving_secondary = False
        self._is_parked = False
        self._is_at_home = False
        self._tracking = False
        self._goto_in_progress = False  #Indicates if a goto is in progress rather than just slew to allow for moveaxis to be executed during...moveaxis

        # Target state
        self._is_target_set = False
        self._target_right_ascension_set = False
        self._target_declination_set = False

        # Pulse guiding state
        self._pulse_guide_duration = 0
        self._pulse_guide_start = datetime.min
        
        # Site location for coordinate transforms
        self._site_location = None
        self._update_site_location()

        #Other misc variables
        self._AxisRates = [Rate(0.0, 3.5)]
        self._DriveRates = [DriveRates.driveSidereal, DriveRates.driveLunar, DriveRates.driveSolar]

        #MoveAxis specific variables
        self._TICKS_PER_DEGREE = {
            TelescopeAxes.axisPrimary: 13033502.0 / 360.0,    # H axis
            TelescopeAxes.axisSecondary: 13146621.0 / 360.0   # E axis
        }
        self._TICKS_PER_PULSE = 7.0
        self._CLOCK_FREQ = 57600
        self._MAX_RATE = max(rate.maximum for rate in self._AxisRates)

        self._AXIS_COMMANDS = {
            TelescopeAxes.axisPrimary: {
                'stop': ':Qe#', 'pos': ':*Me', 'neg': ':*Mw', 'name': 'Primary'
            },
            TelescopeAxes.axisSecondary: {
                'stop': ':Qn#', 'pos': ':*Mn', 'neg': ':*Ms', 'name': 'Secondary'
            }
        }


    def __del__(self):
        # Trash collection
        try:
            if hasattr(self, 'executor'):
                self.executor.shutdown(wait=False)
            self._serial_manager.cleanup()
        except:
            pass

    def _update_site_location(self) -> None:
        """Update AstroPy site location from config."""
        try:
            lat = float(self._config.site_latitude) if self._config.site_latitude else 0.0
            lon = float(self._config.site_longitude) if self._config.site_longitude else 0.0 
            elev = float(self._config.site_elevation) if self._config.site_elevation else 0.0
            
            self._site_location = EarthLocation(
                lat=lat * u.deg,
                lon=lon * u.deg,
                height=elev * u.m
            )
        except (ValueError, TypeError):
            self._site_location = EarthLocation(
                lat=0.0 * u.deg,
                lon=0.0 * u.deg,
                height=0.0 * u.m
            )
    
    # Connection Management
    def Connect(self) -> Optional[Future]:
        """Connect to the TTS160 mount."""
        with self._lock:
            if self._Connected:
                self._serial_manager.connection_count += 1
                return
            
            #If we are already trying to connect
            if self._Connecting:
                self._serial_manager.connection_count += 1
                return

            self._Connecting = True
            
        try:
            self._logger.info("Starting Async Connect Routine")
            self._config.reload()
            self._executor.submit(self._connect_mount)
            return

        except Exception as ex:
            with self._lock:
                self._Connecting = False  # Reset if submit fails
            self._logger.error(f"Connection failed: {ex}")
            raise DriverException(0x500, "Connection failed", ex)
    
    #Synchronous method broken out to allow either sync or async execution (using self._executor object)
    def _connect_mount(self) -> None:
        try:
            import TTS160Global
            if not self._serial_manager:
                self._serial_manager = TTS160Global.get_serial_manager(self._logger)

            self._serial_manager.connect(self._config.dev_port)
            self._initialize_mount()
            with self._lock:
                self._Connected = True
                self._Connecting = False
            self._logger.info("TTS160 connected successfully")
            
        except Exception as ex:
            self._logger.error(f"Connection failed: {ex}")
            raise DriverException(0x500, "Connection failed", ex)
        finally:
            self._Connecting = False

    def _initialize_mount(self) -> None:
        """Initialize mount after connection."""
        try:
            # Get mount information
            mount_name = self._send_command(":GVP#", CommandType.STRING).rstrip('#')
            firmware = self._send_command(":GVN#", CommandType.STRING).rstrip('#')
            firmware_date = self._send_command(":GVD#", CommandType.STRING).rstrip('#')
            
            self._logger.info(f"Connected to: {mount_name}")
            self._logger.info(f"Firmware: {firmware} ({firmware_date})")
            
            # Update site coordinates from mount
            self._update_site_coordinates_from_mount()
            
            # Update mount time from computer if desired
            if self._config.sync_time_on_connect:
                self.UTCDate = datetime.now(timezone.utc)

            # Initialize state
            #with self._lock:
            #    self._is_slewing = False
            #    self._is_slewing_to_target = False
            #    self._is_pulse_guiding = False
            #    self._moving_primary = False
            #    self._moving_secondary = False
            
        except Exception as ex:
            raise DriverException(0x500, "Mount initialization failed", ex)
    
    def _update_site_coordinates_from_mount(self) -> None:
        """Update site coordinates from mount."""
        try:
            # Get latitude
            lat_result = self._send_command(":*Gt#", CommandType.STRING)
            latitude = self._dms_to_degrees(lat_result)
            
            # Get longitude  
            lon_result = self._send_command(":*Gg#", CommandType.STRING)
            longitude = -1 * self._dms_to_degrees(lon_result)  # Convert to West negative
            
            with self._lock:
                # Update configuration
                self._config.site_latitude = latitude
                self._config.site_longitude = longitude
                self._config.save()
                # Update AstroPy location
                elevation = float(self._config.site_elevation) if self._config.site_elevation else 0.0
                self._site_location = EarthLocation(
                    lat=latitude * u.deg,
                    lon=longitude * u.deg,
                    height=elevation * u.m
                )
            
            self._logger.info(f"Site coordinates: {latitude:.6f}°, {longitude:.6f}°, {elevation}m")
            
        except Exception as ex:
            self._logger.warning(f"Failed to update site coordinates: {ex}")
    
    def Disconnect(self) -> None:
        """Disconnect from the TTS160 mount."""
        with self._lock:
            if not self._Connected:
                return

            if self._serial_manager.connection_count > 1:
                self._serial_manager.connection_count -= 1
                return

            self._Connecting = True
            
            try:
                if self._serial_manager:
                    self._config.save()
                    self._serial_manager.disconnect()
                    self._serial_manager = None
                
                if not self._serial_manager or not self._serial_manager.is_connected:
                    self._Connected = False
                
                self._logger.info("TTS160 disconnected")
                
            except Exception as ex:
                self._logger.error(f"Disconnect error: {ex}")
            finally:
                self._Connecting = False

    def CommandBlind(self, msg: str) -> None:
        raise NotImplementedException()
    
    def CommandBool(self, msg: str) -> bool:
        raise NotImplementedException()
    
    def CommandString(self, msg: str) -> str:
        raise NotImplementedException()

    def _send_command(self, command: str, command_type: CommandType) -> str:
        """Send command to mount."""
        try:

            if not self._Connected:
                raise RuntimeError("Device not connected")
            
            return self._serial_manager.send_command(command, command_type)
        except Exception as ex:
            raise DriverException(0x555, f"Error sending command: {ex}")
        
    # Coordinate Conversion Utilities
    def _dms_to_degrees(self, dms_str: str) -> float:
        """Convert DMS string to degrees."""
        try:
            dms_str = dms_str.rstrip('#')
            
            # Extract sign
            sign = -1 if dms_str.startswith('-') else 1
            dms_str = dms_str.lstrip('+-')
            
            # Split by common separators
            parts = dms_str.replace('*', ':').replace("'", ':').split(':')
            
            degrees = float(parts[0])
            minutes = float(parts[1]) if len(parts) > 1 else 0
            seconds = float(parts[2]) if len(parts) > 2 else 0
            
            return sign * (degrees + minutes/60 + seconds/3600)
            
        except Exception:
            raise InvalidValueException(f"Invalid DMS format: {dms_str}")
    
    def _hms_to_hours(self, hms_str: str) -> float:
        """Convert HMS string to hours."""
        try:
            hms_str = hms_str.rstrip('#')
            parts = hms_str.split(':')
            
            hours = float(parts[0])
            minutes = float(parts[1]) if len(parts) > 1 else 0
            seconds = float(parts[2]) if len(parts) > 2 else 0
            
            return hours + minutes/60 + seconds/3600
            
        except Exception:
            raise InvalidValueException(f"Invalid HMS format: {hms_str}")
    
    def _degrees_to_dms(self, degrees: float, deg_sep: str = "*", min_sep: str = ":") -> str:
        """Convert degrees to DMS string."""
        sign = "-" if degrees < 0 else "+"
        degrees = abs(degrees)
        
        deg = int(degrees)
        minutes = (degrees - deg) * 60
        min_val = int(minutes)
        seconds = (minutes - min_val) * 60
        
        return f"{sign}{deg:02d}{deg_sep}{min_val:02d}{min_sep}{seconds:04.1f}"
    
    def _hours_to_hms(self, hours: float) -> str:
        """Convert hours to HMS string."""
        hours = hours % 24  # Normalize to 0-24
        
        h = int(hours)
        minutes = (hours - h) * 60
        m = int(minutes)
        seconds = (minutes - m) * 60
        
        return f"{h:02d}:{m:02d}:{seconds:04.1f}"
    
    def _altaz_to_radec(self, azimuth: float, altitude: float) -> Tuple[float, float]:
        """
        Convert Alt/Az coordinates to RA/Dec in the appropriate mount epoch

        Args:
            azimuth: Azimuth in decimal degrees (0-360)
            altitude: Altitude in decimal degrees (-90 to +90)
        
        Returns:
            Tuple of (right_ascension_hours, declination_degrees)
        """
        try:
            #if the mount uses equTopocentric, convert to GCRS(now), otherwise convert to ICRS
            if self.EquatorialSystem == EquatorialCoordinateType.equTopocentric:
                return self._altaz_to_gcrs(azimuth, altitude)
            else:
                return self._altaz_to_icrs(azimuth, altitude)
        except:
            raise

    def _radec_to_altaz(self, right_ascension: float, declination: float) -> Tuple[float, float]:
        """
        Convert RA/Dec coordinates to Alt/Az in the appropriate mount epoch

        Args:
            right_ascension: RA in decimal hours (0-24)
            declination: Declination in decimal degrees (-90 to +90)
        
        Returns:
            Tuple of (azimuth_degrees, altitude_degrees)
        """
        try:
            #if the mount uses equTopocentric, convert to GCRS(now), otherwise convert to ICRS
            if self.EquatorialSystem == EquatorialCoordinateType.equTopocentric:
                return self._gcrs_to_altaz(right_ascension, declination)
            else:
                return self._icrs_to_altaz(right_ascension, declination)
        except:
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
            if not (0 <= azimuth <= 360):
                raise InvalidValueException(f"Azimuth {azimuth} outside valid range 0-360 degrees")
            if not (-90 <= altitude <= 90):
                raise InvalidValueException(f"Altitude {altitude} outside valid range -90 to +90 degrees")
                
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
            if not (0 <= right_ascension < 24):
                raise InvalidValueException(f"Right ascension {right_ascension} outside valid range 0-24 hours")
            if not (-90 <= declination <= 90):
                raise InvalidValueException(f"Declination {declination} outside valid range -90 to +90 degrees")
                
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
            if not (0 <= azimuth <= 360):
                raise InvalidValueException(f"Azimuth {azimuth} outside valid range 0-360 degrees")
            if not (-90 <= altitude <= 90):
                raise InvalidValueException(f"Altitude {altitude} outside valid range -90 to +90 degrees")
                
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
            if not (0 <= right_ascension < 24):
                raise InvalidValueException(f"Right ascension {right_ascension} outside valid range 0-24 hours")
            if not (-90 <= declination <= 90):
                raise InvalidValueException(f"Declination {declination} outside valid range -90 to +90 degrees")
                
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
            if not (0 <= right_ascension < 24):
                raise InvalidValueException(f"Right ascension {right_ascension} outside valid range 0-24 hours")
            if not (-90 <= declination <= 90):
                raise InvalidValueException(f"Declination {declination} outside valid range -90 to +90 degrees")
                
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
            if not (0 <= right_ascension < 24):
                raise InvalidValueException(f"Right ascension {right_ascension} outside valid range 0-24 hours")
            if not (-90 <= declination <= 90):
                raise InvalidValueException(f"Declination {declination} outside valid range -90 to +90 degrees")
                
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
        """Calculate local apparent sidereal time using AstroPy."""
        if time is None:
            time = datetime.now(timezone.utc)
        
        # Get Greenwich Mean Sidereal Time
        astro_time = Time(time)
        gmst = astro_time.sidereal_time('mean', 'greenwich').hour
        
        # Convert to local sidereal time
        longitude_hours = self._site_location.lon.degree / 15.0
        lst = gmst + longitude_hours
        
        # Normalize to 0-24 hours
        return lst % 24
    
    def _calculate_hour_angle(self, right_ascension: float, 
                             time: datetime = None) -> float:
        """Calculate hour angle for given RA."""
        lst = self._calculate_sidereal_time(time)
        ha = lst - right_ascension
        
        # Normalize to -12 to +12 hours
        while ha > 12:
            ha -= 24
        while ha <= -12:
            ha += 24
            
        return ha
    
    def _condition_ha(self, ha) -> float:
        """Condition hour angle to be in range -12.0 to +12.0"""
        ha = ha % 24.0
        if ha > 12.0:
            ha -= 24.0
        return ha

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
    def Action(self, action_name: str, action_parameters: str) -> str:
        """Invokes the specified device-specific custom action."""
        self._logger.info(f"Action: {action_name}; Parameters: {action_parameters}")
        
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
        """Current altitude in degrees."""
        try:
            result = self._send_command(":*GA#", CommandType.STRING).rstrip('#')
            return float(result) * (180 / math.pi)  # Convert radians to degrees
        except Exception as ex:
            raise DriverException(0x500, "Failed to get altitude", ex)
    
    @property
    def Azimuth(self) -> float:
        """Current azimuth in degrees."""
        try:
            result = self._send_command(":*GZ#", CommandType.STRING).rstrip('#')
            return float(result) * (180 / math.pi)  # Convert radians to degrees
        except Exception as ex:
            raise DriverException(0x500, "Failed to get azimuth", ex)
    
    @property
    def Declination(self) -> float:
        """Current declination in degrees."""
        try:
            result = self._send_command(":*GD#", CommandType.STRING).rstrip('#')
            return float(result) * (180 / math.pi)  # Convert radians to degrees
        except Exception as ex:
            raise DriverException(0x500, "Failed to get declination", ex)
    
    @property
    def RightAscension(self) -> float:
        """Current right ascension in hours."""
        try:
            result = self._send_command(":*GR#", CommandType.STRING).rstrip('#')
            ra = float(result) * (180 / math.pi) / 15  # Convert radians to hours
            return ra % 24  # Normalize to 0-24 hours
        except Exception as ex:
            raise DriverException(0x500, "Failed to get right ascension", ex)
    
    @property
    def SiderealTime(self) -> float:
        """Local sidereal time in hours."""
        try:
            # Get GMST from mount
            result = self._send_command(":GS#", CommandType.STRING).rstrip('#')
            gmst = self._hms_to_hours(result)
            
            # Convert to local sidereal time
            longitude_hours = self._site_location.lon.degree / 15.0
            lst = gmst + longitude_hours
            
            return lst % 24  # Normalize to 0-24 hours
        except Exception as ex:
            raise DriverException(0x500, "Failed to get sidereal time", ex)
    
    def DestinationSideOfPier(self, ra: float, dec: float) -> PierSide:

        return self._calculate_side_of_pier(ra)

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
        """Site latitude in degrees."""

        try:
            command = ":*Gt#"
            latitude = self._send_command(command, CommandType.STRING).rstrip("#")
            latitude_deg = self._dms_to_degrees(latitude)

            self._site_location = EarthLocation(
                lat = latitude_deg * u.deg,
                lon = self._site_location.lon,
                height = self._site_location.height
            )

            self._config.site_latitude = latitude_deg

            return latitude_deg
        except Exception as ex:
            raise DriverException(f"Get latitude failed: {ex}")
    
    #TODO: I don't think this was implemented in the ASCOM driver, verify.
    @SiteLatitude.setter
    def SiteLatitude(self, value: float) -> None:
        raise NotImplementedException()
    
    @property
    def SiteLongitude(self) -> float:
        """Site longitude in degrees."""

        try:
            command = ":*Gg#"
            longitude = self._send_command(command, CommandType.STRING).rstrip("#")
            longitude_deg = -1 * self._dms_to_degrees(longitude) # Mount reports as east negative

            self._site_location = EarthLocation(
                lat = self._site_location.lat,
                lon = longitude_deg * u.deg,
                height = self._site_location.height
            )

            self._config.site_longitude = longitude_deg

            return longitude_deg
        except Exception as ex:
            raise DriverException(f"Get latitude failed: {ex}")
    
    #TODO: I don't think this was implemented in the ASCOM driver, verify
    @SiteLongitude.setter  
    def SiteLongitude(self, value: float) -> None:
        """Set site longitude."""
        if not -180 <= value <= 180:
            raise InvalidValueException(f"Invalid longitude: {value}")
        
        self._site_location = EarthLocation(
            lat=self._site_location.lat,
            lon=value * u.deg,
            height=self._site_location.height
        )
    
    @property
    def SiteElevation(self) -> float:
        """Site elevation in meters."""
        return self._site_location.height.value
    
    #TODO: Ibid.  If I do want this implemented, it needs to feed back to the configuration object
    @SiteElevation.setter
    def SiteElevation(self, value: float) -> None:
        """Set site elevation."""
        if value < -500:  # Reasonable lower bound
            raise InvalidValueException(f"Invalid elevation: {value}")
        
        self._site_location = EarthLocation(
            lat=self._site_location.lat,
            lon=self._site_location.lon,
            height=value * u.m
        )
    
    # Mount State Properties
    @property
    def AlignmentMode(self) -> AlignmentModes:
        return AlignmentModes.algAltAz

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

        self._send_command(f":gRS{val}#", CommandType.BLIND)

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

        self._send_command(f":gRS{val}#", CommandType.BLIND)

    def _calculate_side_of_pier(self, right_ascension) -> PierSide:
        """Calculate which side of pier the telescope should be on"""
        hour_angle = self._condition_ha(self.SiderealTime - right_ascension)
        destination_sop = PierSide.pierEast if hour_angle > 0 else PierSide.pierWest
        return destination_sop

    @property
    def SideOfPier(self) -> PierSide:
        """Calculates and returns SideofPier"""
        return self._calculate_side_of_pier(self.RightAscension)

    @property
    def Slewing(self) -> bool:
        """True if mount is slewing."""
        try:
            
            return self._slew_in_progress and not self._slew_in_progress.done()                    
            
            # Check hardware slewing status
            #result = self._send_command(":D#", CommandType.STRING)
            #is_slewing = result == "|#"
            
            #with self._lock:
            #    if not is_slewing and self._is_slewing:
            #        # Slew just finished - handle settle time
            #        self._handle_slew_completion()
                
            #    self._is_slewing = is_slewing
            #    return is_slewing
                
        except Exception as ex:
            raise DriverException(0x500, f"Error checking slewing status: {ex}")
            
    
    #TODO: This needs to be made asynchronous...spin it off into its own thread?
    #def _handle_slew_completion(self) -> None:
    #    """Handle slew completion and settling."""
    #    #TODO: Why use getattr rather than just the self._config.SlewSettleTime?
    #    settle_time = getattr(self._config, 'slew_settle_time', 0)
    #    if settle_time > 0:
    #        time.sleep(settle_time)
        
    #    # Reset slewing flags
    #    #TODO: Can we get rid of moving primary, moving secondary??  What about _is_slewing?  _is_slewing_to_target?
    #    self._is_slewing = False
    #    self._is_slewing_to_target = False
    #    self._moving_primary = False
    #    self._moving_secondary = False
    #    self._goto_in_progress = False
    
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
    def SlewSettleTime(self) -> int:
        return self._config.slew_settle_time
    
    @SlewSettleTime.setter
    def SlewSettleTime(self, value: int) -> None:
        with self._lock:
            self._config.slew_settle_time = value
        

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
        monitor = self._pulse_guide_monitor.get(axis)
        
        # No monitor or monitor completed
        if not monitor or monitor.done():
            return False
        
        # Get axis-specific timing attributes
        start_attr = f'_pulse_guide_{axis}_start'
        duration_attr = f'_pulse_guide_{axis}_duration'
        stop_event_attr = f'_stop_pulse_{axis}'
        
        # Check if required attributes exist
        if not all(hasattr(self, attr) for attr in [start_attr, duration_attr, stop_event_attr]):
            return False
        
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
            sign = "+" if value >= 0 else ""
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
        if not 0 <= value < 24:
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
            
            #TODO: Review all of these flags for necessity
            # Reset all movement states
            #with self._lock:
            #    self._is_slewing = False
            #    self._is_slewing_to_target = False
            #    self._is_pulse_guiding = False
            #    self._moving_primary = False
            #    self._moving_secondary = False
            
        except Exception as ex:
            raise DriverException(0x500, "Failed to abort slew", ex)
    
    def FindHome(self):
        """Locates the telescope's home position (synchronous)"""
        self._logger.info("Moving to Home")
        
        try:
            
            if self._is_parked:
                raise InvalidOperationException("The requested operation cannot be undertaken at this time: the mount is parked.")

            if self.Slewing:
                raise InvalidOperationException("The requested operation cannot be undertaken at this time: the mount is slewing.")
            
            if self.AtHome:
                self._logger.info("Mount is already at Home")
                return

            #TODO: pull park alt and az and use those rather than 180/0    
            home_az = 180
            current_time = Time.now()
            
            # Try altitudes 0-9 degrees to find position above horizon
            for target_alt in range(10):
                altaz_coord = AltAz(
                    az=home_az * u.deg, 
                    alt=target_alt * u.deg,
                    obstime=current_time,
                    location=self._site_location
                )
                
                # Convert to GCRS with current epoch (JNow)
                gcrs_coord = altaz_coord.transform_to(GCRS(obstime=current_time))
                self.TargetDeclination = gcrs_coord.dec.deg
                self.TargetRightAscension = gcrs_coord.ra.hour
                
                # Try to slew - returns False if target is reachable
                if not bool(int(self._send_command(":MS#", CommandType.STRING))):
                    self._executor.submit(self._home_arrival_monitor, target_alt)
                    self._slew_in_progress = self._executor.submit(self._slew_status_monitor)
                    return
            
            raise InvalidOperationException("Home position is below horizon, check mount alignment")
            
        except Exception as ex:
            self._logger.error(f"FindHome error: {ex}")
            raise
    
    def _slew_status_monitor(self) -> None:
        """Monitor thread to keep track of mount motion."""
        try: 

            # Check hardware slewing status
            while self._send_command(":D#", CommandType.STRING) == "|#":
                time.sleep(0.1)  # 100 ms between checks
            
            #We only care about slew settle time after gotos...
            if self._goto_in_progress:
                time.sleep(self._config.slew_settle_time)  # slew settle time is given in seconds
                self._goto_in_progress = False

        except Exception as ex:

            raise DriverException(0x502, f"Error checking slew status {ex}. Verify mount operation before proceeding!")

    def _home_arrival_monitor(self, target_alt) -> None:
        """Monitor slewing completion and verify home position"""
        try:
            while self.Slewing:
                time.sleep(0.5)
            
            alt, az = self.Altitude, self.Azimuth
            
            if abs(alt - target_alt) < 2 and abs(180 - az) < 5:
                self.AtHome = True
                self._logger.info(f"Arrived at home. Alt: {alt:.1f}, Az: {az:.1f}")
            else:
                msg = f"Did not reach home position. Alt: {alt:.1f}, Az: {az:.1f}"
                self._logger.error(msg)
                raise DriverException(f"FindHome error: {msg}")

        except Exception as ex:
            self._logger.error(f"FindHome monitoring exception: {ex}")
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
        
        if self.AtPark:
            raise ParkedException("Cannot sync while parked.")
        
        if not (0 <= altitude <= 90):
            raise InvalidValueException(f"Invalid altitude: {altitude}.  Must be between 0 and 90 deg.")

        if not (0 <= azimuth <= 360):
            raise InvalidValueException(f"Invalid azimuth: {azimuth}.  Must be between 0 and 360 deg.")
        
        try:
            
            right_ascension, declination = self._altaz_to_radec(azimuth, altitude)
            self.SyncToCoordinates(right_ascension, declination)

        except Exception as ex:
            raise DriverException(0x500,f"Sync failed: {ex}")

    def SyncToCoordinates(self, right_ascension: float, declination: float) -> None:

        if self.AtPark:
            raise ParkedException("Cannot sync while parked.")
        
        if not (0 <= right_ascension <= 24):
            raise InvalidValueException(f"Invalid altitude: {right_ascension}.  Must be between 0 and 24 hr.")

        if not (-90 <= declination <= 90):
            raise InvalidValueException(f"Invalid azimuth: {declination}.  Must be between -90 and 90 deg.")
        
        # Need to figure out how to handle the driver AlignOnSync mode.  Alternative is to query firmware on if it is in the auto alignonsync mode. <----- This is the way.
        try:
            self.TargetRightAscension = right_ascension
            self.TargetDeclination = declination
            auto_align_on_sync = ''
            command = f":{auto_align_on_sync}CM#"
            self._send_command(command, CommandType.STRING)
            #Need to figure out how to put in sync wait time here to delay position requests... ~200 ms...in a non-blocking manner
        except Exception as ex:
            raise DriverException(f"Synchronize failed. {ex}")

    def SyncToTarget(self) -> None:
        
        if self.AtPark:
            raise ParkedException("Cannot sync while parked.")
        
         # Need to figure out how to handle the driver AlignOnSync mode.  Alternative is to query firmware on if it is in the auto alignonsync mode. <----- This is the way.
        try:
            auto_align_on_sync = ''
            command = f":{auto_align_on_sync}CM#"
            self._send_command(command, CommandType.STRING)
            #Need to figure out how to put in sync wait time here to delay position requests... ~200 ms...in a non-blocking manner
        except Exception as ex:
            raise DriverException(f"Synchronize failed. {ex}")


    def SlewToAltAz(self, azimuth: float, altitude: float) -> None:
        """Slew to given altaz coordinates (synchronous)."""
        raise NotImplementedException()
    
    def SlewToAltAzAsync(self, azimuth: float, altitude: float) -> None:
        """Slew to given altaz coordinates (asynchronous)."""
        
        if self.Slewing:
            raise InvalidOperationException("Unable to start goto while slewing.")
        
        if self.Tracking:
            raise InvalidOperationException("Unable to start AltAz goto while tracking is enabled.")
        
        if self.AtPark:
            raise ParkedException("Unable to start goto while parked.")

        if not (0 <= altitude <= 90):
            raise InvalidValueException(f"Invalid altitude value: {altitude}, must be 0-90 deg.")
        
        if not (0 <= azimuth <= 360):
            raise InvalidValueException(f"Invalid azimuth value: {altitude}, must be 0-360 deg.")
        
        right_ascension, declination = self._altaz_to_radec(azimuth, altitude)

        self.SlewToCoordinatesAsync(right_ascension, declination)

    def SlewToCoordinates(self, rightAscension: float, declination: float) -> None:
        """Slew to given equatorial coordinates (synchronous)."""
        raise NotImplementedException()
    
    def SlewToCoordinatesAsync(self, right_ascension: float, declination: float) -> None:
        """Slew to given equatorial coordinates (asynchronous)."""
        # Set target coordinates
        self.TargetRightAscension = right_ascension  
        self.TargetDeclination = declination
        
        # Start async slew
        self.SlewToTargetAsync()
    
    def SlewToTarget(self) -> None:
        """Slew to current target coordinates (synchronous)."""
        raise NotImplementedException()        

    
    def SlewToTargetAsync(self) -> None:
        """Slew to target coordinates (asynchronous)."""
        with self._lock:
            if not self._is_target_set:
                raise InvalidOperationException("Target not set")
        
            try:
                # Send slew command
                result = self._send_command(":MS#", CommandType.BOOL)
                if result == "True":
                    raise InvalidOperationException("Target below horizon")
                
                self._goto_in_progress = True
                self._slew_in_progress = self._executor.submit(self._slew_status_monitor)

                # Store slew target and set flags
                #self._slew_target = self._target  #Not sure why I think I wanted to do this
                self._is_at_home = False
                
            except Exception as ex:
                raise DriverException(0x500, "Async slew failed", ex)
    
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
            max_alt = 89.0  # Prevent divide by zero near zenith
            
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
            if not hasattr(self, '_pulse_guide_ns_start') or not hasattr(self, '_pulse_guide_ns_duration'):
                return
                
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
            if not hasattr(self, '_pulse_guide_ew_start') or not hasattr(self, '_pulse_guide_ew_duration'):
                return
                
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

    def Park(self) -> None:
        """Park the mount."""
        if self.AtPark:
            return
        
        try:
            self._send_command(":hP#", CommandType.BLIND)
            self.AtPark = True
            
        except Exception as ex:
            raise DriverException(0x500, "Park failed", ex)
    
    def SetPark(self) -> None:
        """Set the telescopes park position to its current position."""

        try:
            self._config.park_location = True
            park_alt = round(self.Altitude, 3)
            park_az = round(self.Azimuth, 3)
            
            self._config.park_location_altitude = park_alt
            self._config.park_location_azimuth = park_az
            
            # Format as DDD.ddd for both azimuth and altitude
            command = f":*PS1{park_az:07.3f}{park_alt:07.3f}#"
            self._send_command(command, CommandType.BLIND)
            self._config.save()
            
        except Exception as ex:
            raise DriverException(0x500, f"SetPark failed: {ex}")

    def Unpark(self) -> None:
        """Unpark the mount (not supported by TTS160)."""
        raise NotImplementedException()
    
    # UTC Date Property
    @property
    def UTCDate(self) -> str:
        """Get mount's UTC date and time."""
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
            
            # Create local datetime
            local_dt = datetime(year, month, day, hour, minute, second)
            
            # Convert to UTC
            utc_dt = local_dt + timedelta(hours=offset_hours)
            
            return utc_dt.replace(tzinfo=timezone.utc).isoformat()
            
        except Exception as ex:
            raise DriverException(0x500, "Failed to get UTC date", ex)
    
    @UTCDate.setter
    def UTCDate(self, value: datetime) -> None:
        """Set mount's UTC date and time."""
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
            
        except Exception as ex:
            raise DriverException(0x500, "Failed to set UTC date", ex)

    # Capability Properties (static for TTS160)
    @property
    def CanFindHome(self) -> bool:
        return self._CanFindHome
    
    @property
    def CanPark(self) -> bool:
        return self._CanPark
    
    @property
    def CanPulseGuide(self) -> bool:
        return self._CanPulseGuide
    
    @property
    def CanSetPierSide(self) -> bool:
        return self._CanSetPierSide

    @property
    def CanSetTracking(self) -> bool:
        return self._CanSetTracking
    
    @property
    def CanSlew(self) -> bool:
        return self._CanSlew
    
    @property
    def CanSlewAltAz(self) -> bool:
        return self._CanSlewAltAz
    
    @property
    def CanSlewAltAzAsync(self) -> bool:
        return self._CanSlewAltAzAsync

    @property
    def CanSlewAsync(self) -> bool:
        return self._CanSlewAsync
    
    def CanMoveAxis(self, axis) -> bool:
        
        if axis <= 1:
            return self._CanMoveAxis
        else:
            return False
    
    @property
    def CanSetDeclinationRate(self) -> bool:
        return self._CanSetDeclinationRate
    
    @property
    def CanSetRightAscensionRate(self) -> bool:
        return self._CanSetRightAscensionRate
    
    @property
    def CanSetPark(self) -> bool:
        return self._CanSetPark
    
    @property
    def CanSetGuideRates(self) -> bool:
        return self._CanSetGuideRates  

    def AxisRates(self, axis: TelescopeAxes) -> List[Rate]:
        """Get available rates for specified axis."""
        if axis in [TelescopeAxes.axisPrimary, TelescopeAxes.axisSecondary]:  # Primary and secondary axes
            return self._AxisRates
        else:
            return []
    
    @property
    def CanSync(self) -> bool:
        return self._CanSync
    
    @property
    def CanSyncAltAz(self) -> bool:
        return self._CanSyncAltAz
    
    @property
    def CanUnpark(self) -> bool:
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