# -*- coding: utf-8 -*-
"""
State Management for TTS160 GUI

Reactive state container for UI updates using NiceGUI's reactive system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import threading


class DisclosureLevel(Enum):
    """Progressive disclosure levels."""
    BASIC = 1      # Essential controls and status
    EXPANDED = 2   # Additional details
    ADVANCED = 3   # Diagnostics and debugging


class AlignmentState(Enum):
    """Alignment monitor states."""
    DISABLED = "disabled"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CAPTURING = "capturing"
    SOLVING = "solving"
    MONITORING = "monitoring"
    ERROR = "error"


class DecisionResult(Enum):
    """Alignment decision results."""
    NONE = "none"
    NO_ACTION = "no_action"
    SYNC = "sync"
    ALIGN = "align"
    LOCKOUT = "lockout"
    ERROR = "error"


@dataclass
class TelescopeState:
    """Reactive state container for telescope data.

    All fields trigger UI updates when modified through the update() method.
    """

    # Connection status
    connected: bool = False
    connection_error: Optional[str] = None
    serial_port: str = ""
    last_communication: Optional[datetime] = None

    # Position (updated at 1-2 Hz)
    ra_hours: float = 0.0
    dec_degrees: float = 0.0
    alt_degrees: float = 0.0
    az_degrees: float = 0.0
    sidereal_time: float = 0.0
    pier_side: str = "unknown"  # "east", "west", "unknown"

    # Tracking
    tracking_enabled: bool = False
    tracking_rate: str = "sidereal"  # "sidereal", "lunar", "solar", "king"
    slewing: bool = False
    slew_settling: bool = False

    # Hardware status
    at_park: bool = False
    at_home: bool = False
    motors_enabled: bool = False

    # GPS status
    gps_enabled: bool = False
    gps_fix: bool = False
    gps_satellites: int = 0
    gps_latitude: float = 0.0
    gps_longitude: float = 0.0
    gps_altitude: float = 0.0

    # Alignment monitor
    alignment_state: AlignmentState = AlignmentState.DISABLED
    alignment_error_arcsec: float = 0.0
    alignment_error_ra: float = 0.0
    alignment_error_dec: float = 0.0
    geometry_determinant: float = 0.0
    last_decision: DecisionResult = DecisionResult.NONE
    lockout_remaining_sec: float = 0.0
    health_alert: bool = False
    camera_source: str = "alpaca"

    # UI state
    current_theme: str = "dark"
    disclosure_level: DisclosureLevel = DisclosureLevel.BASIC

    # Data freshness
    last_update: Optional[datetime] = None
    is_stale: bool = False

    def __post_init__(self):
        """Initialize internal state."""
        self._lock = threading.RLock()
        self._listeners: List[Callable[[str, Any], None]] = []

    def update(self, **kwargs) -> None:
        """Update state fields and notify listeners.

        Args:
            **kwargs: Field names and new values.
        """
        with self._lock:
            changed_fields = []
            for key, value in kwargs.items():
                if hasattr(self, key):
                    old_value = getattr(self, key)
                    if old_value != value:
                        setattr(self, key, value)
                        changed_fields.append((key, value))

            if changed_fields:
                self.last_update = datetime.now()
                self.is_stale = False

                # Notify listeners
                for field_name, new_value in changed_fields:
                    for listener in self._listeners:
                        try:
                            listener(field_name, new_value)
                        except Exception:
                            pass  # Don't let listener errors break updates

    def add_listener(self, callback: Callable[[str, Any], None]) -> None:
        """Add a state change listener.

        Args:
            callback: Function called with (field_name, new_value) on changes.
        """
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str, Any], None]) -> None:
        """Remove a state change listener.

        Args:
            callback: Previously registered callback.
        """
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def get_position_dict(self) -> Dict[str, float]:
        """Get position data as dictionary.

        Returns:
            Dict with ra_hours, dec_degrees, alt_degrees, az_degrees.
        """
        with self._lock:
            return {
                'ra_hours': self.ra_hours,
                'dec_degrees': self.dec_degrees,
                'alt_degrees': self.alt_degrees,
                'az_degrees': self.az_degrees,
                'sidereal_time': self.sidereal_time,
            }

    def get_status_dict(self) -> Dict[str, Any]:
        """Get status data as dictionary.

        Returns:
            Dict with connection, tracking, and hardware status.
        """
        with self._lock:
            return {
                'connected': self.connected,
                'tracking_enabled': self.tracking_enabled,
                'tracking_rate': self.tracking_rate,
                'slewing': self.slewing,
                'at_park': self.at_park,
                'at_home': self.at_home,
                'pier_side': self.pier_side,
            }

    def get_alignment_dict(self) -> Dict[str, Any]:
        """Get alignment data as dictionary.

        Returns:
            Dict with alignment monitor status.
        """
        with self._lock:
            return {
                'state': self.alignment_state.value,
                'error_arcsec': self.alignment_error_arcsec,
                'error_ra': self.alignment_error_ra,
                'error_dec': self.alignment_error_dec,
                'geometry_determinant': self.geometry_determinant,
                'last_decision': self.last_decision.value,
                'lockout_remaining': self.lockout_remaining_sec,
                'health_alert': self.health_alert,
            }

    def mark_stale(self, threshold_seconds: float = 5.0) -> bool:
        """Check if data is stale and mark if so.

        Args:
            threshold_seconds: Seconds without update before data is stale.

        Returns:
            True if data is stale.
        """
        with self._lock:
            if self.last_update is None:
                self.is_stale = True
                return True

            age = (datetime.now() - self.last_update).total_seconds()
            self.is_stale = age > threshold_seconds
            return self.is_stale


def create_state() -> TelescopeState:
    """Create a new telescope state instance.

    Returns:
        Fresh TelescopeState with default values.
    """
    return TelescopeState()


# Formatting utilities for display
def format_ra(hours: float) -> str:
    """Format RA in HMS notation.

    Args:
        hours: RA in decimal hours.

    Returns:
        Formatted string like "12h 34m 56.7s"
    """
    h = int(hours)
    m = int((hours - h) * 60)
    s = ((hours - h) * 60 - m) * 60
    return f"{h:02d}h {m:02d}m {s:04.1f}s"


def format_dec(degrees: float) -> str:
    """Format Dec in DMS notation.

    Args:
        degrees: Dec in decimal degrees.

    Returns:
        Formatted string like "+12° 34' 56\""
    """
    sign = "+" if degrees >= 0 else "-"
    degrees = abs(degrees)
    d = int(degrees)
    m = int((degrees - d) * 60)
    s = ((degrees - d) * 60 - m) * 60
    return f"{sign}{d:02d}° {m:02d}' {s:04.1f}\""


def format_angle(degrees: float, precision: int = 1) -> str:
    """Format angle in degrees.

    Args:
        degrees: Angle in decimal degrees.
        precision: Decimal places.

    Returns:
        Formatted string like "123.4°"
    """
    return f"{degrees:.{precision}f}°"


def format_sidereal_time(hours: float) -> str:
    """Format sidereal time.

    Args:
        hours: LST in decimal hours.

    Returns:
        Formatted string like "08h 12m 34s"
    """
    h = int(hours) % 24
    m = int((hours % 1) * 60)
    s = int(((hours % 1) * 60 - m) * 60)
    return f"{h:02d}h {m:02d}m {s:02d}s"


def format_error(arcsec: float) -> str:
    """Format pointing error with appropriate units.

    Args:
        arcsec: Error in arcseconds.

    Returns:
        Formatted string with arcsec or arcmin.
    """
    if abs(arcsec) >= 60:
        return f"{arcsec / 60:.1f}'"
    return f'{arcsec:.1f}"'
