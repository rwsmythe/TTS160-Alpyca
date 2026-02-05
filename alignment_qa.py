"""
Alignment Quality Assurance Subsystem for TTS160 Alpaca Driver.

This module provides independent verification of the mount's alignment model by:
- Calculating an alignment quaternion using Davenport's Q-method
- Converting tick positions to celestial coordinates
- Comparing driver-calculated values against firmware-reported values

Reference: alignment_qa_subsystem_requirements.md

Thread Safety:
    All public methods are thread-safe via RLock protection.
"""

import logging
import math
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Callable

import numpy as np


# =============================================================================
# Constants (matching firmware align.h)
# =============================================================================

# Solar to sidereal time ratio
SOLAR_TO_SID = 1.002737908

# Firmware uses 960 ticks per second (not 1000)
CLOCKSCALER = 960.0

# Time to radians conversions
SEC_TO_RAD = math.pi / (12 * 3600)  # Seconds to radians
MSEC_TO_RAD = SEC_TO_RAD / CLOCKSCALER  # IS_MSECS to radians

# Angle conversions
RAD_TO_ARCSEC = 206264.806247
ARCSEC_TO_RAD = 1.0 / RAD_TO_ARCSEC
RAD_TO_DEG = 180.0 / math.pi
DEG_TO_RAD = math.pi / 180.0


# =============================================================================
# QA Status Enum
# =============================================================================

class QAStatusCode(Enum):
    """QA subsystem status codes."""
    VALID = "valid"           # All calculations successful
    INVALID = "invalid"       # Calculation failed or data invalid
    STALE = "stale"           # Data is outdated
    NO_DATA = "no_data"       # No firmware data available
    SYNTHETIC = "synthetic"   # Contains synthetic alignment points


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FirmwareAlignmentData:
    """Raw alignment data retrieved from firmware via binary protocol.

    All coordinate values are in radians unless otherwise noted.
    Timestamps are in IS_MSECS (960 ticks/second, not true milliseconds).
    """
    # Point status (A16, A17)
    point_count: int                    # Number of real points (sat=1)
    point_flags: int                    # Bitfield: bits 0-2=sat, bits 4-6=manual

    # Star tick positions (A4-A9)
    star_ticks: List[Tuple[int, int]]   # [(h_ticks, e_ticks), ...] per star

    # Star equatorial coordinates (A10-A15)
    star_coords: List[Tuple[float, float]]  # [(ra_rad, dec_rad), ...] per star

    # Capture timestamps (A18-A20)
    star_timestamps: List[int]          # IS_MSECS values

    # Sidereal time references (A2, A3)
    start_sid_time: float               # Sidereal time at startup (radians)
    align_sid_time: float               # Sidereal time at alignment (radians)

    # Model status (A21, A22)
    rms_error: float                    # Alignment model RMS error (radians)
    model_valid: bool                   # True if alignment model calculated

    # Mount configuration (M8, M9)
    ticks_per_rev_h: int                # H-axis ticks per revolution
    ticks_per_rev_e: int                # E-axis ticks per revolution

    # Site location (C17, C18)
    longitude: float                    # Site longitude (radians)
    latitude: float                     # Site latitude (radians)

    # Firmware quaternions (T31, T32)
    firmware_quaternion: Tuple[float, float, float, float]  # (w, x, y, z)
    inverse_quaternion: Tuple[float, float, float, float]   # (w, x, y, z)


@dataclass
class AlignmentPointQA:
    """Per-alignment-point QA data with synthetic point detection."""
    index: int                  # Point index (0, 1, or 2)
    is_synthetic: bool          # True if sat=0 (not user-captured)
    is_manual: bool             # True if manual flag set
    h_ticks: int                # H-axis encoder ticks
    e_ticks: int                # E-axis encoder ticks
    ra_rad: float               # Original RA (radians)
    dec_rad: float              # Original Dec (radians)
    ra_adjusted_rad: float      # RA after sidereal correction (radians)
    timestamp: int              # Capture timestamp (IS_MSECS)
    alt_rad: float              # Computed altitude (radians)
    az_rad: float               # Computed azimuth (radians)
    residual_arcsec: float      # Pointing residual at this point (arcseconds)


