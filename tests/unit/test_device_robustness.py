# -*- coding: utf-8 -*-
"""Unit tests for the Fix Arc 4 driver robustness bundle.

Covers the grounded defects fixed in this arc (see the harness review registers
docs/reviews/tts160-device-findings.md and tts160-alignment-findings.md):

  - D1  : DeviceState maps DEC<-T17 and RA<-T16 and queries the correct variables
          (the prior "T18,17" resolved -- via firmware category stickiness -- to
          TARGET_RA and DEC, swapping the two equatorial fields).
  - D2  : _slew_status_monitor clears _goto_in_progress on the serial-error path
          (previously it leaked True and permanently blocked MoveAxis/FindHome).
  - D12 : ConnectedSet raises instead of hanging forever on a failed async connect.
  - A1  : SideOfPier / DestinationSideOfPier report pierUnknown on the alt-az mount.

These are method-level tests: they build a TTS160Device via __new__ (bypassing the
heavy __init__) and inject only the attributes each method under test touches.
"""

import math
import threading
from unittest.mock import Mock, PropertyMock, patch

import pytest

from TTS160Device import TTS160Device
from tts160_types import CommandType
from telescope import PierSide


def _bare_device():
    """A TTS160Device with __init__ bypassed (no serial / no threads)."""
    dev = TTS160Device.__new__(TTS160Device)
    dev._logger = Mock()
    dev._lock = threading.RLock()
    return dev


# ---------------------------------------------------------------------------
# D1 -- DeviceState field mapping
# ---------------------------------------------------------------------------

class TestDeviceStateMapping:
    def test_query_uses_dec_then_ra_variables(self):
        """The bulk query must request X1,C5,X2,T17(DEC),T16(RA) -- not T18,17."""
        dev = _bare_device()
        dev.TTS160_cache = Mock()
        # data order follows the query: [X1=alt, C5=park, X2=az, T17=dec, T16=ra]
        dev._send_command = Mock(return_value=[0.0, 0.0, 0.0, 0.0, 0.0])

        props = ['AtHome', 'IsPulseGuiding', 'SideOfPier', 'SiderealTime',
                 'Slewing', 'Tracking', 'UTCDate']
        with _patch_props(dev, props):
            dev.DeviceState

        sent_cmd = dev._send_command.call_args[0][0]
        sent_type = dev._send_command.call_args[0][1]
        assert sent_cmd == ":*!G X1,C5,X2,T17,T16#"
        assert sent_type == CommandType.AUTO
        # regression guard: the two off-by-one bugs must be gone
        assert "T18" not in sent_cmd
        assert ",17#" not in sent_cmd and ",17," not in sent_cmd

    def test_dec_and_ra_land_in_correct_fields(self):
        """data[3]=T17 -> Declination(deg); data[4]=T16 -> RightAscension(hours)."""
        dev = _bare_device()
        dev.TTS160_cache = Mock()
        dec_rad = math.radians(45.0)   # +45 deg declination
        ra_rad = math.radians(45.0)    # 45 deg = 3 hours of RA
        dev._send_command = Mock(return_value=[0.0, 0.0, 0.0, dec_rad, ra_rad])

        props = ['AtHome', 'IsPulseGuiding', 'SideOfPier', 'SiderealTime',
                 'Slewing', 'Tracking', 'UTCDate']
        with _patch_props(dev, props):
            state = dev.DeviceState

        values = {item["name"]: item["value"] for item in state}
        assert values["Declination"] == pytest.approx(45.0)
        assert values["RightAscension"] == pytest.approx(3.0)


def _patch_props(dev, names):
    """Context manager patching a list of TTS160Device properties to Mocks."""
    from contextlib import ExitStack
    stack = ExitStack()
    for name in names:
        stack.enter_context(
            patch.object(type(dev), name, new_callable=PropertyMock,
                         return_value=False))
    return stack


# ---------------------------------------------------------------------------
# D2 -- _slew_status_monitor must not leak _goto_in_progress on a serial error
# ---------------------------------------------------------------------------

class TestSlewMonitorErrorPath:
    def test_goto_flag_cleared_on_serial_error(self):
        dev = _bare_device()
        dev._goto_in_progress = True
        dev._slewing_hold = True
        dev._config = Mock(slew_settle_time=0)
        # The :D# poll raises a transport error.
        dev._send_command = Mock(side_effect=RuntimeError("serial boom"))

        with pytest.raises(RuntimeError):
            dev._slew_status_monitor()

        # Pre-fix: the exception skipped the reset and left _goto_in_progress=True,
        # permanently blocking MoveAxis/FindHome. The try/finally must clear both.
        assert dev._goto_in_progress is False
        assert dev._slewing_hold is False

    def test_goto_flag_cleared_on_normal_completion(self):
        dev = _bare_device()
        dev._goto_in_progress = True
        dev._slewing_hold = True
        dev._config = Mock(slew_settle_time=0)
        # First poll reports "still slewing", second reports "done".
        dev._send_command = Mock(side_effect=["|#", "done#"])

        dev._slew_status_monitor()

        assert dev._goto_in_progress is False
        assert dev._slewing_hold is False


# ---------------------------------------------------------------------------
# D12 -- ConnectedSet must not hang on a failed async connect
# ---------------------------------------------------------------------------

class TestConnectedSetTimeout:
    def test_raises_when_connect_fails(self):
        """Connecting cleared without Connected -> raise, do not spin forever."""
        dev = _bare_device()
        dev._Connected = False
        dev._Connecting = False   # async connect already finished, unsuccessfully
        dev._config = Mock(dev_port="COM5")
        dev.Connect = Mock()      # returns immediately, sets nothing

        with pytest.raises(RuntimeError):
            dev.ConnectedSet(True, {"1": "addr"})
        dev.Connect.assert_called_once()

    def test_raises_on_timeout(self):
        """Connecting stuck True past the deadline -> timeout raise, no hang."""
        dev = _bare_device()
        dev._Connected = False
        dev._Connecting = True    # never completes
        dev._config = Mock(dev_port="COM5")
        dev.Connect = Mock()
        dev.CONNECT_TIMEOUT_SEC = 0.0   # deadline is immediate

        with pytest.raises(RuntimeError):
            dev.ConnectedSet(True, {"1": "addr"})


# ---------------------------------------------------------------------------
# A1 -- SideOfPier conformance on the alt-az mount
# ---------------------------------------------------------------------------

class TestSideOfPierAltAz:
    def test_side_of_pier_is_unknown(self):
        dev = _bare_device()
        dev.TTS160_cache = Mock()
        assert dev.SideOfPier == PierSide.pierUnknown

    def test_destination_side_of_pier_is_unknown(self):
        dev = _bare_device()
        dev._validate_coordinates = Mock()
        assert dev.DestinationSideOfPier(3.0, 45.0) == PierSide.pierUnknown
