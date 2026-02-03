"""
Alignment Monitor Module

A semi-autonomous subsystem for telescope mount drivers that continuously evaluates
pointing accuracy and alignment model quality, automatically initiating synchronization
or alignment point replacement operations to maintain optimal pointing performance.

This module provides the core decision logic, data structures, and algorithms for
the Alignment Monitor system as specified in the Alignment Monitor Specification v1.0.

Example usage:
    from alignment_monitor import AlignmentMonitor, AlignmentMonitorConfig
    
    config = AlignmentMonitorConfig.from_toml("config.toml")
    monitor = AlignmentMonitor(config, firmware_interface)
    
    # Called after goto settle or on periodic drumbeat
    action = monitor.evaluate(plate_solve_position)

Author: [Your Name]
Version: 1.0
Date: February 2, 2026
"""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Tuple, List, Protocol

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

ARCSEC_PER_RADIAN = 206264.806
"""Conversion factor from radians to arcseconds."""

DEG_TO_RAD = math.pi / 180.0
"""Conversion factor from degrees to radians."""

RAD_TO_DEG = 180.0 / math.pi
"""Conversion factor from radians to degrees."""


# =============================================================================
# Enumerations
# =============================================================================

class MonitorAction(Enum):
    """Actions that the Alignment Monitor can take."""
    
    NO_ACTION = auto()
    """No action required; pointing is acceptable."""
    
    SYNC = auto()
    """Synchronization performed to correct transient offset."""
    
    ALIGN = auto()
    """Alignment point replaced to improve model."""


class EvaluationSkipReason(Enum):
    """Reasons why an evaluation cycle may be skipped."""
    
    IN_LOCKOUT = auto()
    """Currently in post-action lockout period."""
    
    MOUNT_NOT_STATIC = auto()
    """Mount is slewing or otherwise not stable."""
    
    PLATE_SOLVE_UNAVAILABLE = auto()
    """No valid plate solve data available."""
    
    PLATE_SOLVE_STALE = auto()
    """Plate solve data is too old."""


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class EquatorialCoord:
    """
    Equatorial coordinate pair.
    
    Attributes:
        ra: Right ascension in radians.
        dec: Declination in radians.
    """
    ra: float
    dec: float
    
    def to_unit_vector(self) -> Tuple[float, float, float]:
        """
        Convert to unit direction vector.
        
        Returns:
            Tuple (x, y, z) representing the unit vector pointing to this coordinate.
        """
        cos_dec = math.cos(self.dec)
        return (
            cos_dec * math.cos(self.ra),
            cos_dec * math.sin(self.ra),
            math.sin(self.dec)
        )


@dataclass
class HorizontalCoord:
    """
    Horizontal (alt-az) coordinate pair.
    
    Attributes:
        alt: Altitude in radians.
        az: Azimuth in radians (north-referenced).
    """
    alt: float
    az: float
    
    def to_unit_vector(self) -> Tuple[float, float, float]:
        """
        Convert to unit direction vector.
        
        Returns:
            Tuple (x, y, z) representing the unit vector pointing to this coordinate.
        """
        cos_alt = math.cos(self.alt)
        return (
            cos_alt * math.cos(self.az),
            cos_alt * math.sin(self.az),
            math.sin(self.alt)
        )


@dataclass
class EncoderTicks:
    """
    Mount encoder tick counts.
    
    Attributes:
        h_ticks: Horizontal (azimuth) axis encoder ticks.
        e_ticks: Elevation (altitude) axis encoder ticks.
    """
    h_ticks: int
    e_ticks: int


@dataclass
class AlignmentPoint:
    """
    Record of a single alignment point.
    
    Attributes:
        index: Point index (1, 2, or 3).
        equatorial: Equatorial coordinates at capture time.
        ticks: Encoder tick values at capture time.
        timestamp: When the point was captured.
        manual: True if user-selected, False if auto-captured.
        weighted_error_sum: Accumulated weighted pointing error (arcseconds).
        weighted_error_weight: Accumulated weight for error calculation.
    """
    index: int
    equatorial: EquatorialCoord
    ticks: EncoderTicks
    timestamp: datetime
    manual: bool = True
    weighted_error_sum: float = 0.0
    weighted_error_weight: float = 0.0
    
    @property
    def mean_weighted_error(self) -> float:
        """
        Calculate mean weighted error for this point.
        
        Returns:
            Mean weighted error in arcseconds, or 0.0 if no observations recorded.
        """
        if self.weighted_error_weight > 0:
            return self.weighted_error_sum / self.weighted_error_weight
        return 0.0
    
    def reset_weighted_error(self) -> None:
        """Reset the weighted error accumulators to zero."""
        self.weighted_error_sum = 0.0
        self.weighted_error_weight = 0.0
    
    def update_weighted_error(
        self, 
        current_position: EquatorialCoord, 
        pointing_error_arcsec: float,
        scale_radius_deg: float
    ) -> None:
        """
        Update weighted error accumulator based on a new observation.
        
        The weight is calculated using an inverse-square falloff based on the
        angular distance from the current observation position to this alignment
        point. Observations closer to this point contribute more to its error metric.
        
        Args:
            current_position: Current mount position where error was observed.
            pointing_error_arcsec: Observed pointing error in arcseconds.
            scale_radius_deg: Distance scale for weight falloff in degrees.
        """
        distance_rad = angular_separation(current_position, self.equatorial)
        distance_deg = distance_rad * RAD_TO_DEG
        
        # Inverse-square weight falloff
        weight = 1.0 / (1.0 + (distance_deg / scale_radius_deg) ** 2)
        
        self.weighted_error_sum += weight * pointing_error_arcsec
        self.weighted_error_weight += weight


