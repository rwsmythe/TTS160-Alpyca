# -*- coding: utf-8 -*-
"""
Alignment Geometry Calculations for TTS160 Alpaca Driver.

Provides geometric evaluation of alignment point configurations:
- Determinant calculation for three-point alignment quality
- Angular separation calculations
- Candidate evaluation for point replacement

The determinant metric measures the "spread" of alignment points:
- det = 0: Points are coplanar through origin (degenerate)
- det → 1: Points are maximally spread (optimal)

See alignment_monitor_specification.md for algorithm details.
"""

import math
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class GeometryConfig:
    """Configuration for geometry calculations.

    Attributes:
        det_excellent: Threshold for excellent geometry (protect).
        det_good: Threshold for good geometry (be selective).
        det_marginal: Threshold for marginal geometry (seek improvement).
        det_improvement_min: Minimum improvement to justify replacement.
        min_separation: Minimum angle between points (degrees).
        refresh_radius: Distance for refresh logic (degrees).
        scale_radius: Distance falloff for weighted errors (degrees).
        refresh_error_threshold: Weighted error for refresh (arcseconds).
    """
    det_excellent: float = 0.80
    det_good: float = 0.60
    det_marginal: float = 0.40
    det_improvement_min: float = 0.10
    min_separation: float = 15.0
    refresh_radius: float = 10.0
    scale_radius: float = 30.0
    refresh_error_threshold: float = 60.0


def compute_geometry_determinant(points: List[Tuple[float, float]]) -> float:
    """Compute alignment geometry quality using matrix determinant.

    The quality of a three-point alignment configuration is measured by
    the absolute determinant of the 3x3 matrix formed by unit direction
    vectors from the alignment points in alt/az coordinates.

    Args:
        points: List of 3 (alt, az) tuples in radians.

    Returns:
        Absolute determinant value:
        - 0.0: Points are coplanar (degenerate, useless)
        - ~1.0: Points are maximally spread (optimal)
        - Returns 0.0 if not exactly 3 points provided.
    """
    if len(points) != 3:
        return 0.0

    # Convert alt/az to unit vectors
    # v = [cos(alt)*cos(az), cos(alt)*sin(az), sin(alt)]
    vectors = []
    for alt, az in points:
        cos_alt = math.cos(alt)
        v = [
            cos_alt * math.cos(az),
            cos_alt * math.sin(az),
            math.sin(alt)
        ]
        vectors.append(v)

    # Compute det(M) = v1 · (v2 × v3) using scalar triple product
    v1, v2, v3 = vectors

    # Cross product v2 × v3
    cross = [
        v2[1] * v3[2] - v2[2] * v3[1],
        v2[2] * v3[0] - v2[0] * v3[2],
        v2[0] * v3[1] - v2[1] * v3[0]
    ]

    # Dot product v1 · cross
    det = v1[0] * cross[0] + v1[1] * cross[1] + v1[2] * cross[2]

    return abs(det)


def angular_separation_altaz(
    alt1: float, az1: float,
    alt2: float, az2: float
) -> float:
    """Calculate angular separation between two alt/az positions.

    Uses the haversine formula for numerical stability.

    Args:
        alt1, az1: First position altitude and azimuth (radians).
        alt2, az2: Second position altitude and azimuth (radians).

    Returns:
        Angular separation in radians.
    """
    # Haversine formula adapted for alt/az
    # Treat alt as latitude, az as longitude
    d_alt = alt2 - alt1
    d_az = az2 - az1

    a = (math.sin(d_alt / 2) ** 2 +
         math.cos(alt1) * math.cos(alt2) * math.sin(d_az / 2) ** 2)

    # Clamp to avoid numerical issues with asin
    a = min(1.0, max(0.0, a))
    sep = 2 * math.asin(math.sqrt(a))

    return sep


