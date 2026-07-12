"""
Unit tests for the FC-1 ephemeris push (Phase B2.b).

Covers:
  * The wire-frame bytes for SET_TIME_REFERENCE (0x14) and SET_BODY_EPHEMERIS
    (0x15) -- payload layout, RA wrap, and the full :*!S framing.
  * The EphemerisPusher scheduling core (deterministic, mocked sender + astro
    service + fake clock -- no real thread, serial link, or astropy call).

These are pure/mocked tests; no hardware or network required.
"""

import math
import struct
import sys
import os
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tts160_serial import V357Protocol
from tts160_types import SetCommand, EphemerisBody
from astro_services import EphemerisPusher, EphemerisPushConfig, _BODY_NAME_TO_ID


TWO_PI = 2.0 * math.pi


class TestSetCommandIds:
    """The new SET ids match the firmware contract (binary.h)."""

    @pytest.mark.unit
    def test_command_ids(self):
        assert SetCommand.SET_TIME_REFERENCE == 0x14
        assert SetCommand.SET_BODY_EPHEMERIS == 0x15

    @pytest.mark.unit
    def test_body_ids_mirror_firmware(self):
        # 0=Sun, 1=Moon, 2..9 planets (EPHEM_BODY_* in central/binary.h)
        assert EphemerisBody.SUN == 0
        assert EphemerisBody.MOON == 1
        assert EphemerisBody.PLUTO == 9


class TestPackTimeReference:
    """0x14 payload = single float LST (radians), wrapped to [0, 2*pi)."""

    @pytest.mark.unit
    def test_payload_layout(self):
        data = V357Protocol.pack_time_reference(1.2345)
        assert len(data) == 4
        (lst,) = struct.unpack('<f', data)
        assert lst == pytest.approx(1.2345, abs=1e-6)

    @pytest.mark.unit
    def test_ra_style_wrap_positive(self):
        data = V357Protocol.pack_time_reference(TWO_PI + 0.5)
        (lst,) = struct.unpack('<f', data)
        assert lst == pytest.approx(0.5, abs=1e-5)
        assert 0.0 <= lst < TWO_PI

    @pytest.mark.unit
    def test_negative_wraps_into_range(self):
        data = V357Protocol.pack_time_reference(-0.5)
        (lst,) = struct.unpack('<f', data)
        assert 0.0 <= lst < TWO_PI
        assert lst == pytest.approx(TWO_PI - 0.5, abs=1e-5)

    @pytest.mark.unit
    def test_full_frame_bytes(self):
        frame = V357Protocol.build_set_command_bytes(
            SetCommand.SET_TIME_REFERENCE, V357Protocol.pack_time_reference(1.0)
        )
        # :*!S <head>;<len><payload>#  -- head is a base-36 char, len is one byte
        assert frame.startswith(b':*!S ')
        assert frame.endswith(b'#')
        # length byte immediately after ';' equals the 4-byte payload length
        semi = frame.index(b';')
        assert frame[semi + 1] == 4


class TestPackBodyEphemeris:
    """0x15 payload = body_id(uint8) + ra,dec,ra_rate,dec_rate(float)."""

    @pytest.mark.unit
    def test_payload_layout(self):
        data = V357Protocol.pack_body_ephemeris(
            EphemerisBody.MOON, 1.1, -0.3, 1e-4, -2e-5
        )
        assert len(data) == 17
        body_id, ra, dec, ra_rate, dec_rate = struct.unpack('<Bffff', data)
        assert body_id == int(EphemerisBody.MOON)
        assert ra == pytest.approx(1.1, abs=1e-6)
        assert dec == pytest.approx(-0.3, abs=1e-6)
        assert ra_rate == pytest.approx(1e-4, abs=1e-9)
        assert dec_rate == pytest.approx(-2e-5, abs=1e-9)

    @pytest.mark.unit
    def test_ra_wrap(self):
        data = V357Protocol.pack_body_ephemeris(1, TWO_PI + 0.25, 0.0, 0.0, 0.0)
        _, ra, _, _, _ = struct.unpack('<Bffff', data)
        assert 0.0 <= ra < TWO_PI
        assert ra == pytest.approx(0.25, abs=1e-5)

    @pytest.mark.unit
    def test_full_frame_bytes(self):
        payload = V357Protocol.pack_body_ephemeris(2, 0.5, 0.5, 0.0, 0.0)
        frame = V357Protocol.build_set_command_bytes(
            SetCommand.SET_BODY_EPHEMERIS, payload
        )
        assert frame.startswith(b':*!S ')
        assert frame.endswith(b'#')
        semi = frame.index(b';')
        assert frame[semi + 1] == 17