@dataclass
class QAStatus:
    """Overall QA status container for display and API."""
    status: QAStatusCode                # Overall status code
    driver_quaternion: Tuple[float, float, float, float]   # Driver-calculated (w,x,y,z)
    firmware_quaternion: Tuple[float, float, float, float]  # Firmware-reported (w,x,y,z)
    quaternion_delta_arcsec: float      # Angular difference between quaternions
    driver_alt_deg: float               # Driver-calculated altitude (degrees)
    driver_az_deg: float                # Driver-calculated azimuth (degrees)
    driver_ra_hours: float              # Driver-calculated RA (hours)
    driver_dec_deg: float               # Driver-calculated Dec (degrees)
    mount_ra_hours: float               # Mount-reported RA (hours)
    mount_dec_deg: float                # Mount-reported Dec (degrees)
    position_delta_arcsec: float        # Angular separation driver vs mount
    alignment_points: List[AlignmentPointQA]  # Per-point QA data
    synthetic_point_count: int          # Number of synthetic points detected
    model_valid: bool                   # Firmware model validity flag
    rms_error_arcsec: float             # Firmware RMS error (arcseconds)
    last_update: datetime               # When QA was last calculated
    error_message: str = ""             # Error description if status != VALID


@dataclass
class QAHistoryEntry:
    """Historical QA snapshot for trend analysis."""
    timestamp: datetime
    quaternion_delta_arcsec: float
    position_delta_arcsec: float
    synthetic_count: int
    model_valid: bool


# =============================================================================
# AlignmentQA Class
# =============================================================================

