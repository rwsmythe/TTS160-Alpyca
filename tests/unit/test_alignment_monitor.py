# -*- coding: utf-8 -*-
"""
Unit tests for the Alignment Monitor module.

Tests state management, measurement calculations, and alignment operations
without requiring actual camera hardware or plate solving databases.
"""

import pytest
import time
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
import numpy as np

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from alignment_monitor import (
    AlignmentMonitor,
    AlignmentState,
    AlignmentPoint,
    AlignmentStatus,
)


@pytest.fixture
def mock_alignment_config():
    """Create mock alignment configuration."""
    config = Mock()
    config.alignment_enabled = True
    config.alignment_camera_address = '127.0.0.1'
    config.alignment_camera_port = 11111
    config.alignment_camera_device = 0
    config.alignment_exposure_time = 1.0
    config.alignment_binning = 2
    config.alignment_interval = 30.0
    config.alignment_fov_estimate = 1.0
    config.alignment_detection_threshold = 5.0
    config.alignment_max_stars = 50
    config.alignment_error_threshold = 60.0
    config.alignment_database_path = 'tetra3_database.npz'
    config.alignment_verbose_logging = False
    return config


@pytest.fixture
def alignment_monitor(mock_alignment_config, mock_logger):
    """Create AlignmentMonitor instance with mocked dependencies."""
    monitor = AlignmentMonitor(mock_alignment_config, mock_logger)
    return monitor


class TestAlignmentMonitorInitialization:
    """Test alignment monitor initialization."""

    @pytest.mark.unit
    def test_monitor_initializes_with_config(self, mock_alignment_config, mock_logger):
        """Alignment monitor should initialize with provided config."""
        monitor = AlignmentMonitor(mock_alignment_config, mock_logger)
        assert monitor._config == mock_alignment_config
        assert monitor._logger == mock_logger

    @pytest.mark.unit
    def test_monitor_starts_in_disabled_state(self, alignment_monitor):
        """Alignment monitor should start in DISABLED state."""
        assert alignment_monitor._state == AlignmentState.DISABLED

    @pytest.mark.unit
    def test_monitor_has_thread_lock(self, alignment_monitor):
        """Alignment monitor should have a threading lock."""
        assert alignment_monitor._lock is not None

    @pytest.mark.unit
    def test_monitor_initializes_empty_history(self, alignment_monitor):
        """Alignment monitor should start with empty history."""
        assert alignment_monitor._history == []
        assert alignment_monitor._measurement_count == 0


class TestAlignmentPoint:
    """Test AlignmentPoint dataclass."""

    @pytest.mark.unit
    def test_point_creation(self):
        """AlignmentPoint should be created with required fields."""
        point = AlignmentPoint(
            timestamp=datetime.now(),
            mount_ra=12.5,
            mount_dec=45.0,
            solved_ra=12.501,
            solved_dec=45.002,
            ra_error=5.4,
            dec_error=7.2,
            total_error=9.0,
            solve_time_ms=15.5,
            stars_detected=25,
            confidence=0.95
        )
        assert point.mount_ra == 12.5
        assert point.mount_dec == 45.0
        assert point.total_error == 9.0
        assert point.stars_detected == 25

    @pytest.mark.unit
    def test_point_error_values(self):
        """AlignmentPoint should store error values correctly."""
        point = AlignmentPoint(
            timestamp=datetime.now(),
            mount_ra=6.0,
            mount_dec=30.0,
            solved_ra=6.0001,
            solved_dec=30.0005,
            ra_error=1.5,
            dec_error=1.8,
            total_error=2.3,
            solve_time_ms=12.0,
            stars_detected=30,
            confidence=0.99
        )
        assert point.ra_error == 1.5
        assert point.dec_error == 1.8
        assert abs(point.total_error - 2.3) < 0.01