@dataclass
class SyncOffsetTracker:
    """
    Tracks cumulative sync adjustments for evaluation consistency.
    
    When syncs are performed, they shift the mount's reported position without
    modifying the alignment model. This tracker maintains the cumulative offset
    so that pointing error evaluation remains consistent across syncs.
    
    Attributes:
        cumulative_h_ticks: Total H-axis sync adjustments since last alignment.
        cumulative_e_ticks: Total E-axis sync adjustments since last alignment.
        last_reset: Timestamp of last reset (at alignment).
    """
    cumulative_h_ticks: int = 0
    cumulative_e_ticks: int = 0
    last_reset: Optional[datetime] = None
    
    def record_sync(self, h_delta: int, e_delta: int) -> None:
        """
        Record a sync adjustment.
        
        Args:
            h_delta: Change in H-axis ticks from sync.
            e_delta: Change in E-axis ticks from sync.
        """
        self.cumulative_h_ticks += h_delta
        self.cumulative_e_ticks += e_delta
        logger.debug(
            f"Sync recorded: h_delta={h_delta}, e_delta={e_delta}, "
            f"cumulative=({self.cumulative_h_ticks}, {self.cumulative_e_ticks})"
        )
    
    def reset(self) -> None:
        """Reset cumulative offsets (called after alignment)."""
        self.cumulative_h_ticks = 0
        self.cumulative_e_ticks = 0
        self.last_reset = datetime.now()
        logger.debug("Sync offset tracker reset")


@dataclass
class HealthEvent:
    """
    Record of a high-error health event.
    
    Attributes:
        timestamp: When the event occurred.
        error_arcsec: Pointing error magnitude in arcseconds.
    """
    timestamp: datetime
    error_arcsec: float


@dataclass
class HealthMonitor:
    """
    Monitors alignment system health by tracking high-error events.
    
    Attributes:
        events: List of recent high-error events.
        alert_active: Whether a health alert is currently raised.
        window_seconds: Time window for event tracking.
        alert_threshold: Number of events to trigger alert.
    """
    events: List[HealthEvent] = field(default_factory=list)
    alert_active: bool = False
    window_seconds: float = 1800.0  # 30 minutes
    alert_threshold: int = 5
    
    def log_event(self, error_arcsec: float) -> None:
        """
        Log a high-error health event.
        
        Args:
            error_arcsec: Pointing error magnitude in arcseconds.
        """
        self.events.append(HealthEvent(datetime.now(), error_arcsec))
        self._prune_old_events()
        logger.info(f"Health event logged: error={error_arcsec:.1f} arcsec")
    
    def _prune_old_events(self) -> None:
        """Remove events older than the tracking window."""
        cutoff = datetime.now() - timedelta(seconds=self.window_seconds)
        self.events = [e for e in self.events if e.timestamp > cutoff]
    
    def check_alert(self) -> bool:
        """
        Check if alert threshold is exceeded.
        
        Returns:
            True if alert should be raised, False otherwise.
        """
        self._prune_old_events()
        
        if len(self.events) >= self.alert_threshold:
            if not self.alert_active:
                self.alert_active = True
                logger.warning(
                    f"Alignment health alert: {len(self.events)} high-error events "
                    f"in past {self.window_seconds / 60:.0f} minutes. "
                    "Possible causes: loose plate solver, mechanical issues, unstable mount."
                )
            return True
        else:
            self.alert_active = False
            return False
    
    @property
    def event_count(self) -> int:
        """Return current number of events in window."""
        self._prune_old_events()
        return len(self.events)


@dataclass
class ReplacementCandidate:
    """
    Candidate for alignment point replacement.
    
    Attributes:
        point: The alignment point that would be replaced.
        resulting_det: Determinant value after replacement.
        improvement: Change in determinant from current value.
        reason: Why this candidate was identified ("geometry" or "refresh").
    """
    point: AlignmentPoint
    resulting_det: float
    improvement: float
    reason: str  # "geometry" or "refresh"


