# -*- coding: utf-8 -*-
"""Driver fix arc 2026-11, FIX 3 (review finding F-DR-0600).

The device's ``_config`` is ``TTS160Config``; ``_start_ephemeris_pusher`` read
``ephemeris_push_enabled`` and two cadences that existed only on the server
``Config``, so it always died with AttributeError.  ``TTS160Config`` now carries
the three keys in section ``[driver]`` -- the pusher is OFF BY DEFAULT (missing
key -> False; the shipped TTS160config.toml says ``false``) and CAN start when
the operator enables it.

The connect tests run the device's real ``_perform_mount_connection`` (mount
initialisation stubbed) with a ``TTS160Config`` loaded from a copy of the
SHIPPED ``TTS160config.toml``, and the pusher's real sender methods
(``SerialManager.push_time_reference`` / ``push_body_ephemeris``) recording the
SET command ids they would put on the wire.
"""

import threading
import time
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

from TTS160Config import TTS160Config
from TTS160Device import TTS160Device
from tts160_serial import SerialManager
from tts160_types import SetCommand

SHIPPED_TOML = Path(__file__).resolve().parents[2] / 'TTS160config.toml'
PUSH_IDS = {SetCommand.SET_TIME_REFERENCE, SetCommand.SET_BODY_EPHEMERIS}  # 0x14, 0x15


class FakeLink:
    """Serial-manager double for Connect: records every SET command id."""

    def __init__(self):
        self.sets = []
        self._lk = threading.Lock()
        self.push_time_reference = types.MethodType(SerialManager.push_time_reference, self)
        self.push_body_ephemeris = types.MethodType(SerialManager.push_body_ephemeris, self)

    is_connected = True

    def connect(self, port):
        return True

    def add_client(self, client):
        pass

    def execute_set_command(self, cmd_id, data=b'', priority=None):
        with self._lk:
            self.sets.append(int(cmd_id))
        return [(1, 0)]


def _config_from(tmp_path, monkeypatch, edit=None):
    text = SHIPPED_TOML.read_text(encoding='utf-8')
    if edit is not None:
        text = edit(text)
    (tmp_path / 'TTS160config.toml').write_text(text, encoding='utf-8')
    monkeypatch.chdir(tmp_path)  # TTS160Config reads ./TTS160config.toml
    cfg = TTS160Config()
    assert cfg._config_file == tmp_path / 'TTS160config.toml'
    return cfg


def _connect(cfg, link):
    dev = TTS160Device.__new__(TTS160Device)
    dev._logger = Mock()
    dev._lock = threading.RLock()
    dev._config = cfg
    dev._serial_manager = link
    dev._Connected = False
    dev._Connecting = True
    dev._ephemeris_pusher = None
    dev._initialize_connected_mount = Mock()
    dev.TTS160_cache = Mock()
    astro = Mock()
    astro.sidereal_reference_rad.return_value = 1.0
    astro.body_ephemeris_with_rates.return_value = (1.0, 0.1, 0.0, 0.0)
    dev._astro_services = astro
    dev._perform_mount_connection({'test': '127.0.0.1'})
    assert dev._Connected is True
    return dev


def _settle_and_stop(dev, seconds=1.5):
    time.sleep(seconds)  # a started pusher polls immediately, then every tick_s (1 s)
    pusher = dev._ephemeris_pusher
    if pusher is not None:
        pusher.stop()
    return pusher


# ---------------------------------------------------------------------------
# Shipped configuration: a connect starts no pusher and sends no 0x14 / 0x15
# ---------------------------------------------------------------------------

def test_shipped_toml_disables_push():
    text = SHIPPED_TOML.read_text(encoding='utf-8')
    assert 'ephemeris_push_enabled = false' in text


def test_connect_with_shipped_config_starts_no_pusher(tmp_path, monkeypatch):
    cfg = _config_from(tmp_path, monkeypatch)
    link = FakeLink()
    dev = _connect(cfg, link)
    pusher = _settle_and_stop(dev)
    assert pusher is None
    assert not PUSH_IDS.intersection(link.sets), link.sets