class TestAlignmentStatus:
    """Test AlignmentStatus dataclass."""

    @pytest.mark.unit
    def test_status_default_values(self):
        """AlignmentStatus should have sensible defaults."""
        status = AlignmentStatus(
            state=AlignmentState.DISABLED,
            camera_connected=False,
            camera_name='',
            last_solve_time=None,
            last_ra_error=0.0,
            last_dec_error=0.0,
            last_total_error=0.0,
            average_error=0.0,
            max_error=0.0,
            measurement_count=0,
            stars_detected=0,
            solve_confidence=0.0,
            error_message=''
        )
        assert status.state == AlignmentState.DISABLED
        assert status.camera_connected is False
        assert status.measurement_count == 0

    @pytest.mark.unit
    def test_status_with_history(self):
        """AlignmentStatus should contain history list."""
        point = AlignmentPoint(
            timestamp=datetime.now(),
            mount_ra=12.0,
            mount_dec=45.0,
            solved_ra=12.001,
            solved_dec=45.002,
            ra_error=5.0,
            dec_error=7.0,
            total_error=8.6,
            solve_time_ms=10.0,
            stars_detected=20,
            confidence=0.9
        )
        status = AlignmentStatus(
            state=AlignmentState.MONITORING,
            camera_connected=True,
            camera_name='Test Camera',
            last_solve_time=datetime.now(),
            last_ra_error=5.0,
            last_dec_error=7.0,
            last_total_error=8.6,
            average_error=8.0,
            max_error=10.0,
            measurement_count=5,
            stars_detected=20,
            solve_confidence=0.9,
            error_message='',
            history=[point]
        )
        assert len(status.history) == 1
        assert status.history[0].total_error == 8.6


class TestAlignmentState:
    """Test AlignmentState enumeration."""

    @pytest.mark.unit
    def test_state_values(self):
        """Alignment state enum should have expected values."""
        assert AlignmentState.DISABLED is not None
        assert AlignmentState.DISCONNECTED is not None
        assert AlignmentState.CONNECTING is not None
        assert AlignmentState.CONNECTED is not None
        assert AlignmentState.CAPTURING is not None
        assert AlignmentState.SOLVING is not None
        assert AlignmentState.MONITORING is not None
        assert AlignmentState.ERROR is not None

    @pytest.mark.unit
    def test_state_ordering(self):
        """States should have numeric ordering."""
        assert AlignmentState.DISABLED.value < AlignmentState.DISCONNECTED.value
        assert AlignmentState.CONNECTED.value < AlignmentState.CAPTURING.value


class TestGetStatus:
    """Test status reporting."""

    @pytest.mark.unit
    def test_get_status_returns_status_object(self, alignment_monitor):
        """get_status should return an AlignmentStatus object."""
        status = alignment_monitor.get_status()
        assert isinstance(status, AlignmentStatus)

    @pytest.mark.unit
    def test_get_status_reflects_state(self, alignment_monitor):
        """Status should reflect current alignment state."""
        alignment_monitor._state = AlignmentState.MONITORING
        alignment_monitor._measurement_count = 10
        alignment_monitor._average_error = 5.5

        status = alignment_monitor.get_status()

        assert status.state == AlignmentState.MONITORING
        assert status.measurement_count == 10
        assert status.average_error == 5.5


class TestMountPositionCallback:
    """Test mount position callback functionality."""

    @pytest.mark.unit
    def test_set_mount_position_callback(self, alignment_monitor):
        """Should accept and store mount position callback."""
        callback = Mock(return_value=(12.5, 45.0))
        alignment_monitor.set_mount_position_callback(callback)
        assert alignment_monitor._mount_position_callback == callback

    @pytest.mark.unit
    def test_callback_returns_tuple(self, alignment_monitor):
        """Callback should return (ra, dec) tuple."""
        callback = Mock(return_value=(18.5, -30.0))
        alignment_monitor.set_mount_position_callback(callback)

        ra, dec = alignment_monitor._mount_position_callback()

        assert ra == 18.5
        assert dec == -30.0


