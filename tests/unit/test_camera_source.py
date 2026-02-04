# -*- coding: utf-8 -*-
"""
Unit Tests for Camera Source Abstraction

Tests the camera source interface, factory, and implementations.
"""

import pytest
import sys
from unittest.mock import MagicMock, patch
from pathlib import Path
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from camera_source import CameraSource, CaptureResult


# =============================================================================
# CaptureResult Tests
# =============================================================================

class TestCaptureResult:
    """Test CaptureResult dataclass."""

    def test_capture_result_creation(self):
        """CaptureResult should store all fields."""
        import numpy as np

        image = np.zeros((100, 200), dtype=np.uint16)
        result = CaptureResult(
            image=image,
            width=200,
            height=100,
            exposure_time=2.0,
            binning=2,
            camera_info={'name': 'Test Camera'}
        )

        assert result.width == 200
        assert result.height == 100
        assert result.exposure_time == 2.0
        assert result.binning == 2
        assert result.camera_info['name'] == 'Test Camera'
        assert result.image.shape == (100, 200)


# =============================================================================
# CameraSource Interface Tests
# =============================================================================

class TestCameraSourceInterface:
    """Test CameraSource abstract interface."""

    def test_camera_source_is_abstract(self):
        """CameraSource should be abstract and not instantiable directly."""
        # CameraSource has abstract methods, so it can't be instantiated
        with pytest.raises(TypeError):
            CameraSource(logging.getLogger('test'))

    def test_camera_source_is_available_default(self):
        """Default is_available should return False."""
        assert CameraSource.is_available() is False


# =============================================================================
# AlpacaCameraSource Tests
# =============================================================================

class TestAlpacaCameraSource:
    """Test AlpacaCameraSource implementation."""

    @pytest.fixture
    def mock_camera_manager(self):
        """Create mock CameraManager."""
        mock = MagicMock()
        mock.is_connected.return_value = False
        mock.connect.return_value = True
        mock.get_error_message.return_value = ""
        return mock

    def test_alpaca_source_type(self):
        """AlpacaCameraSource should report 'alpaca' type."""
        from alpaca_camera import AlpacaCameraSource

        with patch('alpaca_camera.CameraManager'):
            source = AlpacaCameraSource(
                logging.getLogger('test'),
                address='127.0.0.1',
                port=11111
            )
            assert source.source_type == 'alpaca'

    def test_alpaca_is_available_depends_on_alpyca(self):
        """is_available should depend on ALPYCA_AVAILABLE."""
        from alpaca_camera import AlpacaCameraSource, ALPYCA_AVAILABLE

        # Result should match module constant
        assert AlpacaCameraSource.is_available() == ALPYCA_AVAILABLE

    def test_alpaca_connect_calls_manager(self):
        """connect should delegate to CameraManager."""
        from alpaca_camera import AlpacaCameraSource

        mock_manager = MagicMock()
        mock_manager.connect.return_value = True
        mock_manager.get_error_message.return_value = ""

        with patch('alpaca_camera.CameraManager', return_value=mock_manager), \
             patch('alpaca_camera.ALPYCA_AVAILABLE', True):
            source = AlpacaCameraSource(
                logging.getLogger('test'),
                address='192.168.1.100',
                port=11111,
                device_number=0
            )

            result = source.connect()

            mock_manager.connect.assert_called_once_with(
                '192.168.1.100', 11111, 0
            )
            assert result is True

    def test_alpaca_disconnect_calls_manager(self, mock_camera_manager):
        """disconnect should delegate to CameraManager."""
        from alpaca_camera import AlpacaCameraSource

        with patch('alpaca_camera.CameraManager', return_value=mock_camera_manager):
            source = AlpacaCameraSource(logging.getLogger('test'))

            source.disconnect()

            mock_camera_manager.disconnect.assert_called_once()

    def test_alpaca_get_info_not_connected(self, mock_camera_manager):
        """get_info should return default values when not connected."""
        from alpaca_camera import AlpacaCameraSource

        mock_camera_manager.get_camera_info.return_value = None

        with patch('alpaca_camera.CameraManager', return_value=mock_camera_manager):
            source = AlpacaCameraSource(logging.getLogger('test'))

            info = source.get_info()

            assert info['name'] == 'Not connected'
            assert info['pixel_size_um'] == 0.0


# =============================================================================
# ZWOCameraSource Tests
# =============================================================================

class TestZWOCameraSource:
    """Test ZWOCameraSource implementation."""

    def test_zwo_source_type(self):
        """ZWOCameraSource should report 'zwo' type."""
        from zwo_camera_source import ZWOCameraSource

        with patch('zwo_camera_source.ZWO_AVAILABLE', True):
            source = ZWOCameraSource(
                logging.getLogger('test'),
                camera_id=0
            )
            assert source.source_type == 'zwo'

    def test_zwo_is_available_when_sdk_missing(self):
        """is_available should return False when SDK not available."""
        from zwo_camera_source import ZWOCameraSource

        with patch('zwo_camera_source.ZWO_AVAILABLE', False):
            assert ZWOCameraSource.is_available() is False

    def test_zwo_connect_when_unavailable(self):
        """connect should return False when ZWO not available."""
        from zwo_camera_source import ZWOCameraSource

        with patch('zwo_camera_source.ZWO_AVAILABLE', False):
            source = ZWOCameraSource(logging.getLogger('test'))

            result = source.connect()

            assert result is False
            assert 'not available' in source.get_error_message().lower()

    def test_zwo_get_info_not_connected(self):
        """get_info should return default values when not connected."""
        from zwo_camera_source import ZWOCameraSource

        with patch('zwo_camera_source.ZWO_AVAILABLE', False):
            source = ZWOCameraSource(logging.getLogger('test'))

            info = source.get_info()

            assert info['name'] == 'Not connected'
            assert info['pixel_size_um'] == 0.0

    def test_zwo_set_gain(self):
        """set_gain should update internal gain setting."""
        from zwo_camera_source import ZWOCameraSource

        with patch('zwo_camera_source.ZWO_AVAILABLE', True):
            source = ZWOCameraSource(logging.getLogger('test'), gain=100)

            source.set_gain(200)

            assert source._gain == 200

    def test_zwo_set_image_type(self):
        """set_image_type should update internal setting."""
        from zwo_camera_source import ZWOCameraSource

        with patch('zwo_camera_source.ZWO_AVAILABLE', True):
            source = ZWOCameraSource(logging.getLogger('test'), image_type='RAW16')

            source.set_image_type('RAW8')

            assert source._image_type == 'RAW8'


