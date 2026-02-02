"""
Unit tests for the TTS160 cache module.

Tests cache operations, staleness detection, and thread safety
without requiring hardware connections.
"""

import pytest
import time
from unittest.mock import Mock, patch

# Import module under test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tts160_cache import (
    TTS160Cache,
    CACHE_STALENESS_THRESHOLD,
    CACHED_PROPERTIES,
    UPDATE_INTERVAL,
)


class TestCacheInitialization:
    """Test cache initialization and setup."""

    @pytest.mark.unit
    def test_cache_initializes_empty(self, mock_logger):
        """Cache should start with no cached values."""
        cache = TTS160Cache(mock_logger)
        assert len(cache._cache) == 0

    @pytest.mark.unit
    def test_cache_has_lock(self, mock_logger):
        """Cache should have a threading lock for thread safety."""
        cache = TTS160Cache(mock_logger)
        assert cache._lock is not None

    @pytest.mark.unit
    def test_cache_logger_assigned(self, mock_logger):
        """Cache should store the provided logger."""
        cache = TTS160Cache(mock_logger)
        assert cache.logger is mock_logger


class TestCacheUpdateProperty:
    """Test property update operations."""

    @pytest.mark.unit
    def test_update_valid_property(self, isolated_cache):
        """Updating a valid property should store the value."""
        isolated_cache.update_property('RightAscension', 12.5)
        entry = isolated_cache.get_property('RightAscension')

        assert entry is not None
        assert entry['value'] == 12.5
        assert entry['error'] is None
        assert 'timestamp' in entry

    @pytest.mark.unit
    def test_update_ignores_invalid_property(self, isolated_cache):
        """Updating an uncached property should be ignored."""
        isolated_cache.update_property('InvalidProperty', 999)
        entry = isolated_cache.get_property('InvalidProperty')

        assert entry is None

    @pytest.mark.unit
    def test_update_ignores_non_string_property(self, isolated_cache):
        """Non-string property names should be ignored."""
        isolated_cache.update_property(123, 'value')
        assert len(isolated_cache._cache) == 0

    @pytest.mark.unit
    def test_update_overwrites_previous_value(self, isolated_cache):
        """Updating a property should overwrite the previous value."""
        isolated_cache.update_property('Declination', 30.0)
        isolated_cache.update_property('Declination', 45.0)

        value = isolated_cache.get_property_value('Declination')
        assert value == 45.0

    @pytest.mark.unit
    def test_update_refreshes_timestamp(self, isolated_cache):
        """Updating should refresh the timestamp."""
        isolated_cache.update_property('Altitude', 60.0)
        first_timestamp = isolated_cache.get_property('Altitude')['timestamp']

        time.sleep(0.01)  # Small delay

        isolated_cache.update_property('Altitude', 65.0)
        second_timestamp = isolated_cache.get_property('Altitude')['timestamp']

        assert second_timestamp > first_timestamp


class TestCacheGetProperty:
    """Test property retrieval operations."""

    @pytest.mark.unit
    def test_get_existing_property(self, isolated_cache, cache_test_properties):
        """Getting an existing property should return the entry."""
        isolated_cache.update_property('RightAscension', 12.5)
        entry = isolated_cache.get_property('RightAscension')

        assert entry is not None
        assert entry['value'] == 12.5

    @pytest.mark.unit
    def test_get_missing_property_returns_none(self, isolated_cache):
        """Getting a missing property should return None."""
        entry = isolated_cache.get_property('RightAscension')
        assert entry is None

    @pytest.mark.unit
    def test_get_property_value_with_default(self, isolated_cache):
        """get_property_value should return default for missing properties."""
        value = isolated_cache.get_property_value('NonExistent', default=-999)
        assert value == -999

    @pytest.mark.unit
    def test_get_property_value_returns_cached(self, isolated_cache):
        """get_property_value should return cached value when available."""
        isolated_cache.update_property('Azimuth', 180.0)
        value = isolated_cache.get_property_value('Azimuth', default=0.0)
        assert value == 180.0

    @pytest.mark.unit
    def test_get_property_value_default_on_error(self, isolated_cache):
        """get_property_value should return default when entry has error."""
        # Manually inject an error entry
        isolated_cache._cache['Tracking'] = {
            'value': True,
            'timestamp': time.time(),
            'error': 'Connection failed'
        }

        value = isolated_cache.get_property_value('Tracking', default=False)
        assert value is False


