# -*- coding: utf-8 -*-
"""Unit tests for the Phase B1 alignment FINISH work (F1-F7).

Covers the fixed plate-solver seam (F1/AM2), the J2000->JNOW epoch gate
(F2/AM4), the wired decision engine (F3/AM1), the firmware 0x12/0x13 issuance
(F4/AM3), and get_status() responsiveness during a capture (F5/AM5).

No camera / serial hardware is required; the camera, detector, solver and
epoch/serial callbacks are faked/mocked.
"""

import os
import struct
import sys
import threading
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from alignment_monitor import (
    AlignmentMonitor,
    AlignmentState,
    DecisionResult,
    ReplacementCandidate,
    AlignmentPointRecord,
)
from plate_solver import SolveResult
from astro_services import AstroServices


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeCapture:
    def __init__(self, width=640, height=480):
        self.image = np.zeros((height, width), dtype=np.float32)
        self.width = width
        self.height = height


class FakeCamera:
    """Fake camera source; capture() may block on an event for the F5 test."""

    def __init__(self, block_event=None, started_event=None):
        self.source_type = "fake"
        self._block_event = block_event
        self._started_event = started_event
        self.disconnected = False

    def is_connected(self):
        return True

    def connect(self):
        return True

    def get_info(self):
        return {"name": "fake-cam"}

    def get_error_message(self):
        return ""

    def capture(self, exposure_time, binning):
        if self._started_event is not None:
            self._started_event.set()
        if self._block_event is not None:
            self._block_event.wait(timeout=5.0)
        return FakeCapture()

    def disconnect(self):
        self.disconnected = True


class FakeDetection:
    def __init__(self, n=8):
        self.centroids = np.array([[float(i), float(i)] for i in range(n)])
        self.star_count = n


class FakeDetector:
    def detect_stars(self, image, threshold_sigma=5.0, max_stars=50):
        return FakeDetection()


class FakeSolver:
    """Records solve_from_centroids call args; returns a fixed SolveResult."""

    def __init__(self, result):
        self._result = result
        self.calls = []

    def solve_from_centroids(self, centroids, image_width, image_height,
                             fov_estimate=None, timeout_ms=None):
        self.calls.append(dict(
            centroids=centroids, image_width=image_width,
            image_height=image_height, fov_estimate=fov_estimate,
            timeout_ms=timeout_ms,
        ))
        return self._result


def make_config():
    """Numeric alignment config covering every field the paths below read."""
    return SimpleNamespace(
        alignment_enabled=True,
        alignment_qa_enabled=False,
        alignment_exposure_time=0.01,
        alignment_binning=1,
        alignment_detection_threshold=5.0,
        alignment_max_stars=50,
        alignment_fov_estimate=1.0,
        alignment_verbose_logging=False,
        alignment_error_threshold=60.0,
        alignment_interval=5.0,
        # Decision-engine thresholds (arcsec)
        alignment_error_ignore=30.0,
        alignment_error_sync=120.0,
        alignment_error_max=600.0,
        alignment_lockout_post_sync=30.0,
        alignment_lockout_post_align=60.0,
        alignment_scale_radius=20.0,
        alignment_health_window=1800.0,
        alignment_health_alert_threshold=5,
        alignment_database_path=None,
    )


def make_monitor(config=None, solver_result=None, camera=None):
    """AlignmentMonitor with components injected (start() bypassed)."""
    config = config or make_config()
    mon = AlignmentMonitor(config, Mock())
    mon._camera_source = camera or FakeCamera()
    mon._star_detector = FakeDetector()
    if solver_result is None:
        solver_result = SolveResult(
            success=True, ra=5.5, dec=22.0, roll=0.0, fov=1.0,
            solve_time_ms=10.0, matched_stars=8, rmse=1.0, confidence=0.9,
        )
    mon._plate_solver = FakeSolver(solver_result)
    return mon


