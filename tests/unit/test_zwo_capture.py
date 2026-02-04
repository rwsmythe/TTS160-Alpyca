# -*- coding: utf-8 -*-
"""
Unit Tests for ZWO Capture Module

Tests the zwo_capture package components with mocked SDK.
"""

import pytest
import sys
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from zwo_capture.exceptions import (
    ZWOError,
    ZWONotAvailable,
    ZWOCameraError,
    ZWOTimeoutError,
    ZWOConfigurationError,
)
from zwo_capture.config import (
    DEFAULT_CONFIG,
    IMAGE_TYPES,
    SUPPORTED_BINNING,
    get_default_config,
    validate_image_type,
    validate_binning,
)


# =============================================================================
# Exception Tests
# =============================================================================

class TestExceptions:
    """Test exception hierarchy."""

    def test_zwo_error_is_base(self):
        """ZWOError should be the base exception."""
        assert issubclass(ZWONotAvailable, ZWOError)
        assert issubclass(ZWOCameraError, ZWOError)

    def test_zwo_camera_error_hierarchy(self):
        """Camera-specific errors should inherit from ZWOCameraError."""
        assert issubclass(ZWOTimeoutError, ZWOCameraError)
        assert issubclass(ZWOConfigurationError, ZWOCameraError)

    def test_exception_messages(self):
        """Exceptions should preserve messages."""
        msg = "Test error message"
        assert str(ZWOError(msg)) == msg
        assert str(ZWONotAvailable(msg)) == msg
        assert str(ZWOCameraError(msg)) == msg
        assert str(ZWOTimeoutError(msg)) == msg
        assert str(ZWOConfigurationError(msg)) == msg

    def test_catch_all_zwo_errors(self):
        """Should be able to catch all ZWO errors with base class."""
        exceptions = [
            ZWONotAvailable("test"),
            ZWOCameraError("test"),
            ZWOTimeoutError("test"),
            ZWOConfigurationError("test"),
        ]
        for exc in exceptions:
            try:
                raise exc
            except ZWOError:
                pass  # Should catch all


# =============================================================================
# Config Tests
# =============================================================================

class TestConfig:
    """Test configuration defaults and validation."""

    def test_default_config_values(self):
        """Default config should have expected values."""
        assert DEFAULT_CONFIG['exposure_ms'] == 2000
        assert DEFAULT_CONFIG['gain'] == 100
        assert DEFAULT_CONFIG['binning'] == 2
        assert DEFAULT_CONFIG['image_type'] == 'RAW16'
        assert DEFAULT_CONFIG['bandwidth'] == 80
        assert DEFAULT_CONFIG['timeout_ms'] == 30000

    def test_get_default_config_returns_copy(self):
        """get_default_config should return a copy."""
        config1 = get_default_config()
        config2 = get_default_config()
        config1['exposure_ms'] = 9999
        assert config2['exposure_ms'] == 2000

    def test_image_types_mapping(self):
        """Image types should map to correct SDK values."""
        assert IMAGE_TYPES['RAW8'] == 0
        assert IMAGE_TYPES['RGB24'] == 1
        assert IMAGE_TYPES['RAW16'] == 2
        assert IMAGE_TYPES['Y8'] == 3

    def test_supported_binning(self):
        """Supported binning should include standard values."""
        assert 1 in SUPPORTED_BINNING
        assert 2 in SUPPORTED_BINNING
        assert 4 in SUPPORTED_BINNING

    def test_validate_image_type_valid(self):
        """Valid image types should pass validation."""
        assert validate_image_type('RAW8') == 0
        assert validate_image_type('raw16') == 2  # Case insensitive
        assert validate_image_type('RGB24') == 1

    def test_validate_image_type_invalid(self):
        """Invalid image types should raise ValueError."""
        with pytest.raises(ValueError) as excinfo:
            validate_image_type('INVALID')
        assert 'Invalid image type' in str(excinfo.value)

    def test_validate_binning_valid(self):
        """Valid binning values should pass validation."""
        assert validate_binning(1) == 1
        assert validate_binning(2) == 2
        assert validate_binning(4) == 4

    def test_validate_binning_invalid(self):
        """Invalid binning values should raise ValueError."""
        with pytest.raises(ValueError) as excinfo:
            validate_binning(5)
        assert 'Invalid binning' in str(excinfo.value)


# =============================================================================
# SDK Loader Tests
# =============================================================================

