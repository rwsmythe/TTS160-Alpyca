# File: TTS160Device.py
"""Complete TTS160 Device Hardware Implementation."""

import threading
import time
import math
import bisect
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from logging import Logger
from concurrent.futures import ThreadPoolExecutor, Future

# AstroPy imports for coordinate transformations
from astropy.coordinates import SkyCoord, AltAz, ICRS, EarthLocation, GCRS
from astropy.time import Time
from astropy import units as u

# Local imports
from tts160_types import CommandType, Rate, EquatorialCoordinates
from exceptions import (
    DriverException, InvalidValueException, InvalidOperationException,
    NotImplementedException
)
from telescope import (
    TelescopeMetadata, EquatorialCoordinateType, DriveRates, PierSide,
    AlignmentModes
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
        self._is_slewing = False
        self._is_slewing_to_target = False
        self._is_pulse_guiding = False
        self._moving_primary = False
        self._moving_secondary = False
        self._is_parked = False
        self._is_at_home = False
        self._tracking = False
        
        # Target state
        self._target = EquatorialCoordinates(0.0, 0.0)
        self._slew_target = EquatorialCoordinates(0.0, 0.0)
        self._is_target_set = False
        
        # Pulse guiding state
        self._pulse_guide_duration = 0
        self._pulse_guide_start = datetime.min
        
        # Site location for coordinate transforms
        self._site_location = None
        self._update_site_location()

        #Other misc variables
        self._AxisRates = [Rate(0.0, 3.5)]
        self._DriveRates = [DriveRates.driveSidereal, DriveRates.driveLunar, DriveRates.driveSolar]

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
            #self._logger.info("Starting Async Connect Routine")
            #return self._executor.submit(self._connect_mount)
            self._connect_mount()

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
            self._Connected = True
            self._initialize_mount()
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
            with self._lock:
                self._is_slewing = False
                self._is_slewing_to_target = False
                self._is_pulse_guiding = False
                self._moving_primary = False
                self._moving_secondary = False
            
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

            self._Connecting = True
            
            try:
                if self._serial_manager:
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
        return NotImplementedException()
    
    def CommandBool(self, msg: str) -> bool:
        return NotImplementedException()
    
    def CommandString(self, msg: str) -> str:
        return NotImplementedException()

    def _send_command(self, command: str, command_type: CommandType) -> str:
        """Send command to mount."""
        if not self._Connected:
            raise RuntimeError("Device not connected")
        
        return self._serial_manager.send_command(command, command_type)
    
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
    
    def _altaz_to_radec(self, azimuth: float, altitude: float, 
                       time: datetime = None) -> tuple[float, float]:
        """Convert Alt/Az to RA/Dec using AstroPy."""
        #TODO: Time should be preferentially taken from the mount, not the computer, I think
        if time is None:
            time = datetime.now(timezone.utc)
        
        # Create AltAz coordinate
        altaz_frame = AltAz(obstime=Time(time), location=self._site_location)
        altaz_coord = SkyCoord(
            az=azimuth * u.deg,
            alt=altitude * u.deg,
            frame=altaz_frame
        )
        
        #TODO: Verify that ICRS is equivalent to JNow/TopoEqu.  Also provide for conversion to J2000 if that is what the epoch is set to.
        # Transform to ICRS
        icrs_coord = altaz_coord.icrs
        
        return icrs_coord.ra.hour, icrs_coord.dec.degree
    
    #TODO: Note, here and above: ICRS is ~J2000 unless current epoch is specified.  See "https://stackoverflow.com/questions/52900678/coordinates-transformation-in-astropy" for add'l details
    #In order to convert to "JNow", consider doing ICRS->GCRS conversion with timenow.
    #Implementation Example:
    """
    # Starting coordinates (ICRS/J2000)
    coord = SkyCoord(ra=83.633*u.deg, dec=22.014*u.deg, frame='icrs')

    # Current time and observer location
    now = Time.now()
    location = EarthLocation(lat=40.7*u.deg, lon=-74.0*u.deg, height=100*u.m)

    # Convert to current epoch equatorial (accounting for precession)
    coord_now = coord.transform_to('gcrs', obstime=now)

    # Convert to topocentric (Alt/Az frame includes all effects)
    altaz_frame = AltAz(obstime=now, location=location)
    coord_topocentric = coord.transform_to(altaz_frame)
    """

    def _radec_to_altaz(self, right_ascension: float, declination: float,
                       time: datetime = None) -> tuple[float, float]:
        """Convert RA/Dec to Alt/Az using AstroPy."""
        if time is None:
            time = datetime.now(timezone.utc)
        
        # Create ICRS coordinate
        icrs_coord = SkyCoord(
            ra=right_ascension * u.hour,
            dec=declination * u.deg,
            frame='icrs'
        )
        
        # Transform to AltAz
        altaz_frame = AltAz(obstime=Time(time), location=self._site_location)
        altaz_coord = icrs_coord.transform_to(altaz_frame)
        
        return altaz_coord.az.degree, altaz_coord.alt.degree
    
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
            self._check_connected("Action")
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

    # Site Properties
    @property  
    def SiteLatitude(self) -> float:
        """Site latitude in degrees."""
        return self._site_location.lat.degree
    
    #TODO: I don't think this was implemented in the ASCOM driver, verify.
    @SiteLatitude.setter
    def SiteLatitude(self, value: float) -> None:
        """Set site latitude."""
        if not -90 <= value <= 90:
            raise InvalidValueException(f"Invalid latitude: {value}")
        
        self._site_location = EarthLocation(
            lat=value * u.deg,
            lon=self._site_location.lon,
            height=self._site_location.height
        )
    
    @property
    def SiteLongitude(self) -> float:
        """Site longitude in degrees."""
        return self._site_location.lon.degree
    
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
            self._logger.warning(f"Error checking slewing status: {ex}")
            with self._lock:
                return self._is_slewing
    
    #TODO: This needs to be made asynchronous...spin it off into its own thread?
    def _handle_slew_completion(self) -> None:
        """Handle slew completion and settling."""
        #TODO: Why use getattr rather than just the self._config.SlewSettleTime?
        settle_time = getattr(self._config, 'slew_settle_time', 0)
        if settle_time > 0:
            time.sleep(settle_time)
        
        # Reset slewing flags
        self._is_slewing = False
        self._is_slewing_to_target = False
        self._moving_primary = False
        self._moving_secondary = False
    
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
    def IsPulseGuiding(self) -> bool:
        """True if pulse guiding is active."""
        with self._lock:
            # Check if pulse guide duration has expired
            if (self._pulse_guide_start > datetime.min and 
                self._pulse_guide_duration > 0):
                
                elapsed = (datetime.now() - self._pulse_guide_start).total_seconds() * 1000
                if elapsed >= self._pulse_guide_duration:
                    self._is_pulse_guiding = False
                    self._pulse_guide_start = datetime.min
            
            return self._is_pulse_guiding
    
    # Target Properties
    @property
    def TargetDeclination(self) -> float:
        """Target declination in degrees."""
        with self._lock:
            if not self._is_target_set:
                raise InvalidOperationException("Target declination not set")
            return self._target.declination
    
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
            #TODO: can python test a boolean variable like that?
            if result != "True":
                raise InvalidValueException("Mount rejected declination value")
            
            # Update state
            with self._lock:
                self._target = EquatorialCoordinates(self._target.right_ascension, value)
                if self._target.right_ascension != 0:
                    self._is_target_set = True
                
        except Exception as ex:
            raise DriverException(0x500, "Failed to set target declination", ex)
    
    @property
    def TargetRightAscension(self) -> float:
        """Target right ascension in hours.""" 
        with self._lock:
            if not self._is_target_set:
                raise InvalidOperationException("Target right ascension not set")
            return self._target.right_ascension
    
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
            if result != "True":
                raise InvalidValueException("Mount rejected right ascension value")
            
            # Update state
            with self._lock:
                self._target = EquatorialCoordinates(value, self._target.declination)
                if self._target.declination != 0:
                    self._is_target_set = True
                
        except Exception as ex:
            raise DriverException(0x500, "Failed to set target right ascension", ex)
    
    # Movement Methods
    def AbortSlew(self) -> None:
        """Abort any current slewing."""
        try:
            self._send_command(":Q#", CommandType.BLIND)
            
            #TODO: Review all of these flags for necessity
            # Reset all movement states
            with self._lock:
                self._is_slewing = False
                self._is_slewing_to_target = False
                self._is_pulse_guiding = False
                self._moving_primary = False
                self._moving_secondary = False
            
        except Exception as ex:
            raise DriverException(0x500, "Failed to abort slew", ex)
    
    def FindHome(self):
        """Locates the telescope's home position (synchronous)"""
        self._logger.info("Moving to Home")
        
        try:
            
            if self._is_parked:
                raise InvalidOperationException("The requirest operation cannot be undertaken at this time: the mount is parked.")

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
                    self._executor.submit(self._monitor_home_arrival, target_alt)
                    self._slew_in_progress = self._executor.submit(self._monitor_slew_status)
                    return
            
            raise InvalidOperationException("Home position is below horizon, check mount alignment")
            
        except Exception as ex:
            self._logger.error(f"FindHome error: {ex}")
            raise
    
    def _monitor_slew_status(self) -> None:
        """Monitor thread to keep track of mount motion."""
        try: 

            # Check hardware slewing status
            while self._send_command(":D#", CommandType.STRING) == "|#":
                time.sleep(0.1)  # 100 ms between checks
            
            time.sleep(self._config.slew_settle_time)  # slew settle time is given in seconds
                
        except Exception as ex:

            raise DriverException(0x502, f"Error checking slew status {ex}. Verify mount operation before proceeding!")
  
    
    #TODO: This needs to be made asynchronous...spin it off into its own thread?
    #def _handle_slew_completion(self) -> None:
    #    """Handle slew completion and settling."""
    #    #TODO: Why use getattr rather than just the self._config.SlewSettleTime?
    #    settle_time = getattr(self._config, 'slew_settle_time', 0)
    #    if settle_time > 0:
    #        time.sleep(settle_time)
        
        # Reset slewing flags
    #    self._is_slewing = False
    #    self._is_slewing_to_target = False
    #    self._moving_primary = False
    #    self._moving_secondary = False

    def _monitor_home_arrival(self, target_alt) -> None:
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
    
    def SlewToAltAz(self, altitude: float, azimuth: float) -> None:
        """Slew to given altaz coordinates (synchronous)."""
        raise NotImplementedException()
    
    def SlewToAltAzAsync(self, altitude: float, azimuth: float) -> None:
        """Slew to given altaz coordinates (asynchronous)."""
        test = False

    def SlewToCoordinates(self, rightAscension: float, declination: float) -> None:
        """Slew to given equatorial coordinates (synchronous)."""
        raise NotImplementedException()
    
    def SlewToCoordinatesAsync(self, rightAscension: float, declination: float) -> None:
        """Slew to given equatorial coordinates (asynchronous)."""
        # Set target coordinates
        self.TargetRightAscension = rightAscension  
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
                
                self._slew_in_progress = self._executor.submit(self._monitor_slew_status)

                # Store slew target and set flags
                self._slew_target = self._target
                self._is_at_home = False
                
            except Exception as ex:
                raise DriverException(0x500, "Async slew failed", ex)
    
    def PulseGuide(self, direction: int, duration: int) -> None:
        """Pulse guide in specified direction for given duration."""
        if not 0 <= duration <= 9999:
            raise InvalidValueException(f"Duration {duration} outside valid range 0-9999ms")
        
        try:
            # Map directions to mount commands (note: N/S are reversed on TTS160)
            command_map = {
                2: f":Mge{duration:04d}#",    # guideEast
                3: f":Mgw{duration:04d}#",    # guideWest
                0: f":Mgs{duration:04d}#",    # guideNorth (reversed)
                1: f":Mgn{duration:04d}#"     # guideSouth (reversed)
            }
            
            if direction not in command_map:
                raise InvalidValueException(f"Invalid guide direction: {direction}")
            
            self._send_command(command_map[direction], CommandType.BLIND)
            
            # Set pulse guide state
            with self._lock:
                self._is_pulse_guiding = True
                self._pulse_guide_duration = duration
                self._pulse_guide_start = datetime.now()
            
        except Exception as ex:
            raise DriverException(0x500, "Pulse guide failed", ex)
    
    def Park(self) -> None:
        """Park the mount."""
        if self.AtPark:
            return
        
        try:
            self._send_command(":hP#", CommandType.BLIND)
            self.AtPark = True
            
        except Exception as ex:
            raise DriverException(0x500, "Park failed", ex)
    
    def Unpark(self) -> None:
        """Unpark the mount (not supported by TTS160)."""
        raise InvalidOperationException("Unpark is not supported by TTS160")
    
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

    def AxisRates(self, axis: int) -> List[Rate]:
        """Get available rates for specified axis."""
        if axis in [0, 1]:  # Primary and secondary axes
            return self._AxisRates
        else:
            return []
    
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