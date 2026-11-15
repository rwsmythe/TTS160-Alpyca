# -*- coding: utf-8 -*-
"""Driver fix arc 2026-11, FIX 1 (review finding F-X-0001).

Firmware 357 does not implement the extended LX200 getters ``:*Gt#`` / ``:*Gg#``
/ ``:*Gr#`` / ``:*Gd#`` (it NAKs them), so the site and target getters -- and the
connect sequence, which reads the site through ``_sync_site_coordinates_from_mount``
-- must read the v357 binary variables instead:

  C18 C_LATITUDE   float32 radians, north-positive (firmware sign 1 = South)
  C17 C_LONGITUDE  float32 radians in the firmware's arithmetic convention,
                   West-positive -> ASCOM SiteLongitude = -degrees(C17)
                   (CHARC ruling (a); F-FW-0722 stays a firmware defect)
  L9  L_OBJECT_RA  float32 radians -> hours = (degrees / 15) mod 24
  L10 L_OBJECT_DEC float32 radians -> degrees

The fake mount below answers ONLY the binary query ``:*!G ...#`` and NAKs every
``:*G`` text getter, the way the pinned firmware does.  The real
``SerialManager.query_variables`` / ``_map_query_result`` run against it.
"""

import math
import threading
import types
from unittest.mock import Mock

import astropy.units as u
import pytest
from astropy.coordinates import EarthLocation

from TTS160Device import TTS160Device
from tts160_serial import SerialManager


class _Nak(Exception):
    """Stands in for the firmware's NAK (0x15) of an unimplemented text command."""


class FakeMount357:
    """Serial-manager double: binary variable queries answered, ``:*G`` text NAKed."""

    def __init__(self, values):
        self.values = dict(values)
        self.sent = []
        self._logger = Mock()
        # the driver's own query path, unchanged
        self.query_variables = types.MethodType(SerialManager.query_variables, self)
        self._map_query_result = types.MethodType(SerialManager._map_query_result, self)

    def send_command(self, command, command_type=None, priority=None):
        self.sent.append(command)
        if command.startswith(':*!G ') and command.endswith('#'):
            names = command[len(':*!G '):-1].split(',')
            return [self.values[n] for n in names]
        if command.startswith(':*G'):
            raise _Nak('NAK 0x15 for %s' % command)
        raise AssertionError('unexpected command %r' % command)


def _device(mount, connected=True, connecting=False):
    dev = TTS160Device.__new__(TTS160Device)
    dev._logger = Mock()
    dev._lock = threading.RLock()
    dev._serial_manager = mount
    dev._Connected = connected
    dev._Connecting = connecting
    dev._config = Mock(site_elevation=100.0, site_latitude=0.0, site_longitude=0.0)
    dev._site_location = EarthLocation(lat=0.0 * u.deg, lon=0.0 * u.deg, height=100.0 * u.m)
    dev.TTS160_cache = Mock()
    dev._invalidate_cache = Mock()
    return dev


def _no_text_getter(mount):
    return [c for c in mount.sent if c.startswith(':*G')]


# ---------------------------------------------------------------------------
# SiteLatitude <- C18
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('lat_deg', [34.5, -33.875])
def test_site_latitude_reads_c18(lat_deg):
    mount = FakeMount357({'C18': math.radians(lat_deg)})
    dev = _device(mount)

    assert dev.SiteLatitude == pytest.approx(lat_deg)

    assert mount.sent == [':*!G C18#']
    assert _no_text_getter(mount) == []
    # side effects kept: config, site location, cache
    assert dev._config.site_latitude == pytest.approx(lat_deg)
    assert dev._site_location.lat.deg == pytest.approx(lat_deg)
    dev.TTS160_cache.update_property.assert_called_once()
    assert dev.TTS160_cache.update_property.call_args[0][0] == 'SiteLatitude'