class TestSDKLoader:
    """Test SDK loader platform detection and path resolution."""

    def test_get_platform_info_returns_tuple(self):
        """get_platform_info should return (platform, arch) tuple."""
        from zwo_capture.sdk_loader import get_platform_info

        # This will run on the actual platform
        platform, arch = get_platform_info()
        assert platform in ('windows', 'linux', 'macos')
        assert isinstance(arch, str)

    @patch('zwo_capture.sdk_loader.platform.system')
    @patch('zwo_capture.sdk_loader.struct.calcsize')
    def test_windows_x64_detection(self, mock_calcsize, mock_system):
        """Should detect Windows x64 correctly."""
        from zwo_capture.sdk_loader import get_platform_info

        mock_system.return_value = 'Windows'
        mock_calcsize.return_value = 8  # 64-bit

        plat, arch = get_platform_info()
        assert plat == 'windows'
        assert arch == 'x64'

    @patch('zwo_capture.sdk_loader.platform.system')
    @patch('zwo_capture.sdk_loader.struct.calcsize')
    def test_windows_x86_detection(self, mock_calcsize, mock_system):
        """Should detect Windows x86 correctly."""
        from zwo_capture.sdk_loader import get_platform_info

        mock_system.return_value = 'Windows'
        mock_calcsize.return_value = 4  # 32-bit

        plat, arch = get_platform_info()
        assert plat == 'windows'
        assert arch == 'x86'

    @patch('zwo_capture.sdk_loader.platform.system')
    def test_macos_detection(self, mock_system):
        """Should detect macOS correctly."""
        from zwo_capture.sdk_loader import get_platform_info

        mock_system.return_value = 'Darwin'

        plat, arch = get_platform_info()
        assert plat == 'macos'
        assert arch == 'universal'

    @patch('zwo_capture.sdk_loader.platform.system')
    @patch('zwo_capture.sdk_loader.platform.machine')
    def test_linux_x64_detection(self, mock_machine, mock_system):
        """Should detect Linux x64 correctly."""
        from zwo_capture.sdk_loader import get_platform_info

        mock_system.return_value = 'Linux'
        mock_machine.return_value = 'x86_64'

        plat, arch = get_platform_info()
        assert plat == 'linux'
        assert arch == 'x64'

    @patch('zwo_capture.sdk_loader.platform.system')
    @patch('zwo_capture.sdk_loader.platform.machine')
    def test_linux_armv7_detection(self, mock_machine, mock_system):
        """Should detect Linux armv7 correctly."""
        from zwo_capture.sdk_loader import get_platform_info

        mock_system.return_value = 'Linux'
        mock_machine.return_value = 'armv7l'

        plat, arch = get_platform_info()
        assert plat == 'linux'
        assert arch == 'armv7'

    @patch('zwo_capture.sdk_loader.platform.system')
    @patch('zwo_capture.sdk_loader.platform.machine')
    def test_linux_armv8_detection(self, mock_machine, mock_system):
        """Should detect Linux aarch64 correctly."""
        from zwo_capture.sdk_loader import get_platform_info

        mock_system.return_value = 'Linux'
        mock_machine.return_value = 'aarch64'

        plat, arch = get_platform_info()
        assert plat == 'linux'
        assert arch == 'armv8'

    @patch.dict('os.environ', {'ZWO_ASI_LIB': '/custom/path/to/sdk.dll'})
    @patch('os.path.isfile')
    def test_env_sdk_path_used(self, mock_isfile):
        """Should use ZWO_ASI_LIB environment variable when set."""
        from zwo_capture.sdk_loader import get_env_sdk_path

        mock_isfile.return_value = True
        path = get_env_sdk_path()
        assert path == '/custom/path/to/sdk.dll'

    @patch.dict('os.environ', {'ZWO_ASI_LIB': '/nonexistent/sdk.dll'})
    @patch('os.path.isfile')
    def test_env_sdk_path_missing_file(self, mock_isfile):
        """Should return None if env path doesn't exist."""
        from zwo_capture.sdk_loader import get_env_sdk_path

        mock_isfile.return_value = False
        path = get_env_sdk_path()
        assert path is None

    def test_is_sdk_available_returns_bool(self):
        """is_sdk_available should return boolean without throwing."""
        from zwo_capture.sdk_loader import is_sdk_available

        # Should not throw, just return bool
        result = is_sdk_available()
        assert isinstance(result, bool)

    def test_reset_sdk_clears_state(self):
        """reset_sdk should clear module state."""
        from zwo_capture import sdk_loader

        # Set some state
        sdk_loader._sdk_path = '/some/path'
        sdk_loader._sdk_initialized = True

        # Reset
        sdk_loader.reset_sdk()

        assert sdk_loader._sdk_path is None
        assert sdk_loader._sdk_initialized is False


# =============================================================================
# Camera Class Tests (with mocked zwoasi)
# =============================================================================

