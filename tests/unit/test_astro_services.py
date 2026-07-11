# -*- coding: utf-8 -*-
"""Unit tests for the astro_services astrometry layer (Phase A foundation).

Grounds the brief's requirements (docs/briefs/tts160-astro-services-a.md):

  * local_sidereal_time is Local APPARENT sidereal time, validated against an
    independent astropy reference AND a known almanac value.
  * icrs_to_jnow / jnow_to_icrs are of-date (TETE) conversions, validated by an
    exact round-trip and against a direct astropy computation.
  * explicit-time discipline: the epoch transforms require an explicit time;
    the only sanctioned Time.now() default path is local_sidereal_time.
  * the SiderealTime ASCOM property returns the service value (fixed time+site).
"""

import inspect
import math
import threading
from unittest.mock import Mock

import numpy as np
import pytest

from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, ICRS, TETE
from astropy import units as u

import astro_services
from astro_services import AstroServices, TimestampedPosition


# Fixed site (Boulder-ish) + fixed epoch used throughout.
SITE = EarthLocation(lat=40.0 * u.deg, lon=-105.0 * u.deg, height=1600.0 * u.m)
FIXED_T = Time("2026-07-10T04:00:00", scale="utc")


def _service(location=SITE):
    return AstroServices(location_provider=lambda: location, logger=Mock())


# ---------------------------------------------------------------------------
# Sidereal time
# ---------------------------------------------------------------------------