def angular_separation_radec(
    ra1: float, dec1: float,
    ra2: float, dec2: float
) -> float:
    """Calculate angular separation between two RA/Dec positions.

    Uses the haversine formula for numerical stability.

    Args:
        ra1, dec1: First position RA and Dec (radians).
        ra2, dec2: Second position RA and Dec (radians).

    Returns:
        Angular separation in radians.
    """
    # Haversine formula for spherical coordinates
    d_dec = dec2 - dec1
    d_ra = ra2 - ra1

    a = (math.sin(d_dec / 2) ** 2 +
         math.cos(dec1) * math.cos(dec2) * math.sin(d_ra / 2) ** 2)

    # Clamp to avoid numerical issues with asin
    a = min(1.0, max(0.0, a))
    sep = 2 * math.asin(math.sqrt(a))

    return sep


def radians_to_arcseconds(radians: float) -> float:
    """Convert radians to arcseconds.

    Args:
        radians: Angle in radians.

    Returns:
        Angle in arcseconds.
    """
    return radians * 206264.806


def degrees_to_radians(degrees: float) -> float:
    """Convert degrees to radians.

    Args:
        degrees: Angle in degrees.

    Returns:
        Angle in radians.
    """
    return degrees * math.pi / 180.0


def radians_to_degrees(radians: float) -> float:
    """Convert radians to degrees.

    Args:
        radians: Angle in radians.

    Returns:
        Angle in degrees.
    """
    return radians * 180.0 / math.pi


def compute_weight_for_distance(
    distance_deg: float,
    scale_radius_deg: float
) -> float:
    """Compute distance-based weight for error accumulation.

    Uses inverse-square-like falloff: weight = 1 / (1 + (d/r)²)

    Args:
        distance_deg: Angular distance in degrees.
        scale_radius_deg: Scale radius for falloff in degrees.

    Returns:
        Weight value between 0 and 1.
    """
    if scale_radius_deg <= 0:
        return 0.0
    ratio = distance_deg / scale_radius_deg
    return 1.0 / (1.0 + ratio * ratio)


def check_minimum_separation(
    points: List[Tuple[float, float]],
    min_separation_rad: float
) -> bool:
    """Check if all point pairs meet minimum separation requirement.

    Args:
        points: List of (alt, az) tuples in radians.
        min_separation_rad: Minimum required separation in radians.

    Returns:
        True if all pairs are sufficiently separated.
    """
    n = len(points)
    for i in range(n):
        for j in range(i + 1, n):
            sep = angular_separation_altaz(
                points[i][0], points[i][1],
                points[j][0], points[j][1]
            )
            if sep < min_separation_rad:
                return False
    return True


def compute_determinant_with_replacement(
    current_points: List[Tuple[float, float]],
    replacement_index: int,
    new_point: Tuple[float, float]
) -> float:
    """Compute determinant if one point is replaced.

    Args:
        current_points: Current 3 alignment points as (alt, az) in radians.
        replacement_index: Index (0, 1, or 2) of point to replace.
        new_point: New point (alt, az) in radians.

    Returns:
        Determinant of the configuration with replacement.
    """
    if len(current_points) != 3 or replacement_index not in (0, 1, 2):
        return 0.0

    modified_points = list(current_points)
    modified_points[replacement_index] = new_point

    return compute_geometry_determinant(modified_points)


@dataclass
class CandidateEvaluation:
    """Result of evaluating a replacement candidate.

    Attributes:
        point_index: Index of the alignment point (0, 1, or 2).
        new_det: Determinant after replacement.
        improvement: Change in determinant from current.
        reason: "geometry" or "refresh".
        distance_deg: Distance from candidate position to point (degrees).
        meets_separation: Whether minimum separation is satisfied.
    """
    point_index: int
    new_det: float
    improvement: float
    reason: str
    distance_deg: float
    meets_separation: bool


