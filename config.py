# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# config.py - Device configuration file with TOML persistence
# Part of the AlpycaDevice Alpaca skeleton/template device driver
#
# Author:   Robert B. Denny <rdenny@dc3.com> (rbd)
#           Enhanced by: Reid W. Smythe <rwsmythe@gmail.com> (rws)
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
import logging


class ConfigError(Exception):
    """Custom exception for configuration errors"""
    pass


class Config:
    """Device configuration with thread-safe TOML persistence.
    
    For docker-based installations, looks for /alpyca/config.toml
    first, with any settings there overriding ./config.toml.
    
    Attributes:
        ip_address: Network IP address
        port: Network port
        location: Server location description
        verbose_driver_exceptions: Enable verbose driver exception reporting
        log_level: Logging level (integer)
        log_to_stdout: Enable logging to stdout
        max_size_mb: Maximum log file size in MB
        num_keep_logs: Number of log files to keep
    """
    
    # Class constants
    DEFAULT_CONFIG_FILE = 'config.toml'
    OVERRIDE_CONFIG_PATH = '/alpyca/config.toml'
    
    def get_config_dir(self):
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent
        return Path(sys.path[0])

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
            ConfigError: If primary config file cannot be loaded.
        """
        with self._lock:
            # Load primary config file
            try:
                self._dict = toml.load(self._config_file)
            except (FileNotFoundError, toml.TomlDecodeError) as e:
                raise ConfigError(
                    f"Failed to load primary config file {self._config_file}: {e}"
                ) from e
            
            # Load optional override file
            try:
                if self._override_file.exists():
                    self._dict2 = toml.load(self._override_file)
            except toml.TomlDecodeError as e:
                raise ConfigError(
                    f"Failed to load override config file {self._override_file}: {e}"
                ) from e
    
    def _get_toml(self, sect: str, item: str) -> Any:
        """Get configuration value, checking override file first.
        
        Args:
            sect: Configuration section name
            item: Configuration item name
            
        Returns:
            Configuration value or empty string if not found
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
                    return ''
    
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
            ConfigError: If configuration cannot be saved.
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
                raise ConfigError(f"Failed to save configuration: {e}") from e
    
    def reload(self) -> None:
        """Reload configuration from files.
        
        Raises:
            ConfigError: If configuration files cannot be reloaded.
        """
        with self._lock:
            self._dict = {}
            self._dict2 = {}
            self._load_config()
    
    # Configuration section constants
    NETWORK_SECTION = 'network'
    SERVER_SECTION = 'server'
    LOGGING_SECTION = 'logging'
    
    # ---------------
    # Network Section
    # ---------------
    
    @property
    def ip_address(self) -> str:
        """Network IP address configuration."""
        return self._get_toml(self.NETWORK_SECTION, 'ip_address')
    
    @ip_address.setter
    def ip_address(self, value: str) -> None:
        self._put_toml(self.NETWORK_SECTION, 'ip_address', value)
    
    @property
    def port(self) -> int:
        """Network port configuration."""
        return self._get_toml(self.NETWORK_SECTION, 'port')
    
    @port.setter
    def port(self, value: int) -> None:
        self._put_toml(self.NETWORK_SECTION, 'port', value)
    
    # --------------
    # Server Section
    # --------------
    
    @property
    def location(self) -> str:
        """Server location description."""
        return self._get_toml(self.SERVER_SECTION, 'location')
    
    @location.setter
    def location(self, value: str) -> None:
        self._put_toml(self.SERVER_SECTION, 'location', value)
    
    @property
    def verbose_driver_exceptions(self) -> bool:
        """Enable verbose driver exception reporting."""
        return self._get_toml(self.SERVER_SECTION, 'verbose_driver_exceptions')
    
    @verbose_driver_exceptions.setter
    def verbose_driver_exceptions(self, value: bool) -> None:
        self._put_toml(self.SERVER_SECTION, 'verbose_driver_exceptions', value)
    
    @property
    def setup_port(self) -> int:
        """Network port configuration."""
        return self._get_toml(self.SERVER_SECTION, 'setup_port')
    
    @setup_port.setter
    def setup_port(self, value: int) -> None:
        self._put_toml(self.SERVER_SECTION, 'setup_port', value)
    
    # ---------------
    # Logging Section
    # ---------------
    
    @property
    def log_level(self) -> int:
        """Logging level as integer."""
        return logging.getLevelName(self._get_toml(self.LOGGING_SECTION, 'log_level'))
    
    @log_level.setter
    def log_level(self, value: str) -> None:
        """Set log level using string value."""
        self._put_toml(self.LOGGING_SECTION, 'log_level', value)
    
    @property
    def log_to_stdout(self) -> bool:
        """Enable logging to stdout."""
        return self._get_toml(self.LOGGING_SECTION, 'log_to_stdout')
    
    @log_to_stdout.setter
    def log_to_stdout(self, value: bool) -> None:
        self._put_toml(self.LOGGING_SECTION, 'log_to_stdout', value)
    
    @property
    def max_size_mb(self) -> int:
        """Maximum log file size in MB."""
        return self._get_toml(self.LOGGING_SECTION, 'max_size_mb')
    
    @max_size_mb.setter
    def max_size_mb(self, value: int) -> None:
        self._put_toml(self.LOGGING_SECTION, 'max_size_mb', value)
    
    @property
    def num_keep_logs(self) -> int:
        """Number of log files to keep."""
        return self._get_toml(self.LOGGING_SECTION, 'num_keep_logs')
    
    @num_keep_logs.setter
    def num_keep_logs(self, value: int) -> None:
        self._put_toml(self.LOGGING_SECTION, 'num_keep_logs', value)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"{self.__class__.__name__}("
            f"config_file='{self._config_file}', "
            f"override_file='{self._override_file}')"
        )