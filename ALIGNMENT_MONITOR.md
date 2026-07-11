# Alignment Monitor (V1)

> **STATUS: PARKED / INACTIVE (not currently functional).** By operator decision
> this subsystem is disabled by default (`[alignment] enabled = false`) and is
> **non-functional as wired**: the decision engine `evaluate()` has no callers, the
> `PlateSolver` seam fails on construction (dead on arrival), and the firmware
> action callbacks are never wired (so ALIGN_POINT/PERFORM_ALIGNMENT and QA are
> unreachable). The V1 capabilities described below are **aspirational, not live**.
> See the grounded review and the FINISH-vs-PARK decision matrix in the harness
> register `tts160-alignment-findings.md` (findings AM1, AM2, AM3). Making it live
> is the FINISH decision, which has NOT been taken.

The alignment monitor is a background subsystem intended to continuously evaluate pointing accuracy by capturing images, detecting stars, plate solving, and comparing the solved position against the mount's reported position.

**Current Version:** V1 (Decision Engine) -- **PARKED, see status note above**

## V1 Features

The V1 implementation adds autonomous decision-making capabilities:

- **Decision Engine**: Threshold-based logic for sync vs. alignment decisions
- **Geometry Evaluation**: Determinant-based quality metric for 3-point alignment spread
- **Per-point Weighted Error**: Distance-based attribution of errors to alignment points
- **Health Monitoring**: Sliding window detection of persistent alignment problems
- **Lockout System**: Prevents rapid repeated sync/align actions
- **Firmware Abstraction**: Graceful fallback when ALIGN_POINT command unavailable

## Data Flow

> **PARKED:** the diagram below shows the INTENDED design. In the code as it
> stands the `evaluate()` box is NOT in any live loop (it has zero callers, AM1)
> and the `PlateSolver` box never constructs successfully (AM2), so no branch of
> this flow actually executes.

```text
┌──────────────┐    ┌───────────────┐    ┌──────────────┐    ┌─────────────┐
│ CameraManager│ -> │ StarDetector  │ -> │ PlateSolver  │ -> │ Comparison  │
│   (alpyca)   │    │    (SEP)      │    │   (tetra3)   │    │             │
├──────────────┤    ├───────────────┤    ├──────────────┤    ├─────────────┤
│ capture_image│    │ detect_stars  │    │ solve_from_  │    │ mount_pos - │
│ -> ImageData │    │ -> centroids  │    │ centroids    │    │ solved_pos  │
│ (numpy array)│    │ (Nx2 array)   │    │ -> RA,Dec    │    │ = error     │
└──────────────┘    └───────────────┘    └──────────────┘    └─────────────┘
                                                                    │
                                                                    ▼
                                                         ┌─────────────────┐
                                                         │ V1 Decision     │
                                                         │ Engine          │
                                                         ├─────────────────┤
                                                         │ evaluate() ->   │
                                                         │ NO_ACTION/SYNC/ │
                                                         │ ALIGN/LOCKOUT   │
                                                         └─────────────────┘
```

## State Machine

> **PARKED:** intended state machine. The `evaluate()` transitions shown below do
> not occur -- `evaluate()` is never called (AM1) -- and the pipeline does not
> advance past start-up because the `PlateSolver` seam raises on construction (AM2).

```text
DISABLED → DISCONNECTED → CONNECTING → CONNECTED → CAPTURING → SOLVING → MONITORING
                                                                              ↓
                                                                    ┌─── evaluate() ───┐
                                                                    │                  │
                                                              NO_ACTION          SYNC/ALIGN
                                                                    │                  │
                                                                    └───── LOCKOUT ────┘
                                                                              ↓
                                                                           ERROR
```

## Configuration (`TTS160config.toml`)

