# -*- coding: utf-8 -*-
"""Driver fix arc 2026-11, FIX 2 (review findings F-X-0006 + F-DR-0508): Park parks.

- The Alpaca ``park`` responder must CALL ``TTS160_dev.Park()`` (it evaluated the
  bound method and returned success without parking -- F-DR-0508).
- The PARK_UNPARK (0x0B) byte must match the firmware AS IMPLEMENTED
  (binary.c:2030-2035): non-zero sets Park_Cmd (park), zero sets Unpark_Cmd
  (unpark).  The driver sent 0 to park and 1 to unpark -- F-X-0006.
"""

import struct
import threading
from unittest.mock import Mock

import pytest
from falcon import App, testing

from TTS160Device import TTS160Device
from tts160_serial import SerialManager
from tts160_types import SetCommand


# ---------------------------------------------------------------------------
# Alpaca responder: PUT /park calls Park() exactly once
# ---------------------------------------------------------------------------

@pytest.fixture
def park_client(mock_logger):
    import exceptions
    import shr
    import telescope

    saved = (telescope.TTS160_dev, telescope.TTS160_cache, telescope.logger, shr.logger, exceptions.logger)
    device = Mock()
    device.Connected = True
    device.AtPark = False
    telescope.TTS160_dev = device
    telescope.TTS160_cache = None
    telescope.logger = mock_logger
    shr.logger = mock_logger
    exceptions.logger = mock_logger
    app = App()
    app.add_route('/api/v1/telescope/{devnum:int}/park', telescope.park())
    yield testing.TestClient(app), device
    (telescope.TTS160_dev, telescope.TTS160_cache, telescope.logger, shr.logger, exceptions.logger) = saved


def _put_park(client):
    return client.simulate_put('/api/v1/telescope/0/park',
                               body='ClientID=7&ClientTransactionID=11',
                               headers={'Content-Type': 'application/x-www-form-urlencoded'})


def test_park_responder_calls_device_park_once(park_client):
    client, device = park_client
    resp = _put_park(client)
    assert resp.status_code == 200
    assert resp.json['ErrorNumber'] == 0
    device.Park.assert_called_once_with()


def test_park_responder_reports_device_park_failure(park_client):
    client, device = park_client
    device.Park.side_effect = RuntimeError('Park failed')
    resp = _put_park(client)
    assert resp.json['ErrorNumber'] == 0x500
    device.Park.assert_called_once_with()


# ---------------------------------------------------------------------------
# TTS160Device._park_v357 / _unpark_v357 bytes
# ---------------------------------------------------------------------------

def _bare_device():
    dev = TTS160Device.__new__(TTS160Device)
    dev._logger = Mock()
    dev._lock = threading.RLock()
    dev._execute_v357_set = Mock(return_value=True)
    return dev


def test_device_park_sends_one():
    dev = _bare_device()
    dev._park_v357()
    dev._execute_v357_set.assert_called_once_with(SetCommand.PARK_UNPARK, struct.pack('<B', 1))


def test_device_unpark_sends_zero():
    dev = _bare_device()
    dev._unpark_v357()
    dev._execute_v357_set.assert_called_once_with(SetCommand.PARK_UNPARK, struct.pack('<B', 0))


# ---------------------------------------------------------------------------
# SerialManager.park / unpark bytes (no non-test caller; same defect)
# ---------------------------------------------------------------------------

def _bare_manager():
    sm = SerialManager.__new__(SerialManager)
    sm.execute_set_command = Mock(return_value=[(1, 0)])
    return sm


def test_serial_manager_park_sends_one():
    sm = _bare_manager()
    assert sm.park() is True
    sm.execute_set_command.assert_called_once_with(SetCommand.PARK_UNPARK, struct.pack('<B', 1), None)


def test_serial_manager_unpark_sends_zero():
    sm = _bare_manager()
    assert sm.unpark() is True
    sm.execute_set_command.assert_called_once_with(SetCommand.PARK_UNPARK, struct.pack('<B', 0), None)