# ---------------------------------------------------------------------------
# SiteLongitude <- -degrees(C17)   (firmware arithmetic convention, West-positive)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('c17_deg, ascom_deg', [
    (111.5, -111.5),     # handpad-entered WEST site: stored sign 0 -> C17 > 0 -> ASCOM west (negative)
    (-151.25, 151.25),   # handpad-entered EAST site: stored sign 1 -> C17 < 0 -> ASCOM east (positive)
])
def test_site_longitude_reads_c17_west_positive(c17_deg, ascom_deg):
    mount = FakeMount357({'C17': math.radians(c17_deg)})
    dev = _device(mount)

    assert dev.SiteLongitude == pytest.approx(ascom_deg)

    assert mount.sent == [':*!G C17#']
    assert _no_text_getter(mount) == []
    assert dev._config.site_longitude == pytest.approx(ascom_deg)
    assert dev._site_location.lon.deg == pytest.approx(ascom_deg)
    dev.TTS160_cache.update_property.assert_called_once()
    assert dev.TTS160_cache.update_property.call_args[0][0] == 'SiteLongitude'


def test_site_getters_still_guard_disconnected():
    mount = FakeMount357({'C17': 0.0, 'C18': 0.0})
    dev = _device(mount, connected=False, connecting=False)
    with pytest.raises(ConnectionError):
        dev.SiteLatitude
    with pytest.raises(ConnectionError):
        dev.SiteLongitude
    assert mount.sent == []


def test_site_getter_query_failure_is_wrapped():
    mount = FakeMount357({})  # the query raises (KeyError in the fake) -> wrapped as before
    dev = _device(mount)
    with pytest.raises(RuntimeError):
        dev.SiteLatitude
    with pytest.raises(RuntimeError):
        dev.SiteLongitude


# ---------------------------------------------------------------------------
# TargetRightAscension <- L9, TargetDeclination <- L10
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('ra_hours', [5.5, 23.75])
def test_target_right_ascension_reads_l9(ra_hours):
    mount = FakeMount357({'L9': math.radians(ra_hours * 15.0)})
    dev = _device(mount)

    assert dev.TargetRightAscension == pytest.approx(ra_hours)

    assert mount.sent == [':*!G L9#']
    assert _no_text_getter(mount) == []
    dev.TTS160_cache.update_property.assert_called_once()
    assert dev.TTS160_cache.update_property.call_args[0][0] == 'TargetRightAscension'


def test_target_right_ascension_wraps_negative_radians():
    # hms_to_rad of a value the firmware holds with a sign bit can come back negative
    mount = FakeMount357({'L9': -math.radians(15.0)})  # -1 h
    dev = _device(mount)
    assert dev.TargetRightAscension == pytest.approx(23.0)


@pytest.mark.parametrize('dec_deg', [41.25, -30.5])
def test_target_declination_reads_l10(dec_deg):
    mount = FakeMount357({'L10': math.radians(dec_deg)})
    dev = _device(mount)

    assert dev.TargetDeclination == pytest.approx(dec_deg)

    assert mount.sent == [':*!G L10#']
    assert _no_text_getter(mount) == []
    dev.TTS160_cache.update_property.assert_called_once()
    assert dev.TTS160_cache.update_property.call_args[0][0] == 'TargetDeclination'


# ---------------------------------------------------------------------------
# Connect: the site sync succeeds against a mount that answers only binary
# ---------------------------------------------------------------------------

def test_connect_site_sync_succeeds_binary_only():
    """``_sync_site_coordinates_from_mount`` (Connect step) against the NAKing fake.

    At 8a136fc this raised: SiteLatitude sent ``:*Gt#`` and the firmware NAKs it.
    """
    lat, west_c17 = 34.5, 111.5
    mount = FakeMount357({'C18': math.radians(lat), 'C17': math.radians(west_c17)})
    dev = _device(mount, connected=False, connecting=True)  # Connect runs with _Connecting set

    dev._sync_site_coordinates_from_mount()

    assert _no_text_getter(mount) == []
    assert mount.sent == [':*!G C18#', ':*!G C17#']
    assert dev._config.site_latitude == pytest.approx(lat)
    assert dev._config.site_longitude == pytest.approx(-west_c17)
    dev._config.save.assert_called()
    assert dev._site_location.lat.deg == pytest.approx(lat)
    assert dev._site_location.lon.deg == pytest.approx(-west_c17)
    assert dev._site_location.height.value == pytest.approx(100.0)