```toml
[alignment]
# === Core Settings ===
enabled = false                 # Enable alignment monitoring
camera_source = "alpaca"        # Camera source: "alpaca" or "zwo"
camera_address = "127.0.0.1"    # Alpaca camera server address
camera_port = 11111             # Alpaca camera server port
camera_device = 0               # Camera device number
exposure_time = 1.0             # Exposure time in seconds
binning = 2                     # Camera binning (1, 2, or 4)
interval = 30.0                 # Interval between measurements (seconds)
fov_estimate = 1.0              # Estimated field of view (degrees)
detection_threshold = 5.0       # Star detection threshold (sigma)
max_stars = 50                  # Maximum stars for solving
error_threshold = 60.0          # Error warning threshold (arcseconds)
database_path = "tetra3_database.npz"
verbose_logging = false

# === V1 Decision Thresholds (arcseconds) ===
error_ignore = 30.0             # Below this, take no action
error_sync = 120.0              # Above this, sync if not aligning
error_concern = 300.0           # Above this, evaluate alignment replacement
error_max = 600.0               # Above this, force action and log health event

# === Geometry Thresholds (determinant, dimensionless 0-1) ===
det_excellent = 0.80            # Near-optimal; protect this geometry
det_good = 0.60                 # Solid; be selective about changes
det_marginal = 0.40             # Weak; actively seek improvement
det_improvement_min = 0.10      # Minimum improvement to justify replacement

# === Angular Constraints (degrees) ===
min_separation = 15.0           # Minimum angle between any two alignment points
refresh_radius = 10.0           # Distance within which "refresh" logic applies
scale_radius = 30.0             # Per-point weighted error distance falloff

# === Refresh Logic ===
refresh_error_threshold = 60.0  # Weighted error threshold for refresh eligibility (arcsec)

# === Lockout Periods (seconds) ===
lockout_post_align = 60.0       # After alignment point replacement
lockout_post_sync = 10.0        # After sync operation

# === Health Monitoring ===
health_window = 1800.0          # Window duration (seconds) - 30 minutes
health_alert_threshold = 5      # Events within window to trigger alert

# === ZWO Camera Settings (when camera_source = "zwo") ===
[alignment.zwo]
camera_id = 0                   # Camera index (0 for first ZWO camera)
exposure_ms = 2000              # Exposure time in milliseconds
gain = 100                      # Camera gain (0-500 typical)
binning = 2                     # Pixel binning (1, 2, or 4)
image_type = "RAW16"            # RAW8, RAW16, RGB24, Y8
```

## Camera Source Selection

The alignment monitor supports two camera sources:

| Source   | Description          | When to Use                                                      |
|----------|----------------------|------------------------------------------------------------------|
| `alpaca` | ASCOM Alpaca protocol | Camera exposed via Alpaca server (NINA, SharpCap, etc.)         |
| `zwo`   | Native ZWO SDK        | Direct ZWO camera connection, no server needed                  |

Set `camera_source = "zwo"` to use native ZWO support. The ZWO SDK must be installed (bundled in `zwo_capture/sdk/`).

## Geometry Determinant

The geometry quality is measured by the absolute determinant of a 3x3 matrix formed by unit direction vectors from the three alignment points in alt/az coordinates:

- **det = 0**: Points are coplanar through origin (degenerate, useless)
- **det -> 1**: Points are maximally spread (optimal geometry)

```python
# Computed in alignment_geometry.py
det = |v1 . (v2 x v3)|  # where v_i are unit vectors from alt/az
```

## V1 Decision Logic

```text
1. Check lockout period -> LOCKOUT if active
2. Check mount state -> NO_ACTION if slewing
3. Get pointing error from plate solve
4. Update per-point weighted errors (distance-based)
5. If error < error_ignore -> NO_ACTION
6. Refresh alignment point data from firmware
7. Find valid replacement candidates:
   - Geometry improvement candidates (det_improvement_min)
   - Refresh candidates (within refresh_radius + high weighted error)
8. If no candidates and error > error_sync -> SYNC
9. Select best candidate (refresh priority, then geometry by threshold)
10. If error > error_max -> log health event, check alert
11. Execute alignment (or sync fallback if firmware unsupported)
```

