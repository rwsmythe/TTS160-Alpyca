"""Config and connection lifecycle tests with an entirely mocked serial link."""

import csv
import logging
import threading
import time
from unittest.mock import Mock, patch

import pytest

from TTS160Config import TTS160Config
from TTS160Device import TTS160Device
from tts160_serial import CommandPriority
import variable_logger as vl


@pytest.fixture
def config(tmp_path, monkeypatch):
    (tmp_path / "TTS160config.toml").write_text("[driver]\nsync_time_on_connect = false\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(TTS160Config, "OVERRIDE_CONFIG_PATH", str(tmp_path / "absent.toml"))
    return TTS160Config()


@pytest.fixture
def device(config, monkeypatch):
    dev = TTS160Device.__new__(TTS160Device)
    dev._config = config
    dev._logger = Mock(spec=logging.Logger)
    dev._serial_manager = Mock()
    dev._serial_manager._connection_count = 1
    dev._lock = threading.RLock()
    dev._Connected = False
    dev._Connecting = True
    dev.TTS160_cache = Mock()
    dev._send_command = Mock(return_value="test#")
    dev._sync_site_coordinates_from_mount = Mock()
    dev._start_gps_if_enabled = Mock()
    dev._start_alignment_if_enabled = Mock()
    dev._start_ephemeris_pusher = Mock()
    dev._stop_ephemeris_pusher = Mock()
    dev._stop_alignment = Mock()
    dev._stop_gps = Mock()
    monkeypatch.setattr(TTS160Device, "_altaz_frame", property(lambda self: None))
    monkeypatch.setattr(TTS160Device, "_gcrs_frame", property(lambda self: None))
    yield dev
    obj = getattr(dev, "_variable_logger", None)
    if obj is not None:
        obj.stop()


def test_defaults_when_section_absent(config):
    assert config.debug_logger_enabled is False
    assert config.debug_logger_variables == list(vl.DEFAULT_VARIABLES)
    assert config.debug_logger_interval_s == 1.0
    assert config.debug_logger_directory == "variable_logs"


def test_config_properties_preserve_explicit_values_and_overrides(config, tmp_path):
    config.debug_logger_enabled = True
    config.debug_logger_variables = []
    config.debug_logger_interval_s = 0.0
    config.debug_logger_directory = str(tmp_path)
    assert config.debug_logger_enabled is True
    assert config.debug_logger_variables == []
    assert config.debug_logger_interval_s == 0.0
    assert config.debug_logger_directory == str(tmp_path)
    config._dict2 = {"debug_logger": {"interval_s": 2.0}}
    assert config.debug_logger_interval_s == 2.0


def test_disabled_hook_constructs_nothing(device):
    with patch("TTS160Device.VariableLogger", create=True) as factory:
        device._start_variable_logger_if_enabled()
    factory.assert_not_called()


def test_enabled_hook_starts_once_with_low_priority_read(device):
    device._config.debug_logger_enabled = True
    with patch("TTS160Device.VariableLogger", create=True) as factory:
        device._start_variable_logger_if_enabled()
        device._start_variable_logger_if_enabled()
    factory.assert_called_once()
    factory.return_value.start.assert_called_once_with()
    query = factory.call_args.kwargs["query"]
    query(["T1"])
    device._serial_manager.query_variables.assert_called_once_with(["T1"], priority=CommandPriority.LOW)


@pytest.mark.parametrize("stage", ["constructor", "start"])
def test_start_hook_contains_every_exception(device, stage):
    device._config.debug_logger_enabled = True
    with patch("TTS160Device.VariableLogger", create=True) as factory:
        if stage == "constructor":
            factory.side_effect = RuntimeError("broken constructor")
        else:
            factory.return_value.start.side_effect = RuntimeError("broken start")
        device._perform_mount_connection({"test": "client"})
    assert device._Connected
    device._logger.warning.assert_called_once()


def test_stop_hook_without_logger_is_safe(device):
    device._stop_variable_logger()


@pytest.mark.parametrize("raises", [False, True])
def test_stop_hook_stops_once_and_clears_attribute(device, raises):
    obj = Mock()
    device._variable_logger = obj
    if raises:
        obj.stop.side_effect = RuntimeError("broken stop")
    device._stop_variable_logger()
    device._stop_variable_logger()
    obj.stop.assert_called_once_with()
    assert device._variable_logger is None
    assert device._logger.warning.call_count == int(raises)


@pytest.mark.parametrize("variables,interval", [
    (["Q1"], 1.0), (["T31"], 1.0), (["T32"], 1.0), (["T1", "T1"], 1.0),
    ([], 1.0), ([f"T{i}" for i in range(1, 22)], 1.0), (["T1"], 0.5),
])
def test_bad_config_does_not_fail_connect(device, tmp_path, caplog, variables, interval):
    config = device._config
    config.debug_logger_enabled = True
    config.debug_logger_variables = variables
    config.debug_logger_interval_s = interval
    config.debug_logger_directory = str(tmp_path)
    device._logger = logging.getLogger("variable_logger_wiring")
    device._perform_mount_connection({"test": "client"})
    assert device._Connected
    obj = getattr(device, "_variable_logger", None)
    assert obj is None or not obj.running
    device._serial_manager.query_variables.assert_not_called()
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert not list(tmp_path.glob("*.csv"))


def test_disconnect_while_poll_in_flight_is_bounded_and_closes_file(device, tmp_path):
    entered, release = threading.Event(), threading.Event()

    def query(variables, priority):
        assert priority == CommandPriority.LOW
        entered.set()
        release.wait(10)
        return dict.fromkeys(variables, 1)

    device._config.debug_logger_enabled = True
    device._config.debug_logger_directory = str(tmp_path)
    device._serial_manager.query_variables.side_effect = query
    obj = None
    try:
        device._perform_mount_connection({"test": "client"})
        assert entered.wait(1)
        obj = device._variable_logger
        # The serial disconnect releases the in-flight mocked read, as a closed link does.
        device._serial_manager.disconnect.side_effect = release.set
        before = time.monotonic()
        device.Disconnect({"test": "client"})
        assert time.monotonic() - before < 2.5
        assert not device._Connected
        assert device._variable_logger is None
        assert not obj.running
        obj._thread.join(0.4)
        assert not obj._thread.is_alive()
        assert obj._file.closed
        with open(obj.path, newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream))
        assert rows == [vl.header_row(vl.DEFAULT_VARIABLES)]
        assert device._serial_manager.query_variables.call_count == 1
    finally:
        release.set()
        if obj is not None:
            obj.stop()