class TestLocalSiderealTime:
    def test_matches_astropy_apparent_reference(self):
        """Service LST equals an independent astropy apparent-LST computation."""
        svc = _service()
        got = svc.local_sidereal_time(FIXED_T)
        ref = FIXED_T.sidereal_time("apparent", longitude=SITE.lon).hour % 24.0
        assert got == pytest.approx(ref, abs=1e-9)

    def test_is_apparent_not_mean(self):
        """The service uses the 'apparent' model (differs from 'mean')."""
        svc = _service()
        got = svc.local_sidereal_time(FIXED_T)
        mean = FIXED_T.sidereal_time("mean", longitude=SITE.lon).hour % 24.0
        # equation of the equinoxes is nonzero (~arcsec) but small
        assert abs(got - mean) > 1e-6
        assert abs(got - mean) < 1e-3

    def test_known_almanac_value_greenwich_j2000(self):
        """Greenwich apparent LST at 2000-01-01 00:00 UTC ~ GMST 6h39m52.27s.

        The Astronomical Almanac gives GMST at that instant = 6h39m52.27s
        (6.6645194 h). Apparent LST at Greenwich should agree to well within a
        sidereal-minute (equation of equinoxes + DUT1 are sub-second here).
        """
        gw = EarthLocation(lat=51.0 * u.deg, lon=0.0 * u.deg, height=0.0 * u.m)
        svc = _service(location=gw)
        t = Time("2000-01-01T00:00:00", scale="utc")
        got = svc.local_sidereal_time(t)
        almanac_gmst = 6.0 + 39.0 / 60.0 + 52.27 / 3600.0  # 6.6645194 h
        assert got == pytest.approx(almanac_gmst, abs=1e-3)

    def test_normalised_range(self):
        svc = _service()
        for iso in ("2026-01-01T00:00:00", "2026-06-30T18:00:00",
                    "2026-12-31T23:59:59"):
            lst = svc.local_sidereal_time(Time(iso, scale="utc"))
            assert 0.0 <= lst < 24.0

    def test_default_path_uses_now(self, monkeypatch):
        """t=None resolves to Time.now() (the one sanctioned default path)."""
        monkeypatch.setattr(astro_services.Time, "now",
                            classmethod(lambda cls: FIXED_T))
        svc = _service()
        got = svc.local_sidereal_time()  # no explicit time -> now() == FIXED_T
        ref = FIXED_T.sidereal_time("apparent", longitude=SITE.lon).hour % 24.0
        assert got == pytest.approx(ref, abs=1e-9)

    def test_missing_location_raises(self):
        svc = AstroServices(location_provider=lambda: None, logger=Mock())
        with pytest.raises(ValueError):
            svc.local_sidereal_time(FIXED_T)

    def test_location_provider_tracks_runtime_change(self):
        """Held as a provider (not a snapshot): a site change is reflected."""
        box = {"loc": SITE}
        svc = AstroServices(location_provider=lambda: box["loc"], logger=Mock())
        first = svc.local_sidereal_time(FIXED_T)
        box["loc"] = EarthLocation(lat=40.0 * u.deg, lon=0.0 * u.deg,
                                   height=0.0 * u.m)
        second = svc.local_sidereal_time(FIXED_T)
        # 105 deg west == 7 h of LST difference
        assert (first - second) % 24.0 == pytest.approx(-7.0 % 24.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Epoch conversions (ICRS <-> JNOW/TETE)
# ---------------------------------------------------------------------------

class TestEpochConversions:
    def test_icrs_to_jnow_matches_direct_astropy(self):
        svc = _service()
        ra, dec = 10.0, 20.0
        got_ra, got_dec = svc.icrs_to_jnow(ra, dec, FIXED_T)
        direct = SkyCoord(ra=ra * u.hourangle, dec=dec * u.deg,
                          frame=ICRS()).transform_to(TETE(obstime=FIXED_T))
        assert got_ra == pytest.approx(direct.ra.hour % 24.0, abs=1e-9)
        assert got_dec == pytest.approx(direct.dec.degree, abs=1e-9)

    def test_round_trip_icrs_jnow_icrs(self):
        svc = _service()
        for ra, dec in [(0.0, 0.0), (6.0, 45.0), (18.0, -30.0), (23.5, 80.0)]:
            jra, jdec = svc.icrs_to_jnow(ra, dec, FIXED_T)
            bra, bdec = svc.jnow_to_icrs(jra, jdec, FIXED_T)
            assert bra == pytest.approx(ra, abs=1e-6)
            assert bdec == pytest.approx(dec, abs=1e-6)

    def test_of_date_shift_is_precession_scale(self):
        """ICRS->JNOW at 2026 moves a mid-sky point by the precession scale
        (~1300 arcsec) -- i.e. the AM4/F2 bias the conversion exists to remove."""
        svc = _service()
        ra, dec = 10.0, 20.0
        jra, jdec = svc.icrs_to_jnow(ra, dec, FIXED_T)
        dra = (jra - ra) * 3600.0 * 15.0 * math.cos(math.radians(dec))
        ddec = (jdec - dec) * 3600.0
        total = math.hypot(dra, ddec)
        assert 1000.0 < total < 1600.0

    def test_jnow_to_icrs_matches_direct_astropy(self):
        svc = _service()
        ra, dec = 4.0, -10.0
        got_ra, got_dec = svc.jnow_to_icrs(ra, dec, FIXED_T)
        direct = SkyCoord(ra=ra * u.hourangle, dec=dec * u.deg,
                          frame=TETE(obstime=FIXED_T)).transform_to(ICRS())
        assert got_ra == pytest.approx(direct.ra.hour % 24.0, abs=1e-9)
        assert got_dec == pytest.approx(direct.dec.degree, abs=1e-9)

    def test_accepts_datetime_and_time_equivalently(self):
        from datetime import datetime, timezone
        svc = _service()
        dt = datetime(2026, 7, 10, 4, 0, 0, tzinfo=timezone.utc)
        a = svc.icrs_to_jnow(10.0, 20.0, dt)
        b = svc.icrs_to_jnow(10.0, 20.0, FIXED_T)
        assert a[0] == pytest.approx(b[0], abs=1e-9)
        assert a[1] == pytest.approx(b[1], abs=1e-9)


# ---------------------------------------------------------------------------
# Explicit-time discipline
# ---------------------------------------------------------------------------

class TestExplicitTimeDiscipline:
    def test_epoch_transforms_require_explicit_time(self):
        """t must be a required argument on both epoch transforms."""
        for name in ("icrs_to_jnow", "jnow_to_icrs"):
            sig = inspect.signature(getattr(AstroServices, name))
            assert sig.parameters["t"].default is inspect.Parameter.empty, name

    def test_sidereal_time_default_is_none(self):
        sig = inspect.signature(AstroServices.local_sidereal_time)
        assert sig.parameters["t"].default is None

    def test_now_lives_only_in_coerce_time(self):
        """The executable Time.now() lives only in the sanctioned default path
        (_coerce_time); no transform buries a hidden 'now'."""
        # the default-path helper owns the only now()
        assert "Time.now()" in inspect.getsource(astro_services._coerce_time)
        # neither epoch transform nor the LST method calls now() directly
        for fn in (AstroServices.icrs_to_jnow, AstroServices.jnow_to_icrs,
                   AstroServices.local_sidereal_time):
            assert "Time.now()" not in inspect.getsource(fn), fn.__name__
        # no datetime.now anywhere in the module source
        assert "datetime.now" not in inspect.getsource(astro_services)


# ---------------------------------------------------------------------------
# TimestampedPosition primitive
# ---------------------------------------------------------------------------

class TestTimestampedPosition:
    def test_carries_value_and_timestamp(self):
        tp = TimestampedPosition(value=(10.0, 20.0), timestamp=FIXED_T)
        assert tp.value == (10.0, 20.0)
        assert tp.timestamp is FIXED_T

    def test_at_coerces_time(self):
        from datetime import datetime, timezone
        dt = datetime(2026, 7, 10, 4, 0, 0, tzinfo=timezone.utc)
        tp = TimestampedPosition.at((1.0, 2.0), dt)
        assert isinstance(tp.timestamp, Time)
        assert tp.value == (1.0, 2.0)

    def test_is_frozen(self):
        tp = TimestampedPosition.at(5.0, FIXED_T)
        with pytest.raises(Exception):
            tp.value = 6.0


# ---------------------------------------------------------------------------
# SiderealTime ASCOM property returns the service value
# ---------------------------------------------------------------------------

class TestSiderealTimePropertyDelegation:
    def _device(self, monkeypatch):
        from TTS160Device import TTS160Device
        dev = TTS160Device.__new__(TTS160Device)
        dev._logger = Mock()
        dev._lock = threading.RLock()
        dev._Connected = True
        dev._Connecting = False
        dev._site_location = SITE
        dev.TTS160_cache = Mock()
        dev._astro_services = AstroServices(
            location_provider=lambda: dev._site_location, logger=Mock())
        # pin "now" so the property (which uses the default path) is deterministic
        monkeypatch.setattr(astro_services.Time, "now",
                            classmethod(lambda cls: FIXED_T))
        return dev

    def test_property_returns_service_value(self, monkeypatch):
        dev = self._device(monkeypatch)
        expected = FIXED_T.sidereal_time("apparent", longitude=SITE.lon).hour % 24.0
        assert dev.SiderealTime == pytest.approx(expected, abs=1e-9)

    def test_property_does_not_query_mount(self, monkeypatch):
        """The ASCOM value no longer routes through the mount :GS# path."""
        dev = self._device(monkeypatch)
        dev._send_command = Mock(side_effect=AssertionError("must not hit mount"))
        _ = dev.SiderealTime  # would raise if it sent :GS#
        dev._send_command.assert_not_called()

    def test_calculate_sidereal_time_delegates_to_service(self, monkeypatch):
        dev = self._device(monkeypatch)
        got = dev._calculate_sidereal_time(FIXED_T)
        assert got == pytest.approx(dev._astro_services.local_sidereal_time(FIXED_T),
                                    abs=1e-9)

    def test_disconnected_raises(self, monkeypatch):
        dev = self._device(monkeypatch)
        dev._Connected = False
        dev._Connecting = False
        with pytest.raises(ConnectionError):
            _ = dev.SiderealTime