@dataclass 
class EvaluationResult:
    """
    Result of an alignment monitor evaluation cycle.
    
    Attributes:
        action: The action taken (or NO_ACTION).
        skip_reason: If skipped, the reason why (None if evaluated).
        pointing_error_arcsec: Observed pointing error (None if skipped).
        current_det: Current geometry determinant (None if skipped).
        replaced_point: Index of replaced point (None if not ALIGN).
        new_det: New geometry determinant after replacement (None if not ALIGN).
    """
    action: MonitorAction
    skip_reason: Optional[EvaluationSkipReason] = None
    pointing_error_arcsec: Optional[float] = None
    current_det: Optional[float] = None
    replaced_point: Optional[int] = None
    new_det: Optional[float] = None


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class AlignmentMonitorConfig:
    """
    Configuration parameters for the Alignment Monitor.
    
    All angular parameters use consistent units as documented.
    Error thresholds are in arcseconds; angular constraints are in degrees.
    
    Attributes:
        enabled: Whether the alignment monitor is active.
        drumbeat_interval: Evaluation interval during tracking (seconds).
        error_ignore: Pointing error below which no action is taken (arcseconds).
        error_sync: Pointing error above which sync is performed (arcseconds).
        error_concern: Pointing error above which alignment is evaluated (arcseconds).
        error_max: Pointing error above which health event is logged (arcseconds).
        det_excellent: Determinant threshold for excellent geometry.
        det_good: Determinant threshold for good geometry.
        det_marginal: Determinant threshold for marginal geometry.
        det_improvement_min: Minimum determinant improvement to justify replacement.
        min_separation: Minimum angle between alignment points (degrees).
        refresh_radius: Distance for refresh logic eligibility (degrees).
        scale_radius: Per-point weighted error distance scale (degrees).
        refresh_error_threshold: Weighted error threshold for refresh (arcseconds).
        lockout_post_align: Lockout duration after alignment (seconds).
        lockout_post_sync: Lockout duration after sync (seconds).
        health_window: Health event tracking window (seconds).
        health_alert_threshold: Number of events to trigger health alert.
    """
    enabled: bool = True
    drumbeat_interval: float = 60.0
    
    # Pointing error thresholds (arcseconds)
    error_ignore: float = 30.0
    error_sync: float = 120.0
    error_concern: float = 300.0
    error_max: float = 600.0
    
    # Geometry thresholds (dimensionless)
    det_excellent: float = 0.80
    det_good: float = 0.60
    det_marginal: float = 0.40
    det_improvement_min: float = 0.10
    
    # Angular constraints (degrees)
    min_separation: float = 15.0
    refresh_radius: float = 10.0
    scale_radius: float = 30.0
    
    # Refresh threshold (arcseconds)
    refresh_error_threshold: float = 60.0
    
    # Lockout periods (seconds)
    lockout_post_align: float = 60.0
    lockout_post_sync: float = 10.0
    
    # Health monitoring
    health_window: float = 1800.0
    health_alert_threshold: int = 5
    
    @classmethod
    def from_toml(cls, path: Path | str) -> AlignmentMonitorConfig:
        """
        Load configuration from a TOML file.
        
        Args:
            path: Path to the TOML configuration file.
            
        Returns:
            AlignmentMonitorConfig instance with values from file.
            
        Raises:
            FileNotFoundError: If the configuration file does not exist.
            ValueError: If the configuration file is malformed.
        """
        # Implementation note: requires `tomllib` (Python 3.11+) or `toml` package
        try:
            import tomllib
        except ImportError:
            import toml as tomllib  # type: ignore
        
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(path, "rb") as f:
            data = tomllib.load(f)
        
        section = data.get("alignment_monitor", {})
        
        return cls(
            enabled=section.get("enabled", cls.enabled),
            drumbeat_interval=section.get("drumbeat_interval", cls.drumbeat_interval),
            error_ignore=section.get("error_ignore", cls.error_ignore),
            error_sync=section.get("error_sync", cls.error_sync),
            error_concern=section.get("error_concern", cls.error_concern),
            error_max=section.get("error_max", cls.error_max),
            det_excellent=section.get("det_excellent", cls.det_excellent),
            det_good=section.get("det_good", cls.det_good),
            det_marginal=section.get("det_marginal", cls.det_marginal),
            det_improvement_min=section.get("det_improvement_min", cls.det_improvement_min),
            min_separation=section.get("min_separation", cls.min_separation),
            refresh_radius=section.get("refresh_radius", cls.refresh_radius),
            scale_radius=section.get("scale_radius", cls.scale_radius),
            refresh_error_threshold=section.get("refresh_error_threshold", cls.refresh_error_threshold),
            lockout_post_align=section.get("lockout_post_align", cls.lockout_post_align),
            lockout_post_sync=section.get("lockout_post_sync", cls.lockout_post_sync),
            health_window=section.get("health_window", cls.health_window),
            health_alert_threshold=section.get("health_alert_threshold", cls.health_alert_threshold),
        )
    
    def to_toml(self, path: Path | str) -> None:
        """
        Save configuration to a TOML file.
        
        Args:
            path: Path to write the TOML configuration file.
        """
        try:
            import toml
        except ImportError:
            raise ImportError("toml package required for writing TOML files")
        
        data = {
            "alignment_monitor": {
                "enabled": self.enabled,
                "drumbeat_interval": self.drumbeat_interval,
                "error_ignore": self.error_ignore,
                "error_sync": self.error_sync,
                "error_concern": self.error_concern,
                "error_max": self.error_max,
                "det_excellent": self.det_excellent,
                "det_good": self.det_good,
                "det_marginal": self.det_marginal,
                "det_improvement_min": self.det_improvement_min,
                "min_separation": self.min_separation,
                "refresh_radius": self.refresh_radius,
                "scale_radius": self.scale_radius,
                "refresh_error_threshold": self.refresh_error_threshold,
                "lockout_post_align": self.lockout_post_align,
                "lockout_post_sync": self.lockout_post_sync,
                "health_window": self.health_window,
                "health_alert_threshold": self.health_alert_threshold,
            }
        }
        
        with open(path, "w") as f:
            toml.dump(data, f)