class TestErrorCalculation:
    """Test pointing error calculation."""

    @pytest.mark.unit
    def test_calculate_error_small_difference(self, alignment_monitor):
        """Should calculate error for small coordinate differences."""
        # Small difference at moderate declination
        ra_error, dec_error, total_error = alignment_monitor._calculate_error(
            mount_ra=12.0,
            mount_dec=45.0,
            solved_ra=12.0001,  # ~0.36" at dec=45
            solved_dec=45.0005  # 1.8"
        )

        # Dec error should be about 1.8"
        assert abs(dec_error - 1.8) < 0.1
        # Total error should be computed
        assert total_error > 0

    @pytest.mark.unit
    def test_calculate_error_at_pole(self, alignment_monitor):
        """Should handle calculations near celestial pole."""
        # Near pole, RA errors are compressed
        ra_error, dec_error, total_error = alignment_monitor._calculate_error(
            mount_ra=0.0,
            mount_dec=89.0,
            solved_ra=0.001,
            solved_dec=89.001
        )

        # Dec error dominates near pole
        assert dec_error > 0
        assert total_error > 0

    @pytest.mark.unit
    def test_calculate_error_ra_wraparound(self, alignment_monitor):
        """Should handle RA wraparound at 24h."""
        # RA near 24h/0h boundary
        ra_error, dec_error, total_error = alignment_monitor._calculate_error(
            mount_ra=23.999,
            mount_dec=0.0,
            solved_ra=0.001,  # Wrapped around
            solved_dec=0.0
        )

        # Should compute small error, not 24h difference
        # 0.002h = 7.2s = 108" at equator
        assert abs(ra_error) < 200  # Should be ~108" not huge

    @pytest.mark.unit
    def test_calculate_error_zero_at_match(self, alignment_monitor):
        """Should return zero error when positions match."""
        ra_error, dec_error, total_error = alignment_monitor._calculate_error(
            mount_ra=6.0,
            mount_dec=30.0,
            solved_ra=6.0,
            solved_dec=30.0
        )

        assert ra_error == 0.0
        assert dec_error == 0.0
        assert total_error == 0.0


class TestStatistics:
    """Test statistics calculation."""

    @pytest.mark.unit
    def test_update_statistics_empty_history(self, alignment_monitor):
        """Should handle empty history."""
        alignment_monitor._history = []
        alignment_monitor._update_statistics()

        assert alignment_monitor._average_error == 0.0
        assert alignment_monitor._max_error == 0.0

    @pytest.mark.unit
    def test_update_statistics_single_point(self, alignment_monitor):
        """Should compute statistics for single measurement."""
        point = AlignmentPoint(
            timestamp=datetime.now(),
            mount_ra=12.0,
            mount_dec=45.0,
            solved_ra=12.001,
            solved_dec=45.001,
            ra_error=5.0,
            dec_error=3.6,
            total_error=6.2,
            solve_time_ms=10.0,
            stars_detected=20,
            confidence=0.9
        )
        alignment_monitor._history = [point]
        alignment_monitor._update_statistics()

        assert alignment_monitor._average_error == 6.2
        assert alignment_monitor._max_error == 6.2

    @pytest.mark.unit
    def test_update_statistics_multiple_points(self, alignment_monitor):
        """Should compute statistics for multiple measurements."""
        now = datetime.now()
        points = [
            AlignmentPoint(timestamp=now, mount_ra=12.0, mount_dec=45.0,
                          solved_ra=12.0, solved_dec=45.0, ra_error=0, dec_error=0,
                          total_error=5.0, solve_time_ms=10, stars_detected=20, confidence=0.9),
            AlignmentPoint(timestamp=now, mount_ra=12.0, mount_dec=45.0,
                          solved_ra=12.0, solved_dec=45.0, ra_error=0, dec_error=0,
                          total_error=10.0, solve_time_ms=10, stars_detected=20, confidence=0.9),
            AlignmentPoint(timestamp=now, mount_ra=12.0, mount_dec=45.0,
                          solved_ra=12.0, solved_dec=45.0, ra_error=0, dec_error=0,
                          total_error=15.0, solve_time_ms=10, stars_detected=20, confidence=0.9),
        ]
        alignment_monitor._history = points
        alignment_monitor._update_statistics()

        assert alignment_monitor._average_error == 10.0  # (5+10+15)/3
        assert alignment_monitor._max_error == 15.0


