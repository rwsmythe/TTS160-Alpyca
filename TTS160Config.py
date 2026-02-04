# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# TTS160config.py - TTS160 persistent configuration file.  Adapted from Alpyca's
# config.py
#
# Author:   Reid W. Smythe <rwsmythe@gmail.com> (rws)
#
# Python Compatibility: Requires Python 3.7 or later
# GitHub: https://github.com/ASCOMInitiative/AlpycaDevice
#
# -----------------------------------------------------------------------------
# MIT License
#
# Copyright (c) 2022-2024 Bob Denny
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# -----------------------------------------------------------------------------

import threading
from pathlib import Path
from typing import Any, Union
import sys
import toml


class TTS160ConfigError(Exception):
    """Custom exception for TTS160 configuration errors"""
    pass


class TTS160Config:
    """Device configuration with thread-safe TOML persistence.
    
    For docker-based installations, looks for /alpyca/TTS160config.toml
    first, with any settings there overriding ./TTS160config.toml.
    
    Attributes:
        dev_port: Device communication port
        site_elevation: Observatory elevation
        site_latitude: Observatory latitude  
        site_longitude: Observatory longitude
        sync_time_on_connect: Sync mount time with computer on initial connect
        pulse_guide_equatorial_frame: Pulses move mount in the equatorial frame
        pulse_guide_altitude_compensation: Compensate azimuth pulse length for altitude
        pulse_guide_max_compensation: maximum compensation time to prevent a timeout condition due to unexpected length (int, ms)
        pulse_guide_compensation_buffer: set a safety buffer to the maximum compensation time (int, ms)
        slew_settle_time: Settle time after slew events (int, sec)
    """
    
    # Class constants
    DEFAULT_CONFIG_FILE = 'TTS160config.toml'
    OVERRIDE_CONFIG_PATH = '/alpyca/TTS160config.toml'
    
    def get_config_dir(self):
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent
        return Path.cwd()

    def __init__(self):
        """Initialize configuration by loading TOML files."""
        self._lock = threading.RLock()
        self._dict = {}
        self._dict2 = {}
        
        # Use pathlib for file paths
        self._config_file = self.get_config_dir() / self.DEFAULT_CONFIG_FILE
        self._override_file = Path(self.OVERRIDE_CONFIG_PATH)
        
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from TOML files.
        
        Raises:
            TTS160ConfigError: If primary config file cannot be loaded.
        """
        with self._lock:
            # Load primary config file
            try:
                self._dict = toml.load(self._config_file)
            except (FileNotFoundError, toml.TomlDecodeError) as e:
                raise TTS160ConfigError(
                    f"Failed to load primary config file {self._config_file}: {e}"
                ) from e
            
            # Load optional override file
            try:
                if self._override_file.exists():
                    self._dict2 = toml.load(self._override_file)
            except toml.TomlDecodeError as e:
                raise TTS160ConfigError(
                    f"Failed to load override config file {self._override_file}: {e}"
                ) from e
    
    def _get_toml(self, sect: str, item: str) -> Any:
        """Get configuration value, checking override file first.
        
        Args:
            sect: Configuration section name
            item: Configuration item name
            
        Returns:
            Configuration value or None if not found
        """
        with self._lock:
            try:
                # Check override file first
                return self._dict2[sect][item]
            except KeyError:
                try:
                    # Fall back to primary config
                    return self._dict[sect][item]
                except KeyError:
                    return None
    
    def _put_toml(self, sect: str, item: str, setting: Any) -> None:
        """Set configuration value in the appropriate dictionary.
        
        Args:
            sect: Configuration section name
            item: Configuration item name
            setting: Value to set
        """
        with self._lock:
            # If override file exists or has been used, update it
            # Otherwise update primary config
            if self._dict2 or self._override_file.exists():
                if sect not in self._dict2:
                    self._dict2[sect] = {}
                self._dict2[sect][item] = setting
            else:
                if sect not in self._dict:
                    self._dict[sect] = {}
                self._dict[sect][item] = setting
    
    def save(self) -> None:
        """Save configuration to file, overwriting existing.
        
        Raises:
            TTS160ConfigError: If configuration cannot be saved.
        """
        with self._lock:
            try:
                # Save to override file if it exists or has been used
                if self._dict2 or self._override_file.exists():
                    # Ensure directory exists
                    self._override_file.parent.mkdir(parents=True, exist_ok=True)
                    with self._override_file.open('w', encoding='utf-8') as f:
                        toml.dump(self._dict2, f)
                else:
                    # Save to primary config file
                    with self._config_file.open('w', encoding='utf-8') as f:
                        toml.dump(self._dict, f)
            except (OSError, PermissionError) as e:
                raise TTS160ConfigError(f"Failed to save configuration: {e}") from e
    
    def reload(self) -> None:
        """Reload configuration from files.
        
        Raises:
            TTS160ConfigError: If configuration files cannot be reloaded.
        """
        with self._lock:
            self._dict = {}
            self._dict2 = {}
            self._load_config()
    
    # Configuration section constants
    DEVICE_SECTION = 'device'
    SITE_SECTION = 'site'
    DRIVER_SECTION = 'driver'
    GPS_SECTION = 'gps'
    ALIGNMENT_SECTION = 'alignment'
    
    # --------------
    # Device Section
    # --------------
    
    @property
    def dev_port(self) -> str:
        """Device port configuration."""
        return self._get_toml(self.DEVICE_SECTION, 'dev_port') or 'COM1'
    
    @dev_port.setter
    def dev_port(self, value: str) -> None:
        self._put_toml(self.DEVICE_SECTION, 'dev_port', value)
    
    # --------------
    # Site Section
    # --------------
    
    @property
    def site_elevation(self) -> Union[str, float]:
        """Site elevation configuration."""
        return self._get_toml(self.SITE_SECTION, 'site_elevation') or 0.0
    
    @site_elevation.setter
    def site_elevation(self, value: Union[str, float]) -> None:
        self._put_toml(self.SITE_SECTION, 'site_elevation', value)
    
    @property
    def site_latitude(self) -> Union[str, float]:
        """Site latitude configuration."""
        return self._get_toml(self.SITE_SECTION, 'site_latitude') or 0.0
    
    @site_latitude.setter
    def site_latitude(self, value: Union[str, float]) -> None:
        self._put_toml(self.SITE_SECTION, 'site_latitude', value)
    
    @property
    def site_longitude(self) -> Union[str, float]:
        """Site longitude configuration."""
        return self._get_toml(self.SITE_SECTION, 'site_longitude') or 0.0
    
    @site_longitude.setter
    def site_longitude(self, value: Union[str, float]) -> None:
        self._put_toml(self.SITE_SECTION, 'site_longitude', value)
    
    #-----------------
    # Driver Section
    #-----------------

    @property
    def sync_time_on_connect(self) -> bool:
        """Synch mount time with computer on connect."""
        value = self._get_toml(self.DRIVER_SECTION, 'sync_time_on_connect')
        return True if value is None else value
    
    @sync_time_on_connect.setter
    def sync_time_on_connect(self, value: bool) -> None:
        self._put_toml(self.DRIVER_SECTION, 'sync_time_on_connect', value)

    @property
    def pulse_guide_equatorial_frame(self) -> bool:
        """Use the equatorial frame for pulse guides"""
        value = self._get_toml(self.DRIVER_SECTION, 'pulse_guide_equatorial_frame')
        return True if value is None else value
    
    @pulse_guide_equatorial_frame.setter
    def pulse_guide_equatorial_frame(self, value: bool) -> None:
        self._put_toml(self.DRIVER_SECTION, 'pulse_guide_equatorial_frame',value)

    @property
    def pulse_guide_altitude_compensation(self) -> bool:
        """Compensate azimuth pulse length for mount altitude"""
        value = self._get_toml(self.DRIVER_SECTION, 'pulse_guide_altitude_compensation')
        return True if value is None else value

    @pulse_guide_altitude_compensation.setter
    def pulse_guide_altitude_compensation(self, value: bool) -> None:
        self._put_toml(self.DRIVER_SECTION, 'pulse_guide_altitude_compensation', value)

    @property
    def pulse_guide_max_compensation(self) -> int:
        """Compensate azimuth pulse length for mount altitude"""
        return self._get_toml(self.DRIVER_SECTION, 'pulse_guide_max_compensation') or 1000

    @pulse_guide_max_compensation.setter
    def pulse_guide_max_compensation(self, value: int) -> None:
        self._put_toml(self.DRIVER_SECTION, 'pulse_guide_max_compensation', value)

    @property
    def pulse_guide_compensation_buffer(self) -> int:
        """Compensate azimuth pulse length for mount altitude"""
        return self._get_toml(self.DRIVER_SECTION, 'pulse_guide_compensation_buffer') or 20

    @pulse_guide_compensation_buffer.setter
    def pulse_guide_compensation_buffer(self, value: int) -> None:
        self._put_toml(self.DRIVER_SECTION, 'pulse_guide_compensation_buffer', value)
    
    @property
    def slew_settle_time(self) -> int:
        """Time to wait after slew event"""
        return self._get_toml(self.DRIVER_SECTION, 'slew_settle_time') or 1
    
    @slew_settle_time.setter
    def slew_settle_time(self, value: int) -> None:
        self._put_toml(self.DRIVER_SECTION, 'slew_settle_time', value)

    # --------------
    # GPS Section
    # --------------

    @property
    def gps_enabled(self) -> bool:
        """Enable GPS support for automatic location updates."""
        value = self._get_toml(self.GPS_SECTION, 'enabled')
        return False if value is None else value

    @gps_enabled.setter
    def gps_enabled(self, value: bool) -> None:
        self._put_toml(self.GPS_SECTION, 'enabled', value)

    @property
    def gps_port(self) -> str:
        """GPS serial port (e.g., 'COM6' or '/dev/ttyUSB1')."""
        return self._get_toml(self.GPS_SECTION, 'port') or ''

    @gps_port.setter
    def gps_port(self, value: str) -> None:
        self._put_toml(self.GPS_SECTION, 'port', value)

    @property
    def gps_baudrate(self) -> int:
        """GPS serial port baud rate."""
        return self._get_toml(self.GPS_SECTION, 'baudrate') or 9600

    @gps_baudrate.setter
    def gps_baudrate(self, value: int) -> None:
        self._put_toml(self.GPS_SECTION, 'baudrate', value)

    @property
    def gps_min_fix_quality(self) -> int:
        """Minimum NMEA GGA fix quality (1=GPS, 2=DGPS, 4=RTK)."""
        return self._get_toml(self.GPS_SECTION, 'min_fix_quality') or 1

    @gps_min_fix_quality.setter
    def gps_min_fix_quality(self, value: int) -> None:
        self._put_toml(self.GPS_SECTION, 'min_fix_quality', value)

    @property
    def gps_min_satellites(self) -> int:
        """Minimum satellites required for valid fix."""
        return self._get_toml(self.GPS_SECTION, 'min_satellites') or 4

    @gps_min_satellites.setter
    def gps_min_satellites(self, value: int) -> None:
        self._put_toml(self.GPS_SECTION, 'min_satellites', value)

    @property
    def gps_push_on_connect(self) -> bool:
        """Push GPS location to mount once when connecting (if fix available)."""
        value = self._get_toml(self.GPS_SECTION, 'push_on_connect')
        return True if value is None else value

    @gps_push_on_connect.setter
    def gps_push_on_connect(self, value: bool) -> None:
        self._put_toml(self.GPS_SECTION, 'push_on_connect', value)

    @property
    def gps_location_name(self) -> str:
        """Location name sent to mount (max 10 chars)."""
        return self._get_toml(self.GPS_SECTION, 'location_name') or 'GPS'

    @gps_location_name.setter
    def gps_location_name(self, value: str) -> None:
        self._put_toml(self.GPS_SECTION, 'location_name', value[:10])

    @property
    def gps_read_timeout(self) -> float:
        """Serial read timeout in seconds."""
        return self._get_toml(self.GPS_SECTION, 'read_timeout') or 2.0

    @gps_read_timeout.setter
    def gps_read_timeout(self, value: float) -> None:
        self._put_toml(self.GPS_SECTION, 'read_timeout', value)

    @property
    def gps_verbose_logging(self) -> bool:
        """Enable verbose GPS logging for debugging."""
        value = self._get_toml(self.GPS_SECTION, 'verbose_logging')
        return False if value is None else value

    @gps_verbose_logging.setter
    def gps_verbose_logging(self, value: bool) -> None:
        self._put_toml(self.GPS_SECTION, 'verbose_logging', value)

    # -------------------
    # Alignment Section
    # -------------------

    @property
    def alignment_enabled(self) -> bool:
        """Enable alignment monitoring with plate solving."""
        value = self._get_toml(self.ALIGNMENT_SECTION, 'enabled')
        return False if value is None else value

    @alignment_enabled.setter
    def alignment_enabled(self, value: bool) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'enabled', value)

    @property
    def alignment_camera_address(self) -> str:
        """Alpaca camera server address."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'camera_address') or '127.0.0.1'

    @alignment_camera_address.setter
    def alignment_camera_address(self, value: str) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'camera_address', value)

    @property
    def alignment_camera_port(self) -> int:
        """Alpaca camera server port."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'camera_port') or 11111

    @alignment_camera_port.setter
    def alignment_camera_port(self, value: int) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'camera_port', value)

    @property
    def alignment_camera_device(self) -> int:
        """Alpaca camera device number."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'camera_device') or 0

    @alignment_camera_device.setter
    def alignment_camera_device(self, value: int) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'camera_device', value)

    @property
    def alignment_exposure_time(self) -> float:
        """Exposure time in seconds for alignment captures."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'exposure_time') or 1.0

    @alignment_exposure_time.setter
    def alignment_exposure_time(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'exposure_time', value)

    @property
    def alignment_binning(self) -> int:
        """Camera binning (1, 2, or 4)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'binning') or 2

    @alignment_binning.setter
    def alignment_binning(self, value: int) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'binning', value)

    @property
    def alignment_interval(self) -> float:
        """Interval between alignment measurements in seconds."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'interval') or 30.0

    @alignment_interval.setter
    def alignment_interval(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'interval', value)

    @property
    def alignment_fov_estimate(self) -> float:
        """Estimated camera field of view in degrees."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'fov_estimate') or 1.0

    @alignment_fov_estimate.setter
    def alignment_fov_estimate(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'fov_estimate', value)

    @property
    def alignment_detection_threshold(self) -> float:
        """Star detection threshold in sigma above background."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'detection_threshold') or 5.0

    @alignment_detection_threshold.setter
    def alignment_detection_threshold(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'detection_threshold', value)

    @property
    def alignment_max_stars(self) -> int:
        """Maximum stars to use for plate solving."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'max_stars') or 50

    @alignment_max_stars.setter
    def alignment_max_stars(self, value: int) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'max_stars', value)

    @property
    def alignment_error_threshold(self) -> float:
        """Error threshold in arcseconds for warnings."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'error_threshold') or 60.0

    @alignment_error_threshold.setter
    def alignment_error_threshold(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'error_threshold', value)

    @property
    def alignment_database_path(self) -> str:
        """Path to tetra3 star pattern database."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'database_path') or 'tetra3_database.npz'

    @alignment_database_path.setter
    def alignment_database_path(self, value: str) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'database_path', value)

    @property
    def alignment_verbose_logging(self) -> bool:
        """Enable verbose alignment logging for debugging."""
        value = self._get_toml(self.ALIGNMENT_SECTION, 'verbose_logging')
        return False if value is None else value

    @alignment_verbose_logging.setter
    def alignment_verbose_logging(self, value: bool) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'verbose_logging', value)

    # -------------------
    # V1 Decision Thresholds (arcseconds)
    # -------------------

    @property
    def alignment_error_ignore(self) -> float:
        """Pointing error below which no action is taken (arcseconds)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'error_ignore') or 30.0

    @alignment_error_ignore.setter
    def alignment_error_ignore(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'error_ignore', value)

    @property
    def alignment_error_sync(self) -> float:
        """Pointing error above which sync is performed (arcseconds)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'error_sync') or 120.0

    @alignment_error_sync.setter
    def alignment_error_sync(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'error_sync', value)

    @property
    def alignment_error_concern(self) -> float:
        """Pointing error above which alignment replacement is considered (arcseconds)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'error_concern') or 300.0

    @alignment_error_concern.setter
    def alignment_error_concern(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'error_concern', value)

    @property
    def alignment_error_max(self) -> float:
        """Pointing error above which action is forced and health event logged (arcseconds)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'error_max') or 600.0

    @alignment_error_max.setter
    def alignment_error_max(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'error_max', value)

    # -------------------
    # V1 Geometry Thresholds (determinant, 0-1)
    # -------------------

    @property
    def alignment_det_excellent(self) -> float:
        """Geometry determinant threshold for excellent alignment (protect this)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'det_excellent') or 0.80

    @alignment_det_excellent.setter
    def alignment_det_excellent(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'det_excellent', value)

    @property
    def alignment_det_good(self) -> float:
        """Geometry determinant threshold for good alignment (be selective)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'det_good') or 0.60

    @alignment_det_good.setter
    def alignment_det_good(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'det_good', value)

    @property
    def alignment_det_marginal(self) -> float:
        """Geometry determinant threshold for marginal alignment (seek improvement)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'det_marginal') or 0.40

    @alignment_det_marginal.setter
    def alignment_det_marginal(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'det_marginal', value)

    @property
    def alignment_det_improvement_min(self) -> float:
        """Minimum determinant improvement to justify replacement."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'det_improvement_min') or 0.10

    @alignment_det_improvement_min.setter
    def alignment_det_improvement_min(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'det_improvement_min', value)

    # -------------------
    # V1 Angular Constraints (degrees)
    # -------------------

    @property
    def alignment_min_separation(self) -> float:
        """Minimum angular separation between alignment points (degrees)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'min_separation') or 15.0

    @alignment_min_separation.setter
    def alignment_min_separation(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'min_separation', value)

    @property
    def alignment_refresh_radius(self) -> float:
        """Distance within which refresh logic applies (degrees)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'refresh_radius') or 10.0

    @alignment_refresh_radius.setter
    def alignment_refresh_radius(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'refresh_radius', value)

    @property
    def alignment_scale_radius(self) -> float:
        """Distance falloff for per-point weighted error (degrees)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'scale_radius') or 30.0

    @alignment_scale_radius.setter
    def alignment_scale_radius(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'scale_radius', value)

    @property
    def alignment_refresh_error_threshold(self) -> float:
        """Weighted error threshold for refresh eligibility (arcseconds)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'refresh_error_threshold') or 60.0

    @alignment_refresh_error_threshold.setter
    def alignment_refresh_error_threshold(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'refresh_error_threshold', value)

    # -------------------
    # V1 Lockout Periods (seconds)
    # -------------------

    @property
    def alignment_lockout_post_align(self) -> float:
        """Lockout period after alignment point replacement (seconds)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'lockout_post_align') or 60.0

    @alignment_lockout_post_align.setter
    def alignment_lockout_post_align(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'lockout_post_align', value)

    @property
    def alignment_lockout_post_sync(self) -> float:
        """Lockout period after sync operation (seconds)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'lockout_post_sync') or 10.0

    @alignment_lockout_post_sync.setter
    def alignment_lockout_post_sync(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'lockout_post_sync', value)

    # -------------------
    # V1 Health Monitoring
    # -------------------

    @property
    def alignment_health_window(self) -> float:
        """Health monitoring window duration (seconds)."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'health_window') or 1800.0

    @alignment_health_window.setter
    def alignment_health_window(self, value: float) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'health_window', value)

    @property
    def alignment_health_alert_threshold(self) -> int:
        """Number of high-error events within window to trigger alert."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'health_alert_threshold') or 5

    @alignment_health_alert_threshold.setter
    def alignment_health_alert_threshold(self, value: int) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'health_alert_threshold', value)

    # -------------------
    # Camera Source Selection
    # -------------------

    @property
    def alignment_camera_source(self) -> str:
        """Camera source type: 'alpaca' or 'zwo'."""
        return self._get_toml(self.ALIGNMENT_SECTION, 'camera_source') or 'alpaca'

    @alignment_camera_source.setter
    def alignment_camera_source(self, value: str) -> None:
        self._put_toml(self.ALIGNMENT_SECTION, 'camera_source', value.lower())

    # -------------------
    # ZWO Camera Settings
    # -------------------

    ZWO_SECTION = 'alignment.zwo'

    @property
    def zwo_camera_id(self) -> int:
        """ZWO camera index (0 for first camera)."""
        return self._get_toml(self.ZWO_SECTION, 'camera_id') or 0

    @zwo_camera_id.setter
    def zwo_camera_id(self, value: int) -> None:
        self._put_toml(self.ZWO_SECTION, 'camera_id', value)

    @property
    def zwo_exposure_ms(self) -> int:
        """ZWO camera exposure time in milliseconds."""
        return self._get_toml(self.ZWO_SECTION, 'exposure_ms') or 2000

    @zwo_exposure_ms.setter
    def zwo_exposure_ms(self, value: int) -> None:
        self._put_toml(self.ZWO_SECTION, 'exposure_ms', value)

    @property
    def zwo_gain(self) -> int:
        """ZWO camera gain setting (typically 0-500)."""
        return self._get_toml(self.ZWO_SECTION, 'gain') or 100

    @zwo_gain.setter
    def zwo_gain(self, value: int) -> None:
        self._put_toml(self.ZWO_SECTION, 'gain', value)

    @property
    def zwo_binning(self) -> int:
        """ZWO camera binning (1, 2, or 4)."""
        return self._get_toml(self.ZWO_SECTION, 'binning') or 2

    @zwo_binning.setter
    def zwo_binning(self, value: int) -> None:
        self._put_toml(self.ZWO_SECTION, 'binning', value)

    @property
    def zwo_image_type(self) -> str:
        """ZWO camera image type (RAW8, RAW16, RGB24, Y8)."""
        return self._get_toml(self.ZWO_SECTION, 'image_type') or 'RAW16'

    @zwo_image_type.setter
    def zwo_image_type(self, value: str) -> None:
        self._put_toml(self.ZWO_SECTION, 'image_type', value.upper())

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"{self.__class__.__name__}("
            f"config_file='{self._config_file}', "
            f"override_file='{self._override_file}')"
        )