def evaluate_replacement_candidates(
    current_points: List[Tuple[float, float]],
    candidate_altaz: Tuple[float, float],
    config: GeometryConfig,
    weighted_errors: Optional[List[float]] = None
) -> List[CandidateEvaluation]:
    """Evaluate each existing point as a potential replacement target.

    Returns candidates that meet minimum separation and either:
    - Improve geometry by det_improvement_min, OR
    - Are within refresh_radius with high weighted error

    Args:
        current_points: Current 3 alignment points as (alt, az) in radians.
        candidate_altaz: Candidate position (alt, az) in radians.
        config: GeometryConfig with thresholds.
        weighted_errors: Optional list of mean weighted errors per point.

    Returns:
        List of CandidateEvaluation objects for valid candidates.
    """
    if len(current_points) != 3:
        return []

    current_det = compute_geometry_determinant(current_points)
    min_sep_rad = degrees_to_radians(config.min_separation)
    refresh_rad = degrees_to_radians(config.refresh_radius)

    candidates = []

    for i, point in enumerate(current_points):
        # Calculate distance from candidate to this point
        distance_rad = angular_separation_altaz(
            candidate_altaz[0], candidate_altaz[1],
            point[0], point[1]
        )
        distance_deg = radians_to_degrees(distance_rad)

        # Calculate new determinant
        new_det = compute_determinant_with_replacement(
            current_points, i, candidate_altaz
        )
        improvement = new_det - current_det

        # Check minimum separation with replacement
        modified_points = list(current_points)
        modified_points[i] = candidate_altaz
        meets_separation = check_minimum_separation(modified_points, min_sep_rad)

        if not meets_separation:
            continue

        reason = None

        # Check geometry improvement criterion
        if improvement >= config.det_improvement_min:
            reason = "geometry"

        # Check refresh criterion (within radius with high weighted error)
        elif distance_rad < refresh_rad:
            if weighted_errors and len(weighted_errors) > i:
                if weighted_errors[i] > config.refresh_error_threshold:
                    reason = "refresh"

        if reason:
            candidates.append(CandidateEvaluation(
                point_index=i,
                new_det=new_det,
                improvement=improvement,
                reason=reason,
                distance_deg=distance_deg,
                meets_separation=True
            ))

    return candidates


def select_best_candidate(
    candidates: List[CandidateEvaluation],
    point_timestamps: List[float],  # epoch timestamps
    config: GeometryConfig
) -> Optional[CandidateEvaluation]:
    """Select the best replacement candidate.

    Selection priority:
    1. Refresh candidates (fixing bad data) - oldest first
    2. Geometry improvement - by threshold crossing, oldest tiebreaker

    Args:
        candidates: List of valid CandidateEvaluation objects.
        point_timestamps: Creation timestamps for each point (epoch seconds).
        config: GeometryConfig with thresholds.

    Returns:
        Best CandidateEvaluation or None if no candidates.
    """
    if not candidates:
        return None

    # Priority 1: Refresh candidates
    refresh_candidates = [c for c in candidates if c.reason == "refresh"]
    if refresh_candidates:
        # Pick oldest point
        return min(
            refresh_candidates,
            key=lambda c: point_timestamps[c.point_index]
        )

    # Priority 2: Geometry improvement by threshold crossing
    thresholds = [config.det_excellent, config.det_good, config.det_marginal, 0.0]

    def highest_threshold_crossed(det: float) -> float:
        for t in thresholds:
            if det >= t:
                return t
        return 0.0

    candidate_threshold_pairs = [
        (c, highest_threshold_crossed(c.new_det))
        for c in candidates
    ]
    max_threshold = max(ct[1] for ct in candidate_threshold_pairs)

    top_candidates = [
        ct[0] for ct in candidate_threshold_pairs
        if ct[1] == max_threshold
    ]

    if len(top_candidates) > 1:
        # Multiple at same threshold: pick oldest
        return min(
            top_candidates,
            key=lambda c: point_timestamps[c.point_index]
        )
    else:
        return top_candidates[0]
