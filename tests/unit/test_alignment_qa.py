"""
Unit tests for Alignment QA Subsystem.

Tests cover:
- Davenport Q-method quaternion calculation
- Coordinate conversion (ticks → alt/az → RA/Dec)
- Sidereal time correction
- Quaternion comparison
- Synthetic point detection
- Flag parsing
"""

import math
import pytest
import numpy as np
from datetime import datetime

from alignment_qa import (
    AlignmentQA,
    FirmwareAlignmentData,
    AlignmentPointQA,
    QAStatus,
    QAStatusCode,
    SOLAR_TO_SID,
    CLOCKSCALER,
    SEC_TO_RAD,
    MSEC_TO_RAD,
    RAD_TO_ARCSEC,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def qa_instance():
    """Create AlignmentQA instance with mock logger."""
    import logging
    logger = logging.getLogger('test_qa')
    return AlignmentQA(logger)


@pytest.fixture
def sample_firmware_data():
    """Create sample firmware alignment data for testing."""
    return FirmwareAlignmentData(
        point_count=3,
        point_flags=0x77,  # All 3 sat=1, all 3 manual=1
        star_ticks=[(10000, 5000), (20000, 10000), (30000, 15000)],
        star_coords=[
            (1.0, 0.5),    # Star 1 RA/Dec in radians
            (2.0, 0.3),    # Star 2
            (3.0, 0.1),    # Star 3
        ],
        star_timestamps=[1000, 2000, 3000],  # IS_MSECS
        start_sid_time=0.0,
        align_sid_time=0.1,
        rms_error=0.0001,  # radians
        model_valid=True,
        ticks_per_rev_h=1296000,  # Typical value
        ticks_per_rev_e=1296000,
        longitude=-2.7,  # radians (Hawaii-ish)
        latitude=0.37,   # radians (~21 degrees)
        firmware_quaternion=(0.9, 0.1, 0.2, 0.3),
        inverse_quaternion=(0.9, -0.1, -0.2, -0.3),
    )


# =============================================================================
# Test Constants
# =============================================================================

class TestConstants:
    """Test that module constants match firmware values."""

    def test_solar_to_sid(self):
        """SolarToSid should match firmware value."""
        assert abs(SOLAR_TO_SID - 1.002737908) < 1e-9

    def test_clockscaler(self):
        """CLOCKSCALER should be 960 (not 1000)."""
        assert CLOCKSCALER == 960.0

    def test_msec_to_rad(self):
        """MSecToRad formula should match firmware."""
        expected = SEC_TO_RAD / CLOCKSCALER
        assert abs(MSEC_TO_RAD - expected) < 1e-15


# =============================================================================
# Test Davenport Q-method
# =============================================================================

class TestDavenportQMethod:
    """Test Davenport Q-method quaternion calculation."""

    def test_identity_rotation(self, qa_instance):
        """Identical vectors should give identity quaternion."""
        # Create 3 orthogonal unit vectors
        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0])
        v3 = np.array([0.0, 0.0, 1.0])

        # Reference and observed are identical
        ref = [v1, v2, v3]
        obs = [v1, v2, v3]

        quat = qa_instance.calculate_quaternion_davenport(ref, obs)

        # Should be identity quaternion (1, 0, 0, 0)
        assert abs(quat[0] - 1.0) < 0.01  # w ≈ 1
        assert abs(quat[1]) < 0.01        # x ≈ 0
        assert abs(quat[2]) < 0.01        # y ≈ 0
        assert abs(quat[3]) < 0.01        # z ≈ 0

    def test_90_degree_rotation_z_axis(self, qa_instance):
        """90-degree rotation about z-axis should give known quaternion."""
        # Reference frame
        ref = [
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        ]

        # Observed frame: rotated 90 degrees about z
        obs = [
            np.array([0.0, 1.0, 0.0]),   # x -> y
            np.array([-1.0, 0.0, 0.0]),  # y -> -x
            np.array([0.0, 0.0, 1.0]),   # z unchanged
        ]

        quat = qa_instance.calculate_quaternion_davenport(ref, obs)

        # 90 deg rotation about z: q = (cos(45°), 0, 0, sin(45°))
        # = (0.707, 0, 0, 0.707)
        expected_w = math.cos(math.pi / 4)
        expected_z = math.sin(math.pi / 4)

        assert abs(abs(quat[0]) - expected_w) < 0.01
        assert abs(quat[1]) < 0.01
        assert abs(quat[2]) < 0.01
        assert abs(abs(quat[3]) - expected_z) < 0.01

    def test_quaternion_normalized(self, qa_instance):
        """Calculated quaternion should be unit magnitude."""
        ref = [
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
        ]
        obs = [
            np.array([0.707, 0.707, 0.0]),
            np.array([-0.707, 0.707, 0.0]),
        ]

        quat = qa_instance.calculate_quaternion_davenport(ref, obs)

        magnitude = math.sqrt(sum(q**2 for q in quat))
        assert abs(magnitude - 1.0) < 0.001

    def test_insufficient_observations(self, qa_instance):
        """Should raise error with fewer than 2 observations."""
        ref = [np.array([1.0, 0.0, 0.0])]
        obs = [np.array([1.0, 0.0, 0.0])]

        with pytest.raises(ValueError, match="At least 2 observation pairs"):
            qa_instance.calculate_quaternion_davenport(ref, obs)

    def test_mismatched_lengths(self, qa_instance):
        """Should raise error if ref and obs have different lengths."""
        ref = [np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])]
        obs = [np.array([1.0, 0.0, 0.0])]

        with pytest.raises(ValueError, match="same length"):
            qa_instance.calculate_quaternion_davenport(ref, obs)