class TestHistoryManagement:
    """Test measurement history management."""

    @pytest.mark.unit
    def test_get_history_empty(self, alignment_monitor):
        """Should return empty list when no history."""
        history = alignment_monitor.get_history()
        assert history == []

    @pytest.mark.unit
    def test_get_history_returns_copy(self, alignment_monitor):
        """Should return copy of history, not reference."""
        now = datetime.now()
        point = AlignmentPoint(
            timestamp=now, mount_ra=12.0, mount_dec=45.0,
            solved_ra=12.0, solved_dec=45.0, ra_error=0, dec_error=0,
            total_error=5.0, solve_time_ms=10, stars_detected=20, confidence=0.9
        )
        alignment_monitor._history = [point]

        history = alignment_monitor.get_history()
        history.append(point)  # Modify returned list

        # Original should be unchanged
        assert len(alignment_monitor._history) == 1

    @pytest.mark.unit
    def test_get_history_with_limit(self, alignment_monitor):
        """Should respect limit parameter."""
        now = datetime.now()
        points = [
            AlignmentPoint(timestamp=now, mount_ra=12.0, mount_dec=45.0,
                          solved_ra=12.0, solved_dec=45.0, ra_error=0, dec_error=0,
                          total_error=i, solve_time_ms=10, stars_detected=20, confidence=0.9)
            for i in range(10)
        ]
        alignment_monitor._history = points

        history = alignment_monitor.get_history(limit=5)

        assert len(history) == 5
        # Should return most recent 5
        assert history[-1].total_error == 9

    @pytest.mark.unit
    def test_clear_history(self, alignment_monitor):
        """clear_history should reset all tracking."""
        now = datetime.now()
        point = AlignmentPoint(
            timestamp=now, mount_ra=12.0, mount_dec=45.0,
            solved_ra=12.0, solved_dec=45.0, ra_error=5.0, dec_error=3.0,
            total_error=5.8, solve_time_ms=10, stars_detected=20, confidence=0.9
        )
        alignment_monitor._history = [point]
        alignment_monitor._last_measurement = point
        alignment_monitor._measurement_count = 5
        alignment_monitor._average_error = 5.8
        alignment_monitor._max_error = 10.0

        alignment_monitor.clear_history()

        assert alignment_monitor._history == []
        assert alignment_monitor._last_measurement is None
        assert alignment_monitor._measurement_count == 0
        assert alignment_monitor._average_error == 0.0
        assert alignment_monitor._max_error == 0.0


class TestStateTransitions:
    """Test alignment state transitions."""

    @pytest.mark.unit
    def test_update_state_changes_state(self, alignment_monitor):
        """_update_state should change the current state."""
        alignment_monitor._state = AlignmentState.DISABLED
        alignment_monitor._update_state(AlignmentState.DISCONNECTED)
        assert alignment_monitor._state == AlignmentState.DISCONNECTED

    @pytest.mark.unit
    def test_update_state_logs_transition(self, alignment_monitor, mock_logger):
        """_update_state should log state transitions."""
        alignment_monitor._state = AlignmentState.DISCONNECTED
        alignment_monitor._update_state(AlignmentState.CONNECTED)
        # Verify logging was called
        mock_logger.debug.assert_called()

    @pytest.mark.unit
    def test_update_state_no_log_if_same(self, alignment_monitor, mock_logger):
        """_update_state should not log if state unchanged."""
        alignment_monitor._state = AlignmentState.MONITORING
        mock_logger.debug.reset_mock()

        alignment_monitor._update_state(AlignmentState.MONITORING)

        # No debug call for same state
        assert not any(
            'state' in str(call).lower()
            for call in mock_logger.debug.call_args_list
        )


class TestStartStop:
    """Test alignment monitor start/stop lifecycle."""

    @pytest.mark.unit
    def test_start_when_disabled_in_config(self, alignment_monitor, mock_alignment_config):
        """Start should return False when disabled in config."""
        mock_alignment_config.alignment_enabled = False

        result = alignment_monitor.start()

        assert result is False
        assert alignment_monitor._state == AlignmentState.DISABLED

    @pytest.mark.unit
    def test_stop_when_not_started(self, alignment_monitor):
        """Stop should handle not-started state gracefully."""
        # Should not raise
        alignment_monitor.stop()
        assert alignment_monitor._state == AlignmentState.DISABLED

    @pytest.mark.unit
    def test_stop_sets_stop_event(self, alignment_monitor):
        """Stop should set the stop event."""
        alignment_monitor._stop_event.clear()
        alignment_monitor.stop()
        assert alignment_monitor._stop_event.is_set()


