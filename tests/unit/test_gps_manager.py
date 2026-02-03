# -*- coding: utf-8 -*-
"""
Unit tests for the GPS Manager module.

Tests NMEA parsing, state management, and GPS operations
without requiring actual GPS hardware.
"""

import pytest
import time
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from gps_manager import (
    GPSManager,
    GPSState,
    GPSFixQuality,
    GPSPosition,
    GPSDateTime,
    GPSStatus,
)


@pytest.fixture
def mock_gps_config():
    """Create mock GPS configuration."""
    config = Mock()
    config.gps_enabled = True
    config.gps_port = 'COM10'
    config.gps_baudrate = 9600
    config.gps_min_fix_quality = 1
    config.gps_min_satellites = 4
    config.gps_push_on_connect = True
    config.gps_location_name = 'GPS'
    config.gps_read_timeout = 2.0
    config.gps_verbose_logging = False
    return config


@pytest.fixture
def gps_manager(mock_gps_config, mock_logger):
    """Create GPSManager instance with mocked dependencies."""
    manager = GPSManager(mock_gps_config, mock_logger)
    return manager


class TestGPSManagerInitialization:
    """Test GPS manager initialization."""

    @pytest.mark.unit
    def test_manager_initializes_with_config(self, mock_gps_config, mock_logger):
        """GPS manager should initialize with provided config."""
        manager = GPSManager(mock_gps_config, mock_logger)
        assert manager._config == mock_gps_config
        assert manager._logger == mock_logger

    @pytest.mark.unit
    def test_manager_starts_in_disconnected_state(self, gps_manager):
        """GPS manager should start in DISCONNECTED state."""
        assert gps_manager._state == GPSState.DISCONNECTED

    @pytest.mark.unit
    def test_manager_has_thread_lock(self, gps_manager):
        """GPS manager should have a threading lock."""
        assert gps_manager._lock is not None

    @pytest.mark.unit
    def test_manager_initializes_position_object(self, gps_manager):
        """GPS manager should start with a GPSPosition object."""
        assert gps_manager._position is not None
        assert isinstance(gps_manager._position, GPSPosition)


class TestGPSPosition:
    """Test GPSPosition dataclass."""

    @pytest.mark.unit
    def test_position_default_values(self):
        """GPSPosition should have sensible defaults."""
        pos = GPSPosition()
        assert pos.latitude == 0.0
        assert pos.longitude == 0.0
        assert pos.altitude == 0.0
        assert pos.fix_quality == GPSFixQuality.INVALID
        assert pos.satellites == 0
        assert pos.hdop == 99.9
        assert pos.valid is False

    @pytest.mark.unit
    def test_position_custom_values(self):
        """GPSPosition should accept custom values."""
        pos = GPSPosition(
            latitude=21.347,
            longitude=-157.903,
            altitude=100.0,
            fix_quality=GPSFixQuality.GPS_FIX,
            satellites=10,
            hdop=1.2,
            valid=True
        )
        assert pos.latitude == 21.347
        assert pos.longitude == -157.903
        assert pos.altitude == 100.0
        assert pos.fix_quality == GPSFixQuality.GPS_FIX
        assert pos.satellites == 10


class TestFixQuality:
    """Test GPS fix quality enumeration."""

    @pytest.mark.unit
    def test_fix_quality_values(self):
        """Fix quality enum should have correct values."""
        assert GPSFixQuality.INVALID.value == 0
        assert GPSFixQuality.GPS_FIX.value == 1
        assert GPSFixQuality.DGPS_FIX.value == 2
        assert GPSFixQuality.RTK_FIX.value == 4
        assert GPSFixQuality.RTK_FLOAT.value == 5

    @pytest.mark.unit
    def test_fix_quality_from_int(self):
        """Should create fix quality from integer."""
        assert GPSFixQuality(0) == GPSFixQuality.INVALID
        assert GPSFixQuality(1) == GPSFixQuality.GPS_FIX
        assert GPSFixQuality(2) == GPSFixQuality.DGPS_FIX