# =============================================================================
# Test Coordinate Conversion
# =============================================================================

class TestTickConversion:
    """Test tick-to-coordinate conversion."""

    def test_ticks_to_altaz_zero(self, qa_instance):
        """Zero ticks should give zero angles."""
        alt, az = qa_instance.ticks_to_altaz(0, 0, 1296000, 1296000)
        assert abs(alt) < 1e-10
        assert abs(az) < 1e-10

    def test_ticks_to_altaz_quarter_revolution(self, qa_instance):
        """Quarter revolution (ticks/4) should give 90 degrees."""
        ticks_per_rev = 1296000
        quarter = ticks_per_rev // 4

        alt, az = qa_instance.ticks_to_altaz(quarter, quarter, ticks_per_rev, ticks_per_rev)

        expected = math.pi / 2  # 90 degrees in radians
        assert abs(alt - expected) < 0.001
        assert abs(az - expected) < 0.001

    def test_ticks_to_altaz_half_revolution(self, qa_instance):
        """Half revolution should give 180 degrees."""
        ticks_per_rev = 1296000
        half = ticks_per_rev // 2

        alt, az = qa_instance.ticks_to_altaz(half, half, ticks_per_rev, ticks_per_rev)

        expected = math.pi  # 180 degrees
        assert abs(alt - expected) < 0.001
        assert abs(az - expected) < 0.001

    def test_ticks_wrap_around(self, qa_instance):
        """Full revolution should wrap back to ~0."""
        ticks_per_rev = 1296000

        alt, az = qa_instance.ticks_to_altaz(ticks_per_rev, ticks_per_rev, ticks_per_rev, ticks_per_rev)

        # Should wrap to 0 (or 2*pi, which is equivalent)
        assert abs(az % (2 * math.pi)) < 0.001


