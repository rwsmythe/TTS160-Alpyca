"""
Unit tests for the telescope.py cache integration.

Tests the get_cached_or_fresh helper function and PROPERTY_STALENESS configuration.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestPropertyStalenessConfig:
    """Test PROPERTY_STALENESS configuration."""

    @pytest.mark.unit
    def test_staleness_config_exists(self):
        """PROPERTY_STALENESS should be defined."""
        from telescope import PROPERTY_STALENESS
        assert PROPERTY_STALENESS is not None
        assert isinstance(PROPERTY_STALENESS, dict)

    @pytest.mark.unit
    def test_position_properties_have_low_staleness(self):
        """Position properties should have low staleness thresholds."""
        from telescope import PROPERTY_STALENESS
        assert PROPERTY_STALENESS['RightAscension'] <= 1.0
        assert PROPERTY_STALENESS['Declination'] <= 1.0
        assert PROPERTY_STALENESS['Altitude'] <= 1.0
        assert PROPERTY_STALENESS['Azimuth'] <= 1.0

    @pytest.mark.unit
    def test_critical_status_has_very_low_staleness(self):
        """Critical status properties should have very low staleness."""
        from telescope import PROPERTY_STALENESS
        assert PROPERTY_STALENESS['Slewing'] <= 0.5
        assert PROPERTY_STALENESS['IsPulseGuiding'] <= 0.5

    @pytest.mark.unit
    def test_park_home_have_higher_staleness(self):
        """Park/home status can have higher staleness."""
        from telescope import PROPERTY_STALENESS
        assert PROPERTY_STALENESS['AtPark'] >= 1.0
        assert PROPERTY_STALENESS['AtHome'] >= 1.0


class TestGetCachedOrFresh:
    """Test get_cached_or_fresh helper function."""

    @pytest.fixture
    def setup_telescope_mocks(self):
        """Setup mocks for telescope module globals."""
        with patch('telescope.TTS160_cache') as mock_cache, \
             patch('telescope.logger') as mock_logger:
            mock_logger.debug = Mock()
            yield mock_cache, mock_logger

    @pytest.mark.unit
    def test_returns_cached_value_when_fresh(self, setup_telescope_mocks):
        """Should return cached value when it's fresh."""
        mock_cache, mock_logger = setup_telescope_mocks
        from telescope import get_cached_or_fresh

        # Setup fresh cache entry
        mock_cache.get_property.return_value = {
            'value': 12.5,
            'timestamp': time.time(),  # Very fresh
            'error': None
        }

        fresh_getter = Mock(return_value=99.9)
        result = get_cached_or_fresh('RightAscension', fresh_getter)

        assert result == 12.5
        fresh_getter.assert_not_called()  # Should not call device

    @pytest.mark.unit
    def test_calls_fresh_getter_when_stale(self, setup_telescope_mocks):
        """Should call fresh_getter when cache is stale."""
        mock_cache, mock_logger = setup_telescope_mocks
        from telescope import get_cached_or_fresh

        # Setup stale cache entry (10 seconds old)
        mock_cache.get_property.return_value = {
            'value': 12.5,
            'timestamp': time.time() - 10,  # Old
            'error': None
        }

        fresh_getter = Mock(return_value=13.0)
        result = get_cached_or_fresh('RightAscension', fresh_getter, staleness_threshold=0.5)

        assert result == 13.0
        fresh_getter.assert_called_once()
        mock_cache.update_property.assert_called_once_with('RightAscension', 13.0)

    @pytest.mark.unit
    def test_calls_fresh_getter_when_cache_empty(self, setup_telescope_mocks):
        """Should call fresh_getter when cache is empty."""
        mock_cache, mock_logger = setup_telescope_mocks
        from telescope import get_cached_or_fresh

        mock_cache.get_property.return_value = None

        fresh_getter = Mock(return_value=45.0)
        result = get_cached_or_fresh('Declination', fresh_getter)

        assert result == 45.0
        fresh_getter.assert_called_once()

    @pytest.mark.unit
    def test_calls_fresh_getter_when_cache_has_error(self, setup_telescope_mocks):
        """Should call fresh_getter when cache entry has error."""
        mock_cache, mock_logger = setup_telescope_mocks
        from telescope import get_cached_or_fresh

        mock_cache.get_property.return_value = {
            'value': 12.5,
            'timestamp': time.time(),
            'error': 'Connection failed'  # Has error
        }

        fresh_getter = Mock(return_value=13.0)
        result = get_cached_or_fresh('RightAscension', fresh_getter)

        assert result == 13.0
        fresh_getter.assert_called_once()

    @pytest.mark.unit
    def test_uses_property_specific_staleness(self, setup_telescope_mocks):
        """Should use PROPERTY_STALENESS for default threshold."""
        mock_cache, mock_logger = setup_telescope_mocks
        from telescope import get_cached_or_fresh, PROPERTY_STALENESS

        # Entry is 0.4 seconds old
        mock_cache.get_property.return_value = {
            'value': True,
            'timestamp': time.time() - 0.4,
            'error': None
        }

        fresh_getter = Mock(return_value=False)

        # Slewing has 0.3s threshold, so 0.4s should be stale
        result = get_cached_or_fresh('Slewing', fresh_getter)
        fresh_getter.assert_called_once()

    @pytest.mark.unit
    def test_works_without_cache(self, setup_telescope_mocks):
        """Should work when cache is None."""
        mock_cache, mock_logger = setup_telescope_mocks
        import telescope

        # Temporarily set cache to None
        original_cache = telescope.TTS160_cache
        telescope.TTS160_cache = None

        try:
            fresh_getter = Mock(return_value=180.0)
            result = telescope.get_cached_or_fresh('Azimuth', fresh_getter)

            assert result == 180.0
            fresh_getter.assert_called_once()
        finally:
            telescope.TTS160_cache = original_cache


class TestCacheHelperConstants:
    """Test cache helper related constants."""

    @pytest.mark.unit
    def test_all_cached_properties_have_staleness(self):
        """All high-frequency properties should have staleness defined."""
        from telescope import PROPERTY_STALENESS

        expected_properties = [
            'RightAscension', 'Declination', 'Altitude', 'Azimuth',
            'Slewing', 'IsPulseGuiding', 'Tracking', 'SideOfPier',
            'SiderealTime', 'AtPark', 'AtHome'
        ]

        for prop in expected_properties:
            assert prop in PROPERTY_STALENESS, f"Missing staleness for {prop}"
            assert isinstance(PROPERTY_STALENESS[prop], (int, float))
            assert PROPERTY_STALENESS[prop] > 0
