"""
Integration tests for cache and device interaction.

Tests the cache update cycle, staleness handling, and thread coordination.
"""

import pytest
import threading
import time
from unittest.mock import Mock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestCacheDeviceIntegration:
    """Test cache interaction with device."""

    @pytest.fixture
    def mock_device(self):
        """Create a mock device with dynamic property values."""
        device = MagicMock()
        device.Connected = True

        # Use side_effect to simulate changing values
        ra_values = iter([12.0, 12.001, 12.002, 12.003])
        dec_values = iter([45.0, 45.001, 45.002, 45.003])

        device.RightAscension = property(lambda self: next(ra_values, 12.0))
        device._RightAscension = 12.0
        device._Declination = 45.0
        device._Altitude = 60.0
        device._Azimuth = 180.0
        device._Slewing = False
        device._Tracking = True
        device._AtPark = False
        device._AtHome = False

        return device

    @pytest.fixture
    def cache(self, mock_logger):
        """Create a real cache instance."""
        from tts160_cache import TTS160Cache
        cache = TTS160Cache(mock_logger)
        yield cache
        cache.stop_cache_thread()  # Clean up

    @pytest.mark.integration
    def test_cache_stores_property_value(self, cache):
        """Cache should store property values."""
        cache.update_property('RightAscension', 12.5)
        value = cache.get_property_value('RightAscension')
        assert abs(value - 12.5) < 0.0001

    @pytest.mark.integration
    def test_cache_tracks_timestamp(self, cache):
        """Cache should track when values were updated."""
        before = time.time()
        cache.update_property('Declination', 45.0)
        after = time.time()

        entry = cache.get_property('Declination')
        assert before <= entry['timestamp'] <= after

    @pytest.mark.integration
    def test_staleness_detection(self, cache):
        """Cache should detect stale entries."""
        from tts160_cache import CACHE_STALENESS_THRESHOLD

        cache.update_property('Altitude', 60.0)
        assert not cache.is_property_stale('Altitude')

        # Age the entry
        cache._cache['Altitude']['timestamp'] -= (CACHE_STALENESS_THRESHOLD + 1)
        assert cache.is_property_stale('Altitude')

    @pytest.mark.integration
    def test_multiple_property_updates(self, cache):
        """Cache should handle multiple property updates."""
        properties = {
            'RightAscension': 12.5,
            'Declination': 45.0,
            'Altitude': 60.0,
            'Azimuth': 180.0,
            'Tracking': True,
            'Slewing': False,
        }

        for name, value in properties.items():
            cache.update_property(name, value)

        for name, expected in properties.items():
            actual = cache.get_property_value(name)
            if isinstance(expected, bool):
                assert actual == expected
            else:
                assert abs(actual - expected) < 0.0001

    @pytest.mark.integration
    def test_cache_clears_all_entries(self, cache):
        """Clear should remove all cached entries."""
        cache.update_property('RightAscension', 12.5)
        cache.update_property('Declination', 45.0)

        assert len(cache._cache) == 2

        cache.clear_cache()

        assert len(cache._cache) == 0