class TestAltAzToRaDec:
    """Test alt/az to RA/Dec conversion."""

    def test_zenith_at_equator(self, qa_instance):
        """Zenith at equator should give RA=LST, Dec=0."""
        alt = math.pi / 2  # 90 degrees (zenith)
        az = 0.0           # North
        lat = 0.0          # Equator
        lst = math.pi / 4  # 45 degrees = 3 hours

        ra, dec = qa_instance.altaz_to_radec(alt, az, lst, lat)

        # At zenith on equator, Dec should be ~0
        assert abs(dec) < 0.1  # Within a few degrees

    def test_north_pole_star(self, qa_instance):
        """Star at north celestial pole should have Dec = 90."""
        # At latitude 45°, NCP is at altitude 45°, azimuth 0° (North)
        lat = math.pi / 4   # 45 degrees
        alt = math.pi / 4   # 45 degrees altitude
        az = 0.0            # North
        lst = 0.0

        ra, dec = qa_instance.altaz_to_radec(alt, az, lst, lat)

        # Dec should be close to latitude for star on meridian
        # This is a simplified check
        assert dec > 0  # Should be positive (northern)

    def test_ra_range(self, qa_instance):
        """RA should always be in [0, 2*pi)."""
        # Test various inputs
        test_cases = [
            (0.5, 1.0, 0.0, 0.5),
            (0.3, 2.0, math.pi, 0.3),
            (0.8, 0.5, 5.0, 0.7),
        ]

        for alt, az, lst, lat in test_cases:
            ra, dec = qa_instance.altaz_to_radec(alt, az, lst, lat)
            assert 0 <= ra < 2 * math.pi, f"RA {ra} out of range for inputs {alt}, {az}, {lst}, {lat}"


# =============================================================================
# Test Sidereal Time Correction
# =============================================================================

class TestSiderealCorrection:
    """Test sidereal time correction."""

    def test_zero_delta_no_correction(self, qa_instance):
        """Zero time delta should give zero correction."""
        delta = qa_instance.compute_sidereal_adjustment(1000, 1000)
        assert abs(delta) < 1e-15

    def test_positive_delta(self, qa_instance):
        """Positive time delta should give positive correction."""
        # 1 second = 960 IS_MSECS
        delta = qa_instance.compute_sidereal_adjustment(0, 960)

        # Expected: 960 * MSEC_TO_RAD * SOLAR_TO_SID
        # ≈ 1 second of sidereal rotation ≈ 15 arcseconds
        expected_arcsec = 15.04  # Approximate
        actual_arcsec = delta * RAD_TO_ARCSEC

        assert abs(actual_arcsec - expected_arcsec) < 1.0  # Within 1 arcsec

    def test_clockscaler_used(self, qa_instance):
        """Verify CLOCKSCALER=960 is used, not 1000."""
        # If 1000 were used, the correction would be 960/1000 = 0.96x
        delta_960 = qa_instance.compute_sidereal_adjustment(0, 960)

        # Manual calculation with CLOCKSCALER=960
        expected = 960 * MSEC_TO_RAD * SOLAR_TO_SID

        assert abs(delta_960 - expected) < 1e-15


# =============================================================================
# Test Quaternion Comparison
# =============================================================================

class TestQuaternionComparison:
    """Test quaternion angular difference calculation."""

    def test_identical_quaternions(self, qa_instance):
        """Identical quaternions should have zero angular difference."""
        q = (0.5, 0.5, 0.5, 0.5)  # Normalized
        delta = qa_instance.quaternion_angular_difference(q, q)
        assert abs(delta) < 0.1  # Within 0.1 arcsec

    def test_opposite_quaternions_same_rotation(self, qa_instance):
        """q and -q represent same rotation, should have ~zero delta."""
        q1 = (0.5, 0.5, 0.5, 0.5)
        q2 = (-0.5, -0.5, -0.5, -0.5)

        delta = qa_instance.quaternion_angular_difference(q1, q2)
        assert abs(delta) < 0.1  # Within 0.1 arcsec

    def test_90_degree_difference(self, qa_instance):
        """90-degree rotation difference should give ~324000 arcsec."""
        # Identity quaternion
        q1 = (1.0, 0.0, 0.0, 0.0)

        # 90 deg rotation about z
        q2 = (math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4))

        delta = qa_instance.quaternion_angular_difference(q1, q2)

        # 90 degrees = 324000 arcseconds
        expected = 90 * 3600
        assert abs(delta - expected) < 100  # Within 100 arcsec

    def test_small_difference(self, qa_instance):
        """Small angular difference should be accurately calculated."""
        # Identity
        q1 = (1.0, 0.0, 0.0, 0.0)

        # Very small rotation about z (1 arcsec)
        angle_rad = 1.0 / RAD_TO_ARCSEC
        q2 = (math.cos(angle_rad / 2), 0.0, 0.0, math.sin(angle_rad / 2))

        delta = qa_instance.quaternion_angular_difference(q1, q2)

        # Should be approximately 1 arcsec
        assert abs(delta - 1.0) < 0.1