# =============================================================================
# Firmware Interface Protocol
# =============================================================================

class FirmwareInterface(Protocol):
    """
    Protocol defining the required interface to mount firmware.
    
    Implementations must provide these methods for the Alignment Monitor
    to communicate with the telescope mount.
    """
    
    def get_mount_position(self) -> EquatorialCoord:
        """
        Get current mount-reported equatorial position.
        
        Returns:
            Current RA/Dec as reported by the mount.
        """
        ...
    
    def get_mount_ticks(self) -> EncoderTicks:
        """
        Get current encoder tick values.
        
        Returns:
            Current H and E axis encoder ticks.
        """
        ...
    
    def is_mount_static(self) -> bool:
        """
        Check if mount is static (not slewing).
        
        Returns:
            True if mount is stationary or tracking, False if slewing.
        """
        ...
    
    def perform_sync(self, target: EquatorialCoord) -> bool:
        """
        Perform a sync operation to adjust reported position.
        
        Args:
            target: Target RA/Dec to sync to.
            
        Returns:
            True if sync succeeded, False otherwise.
        """
        ...
    
    def capture_alignment_point(
        self, 
        index: int, 
        position: EquatorialCoord
    ) -> bool:
        """
        Capture an alignment point at the current position.
        
        Args:
            index: Point index (1, 2, or 3).
            position: Plate-solved RA/Dec for this position.
            
        Returns:
            True if capture succeeded, False otherwise.
        """
        ...
    
    def perform_alignment(self) -> bool:
        """
        Recalculate alignment model from current points.
        
        Returns:
            True if alignment calculation succeeded, False otherwise.
        """
        ...
    
    def get_alignment_points(self) -> List[AlignmentPoint]:
        """
        Retrieve current alignment point data from firmware.
        
        Returns:
            List of three AlignmentPoint records.
        """
        ...


# =============================================================================
# Utility Functions
# =============================================================================

def angular_separation(coord1: EquatorialCoord, coord2: EquatorialCoord) -> float:
    """
    Calculate angular separation between two equatorial coordinates.
    
    Uses the numerically stable haversine formula.
    
    Args:
        coord1: First coordinate.
        coord2: Second coordinate.
        
    Returns:
        Angular separation in radians.
    """
    delta_dec = coord2.dec - coord1.dec
    delta_ra = coord2.ra - coord1.ra
    
    a = (
        math.sin(delta_dec / 2) ** 2 +
        math.cos(coord1.dec) * math.cos(coord2.dec) * math.sin(delta_ra / 2) ** 2
    )
    
    return 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def angular_separation_arcsec(coord1: EquatorialCoord, coord2: EquatorialCoord) -> float:
    """
    Calculate angular separation in arcseconds.
    
    Args:
        coord1: First coordinate.
        coord2: Second coordinate.
        
    Returns:
        Angular separation in arcseconds.
    """
    return angular_separation(coord1, coord2) * ARCSEC_PER_RADIAN


def compute_geometry_determinant(points: List[EquatorialCoord]) -> float:
    """
    Compute the geometry quality metric for three alignment points.
    
    The determinant of the 3x3 matrix formed by the three unit direction
    vectors measures how well-spread the points are. Values range from 0
    (coplanar/degenerate) to approximately 1 (maximally spread).
    
    Args:
        points: List of exactly three equatorial coordinates.
        
    Returns:
        Absolute value of the determinant.
        
    Raises:
        ValueError: If not exactly three points provided.
    """
    if len(points) != 3:
        raise ValueError(f"Expected 3 points, got {len(points)}")
    
    # Convert to unit vectors
    v1 = points[0].to_unit_vector()
    v2 = points[1].to_unit_vector()
    v3 = points[2].to_unit_vector()
    
    # Compute determinant: v1 · (v2 × v3)
    # Cross product v2 × v3
    cross_x = v2[1] * v3[2] - v2[2] * v3[1]
    cross_y = v2[2] * v3[0] - v2[0] * v3[2]
    cross_z = v2[0] * v3[1] - v2[1] * v3[0]
    
    # Dot product v1 · cross
    det = v1[0] * cross_x + v1[1] * cross_y + v1[2] * cross_z
    
    return abs(det)