def make_astro():
    from astropy.coordinates import EarthLocation
    import astropy.units as u
    loc = EarthLocation(lat=45.0 * u.deg, lon=-93.0 * u.deg, height=250.0 * u.m)
    return AstroServices(location_provider=lambda: loc)


# ---------------------------------------------------------------------------
# F2 / AM4 -- the epoch gate
# ---------------------------------------------------------------------------

class TestEpochGate:

    @pytest.mark.unit
    def test_perfect_pointing_yields_near_zero_error_post_conversion(self):
        """A perfect J2000 solve vs the mount JNOW position -> ~0 error once
        the solve is converted to JNOW (F2/AM4)."""
        from astropy.time import Time
        astro = make_astro()
        t = Time("2026-07-11T05:00:00", scale="utc")

        ra_icrs, dec_icrs = 5.5, 22.0  # the true sky direction (J2000)
        # Mount reports the SAME direction in its of-date (JNOW) frame.
        ra_jnow, dec_jnow = astro.icrs_to_jnow(ra_icrs, dec_icrs, t)

        solver_result = SolveResult(
            success=True, ra=ra_icrs, dec=dec_icrs, roll=0.0, fov=1.0,
            solve_time_ms=10.0, matched_stars=8, rmse=1.0, confidence=0.9,
        )
        mon = make_monitor(solver_result=solver_result)
        mon.set_mount_position_callback(lambda: (ra_jnow, dec_jnow))
        # Pin the conversion epoch to t so the assertion is deterministic.
        mon.set_epoch_convert_callback(lambda ra, dec, _t: astro.icrs_to_jnow(ra, dec, t))

        point = mon._perform_measurement()
        assert point is not None
        # Post-conversion error is essentially zero (well under 1 arcsec).
        assert point.total_error < 1.0
        # The STORED solved coords are in the mount JNOW frame, not raw J2000.
        assert point.solved_ra == pytest.approx(ra_jnow, abs=1e-6)
        assert point.solved_dec == pytest.approx(dec_jnow, abs=1e-6)

    @pytest.mark.unit
    def test_without_conversion_error_is_large(self):
        """Distinguishing check: differencing raw J2000 against JNOW fabricates
        ~15 arcmin of error -- proving the conversion is load-bearing."""
        from astropy.time import Time
        astro = make_astro()
        t = Time("2026-07-11T05:00:00", scale="utc")
        ra_icrs, dec_icrs = 5.5, 22.0
        ra_jnow, dec_jnow = astro.icrs_to_jnow(ra_icrs, dec_icrs, t)

        mon = make_monitor()
        # Raw J2000 solve vs JNOW mount (the pre-fix AM4 bug).
        _, _, total = mon._calculate_error(ra_jnow, dec_jnow, ra_icrs, dec_icrs)
        assert total > 120.0  # above error_sync -- the fabricated ~15' bias

    @pytest.mark.unit
    def test_measurement_skipped_without_epoch_callback(self):
        """The epoch gate is mandatory: no converter -> no measurement (F2)."""
        mon = make_monitor()
        mon.set_mount_position_callback(lambda: (5.5, 22.0))
        # deliberately NOT setting the epoch-convert callback
        assert mon._perform_measurement() is None
        assert mon._measurement_count == 0


# ---------------------------------------------------------------------------
# F1 / AM2 -- the fixed plate-solver seam
# ---------------------------------------------------------------------------