class TestFixValidity:
    """Test fix validity determination."""

    @pytest.mark.unit
    def test_has_valid_fix_with_good_quality(self, gps_manager):
        """Should report valid fix when quality and satellites meet threshold."""
        gps_manager._position = GPSPosition(
            latitude=21.3,
            longitude=-157.9,
            fix_quality=GPSFixQuality.GPS_FIX,
            satellites=8,
            valid=True
        )
        gps_manager._last_valid_sentence = time.time()

        assert gps_manager.has_valid_fix() is True

    @pytest.mark.unit
    def test_has_valid_fix_insufficient_quality(self, gps_manager):
        """Should report invalid fix when quality is too low."""
        gps_manager._position = GPSPosition(
            latitude=21.3,
            longitude=-157.9,
            fix_quality=GPSFixQuality.INVALID,
            satellites=8,
            valid=False
        )

        assert gps_manager.has_valid_fix() is False

    @pytest.mark.unit
    def test_has_valid_fix_insufficient_satellites(self, gps_manager):
        """Should report invalid fix when satellites are too few."""
        gps_manager._position = GPSPosition(
            latitude=21.3,
            longitude=-157.9,
            fix_quality=GPSFixQuality.GPS_FIX,
            satellites=2,  # Below default threshold of 4
            valid=False
        )

        assert gps_manager.has_valid_fix() is False


class TestGPSStatus:
    """Test GPS status reporting."""

    @pytest.mark.unit
    def test_get_status_returns_status_object(self, gps_manager):
        """get_status should return a GPSStatus object."""
        status = gps_manager.get_status()
        assert isinstance(status, GPSStatus)

    @pytest.mark.unit
    def test_get_status_reflects_state(self, gps_manager):
        """Status should reflect current GPS state."""
        gps_manager._state = GPSState.FIX_VALID
        gps_manager._connected = True
        gps_manager._position = GPSPosition(
            latitude=21.347,
            longitude=-157.903,
            fix_quality=GPSFixQuality.GPS_FIX,
            satellites=10,
            valid=True
        )

        status = gps_manager.get_status()

        assert status.state == GPSState.FIX_VALID
        assert status.connected is True
        assert status.position.fix_quality == GPSFixQuality.GPS_FIX
        assert status.position.satellites == 10

    @pytest.mark.unit
    def test_get_position_returns_position(self, gps_manager):
        """get_position should return position data."""
        gps_manager._position = GPSPosition(
            latitude=21.347,
            longitude=-157.903,
            altitude=100.0
        )

        pos = gps_manager.get_position()

        assert pos is not None
        assert abs(pos.latitude - 21.347) < 0.001
        assert abs(pos.longitude - (-157.903)) < 0.001


class TestPushCallback:
    """Test location push callback functionality."""

    @pytest.mark.unit
    def test_set_push_callback(self, gps_manager):
        """Should accept and store push callback."""
        callback = Mock()
        gps_manager.set_push_callback(callback)
        assert gps_manager._push_callback == callback

    @pytest.mark.unit
    def test_push_location_calls_callback(self, gps_manager):
        """Should call push callback with coordinates."""
        callback = Mock(return_value=True)
        gps_manager.set_push_callback(callback)
        gps_manager._position = GPSPosition(
            latitude=21.347,
            longitude=-157.903,
            fix_quality=GPSFixQuality.GPS_FIX,
            satellites=8,
            valid=True
        )

        result = gps_manager._push_location_to_mount()

        callback.assert_called_once()
        # Verify coordinates were passed
        call_args = callback.call_args
        assert abs(call_args[0][0] - 21.347) < 0.001  # latitude
        assert abs(call_args[0][1] - (-157.903)) < 0.001  # longitude

    @pytest.mark.unit
    def test_push_location_no_callback(self, gps_manager):
        """Should handle missing callback gracefully."""
        gps_manager._push_callback = None
        gps_manager._position = GPSPosition(
            latitude=21.347,
            longitude=-157.903,
            valid=True
        )

        result = gps_manager._push_location_to_mount()

        assert result is False

    @pytest.mark.unit
    def test_push_location_invalid_position(self, gps_manager):
        """Should not push when position is not valid."""
        callback = Mock(return_value=True)
        gps_manager.set_push_callback(callback)
        gps_manager._position = GPSPosition(valid=False)

        result = gps_manager._push_location_to_mount()

        callback.assert_not_called()
        assert result is False


class TestGPSState:
    """Test GPS state enumeration."""

    @pytest.mark.unit
    def test_state_values(self):
        """GPS state enum should have expected values."""
        assert GPSState.DISABLED is not None
        assert GPSState.DISCONNECTED is not None
        assert GPSState.CONNECTING is not None
        assert GPSState.CONNECTED is not None
        assert GPSState.ACQUIRING_FIX is not None
        assert GPSState.FIX_VALID is not None
        assert GPSState.ERROR is not None


