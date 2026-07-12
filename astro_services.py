# File: astro_services.py
"""Authoritative astrometry services for the TTS160 driver.

This module is the SINGLE source of truth for the driver's time/epoch
astrometry.  It exists so that sidereal time and J2000<->of-date epoch
conversions have exactly one implementation (library-delegated to astropy)
rather than being re-derived at each call site.

Responsibilities
----------------
* ``local_sidereal_time`` -- the one and only Local Apparent Sidereal Time
  source, computed from the system clock and the site location.
* ``icrs_to_jnow`` / ``jnow_to_icrs`` -- J2000 ICRS <-> of-date ("JNOW")
  equatorial conversions with library-delegated precession + nutation.
* ``TimestampedPosition`` -- a small ``(value, timestamp)`` carrier plus the
  house convention that every transform takes an EXPLICIT time (no buried
  ``Time.now()``), so a caller can pair a measurement with its own timestamp
  (e.g. an exposure mid-time) instead of "now".

Design note (ownership): an instance is constructed and owned by the Device.
Because the site location can change at runtime (GPS / config updates), the
service holds a *location provider* callable rather than a snapshot, so it
always reads the current ``EarthLocation`` without needing reconstruction.

Frame definitions and accuracy bounds
--------------------------------------
* **Local Apparent Sidereal Time (LAST).**  ASCOM ITelescopeV4 specifies that
  ``Telescope.SiderealTime`` is the *Local Apparent Sidereal Time* in hours
  (see the ASCOM ITelescopeV4 SiderealTime member: "local apparent sidereal
  time").  We therefore use astropy ``Time(...).sidereal_time('apparent',
  longitude)`` -- the ``'apparent'`` model includes the equation of the
  equinoxes (nutation), unlike ``'mean'``.  The mean-vs-apparent difference is
  up to ~1.1 s (~17 arcsec) of the equation of the equinoxes.

* **"JNOW" == astropy TETE (True Equator, True Equinox of date).**  ``JNOW``
  here is the geocentric apparent equatorial frame of date: the ICRS/J2000
  catalog place rotated by the IAU precession + nutation models to the true
  equator and true equinox of ``t`` (astropy delegates the SOFA/ERFA models).
  Reached via GCRS, TETE also carries annual aberration and gravitational
  light deflection, so it is a full geocentric *apparent* place.  The dominant
  of-date term is precession (~50 arcsec/yr); over ~26 years since J2000 the
  ICRS->JNOW shift is ~0.4 deg (quantified: ~1300 arcsec for a mid-sky point at
  2026-07).  Round-tripping ``icrs_to_jnow`` -> ``jnow_to_icrs`` is exact to
  ~1e-9 h.  Not modelled: diurnal aberration and atmospheric refraction (the
  driver applies no refraction -- see ``DoesRefraction``), i.e. this is a
  geocentric, not a topocentric-observed, place.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple, Union

from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, ICRS, TETE, get_body
from astropy import units as u

# A time may be given as an astropy Time, a datetime (naive == UTC), or None
# (LST default path only -> "now").
TimeLike = Union[Time, datetime, None]


@dataclass(frozen=True)
class TimestampedPosition:
    """A value paired with the astropy ``Time`` it was valid at.

    Intentionally value-agnostic: ``value`` may be an ``(ra, dec)`` tuple, an
    alt/az pair, a scalar, etc.  The point of the carrier is to keep the
    measurement bound to an EXPLICIT timestamp so downstream transforms never
    have to guess "when" (and never silently fall back to ``Time.now()``).
    """

    value: Any
    timestamp: Time

    @classmethod
    def at(cls, value: Any, t: TimeLike) -> "TimestampedPosition":
        """Build a carrier, coercing ``t`` to an astropy ``Time`` (t required)."""
        return cls(value=value, timestamp=_coerce_time(t))


def _coerce_time(t: TimeLike) -> Time:
    """Coerce ``t`` to an astropy ``Time``.

    ``None`` resolves to ``Time.now()`` -- this is the ONE sanctioned default
    path in the module.  Transforms pass an explicit ``t`` (required argument),
    so they never reach the ``now()`` branch by default.
    """
    if t is None:
        return Time.now()
    if isinstance(t, Time):
        return t
    if isinstance(t, datetime):
        # astropy treats a naive datetime as UTC and honours tz-aware datetimes.
        return Time(t)
    raise ValueError(
        f"time must be an astropy Time, a datetime, or None; got {type(t)!r}"
    )


class AstroServices:
    """The driver's single astrometry service (owned/constructed by Device)."""

    def __init__(
        self,
        location_provider: Callable[[], EarthLocation],
        logger: Optional[Any] = None,
    ) -> None:
        """
        Args:
            location_provider: zero-arg callable returning the CURRENT site
                ``EarthLocation``.  Held as a callable (not a snapshot) so the
                service tracks runtime site-location changes.
            logger: optional logger for debug tracing.
        """
        if not callable(location_provider):
            raise TypeError("location_provider must be callable")
        self._location_provider = location_provider
        self._logger = logger

    # -- Sidereal time -----------------------------------------------------

    def local_sidereal_time(self, t: TimeLike = None) -> float:
        """Local Apparent Sidereal Time in hours (0-24).

        THE single sidereal-time source for the driver.  ASCOM ITelescopeV4
        defines ``SiderealTime`` as Local Apparent Sidereal Time, so this uses
        astropy's ``'apparent'`` model (precession + nutation) at the site
        longitude.

        Args:
            t: explicit time (astropy ``Time`` or ``datetime``).  ``None`` (the
               default path) uses the system clock -- the only sanctioned
               ``now()`` in this module.

        Returns:
            Local apparent sidereal time in decimal hours, 0 <= lst < 24.
        """
        location = self._location_provider()
        if location is None:
            raise ValueError("site location is not available for sidereal time")
        astro_time = _coerce_time(t)
        lst = astro_time.sidereal_time("apparent", longitude=location.lon).hour
        lst %= 24.0
        if self._logger is not None:
            self._logger.debug(
                f"LAST {lst:.6f}h @ lon {location.lon.degree:.4f} deg, t={astro_time.iso}"
            )
        return lst

    # -- Epoch conversions -------------------------------------------------

    def icrs_to_jnow(self, ra: float, dec: float, t: TimeLike) -> Tuple[float, float]:
        """Convert J2000 ICRS RA/Dec to of-date JNOW (TETE) RA/Dec.

        Args:
            ra: ICRS right ascension in decimal hours (0-24).
            dec: ICRS declination in decimal degrees (-90..+90).
            t: EXPLICIT time defining the of-date epoch (required -- no buried
               ``now()``; pass e.g. an exposure mid-time).

        Returns:
            ``(ra_hours, dec_degrees)`` in the geocentric apparent frame of date
            (True Equator, True Equinox of ``t``).  RA normalised to 0-24.
        """
        astro_time = _coerce_time(t)
        icrs = SkyCoord(ra=ra * u.hourangle, dec=dec * u.deg, frame=ICRS())
        jnow = icrs.transform_to(TETE(obstime=astro_time))
        return jnow.ra.hour % 24.0, jnow.dec.degree

    def jnow_to_icrs(self, ra: float, dec: float, t: TimeLike) -> Tuple[float, float]:
        """Convert of-date JNOW (TETE) RA/Dec back to J2000 ICRS RA/Dec.

        Inverse of :meth:`icrs_to_jnow`; round-trips to ~1e-9 h.

        Args:
            ra: JNOW right ascension in decimal hours (0-24).
            dec: JNOW declination in decimal degrees (-90..+90).
            t: EXPLICIT time defining the of-date epoch (required).

        Returns:
            ``(ra_hours, dec_degrees)`` in J2000 ICRS.  RA normalised to 0-24.
        """
        astro_time = _coerce_time(t)
        jnow = SkyCoord(
            ra=ra * u.hourangle, dec=dec * u.deg, frame=TETE(obstime=astro_time)
        )
        icrs = jnow.transform_to(ICRS())
        return icrs.ra.hour % 24.0, icrs.dec.degree

    # -- FC-1 ephemeris-push source ---------------------------------------

    def sidereal_reference_rad(self, t: TimeLike = None) -> float:
        """Local Apparent Sidereal Time in RADIANS (0 <= lst < 2*pi).

        Thin radian wrapper over :meth:`local_sidereal_time` for the FC-1
        0x14 push, which carries LST in radians.
        """
        return (self.local_sidereal_time(t) * math.pi / 12.0) % (2.0 * math.pi)

    def body_topocentric_of_date(
        self, body: str, t: TimeLike
    ) -> Tuple[float, float]:
        """Topocentric apparent-of-date RA/Dec of a solar-system body, in RADIANS.

        Uses astropy ``get_body`` (observer-located, so light-travel time is
        applied) then transforms into ``TETE`` carrying the site ``location`` --
        a TETE with a location is topocentric, so this applies diurnal parallax
        (critical for the Moon, ~1 deg) and yields the true-equator/true-equinox
        apparent place of date the firmware consumers expect.

        Args:
            body: astropy body name ('sun', 'moon', 'mercury'..'neptune', ...).
            t: EXPLICIT time (astropy ``Time`` or ``datetime``); ``None`` = now.

        Returns:
            ``(ra_rad, dec_rad)`` -- RA normalised to [0, 2*pi).
        """
        location = self._location_provider()
        if location is None:
            raise ValueError("site location is not available for body ephemeris")
        astro_time = _coerce_time(t)
        gcrs = get_body(body, astro_time, location)
        tete = gcrs.transform_to(TETE(obstime=astro_time, location=location))
        ra = float(tete.ra.radian) % (2.0 * math.pi)
        return ra, float(tete.dec.radian)

    def body_ephemeris_with_rates(
        self, body: str, t: TimeLike, dt_seconds: float = 60.0
    ) -> Tuple[float, float, float, float]:
        """Topocentric apparent position + RA/Dec rates for an FC-1 body push.

        Position is evaluated at ``t``; rates are a CENTRAL finite difference
        across ``+/- dt_seconds`` (default 60 s), with RA unwrapped across the
        0/2*pi seam so a body straddling the seam yields a small, correct rate.

        Args:
            body: astropy body name.
            t: EXPLICIT time defining the epoch of the returned position.
            dt_seconds: half-step of the central difference (seconds).

        Returns:
            ``(ra_rad, dec_rad, ra_rate_rad_s, dec_rate_rad_s)``.
        """
        astro_time = _coerce_time(t)
        ra0, dec0 = self.body_topocentric_of_date(body, astro_time)
        ra_m, dec_m = self.body_topocentric_of_date(
            body, astro_time - dt_seconds * u.s
        )
        ra_p, dec_p = self.body_topocentric_of_date(
            body, astro_time + dt_seconds * u.s
        )
        two_pi = 2.0 * math.pi
        dra = ra_p - ra_m
        # Unwrap the RA difference into (-pi, pi] so a seam crossing is small.
        while dra > math.pi:
            dra -= two_pi
        while dra <= -math.pi:
            dra += two_pi
        ra_rate = dra / (2.0 * dt_seconds)
        dec_rate = (dec_p - dec_m) / (2.0 * dt_seconds)
        return ra0, dec0, ra_rate, dec_rate