class TestSolverSeam:

    @pytest.mark.unit
    def test_start_constructs_plate_solver_with_correct_arg_order(self, monkeypatch):
        """start() must construct PlateSolver(logger, fov_estimate, database_path)
        -- the old (database_path, logger) order raised AttributeError (F1/AM2)."""
        import alignment_monitor as am
        captured = {}

        class SpySolver:
            def __init__(self, logger, fov_estimate=1.0, database_path=None):
                captured['logger'] = logger
                captured['fov_estimate'] = fov_estimate
                captured['database_path'] = database_path

            def is_available(self):
                return True

        monkeypatch.setattr(am, "PlateSolver", SpySolver)
        monkeypatch.setattr(am, "create_camera_source", lambda cfg, logger: FakeCamera())
        monkeypatch.setattr(am.StarDetector, "is_available", staticmethod(lambda: True))

        cfg = make_config()
        cfg.alignment_database_path = "some_db.npz"
        mon = AlignmentMonitor(cfg, Mock())
        assert mon.start() is True
        # logger bound to the logger (not the db-path string); db-path by keyword.
        assert captured['logger'] is mon._logger
        assert captured['database_path'] == "some_db.npz"
        assert captured['fov_estimate'] == cfg.alignment_fov_estimate
        mon.stop()

    @pytest.mark.unit
    def test_solve_called_with_positional_wh_and_timeout(self):
        """solve_from_centroids gets width/height as two positionals + a timeout,
        and .ra/.dec are read (not .ra_hours/.dec_degrees) (F1/AM2)."""
        astro = make_astro()
        from astropy.time import Time
        t = Time("2026-07-11T05:00:00", scale="utc")
        mon = make_monitor()
        mon.set_mount_position_callback(lambda: (5.5, 22.0))
        mon.set_epoch_convert_callback(lambda ra, dec, _t: astro.icrs_to_jnow(ra, dec, t))

        point = mon._perform_measurement()
        assert point is not None
        call = mon._plate_solver.calls[0]
        assert call['image_width'] == 640
        assert call['image_height'] == 480
        assert call['timeout_ms'] == AlignmentMonitor.SOLVE_TIMEOUT_MS

    @pytest.mark.unit
    def test_failed_solve_guarded_by_success_flag(self):
        """A failed solve (success=False, ra=dec=0.0) must NOT publish a point;
        the old `is None` guard let ra=0/dec=0 through (F1/AM2)."""
        failed = SolveResult(
            success=False, ra=0.0, dec=0.0, roll=0.0, fov=0.0,
            solve_time_ms=0.0, matched_stars=0, rmse=0.0, confidence=0.0,
            error_message="No solution found",
        )
        mon = make_monitor(solver_result=failed)
        mon.set_mount_position_callback(lambda: (5.5, 22.0))
        mon.set_epoch_convert_callback(lambda ra, dec, _t: (ra, dec))
        assert mon._perform_measurement() is None
        assert mon._measurement_count == 0


# ---------------------------------------------------------------------------
# F3 / AM1 -- the decision engine, wired and exercised
# ---------------------------------------------------------------------------

def _measurement_point(total_error):
    from alignment_monitor import AlignmentPoint
    return AlignmentPoint(
        timestamp=datetime.now(), mount_ra=5.5, mount_dec=22.0,
        solved_ra=5.5, solved_dec=22.0, ra_error=total_error, dec_error=0.0,
        total_error=total_error, solve_time_ms=10.0, stars_detected=8,
        confidence=0.9,
    )


class TestDecisionEngine:

    @pytest.mark.unit
    def test_lockout_branch(self):
        mon = make_monitor()
        mon._last_measurement = _measurement_point(500.0)
        mon._lockout_until = datetime.now() + timedelta(seconds=60)
        assert mon.evaluate() == DecisionResult.LOCKOUT

    @pytest.mark.unit
    def test_ignorable_error_no_action(self):
        mon = make_monitor()
        mon._last_measurement = _measurement_point(10.0)  # < error_ignore (30)
        assert mon.evaluate() == DecisionResult.NO_ACTION

    @pytest.mark.unit
    def test_sync_fallback_when_no_candidates(self):
        mon = make_monitor()
        mon._last_measurement = _measurement_point(200.0)  # > error_sync (120)
        sync = Mock(return_value=True)
        mon.set_sync_callback(sync)
        result = mon.evaluate()
        assert result == DecisionResult.SYNC
        sync.assert_called_once()
        assert mon._lockout_until is not None  # post-sync lockout armed

    @pytest.mark.unit
    def test_align_branch_issues_firmware_calls(self, monkeypatch):
        mon = make_monitor()
        mon._last_measurement = _measurement_point(700.0)  # > error_max
        # Force a replacement candidate without needing real geometry.
        rec = AlignmentPointRecord(
            index=2, equatorial=(0.0, 0.0), altaz=(0.5, 0.5),
            ticks=(10, 20), timestamp=datetime.now(),
        )
        candidate = ReplacementCandidate(
            point=rec, new_det=0.5, improvement=0.1, reason="geometry", distance=10.0,
        )
        monkeypatch.setattr(mon, "_find_replacement_candidates", lambda: [candidate])
        monkeypatch.setattr(mon, "_select_replacement_candidate", lambda c: candidate)

        align_cb = Mock(return_value=(True, 0))
        perform_cb = Mock(return_value=(True, 0))
        mon.set_align_point_callback(align_cb)
        mon.set_perform_alignment_callback(perform_cb)

        result = mon.evaluate()
        assert result == DecisionResult.ALIGN
        align_cb.assert_called_once_with(2, 5.5, 22.0)
        perform_cb.assert_called_once()