class TestTriggerMeasurement:
    """Test manual measurement triggering."""

    @pytest.mark.unit
    def test_trigger_when_disabled(self, alignment_monitor):
        """Should return None when monitor is disabled."""
        alignment_monitor._state = AlignmentState.DISABLED

        result = alignment_monitor.trigger_measurement()

        assert result is None

    @pytest.mark.unit
    def test_trigger_without_camera(self, alignment_monitor):
        """Should return None when camera not connected."""
        alignment_monitor._state = AlignmentState.DISCONNECTED
        alignment_monitor._camera_manager = None

        result = alignment_monitor.trigger_measurement()

        assert result is None


class TestHistoryLimit:
    """Test history size limiting."""

    @pytest.mark.unit
    def test_history_limit_constant(self, alignment_monitor):
        """Should have a defined history limit."""
        assert alignment_monitor.HISTORY_LIMIT == 100

    @pytest.mark.unit
    def test_min_interval_constant(self, alignment_monitor):
        """Should have a minimum interval constant."""
        assert alignment_monitor.MIN_INTERVAL == 5.0


# =============================================================================
# V1 Data Structure Tests
# =============================================================================

class TestAlignmentPointRecord:
    """Test V1 AlignmentPointRecord dataclass."""

    @pytest.mark.unit
    def test_point_record_creation(self):
        """Should create AlignmentPointRecord with required fields."""
        from alignment_monitor import AlignmentPointRecord
        point = AlignmentPointRecord(
            index=1,
            equatorial=(1.0, 0.5),
            altaz=(0.7, 1.2),
            ticks=(1000, 2000),
            timestamp=datetime.now()
        )
        assert point.index == 1
        assert point.equatorial == (1.0, 0.5)
        assert point.manual is False  # default

    @pytest.mark.unit
    def test_point_record_mean_weighted_error(self):
        """Should calculate mean weighted error correctly."""
        from alignment_monitor import AlignmentPointRecord
        point = AlignmentPointRecord(
            index=1,
            equatorial=(1.0, 0.5),
            altaz=(0.7, 1.2),
            ticks=(1000, 2000),
            timestamp=datetime.now(),
            weighted_error_sum=150.0,
            weighted_error_weight=3.0
        )
        assert point.mean_weighted_error == 50.0

    @pytest.mark.unit
    def test_point_record_mean_weighted_error_zero_weight(self):
        """Should return 0 when weight is 0."""
        from alignment_monitor import AlignmentPointRecord
        point = AlignmentPointRecord(
            index=1,
            equatorial=(1.0, 0.5),
            altaz=(0.7, 1.2),
            ticks=(1000, 2000),
            timestamp=datetime.now()
        )
        assert point.mean_weighted_error == 0.0

    @pytest.mark.unit
    def test_point_record_add_weighted_error(self):
        """Should accumulate weighted errors."""
        from alignment_monitor import AlignmentPointRecord
        point = AlignmentPointRecord(
            index=1,
            equatorial=(1.0, 0.5),
            altaz=(0.7, 1.2),
            ticks=(1000, 2000),
            timestamp=datetime.now()
        )
        point.add_weighted_error(100.0, 0.5)
        point.add_weighted_error(50.0, 0.5)

        assert point.weighted_error_sum == 75.0  # 100*0.5 + 50*0.5
        assert point.weighted_error_weight == 1.0
        assert point.mean_weighted_error == 75.0

    @pytest.mark.unit
    def test_point_record_reset_weighted_error(self):
        """Should reset weighted error accumulators."""
        from alignment_monitor import AlignmentPointRecord
        point = AlignmentPointRecord(
            index=1,
            equatorial=(1.0, 0.5),
            altaz=(0.7, 1.2),
            ticks=(1000, 2000),
            timestamp=datetime.now(),
            weighted_error_sum=100.0,
            weighted_error_weight=2.0
        )
        point.reset_weighted_error()

        assert point.weighted_error_sum == 0.0
        assert point.weighted_error_weight == 0.0