class AlignmentQA:
    """Alignment Quality Assurance calculator.

    Provides independent verification of mount alignment by:
    - Calculating alignment quaternion using Davenport's Q-method
    - Converting tick positions to celestial coordinates
    - Comparing driver vs firmware calculations
    - Detecting synthetic alignment points

    Thread Safety:
        All public methods are thread-safe via RLock protection.

    Usage:
        qa = AlignmentQA(logger)
        qa.update_from_firmware(serial_manager)
        qa.recalculate_driver_quaternion()
        status = qa.get_qa_status()
    """

    def __init__(self, logger: logging.Logger):
        """Initialize the QA subsystem.

        Args:
            logger: Logger instance for diagnostic output.
        """
        self._logger = logger
        self._lock = threading.RLock()

        # Cached firmware data
        self._firmware_data: Optional[FirmwareAlignmentData] = None

        # Driver-calculated values
        self._driver_quaternion: Optional[Tuple[float, float, float, float]] = None
        self._alignment_points_qa: List[AlignmentPointQA] = []

        # Status tracking
        self._qa_status: Optional[QAStatus] = None
        self._last_calculation: Optional[datetime] = None
        self._error_message: str = ""

        # History for trend analysis
        self._qa_history: List[QAHistoryEntry] = []
        self._max_history_size: int = 100

        # Callbacks (set by AlignmentMonitor integration)
        self._serial_manager_callback: Optional[Callable] = None

    # =========================================================================
    # Coordinate Conversion Pipeline
    # =========================================================================

    def ticks_to_altaz(
        self,
        h_ticks: int,
        e_ticks: int,
        ticks_per_rev_h: int,
        ticks_per_rev_e: int
    ) -> Tuple[float, float]:
        """Convert encoder ticks to altitude/azimuth coordinates.

        Args:
            h_ticks: Horizontal axis encoder ticks.
            e_ticks: Elevation axis encoder ticks.
            ticks_per_rev_h: H-axis ticks per full revolution.
            ticks_per_rev_e: E-axis ticks per full revolution.

        Returns:
            Tuple of (altitude_rad, azimuth_rad).

        Note:
            The conversion assumes zero-point calibration. Actual mount
            may require offset corrections based on home position.
        """
        two_pi = 2.0 * math.pi

        # Convert ticks to radians
        az_rad = h_ticks * (two_pi / ticks_per_rev_h)
        alt_rad = e_ticks * (two_pi / ticks_per_rev_e)

        # Normalize to [0, 2*pi) for azimuth, [-pi/2, pi/2] for altitude
        az_rad = az_rad % two_pi
        # Altitude normalization may depend on mount configuration

        return (alt_rad, az_rad)

    def altaz_to_radec(
        self,
        alt_rad: float,
        az_rad: float,
        lst_rad: float,
        lat_rad: float
    ) -> Tuple[float, float]:
        """Convert horizontal coordinates to equatorial coordinates.

        Uses standard spherical trigonometry transformation.

        Args:
            alt_rad: Altitude in radians.
            az_rad: Azimuth in radians (North=0, East=pi/2).
            lst_rad: Local sidereal time in radians.
            lat_rad: Observer latitude in radians.

        Returns:
            Tuple of (ra_rad, dec_rad).
        """
        sin_alt = math.sin(alt_rad)
        cos_alt = math.cos(alt_rad)
        sin_az = math.sin(az_rad)
        cos_az = math.cos(az_rad)
        sin_lat = math.sin(lat_rad)
        cos_lat = math.cos(lat_rad)

        # Calculate declination
        sin_dec = sin_alt * sin_lat + cos_alt * cos_lat * cos_az
        # Clamp for numerical stability
        sin_dec = max(-1.0, min(1.0, sin_dec))
        dec_rad = math.asin(sin_dec)

        # Calculate hour angle
        cos_dec = math.cos(dec_rad)
        if abs(cos_dec) < 1e-10 or abs(cos_lat) < 1e-10:
            # Near pole - hour angle undefined
            ha_rad = 0.0
        else:
            cos_ha = (sin_alt - sin_lat * sin_dec) / (cos_lat * cos_dec)
            cos_ha = max(-1.0, min(1.0, cos_ha))
            ha_rad = math.acos(cos_ha)
            # Determine sign based on azimuth
            if sin_az > 0:
                ha_rad = 2.0 * math.pi - ha_rad

        # Calculate right ascension
        ra_rad = lst_rad - ha_rad
        # Normalize to [0, 2*pi)
        while ra_rad < 0:
            ra_rad += 2.0 * math.pi
        while ra_rad >= 2.0 * math.pi:
            ra_rad -= 2.0 * math.pi

        return (ra_rad, dec_rad)

    def ticks_to_radec(
        self,
        h_ticks: int,
        e_ticks: int,
        ticks_per_rev_h: int,
        ticks_per_rev_e: int,
        lst_rad: float,
        lat_rad: float
    ) -> Tuple[float, float]:
        """Complete tick-to-equatorial conversion pipeline.

        Args:
            h_ticks: Horizontal axis encoder ticks.
            e_ticks: Elevation axis encoder ticks.
            ticks_per_rev_h: H-axis ticks per full revolution.
            ticks_per_rev_e: E-axis ticks per full revolution.
            lst_rad: Local sidereal time in radians.
            lat_rad: Observer latitude in radians.

        Returns:
            Tuple of (ra_rad, dec_rad).
        """
        alt_rad, az_rad = self.ticks_to_altaz(
            h_ticks, e_ticks, ticks_per_rev_h, ticks_per_rev_e
        )
        return self.altaz_to_radec(alt_rad, az_rad, lst_rad, lat_rad)

    # =========================================================================
    # Sidereal Time Correction
    # =========================================================================

    def compute_sidereal_adjustment(
        self,
        time1_msec: int,
        time2_msec: int
    ) -> float:
        """Compute RA adjustment for Earth rotation between timestamps.

        The firmware uses CLOCKSCALER=960, so IS_MSECS are not true
        milliseconds. One second equals 960 IS_MSECS ticks.

        Args:
            time1_msec: First timestamp in IS_MSECS.
            time2_msec: Second timestamp in IS_MSECS.

        Returns:
            RA adjustment in radians (subtract from star 2/3 RA).

        Formula (from firmware):
            delta_rad = (time2 - time1) * MSEC_TO_RAD * SOLAR_TO_SID
        """
        delta_ticks = time2_msec - time1_msec
        delta_rad = delta_ticks * MSEC_TO_RAD * SOLAR_TO_SID
        return delta_rad

    # =========================================================================
    # Vector Conversion Helpers
    # =========================================================================

    def _radec_to_unit_vector(self, ra_rad: float, dec_rad: float) -> np.ndarray:
        """Convert RA/Dec to unit direction vector (equatorial frame).

        Args:
            ra_rad: Right ascension in radians.
            dec_rad: Declination in radians.

        Returns:
            3-element numpy array representing unit vector.
        """
        cos_dec = math.cos(dec_rad)
        return np.array([
            cos_dec * math.cos(ra_rad),
            cos_dec * math.sin(ra_rad),
            math.sin(dec_rad)
        ])

    def _altaz_to_unit_vector(self, alt_rad: float, az_rad: float) -> np.ndarray:
        """Convert Alt/Az to unit direction vector (horizontal frame).

        Args:
            alt_rad: Altitude in radians.
            az_rad: Azimuth in radians.

        Returns:
            3-element numpy array representing unit vector.
        """
        cos_alt = math.cos(alt_rad)
        return np.array([
            cos_alt * math.cos(az_rad),
            cos_alt * math.sin(az_rad),
            math.sin(alt_rad)
        ])

    # =========================================================================
    # Davenport Q-method Quaternion Calculation
    # =========================================================================

    def calculate_quaternion_davenport(
        self,
        reference_vectors: List[np.ndarray],
        observed_vectors: List[np.ndarray],
        weights: Optional[List[float]] = None
    ) -> Tuple[float, float, float, float]:
        """Calculate optimal rotation quaternion using Davenport's Q-method.

        The Q-method finds the quaternion q that minimizes:
            sum_i w_i * ||r_i - R(q) * o_i||^2

        where R(q) is the rotation matrix corresponding to quaternion q.

        Algorithm:
        1. Build B matrix from observation pairs
        2. Construct 4x4 K matrix from B
        3. Find eigenvector corresponding to largest eigenvalue
        4. Return normalized quaternion (w, x, y, z)

        Args:
            reference_vectors: List of unit vectors in reference frame
                (equatorial coordinates).
            observed_vectors: List of unit vectors in observed frame
                (telescope/horizontal coordinates).
            weights: Optional weights for each observation pair.
                Defaults to equal weights.

        Returns:
            Quaternion as (w, x, y, z) tuple, normalized.

        Raises:
            ValueError: If inputs are invalid or insufficient.

        Reference:
            Davenport, P.B. (1968) - "A Vector Approach to the Algebra
            of Rotations with Applications"
        """
        n_obs = len(reference_vectors)
        if n_obs != len(observed_vectors):
            raise ValueError("Reference and observed vector lists must have same length")
        if n_obs < 2:
            raise ValueError("At least 2 observation pairs required")

        # Default to equal weights
        if weights is None:
            weights = [1.0] * n_obs
        elif len(weights) != n_obs:
            raise ValueError("Weights list must match number of observations")

        # Normalize weights
        total_weight = sum(weights)
        if total_weight <= 0:
            raise ValueError("Total weight must be positive")
        weights = [w / total_weight for w in weights]

        # Build B matrix: B = sum(w_i * outer(o_i, r_i))
        B = np.zeros((3, 3))
        for i in range(n_obs):
            o = observed_vectors[i]
            r = reference_vectors[i]
            B += weights[i] * np.outer(o, r)

        # Construct K matrix
        S = B + B.T
        sigma = np.trace(B)
        Z = np.array([
            B[1, 2] - B[2, 1],
            B[2, 0] - B[0, 2],
            B[0, 1] - B[1, 0]
        ])

        # K matrix (4x4)
        K = np.zeros((4, 4))
        K[0, 0] = sigma
        K[0, 1:4] = Z
        K[1:4, 0] = Z
        K[1:4, 1:4] = S - sigma * np.eye(3)

        # Find eigenvalues and eigenvectors
        eigenvalues, eigenvectors = np.linalg.eigh(K)

        # Optimal quaternion is eigenvector of largest eigenvalue
        max_idx = np.argmax(eigenvalues)
        q = eigenvectors[:, max_idx]

        # Ensure w (scalar) is positive for consistency
        if q[0] < 0:
            q = -q

        # Normalize (should already be unit, but ensure numerical stability)
        q = q / np.linalg.norm(q)

        return (float(q[0]), float(q[1]), float(q[2]), float(q[3]))

    # =========================================================================
    # Quaternion Comparison
    # =========================================================================

    def quaternion_angular_difference(
        self,
        q1: Tuple[float, float, float, float],
        q2: Tuple[float, float, float, float]
    ) -> float:
        """Calculate angular difference between two quaternions.

        The angle between two quaternions representing rotations is:
            angle = 2 * arccos(|q1 . q2|)

        Note: q and -q represent the same rotation, so we use absolute
        value of the dot product.

        Args:
            q1: First quaternion as (w, x, y, z).
            q2: Second quaternion as (w, x, y, z).

        Returns:
            Angular difference in arcseconds.
        """
        # Dot product
        dot = abs(
            q1[0] * q2[0] +
            q1[1] * q2[1] +
            q1[2] * q2[2] +
            q1[3] * q2[3]
        )

        # Clamp for numerical stability
        dot = min(1.0, dot)

        # Angle in radians
        angle_rad = 2.0 * math.acos(dot)

        # Convert to arcseconds
        return angle_rad * RAD_TO_ARCSEC

    # =========================================================================
    # Validation Functions
    # =========================================================================

    def validate_quaternion(
        self,
        q: Tuple[float, float, float, float],
        tolerance: float = 0.001
    ) -> bool:
        """Validate quaternion normalization.

        Args:
            q: Quaternion as (w, x, y, z).
            tolerance: Maximum deviation from unit magnitude.

        Returns:
            True if quaternion is valid (unit magnitude within tolerance).
        """
        magnitude = math.sqrt(q[0]**2 + q[1]**2 + q[2]**2 + q[3]**2)
        return abs(magnitude - 1.0) <= tolerance

    def validate_coordinates(self, ra_rad: float, dec_rad: float) -> bool:
        """Validate coordinate ranges.

        Args:
            ra_rad: Right ascension in radians (should be 0 to 2*pi).
            dec_rad: Declination in radians (should be -pi/2 to +pi/2).

        Returns:
            True if coordinates are within valid ranges.
        """
        if ra_rad < 0 or ra_rad >= 2.0 * math.pi:
            return False
        if dec_rad < -math.pi / 2.0 or dec_rad > math.pi / 2.0:
            return False
        return True

    # =========================================================================
    # Synthetic Point Detection
    # =========================================================================

    def parse_point_flags(self, flags: int) -> List[Tuple[bool, bool]]:
        """Parse A17 bitfield into per-point flags.

        A17 format:
            Bits 0-2: sat flags (1 = user-captured, 0 = not captured/synthetic)
            Bits 4-6: manual flags (1 = user-entered coords, 0 = catalog/auto)

        Args:
            flags: A17 bitfield value.

        Returns:
            List of (is_sat, is_manual) tuples for each of 3 stars.
        """
        result = []
        for i in range(3):
            is_sat = bool((flags >> i) & 1)
            is_manual = bool((flags >> (i + 4)) & 1)
            result.append((is_sat, is_manual))
        return result

    def detect_synthetic_points(
        self,
        point_count: int,
        point_flags: int
    ) -> List[int]:
        """Detect which alignment points are synthetic.

        A point is synthetic if:
        - sat flag is 0 (not user-captured)
        - AND the alignment has at least 1 real point (so model was calculated)

        Args:
            point_count: Number of real points (A16).
            point_flags: Point flags bitfield (A17).

        Returns:
            List of indices (0-2) that are synthetic points.
        """
        if point_count == 0:
            # No alignment performed yet - no synthetic points
            return []

        synthetic_indices = []
        parsed = self.parse_point_flags(point_flags)

        for i, (is_sat, _) in enumerate(parsed):
            if not is_sat:
                # Point is not user-captured - likely synthetic
                synthetic_indices.append(i)

        return synthetic_indices

    # =========================================================================
    # Data Retrieval (to be called by integration layer)
    # =========================================================================

    def set_firmware_data(self, data: FirmwareAlignmentData) -> None:
        """Set firmware alignment data for QA calculation.

        This is called by the integration layer after querying the mount.

        Args:
            data: Firmware alignment data structure.
        """
        with self._lock:
            self._firmware_data = data
            self._last_calculation = None  # Invalidate cached calculations

    # =========================================================================
    # Full QA Calculation
    # =========================================================================

    def recalculate_driver_quaternion(self) -> bool:
        """Recalculate driver quaternion from current firmware data.

        This performs the full QA calculation pipeline:
        1. Parse alignment point data
        2. Apply sidereal time corrections
        3. Convert coordinates to unit vectors
        4. Calculate quaternion using Davenport Q-method
        5. Compare with firmware quaternion

        Returns:
            True if calculation succeeded, False otherwise.
        """
        with self._lock:
            if self._firmware_data is None:
                self._error_message = "No firmware data available"
                return False

            try:
                data = self._firmware_data

                # Parse point flags for synthetic detection
                point_flags_parsed = self.parse_point_flags(data.point_flags)
                synthetic_indices = self.detect_synthetic_points(
                    data.point_count, data.point_flags
                )

                # Build QA data for each alignment point
                self._alignment_points_qa = []
                reference_vectors = []
                observed_vectors = []

                for i in range(3):
                    is_sat, is_manual = point_flags_parsed[i]
                    is_synthetic = i in synthetic_indices

                    # Get tick and coordinate data
                    h_ticks, e_ticks = data.star_ticks[i] if i < len(data.star_ticks) else (0, 0)
                    ra_rad, dec_rad = data.star_coords[i] if i < len(data.star_coords) else (0.0, 0.0)
                    timestamp = data.star_timestamps[i] if i < len(data.star_timestamps) else 0

                    # Apply sidereal correction (relative to star 1)
                    if i > 0 and len(data.star_timestamps) > 0:
                        time_delta = self.compute_sidereal_adjustment(
                            data.star_timestamps[0], timestamp
                        )
                        ra_adjusted = ra_rad - time_delta
                    else:
                        ra_adjusted = ra_rad

                    # Normalize RA to [0, 2*pi)
                    while ra_adjusted < 0:
                        ra_adjusted += 2.0 * math.pi
                    while ra_adjusted >= 2.0 * math.pi:
                        ra_adjusted -= 2.0 * math.pi

                    # Convert ticks to alt/az
                    alt_rad, az_rad = self.ticks_to_altaz(
                        h_ticks, e_ticks,
                        data.ticks_per_rev_h, data.ticks_per_rev_e
                    )

                    # Create QA point record
                    point_qa = AlignmentPointQA(
                        index=i,
                        is_synthetic=is_synthetic,
                        is_manual=is_manual,
                        h_ticks=h_ticks,
                        e_ticks=e_ticks,
                        ra_rad=ra_rad,
                        dec_rad=dec_rad,
                        ra_adjusted_rad=ra_adjusted,
                        timestamp=timestamp,
                        alt_rad=alt_rad,
                        az_rad=az_rad,
                        residual_arcsec=0.0  # Calculated later
                    )
                    self._alignment_points_qa.append(point_qa)

                    # Build vectors for quaternion calculation
                    # Only use points with valid data
                    if is_sat or (data.point_count > 0 and i < 3):
                        ref_vec = self._radec_to_unit_vector(ra_adjusted, dec_rad)
                        obs_vec = self._altaz_to_unit_vector(alt_rad, az_rad)
                        reference_vectors.append(ref_vec)
                        observed_vectors.append(obs_vec)

                # Calculate driver quaternion
                if len(reference_vectors) >= 2:
                    self._driver_quaternion = self.calculate_quaternion_davenport(
                        reference_vectors, observed_vectors
                    )
                else:
                    self._error_message = "Insufficient alignment points for quaternion calculation"
                    return False

                # Calculate per-point residuals
                self._calculate_point_residuals()

                self._last_calculation = datetime.now()
                self._error_message = ""
                return True

            except Exception as e:
                self._error_message = f"QA calculation failed: {e}"
                self._logger.error(f"QA calculation error: {e}")
                return False

    def _calculate_point_residuals(self) -> None:
        """Calculate pointing residual at each alignment point.

        The residual is the angular separation between the expected position
        (from the driver quaternion) and the actual position.
        """
        if self._driver_quaternion is None or self._firmware_data is None:
            return

        # For now, use a simplified residual calculation
        # Full implementation would transform through the driver quaternion
        # and compare with observed positions
        for point in self._alignment_points_qa:
            # Placeholder: actual implementation needs quaternion transformation
            point.residual_arcsec = 0.0

    # =========================================================================
    # Status Generation
    # =========================================================================

    def get_qa_status(self) -> Optional[QAStatus]:
        """Get current QA status for display/API.

        Returns:
            QAStatus object with all QA metrics, or None if no data.
        """
        with self._lock:
            if self._firmware_data is None:
                return QAStatus(
                    status=QAStatusCode.NO_DATA,
                    driver_quaternion=(1.0, 0.0, 0.0, 0.0),
                    firmware_quaternion=(1.0, 0.0, 0.0, 0.0),
                    quaternion_delta_arcsec=0.0,
                    driver_alt_deg=0.0,
                    driver_az_deg=0.0,
                    driver_ra_hours=0.0,
                    driver_dec_deg=0.0,
                    mount_ra_hours=0.0,
                    mount_dec_deg=0.0,
                    position_delta_arcsec=0.0,
                    alignment_points=[],
                    synthetic_point_count=0,
                    model_valid=False,
                    rms_error_arcsec=0.0,
                    last_update=datetime.now(),
                    error_message="No firmware data available"
                )

            data = self._firmware_data

            # Determine status code
            synthetic_count = len(self.detect_synthetic_points(
                data.point_count, data.point_flags
            ))

            if not data.model_valid:
                status_code = QAStatusCode.INVALID
            elif synthetic_count > 0:
                status_code = QAStatusCode.SYNTHETIC
            elif self._driver_quaternion is None:
                status_code = QAStatusCode.INVALID
            else:
                status_code = QAStatusCode.VALID

            # Calculate quaternion delta
            driver_quat = self._driver_quaternion or (1.0, 0.0, 0.0, 0.0)
            firmware_quat = data.firmware_quaternion
            quat_delta = self.quaternion_angular_difference(driver_quat, firmware_quat)

            # Build status
            status = QAStatus(
                status=status_code,
                driver_quaternion=driver_quat,
                firmware_quaternion=firmware_quat,
                quaternion_delta_arcsec=quat_delta,
                driver_alt_deg=0.0,  # Would need current position
                driver_az_deg=0.0,
                driver_ra_hours=0.0,
                driver_dec_deg=0.0,
                mount_ra_hours=0.0,
                mount_dec_deg=0.0,
                position_delta_arcsec=0.0,
                alignment_points=self._alignment_points_qa.copy(),
                synthetic_point_count=synthetic_count,
                model_valid=data.model_valid,
                rms_error_arcsec=data.rms_error * RAD_TO_ARCSEC,
                last_update=self._last_calculation or datetime.now(),
                error_message=self._error_message
            )

            # Add to history
            self._add_to_history(status)

            return status

    def _add_to_history(self, status: QAStatus) -> None:
        """Add status snapshot to history for trend analysis."""
        entry = QAHistoryEntry(
            timestamp=status.last_update,
            quaternion_delta_arcsec=status.quaternion_delta_arcsec,
            position_delta_arcsec=status.position_delta_arcsec,
            synthetic_count=status.synthetic_point_count,
            model_valid=status.model_valid
        )

        self._qa_history.append(entry)

        # Trim history if needed
        while len(self._qa_history) > self._max_history_size:
            self._qa_history.pop(0)

    def get_history(self) -> List[QAHistoryEntry]:
        """Get QA history for trend analysis.

        Returns:
            List of historical QA snapshots.
        """
        with self._lock:
            return self._qa_history.copy()

    def clear_history(self) -> None:
        """Clear QA history."""
        with self._lock:
            self._qa_history.clear()