# ---------------------------------------------------------------------------
# F4 / AM3 -- firmware 0x12 / 0x13 issuance (mock serial, frame bytes)
# ---------------------------------------------------------------------------

class TestFirmwareIssuance:

    @pytest.mark.unit
    def test_align_point_issues_0x12_with_packed_payload(self):
        from tts160_serial import SerialManager
        from tts160_types import SetCommand
        mgr = SerialManager.__new__(SerialManager)
        mgr._logger = Mock()
        mgr.execute_set_command = Mock(return_value=[(0, 0)])

        success, err = mgr.align_point(2, 12.5, 45.0)
        assert (success, err) == (True, 0)
        cmd_id, data = mgr.execute_set_command.call_args[0][:2]
        assert cmd_id == SetCommand.ALIGN_POINT == 0x12
        assert data == struct.pack('<Bff', 2, 12.5, 45.0)

    @pytest.mark.unit
    def test_perform_alignment_issues_0x13_no_payload(self):
        from tts160_serial import SerialManager
        from tts160_types import SetCommand
        mgr = SerialManager.__new__(SerialManager)
        mgr._logger = Mock()
        mgr.execute_set_command = Mock(return_value=[(0, 0)])

        success, err = mgr.perform_alignment()
        assert (success, err) == (True, 0)
        cmd_id, data = mgr.execute_set_command.call_args[0][:2]
        assert cmd_id == SetCommand.PERFORM_ALIGNMENT == 0x13
        assert data == b''

    @pytest.mark.unit
    def test_align_point_frame_bytes_on_wire(self):
        """The 0x12 wire frame carries the base-36 head + the packed payload."""
        from tts160_serial import V357Protocol
        from tts160_types import SetCommand
        payload = struct.pack('<Bff', 2, 12.5, 45.0)
        frame = V357Protocol.build_set_command_bytes(SetCommand.ALIGN_POINT, payload)
        assert frame.startswith(b":*!S ")
        assert frame.endswith(b'#')
        assert payload in frame
        # length byte precedes the payload
        assert bytes([len(payload)]) + payload in frame


# ---------------------------------------------------------------------------
# B1.1 -- align_point index contract: driver 0-based == firmware 0x12 range
#
# Firmware authority: TTS-Central central/binary.c case BINARY_CMD_ALIGN_POINT
# (0x12) documents "[0] point_index (uint8_t, 0-2)" and rejects index > 2 with
# error 1 (invalid index).  The driver convention is re-ranged to 0-based so the
# engine-produced index == the list position == the firmware-accepted index.
# ---------------------------------------------------------------------------

