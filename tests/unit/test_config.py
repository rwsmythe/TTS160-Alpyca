"""
Unit tests for the TTS160 configuration module.

Tests configuration loading, property access, and TOML persistence
using temporary files to avoid modifying actual config.
"""

import pytest
import toml
from pathlib import Path
from unittest.mock import patch, Mock

# Import module under test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import Config, ConfigError


class TestConfigInitialization:
    """Test configuration initialization."""

    @pytest.mark.unit
    def test_config_loads_from_file(self, temp_toml_file, tmp_path):
        """Config should load successfully from TOML file."""
        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            # Create config.toml in the mocked directory
            config_file = tmp_path / 'config.toml'
            config_file.write_text(temp_toml_file.read_text())

            config = Config()
            assert config is not None

    @pytest.mark.unit
    def test_config_raises_on_missing_file(self, tmp_path):
        """Config should raise error when file is missing."""
        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            with pytest.raises(ConfigError, match="Failed to load"):
                Config()

    @pytest.mark.unit
    def test_config_raises_on_invalid_toml(self, tmp_path):
        """Config should raise error on invalid TOML syntax."""
        config_file = tmp_path / 'config.toml'
        config_file.write_text('invalid toml {{{{')

        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            with pytest.raises(ConfigError):
                Config()

    @pytest.mark.unit
    def test_config_has_lock(self, temp_toml_file, tmp_path):
        """Config should have threading lock for thread safety."""
        config_file = tmp_path / 'config.toml'
        config_file.write_text(temp_toml_file.read_text())

        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            config = Config()
            assert config._lock is not None


class TestConfigNetworkSection:
    """Test network configuration properties."""

    @pytest.fixture
    def loaded_config(self, tmp_path):
        """Create a loaded config instance for testing."""
        config_content = """
[network]
ip_address = '192.168.1.100'
port = 5555
threads = 8

[server]
location = 'Observatory'
verbose_driver_exceptions = true
setup_port = 8080

[logging]
log_level = 'INFO'
log_to_stdout = true
max_size_mb = 10
num_keep_logs = 5
"""
        config_file = tmp_path / 'config.toml'
        config_file.write_text(config_content)

        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            return Config()

    @pytest.mark.unit
    def test_ip_address_property(self, loaded_config):
        """ip_address property should return configured value."""
        assert loaded_config.ip_address == '192.168.1.100'

    @pytest.mark.unit
    def test_port_property(self, loaded_config):
        """port property should return configured value."""
        assert loaded_config.port == 5555

    @pytest.mark.unit
    def test_threads_property(self, loaded_config):
        """threads property should return configured value."""
        assert loaded_config.threads == 8

    @pytest.mark.unit
    def test_threads_default_value(self, tmp_path):
        """threads should default to 4 if not specified."""
        config_content = """
[network]
ip_address = ''
port = 5555

[server]
location = 'Test'
verbose_driver_exceptions = true
setup_port = 8080

[logging]
log_level = 'DEBUG'
log_to_stdout = false
max_size_mb = 5
num_keep_logs = 10
"""
        config_file = tmp_path / 'config.toml'
        config_file.write_text(config_content)

        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            config = Config()
            assert config.threads == 4


class TestConfigServerSection:
    """Test server configuration properties."""

    @pytest.fixture
    def loaded_config(self, tmp_path):
        """Create a loaded config instance for testing."""
        config_content = """
[network]
ip_address = ''
port = 5555
threads = 4

[server]
location = 'Test Observatory'
verbose_driver_exceptions = true
setup_port = 9090

[logging]
log_level = 'WARNING'
log_to_stdout = false
max_size_mb = 20
num_keep_logs = 15
"""
        config_file = tmp_path / 'config.toml'
        config_file.write_text(config_content)

        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            return Config()

    @pytest.mark.unit
    def test_location_property(self, loaded_config):
        """location property should return configured value."""
        assert loaded_config.location == 'Test Observatory'

    @pytest.mark.unit
    def test_verbose_driver_exceptions_property(self, loaded_config):
        """verbose_driver_exceptions should return configured value."""
        assert loaded_config.verbose_driver_exceptions is True

    @pytest.mark.unit
    def test_setup_port_property(self, loaded_config):
        """setup_port property should return configured value."""
        assert loaded_config.setup_port == 9090


class TestConfigLoggingSection:
    """Test logging configuration properties."""

    @pytest.fixture
    def loaded_config(self, tmp_path):
        """Create a loaded config instance for testing."""
        config_content = """
[network]
ip_address = ''
port = 5555
threads = 4

[server]
location = 'Test'
verbose_driver_exceptions = false
setup_port = 8080

[logging]
log_level = 'DEBUG'
log_to_stdout = true
max_size_mb = 25
num_keep_logs = 20
"""
        config_file = tmp_path / 'config.toml'
        config_file.write_text(config_content)

        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            return Config()

    @pytest.mark.unit
    def test_log_to_stdout_property(self, loaded_config):
        """log_to_stdout property should return configured value."""
        assert loaded_config.log_to_stdout is True

    @pytest.mark.unit
    def test_max_size_mb_property(self, loaded_config):
        """max_size_mb property should return configured value."""
        assert loaded_config.max_size_mb == 25

    @pytest.mark.unit
    def test_num_keep_logs_property(self, loaded_config):
        """num_keep_logs property should return configured value."""
        assert loaded_config.num_keep_logs == 20