class TestGPSLifecycle:
    """Test GPS manager start/stop lifecycle."""

    @pytest.mark.unit
    def test_start_without_port_fails(self, gps_manager, mock_gps_config):
        """Start should fail gracefully when port not configured."""
        mock_gps_config.gps_port = ''

        with patch('serial.Serial', side_effect=Exception("No port")):
            result = gps_manager.start()
            assert result is False

    @pytest.mark.unit
    def test_stop_when_not_started(self, gps_manager):
        """Stop should handle not-started state gracefully."""
        # Should not raise
        gps_manager.stop()
        assert gps_manager._state == GPSState.DISCONNECTED

    @pytest.mark.unit
    def test_stop_sets_stop_event(self, gps_manager):
        """Stop should set the stop event."""
        gps_manager._stop_event.clear()
        gps_manager.stop()
        assert gps_manager._stop_event.is_set()


class TestGPSDateTime:
    """Test GPSDateTime dataclass."""

    @pytest.mark.unit
    def test_datetime_default_values(self):
        """GPSDateTime should have sensible defaults."""
        dt = GPSDateTime()
        assert dt.utc_datetime is None
        assert dt.valid is False

    @pytest.mark.unit
    def test_datetime_custom_values(self):
        """GPSDateTime should accept custom values."""
        now = datetime.now(timezone.utc)
        dt = GPSDateTime(utc_datetime=now, valid=True)
        assert dt.utc_datetime == now
        assert dt.valid is True


class TestGPSStatusDataclass:
    """Test GPSStatus dataclass."""

    @pytest.mark.unit
    def test_status_default_values(self):
        """GPSStatus should have sensible defaults."""
        status = GPSStatus()
        assert status.state == GPSState.DISABLED
        assert status.connected is False
        assert status.push_count == 0
        assert status.error_message == ""

    @pytest.mark.unit
    def test_status_with_position(self):
        """GPSStatus should contain position information."""
        pos = GPSPosition(
            latitude=21.347,
            longitude=-157.903,
            fix_quality=GPSFixQuality.GPS_FIX,
            satellites=10,
            valid=True
        )
        status = GPSStatus(
            state=GPSState.FIX_VALID,
            position=pos,
            connected=True
        )

        assert status.state == GPSState.FIX_VALID
        assert status.position.latitude == 21.347
        assert status.position.satellites == 10


class TestNMEAParsing:
    """Test NMEA sentence processing."""

    @pytest.mark.unit
    def test_parse_gga_updates_position(self, gps_manager):
        """_parse_gga should update position from GGA message."""
        # Create mock pynmea2 GGA message
        mock_msg = Mock()
        mock_msg.latitude = 21.347
        mock_msg.longitude = -157.903
        mock_msg.altitude = 100.0
        mock_msg.gps_qual = '1'
        mock_msg.num_sats = '08'
        mock_msg.horizontal_dil = '1.2'

        gps_manager._parse_gga(mock_msg)

        assert abs(gps_manager._position.latitude - 21.347) < 0.001
        assert abs(gps_manager._position.longitude - (-157.903)) < 0.001
        assert gps_manager._position.fix_quality == GPSFixQuality.GPS_FIX
        assert gps_manager._position.satellites == 8

    @pytest.mark.unit
    def test_parse_gga_handles_no_fix(self, gps_manager):
        """_parse_gga should handle no-fix GGA message."""
        mock_msg = Mock()
        mock_msg.latitude = None
        mock_msg.longitude = None
        mock_msg.altitude = None
        mock_msg.gps_qual = '0'
        mock_msg.num_sats = '00'
        mock_msg.horizontal_dil = '99.9'

        # Should not raise
        gps_manager._parse_gga(mock_msg)

        assert gps_manager._position.fix_quality == GPSFixQuality.INVALID

    @pytest.mark.unit
    def test_parse_rmc_updates_datetime(self, gps_manager):
        """_parse_rmc should update datetime from RMC message."""
        test_datetime = datetime(2026, 2, 2, 12, 30, 45)
        mock_msg = Mock()
        mock_msg.datetime = test_datetime
        mock_msg.status = 'A'

        gps_manager._parse_rmc(mock_msg)

        assert gps_manager._datetime_info.utc_datetime is not None
        assert gps_manager._datetime_info.utc_datetime.year == 2026


class TestStateTransitions:
    """Test GPS state transitions."""

    @pytest.mark.unit
    def test_update_state_changes_state(self, gps_manager):
        """_update_state should change the current state."""
        gps_manager._state = GPSState.DISCONNECTED
        gps_manager._update_state(GPSState.CONNECTING)
        assert gps_manager._state == GPSState.CONNECTING

    @pytest.mark.unit
    def test_update_state_logs_transition(self, gps_manager, mock_logger):
        """_update_state should log state transitions."""
        gps_manager._state = GPSState.DISCONNECTED
        gps_manager._update_state(GPSState.CONNECTED)
        # Verify logging was called
        mock_logger.info.assert_called()