# ---------------------------------------------------------------------------
# FC-1 ephemeris pusher (driver -> mount push cadence)
# ---------------------------------------------------------------------------

# astropy 'builtin' ephemeris supports these solar-system bodies. Pluto (id 9)
# is NOT in the builtin ephemeris, so it is excluded from the default push set
# (the firmware still models it onboard); enable it only with a JPL ephemeris.
_DEFAULT_PUSH_BODIES: Tuple[str, ...] = (
    "sun", "moon", "mercury", "venus", "mars",
    "jupiter", "saturn", "uranus", "neptune",
)

# Body name -> firmware EphemerisBody id (mirrors central/binary.h EPHEM_BODY_*).
_BODY_NAME_TO_ID: Dict[str, int] = {
    "sun": 0, "moon": 1, "mercury": 2, "venus": 3, "mars": 4,
    "jupiter": 5, "saturn": 6, "uranus": 7, "neptune": 8, "pluto": 9,
}


@dataclass
class EphemerisPushConfig:
    """Cadence + kill-switch for the FC-1 ephemeris pusher.

    ``enabled`` DEFAULTS ON -- see the B2.b brief; the default-on choice is
    flagged to the operator. The mount degrades gracefully to onboard values
    if pushes stop, so a driver-side default of ON is safe.
    """

    enabled: bool = True
    lst_interval_s: float = 600.0       # 0x14 sidereal reference: ~10 min
    body_interval_s: float = 120.0      # 0x15 body ephemeris: ~2 min
    bodies: Tuple[str, ...] = _DEFAULT_PUSH_BODIES
    tick_s: float = 1.0                 # thread poll granularity