def compute_minimum_separation(points: List[EquatorialCoord]) -> float:
    """
    Compute the minimum angular separation between any pair of points.
    
    Args:
        points: List of equatorial coordinates.
        
    Returns:
        Minimum pairwise separation in degrees.
    """
    min_sep = float('inf')
    
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            sep = angular_separation(points[i], points[j]) * RAD_TO_DEG
            min_sep = min(min_sep, sep)
    
    return min_sep


# =============================================================================
# Main Alignment Monitor Class
# =============================================================================

class AlignmentMonitor:
    """
    Semi-autonomous alignment management system.
    
    The Alignment Monitor evaluates pointing accuracy on each evaluation cycle
    and determines whether to take no action, perform a sync, or replace an
    alignment point. It tracks per-point error attribution, manages sync offset
    bookkeeping, and monitors system health.
    
    Attributes:
        config: Configuration parameters.
        firmware: Interface to mount firmware.
        alignment_points: Current alignment point records.
        sync_tracker: Cumulative sync offset tracker.
        health_monitor: System health tracker.
        lockout_until: Timestamp when current lockout expires.
    """
    
    def __init__(
        self, 
        config: AlignmentMonitorConfig,
        firmware: FirmwareInterface
    ) -> None:
        """
        Initialize the Alignment Monitor.
        
        Args:
            config: Configuration parameters.
            firmware: Interface to mount firmware.
        """
        self.config = config
        self.firmware = firmware
        
        # Initialize alignment points from firmware
        self.alignment_points: List[AlignmentPoint] = []
        self._refresh_alignment_points()
        
        # Initialize trackers
        self.sync_tracker = SyncOffsetTracker()
        self.health_monitor = HealthMonitor(
            window_seconds=config.health_window,
            alert_threshold=config.health_alert_threshold
        )
        
        # Lockout management
        self.lockout_until: Optional[datetime] = None
        
        logger.info("Alignment Monitor initialized")
    
    def _refresh_alignment_points(self) -> None:
        """Refresh alignment point data from firmware."""
        self.alignment_points = self.firmware.get_alignment_points()
        logger.debug(f"Refreshed alignment points: {len(self.alignment_points)} points")
    
    def _in_lockout(self) -> bool:
        """Check if currently in lockout period."""
        if self.lockout_until is None:
            return False
        return datetime.now() < self.lockout_until
    
    def _start_lockout(self, duration_seconds: float) -> None:
        """Start a lockout period."""
        self.lockout_until = datetime.now() + timedelta(seconds=duration_seconds)
        logger.debug(f"Lockout started for {duration_seconds} seconds")
    
    def _update_weighted_errors(
        self, 
        current_position: EquatorialCoord,
        pointing_error_arcsec: float
    ) -> None:
        """
        Update weighted error accumulators for all alignment points.
        
        Args:
            current_position: Current mount position.
            pointing_error_arcsec: Observed pointing error in arcseconds.
        """
        for point in self.alignment_points:
            point.update_weighted_error(
                current_position,
                pointing_error_arcsec,
                self.config.scale_radius
            )
    
    def _compute_current_det(self) -> float:
        """Compute geometry determinant for current alignment points."""
        coords = [p.equatorial for p in self.alignment_points]
        return compute_geometry_determinant(coords)
    
    def _compute_det_with_replacement(
        self, 
        replace_index: int, 
        new_position: EquatorialCoord
    ) -> float:
        """
        Compute geometry determinant if a point were replaced.
        
        Args:
            replace_index: Index of point to replace (0-2).
            new_position: New position to use.
            
        Returns:
            Determinant value for the modified configuration.
        """
        coords = [p.equatorial for p in self.alignment_points]
        coords[replace_index] = new_position
        return compute_geometry_determinant(coords)
    
    def _compute_min_sep_with_replacement(
        self, 
        replace_index: int, 
        new_position: EquatorialCoord
    ) -> float:
        """
        Compute minimum separation if a point were replaced.
        
        Args:
            replace_index: Index of point to replace (0-2).
            new_position: New position to use.
            
        Returns:
            Minimum pairwise separation in degrees.
        """
        coords = [p.equatorial for p in self.alignment_points]
        coords[replace_index] = new_position
        return compute_minimum_separation(coords)
    
    def _build_candidates(
        self,
        current_position: EquatorialCoord,
        current_det: float
    ) -> List[ReplacementCandidate]:
        """
        Build list of candidate alignment point replacements.
        
        Args:
            current_position: Current mount position (from plate solve).
            current_det: Current geometry determinant.
            
        Returns:
            List of valid replacement candidates.
        """
        candidates = []
        
        for i, point in enumerate(self.alignment_points):
            candidate_det = self._compute_det_with_replacement(i, current_position)
            min_sep = self._compute_min_sep_with_replacement(i, current_position)
            
            # Check minimum separation constraint
            if min_sep < self.config.min_separation:
                continue
            
            det_improvement = candidate_det - current_det
            distance_deg = angular_separation(current_position, point.equatorial) * RAD_TO_DEG
            
            # Check geometry improvement criterion
            if det_improvement >= self.config.det_improvement_min:
                candidates.append(ReplacementCandidate(
                    point=point,
                    resulting_det=candidate_det,
                    improvement=det_improvement,
                    reason="geometry"
                ))
            # Check refresh criterion
            elif (distance_deg < self.config.refresh_radius and 
                  point.mean_weighted_error > self.config.refresh_error_threshold):
                candidates.append(ReplacementCandidate(
                    point=point,
                    resulting_det=candidate_det,
                    improvement=det_improvement,
                    reason="refresh"
                ))
        
        return candidates
    
    def _select_replacement(
        self, 
        candidates: List[ReplacementCandidate],
        current_det: float
    ) -> ReplacementCandidate:
        """
        Select the best replacement candidate.
        
        Selection priority:
        1. Refresh candidates (fixing bad data takes precedence)
        2. Among remaining candidates, prefer those crossing higher thresholds
        3. Ties broken by point age (oldest replaced first)
        
        Args:
            candidates: List of valid candidates.
            current_det: Current geometry determinant.
            
        Returns:
            Selected candidate for replacement.
            
        Raises:
            ValueError: If candidates list is empty.
        """
        if not candidates:
            raise ValueError("Cannot select from empty candidate list")
        
        # Priority 1: Refresh candidates
        refresh_candidates = [c for c in candidates if c.reason == "refresh"]
        if refresh_candidates:
            # Pick oldest point among refresh candidates
            return min(refresh_candidates, key=lambda c: c.point.timestamp)
        
        # Priority 2: Geometry improvement with threshold awareness
        thresholds = [
            self.config.det_excellent,
            self.config.det_good,
            self.config.det_marginal,
            0.0  # Floor
        ]
        
        def highest_crossed_threshold(det: float) -> float:
            for t in thresholds:
                if det >= t:
                    return t
            return 0.0
        
        # Find the highest threshold any candidate crosses
        candidate_thresholds = [
            (c, highest_crossed_threshold(c.resulting_det)) 
            for c in candidates
        ]
        max_threshold = max(ct[1] for ct in candidate_thresholds)
        
        # Get all candidates at that threshold level
        top_candidates = [ct[0] for ct in candidate_thresholds if ct[1] == max_threshold]
        
        if len(top_candidates) > 1:
            # Multiple at same level: pick oldest
            return min(top_candidates, key=lambda c: c.point.timestamp)
        else:
            return top_candidates[0]
    
    def _perform_sync(self, target: EquatorialCoord) -> bool:
        """
        Perform a sync operation and update tracking.
        
        Args:
            target: Target position from plate solve.
            
        Returns:
            True if sync succeeded, False otherwise.
        """
        # Get ticks before sync for offset tracking
        ticks_before = self.firmware.get_mount_ticks()
        
        success = self.firmware.perform_sync(target)
        
        if success:
            # Get ticks after sync
            ticks_after = self.firmware.get_mount_ticks()
            
            # Record the offset
            h_delta = ticks_after.h_ticks - ticks_before.h_ticks
            e_delta = ticks_after.e_ticks - ticks_before.e_ticks
            self.sync_tracker.record_sync(h_delta, e_delta)
            
            logger.info(f"Sync performed to RA={target.ra:.6f}, Dec={target.dec:.6f}")
        else:
            logger.warning("Sync command failed")
        
        return success
    
    def _perform_alignment(
        self, 
        candidate: ReplacementCandidate,
        plate_solve_position: EquatorialCoord
    ) -> bool:
        """
        Perform an alignment point replacement.
        
        Args:
            candidate: The selected replacement candidate.
            plate_solve_position: Plate-solved position for the new point.
            
        Returns:
            True if alignment succeeded, False otherwise.
        """
        point_index = candidate.point.index
        
        # Capture new alignment point
        if not self.firmware.capture_alignment_point(point_index, plate_solve_position):
            logger.warning(f"Failed to capture alignment point {point_index}")
            return False
        
        # Recalculate alignment model
        if not self.firmware.perform_alignment():
            logger.warning("Failed to perform alignment calculation")
            return False
        
        # Reset sync offset tracker (alignment absorbs previous syncs)
        self.sync_tracker.reset()
        
        # Refresh alignment point data
        self._refresh_alignment_points()
        
        # Reset weighted error for the replaced point
        for point in self.alignment_points:
            if point.index == point_index:
                point.reset_weighted_error()
                break
        
        logger.info(
            f"Alignment point {point_index} replaced. "
            f"Reason: {candidate.reason}, "
            f"det: {candidate.resulting_det:.3f} "
            f"(improvement: {candidate.improvement:+.3f})"
        )
        
        return True
    
    def evaluate(
        self, 
        plate_solve_position: Optional[EquatorialCoord],
        plate_solve_timestamp: Optional[datetime] = None,
        max_plate_solve_age_seconds: float = 5.0
    ) -> EvaluationResult:
        """
        Execute one evaluation cycle.
        
        This is the main entry point, called after goto settle or on periodic
        drumbeat during tracking.
        
        Args:
            plate_solve_position: Current plate-solved RA/Dec, or None if unavailable.
            plate_solve_timestamp: When the plate solve was obtained (default: now).
            max_plate_solve_age_seconds: Maximum acceptable age for plate solve data.
            
        Returns:
            EvaluationResult describing the action taken or reason for skipping.
        """
        # Check enabled
        if not self.config.enabled:
            return EvaluationResult(
                action=MonitorAction.NO_ACTION,
                skip_reason=None
            )
        
        # Step 1: Check lockout
        if self._in_lockout():
            return EvaluationResult(
                action=MonitorAction.NO_ACTION,
                skip_reason=EvaluationSkipReason.IN_LOCKOUT
            )
        
        # Step 2: Check mount state
        if not self.firmware.is_mount_static():
            return EvaluationResult(
                action=MonitorAction.NO_ACTION,
                skip_reason=EvaluationSkipReason.MOUNT_NOT_STATIC
            )
        
        # Step 3: Validate plate solve
        if plate_solve_position is None:
            return EvaluationResult(
                action=MonitorAction.NO_ACTION,
                skip_reason=EvaluationSkipReason.PLATE_SOLVE_UNAVAILABLE
            )
        
        if plate_solve_timestamp is not None:
            age = (datetime.now() - plate_solve_timestamp).total_seconds()
            if age > max_plate_solve_age_seconds:
                return EvaluationResult(
                    action=MonitorAction.NO_ACTION,
                    skip_reason=EvaluationSkipReason.PLATE_SOLVE_STALE
                )
        
        # Get mount position
        mount_position = self.firmware.get_mount_position()
        pointing_error_arcsec = angular_separation_arcsec(plate_solve_position, mount_position)
        
        # Step 4: Update per-point weighted errors
        self._update_weighted_errors(mount_position, pointing_error_arcsec)
        
        # Step 5: Check if error is ignorable
        if pointing_error_arcsec < self.config.error_ignore:
            logger.debug(f"Pointing error {pointing_error_arcsec:.1f}\" below threshold, no action")
            return EvaluationResult(
                action=MonitorAction.NO_ACTION,
                pointing_error_arcsec=pointing_error_arcsec
            )
        
        # Step 6: Compute geometry and candidates
        current_det = self._compute_current_det()
        candidates = self._build_candidates(plate_solve_position, current_det)
        
        logger.debug(
            f"Evaluation: error={pointing_error_arcsec:.1f}\", "
            f"det={current_det:.3f}, candidates={len(candidates)}"
        )
        
        # Step 7: No candidates - consider sync
        if not candidates:
            if pointing_error_arcsec > self.config.error_sync:
                if self._perform_sync(plate_solve_position):
                    self._start_lockout(self.config.lockout_post_sync)
                    return EvaluationResult(
                        action=MonitorAction.SYNC,
                        pointing_error_arcsec=pointing_error_arcsec,
                        current_det=current_det
                    )
            
            return EvaluationResult(
                action=MonitorAction.NO_ACTION,
                pointing_error_arcsec=pointing_error_arcsec,
                current_det=current_det
            )
        
        # Step 8: Select replacement
        selected = self._select_replacement(candidates, current_det)
        
        # Step 9: Health monitoring
        if pointing_error_arcsec > self.config.error_max:
            self.health_monitor.log_event(pointing_error_arcsec)
            self.health_monitor.check_alert()
        
        # Step 10: Perform alignment
        if self._perform_alignment(selected, plate_solve_position):
            self._start_lockout(self.config.lockout_post_align)
            return EvaluationResult(
                action=MonitorAction.ALIGN,
                pointing_error_arcsec=pointing_error_arcsec,
                current_det=current_det,
                replaced_point=selected.point.index,
                new_det=selected.resulting_det
            )
        else:
            # Alignment failed - fall back to sync if error is high enough
            if pointing_error_arcsec > self.config.error_sync:
                if self._perform_sync(plate_solve_position):
                    self._start_lockout(self.config.lockout_post_sync)
                    return EvaluationResult(
                        action=MonitorAction.SYNC,
                        pointing_error_arcsec=pointing_error_arcsec,
                        current_det=current_det
                    )
            
            return EvaluationResult(
                action=MonitorAction.NO_ACTION,
                pointing_error_arcsec=pointing_error_arcsec,
                current_det=current_det
            )
    
    @property
    def is_health_alert_active(self) -> bool:
        """Check if a health alert is currently active."""
        return self.health_monitor.alert_active
    
    @property
    def current_geometry_quality(self) -> float:
        """Get current geometry determinant value."""
        return self._compute_current_det()
    
    def get_point_diagnostics(self) -> List[dict]:
        """
        Get diagnostic information for each alignment point.
        
        Returns:
            List of dictionaries with diagnostic info for each point.
        """
        return [
            {
                "index": p.index,
                "ra_deg": p.equatorial.ra * RAD_TO_DEG,
                "dec_deg": p.equatorial.dec * RAD_TO_DEG,
                "age_minutes": (datetime.now() - p.timestamp).total_seconds() / 60,
                "manual": p.manual,
                "mean_weighted_error_arcsec": p.mean_weighted_error,
            }
            for p in self.alignment_points
        ]


