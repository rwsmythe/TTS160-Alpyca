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
    """
    
    # Class constants
    DEFAULT_CONFIG_FILE = 'TTS160config.toml'
    OVERRIDE_CONFIG_PATH = '/alpyca/TTS160config.toml'
    
    def __init__(self):
        """Initialize configuration by loading TOML files."""
        self._lock = threading.RLock()
        self._dict = {}
        self._dict2 = {}
        
        # Use pathlib for file paths
        self._config_file = Path.cwd() / self.DEFAULT_CONFIG_FILE
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
    
    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"{self.__class__.__name__}("
            f"config_file='{self._config_file}', "
            f"override_file='{self._override_file}')"
        )
    
    #-----------------
    # Driver Section
    #-----------------

    @property
    def sync_time_on_connect(self) -> bool:
        """Synch mount time with computer on connect."""
        return self._get_toml(self.DRIVER_SECTION, 'sync_time_on_connect') or True
    
    @sync_time_on_connect.setter
    def sync_time_on_connect(self, value: bool) -> None:
        self._put_toml(self.DRIVER_SECTION, 'sync_time_on_connect', value)