class TestSyncOffsetTracker:
    """Test V1 SyncOffsetTracker dataclass."""

    @pytest.mark.unit
    def test_tracker_default_values(self):
        """Should initialize with zero offsets."""
        from alignment_monitor import SyncOffsetTracker
        tracker = SyncOffsetTracker()
        assert tracker.cumulative_h_ticks == 0
        assert tracker.cumulative_e_ticks == 0

    @pytest.mark.unit
    def test_tracker_add_offset(self):
        """Should accumulate offsets."""
        from alignment_monitor import SyncOffsetTracker
        tracker = SyncOffsetTracker()
        tracker.add_offset(100, 50)
        tracker.add_offset(-20, 30)

        assert tracker.cumulative_h_ticks == 80
        assert tracker.cumulative_e_ticks == 80

    @pytest.mark.unit
    def test_tracker_reset(self):
        """Should reset to zero."""
        from alignment_monitor import SyncOffsetTracker
        tracker = SyncOffsetTracker()
        tracker.add_offset(100, 50)
        tracker.reset()

        assert tracker.cumulative_h_ticks == 0
        assert tracker.cumulative_e_ticks == 0


class TestHealthMonitor:
    """Test V1 HealthMonitor dataclass."""

    @pytest.mark.unit
    def test_health_monitor_default_values(self):
        """Should initialize with no events and no alert."""
        from alignment_monitor import HealthMonitor
        monitor = HealthMonitor()
        assert len(monitor.events) == 0
        assert monitor.alert_active is False

    @pytest.mark.unit
    def test_health_monitor_log_event(self):
        """Should log events and prune old ones."""
        from alignment_monitor import HealthMonitor
        monitor = HealthMonitor()
        monitor.log_event(500.0, 1800.0)  # 30 minute window

        assert len(monitor.events) == 1
        assert monitor.events[0][1] == 500.0

    @pytest.mark.unit
    def test_health_monitor_check_alert_below_threshold(self):
        """Should not trigger alert below threshold."""
        from alignment_monitor import HealthMonitor
        monitor = HealthMonitor()
        for _ in range(3):
            monitor.log_event(500.0, 1800.0)

        result = monitor.check_alert(5)

        assert result is False
        assert monitor.alert_active is False

    @pytest.mark.unit
    def test_health_monitor_check_alert_at_threshold(self):
        """Should trigger alert at threshold."""
        from alignment_monitor import HealthMonitor
        monitor = HealthMonitor()
        for _ in range(5):
            monitor.log_event(500.0, 1800.0)

        result = monitor.check_alert(5)

        assert result is True
        assert monitor.alert_active is True

    @pytest.mark.unit
    def test_health_monitor_clear(self):
        """Should clear events and reset alert."""
        from alignment_monitor import HealthMonitor
        monitor = HealthMonitor()
        monitor.log_event(500.0, 1800.0)
        monitor.alert_active = True
        monitor.clear()

        assert len(monitor.events) == 0
        assert monitor.alert_active is False


class TestDecisionResult:
    """Test V1 DecisionResult enum."""

    @pytest.mark.unit
    def test_decision_result_values(self):
        """Should have expected enum values."""
        from alignment_monitor import DecisionResult
        assert DecisionResult.NO_ACTION.value == "no_action"
        assert DecisionResult.SYNC.value == "sync"
        assert DecisionResult.ALIGN.value == "align"
        assert DecisionResult.LOCKOUT.value == "lockout"
        assert DecisionResult.ERROR.value == "error"


class TestReplacementCandidate:
    """Test V1 ReplacementCandidate dataclass."""

    @pytest.mark.unit
    def test_candidate_creation(self):
        """Should create candidate with required fields."""
        from alignment_monitor import ReplacementCandidate, AlignmentPointRecord
        point = AlignmentPointRecord(
            index=1,
            equatorial=(1.0, 0.5),
            altaz=(0.7, 1.2),
            ticks=(1000, 2000),
            timestamp=datetime.now()
        )
        candidate = ReplacementCandidate(
            point=point,
            new_det=0.75,
            improvement=0.15,
            reason="geometry",
            distance=25.0
        )
        assert candidate.point.index == 1
        assert candidate.new_det == 0.75
        assert candidate.reason == "geometry"


# =============================================================================
# V1 Lockout System Tests
# =============================================================================

