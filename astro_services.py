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

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional, Tuple, Union

from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, ICRS, TETE
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
