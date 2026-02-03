# -*- coding: utf-8 -*-
"""
Unit tests for alignment geometry calculations.

Tests determinant calculation, angular separation, candidate evaluation,
and selection logic without requiring any hardware.
"""

import pytest
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from alignment_geometry import (
    compute_geometry_determinant,
    angular_separation_altaz,
    angular_separation_radec,
    radians_to_arcseconds,
    degrees_to_radians,
    radians_to_degrees,
    compute_weight_for_distance,
    check_minimum_separation,
    compute_determinant_with_replacement,
    evaluate_replacement_candidates,
    select_best_candidate,
    GeometryConfig,
    CandidateEvaluation,
)


class TestDeterminantCalculation:
    """Test geometry determinant calculation."""

    @pytest.mark.unit
    def test_three_orthogonal_points_near_unity(self):
        """Three orthogonal points should give determinant near 1.0."""
        # Points at zenith, horizon east, horizon north
        # zenith: alt=90deg, az=0
        # horizon east: alt=0, az=90deg
        # horizon north: alt=0, az=0
        points = [
            (math.pi / 2, 0),           # zenith
            (0, math.pi / 2),           # horizon east
            (0, 0),                      # horizon north
        ]
        det = compute_geometry_determinant(points)
        assert 0.99 <= det <= 1.01

    @pytest.mark.unit
    def test_coplanar_points_zero_determinant(self):
        """Three coplanar points should give determinant near 0."""
        # All points on the horizon (alt=0)
        points = [
            (0, 0),                      # horizon north
            (0, math.pi / 2),           # horizon east
            (0, math.pi),               # horizon south
        ]
        det = compute_geometry_determinant(points)
        assert det < 0.01

    @pytest.mark.unit
    def test_two_points_returns_zero(self):
        """Two points should return 0 (need 3 for determinant)."""
        points = [(0.5, 0.5), (1.0, 1.0)]
        det = compute_geometry_determinant(points)
        assert det == 0.0

    @pytest.mark.unit
    def test_four_points_returns_zero(self):
        """Four points should return 0 (need exactly 3)."""
        points = [(0.5, 0.5), (1.0, 1.0), (0.5, 1.0), (1.0, 0.5)]
        det = compute_geometry_determinant(points)
        assert det == 0.0

    @pytest.mark.unit
    def test_empty_list_returns_zero(self):
        """Empty list should return 0."""
        det = compute_geometry_determinant([])
        assert det == 0.0

    @pytest.mark.unit
    def test_equilateral_triangle_on_horizon(self):
        """Equilateral triangle on horizon should give moderate det."""
        # 120 degree spacing on horizon
        points = [
            (0, 0),
            (0, 2 * math.pi / 3),
            (0, 4 * math.pi / 3),
        ]
        det = compute_geometry_determinant(points)
        # Coplanar, should be ~0
        assert det < 0.01

    @pytest.mark.unit
    def test_good_spread_configuration(self):
        """Well-spread configuration should give high determinant."""
        # Points at different altitudes and azimuths
        points = [
            (math.radians(60), math.radians(0)),      # high altitude north
            (math.radians(30), math.radians(120)),    # medium altitude
            (math.radians(45), math.radians(240)),    # medium altitude
        ]
        det = compute_geometry_determinant(points)
        assert det > 0.3


class TestAngularSeparation:
    """Test angular separation calculations."""

    @pytest.mark.unit
    def test_same_point_zero_separation(self):
        """Same point should have zero separation."""
        sep = angular_separation_altaz(0.5, 1.0, 0.5, 1.0)
        assert sep < 1e-10

    @pytest.mark.unit
    def test_opposite_horizon_points(self):
        """Points 180 degrees apart on horizon should have pi separation."""
        sep = angular_separation_altaz(0, 0, 0, math.pi)
        assert abs(sep - math.pi) < 0.01

    @pytest.mark.unit
    def test_zenith_to_horizon(self):
        """Zenith to any horizon point should be 90 degrees."""
        sep = angular_separation_altaz(math.pi / 2, 0, 0, 0)
        assert abs(sep - math.pi / 2) < 0.01

    @pytest.mark.unit
    def test_known_separation(self):
        """Test a known separation value."""
        # 45 degrees altitude difference at same azimuth
        alt1 = math.radians(45)
        alt2 = math.radians(90)  # zenith
        sep = angular_separation_altaz(alt1, 0, alt2, 0)
        assert abs(radians_to_degrees(sep) - 45) < 0.1

    @pytest.mark.unit
    def test_radec_same_point_zero(self):
        """Same RA/Dec point should have zero separation."""
        sep = angular_separation_radec(0.5, 0.5, 0.5, 0.5)
        assert sep < 1e-10

    @pytest.mark.unit
    def test_radec_pole_to_equator(self):
        """Pole to equator should be 90 degrees."""
        sep = angular_separation_radec(0, math.pi / 2, 0, 0)  # NCP to equator
        assert abs(sep - math.pi / 2) < 0.01


