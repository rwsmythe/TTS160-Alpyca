# File: TTS160Device.py
"""Complete TTS160 Device Hardware Implementation."""

import threading
import time
import math
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from logging import Logger

# AstroPy imports for coordinate transformations
from astropy.coordinates import SkyCoord, AltAz, ICRS, EarthLocation
from astropy.time import Time
from astropy import units as u

# Local imports
from .tts160_types import CommandType, Rate, EquatorialCoordinates
from exceptions import (
    DriverException, InvalidValueException, InvalidOperationException,
    NotImplementedException
)


class TTS160Device:
    """Complete TTS160 Hardware Implementation with ASCOM compliance."""
    
    # Constants from C# implementation
    MOVEAXIS_WAIT_TIME = 2.0  # seconds
    SYNC_WAIT_TIME = 0.2      # seconds
    
    def __init__(self, logger: Logger):
        self._logger = logger
        self._lock = threading.RLock()
        
        # Import here to avoid circular imports
        from . import TTS160Global
        self._config = TTS160Global.get_config()
        self._serial_manager = None
        
        # Connection state
        self._is_connected = False
        self._connecting = False
        
        # Mount state with thread safety
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
        
        # Hardware capabilities
        self._dev_firmware = True
        
        # Site location for coordinate transforms
        self._site_location = None
        self._update_site_location()
    
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
    def Connect(self) -> None:
        """Connect to the TTS160 mount."""
        with self._lock:
            if self._is_connected:
                return
            
            self._connecting = True
            
            try:
                from . import TTS160Global
                self._serial_manager = TTS160Global.get_serial_manager(self._logger)
                self._serial_manager.connect(self._config.dev_port)
                self._initialize_mount()
                self._is_connected = True
                self._logger.info("TTS160 connected successfully")
                
            except Exception as ex:
                self._logger.error(f"Connection failed: {ex}")
                raise DriverException(0x500, "Connection failed", ex)
            finally:
                self._connecting = False
    
    def Disconnect(self) -> None:
        """Disconnect from the TTS160 mount."""
        with self._lock:
            if not self._is_connected:
                return
            
            self._connecting = True
            
            try:
                if self._serial_manager:
                    self._serial_manager.disconnect()
                    self._serial_manager = None
                
                self._is_connected = False
                self._logger.info("TTS160 disconnected")
                
            except Exception as ex:
                self._logger.error(f"Disconnect error: {ex}")
            finally:
                self._connecting = False
    
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
    
    def _send_command(self, command: str, command_type: CommandType) -> str:
        """Send command to mount."""
        if not self._serial_manager:
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
        if time is None:
            time = datetime.now(timezone.utc)
        
        # Create AltAz coordinate
        altaz_frame = AltAz(obstime=Time(time), location=self._site_location)
        altaz_coord = SkyCoord(
            az=azimuth * u.deg,
            alt=altitude * u.deg,
            frame=altaz_frame
        )
        
        # Transform to ICRS
        icrs_coord = altaz_coord.icrs
        
        return icrs_coord.ra.hour, icrs_coord.dec.degree
    
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
    
    # Connection Properties
    @property
    def Connected(self) -> bool:
        """ASCOM Connected property."""
        with self._lock:
            return self._is_connected
    
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
            return self._connecting
    
    # Mount Position Properties
    @property
    def Altitude(self) -> float:
        """Current altitude in degrees."""
        try:
            if self._dev_firmware:
                result = self._send_command(":*GA#", CommandType.STRING).rstrip('#')
                return float(result) * (180 / math.pi)  # Convert radians to degrees
            else:
                result = self._send_command(":GA#", CommandType.STRING)
                return self._dms_to_degrees(result)
        except Exception as ex:
            raise DriverException(0x500, "Failed to get altitude", ex)
    
    @property
    def Azimuth(self) -> float:
        """Current azimuth in degrees."""
        try:
            if self._dev_firmware:
                result = self._send_command(":*GZ#", CommandType.STRING).rstrip('#')
                return float(result) * (180 / math.pi)  # Convert radians to degrees
            else:
                result = self._send_command(":GZ#", CommandType.STRING)
                return self._dms_to_degrees(result)
        except Exception as ex:
            raise DriverException(0x500, "Failed to get azimuth", ex)
    
    @property
    def Declination(self) -> float:
        """Current declination in degrees."""
        try:
            if self._dev_firmware:
                result = self._send_command(":*GD#", CommandType.STRING).rstrip('#')
                return float(result) * (180 / math.pi)  # Convert radians to degrees
            else:
                result = self._send_command(":GD#", CommandType.STRING)
                return self._dms_to_degrees(result)
        except Exception as ex:
            raise DriverException(0x500, "Failed to get declination", ex)
    
    @property
    def RightAscension(self) -> float:
        """Current right ascension in hours."""
        try:
            if self._dev_firmware:
                result = self._send_command(":*GR#", CommandType.STRING).rstrip('#')
                ra = float(result) * (180 / math.pi) / 15  # Convert radians to hours
                return ra % 24  # Normalize to 0-24 hours
            else:
                result = self._send_command(":GR#", CommandType.STRING)
                return self._hms_to_hours(result)
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
    
    # Site Properties
    @property  
    def SiteLatitude(self) -> float:
        """Site latitude in degrees."""
        return self._site_location.lat.degree
    
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
    def AtHome(self) -> bool:
        """True if mount is at home position."""
        with self._lock:
            return self._is_at_home
    
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
    def Slewing(self) -> bool:
        """True if mount is slewing."""
        try:
            # Check hardware slewing status
            if self._dev_firmware:
                result = self._send_command(":D#", CommandType.STRING)
                is_slewing = result == "|#"
                
                with self._lock:
                    if not is_slewing and self._is_slewing:
                        # Slew just finished - handle settle time
                        self._handle_slew_completion()
                    
                    self._is_slewing = is_slewing
                    return is_slewing
            else:
                with self._lock:
                    return self._is_slewing
                
        except Exception as ex:
            self._logger.warning(f"Error checking slewing status: {ex}")
            with self._lock:
                return self._is_slewing
    
    def _handle_slew_completion(self) -> None:
        """Handle slew completion and settling."""
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
            sign = "+" if value >= 0 else ""
            command = f":Sd{sign}{dms_str}#"
            
            result = self._send_command(command, CommandType.BOOL)
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
            
            # Reset all movement states
            with self._lock:
                self._is_slewing = False
                self._is_slewing_to_target = False
                self._is_pulse_guiding = False
                self._moving_primary = False
                self._moving_secondary = False
            
        except Exception as ex:
            raise DriverException(0x500, "Failed to abort slew", ex)
    
    def SlewToCoordinates(self, rightAscension: float, declination: float) -> None:
        """Slew to given equatorial coordinates (synchronous)."""
        # Set target coordinates
        self.TargetRightAscension = rightAscension
        self.TargetDeclination = declination
        
        # Start slew
        self.SlewToTarget()
    
    def SlewToCoordinatesAsync(self, rightAscension: float, declination: float) -> None:
        """Slew to given equatorial coordinates (asynchronous)."""
        # Set target coordinates
        self.TargetRightAscension = rightAscension  
        self.TargetDeclination = declination
        
        # Start async slew
        self.SlewToTargetAsync()
    
    def SlewToTarget(self) -> None:
        """Slew to current target coordinates (synchronous)."""
        with self._lock:
            if not self._is_target_set:
                raise InvalidOperationException("Target not set")
        
        try:
            # Send slew command
            result = self._send_command(":MS#", CommandType.BOOL)
            if result == "True":
                raise InvalidOperationException("Target below horizon")
            
            # Store slew target
            with self._lock:
                self._slew_target = self._target
                self._is_slewing = True
                self._is_slewing_to_target = True
                self._is_at_home = False
            
            # Wait for slew completion
            timeout = 180  # seconds
            start_time = time.time()
            
            while self.Slewing:
                time.sleep(0.2)
                if time.time() - start_time > timeout:
                    self.AbortSlew()
                    raise DriverException(0x500, "Slew timeout")
            
        except Exception as ex:
            raise DriverException(0x500, "Slew failed", ex)
    
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
            
            # Store slew target and set flags
            self._slew_target = self._target
            self._is_slewing = True
            self._is_slewing_to_target = True
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
    def UTCDate(self) -> datetime:
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
            
            return utc_dt.replace(tzinfo=timezone.utc)
            
        except Exception as ex:
            raise DriverException(0x500, "Failed to get UTC date", ex)
    
    # Capability Properties (static for TTS160)
    @property
    def CanFindHome(self) -> bool:
        return True
    
    @property
    def CanPark(self) -> bool:
        return True
    
    @property
    def CanPulseGuide(self) -> bool:
        return True
    
    @property
    def CanSetTracking(self) -> bool:
        return True
    
    @property
    def CanSlew(self) -> bool:
        return True
    
    @property
    def CanSlewAsync(self) -> bool:
        return True
    
    def AxisRates(self, axis: int) -> List[Rate]:
        """Get available rates for specified axis."""
        if axis in [0, 1]:  # Primary and secondary axes
            return [Rate(0.0, 3.5)]
        else:
            return []
    
    # Static Properties  
    @property
    def Name(self) -> str:
        return "TTS-160"
    
    @property
    def Description(self) -> str:
        return "TTS160 Alpaca Driver v356.1"
    
    @property
    def DriverVersion(self) -> str:
        return "356.1"