class EphemerisPusher:
    """Pushes precise time (0x14) + body ephemeris (0x15) to the mount on a cadence.

    Owns its own low-frequency daemon thread. When the sender reports connected
    and ``enabled`` is set, it pushes the sidereal reference every
    ``lst_interval_s`` and each configured body every ``body_interval_s``. Push
    failures are logged and simply retried on the next tick (no storms). A clean
    :meth:`stop` (call it from Disconnect) joins the thread.

    The scheduling core :meth:`poll` is deterministic and side-effect-isolated
    so it can be unit-tested with a mock sender + mock astro service and a fake
    clock -- no real thread, serial link, or astropy call required.
    """

    def __init__(
        self,
        sender: Any,
        astro: "AstroServices",
        config: Optional[EphemerisPushConfig] = None,
        logger: Optional[Any] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """
        Args:
            sender: object exposing ``is_connected`` (bool/property),
                ``push_time_reference(lst_rad)`` and
                ``push_body_ephemeris(body_id, ra, dec, ra_rate, dec_rate)``
                (the SerialManager satisfies this).
            astro: AstroServices instance providing the ephemeris source.
            config: cadence + kill-switch (defaults: enabled, 10 min / 2 min).
            logger: optional logger.
            clock: monotonic time source (injectable for tests).
        """
        self._sender = sender
        self._astro = astro
        self._cfg = config or EphemerisPushConfig()
        self._logger = logger
        self._clock = clock
        self._next_lst = 0.0            # push both immediately on first poll
        self._next_body = 0.0
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # -- lifecycle --------------------------------------------------------

    def start(self) -> bool:
        """Start the daemon push thread. No-op (returns False) when disabled."""
        if not self._cfg.enabled:
            self._log("debug", "ephemeris push disabled by config; not starting")
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop.clear()
        self._next_lst = 0.0
        self._next_body = 0.0
        self._thread = threading.Thread(
            target=self._run, name="tts160-ephemeris-pusher", daemon=True
        )
        self._thread.start()
        self._log("info", "ephemeris pusher started")
        return True

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the thread to stop and join it (safe to call when not running)."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None
        self._log("info", "ephemeris pusher stopped")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- scheduling core (deterministic, unit-testable) -------------------

    def poll(self, now: float) -> None:
        """Push whatever is due at ``now`` (monotonic seconds). Never raises."""
        if not self._cfg.enabled or not self._is_connected():
            return
        if now >= self._next_lst:
            self._safe_push_time_reference()
            self._next_lst = now + self._cfg.lst_interval_s
        if now >= self._next_body:
            self._safe_push_bodies()
            self._next_body = now + self._cfg.body_interval_s

    # -- internals --------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll(self._clock())
            except Exception as exc:  # defensive: the loop must never die
                self._log("error", f"ephemeris poll error: {exc}")
            self._stop.wait(self._cfg.tick_s)

    def _is_connected(self) -> bool:
        try:
            return bool(getattr(self._sender, "is_connected", False))
        except Exception:
            return False

    def _safe_push_time_reference(self) -> None:
        try:
            lst_rad = self._astro.sidereal_reference_rad(None)
            self._sender.push_time_reference(lst_rad)
        except Exception as exc:
            self._log("warning", f"push_time_reference failed (will retry): {exc}")

    def _safe_push_bodies(self) -> None:
        for name in self._cfg.bodies:
            body_id = _BODY_NAME_TO_ID.get(name.lower())
            if body_id is None:
                continue
            try:
                ra, dec, ra_rate, dec_rate = self._astro.body_ephemeris_with_rates(
                    name, None
                )
                self._sender.push_body_ephemeris(body_id, ra, dec, ra_rate, dec_rate)
            except Exception as exc:
                self._log("warning", f"push_body_ephemeris({name}) failed (will retry): {exc}")

    def _log(self, level: str, msg: str) -> None:
        if self._logger is not None:
            getattr(self._logger, level, self._logger.info)(msg)