class TestCacheBackgroundThread:
    """Test cache background update thread."""

    @pytest.fixture
    def cache_with_mock_device(self, mock_logger):
        """Create cache with mocked device for thread testing."""
        mock_device = MagicMock()
        mock_device.Connected = True
        mock_device._RightAscension = 12.0
        mock_device._Declination = 45.0

        with patch('TTS160Global.get_device', return_value=mock_device):
            from tts160_cache import TTS160Cache
            cache = TTS160Cache(mock_logger)
            yield cache, mock_device
            cache.stop_cache_thread()

    @pytest.mark.integration
    def test_thread_starts(self, mock_logger):
        """Cache thread should start when requested."""
        from tts160_cache import TTS160Cache

        # Mock the device for thread initialization
        mock_device = MagicMock()
        mock_device.Connected = True

        with patch('TTS160Global.get_device', return_value=mock_device):
            cache = TTS160Cache(mock_logger)

            try:
                cache.start_cache_thread()
                time.sleep(0.1)

                status = cache.get_cache_status()
                # Thread should be running after start
                assert status['thread_running'] or cache._thread is not None
            finally:
                cache.stop_cache_thread()

    @pytest.mark.integration
    def test_thread_stops(self, mock_logger):
        """Cache thread should stop when requested."""
        from tts160_cache import TTS160Cache

        # Mock the device for thread initialization
        mock_device = MagicMock()
        mock_device.Connected = True

        with patch('TTS160Global.get_device', return_value=mock_device):
            cache = TTS160Cache(mock_logger)
            cache.start_cache_thread()
            time.sleep(0.1)

            cache.stop_cache_thread()
            time.sleep(0.2)

        status = cache.get_cache_status()
        assert not status['thread_running']


class TestCacheStatusReporting:
    """Test cache status reporting."""

    @pytest.fixture
    def cache(self, mock_logger):
        """Create a cache instance."""
        from tts160_cache import TTS160Cache
        cache = TTS160Cache(mock_logger)
        yield cache
        cache.stop_cache_thread()

    @pytest.mark.integration
    def test_status_reports_total_properties(self, cache):
        """Status should report total cacheable properties."""
        from tts160_cache import CACHED_PROPERTIES

        status = cache.get_cache_status()
        assert status['total_properties'] == len(CACHED_PROPERTIES)

    @pytest.mark.integration
    def test_status_reports_cached_count(self, cache):
        """Status should report number of cached properties."""
        cache.update_property('RightAscension', 12.5)
        cache.update_property('Declination', 45.0)

        status = cache.get_cache_status()
        assert status['cached_properties'] == 2

    @pytest.mark.integration
    def test_status_reports_stale_count(self, cache):
        """Status should report number of stale properties."""
        from tts160_cache import CACHE_STALENESS_THRESHOLD, CACHED_PROPERTIES

        cache.update_property('RightAscension', 12.5)
        cache.update_property('Declination', 45.0)

        # Age one property
        cache._cache['RightAscension']['timestamp'] -= (CACHE_STALENESS_THRESHOLD + 1)

        status = cache.get_cache_status()
        # All uncached + 1 stale = total_properties - 2 + 1
        expected_stale = len(CACHED_PROPERTIES) - 2 + 1
        assert status['stale_properties'] == expected_stale


class TestCacheErrorHandling:
    """Test cache error handling."""

    @pytest.fixture
    def cache(self, mock_logger):
        """Create a cache instance."""
        from tts160_cache import TTS160Cache
        cache = TTS160Cache(mock_logger)
        yield cache
        cache.stop_cache_thread()

    @pytest.mark.integration
    def test_error_entry_returns_default(self, cache):
        """Entry with error should return default value."""
        # Manually inject error entry
        cache._cache['Tracking'] = {
            'value': True,
            'timestamp': time.time(),
            'error': 'Connection failed'
        }

        value = cache.get_property_value('Tracking', default=False)
        assert value is False

    @pytest.mark.integration
    def test_missing_property_returns_default(self, cache):
        """Missing property should return default value."""
        value = cache.get_property_value('NonExistent', default=-999)
        assert value == -999

    @pytest.mark.integration
    def test_invalid_property_ignored(self, cache):
        """Invalid property names should be ignored."""
        cache.update_property('InvalidProperty', 123)
        assert 'InvalidProperty' not in cache._cache