# =============================================================================
# Camera Factory Tests
# =============================================================================

class TestCameraFactory:
    """Test camera factory function."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config object."""
        mock = MagicMock()
        mock.alignment_camera_source = 'alpaca'
        mock.alignment_camera_address = '127.0.0.1'
        mock.alignment_camera_port = 11111
        mock.alignment_camera_device = 0
        mock.zwo_camera_id = 0
        mock.zwo_gain = 100
        mock.zwo_image_type = 'RAW16'
        return mock

    def test_factory_creates_alpaca_source(self, mock_config):
        """Factory should create AlpacaCameraSource for 'alpaca' config."""
        from camera_factory import create_camera_source
        from alpaca_camera import AlpacaCameraSource

        mock_config.alignment_camera_source = 'alpaca'

        with patch('alpaca_camera.ALPYCA_AVAILABLE', True), \
             patch('alpaca_camera.CameraManager'):
            source = create_camera_source(mock_config, logging.getLogger('test'))

            assert isinstance(source, AlpacaCameraSource)

    def test_factory_creates_zwo_source(self, mock_config):
        """Factory should create ZWOCameraSource for 'zwo' config."""
        from camera_factory import create_camera_source
        from zwo_camera_source import ZWOCameraSource

        mock_config.alignment_camera_source = 'zwo'

        with patch('zwo_camera_source.ZWO_AVAILABLE', True), \
             patch('zwo_camera_source.zwo_is_available', return_value=True):
            source = create_camera_source(mock_config, logging.getLogger('test'))

            assert isinstance(source, ZWOCameraSource)

    def test_factory_falls_back_to_alpaca(self, mock_config):
        """Factory should fall back to Alpaca if ZWO unavailable."""
        from camera_factory import create_camera_source
        from alpaca_camera import AlpacaCameraSource

        mock_config.alignment_camera_source = 'zwo'

        with patch('zwo_camera_source.ZWO_AVAILABLE', True), \
             patch('zwo_camera_source.zwo_is_available', return_value=False), \
             patch('alpaca_camera.ALPYCA_AVAILABLE', True), \
             patch('alpaca_camera.CameraManager'):
            source = create_camera_source(mock_config, logging.getLogger('test'))

            # Should fall back to Alpaca
            assert isinstance(source, AlpacaCameraSource)

    def test_factory_returns_none_for_unknown(self, mock_config):
        """Factory should return None for unknown source type."""
        from camera_factory import create_camera_source

        mock_config.alignment_camera_source = 'unknown_source'

        source = create_camera_source(mock_config, logging.getLogger('test'))

        assert source is None

    def test_get_available_sources(self):
        """get_available_sources should return dict of availability."""
        from camera_factory import get_available_sources

        result = get_available_sources()

        assert 'alpaca' in result
        assert 'zwo' in result
        assert isinstance(result['alpaca'], bool)
        assert isinstance(result['zwo'], bool)

    def test_get_source_description(self):
        """get_source_description should return human-readable text."""
        from camera_factory import get_source_description

        alpaca_desc = get_source_description('alpaca')
        zwo_desc = get_source_description('zwo')

        assert 'Alpaca' in alpaca_desc
        assert 'ZWO' in zwo_desc


# =============================================================================
# TTS160Config ZWO Properties Tests
# =============================================================================

class TestTTS160ConfigZWO:
    """Test ZWO-related configuration properties."""

    def test_camera_source_default(self):
        """Default camera source should be 'alpaca'."""
        from TTS160Config import TTS160Config

        with patch.object(TTS160Config, '_load_config'):
            config = TTS160Config()
            config._dict = {'alignment': {}}

            assert config.alignment_camera_source == 'alpaca'

    def test_camera_source_set(self):
        """Should be able to set camera source."""
        from TTS160Config import TTS160Config

        with patch.object(TTS160Config, '_load_config'):
            config = TTS160Config()
            config._dict = {'alignment': {}}

            config.alignment_camera_source = 'zwo'

            assert config._dict['alignment']['camera_source'] == 'zwo'

    def test_zwo_camera_id_default(self):
        """Default ZWO camera ID should be 0."""
        from TTS160Config import TTS160Config

        with patch.object(TTS160Config, '_load_config'):
            config = TTS160Config()
            config._dict = {}

            assert config.zwo_camera_id == 0

    def test_zwo_gain_default(self):
        """Default ZWO gain should be 100."""
        from TTS160Config import TTS160Config

        with patch.object(TTS160Config, '_load_config'):
            config = TTS160Config()
            config._dict = {}

            assert config.zwo_gain == 100

    def test_zwo_image_type_default(self):
        """Default ZWO image type should be RAW16."""
        from TTS160Config import TTS160Config

        with patch.object(TTS160Config, '_load_config'):
            config = TTS160Config()
            config._dict = {}

            assert config.zwo_image_type == 'RAW16'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