class TestZWOCameraMocked:
    """Test ZWOCamera class with mocked zwoasi module."""

    @pytest.fixture
    def mock_zwoasi(self):
        """Create mock zwoasi module."""
        mock = MagicMock()
        mock.get_num_cameras.return_value = 1
        mock.get_camera_property.return_value = {
            'Name': 'ZWO ASI120MM-S',
            'MaxWidth': 1280,
            'MaxHeight': 960,
            'PixelSize': 3.75,
            'IsColorCam': False,
            'BitDepth': 12,
            'SupportedBins': [1, 2, 4],
        }

        # Mock camera instance
        mock_camera = MagicMock()
        mock_camera.get_camera_property.return_value = mock.get_camera_property.return_value
        mock_camera.get_controls.return_value = {
            'Exposure': {'MinValue': 32, 'MaxValue': 2000000000},
            'Gain': {'MinValue': 0, 'MaxValue': 300},
        }
        mock.Camera.return_value = mock_camera

        # Constants
        mock.ASI_EXPOSURE = 1
        mock.ASI_GAIN = 2
        mock.ASI_BANDWIDTHOVERLOAD = 3
        mock.ASI_HIGH_SPEED_MODE = 4
        mock.ASI_TEMPERATURE = 5
        mock.ASI_EXP_SUCCESS = 0
        mock.ASI_EXP_FAILED = 1
        mock.ASI_EXP_WORKING = 2

        return mock

    def test_camera_init_does_not_open(self):
        """Camera init should not open the camera."""
        from zwo_capture.camera import ZWOCamera

        # Patch the SDK initialization
        with patch('zwo_capture.camera.initialize_sdk'):
            cam = ZWOCamera(camera_id=0)
            assert cam.camera_id == 0
            assert not cam.is_open

    def test_camera_context_manager(self, mock_zwoasi):
        """Camera should work as context manager."""
        from zwo_capture.camera import ZWOCamera

        with patch('zwo_capture.camera.initialize_sdk'), \
             patch('zwo_capture.camera.get_zwoasi_module', return_value=mock_zwoasi):

            with ZWOCamera(camera_id=0) as cam:
                assert cam.is_open
            # After context, camera should be closed
            assert not cam.is_open

    def test_camera_close_idempotent(self, mock_zwoasi):
        """Calling close multiple times should be safe."""
        from zwo_capture.camera import ZWOCamera

        with patch('zwo_capture.camera.initialize_sdk'), \
             patch('zwo_capture.camera.get_zwoasi_module', return_value=mock_zwoasi):

            cam = ZWOCamera(camera_id=0)
            cam.open()

            # Close multiple times should not raise
            cam.close()
            cam.close()
            cam.close()

            assert not cam.is_open

    def test_camera_get_info_requires_open(self):
        """get_camera_info should raise if camera not open."""
        from zwo_capture.camera import ZWOCamera

        with patch('zwo_capture.camera.initialize_sdk'):
            cam = ZWOCamera(camera_id=0)

            with pytest.raises(ZWOCameraError) as excinfo:
                cam.get_camera_info()
            assert 'not open' in str(excinfo.value).lower()

    def test_camera_capture_requires_open(self):
        """capture should raise if camera not open."""
        from zwo_capture.camera import ZWOCamera

        with patch('zwo_capture.camera.initialize_sdk'):
            cam = ZWOCamera(camera_id=0)

            with pytest.raises(ZWOCameraError) as excinfo:
                cam.capture()
            assert 'not open' in str(excinfo.value).lower()

    def test_camera_configure_requires_open(self):
        """configure should raise if camera not open."""
        from zwo_capture.camera import ZWOCamera

        with patch('zwo_capture.camera.initialize_sdk'):
            cam = ZWOCamera(camera_id=0)

            with pytest.raises(ZWOCameraError) as excinfo:
                cam.configure(exposure_ms=1000, gain=100, binning=2)
            assert 'not open' in str(excinfo.value).lower()


# =============================================================================
# Public API Tests
# =============================================================================

class TestPublicAPI:
    """Test public API functions."""

    def test_is_available_returns_bool(self):
        """is_available should return bool without throwing."""
        from zwo_capture import is_available

        result = is_available()
        assert isinstance(result, bool)

    def test_get_camera_count_returns_int(self):
        """get_camera_count should return int without throwing."""
        from zwo_capture import get_camera_count

        result = get_camera_count()
        assert isinstance(result, int)
        assert result >= 0

    def test_exports_are_available(self):
        """All documented exports should be available."""
        from zwo_capture import (
            ZWOCamera,
            is_available,
            list_cameras,
            get_camera_count,
            ZWOError,
            ZWONotAvailable,
            ZWOCameraError,
            ZWOTimeoutError,
            ZWOConfigurationError,
        )

        # Just verify they're importable
        assert ZWOCamera is not None
        assert is_available is not None
        assert list_cameras is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