class TestAlignPointIndexContract:

    def _mgr(self):
        from tts160_serial import SerialManager
        mgr = SerialManager.__new__(SerialManager)
        mgr._logger = Mock()
        mgr.execute_set_command = Mock(return_value=[(0, 0)])
        return mgr

    @pytest.mark.unit
    @pytest.mark.parametrize("index", [0, 1, 2])
    def test_all_valid_firmware_indices_pack_on_wire(self, index):
        """Each firmware-valid index (0, 1, 2) is accepted and packed raw."""
        mgr = self._mgr()
        success, err = mgr.align_point(index, 12.5, 45.0)
        assert (success, err) == (True, 0)
        cmd_id, data = mgr.execute_set_command.call_args[0][:2]
        from tts160_types import SetCommand
        assert cmd_id == SetCommand.ALIGN_POINT == 0x12
        assert data == struct.pack('<Bff', index, 12.5, 45.0)

    @pytest.mark.unit
    @pytest.mark.parametrize("index", [-1, 3, 4])
    def test_out_of_range_index_rejected_invalid_index_code(self, index):
        """Out-of-range index -> (False, 1) invalid-index; no wire command."""
        mgr = self._mgr()
        success, err = mgr.align_point(index, 12.5, 45.0)
        assert (success, err) == (False, 1)
        mgr.execute_set_command.assert_not_called()

    @pytest.mark.unit
    def test_engine_produced_index_equals_firmware_accepted_index(self):
        """End-to-end pin: the index the engine builds from firmware data is
        0-based, equals its list position, and is exactly what align_point packs
        onto the wire (engine-produced index == firmware-accepted index)."""
        from TTS160Device import TTS160Device

        # A16=3 points; nonzero ticks-per-rev; arbitrary per-point ticks/coords.
        data = {'A16': 3, 'A17': 0, 'M8': 1_000_000, 'M9': 1_000_000}
        for i in range(3):
            data[f'A{4 + i * 2}'] = 100 * (i + 1)     # h_ticks
            data[f'A{5 + i * 2}'] = 200 * (i + 1)     # e_ticks
            data[f'A{10 + i * 2}'] = 0.1 * (i + 1)    # ra_rad
            data[f'A{11 + i * 2}'] = 0.2 * (i + 1)    # dec_rad

        dev = TTS160Device.__new__(TTS160Device)
        dev._logger = Mock()
        dev._serial_manager = Mock()
        dev._serial_manager.query_variable_group = Mock(return_value=data)

        records = dev._get_alignment_data_for_alignment()
        assert len(records) == 3
        # Engine convention: 0-based, index == list position, firmware-valid set.
        assert [r.index for r in records] == [0, 1, 2]

        # Each engine-produced index packs onto the wire unchanged and is accepted.
        mgr = self._mgr()
        for r in records:
            mgr.execute_set_command.reset_mock()
            success, err = mgr.align_point(r.index, 12.5, 45.0)
            assert (success, err) == (True, 0)
            _, wire = mgr.execute_set_command.call_args[0][:2]
            assert wire == struct.pack('<Bff', r.index, 12.5, 45.0)


# ---------------------------------------------------------------------------
# F5 / AM5 -- get_status() responsive during a capture
# ---------------------------------------------------------------------------

class TestLockResponsiveness:

    @pytest.mark.unit
    def test_get_status_responsive_during_capture(self):
        block = threading.Event()
        started = threading.Event()
        cam = FakeCamera(block_event=block, started_event=started)
        astro = make_astro()
        from astropy.time import Time
        t = Time("2026-07-11T05:00:00", scale="utc")
        mon = make_monitor(camera=cam)
        mon.set_mount_position_callback(lambda: (5.5, 22.0))
        mon.set_epoch_convert_callback(lambda ra, dec, _t: astro.icrs_to_jnow(ra, dec, t))

        worker = threading.Thread(target=mon._perform_measurement, daemon=True)
        worker.start()
        assert started.wait(timeout=2.0), "capture never started"

        # Capture is now blocked; get_status must still return promptly.
        t0 = time.perf_counter()
        status = mon.get_status()
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.5, f"get_status stalled during capture ({elapsed:.2f}s)"
        assert status is not None

        block.set()
        worker.join(timeout=5.0)
        assert not worker.is_alive()