# ---------------------------------------------------------------------------
# Enabled by the operator: the pusher starts (no AttributeError) and its
# cadences come from TTS160Config.  The same harness as above, one key flipped
# -- which also shows the shipped-config test would fail if the default were on.
# ---------------------------------------------------------------------------

def _enable(text):
    """Operator enables the push in [driver] (keys replaced, or inserted if the file predates them)."""
    keys = ('ephemeris_push_enabled = true\n'
            'ephemeris_lst_interval_s = 900.0\n'
            'ephemeris_body_interval_s = 45.0\n')
    text = '\n'.join(line for line in text.splitlines() if not line.startswith('ephemeris_')) + '\n'
    assert text.count('[driver]\n') == 1
    return text.replace('[driver]\n', '[driver]\n' + keys)


def test_connect_with_push_enabled_starts_pusher(tmp_path, monkeypatch):
    cfg = _config_from(tmp_path, monkeypatch, edit=_enable)
    link = FakeLink()
    dev = _connect(cfg, link)
    pusher = dev._ephemeris_pusher
    assert pusher is not None and pusher.running
    assert pusher._cfg.enabled is True
    assert pusher._cfg.lst_interval_s == 900.0
    assert pusher._cfg.body_interval_s == 45.0
    _settle_and_stop(dev)
    assert int(SetCommand.SET_TIME_REFERENCE) in link.sets
    assert int(SetCommand.SET_BODY_EPHEMERIS) in link.sets
    for call in dev._logger.warning.call_args_list:
        assert 'ephemeris pusher failed to start' not in str(call)


# ---------------------------------------------------------------------------
# TTS160Config properties: defaults, invalid values, setters, section [driver]
# ---------------------------------------------------------------------------

def _strip_push_keys(text):
    return '\n'.join(line for line in text.splitlines() if not line.startswith('ephemeris_'))


def test_missing_keys_default_off_and_cadences(tmp_path, monkeypatch):
    cfg = _config_from(tmp_path, monkeypatch, edit=_strip_push_keys)
    assert cfg.ephemeris_push_enabled is False
    assert cfg.ephemeris_lst_interval_s == 600.0
    assert cfg.ephemeris_body_interval_s == 120.0


@pytest.mark.parametrize('bad', ['"fast"', '0', '-5.0', 'true', 'nan', 'inf'])
def test_invalid_cadences_fall_back_to_defaults(tmp_path, monkeypatch, bad):
    def edit(text):
        text = text.replace('ephemeris_lst_interval_s = 600.0', 'ephemeris_lst_interval_s = %s' % bad)
        return text.replace('ephemeris_body_interval_s = 120.0', 'ephemeris_body_interval_s = %s' % bad)
    cfg = _config_from(tmp_path, monkeypatch, edit=edit)
    assert cfg.ephemeris_lst_interval_s == 600.0
    assert cfg.ephemeris_body_interval_s == 120.0


def test_only_a_toml_true_enables(tmp_path, monkeypatch):
    cfg = _config_from(tmp_path, monkeypatch, edit=lambda t: t.replace(
        'ephemeris_push_enabled = false', 'ephemeris_push_enabled = "false"'))
    assert cfg.ephemeris_push_enabled is False


def test_setters_write_driver_section(tmp_path, monkeypatch):
    cfg = _config_from(tmp_path, monkeypatch)
    cfg.ephemeris_push_enabled = True
    cfg.ephemeris_lst_interval_s = 300
    cfg.ephemeris_body_interval_s = 30
    assert cfg._dict['driver']['ephemeris_push_enabled'] is True
    assert cfg._dict['driver']['ephemeris_lst_interval_s'] == 300.0
    assert cfg._dict['driver']['ephemeris_body_interval_s'] == 30.0
    assert cfg.ephemeris_push_enabled is True
    assert cfg.ephemeris_lst_interval_s == 300.0
    assert cfg.ephemeris_body_interval_s == 30.0