## Third-Party Libraries

| Library | License      | Purpose                    |
| ------- | ------------ | -------------------------- |
| alpyca  | MIT          | Alpaca camera control      |
| SEP     | LGPLv3/BSD   | Star detection/centroids   |
| tetra3  | Apache 2.0   | Plate solving              |

See [LICENSE_THIRD_PARTY.md](LICENSE_THIRD_PARTY.md) for full attribution.

## GUI Integration

The alignment status is displayed in the Telescope Status tab with:

- Current state and camera connection status
- RA/Dec error measurements in arcseconds
- Total error with color coding (green/yellow/red)
- Average and maximum error statistics
- Star count and measurement history
- Manual "Measure Now" trigger button
- **V1 additions:**
  - Geometry determinant with quality color coding (red/yellow/green)
  - Last decision result (no_action/sync/align/lockout)
  - Lockout remaining time
  - Health alert indicator

## Usage

1. Configure an Alpaca-compatible camera server (e.g., NINA, SharpCap)
2. Set `enabled = true` in `[alignment]` section of `TTS160config.toml`
3. Configure camera address, port, and exposure settings
4. Provide a tetra3 star database file (or use default path)
5. Connect the telescope - alignment monitor starts automatically

> **PARKED / not implemented as wired:** the former step 6 claimed "the V1 decision
> engine runs automatically after each plate solve." This is **false** -- `evaluate()`
> has zero callers, so no automatic sync/align decision occurs (AM1). Even the
> capture/solve loop does not run because the `PlateSolver` seam fails on start (AM2).

## Module Files

| File                       | Purpose                                    |
| -------------------------- | ------------------------------------------ |
| `alignment_monitor.py`     | Main orchestrator with V1 decision engine  |
| `alignment_geometry.py`    | Determinant and candidate evaluation logic |
| `camera_manager.py`        | Alpyca camera wrapper                      |
| `star_detector.py`         | SEP star detection wrapper                 |
| `plate_solver.py`          | tetra3 plate solving wrapper               |
| `LICENSE_THIRD_PARTY.md`   | License attributions                       |

## Firmware Compatibility

The TTS-160 firmware v357 implements the ALIGN_POINT (0x12) and PERFORM_ALIGNMENT (0x13) binary commands (present and correct in `tts160_serial.py`).

> **PARKED / not wired:** the claim that "the driver auto-detects firmware support
> and falls back to SYNC-only mode" is **false today**. The driver never wires the
> `set_align_point_callback` / `set_perform_alignment_callback` /
> `set_serial_manager_callback` callbacks (AM3), so `_firmware_supports_align_point`
> is never enabled, the 0x12/0x13 path is unreachable, and the SYNC fallback lives
> inside the dead `evaluate()` (AM1). The firmware commands exist but the driver
> does not call them.

---

## V2 Roadmap

### Completed (Now in V1)

- ALIGN_POINT command (0x12) - Firmware v357
- PERFORM_ALIGNMENT command (0x13) - Firmware v357
- Alignment data GET variables (A16-A22) - Firmware v357

### Planned for V2

| Category | Feature                    | Description                                      |
| -------- | -------------------------- | ------------------------------------------------ |
| Firmware | A1-A15 variable access     | Read/write alignment matrix directly             |
| Decision | Multi-star error weighting | Weight errors by star brightness/confidence      |
| Decision | Atmospheric refraction     | Account for refraction in error calculations     |
| Decision | Meridian flip awareness    | Special handling around meridian crossings        |
| Geometry | N-point alignment          | Extend beyond 3-point alignment                  |
| Geometry | Pointing model fitting     | Build pointing model from accumulated data       |
| GUI      | Error history graph        | Time-series plot of pointing errors              |
| GUI      | Alignment point visualization | Sky map showing point positions                |