class TestConfigSetters:
    """Test configuration property setters."""

    @pytest.fixture
    def loaded_config(self, tmp_path):
        """Create a loaded config instance for testing."""
        config_content = """
[network]
ip_address = ''
port = 5555
threads = 4

[server]
location = 'Initial'
verbose_driver_exceptions = false
setup_port = 8080

[logging]
log_level = 'INFO'
log_to_stdout = false
max_size_mb = 5
num_keep_logs = 10
"""
        config_file = tmp_path / 'config.toml'
        config_file.write_text(config_content)

        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            return Config()

    @pytest.mark.unit
    def test_set_ip_address(self, loaded_config):
        """Setting ip_address should update the value."""
        loaded_config.ip_address = '10.0.0.1'
        assert loaded_config.ip_address == '10.0.0.1'

    @pytest.mark.unit
    def test_set_port(self, loaded_config):
        """Setting port should update the value."""
        loaded_config.port = 6666
        assert loaded_config.port == 6666

    @pytest.mark.unit
    def test_set_threads(self, loaded_config):
        """Setting threads should update the value."""
        loaded_config.threads = 16
        assert loaded_config.threads == 16

    @pytest.mark.unit
    def test_set_location(self, loaded_config):
        """Setting location should update the value."""
        loaded_config.location = 'New Observatory'
        assert loaded_config.location == 'New Observatory'


class TestConfigSaveAndReload:
    """Test configuration persistence operations."""

    @pytest.mark.unit
    def test_save_config(self, tmp_path):
        """save() should write configuration to file."""
        config_content = """
[network]
ip_address = ''
port = 5555
threads = 4

[server]
location = 'Original'
verbose_driver_exceptions = true
setup_port = 8080

[logging]
log_level = 'DEBUG'
log_to_stdout = false
max_size_mb = 5
num_keep_logs = 10
"""
        config_file = tmp_path / 'config.toml'
        config_file.write_text(config_content)

        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            config = Config()
            config.location = 'Modified'
            config.save()

        # Read back and verify
        saved_content = toml.load(config_file)
        assert saved_content['server']['location'] == 'Modified'

    @pytest.mark.unit
    def test_reload_config(self, tmp_path):
        """reload() should refresh configuration from file."""
        config_content = """
[network]
ip_address = ''
port = 5555
threads = 4

[server]
location = 'Initial'
verbose_driver_exceptions = true
setup_port = 8080

[logging]
log_level = 'DEBUG'
log_to_stdout = false
max_size_mb = 5
num_keep_logs = 10
"""
        config_file = tmp_path / 'config.toml'
        config_file.write_text(config_content)

        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            config = Config()
            assert config.location == 'Initial'

            # Modify file externally
            new_content = config_content.replace('Initial', 'External Change')
            config_file.write_text(new_content)

            config.reload()
            assert config.location == 'External Change'


class TestConfigMissingValues:
    """Test handling of missing configuration values."""

    @pytest.mark.unit
    def test_missing_value_returns_empty(self, tmp_path):
        """Missing values should return empty string."""
        config_content = """
[network]
port = 5555

[server]
verbose_driver_exceptions = true
setup_port = 8080

[logging]
log_level = 'DEBUG'
log_to_stdout = false
max_size_mb = 5
num_keep_logs = 10
"""
        config_file = tmp_path / 'config.toml'
        config_file.write_text(config_content)

        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            config = Config()
            # ip_address is missing, should return ''
            assert config.ip_address == ''


class TestConfigRepr:
    """Test configuration string representation."""

    @pytest.mark.unit
    def test_repr_includes_class_name(self, tmp_path):
        """__repr__ should include class name."""
        config_content = """
[network]
ip_address = ''
port = 5555
threads = 4

[server]
location = 'Test'
verbose_driver_exceptions = true
setup_port = 8080

[logging]
log_level = 'DEBUG'
log_to_stdout = false
max_size_mb = 5
num_keep_logs = 10
"""
        config_file = tmp_path / 'config.toml'
        config_file.write_text(config_content)

        with patch.object(Config, 'get_config_dir', return_value=tmp_path):
            config = Config()
            repr_str = repr(config)
            assert 'Config' in repr_str
            assert 'config_file' in repr_str


class TestConfigConstants:
    """Test configuration class constants."""

    @pytest.mark.unit
    def test_default_config_file_name(self):
        """DEFAULT_CONFIG_FILE should be config.toml."""
        assert Config.DEFAULT_CONFIG_FILE == 'config.toml'

    @pytest.mark.unit
    def test_section_constants_defined(self):
        """Section constants should be defined."""
        assert Config.NETWORK_SECTION == 'network'
        assert Config.SERVER_SECTION == 'server'
        assert Config.LOGGING_SECTION == 'logging'