class _FakeAstro:
    """Minimal astro-service stand-in for the pusher scheduler tests."""

    def __init__(self):
        self.lst_calls = 0
        self.body_calls = []

    def sidereal_reference_rad(self, t=None):
        self.lst_calls += 1
        return 1.234

    def body_ephemeris_with_rates(self, body, t=None):
        self.body_calls.append(body)
        return (0.1, 0.2, 1e-4, -1e-5)


class _FakeSender:
    """Serial-manager stand-in capturing the pushes the scheduler emits."""

    def __init__(self, connected=True):
        self.is_connected = connected
        self.time_pushes = []
        self.body_pushes = []

    def push_time_reference(self, lst_rad):
        self.time_pushes.append(lst_rad)
        return (True, 0)

    def push_body_ephemeris(self, body_id, ra, dec, ra_rate, dec_rate):
        self.body_pushes.append((body_id, ra, dec, ra_rate, dec_rate))
        return (True, 0)


def _make_pusher(sender, astro, **cfg_kwargs):
    cfg = EphemerisPushConfig(bodies=("sun", "moon"), **cfg_kwargs)
    return EphemerisPusher(sender=sender, astro=astro, config=cfg)


class TestPusherScheduling:
    """Deterministic scheduling via poll(now) with a fake clock."""

    @pytest.mark.unit
    def test_first_poll_pushes_both(self):
        sender, astro = _FakeSender(), _FakeAstro()
        p = _make_pusher(sender, astro, lst_interval_s=600.0, body_interval_s=120.0)
        p.poll(0.0)
        assert len(sender.time_pushes) == 1
        # one body push per configured body
        assert len(sender.body_pushes) == 2
        assert astro.body_calls == ["sun", "moon"]

    @pytest.mark.unit
    def test_body_cadence_faster_than_lst(self):
        sender, astro = _FakeSender(), _FakeAstro()
        p = _make_pusher(sender, astro, lst_interval_s=600.0, body_interval_s=120.0)
        p.poll(0.0)      # both
        p.poll(60.0)     # nothing due yet
        assert len(sender.time_pushes) == 1
        assert len(sender.body_pushes) == 2
        p.poll(120.0)    # body due, lst not
        assert len(sender.time_pushes) == 1
        assert len(sender.body_pushes) == 4
        p.poll(600.0)    # both due
        assert len(sender.time_pushes) == 2
        assert len(sender.body_pushes) == 6

    @pytest.mark.unit
    def test_no_push_when_disconnected(self):
        sender, astro = _FakeSender(connected=False), _FakeAstro()
        p = _make_pusher(sender, astro)
        p.poll(0.0)
        assert sender.time_pushes == []
        assert sender.body_pushes == []

    @pytest.mark.unit
    def test_disabled_config_never_pushes(self):
        sender, astro = _FakeSender(), _FakeAstro()
        cfg = EphemerisPushConfig(enabled=False)
        p = EphemerisPusher(sender=sender, astro=astro, config=cfg)
        p.poll(0.0)
        assert sender.time_pushes == []
        assert sender.body_pushes == []
        assert p.start() is False  # disabled -> start is a no-op

    @pytest.mark.unit
    def test_push_failure_is_isolated_and_retried(self):
        # A raising sender must not kill the loop; the next-due tick retries.
        sender, astro = _FakeSender(), _FakeAstro()

        def boom(*a, **k):
            raise RuntimeError("serial hiccup")

        sender.push_body_ephemeris = boom
        p = _make_pusher(sender, astro, lst_interval_s=600.0, body_interval_s=120.0)
        p.poll(0.0)  # body push raises internally, swallowed
        # time reference still went out despite the body failure
        assert len(sender.time_pushes) == 1

    @pytest.mark.unit
    def test_default_config_enabled_on(self):
        # The kill-switch defaults ON (flagged to operator).
        assert EphemerisPushConfig().enabled is True

    @pytest.mark.unit
    def test_pluto_excluded_from_default_bodies(self):
        # Builtin astropy ephemeris has no Pluto; default push set omits it.
        assert "pluto" not in EphemerisPushConfig().bodies
        assert _BODY_NAME_TO_ID["pluto"] == 9