class TestUnitConversions:
    """Test unit conversion functions."""

    @pytest.mark.unit
    def test_radians_to_arcseconds(self):
        """Test radians to arcseconds conversion."""
        # 1 radian ≈ 206264.806 arcseconds
        result = radians_to_arcseconds(1.0)
        assert abs(result - 206264.806) < 0.01

    @pytest.mark.unit
    def test_degrees_to_radians(self):
        """Test degrees to radians conversion."""
        result = degrees_to_radians(180.0)
        assert abs(result - math.pi) < 1e-10

    @pytest.mark.unit
    def test_radians_to_degrees(self):
        """Test radians to degrees conversion."""
        result = radians_to_degrees(math.pi)
        assert abs(result - 180.0) < 1e-10


class TestWeightCalculation:
    """Test distance-based weight calculation."""

    @pytest.mark.unit
    def test_zero_distance_weight_is_one(self):
        """Zero distance should give weight of 1.0."""
        weight = compute_weight_for_distance(0.0, 30.0)
        assert abs(weight - 1.0) < 1e-10

    @pytest.mark.unit
    def test_at_scale_radius_weight_is_half(self):
        """At scale radius, weight should be 0.5."""
        weight = compute_weight_for_distance(30.0, 30.0)
        assert abs(weight - 0.5) < 1e-10

    @pytest.mark.unit
    def test_large_distance_low_weight(self):
        """Large distance should give low weight."""
        weight = compute_weight_for_distance(90.0, 30.0)
        # 1 / (1 + 9) = 0.1
        assert abs(weight - 0.1) < 1e-10

    @pytest.mark.unit
    def test_zero_scale_radius_returns_zero(self):
        """Zero scale radius should return 0 weight."""
        weight = compute_weight_for_distance(10.0, 0.0)
        assert weight == 0.0

    @pytest.mark.unit
    def test_negative_scale_radius_returns_zero(self):
        """Negative scale radius should return 0 weight."""
        weight = compute_weight_for_distance(10.0, -5.0)
        assert weight == 0.0


class TestMinimumSeparation:
    """Test minimum separation checking."""

    @pytest.mark.unit
    def test_well_separated_points_pass(self):
        """Points that are well separated should pass."""
        points = [
            (math.radians(30), 0),
            (math.radians(30), math.radians(120)),
            (math.radians(30), math.radians(240)),
        ]
        min_sep = degrees_to_radians(10.0)
        assert check_minimum_separation(points, min_sep) is True

    @pytest.mark.unit
    def test_close_points_fail(self):
        """Points that are too close should fail."""
        points = [
            (math.radians(45), 0),
            (math.radians(46), 0),  # Only 1 degree apart
            (math.radians(45), math.radians(90)),
        ]
        min_sep = degrees_to_radians(10.0)
        assert check_minimum_separation(points, min_sep) is False

    @pytest.mark.unit
    def test_slightly_above_threshold(self):
        """Points slightly above threshold should pass."""
        # Two points about 16 degrees apart (slightly above 15 threshold)
        points = [
            (math.radians(44), 0),
            (math.radians(60), 0),
            (math.radians(44), math.radians(90)),
        ]
        min_sep = degrees_to_radians(15.0)
        assert check_minimum_separation(points, min_sep) is True


class TestDeterminantWithReplacement:
    """Test determinant calculation with point replacement."""

    @pytest.mark.unit
    def test_replacement_changes_determinant(self):
        """Replacing a point should change the determinant."""
        points = [
            (math.radians(30), 0),
            (math.radians(30), math.radians(90)),
            (math.radians(30), math.radians(180)),
        ]
        original_det = compute_geometry_determinant(points)

        new_point = (math.radians(60), math.radians(45))
        new_det = compute_determinant_with_replacement(points, 0, new_point)

        assert new_det != original_det

    @pytest.mark.unit
    def test_invalid_index_returns_zero(self):
        """Invalid replacement index should return 0."""
        points = [(0.5, 0.5), (1.0, 1.0), (0.5, 1.0)]
        det = compute_determinant_with_replacement(points, 5, (0.7, 0.7))
        assert det == 0.0

    @pytest.mark.unit
    def test_wrong_point_count_returns_zero(self):
        """Wrong number of points should return 0."""
        points = [(0.5, 0.5), (1.0, 1.0)]  # Only 2 points
        det = compute_determinant_with_replacement(points, 0, (0.7, 0.7))
        assert det == 0.0