class TestCacheStaleness:
    """Test staleness detection."""

    @pytest.mark.unit
    def test_fresh_property_not_stale(self, isolated_cache):
        """Recently updated property should not be stale."""
        isolated_cache.update_property('Slewing', False)
        assert not isolated_cache.is_property_stale('Slewing')

    @pytest.mark.unit
    def test_old_property_is_stale(self, isolated_cache):
        """Property older than threshold should be stale."""
        isolated_cache.update_property('AtPark', True)

        # Manually age the entry past staleness threshold
        entry = isolated_cache._cache['AtPark']
        entry['timestamp'] = time.time() - CACHE_STALENESS_THRESHOLD - 1

        assert isolated_cache.is_property_stale('AtPark')

    @pytest.mark.unit
    def test_missing_property_is_stale(self, isolated_cache):
        """Missing property should be considered stale."""
        assert isolated_cache.is_property_stale('NonExistent')

    @pytest.mark.unit
    def test_staleness_threshold_boundary(self, isolated_cache):
        """Property exactly at threshold should not be stale."""
        isolated_cache.update_property('IsPulseGuiding', False)

        # Set timestamp to exactly threshold age
        entry = isolated_cache._cache['IsPulseGuiding']
        entry['timestamp'] = time.time() - CACHE_STALENESS_THRESHOLD

        # At exactly threshold, should not be stale (uses >)
        assert not isolated_cache.is_property_stale('IsPulseGuiding')


class TestCacheStatus:
    """Test cache status reporting."""

    @pytest.mark.unit
    def test_empty_cache_status(self, isolated_cache):
        """Empty cache should report zero cached properties."""
        status = isolated_cache.get_cache_status()

        assert status['total_properties'] == len(CACHED_PROPERTIES)
        assert status['cached_properties'] == 0
        # thread_running is None or False when no thread exists
        assert not status['thread_running']

    @pytest.mark.unit
    def test_populated_cache_status(self, isolated_cache, cache_test_properties):
        """Populated cache should report accurate counts."""
        for prop, value in cache_test_properties.items():
            isolated_cache.update_property(prop, value)

        status = isolated_cache.get_cache_status()

        assert status['cached_properties'] == len(cache_test_properties)
        assert status['error_properties'] == 0

    @pytest.mark.unit
    def test_stale_properties_counted(self, isolated_cache):
        """Stale properties should be counted in status."""
        isolated_cache.update_property('RightAscension', 10.0)
        isolated_cache.update_property('Declination', 20.0)

        # Age one property
        isolated_cache._cache['RightAscension']['timestamp'] = (
            time.time() - CACHE_STALENESS_THRESHOLD - 10
        )

        status = isolated_cache.get_cache_status()

        # All uncached properties are stale, plus the aged one
        total_stale = len(CACHED_PROPERTIES) - 2 + 1  # -2 cached, +1 aged
        assert status['stale_properties'] == total_stale


class TestCacheClear:
    """Test cache clearing operations."""

    @pytest.mark.unit
    def test_clear_removes_all_entries(self, isolated_cache, cache_test_properties):
        """clear_cache should remove all cached values."""
        for prop, value in cache_test_properties.items():
            isolated_cache.update_property(prop, value)

        assert len(isolated_cache._cache) > 0

        isolated_cache.clear_cache()

        assert len(isolated_cache._cache) == 0

    @pytest.mark.unit
    def test_clear_logs_action(self, isolated_cache, mock_logger):
        """clear_cache should log the action."""
        isolated_cache.logger = mock_logger
        isolated_cache.update_property('Tracking', True)
        isolated_cache.clear_cache()

        mock_logger.info.assert_called()


class TestCachedPropertiesList:
    """Test the CACHED_PROPERTIES constant."""

    @pytest.mark.unit
    def test_cached_properties_not_empty(self):
        """CACHED_PROPERTIES should contain expected properties."""
        assert len(CACHED_PROPERTIES) > 0

    @pytest.mark.unit
    def test_cached_properties_contains_position(self):
        """CACHED_PROPERTIES should include position properties."""
        assert 'RightAscension' in CACHED_PROPERTIES
        assert 'Declination' in CACHED_PROPERTIES
        assert 'Altitude' in CACHED_PROPERTIES
        assert 'Azimuth' in CACHED_PROPERTIES

    @pytest.mark.unit
    def test_cached_properties_contains_status(self):
        """CACHED_PROPERTIES should include status properties."""
        assert 'Tracking' in CACHED_PROPERTIES
        assert 'Slewing' in CACHED_PROPERTIES
        assert 'AtPark' in CACHED_PROPERTIES


class TestCacheConstants:
    """Test cache configuration constants."""

    @pytest.mark.unit
    def test_staleness_threshold_positive(self):
        """Staleness threshold should be a positive number."""
        assert CACHE_STALENESS_THRESHOLD > 0

    @pytest.mark.unit
    def test_update_interval_reasonable(self):
        """Update interval should be reasonable (not too fast or slow)."""
        assert 0.1 <= UPDATE_INTERVAL <= 5.0