class TestCacheThreadSafety:
    """Test cache thread safety."""

    @pytest.fixture
    def cache(self, mock_logger):
        """Create a cache instance."""
        from tts160_cache import TTS160Cache
        cache = TTS160Cache(mock_logger)
        yield cache
        cache.stop_cache_thread()

    @pytest.mark.integration
    def test_concurrent_updates(self, cache):
        """Cache should handle concurrent updates safely."""
        errors = []

        def update_thread(property_name, values):
            try:
                for v in values:
                    cache.update_property(property_name, v)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=update_thread, args=('RightAscension', range(100))),
            threading.Thread(target=update_thread, args=('Declination', range(100))),
            threading.Thread(target=update_thread, args=('Altitude', range(100))),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    @pytest.mark.integration
    def test_concurrent_reads(self, cache):
        """Cache should handle concurrent reads safely."""
        cache.update_property('RightAscension', 12.5)
        errors = []

        def read_thread():
            try:
                for _ in range(100):
                    cache.get_property_value('RightAscension')
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_thread) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    @pytest.mark.integration
    def test_concurrent_read_write(self, cache):
        """Cache should handle concurrent read/write safely."""
        errors = []

        def writer():
            try:
                for i in range(100):
                    cache.update_property('Azimuth', float(i))
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(100):
                    cache.get_property_value('Azimuth')
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestCacheAPIIntegration:
    """Test cache integration with telescope.py get_cached_or_fresh."""

    @pytest.fixture
    def setup_telescope_globals(self, mock_logger):
        """Setup telescope module globals for testing."""
        from tts160_cache import TTS160Cache
        import telescope

        cache = TTS160Cache(mock_logger)
        telescope.TTS160_cache = cache
        telescope.logger = mock_logger

        yield cache

        cache.stop_cache_thread()
        telescope.TTS160_cache = None

    @pytest.mark.integration
    def test_get_cached_or_fresh_uses_cache(self, setup_telescope_globals):
        """get_cached_or_fresh should use cached value when fresh."""
        from telescope import get_cached_or_fresh

        cache = setup_telescope_globals
        cache.update_property('RightAscension', 12.5)

        fresh_getter = Mock(return_value=99.0)
        result = get_cached_or_fresh('RightAscension', fresh_getter, staleness_threshold=5.0)

        assert abs(result - 12.5) < 0.0001
        fresh_getter.assert_not_called()

    @pytest.mark.integration
    def test_get_cached_or_fresh_calls_getter_when_stale(self, setup_telescope_globals):
        """get_cached_or_fresh should call getter when cache is stale."""
        from telescope import get_cached_or_fresh

        cache = setup_telescope_globals
        cache.update_property('RightAscension', 12.5)
        # Age the entry
        cache._cache['RightAscension']['timestamp'] -= 10

        fresh_getter = Mock(return_value=13.0)
        result = get_cached_or_fresh('RightAscension', fresh_getter, staleness_threshold=0.5)

        assert abs(result - 13.0) < 0.0001
        fresh_getter.assert_called_once()

    @pytest.mark.integration
    def test_get_cached_or_fresh_updates_cache(self, setup_telescope_globals):
        """get_cached_or_fresh should update cache after fresh read."""
        from telescope import get_cached_or_fresh

        cache = setup_telescope_globals

        fresh_getter = Mock(return_value=15.0)
        result = get_cached_or_fresh('Declination', fresh_getter)

        # Cache should now have the value
        cached = cache.get_property_value('Declination')
        assert abs(cached - 15.0) < 0.0001

    @pytest.mark.integration
    def test_get_cached_or_fresh_uses_property_staleness(self, setup_telescope_globals):
        """get_cached_or_fresh should use PROPERTY_STALENESS defaults."""
        from telescope import get_cached_or_fresh, PROPERTY_STALENESS

        cache = setup_telescope_globals

        # Set a value that's older than Slewing threshold (0.3s)
        cache.update_property('Slewing', False)
        cache._cache['Slewing']['timestamp'] -= 0.5

        fresh_getter = Mock(return_value=True)
        result = get_cached_or_fresh('Slewing', fresh_getter)

        # Should have called getter because entry is stale (0.5s > 0.3s threshold)
        fresh_getter.assert_called_once()
        assert result is True