class TestCandidateEvaluation:
    """Test replacement candidate evaluation."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return GeometryConfig(
            det_excellent=0.80,
            det_good=0.60,
            det_marginal=0.40,
            det_improvement_min=0.10,
            min_separation=15.0,
            refresh_radius=10.0,
            scale_radius=30.0,
            refresh_error_threshold=60.0,
        )

    @pytest.fixture
    def coplanar_points(self):
        """Create coplanar points (poor geometry)."""
        return [
            (0, 0),
            (0, math.radians(90)),
            (0, math.radians(180)),
        ]

    @pytest.mark.unit
    def test_geometry_improvement_candidate(self, config, coplanar_points):
        """Should identify candidate that improves geometry."""
        # A point at high altitude will improve coplanar geometry
        candidate = (math.radians(60), math.radians(45))

        candidates = evaluate_replacement_candidates(
            coplanar_points, candidate, config
        )

        # Should find at least one geometry improvement candidate
        geometry_candidates = [c for c in candidates if c.reason == "geometry"]
        assert len(geometry_candidates) > 0

    @pytest.mark.unit
    def test_refresh_candidate_with_high_error(self, config):
        """Should identify refresh candidate near point with high error."""
        points = [
            (math.radians(30), 0),
            (math.radians(30), math.radians(90)),
            (math.radians(30), math.radians(180)),
        ]

        # Candidate very close to first point (within refresh radius)
        candidate = (math.radians(31), math.radians(2))

        # First point has high weighted error
        weighted_errors = [100.0, 10.0, 10.0]

        candidates = evaluate_replacement_candidates(
            points, candidate, config, weighted_errors
        )

        refresh_candidates = [c for c in candidates if c.reason == "refresh"]
        assert len(refresh_candidates) > 0

    @pytest.mark.unit
    def test_no_candidates_when_separation_violated(self, config):
        """Should reject candidates that violate minimum separation."""
        points = [
            (math.radians(45), 0),
            (math.radians(45), math.radians(90)),
            (math.radians(45), math.radians(180)),
        ]

        # Candidate too close to second point
        candidate = (math.radians(46), math.radians(91))

        candidates = evaluate_replacement_candidates(
            points, candidate, config
        )

        # Any candidates should have meets_separation = True
        # (candidates that don't meet separation are filtered out)
        for c in candidates:
            assert c.meets_separation is True

    @pytest.mark.unit
    def test_empty_candidates_for_wrong_point_count(self, config):
        """Should return empty list for wrong number of points."""
        points = [(0.5, 0.5), (1.0, 1.0)]  # Only 2 points
        candidate = (0.7, 0.7)

        candidates = evaluate_replacement_candidates(
            points, candidate, config
        )

        assert candidates == []


class TestCandidateSelection:
    """Test best candidate selection logic."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return GeometryConfig(
            det_excellent=0.80,
            det_good=0.60,
            det_marginal=0.40,
            det_improvement_min=0.10,
        )

    @pytest.mark.unit
    def test_refresh_prioritized_over_geometry(self, config):
        """Refresh candidates should be selected over geometry candidates."""
        candidates = [
            CandidateEvaluation(0, 0.7, 0.3, "geometry", 30.0, True),
            CandidateEvaluation(1, 0.5, 0.1, "refresh", 5.0, True),
        ]
        timestamps = [100.0, 200.0, 150.0]

        best = select_best_candidate(candidates, timestamps, config)

        assert best.reason == "refresh"
        assert best.point_index == 1

    @pytest.mark.unit
    def test_oldest_refresh_selected(self, config):
        """Among refresh candidates, oldest point should be selected."""
        candidates = [
            CandidateEvaluation(0, 0.5, 0.1, "refresh", 5.0, True),
            CandidateEvaluation(1, 0.5, 0.1, "refresh", 5.0, True),
        ]
        timestamps = [300.0, 100.0, 200.0]  # Point 1 is oldest

        best = select_best_candidate(candidates, timestamps, config)

        assert best.point_index == 1

    @pytest.mark.unit
    def test_higher_threshold_crossing_preferred(self, config):
        """Candidate crossing higher threshold should be preferred."""
        candidates = [
            CandidateEvaluation(0, 0.65, 0.2, "geometry", 30.0, True),  # crosses good
            CandidateEvaluation(1, 0.85, 0.3, "geometry", 30.0, True),  # crosses excellent
        ]
        timestamps = [100.0, 200.0, 150.0]

        best = select_best_candidate(candidates, timestamps, config)

        assert best.point_index == 1  # crosses excellent threshold

    @pytest.mark.unit
    def test_oldest_selected_for_same_threshold(self, config):
        """Among same threshold crossers, oldest should be selected."""
        candidates = [
            CandidateEvaluation(0, 0.65, 0.2, "geometry", 30.0, True),
            CandidateEvaluation(1, 0.68, 0.25, "geometry", 30.0, True),
        ]
        # Both cross "good" threshold (0.60), point 0 is oldest
        timestamps = [50.0, 200.0, 150.0]

        best = select_best_candidate(candidates, timestamps, config)

        assert best.point_index == 0

    @pytest.mark.unit
    def test_no_candidates_returns_none(self, config):
        """Empty candidate list should return None."""
        best = select_best_candidate([], [100.0, 200.0, 150.0], config)
        assert best is None
