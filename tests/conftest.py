"""
Shared pytest fixtures for TTS160 Alpaca Driver tests.

This module provides common fixtures used across unit and integration tests,
including mock loggers, serial ports, and device instances.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import threading
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_logger():
    """Create a mock logger for testing.

    Returns:
        Mock logger with standard logging methods.
    """
    logger = Mock()
    logger.debug = Mock()
    logger.info = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    logger.critical = Mock()
    return logger


@pytest.fixture
def mock_serial_port():
    """Mock serial port for testing without hardware.

    Yields:
        MagicMock serial port instance.
    """
    with patch('serial.Serial') as mock:
        instance = MagicMock()
        instance.is_open = True
        instance.in_waiting = 0
        instance.timeout = 0.5
        instance.read = Mock(return_value=b'')
        instance.write = Mock(return_value=0)
        instance.read_until = Mock(return_value=b'')
        instance.reset_input_buffer = Mock()
        instance.reset_output_buffer = Mock()
        instance.flush = Mock()
        instance.close = Mock()
        mock.return_value = instance
        yield instance


@pytest.fixture
def mock_config():
    """Create mock configuration object.

    Returns:
        Mock config with standard properties.
    """
    config = Mock()
    config.ip_address = ''
    config.port = 5555
    config.threads = 4
    config.location = 'Test Location'
    config.verbose_driver_exceptions = True
    config.setup_port = 8080
    config.log_level = 10  # DEBUG
    config.log_to_stdout = False
    config.max_size_mb = 5
    config.num_keep_logs = 10
    return config


@pytest.fixture
def mock_telescope_config():
    """Create mock telescope configuration object.

    Returns:
        Mock telescope config with site parameters.
    """
    config = Mock()
    config.dev_port = 'COM1'
    config.site_latitude = 21.3
    config.site_longitude = -157.9
    config.site_elevation = 0.0
    config.sync_time = True
    config.pulse_guide_enabled = True
    return config


@pytest.fixture
def sample_binary_data():
    """Provide sample binary data for testing parsers.

    Returns:
        Dictionary of test binary data samples.
    """
    import struct
    return {
        # Case 2 format: 5i2f (28 bytes)
        'case2': struct.pack('<5i2f', 100, 200, 50, 50, 1, 180.0, 45.0),
        # Three integers
        'integers': struct.pack('<3i', 1, 2, 3),
        # Two floats
        'floats': struct.pack('<2f', 1.5, 2.5),
        # Mixed: 2 ints + 1 float
        'mixed': struct.pack('<2if', 10, 20, 3.14159),
    }


@pytest.fixture
def cache_test_properties():
    """Provide standard test property values for cache testing.

    Returns:
        Dictionary of property name to test value mappings.
    """
    return {
        'RightAscension': 12.5,
        'Declination': 45.0,
        'Altitude': 60.0,
        'Azimuth': 180.0,
        'Tracking': True,
        'Slewing': False,
        'AtPark': False,
        'AtHome': False,
        'SideOfPier': 0,
        'SiderealTime': 18.5,
        'IsPulseGuiding': False,
    }


# Integration test fixtures

@pytest.fixture
def mock_serial_manager(mock_logger, mock_serial_port):
    """Create SerialManager with mocked serial port.

    Args:
        mock_logger: Mock logger fixture
        mock_serial_port: Mock serial port fixture

    Returns:
        SerialManager instance with mocked serial.
    """
    from tts160_serial import SerialManager
    manager = SerialManager(mock_logger)
    manager._serial = mock_serial_port
    manager._serial.is_open = True
    return manager


@pytest.fixture
def isolated_cache(mock_logger):
    """Create an isolated TTS160Cache instance for testing.

    Does not connect to global singletons.

    Args:
        mock_logger: Mock logger fixture

    Returns:
        TTS160Cache instance.
    """
    from tts160_cache import TTS160Cache
    cache = TTS160Cache(mock_logger)
    return cache


# Utility fixtures

@pytest.fixture
def temp_toml_file(tmp_path):
    """Create a temporary TOML config file for testing.

    Args:
        tmp_path: pytest tmp_path fixture

    Returns:
        Path to temporary config file.
    """
    config_content = """
title = "Test Config"

[network]
ip_address = ''
port = 5555
threads = 4

[server]
location = 'Test Location'
verbose_driver_exceptions = true
setup_port = 8080

[logging]
log_level = 'DEBUG'
log_to_stdout = false
max_size_mb = 5
num_keep_logs = 10
"""
    config_file = tmp_path / "test_config.toml"
    config_file.write_text(config_content)
    return config_file