class TestLockoutSystem:
    """Test V1 lockout system."""

    @pytest.mark.unit
    def test_in_lockout_period_when_none(self, alignment_monitor):
        """Should return False when no lockout is set."""
        alignment_monitor._lockout_until = None
        assert alignment_monitor._in_lockout_period() is False

    @pytest.mark.unit
    def test_in_lockout_period_when_active(self, alignment_monitor):
        """Should return True when lockout is active."""
        from datetime import timedelta
        alignment_monitor._lockout_until = datetime.now() + timedelta(seconds=30)
        assert alignment_monitor._in_lockout_period() is True

    @pytest.mark.unit
    def test_in_lockout_period_when_expired(self, alignment_monitor):
        """Should return False when lockout has expired."""
        from datetime import timedelta
        alignment_monitor._lockout_until = datetime.now() - timedelta(seconds=1)
        assert alignment_monitor._in_lockout_period() is False

    @pytest.mark.unit
    def test_start_lockout(self, alignment_monitor):
        """Should set lockout time in the future."""
        alignment_monitor._start_lockout(60.0)
        assert alignment_monitor._lockout_until is not None
        assert alignment_monitor._lockout_until > datetime.now()

    @pytest.mark.unit
    def test_clear_lockout(self, alignment_monitor):
        """Should clear the lockout."""
        from datetime import timedelta
        alignment_monitor._lockout_until = datetime.now() + timedelta(seconds=30)
        alignment_monitor._clear_lockout()
        assert alignment_monitor._lockout_until is None


# =============================================================================
# V1 Status Tests
# =============================================================================

class TestV1AlignmentStatus:
    """Test V1 additions to AlignmentStatus."""

    @pytest.mark.unit
    def test_status_has_v1_fields(self):
        """AlignmentStatus should have V1 fields."""
        from alignment_monitor import AlignmentStatus, AlignmentState
        status = AlignmentStatus(
            state=AlignmentState.MONITORING,
            camera_connected=True,
            camera_name="Test Camera",
            last_solve_time=None,
            last_ra_error=0.0,
            last_dec_error=0.0,
            last_total_error=0.0,
            average_error=0.0,
            max_error=0.0,
            measurement_count=0,
            stars_detected=0,
            solve_confidence=0.0,
            error_message="",
            geometry_determinant=0.75,
            health_alert_active=False,
            last_decision="sync",
            lockout_remaining=10.5
        )
        assert status.geometry_determinant == 0.75
        assert status.health_alert_active is False
        assert status.last_decision == "sync"
        assert status.lockout_remaining == 10.5

    @pytest.mark.unit
    def test_get_status_includes_v1_fields(self, alignment_monitor):
        """get_status should include V1 fields."""
        alignment_monitor._geometry_determinant = 0.65
        alignment_monitor._health_monitor.alert_active = True
        from alignment_monitor import DecisionResult
        alignment_monitor._last_decision = DecisionResult.SYNC

        status = alignment_monitor.get_status()

        assert status.geometry_determinant == 0.65
        assert status.health_alert_active is True
        assert status.last_decision == "sync"


# =============================================================================
# V1 Callback Tests
# =============================================================================

class TestV1Callbacks:
    """Test V1 callback setters."""

    @pytest.mark.unit
    def test_set_mount_altaz_callback(self, alignment_monitor):
        """Should set alt/az callback."""
        callback = lambda: (45.0, 180.0)
        alignment_monitor.set_mount_altaz_callback(callback)
        assert alignment_monitor._mount_altaz_callback is callback

    @pytest.mark.unit
    def test_set_mount_static_callback(self, alignment_monitor):
        """Should set mount static callback."""
        callback = lambda: True
        alignment_monitor.set_mount_static_callback(callback)
        assert alignment_monitor._mount_static_callback is callback

    @pytest.mark.unit
    def test_set_sync_callback(self, alignment_monitor):
        """Should set sync callback."""
        callback = lambda ra, dec: True
        alignment_monitor.set_sync_callback(callback)
        assert alignment_monitor._sync_callback is callback

    @pytest.mark.unit
    def test_set_alignment_data_callback(self, alignment_monitor):
        """Should set alignment data callback."""
        callback = lambda: []
        alignment_monitor.set_alignment_data_callback(callback)
        assert alignment_monitor._alignment_data_callback is callback