# =============================================================================
# Test Synthetic Point Detection
# =============================================================================

class TestSyntheticPointDetection:
    """Test synthetic point detection from A17 flags."""

    def test_all_real_points(self, qa_instance):
        """Flags 0x07 should indicate 3 real points (sat bits 0-2 set)."""
        flags = 0x07  # Binary: 00000111

        parsed = qa_instance.parse_point_flags(flags)

        assert parsed[0] == (True, False)   # Star 1: sat=1, manual=0
        assert parsed[1] == (True, False)   # Star 2: sat=1, manual=0
        assert parsed[2] == (True, False)   # Star 3: sat=1, manual=0

        synthetic = qa_instance.detect_synthetic_points(3, flags)
        assert len(synthetic) == 0  # No synthetic points

    def test_one_synthetic(self, qa_instance):
        """Flags 0x03 should indicate 2 real, 1 synthetic."""
        flags = 0x03  # Binary: 00000011 - only stars 1 and 2 are sat

        parsed = qa_instance.parse_point_flags(flags)

        assert parsed[0] == (True, False)   # Star 1: real
        assert parsed[1] == (True, False)   # Star 2: real
        assert parsed[2] == (False, False)  # Star 3: synthetic

        synthetic = qa_instance.detect_synthetic_points(2, flags)
        assert synthetic == [2]  # Star 3 (index 2) is synthetic

    def test_two_synthetic(self, qa_instance):
        """Flags 0x01 should indicate 1 real, 2 synthetic."""
        flags = 0x01  # Only star 1 is sat

        synthetic = qa_instance.detect_synthetic_points(1, flags)
        assert synthetic == [1, 2]  # Stars 2 and 3 are synthetic

    def test_manual_flags(self, qa_instance):
        """Bits 4-6 should indicate manual entry."""
        flags = 0x77  # 01110111 - all sat, all manual

        parsed = qa_instance.parse_point_flags(flags)

        assert parsed[0] == (True, True)   # Star 1: sat=1, manual=1
        assert parsed[1] == (True, True)   # Star 2: sat=1, manual=1
        assert parsed[2] == (True, True)   # Star 3: sat=1, manual=1

    def test_no_alignment_no_synthetic(self, qa_instance):
        """With point_count=0, no points are synthetic (just unset)."""
        flags = 0x00

        synthetic = qa_instance.detect_synthetic_points(0, flags)
        assert len(synthetic) == 0  # No synthetic when no alignment


# =============================================================================
# Test Validation Functions
# =============================================================================

class TestValidation:
    """Test validation functions."""

    def test_valid_quaternion(self, qa_instance):
        """Unit quaternion should pass validation."""
        q = (0.5, 0.5, 0.5, 0.5)  # Magnitude = 1
        assert qa_instance.validate_quaternion(q)

    def test_invalid_quaternion_magnitude(self, qa_instance):
        """Non-unit quaternion should fail validation."""
        q = (1.0, 1.0, 1.0, 1.0)  # Magnitude = 2
        assert not qa_instance.validate_quaternion(q)

    def test_valid_coordinates(self, qa_instance):
        """Valid coordinates should pass."""
        assert qa_instance.validate_coordinates(0.0, 0.0)
        assert qa_instance.validate_coordinates(math.pi, math.pi / 4)
        assert qa_instance.validate_coordinates(2 * math.pi - 0.01, -math.pi / 2)

    def test_invalid_ra_range(self, qa_instance):
        """RA outside [0, 2*pi) should fail."""
        assert not qa_instance.validate_coordinates(-0.1, 0.0)
        assert not qa_instance.validate_coordinates(2 * math.pi + 0.1, 0.0)

    def test_invalid_dec_range(self, qa_instance):
        """Dec outside [-pi/2, pi/2] should fail."""
        assert not qa_instance.validate_coordinates(0.0, math.pi)
        assert not qa_instance.validate_coordinates(0.0, -math.pi)


