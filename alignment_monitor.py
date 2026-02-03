# -*- coding: utf-8 -*-
"""
Alignment Monitor for TTS160 Alpaca Driver.

Provides alignment quality monitoring by periodically capturing images,
detecting stars, plate solving, and comparing solved position against
mount-reported position.

Components:
    - CameraManager: Alpaca camera control via alpyca
    - StarDetector: Star detection via SEP
    - PlateSolver: Plate solving via tetra3

Third-Party Libraries:
    alpyca - MIT License (ASCOM Initiative)
    SEP - LGPLv3/BSD/MIT (Kyle Barbary)
    tetra3 - Apache 2.0 (European Space Agency)

See LICENSE_THIRD_PARTY.md for full attribution.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum, Enum
from typing import Optional, List, Callable, Tuple

import numpy as np

from camera_manager import CameraManager, CameraState
from star_detector import StarDetector
from plate_solver import PlateSolver
import alignment_geometry as geometry


class AlignmentState(IntEnum):
    """Alignment monitor states."""
    DISABLED = 0
    DISCONNECTED = 1
    CONNECTING = 2
    CONNECTED = 3
    CAPTURING = 4
    SOLVING = 5
    MONITORING = 6
    ERROR = 7


@dataclass
class AlignmentPoint:
    """Single alignment measurement point."""
    timestamp: datetime
    mount_ra: float          # hours
    mount_dec: float         # degrees
    solved_ra: float         # hours
    solved_dec: float        # degrees
    ra_error: float          # arcseconds
    dec_error: float         # arcseconds
    total_error: float       # arcseconds
    solve_time_ms: float
    stars_detected: int
    confidence: float        # 0.0 - 1.0


@dataclass
class AlignmentStatus:
    """Current alignment monitor status."""
    state: AlignmentState
    camera_connected: bool
    camera_name: str
    last_solve_time: Optional[datetime]
    last_ra_error: float
    last_dec_error: float
    last_total_error: float
    average_error: float
    max_error: float
    measurement_count: int
    stars_detected: int
    solve_confidence: float
    error_message: str
    history: List[AlignmentPoint] = field(default_factory=list)
    # V1 additions
    geometry_determinant: float = 0.0
    health_alert_active: bool = False
    last_decision: str = ""
    lockout_remaining: float = 0.0


# =============================================================================
# V1 Data Structures
# =============================================================================

class DecisionResult(Enum):
    """Result of V1 decision engine evaluation."""
    NO_ACTION = "no_action"
    SYNC = "sync"
    ALIGN = "align"
    LOCKOUT = "lockout"
    ERROR = "error"


@dataclass
class AlignmentPointRecord:
    """Mount alignment point record for V1 tracking.

    Tracks one of the three mount alignment points with weighted error
    accumulation for determining which point should be replaced.

    Attributes:
        index: Point index (1, 2, or 3).
        equatorial: (ra, dec) coordinates in radians.
        altaz: (alt, az) coordinates in radians.
        ticks: (h_ticks, e_ticks) encoder counts.
        timestamp: When the point was captured.
        manual: True if user-selected, False if auto-captured.
        weighted_error_sum: Accumulated weighted error (arcseconds).
        weighted_error_weight: Accumulated weights for averaging.
    """
    index: int
    equatorial: Tuple[float, float]  # (ra, dec) in radians
    altaz: Tuple[float, float]       # (alt, az) in radians
    ticks: Tuple[int, int]           # (h_ticks, e_ticks)
    timestamp: datetime
    manual: bool = False
    weighted_error_sum: float = 0.0
    weighted_error_weight: float = 0.0

    @property
    def mean_weighted_error(self) -> float:
        """Calculate mean weighted error in arcseconds."""
        if self.weighted_error_weight == 0:
            return 0.0
        return self.weighted_error_sum / self.weighted_error_weight

    def reset_weighted_error(self) -> None:
        """Reset weighted error accumulators (called after replacement)."""
        self.weighted_error_sum = 0.0
        self.weighted_error_weight = 0.0

    def add_weighted_error(self, error: float, weight: float) -> None:
        """Add a weighted error observation.

        Args:
            error: Pointing error in arcseconds.
            weight: Weight based on distance from this point.
        """
        self.weighted_error_sum += weight * error
        self.weighted_error_weight += weight


@dataclass
class SyncOffsetTracker:
    """Tracks cumulative sync adjustments for V1 evaluation consistency.

    Maintains the total tick adjustments from sync operations since
    the last alignment, allowing error evaluation to be normalized.

    Attributes:
        cumulative_h_ticks: Total H-axis sync adjustments.
        cumulative_e_ticks: Total E-axis sync adjustments.
        last_reset: When the tracker was last cleared.
    """
    cumulative_h_ticks: int = 0
    cumulative_e_ticks: int = 0
    last_reset: datetime = field(default_factory=datetime.now)

    def add_offset(self, h_delta: int, e_delta: int) -> None:
        """Record a sync offset adjustment.

        Args:
            h_delta: H-axis tick change from sync.
            e_delta: E-axis tick change from sync.
        """
        self.cumulative_h_ticks += h_delta
        self.cumulative_e_ticks += e_delta

    def reset(self) -> None:
        """Reset tracker (called after alignment point replacement)."""
        self.cumulative_h_ticks = 0
        self.cumulative_e_ticks = 0
        self.last_reset = datetime.now()


@dataclass
class HealthMonitor:
    """Tracks high-error events for V1 system health assessment.

    Maintains a sliding window of error events to detect persistent
    alignment problems that may indicate mechanical issues.

    Attributes:
        events: List of (timestamp, error_magnitude) tuples.
        alert_active: Whether a health alert is currently raised.
    """
    events: List[Tuple[datetime, float]] = field(default_factory=list)
    alert_active: bool = False

    def log_event(self, error_magnitude: float, window_seconds: float) -> None:
        """Log a high-error event and prune old events.

        Args:
            error_magnitude: The error value in arcseconds.
            window_seconds: Health window duration for pruning.
        """
        now = datetime.now()
        self.events.append((now, error_magnitude))
        cutoff = now - timedelta(seconds=window_seconds)
        self.events = [(t, e) for t, e in self.events if t > cutoff]

    def check_alert(self, threshold: int) -> bool:
        """Check if alert threshold has been crossed.

        Args:
            threshold: Number of events to trigger alert.

        Returns:
            True if alert should be active.
        """
        self.alert_active = len(self.events) >= threshold
        return self.alert_active

    def clear(self) -> None:
        """Clear all events and reset alert."""
        self.events.clear()
        self.alert_active = False


@dataclass
class ReplacementCandidate:
    """Candidate for alignment point replacement.

    Represents a potential alignment point replacement with the
    evaluation metrics needed for selection.

    Attributes:
        point: The alignment point being considered for replacement.
        new_det: Determinant if this point is replaced.
        improvement: Change in determinant from current.
        reason: Why this candidate was selected ("geometry" or "refresh").
        distance: Angular distance from current position to this point.
    """
    point: AlignmentPointRecord
    new_det: float
    improvement: float
    reason: str  # "geometry" or "refresh"
    distance: float  # degrees


class AlignmentMonitor:
    """Alignment quality monitor using plate solving.

    Monitors telescope alignment by periodically capturing images,
    detecting stars, plate solving, and comparing the solved position
    against the mount's reported position.

    Thread Safety:
        All public methods are thread-safe via RLock protection.

    Attributes:
        HISTORY_LIMIT: Maximum number of measurements to retain.
        MIN_INTERVAL: Minimum interval between measurements (seconds).
    """

    HISTORY_LIMIT = 100
    MIN_INTERVAL = 5.0

    def __init__(
        self,
        config,
        logger: logging.Logger
    ):
        """Initialize alignment monitor.

        Args:
            config: TTS160Config instance with alignment settings.
            logger: Logger instance for alignment operations.
        """
        self._config = config
        self._logger = logger
        self._lock = threading.RLock()

        # State
        self._state = AlignmentState.DISABLED
        self._error_message = ""

        # Components (lazy-initialized)
        self._camera_manager: Optional[CameraManager] = None
        self._star_detector: Optional[StarDetector] = None
        self._plate_solver: Optional[PlateSolver] = None

        # Background thread
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Mount position callback
        self._mount_position_callback: Optional[Callable[[], Tuple[float, float]]] = None

        # Measurement history
        self._history: List[AlignmentPoint] = []
        self._last_measurement: Optional[AlignmentPoint] = None

        # Statistics
        self._measurement_count = 0
        self._average_error = 0.0
        self._max_error = 0.0

        # V1 Decision Engine State
        self._alignment_points: List[AlignmentPointRecord] = []
        self._sync_tracker = SyncOffsetTracker()
        self._health_monitor = HealthMonitor()
        self._lockout_until: Optional[datetime] = None
        self._last_decision = DecisionResult.NO_ACTION
        self._geometry_determinant = 0.0

        # V1 Additional Callbacks
        self._mount_altaz_callback: Optional[Callable[[], Tuple[float, float]]] = None
        self._mount_static_callback: Optional[Callable[[], bool]] = None
        self._sync_callback: Optional[Callable[[float, float], bool]] = None
        self._alignment_data_callback: Optional[Callable[[], List[AlignmentPointRecord]]] = None

        # V1 Firmware support flag (false until firmware implements ALIGN_POINT)
        self._firmware_supports_align_point = False

    def start(self) -> bool:
        """Start the alignment monitor.

        Initializes components and starts the background monitoring thread.

        Returns:
            True if started successfully, False otherwise.
        """
        with self._lock:
            if not self._config.alignment_enabled:
                self._logger.info("Alignment monitor is disabled in configuration")
                self._state = AlignmentState.DISABLED
                return False

            if self._monitor_thread is not None and self._monitor_thread.is_alive():
                self._logger.debug("Alignment monitor already running")
                return True

            try:
                self._logger.info("Starting alignment monitor...")

                # Initialize components
                self._camera_manager = CameraManager(self._logger)
                self._star_detector = StarDetector(self._logger)
                self._plate_solver = PlateSolver(
                    self._config.alignment_database_path,
                    self._logger
                )

                # Check component availability
                if not StarDetector.is_available():
                    self._error_message = "SEP library not available"
                    self._update_state(AlignmentState.ERROR)
                    return False

                if not self._plate_solver.is_available():
                    self._error_message = "tetra3 library not available"
                    self._update_state(AlignmentState.ERROR)
                    return False

                # Start background thread
                self._stop_event.clear()
                self._monitor_thread = threading.Thread(
                    target=self._background_monitor,
                    name="AlignmentMonitor",
                    daemon=True
                )
                self._monitor_thread.start()

                self._update_state(AlignmentState.DISCONNECTED)
                self._logger.info("Alignment monitor started")
                return True

            except Exception as e:
                self._error_message = str(e)
                self._update_state(AlignmentState.ERROR)
                self._logger.error(f"Failed to start alignment monitor: {e}")
                return False

    def stop(self) -> None:
        """Stop the alignment monitor and clean up resources."""
        with self._lock:
            # Always set stop event for safety
            self._stop_event.set()

            if self._monitor_thread is None:
                return

            self._logger.info("Stopping alignment monitor...")

        # Wait for thread outside lock
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=5.0)

        with self._lock:
            # Disconnect camera
            if self._camera_manager is not None:
                self._camera_manager.disconnect()
                self._camera_manager = None

            self._star_detector = None
            self._plate_solver = None
            self._monitor_thread = None
            self._update_state(AlignmentState.DISABLED)
            self._logger.info("Alignment monitor stopped")

    def get_status(self) -> AlignmentStatus:
        """Get current alignment status.

        Returns:
            AlignmentStatus with current state and statistics.
        """
        with self._lock:
            camera_connected = (
                self._camera_manager is not None and
                self._camera_manager.is_connected()
            )
            camera_info = (
                self._camera_manager.get_camera_info()
                if self._camera_manager else None
            )
            camera_name = camera_info.name if camera_info else ""

            last_point = self._last_measurement

            # Calculate lockout remaining time
            lockout_remaining = 0.0
            if self._lockout_until:
                remaining = (self._lockout_until - datetime.now()).total_seconds()
                lockout_remaining = max(0.0, remaining)

            return AlignmentStatus(
                state=self._state,
                camera_connected=camera_connected,
                camera_name=camera_name,
                last_solve_time=last_point.timestamp if last_point else None,
                last_ra_error=last_point.ra_error if last_point else 0.0,
                last_dec_error=last_point.dec_error if last_point else 0.0,
                last_total_error=last_point.total_error if last_point else 0.0,
                average_error=self._average_error,
                max_error=self._max_error,
                measurement_count=self._measurement_count,
                stars_detected=last_point.stars_detected if last_point else 0,
                solve_confidence=last_point.confidence if last_point else 0.0,
                error_message=self._error_message,
                history=list(self._history),
                # V1 additions
                geometry_determinant=self._geometry_determinant,
                health_alert_active=self._health_monitor.alert_active,
                last_decision=self._last_decision.value,
                lockout_remaining=lockout_remaining
            )

    def get_history(self, limit: int = 50) -> List[AlignmentPoint]:
        """Get recent measurement history.

        Args:
            limit: Maximum number of points to return.

        Returns:
            List of recent AlignmentPoint measurements.
        """
        with self._lock:
            return list(self._history[-limit:])

    def trigger_measurement(self) -> Optional[AlignmentPoint]:
        """Manually trigger a single measurement.

        Returns:
            AlignmentPoint if successful, None otherwise.
        """
        with self._lock:
            if self._state == AlignmentState.DISABLED:
                self._logger.warning("Cannot trigger measurement: monitor disabled")
                return None

            if not self._camera_manager or not self._camera_manager.is_connected():
                self._logger.warning("Cannot trigger measurement: camera not connected")
                return None

            return self._perform_measurement()

    def clear_history(self) -> None:
        """Clear measurement history and reset statistics."""
        with self._lock:
            self._history.clear()
            self._last_measurement = None
            self._measurement_count = 0
            self._average_error = 0.0
            self._max_error = 0.0
            self._logger.info("Alignment history cleared")

    def set_mount_position_callback(
        self,
        callback: Callable[[], Tuple[float, float]]
    ) -> None:
        """Set callback to get current mount position.

        Args:
            callback: Function returning (ra_hours, dec_degrees).
        """
        with self._lock:
            self._mount_position_callback = callback
            self._logger.debug("Mount position callback set")

    def _background_monitor(self) -> None:
        """Background thread for periodic measurements."""
        self._logger.debug("Background monitor thread started")

        while not self._stop_event.is_set():
            try:
                # Connect camera if needed
                if not self._camera_manager.is_connected():
                    self._connect_camera()

                # Perform measurement if connected
                if self._camera_manager.is_connected():
                    with self._lock:
                        self._perform_measurement()

                # Wait for next interval
                interval = max(
                    self._config.alignment_interval,
                    self.MIN_INTERVAL
                )
                self._stop_event.wait(timeout=interval)

            except Exception as e:
                self._logger.error(f"Background monitor error: {e}")
                with self._lock:
                    self._error_message = str(e)
                    self._update_state(AlignmentState.ERROR)
                self._stop_event.wait(timeout=10.0)

        self._logger.debug("Background monitor thread exiting")

    def _connect_camera(self) -> bool:
        """Connect to the configured camera.

        Returns:
            True if connected successfully, False otherwise.
        """
        with self._lock:
            self._update_state(AlignmentState.CONNECTING)

            success = self._camera_manager.connect(
                self._config.alignment_camera_address,
                self._config.alignment_camera_port,
                self._config.alignment_camera_device
            )

            if success:
                self._update_state(AlignmentState.CONNECTED)
                self._error_message = ""
                return True
            else:
                self._error_message = self._camera_manager.get_error_message()
                self._update_state(AlignmentState.DISCONNECTED)
                return False

    def _perform_measurement(self) -> Optional[AlignmentPoint]:
        """Perform a single measurement cycle.

        Captures image, detects stars, solves plate, calculates error.

        Returns:
            AlignmentPoint if successful, None otherwise.
        """
        # Get mount position
        if self._mount_position_callback is None:
            self._logger.warning("No mount position callback set")
            return None

        try:
            mount_ra, mount_dec = self._mount_position_callback()
        except Exception as e:
            self._logger.error(f"Failed to get mount position: {e}")
            return None

        # Capture image
        self._update_state(AlignmentState.CAPTURING)
        image = self._camera_manager.capture_image(
            self._config.alignment_exposure_time,
            self._config.alignment_binning
        )

        if image is None:
            self._error_message = "Image capture failed"
            self._update_state(AlignmentState.ERROR)
            return None

        # Detect stars
        detection = self._star_detector.detect_stars(
            image.data,
            threshold_sigma=self._config.alignment_detection_threshold,
            max_stars=self._config.alignment_max_stars
        )

        if detection is None or detection.star_count == 0:
            self._error_message = "No stars detected"
            self._update_state(AlignmentState.CONNECTED)
            return None

        # Plate solve
        self._update_state(AlignmentState.SOLVING)
        solve_start = time.time()

        solve_result = self._plate_solver.solve_from_centroids(
            detection.centroids,
            (image.width, image.height),
            fov_estimate=self._config.alignment_fov_estimate
        )

        solve_time_ms = (time.time() - solve_start) * 1000

        if solve_result is None:
            self._error_message = "Plate solve failed"
            self._update_state(AlignmentState.CONNECTED)
            return None

        # Calculate errors
        ra_error, dec_error, total_error = self._calculate_error(
            mount_ra, mount_dec,
            solve_result.ra_hours, solve_result.dec_degrees
        )

        # Create measurement point
        point = AlignmentPoint(
            timestamp=datetime.now(),
            mount_ra=mount_ra,
            mount_dec=mount_dec,
            solved_ra=solve_result.ra_hours,
            solved_dec=solve_result.dec_degrees,
            ra_error=ra_error,
            dec_error=dec_error,
            total_error=total_error,
            solve_time_ms=solve_time_ms,
            stars_detected=detection.star_count,
            confidence=solve_result.confidence
        )

        # Update history and statistics
        self._history.append(point)
        if len(self._history) > self.HISTORY_LIMIT:
            self._history.pop(0)

        self._last_measurement = point
        self._measurement_count += 1
        self._update_statistics()

        self._update_state(AlignmentState.MONITORING)
        self._error_message = ""

        if self._config.alignment_verbose_logging:
            self._logger.info(
                f"Alignment: RA={ra_error:.1f}\" Dec={dec_error:.1f}\" "
                f"Total={total_error:.1f}\" ({detection.star_count} stars, "
                f"{solve_time_ms:.0f}ms)"
            )

        # Check error threshold
        if total_error > self._config.alignment_error_threshold:
            self._logger.warning(
                f"Alignment error {total_error:.1f}\" exceeds threshold "
                f"{self._config.alignment_error_threshold}\"!"
            )

        return point

    def _calculate_error(
        self,
        mount_ra: float,
        mount_dec: float,
        solved_ra: float,
        solved_dec: float
    ) -> Tuple[float, float, float]:
        """Calculate pointing error in arcseconds.

        Args:
            mount_ra: Mount RA in hours.
            mount_dec: Mount Dec in degrees.
            solved_ra: Solved RA in hours.
            solved_dec: Solved Dec in degrees.

        Returns:
            Tuple of (ra_error, dec_error, total_error) in arcseconds.
        """
        # Convert RA difference to arcseconds
        # Account for RA wrapping at 24h
        ra_diff = solved_ra - mount_ra
        if ra_diff > 12.0:
            ra_diff -= 24.0
        elif ra_diff < -12.0:
            ra_diff += 24.0

        # RA error in arcseconds (15 arcsec per second of RA)
        # Corrected for declination (cos(dec) factor)
        cos_dec = np.cos(np.radians(mount_dec))
        ra_error = ra_diff * 15.0 * 3600.0 * cos_dec  # hours to arcsec

        # Dec error in arcseconds
        dec_error = (solved_dec - mount_dec) * 3600.0

        # Total error (angular separation)
        total_error = np.sqrt(ra_error**2 + dec_error**2)

        return ra_error, dec_error, total_error

    def _update_statistics(self) -> None:
        """Update running statistics from history."""
        if not self._history:
            self._average_error = 0.0
            self._max_error = 0.0
            return

        errors = [p.total_error for p in self._history]
        self._average_error = sum(errors) / len(errors)
        self._max_error = max(errors)

    def _update_state(self, new_state: AlignmentState) -> None:
        """Update alignment state with logging.

        Args:
            new_state: New alignment state.
        """
        if self._state != new_state:
            old_state = self._state
            self._state = new_state
            self._logger.debug(
                f"Alignment state: {old_state.name} -> {new_state.name}"
            )

    # =========================================================================
    # V1 Callback Setters
    # =========================================================================

    def set_mount_altaz_callback(
        self,
        callback: Callable[[], Tuple[float, float]]
    ) -> None:
        """Set callback to get current mount alt/az position.

        Args:
            callback: Function returning (altitude_degrees, azimuth_degrees).
        """
        with self._lock:
            self._mount_altaz_callback = callback
            self._logger.debug("Mount alt/az callback set")

    def set_mount_static_callback(
        self,
        callback: Callable[[], bool]
    ) -> None:
        """Set callback to check if mount is static (tracking, not slewing).

        Args:
            callback: Function returning True if mount is static.
        """
        with self._lock:
            self._mount_static_callback = callback
            self._logger.debug("Mount static callback set")

    def set_sync_callback(
        self,
        callback: Callable[[float, float], bool]
    ) -> None:
        """Set callback to perform sync operation.

        Args:
            callback: Function accepting (ra_hours, dec_degrees), returning success.
        """
        with self._lock:
            self._sync_callback = callback
            self._logger.debug("Sync callback set")

    def set_alignment_data_callback(
        self,
        callback: Callable[[], List[AlignmentPointRecord]]
    ) -> None:
        """Set callback to get current alignment point data from firmware.

        Args:
            callback: Function returning list of AlignmentPointRecord.
        """
        with self._lock:
            self._alignment_data_callback = callback
            self._logger.debug("Alignment data callback set")

    # =========================================================================
    # V1 Lockout System
    # =========================================================================

    def _in_lockout_period(self) -> bool:
        """Check if currently in a lockout period.

        Returns:
            True if actions are blocked by lockout.
        """
        if self._lockout_until is None:
            return False
        return datetime.now() < self._lockout_until

    def _start_lockout(self, seconds: float) -> None:
        """Start a lockout period.

        Args:
            seconds: Duration of lockout in seconds.
        """
        self._lockout_until = datetime.now() + timedelta(seconds=seconds)
        self._logger.debug(f"Lockout started for {seconds:.1f}s")

    def _clear_lockout(self) -> None:
        """Clear the current lockout."""
        self._lockout_until = None

    # =========================================================================
    # V1 Weighted Error Tracking
    # =========================================================================

    def _update_weighted_errors(self, pointing_error: float) -> None:
        """Update per-point weighted errors based on current position.

        Uses distance-based weighting to attribute error to nearby alignment points.

        Args:
            pointing_error: Current pointing error in arcseconds.
        """
        if not self._alignment_points:
            return

        if not self._mount_altaz_callback:
            return

        try:
            alt_deg, az_deg = self._mount_altaz_callback()
            current_altaz = (
                geometry.degrees_to_radians(alt_deg),
                geometry.degrees_to_radians(az_deg)
            )
        except Exception as e:
            self._logger.debug(f"Failed to get alt/az for weighted errors: {e}")
            return

        scale_radius = self._config.alignment_scale_radius

        for point in self._alignment_points:
            # Calculate distance from current position to alignment point
            distance_rad = geometry.angular_separation_altaz(
                current_altaz[0], current_altaz[1],
                point.altaz[0], point.altaz[1]
            )
            distance_deg = geometry.radians_to_degrees(distance_rad)

            # Calculate weight based on distance
            weight = geometry.compute_weight_for_distance(distance_deg, scale_radius)

            # Accumulate weighted error
            point.add_weighted_error(pointing_error, weight)

    def _refresh_alignment_points(self) -> None:
        """Refresh alignment point data from firmware callback."""
        if not self._alignment_data_callback:
            return

        try:
            self._alignment_points = self._alignment_data_callback()
            if self._alignment_points:
                self._update_geometry_determinant()
        except Exception as e:
            self._logger.debug(f"Failed to refresh alignment points: {e}")

    # =========================================================================
    # V1 Geometry Calculations
    # =========================================================================

    def _update_geometry_determinant(self) -> None:
        """Update the geometry determinant from current alignment points."""
        if len(self._alignment_points) != 3:
            self._geometry_determinant = 0.0
            return

        points_altaz = [p.altaz for p in self._alignment_points]
        self._geometry_determinant = geometry.compute_geometry_determinant(points_altaz)

    def _get_geometry_config(self) -> geometry.GeometryConfig:
        """Create GeometryConfig from current configuration."""
        return geometry.GeometryConfig(
            det_excellent=self._config.alignment_det_excellent,
            det_good=self._config.alignment_det_good,
            det_marginal=self._config.alignment_det_marginal,
            det_improvement_min=self._config.alignment_det_improvement_min,
            min_separation=self._config.alignment_min_separation,
            refresh_radius=self._config.alignment_refresh_radius,
            scale_radius=self._config.alignment_scale_radius,
            refresh_error_threshold=self._config.alignment_refresh_error_threshold,
        )

    # =========================================================================
    # V1 Health Monitoring
    # =========================================================================

    def _log_health_event(self, error_magnitude: float) -> None:
        """Log a high-error health event.

        Args:
            error_magnitude: Error value in arcseconds.
        """
        self._health_monitor.log_event(
            error_magnitude,
            self._config.alignment_health_window
        )

    def _check_health_alert(self) -> bool:
        """Check if health alert should be raised.

        Returns:
            True if alert is active.
        """
        if self._health_monitor.check_alert(self._config.alignment_health_alert_threshold):
            if not self._health_monitor.alert_active:
                self._logger.warning(
                    f"Alignment health alert - {len(self._health_monitor.events)} "
                    f"high-error events in past "
                    f"{self._config.alignment_health_window / 60:.0f} minutes. "
                    "Possible causes: loose plate solver, mechanical issues, unstable mount."
                )
            return True
        return False

    def clear_health_events(self) -> None:
        """Clear health event history and reset alert."""
        with self._lock:
            self._health_monitor.clear()
            self._logger.info("Health events cleared")

    # =========================================================================
    # V1 Sync Operations
    # =========================================================================

    def _perform_sync(self) -> bool:
        """Perform sync operation with plate-solved coordinates.

        Returns:
            True if sync was successful.
        """
        if not self._sync_callback:
            self._logger.debug("No sync callback set")
            return False

        if not self._last_measurement:
            self._logger.debug("No measurement available for sync")
            return False

        try:
            success = self._sync_callback(
                self._last_measurement.solved_ra,
                self._last_measurement.solved_dec
            )

            if success:
                self._logger.info(
                    f"V1 Sync performed: RA={self._last_measurement.solved_ra:.4f}h "
                    f"Dec={self._last_measurement.solved_dec:.4f}°"
                )
            return success

        except Exception as e:
            self._logger.error(f"Sync operation failed: {e}")
            return False

    # =========================================================================
    # V1 Decision Engine
    # =========================================================================

    def evaluate(self) -> DecisionResult:
        """Execute V1 decision logic after a measurement.

        This is the main V1 decision engine that evaluates pointing error
        and decides whether to sync, replace an alignment point, or do nothing.

        Returns:
            DecisionResult indicating the action taken or reason for no action.
        """
        with self._lock:
            # Step 1: Check lockout
            if self._in_lockout_period():
                self._last_decision = DecisionResult.LOCKOUT
                return DecisionResult.LOCKOUT

            # Step 2: Check mount state
            if self._mount_static_callback:
                try:
                    if not self._mount_static_callback():
                        self._last_decision = DecisionResult.NO_ACTION
                        return DecisionResult.NO_ACTION
                except Exception:
                    pass  # Proceed if callback fails

            # Step 3: Get pointing error from last measurement
            if not self._last_measurement:
                self._last_decision = DecisionResult.NO_ACTION
                return DecisionResult.NO_ACTION

            pointing_error = self._last_measurement.total_error

            # Step 4: Update per-point weighted errors
            self._update_weighted_errors(pointing_error)

            # Step 5: Check if error is ignorable
            if pointing_error < self._config.alignment_error_ignore:
                self._last_decision = DecisionResult.NO_ACTION
                return DecisionResult.NO_ACTION

            # Step 6: Refresh alignment point data and compute geometry
            self._refresh_alignment_points()

            # Step 7: Find replacement candidates
            candidates = self._find_replacement_candidates()

            # Step 8: Handle no candidates - sync if error is high enough
            if len(candidates) == 0:
                if pointing_error > self._config.alignment_error_sync:
                    if self._perform_sync():
                        self._start_lockout(self._config.alignment_lockout_post_sync)
                        self._last_decision = DecisionResult.SYNC
                        return DecisionResult.SYNC
                self._last_decision = DecisionResult.NO_ACTION
                return DecisionResult.NO_ACTION

            # Step 9: Select best replacement candidate
            selected = self._select_replacement_candidate(candidates)
            if not selected:
                self._last_decision = DecisionResult.NO_ACTION
                return DecisionResult.NO_ACTION

            # Step 10: Health monitoring for extreme errors
            if pointing_error > self._config.alignment_error_max:
                self._log_health_event(pointing_error)
                self._check_health_alert()

            # Step 11: Perform alignment or fall back to sync
            if self._firmware_supports_align_point:
                # Future: call firmware ALIGN_POINT command
                self._logger.info(
                    f"V1 Alignment: replacing point {selected.point.index} "
                    f"(reason: {selected.reason}, det: {selected.new_det:.3f})"
                )
                selected.point.reset_weighted_error()
                self._sync_tracker.reset()
                self._start_lockout(self._config.alignment_lockout_post_align)
                self._last_decision = DecisionResult.ALIGN
                return DecisionResult.ALIGN
            else:
                # Firmware doesn't support ALIGN_POINT, log intent and sync instead
                self._logger.info(
                    f"V1 Alignment would replace point {selected.point.index} "
                    f"(reason: {selected.reason}, det: {selected.new_det:.3f}) - "
                    "firmware unsupported, falling back to sync"
                )
                if self._perform_sync():
                    self._start_lockout(self._config.alignment_lockout_post_sync)
                    self._last_decision = DecisionResult.SYNC
                    return DecisionResult.SYNC
                self._last_decision = DecisionResult.NO_ACTION
                return DecisionResult.NO_ACTION

    def _find_replacement_candidates(self) -> List[ReplacementCandidate]:
        """Find valid replacement candidates for alignment points.

        Returns:
            List of ReplacementCandidate objects.
        """
        if len(self._alignment_points) != 3:
            return []

        if not self._mount_altaz_callback:
            return []

        try:
            alt_deg, az_deg = self._mount_altaz_callback()
            candidate_altaz = (
                geometry.degrees_to_radians(alt_deg),
                geometry.degrees_to_radians(az_deg)
            )
        except Exception as e:
            self._logger.debug(f"Failed to get alt/az for candidates: {e}")
            return []

        # Get current points as alt/az tuples
        current_points = [p.altaz for p in self._alignment_points]

        # Get weighted errors for each point
        weighted_errors = [p.mean_weighted_error for p in self._alignment_points]

        # Evaluate candidates using geometry module
        config = self._get_geometry_config()
        evaluations = geometry.evaluate_replacement_candidates(
            current_points, candidate_altaz, config, weighted_errors
        )

        # Convert to ReplacementCandidate objects
        candidates = []
        for eval in evaluations:
            candidates.append(ReplacementCandidate(
                point=self._alignment_points[eval.point_index],
                new_det=eval.new_det,
                improvement=eval.improvement,
                reason=eval.reason,
                distance=eval.distance_deg
            ))

        return candidates

    def _select_replacement_candidate(
        self,
        candidates: List[ReplacementCandidate]
    ) -> Optional[ReplacementCandidate]:
        """Select the best replacement candidate.

        Args:
            candidates: List of valid candidates.

        Returns:
            Best candidate or None.
        """
        if not candidates:
            return None

        # Get timestamps for tiebreaking
        timestamps = [p.timestamp.timestamp() for p in self._alignment_points]

        # Convert to geometry module format
        eval_candidates = [
            geometry.CandidateEvaluation(
                point_index=self._alignment_points.index(c.point),
                new_det=c.new_det,
                improvement=c.improvement,
                reason=c.reason,
                distance_deg=c.distance,
                meets_separation=True
            )
            for c in candidates
        ]

        config = self._get_geometry_config()
        best_eval = geometry.select_best_candidate(eval_candidates, timestamps, config)

        if best_eval:
            # Find corresponding ReplacementCandidate
            for c in candidates:
                if self._alignment_points.index(c.point) == best_eval.point_index:
                    return c

        return None

    def get_geometry_determinant(self) -> float:
        """Get the current geometry determinant value.

        Returns:
            Determinant value (0.0 to ~1.0).
        """
        with self._lock:
            return self._geometry_determinant

    def get_alignment_points(self) -> List[AlignmentPointRecord]:
        """Get the current alignment point records.

        Returns:
            Copy of alignment point records.
        """
        with self._lock:
            return list(self._alignment_points)
