# -*- coding: utf-8 -*-
"""
Unit Tests for GUI Package

Tests for themes, state management, and component utilities.
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# =============================================================================
# Theme Tests
# =============================================================================

class TestThemes:
    """Test theme system."""

    def test_themes_defined(self):
        """All three themes should be defined."""
        from gui.themes import THEMES

        assert 'light' in THEMES
        assert 'dark' in THEMES
        assert 'astronomy' in THEMES

    def test_get_theme_valid(self):
        """get_theme should return correct theme."""
        from gui.themes import get_theme

        theme = get_theme('dark')
        assert theme.name == 'Dark'
        assert theme.background == '#121212'

    def test_get_theme_invalid_returns_default(self):
        """get_theme should return default for invalid name."""
        from gui.themes import get_theme, DEFAULT_THEME, THEMES

        theme = get_theme('invalid_theme')
        assert theme == THEMES[DEFAULT_THEME]

    def test_theme_has_required_colors(self):
        """Each theme should have all required color properties."""
        from gui.themes import THEMES

        required = [
            'background', 'surface', 'primary', 'text', 'text_secondary',
            'success', 'warning', 'error', 'border'
        ]

        for theme_name, theme in THEMES.items():
            for prop in required:
                assert hasattr(theme, prop), f"{theme_name} missing {prop}"
                assert getattr(theme, prop), f"{theme_name}.{prop} is empty"

    def test_astronomy_theme_red_spectrum(self):
        """Astronomy theme should use red-spectrum colors only."""
        from gui.themes import THEMES, is_red_spectrum

        astro = THEMES['astronomy']

        # These should all be in the red spectrum
        red_colors = [
            astro.background, astro.surface, astro.primary,
            astro.text, astro.border
        ]

        for color in red_colors:
            # All colors should have dominant red channel
            hex_color = color.lstrip('#')
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            assert r >= g and r >= b, f"{color} is not red-dominant"

    def test_generate_css(self):
        """generate_css should produce valid CSS."""
        from gui.themes import get_theme, generate_css

        theme = get_theme('dark')
        css = generate_css(theme)

        assert ':root' in css
        assert '--bg-color' in css
        assert theme.background in css
        assert theme.primary in css


# =============================================================================
# State Tests
# =============================================================================

class TestTelescopeState:
    """Test telescope state management."""

    def test_create_state(self):
        """create_state should return new state instance."""
        from gui.state import create_state

        state = create_state()
        assert state is not None
        assert state.connected is False
        assert state.ra_hours == 0.0

    def test_state_update(self):
        """update should modify state fields."""
        from gui.state import create_state

        state = create_state()
        state.update(connected=True, ra_hours=12.5)

        assert state.connected is True
        assert state.ra_hours == 12.5

    def test_state_listener(self):
        """Listeners should be notified of changes."""
        from gui.state import create_state

        state = create_state()
        changes = []

        def listener(field, value):
            changes.append((field, value))

        state.add_listener(listener)
        state.update(connected=True)

        assert len(changes) == 1
        assert changes[0] == ('connected', True)

    def test_state_remove_listener(self):
        """Removed listeners should not receive updates."""
        from gui.state import create_state

        state = create_state()
        changes = []

        def listener(field, value):
            changes.append((field, value))

        state.add_listener(listener)
        state.remove_listener(listener)
        state.update(connected=True)

        assert len(changes) == 0

    def test_state_no_update_if_unchanged(self):
        """No notification if value unchanged."""
        from gui.state import create_state

        state = create_state()
        state.update(connected=False)  # Set initial

        changes = []

        def listener(field, value):
            changes.append((field, value))

        state.add_listener(listener)
        state.update(connected=False)  # Same value

        assert len(changes) == 0

    def test_get_position_dict(self):
        """get_position_dict should return position data."""
        from gui.state import create_state

        state = create_state()
        state.update(ra_hours=12.5, dec_degrees=45.0, alt_degrees=60.0, az_degrees=180.0)

        pos = state.get_position_dict()

        assert pos['ra_hours'] == 12.5
        assert pos['dec_degrees'] == 45.0
        assert pos['alt_degrees'] == 60.0
        assert pos['az_degrees'] == 180.0

    def test_mark_stale(self):
        """mark_stale should detect stale data."""
        from gui.state import create_state
        from datetime import datetime, timedelta

        state = create_state()

        # Fresh update
        state.update(connected=True)
        assert state.mark_stale(threshold_seconds=5.0) is False

        # Simulate old update
        state.last_update = datetime.now() - timedelta(seconds=10)
        assert state.mark_stale(threshold_seconds=5.0) is True


# =============================================================================
# Formatting Tests
# =============================================================================

class TestFormatting:
    """Test value formatting utilities."""

    def test_format_ra(self):
        """format_ra should produce HMS notation."""
        from gui.state import format_ra

        result = format_ra(12.5)
        assert 'h' in result
        assert 'm' in result
        assert 's' in result

    def test_format_dec(self):
        """format_dec should produce DMS notation."""
        from gui.state import format_dec

        result = format_dec(45.5)
        assert '+' in result
        assert '°' in result

        result_neg = format_dec(-30.25)
        assert '-' in result_neg

    def test_format_sidereal_time(self):
        """format_sidereal_time should produce HMS notation."""
        from gui.state import format_sidereal_time

        result = format_sidereal_time(8.5)
        assert 'h' in result
        assert 'm' in result


# =============================================================================
# Disclosure Level Tests
# =============================================================================

class TestDisclosureLevel:
    """Test disclosure level enumeration."""

    def test_disclosure_levels(self):
        """DisclosureLevel should have three levels."""
        from gui.state import DisclosureLevel

        assert DisclosureLevel.BASIC.value == 1
        assert DisclosureLevel.EXPANDED.value == 2
        assert DisclosureLevel.ADVANCED.value == 3


# =============================================================================
# Alignment State Tests
# =============================================================================

class TestAlignmentState:
    """Test alignment state enumeration."""

    def test_alignment_states(self):
        """AlignmentState should have all expected states."""
        from gui.state import AlignmentState

        expected = [
            'DISABLED', 'DISCONNECTED', 'CONNECTING', 'CONNECTED',
            'CAPTURING', 'SOLVING', 'MONITORING', 'ERROR'
        ]

        for state_name in expected:
            assert hasattr(AlignmentState, state_name)


# =============================================================================
# Coordinate Parsing Tests
# =============================================================================

class TestCoordinateParsing:
    """Test coordinate parsing utilities."""

    def test_parse_ra_decimal(self):
        """parse_ra should handle decimal hours."""
        from gui.components.controls.slew import parse_ra

        assert parse_ra('12.5') == 12.5
        assert parse_ra('0.0') == 0.0

    def test_parse_ra_hms(self):
        """parse_ra should handle HMS format."""
        from gui.components.controls.slew import parse_ra

        result = parse_ra('12h30m')
        assert result is not None
        assert 12.4 < result < 12.6

    def test_parse_ra_invalid(self):
        """parse_ra should return None for invalid input."""
        from gui.components.controls.slew import parse_ra

        assert parse_ra('') is None
        assert parse_ra('invalid') is None

    def test_parse_dec_decimal(self):
        """parse_dec should handle decimal degrees."""
        from gui.components.controls.slew import parse_dec

        assert parse_dec('45.5') == 45.5
        assert parse_dec('+45.5') == 45.5
        assert parse_dec('-30.25') == -30.25

    def test_parse_dec_dms(self):
        """parse_dec should handle DMS format."""
        from gui.components.controls.slew import parse_dec

        result = parse_dec('+45°30\'')
        assert result is not None
        assert 45.4 < result < 45.6

    def test_parse_dec_invalid(self):
        """parse_dec should return None for invalid input."""
        from gui.components.controls.slew import parse_dec

        assert parse_dec('') is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