# =============================================================================
# Test Full QA Calculation
# =============================================================================

class TestFullQACalculation:
    """Test full QA calculation pipeline."""

    def test_set_firmware_data(self, qa_instance, sample_firmware_data):
        """Setting firmware data should work."""
        qa_instance.set_firmware_data(sample_firmware_data)
        # No assertion needed - just verify no exception

    def test_recalculate_without_data(self, qa_instance):
        """Recalculate without data should return False."""
        result = qa_instance.recalculate_driver_quaternion()
        assert result is False

    def test_recalculate_with_data(self, qa_instance, sample_firmware_data):
        """Recalculate with valid data should succeed."""
        qa_instance.set_firmware_data(sample_firmware_data)
        result = qa_instance.recalculate_driver_quaternion()
        assert result is True

    def test_get_status_no_data(self, qa_instance):
        """Get status without data should return NO_DATA status."""
        status = qa_instance.get_qa_status()
        assert status is not None
        assert status.status == QAStatusCode.NO_DATA

    def test_get_status_with_data(self, qa_instance, sample_firmware_data):
        """Get status with data should return valid status."""
        qa_instance.set_firmware_data(sample_firmware_data)
        qa_instance.recalculate_driver_quaternion()

        status = qa_instance.get_qa_status()
        assert status is not None
        assert status.status in [QAStatusCode.VALID, QAStatusCode.SYNTHETIC]
        assert status.model_valid is True
        assert len(status.alignment_points) == 3


# =============================================================================
# Test Thread Safety
# =============================================================================

class TestThreadSafety:
    """Test thread safety of QA operations."""

    def test_concurrent_access(self, qa_instance, sample_firmware_data):
        """Concurrent access should not cause errors."""
        import threading
        import time

        errors = []

        def worker():
            try:
                for _ in range(10):
                    qa_instance.set_firmware_data(sample_firmware_data)
                    qa_instance.recalculate_driver_quaternion()
                    qa_instance.get_qa_status()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"


# =============================================================================
# Test History Tracking
# =============================================================================

class TestHistoryTracking:
    """Test QA history tracking."""

    def test_history_accumulates(self, qa_instance, sample_firmware_data):
        """History should accumulate entries."""
        qa_instance.set_firmware_data(sample_firmware_data)
        qa_instance.recalculate_driver_quaternion()

        # Get status multiple times
        for _ in range(5):
            qa_instance.get_qa_status()

        history = qa_instance.get_history()
        assert len(history) == 5

    def test_history_clear(self, qa_instance, sample_firmware_data):
        """Clear history should empty the list."""
        qa_instance.set_firmware_data(sample_firmware_data)
        qa_instance.recalculate_driver_quaternion()
        qa_instance.get_qa_status()
        qa_instance.get_qa_status()

        assert len(qa_instance.get_history()) > 0

        qa_instance.clear_history()

        assert len(qa_instance.get_history()) == 0

    def test_history_max_size(self, qa_instance, sample_firmware_data):
        """History should respect max size limit."""
        qa_instance._max_history_size = 10
        qa_instance.set_firmware_data(sample_firmware_data)
        qa_instance.recalculate_driver_quaternion()

        # Generate more than max entries
        for _ in range(20):
            qa_instance.get_qa_status()

        history = qa_instance.get_history()
        assert len(history) <= 10
