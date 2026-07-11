# Alignment Monitor (V1)

> **STATUS: LIVE, but disabled by default (`[alignment] enabled = false`).**
> This is a hardware-dependent feature (it needs a camera and a plate-solve
> database); the operator enables it deliberately. When enabled, the subsystem
> is fully wired: the capture -> detect -> solve pipeline runs, the decision
> engine `evaluate()` is invoked after each successful measurement, plate solves
> are converted from J2000/ICRS to the mount's of-date (JNOW) frame at the
> exposure mid-time before any comparison or sync/align write (the epoch gate),
> and the firmware ALIGN_POINT (0x12) / PERFORM_ALIGNMENT (0x13) commands plus
> the QA firmware read are wired. Grounded review + FINISH matrix:
> `tts160-alignment-findings.md` (findings AM1-AM5; Phase B1 FINISH).
>
> **Operator-only validation:** the closed-loop behavior with a real camera on
> the sky (does auto-sync/auto-align actually improve pointing?) can only be
> validated on-mount/on-sky. The math (epoch conversion, error), the wire
> protocol (0x12/0x13), and the threading are verified in the test suite.

The alignment monitor is a background subsystem that continuously evaluates pointing accuracy by capturing images, detecting stars, plate solving, and comparing the solved position against the mount's reported position.

**Current Version:** V1 (Decision Engine) -- live when enabled

## V1 Features

The V1 implementation adds autonomous decision-making capabilities:

- **Decision Engine**: Threshold-based logic for sync vs. alignment decisions
- **Geometry Evaluation**: Determinant-based quality metric for 3-point alignment spread
- **Per-point Weighted Error**: Distance-based attribution of errors to alignment points
- **Health Monitoring**: Sliding window detection of persistent alignment problems
- **Lockout System**: Prevents rapid repeated sync/align actions
- **Firmware Abstraction**: Graceful fallback when ALIGN_POINT command unavailable

## Data Flow

The background loop runs the pipeline below and calls `evaluate()` on each
successful measurement. The solved position is converted J2000 -> JNOW at the
exposure mid-time before the comparison (the epoch gate), so the "Comparison"
box differences like-for-like frames.

```text
┌──────────────┐    ┌───────────────┐    ┌──────────────┐    ┌─────────────┐
│ CameraManager│ -> │ StarDetector  │ -> │ PlateSolver  │ -> │ Comparison  │
│   (alpyca)   │    │    (SEP)      │    │   (tetra3)   │    │             │
├──────────────┤    ├───────────────┤    ├──────────────┤    ├─────────────┤
│ capture_image│    │ detect_stars  │    │ solve_from_  │    │ mount_pos - │
│ -> ImageData │    │ -> centroids  │    │ centroids    │    │ solved_pos  │
│ (numpy array)│    │ (Nx2 array)   │    │ -> RA,Dec    │    │ = error     │
│              │    │               │    │ (J2000 ->    │    │ (JNOW vs    │
│              │    │               │    │  JNOW gate)  │    │  JNOW)      │
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

`evaluate()` runs after each successful measurement (from the background loop
and the manual "Measure Now" trigger). Capture / detect / solve run OUTSIDE the
monitor lock, so `get_status()` and `stop()` stay responsive during a capture.

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
error_concern = 300.0           # RESERVED: a config/GUI knob NOT currently read
                                # by the decision engine (the engine uses
                                # error_ignore / error_sync / error_max). Kept
                                # for compatibility; wiring it is a future item.
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
6. The V1 decision engine runs automatically after each successful measurement
   (the solved position is epoch-converted to JNOW first, so sync/align act in
   the mount's frame).

## Module Files

| File                       | Purpose                                    |
| -------------------------- | ------------------------------------------ |
| `alignment_monitor.py`     | Main orchestrator with V1 decision engine  |
| `alignment_geometry.py`    | Determinant and candidate evaluation logic |
| `alignment_qa.py`          | Independent QA (Davenport Q-method) subsystem |
| `camera_source.py`         | Camera source interface (Alpaca / ZWO)     |
| `camera_factory.py`        | Builds the configured camera source        |
| `star_detector.py`         | SEP star detection wrapper                 |
| `plate_solver.py`          | tetra3 plate solving wrapper               |
| `LICENSE_THIRD_PARTY.md`   | License attributions                       |

## Firmware Compatibility

The TTS-160 firmware v357 implements the ALIGN_POINT (0x12) and PERFORM_ALIGNMENT (0x13) binary commands (present and correct in `tts160_serial.py`).

The driver wires the `set_align_point_callback` / `set_perform_alignment_callback`
/ `set_serial_manager_callback` callbacks in
`TTS160Device._start_alignment_if_enabled`, so `_firmware_supports_align_point`
is enabled and `evaluate()` can take the firmware ALIGN_POINT branch (replacing
an alignment point + recalculating the model) when the geometry warrants it,
falling back to SYNC otherwise. The QA subsystem reads the alignment A-variables
(A2-A22, plus M8/M9/C17/C18, T31/T32) through the serial-manager callback.

> **Note (QA per-point residuals):** the QA subsystem's per-point
> `residual_arcsec` is not yet computed (it needs the full quaternion
> transform). `QAStatus.residuals_computed` is `False` to surface this
> honestly -- a `0.0` residual is a placeholder, not a measured zero.

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