# =============================================================================
# Example Usage and Testing Support
# =============================================================================

class MockFirmwareInterface:
    """
    Mock firmware interface for testing.
    
    Provides a simulated firmware that can be configured to return
    specific values and track commands received.
    """
    
    def __init__(self) -> None:
        """Initialize mock firmware with default state."""
        self.mount_position = EquatorialCoord(ra=0.0, dec=0.0)
        self.mount_ticks = EncoderTicks(h_ticks=0, e_ticks=0)
        self.is_static = True
        self.alignment_points: List[AlignmentPoint] = []
        
        # Command history for verification
        self.sync_history: List[EquatorialCoord] = []
        self.alignment_captures: List[Tuple[int, EquatorialCoord]] = []
        self.alignment_count = 0
    
    def get_mount_position(self) -> EquatorialCoord:
        return self.mount_position
    
    def get_mount_ticks(self) -> EncoderTicks:
        return self.mount_ticks
    
    def is_mount_static(self) -> bool:
        return self.is_static
    
    def perform_sync(self, target: EquatorialCoord) -> bool:
        self.sync_history.append(target)
        self.mount_position = target
        return True
    
    def capture_alignment_point(self, index: int, position: EquatorialCoord) -> bool:
        self.alignment_captures.append((index, position))
        
        # Update or add alignment point
        for i, p in enumerate(self.alignment_points):
            if p.index == index:
                self.alignment_points[i] = AlignmentPoint(
                    index=index,
                    equatorial=position,
                    ticks=self.mount_ticks,
                    timestamp=datetime.now(),
                    manual=False
                )
                return True
        
        # Point not found - add it
        self.alignment_points.append(AlignmentPoint(
            index=index,
            equatorial=position,
            ticks=self.mount_ticks,
            timestamp=datetime.now(),
            manual=False
        ))
        return True
    
    def perform_alignment(self) -> bool:
        self.alignment_count += 1
        return True
    
    def get_alignment_points(self) -> List[AlignmentPoint]:
        return self.alignment_points.copy()
    
    def setup_initial_alignment(
        self,
        coords: List[Tuple[float, float]],
        ages_minutes: Optional[List[float]] = None
    ) -> None:
        """
        Set up initial alignment points for testing.
        
        Args:
            coords: List of (ra_deg, dec_deg) tuples.
            ages_minutes: Optional ages for each point (default: 0).
        """
        if ages_minutes is None:
            ages_minutes = [0.0] * len(coords)
        
        self.alignment_points = []
        for i, ((ra_deg, dec_deg), age) in enumerate(zip(coords, ages_minutes)):
            self.alignment_points.append(AlignmentPoint(
                index=i + 1,
                equatorial=EquatorialCoord(
                    ra=ra_deg * DEG_TO_RAD,
                    dec=dec_deg * DEG_TO_RAD
                ),
                ticks=EncoderTicks(h_ticks=i * 1000, e_ticks=i * 500),
                timestamp=datetime.now() - timedelta(minutes=age),
                manual=True
            ))


if __name__ == "__main__":
    # Simple demonstration
    logging.basicConfig(level=logging.DEBUG)
    
    # Create mock firmware with initial alignment
    firmware = MockFirmwareInterface()
    firmware.setup_initial_alignment([
        (0.0, 45.0),    # Point 1: RA=0°, Dec=45°
        (120.0, 45.0),  # Point 2: RA=120°, Dec=45°
        (240.0, 45.0),  # Point 3: RA=240°, Dec=45°
    ])
    
    # Create monitor with default config
    config = AlignmentMonitorConfig()
    monitor = AlignmentMonitor(config, firmware)
    
    print(f"Initial geometry quality: {monitor.current_geometry_quality:.3f}")
    print(f"Point diagnostics: {monitor.get_point_diagnostics()}")
    
    # Simulate an evaluation with small error
    firmware.mount_position = EquatorialCoord(ra=0.5 * DEG_TO_RAD, dec=45.0 * DEG_TO_RAD)
    plate_solve = EquatorialCoord(ra=0.502 * DEG_TO_RAD, dec=45.001 * DEG_TO_RAD)
    
    result = monitor.evaluate(plate_solve)
    print(f"Evaluation result: {result}")
