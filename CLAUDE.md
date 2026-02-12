# CLAUDE.md - TTS160 Alpaca Driver

## Project Overview

This is the **TTS160 Alpaca Driver** - a Python-based, multi-platform ASCOM Alpaca driver for the TTS-160 Panther telescope mount. It provides native cross-platform support (Windows, Linux, macOS, Raspberry Pi) by implementing the Alpaca protocol without requiring ASCOM to be installed.

- **Repository:** <https://github.com/rwsmythe/TTS160-Alpyca>
- **Firmware Compatibility:** TTS-160 firmware v356 and later
- **Protocol:** ASCOM Alpaca v1 (Telescope API v4)
- **GUI:** Web-based interface using NiceGUI (default port 8080)
- **API Port:** Default 5555

## Related Projects

- **TTS-Central (Mount Firmware):** <https://github.com/astrodane/TTS-Central>
  - The TTS-160 mount firmware repository
  - Future work on this driver will focus on compliance with firmware v357

## Architecture

```text
TTS160 Alpyca/
├── app.py                   # Main entry point, Falcon web server
├── config.py                # Server configuration (TOML persistence)
├── TTS160Config.py          # Telescope-specific configuration
├── TTS160Global.py          # Global singleton instances manager
├── log.py                   # Logging initialization
├── shr.py                   # Shared utilities, Alpaca response classes
├── exceptions.py            # Alpaca exception hierarchy
├── discovery.py             # Alpaca UDP discovery responder
├── management.py            # Alpaca management API endpoints
├── setup.py                 # Device setup endpoints
│
├── telescope.py             # Alpaca telescope API responders (60+ endpoints)
├── TTS160Device.py          # Core hardware implementation
├── tts160_serial.py         # Serial communication manager
├── tts160_cache.py          # Thread-safe property cache
├── tts160_types.py          # Type definitions
│
├── gui/                     # NiceGUI web interface package
│   ├── components/          # Reusable UI components
│   ├── panels/              # Tab panel implementations
│   ├── services/            # GUI data services
│   ├── layouts/             # Page layout templates
│   └── themes/              # Theme configuration
│
├── alignment_monitor.py     # Alignment quality monitoring orchestrator (V1)
├── alignment_geometry.py    # Geometry calculations for alignment decisions
├── alignment_qa.py          # Alignment QA subsystem (firmware verification)
├── camera_source.py         # Abstract camera source interface
├── camera_factory.py        # Camera source factory
├── alpaca_camera.py         # Alpaca camera source (wraps camera_manager)
├── zwo_camera_source.py     # ZWO native camera source
├── camera_manager.py        # Alpaca camera control (alpyca wrapper)
├── star_detector.py         # Star detection (SEP wrapper)
├── plate_solver.py          # Plate solving (tetra3 wrapper)
├── gps_manager.py           # GPS NMEA serial integration
│
├── zwo_capture/             # ZWO camera capture package
│   ├── __init__.py          # Public API
│   ├── camera.py            # ZWOCamera class
│   ├── sdk_loader.py        # Platform-specific SDK loading
│   ├── exceptions.py        # ZWO exception hierarchy
│   ├── config.py            # Default capture settings
│   └── sdk/                 # Bundled SDK binaries (per platform)
│
├── config.toml              # Server configuration
├── TTS160config.toml        # Telescope configuration
├── LICENSE_THIRD_PARTY.md   # Third-party license attributions
└── requirements.txt         # Python dependencies
```

## Key Modules

| Module                 | Responsibility                                                 |
| ---------------------- | -------------------------------------------------------------- |
| `app.py`               | Main entry point, HTTP server, route registration              |
| `TTS160Device.py`      | Hardware control, coordinate transforms, slewing, tracking     |
| `tts160_serial.py`     | Serial port communication, LX200 commands, binary parsing      |
| `tts160_cache.py`      | Background property updates (0.5s interval), thread-safe cache |
| `telescope.py`         | Alpaca API endpoint responders                                 |
| `gui/`                 | NiceGUI web interface (components, panels, services, themes)   |
| `exceptions.py`        | Alpaca-compliant exception classes                             |
| `alignment_monitor.py` | Alignment quality monitoring with V1 decision engine           |
| `alignment_geometry.py`| Geometry determinant and candidate evaluation calculations     |
| `alignment_qa.py`      | Alignment QA subsystem (firmware quaternion verification)      |
| `camera_source.py`     | Abstract camera source interface for alignment monitor         |
| `camera_factory.py`    | Factory for creating Alpaca or ZWO camera sources              |
| `camera_manager.py`    | Alpaca camera control via alpyca library                       |
| `zwo_capture/`         | Native ZWO ASI camera support package                          |
| `star_detector.py`     | Star detection and centroid extraction via SEP                 |
| `plate_solver.py`      | Astrometric plate solving via tetra3                           |
| `gps_manager.py`       | GPS NMEA serial integration for site location                  |

## Dependencies

Core dependencies from `requirements.txt`:

- `astropy` - Coordinate transformations and astronomical calculations
- `falcon` - Web framework for Alpaca API
- `nicegui` - Web-based GUI framework
- `pyserial` - Serial port communication
- `toml` - Configuration file parsing
- `psutil` - System monitoring

Alignment Monitor dependencies:

- `alpyca` - ASCOM Alpaca camera control (MIT License, ASCOM Initiative)
- `zwoasi` - Native ZWO ASI camera control (MIT License, python-zwoasi)
- `sep` - Star detection via Source Extractor (LGPLv3/BSD/MIT, Kyle Barbary)
- `tetra3` - Astrometric plate solving (Apache 2.0, European Space Agency)

## Building

Run PyInstaller via the build script:

```bash
pyinstaller TTS160_pyinstaller
```

GitHub Actions builds for Windows, Linux, macOS, and Raspberry Pi automatically on workflow dispatch.

## Configuration

### Server Config (`config.toml`)

```toml
[network]
ip_address = ''             # Any address ('' = 0.0.0.0)
port = 5555                 # Alpaca API port
threads = 4                 # WSGI worker threads

[gui]
enabled = true              # false = headless mode (API only)
auto_open_browser = true    # Open browser on startup
port = 8080                 # GUI web server port
bind_address = "0.0.0.0"    # "" = localhost only, "0.0.0.0" = all interfaces
theme = "dark"              # "dark" or "light"
refresh_interval = 1.0      # Status update interval in seconds

[logging]
log_level = 'DEBUG'
log_to_stdout = false
max_size_mb = 5
num_keep_logs = 10
```

### Telescope Config (`TTS160config.toml`)

- Device: serial port (e.g., "COM5" or "/dev/ttyUSB0")
- Site: latitude, longitude, elevation
- Driver: time sync, pulse guide settings

## Running

### Operating Modes

The driver supports three operating modes:

#### Full GUI Mode (Default)

```bash
python app.py
```

- Starts Alpaca API server on port 5555
- Starts NiceGUI web server on port 8080
- Opens browser automatically to GUI

#### Headless Mode

```bash
python app.py --headless
# or
python app.py --no-gui
```

- Starts Alpaca API server only
- No GUI dependencies loaded
- Ideal for remote observatories, Raspberry Pi, Docker

#### GUI-Available Mode

```bash
python app.py --gui-available
```

- Starts both servers but doesn't open browser
- Good for service/daemon deployments

### Command Line Arguments

| Argument                 | Description                                  |
| ------------------------ | -------------------------------------------- |
| `--headless`, `--no-gui` | Run without GUI (API only)                   |
| `--gui-available`        | Start GUI but don't open browser             |
| `--port`, `-p`           | Alpaca API port (default: 5555)              |
| `--gui-port`             | GUI web server port (default: 8080)          |
| `--bind`, `-b`           | Bind address (default: 0.0.0.0)              |
| `--log-level`            | Logging level (DEBUG, INFO, WARNING, ERROR)  |
| `--config`               | Path to config.toml file                     |

### Examples

```bash
python app.py                        # Normal desktop use with GUI
python app.py --headless             # Remote observatory / Raspberry Pi
python app.py --gui-available        # Service mode
python app.py --port 5556            # Custom API port
python app.py --gui-port 8081        # Custom GUI port
```

Access GUI at `http://localhost:8080`, Alpaca API at `http://localhost:5555`

---

## Code Change Guidelines

### Pythonic Code Requirements

All code changes must be:

1. **Pythonic** - Follow Python idioms and conventions
   - Use list/dict/set comprehensions where appropriate
   - Prefer `with` statements for resource management
   - Use `enumerate()` instead of manual indexing
   - Leverage unpacking and multiple assignment
   - Use `f-strings` for string formatting

2. **PEP 8 Compliant**
   - 4-space indentation
   - Line length limit of 120 characters (project convention)
   - Proper naming: `snake_case` for functions/variables, `PascalCase` for classes
   - Two blank lines between top-level definitions

3. **Well-Documented**
   - Docstrings for all public classes and methods (Google or NumPy style)
   - Type hints for function signatures
   - Inline comments for complex logic only
   - Update existing documentation when modifying behavior

4. **Best Practices**
   - Thread safety: Use appropriate locks (RLock is used throughout)
   - Exception handling: Use project's exception hierarchy in `exceptions.py`
   - Logging: Use the project's logger, not print statements
   - Configuration: Use existing config patterns, not hardcoded values
   - No global mutable state outside `TTS160Global.py` singletons

### Thread Safety

This is a multi-threaded application. Key considerations:

- Use `RLock` for protecting shared state (see `TTS160Global.py` pattern)
- The cache (`tts160_cache.py`) runs in a background thread
- GUI runs in a separate thread from the Alpaca server
- Serial communication must be properly serialized

### Alpaca Protocol Compliance

When modifying API endpoints:

- Follow ASCOM Alpaca protocol specifications
- Use `PropertyResponse` and `MethodResponse` from `shr.py`
- Raise appropriate exceptions from `exceptions.py`
- Maintain ClientID and ClientTransactionID handling

---

## Iterative Code Review Process

All new code changes must undergo the following iterative review cycle:

### Step 1: Initial Review

Review the proposed change for:

- Correctness: Does it implement the intended functionality?
- Pythonic style: Does it follow Python idioms?
- Thread safety: Are shared resources properly protected?
- Error handling: Are exceptions handled appropriately?
- Documentation: Are docstrings and type hints present?
- Consistency: Does it match existing code patterns?

### Step 2: Collect Deficiencies

Document all identified issues:

- Code style violations
- Potential bugs or edge cases
- Missing error handling
- Thread safety concerns
- Missing or inadequate documentation
- Performance issues
- Security concerns

### Step 3: Analyze for False Positives

For each deficiency, determine:

- Is this actually a problem in context?
- Does existing code follow a different pattern intentionally?
- Would the "fix" introduce other issues?
- Is the concern theoretical or practical?

Remove false positives from the deficiency list.

### Step 4: Correct Deficiencies

Apply fixes for all validated deficiencies:

- Make minimal, focused changes
- Preserve existing behavior unless intentionally changing it
- Maintain code style consistency with surrounding code

### Step 5: Re-Analyze

Repeat steps 1-4 on the corrected code:

- Verify all deficiencies have been addressed
- Check that fixes haven't introduced new issues
- Continue until no new deficiencies are found

### Review Checklist

```text
[ ] Code compiles/imports without errors
[ ] Type hints are present and correct
[ ] Docstrings follow project conventions
[ ] Thread safety is maintained
[ ] Exceptions use project hierarchy
[ ] Logging uses project logger
[ ] No hardcoded configuration values
[ ] Consistent naming conventions
[ ] No unnecessary complexity
[ ] Edge cases are handled
[ ] Alpaca protocol compliance (if applicable)
```

---

## Testing

### Running Tests

```bash
# Run all tests
python -m pytest tests/

# Run unit tests only
python -m pytest tests/unit/ -v

# Run integration tests
python -m pytest tests/integration/ -v

# Run specific test file
python -m pytest tests/unit/test_config.py -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html
```

### Test Structure

```text
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Unit tests (no hardware)
│   ├── test_config.py       # Configuration tests (including GUI config)
│   ├── test_cache.py        # Cache mechanism tests
│   ├── test_serial_parsing.py
│   ├── test_telescope_cache.py
│   ├── test_priority_queue.py
│   ├── test_gps_manager.py  # GPS manager tests
│   ├── test_alignment_monitor.py  # Alignment monitor tests (V1)
│   ├── test_alignment_geometry.py # Geometry calculation tests
│   ├── test_zwo_capture.py  # ZWO capture package tests
│   └── test_camera_source.py # Camera source abstraction tests
├── integration/             # Integration tests
│   ├── test_api_endpoints.py
│   ├── test_device.py
│   └── test_cache_integration.py
└── benchmarks/              # Performance benchmarks
    ├── benchmark_api.py
    └── benchmark_concurrent.py
```

### Manual Testing

- Use ConformU (ASCOM validation tool) to validate Alpaca compliance
- Test GUI functionality in browser at `http://localhost:8080`
- Verify serial communication with actual or simulated mount

### Import Validation

```bash
python -c "import app"
python -c "from telescope_gui import TelescopeInterface"
python -c "from config import Config"
```

### Integration Testing Harness

A separate test harness framework exists for integration testing between this driver and the TTS-160 firmware. This harness runs actual firmware code compiled for x86 to validate protocol compatibility.

**Location:** `C:\Users\astronomy\TTS160\TTS160-Test-Harness`

**Key Files:**

| File | Purpose |
| ---- | ------- |
| `TODO.md` | Test results, failure analysis, and required fixes |
| `CLAUDE.md` | Harness-specific documentation |
| `tests/` | Integration tests for LX200 and binary protocols |
| `harness/` | Compiled firmware harness code |

**Workflow:**

1. Check `TODO.md` periodically for test failures that require driver fixes
2. Action items marked with `### Driver (TTS160-Alpyca)` indicate changes needed in this driver
3. After making driver changes, re-run the harness tests to verify compatibility

**Running Harness Tests:**

```bash
cd C:\Users\astronomy\TTS160\TTS160-Test-Harness
python -m pytest tests/ -v
```

**Current Status (as of 2026-02-04):**

- 68 tests passing (35 binary + 21 commands + 12 protocol)
- 0 failures

---

## Common Tasks

### Adding a New Alpaca Endpoint

1. Add responder class in `telescope.py` following existing pattern
2. Implement `on_get()`, `on_put()`, or both
3. Use `PropertyResponse` or `MethodResponse` from `shr.py`
4. Register route in `app.py` (automatic from class name)

### Adding Device Functionality

1. Add method to `TTS160Device.py`
2. If using serial commands, add to `tts160_serial.py`
3. If cacheable, consider adding to `tts160_cache.py`
4. Update GUI if user-facing (`telescope_gui.py`, `telescope_commands.py`)

### Modifying Configuration

1. Add field to appropriate config class (`config.py` or `TTS160Config.py`)
2. Add default value
3. Update corresponding `.toml` file
4. Update GUI config tab if user-editable

---

## Alignment Monitor (V1)

The alignment monitor is a background subsystem that continuously evaluates pointing accuracy by capturing images, detecting stars, plate solving, and comparing the solved position against the mount's reported position.

**Current Version:** V1 (Decision Engine)

### V1 Features

The V1 implementation adds autonomous decision-making capabilities:

- **Decision Engine**: Threshold-based logic for sync vs. alignment decisions
- **Geometry Evaluation**: Determinant-based quality metric for 3-point alignment spread
- **Per-point Weighted Error**: Distance-based attribution of errors to alignment points
- **Health Monitoring**: Sliding window detection of persistent alignment problems
- **Lockout System**: Prevents rapid repeated sync/align actions
- **Firmware Abstraction**: Graceful fallback when ALIGN_POINT command unavailable

### Data Flow

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

### State Machine

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

### Configuration (`TTS160config.toml`)

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

### Camera Source Selection

The alignment monitor supports two camera sources:

| Source | Description | When to Use |
|--------|-------------|-------------|
| `alpaca` | ASCOM Alpaca protocol | Camera exposed via Alpaca server (NINA, SharpCap, etc.) |
| `zwo` | Native ZWO SDK | Direct ZWO camera connection, no server needed |

Set `camera_source = "zwo"` to use native ZWO support. The ZWO SDK must be installed (bundled in `zwo_capture/sdk/`).

### Geometry Determinant

The geometry quality is measured by the absolute determinant of a 3×3 matrix formed by unit direction vectors from the three alignment points in alt/az coordinates:

- **det = 0**: Points are coplanar through origin (degenerate, useless)
- **det → 1**: Points are maximally spread (optimal geometry)

```python
# Computed in alignment_geometry.py
det = |v1 · (v2 × v3)|  # where v_i are unit vectors from alt/az
```

### V1 Decision Logic

```text
1. Check lockout period → LOCKOUT if active
2. Check mount state → NO_ACTION if slewing
3. Get pointing error from plate solve
4. Update per-point weighted errors (distance-based)
5. If error < error_ignore → NO_ACTION
6. Refresh alignment point data from firmware
7. Find valid replacement candidates:
   - Geometry improvement candidates (det_improvement_min)
   - Refresh candidates (within refresh_radius + high weighted error)
8. If no candidates and error > error_sync → SYNC
9. Select best candidate (refresh priority, then geometry by threshold)
10. If error > error_max → log health event, check alert
11. Execute alignment (or sync fallback if firmware unsupported)
```

### Third-Party Libraries

| Library | License      | Purpose                    |
| ------- | ------------ | -------------------------- |
| alpyca  | MIT          | Alpaca camera control      |
| SEP     | LGPLv3/BSD   | Star detection/centroids   |
| tetra3  | Apache 2.0   | Plate solving              |

See [LICENSE_THIRD_PARTY.md](LICENSE_THIRD_PARTY.md) for full attribution.

### GUI Integration

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

### Usage

1. Configure an Alpaca-compatible camera server (e.g., NINA, SharpCap)
2. Set `enabled = true` in `[alignment]` section of `TTS160config.toml`
3. Configure camera address, port, and exposure settings
4. Provide a tetra3 star database file (or use default path)
5. Connect the telescope - alignment monitor starts automatically
6. V1 decision engine runs automatically after each plate solve

### Alignment Module Files

| File                       | Purpose                                    |
| -------------------------- | ------------------------------------------ |
| `alignment_monitor.py`     | Main orchestrator with V1 decision engine  |
| `alignment_geometry.py`    | Determinant and candidate evaluation logic |
| `camera_manager.py`        | Alpyca camera wrapper                      |
| `star_detector.py`         | SEP star detection wrapper                 |
| `plate_solver.py`          | tetra3 plate solving wrapper               |
| `LICENSE_THIRD_PARTY.md`   | License attributions                       |

### Firmware Compatibility Note

The TTS-160 firmware v357 supports ALIGN_POINT (0x12) and PERFORM_ALIGNMENT (0x13) binary commands, enabling the V1 decision engine to replace individual alignment points and trigger model recalculation. The driver auto-detects firmware support and falls back to SYNC-only mode (`:CM#`) on older firmware versions.

---

## V2 Alignment Monitor Roadmap

### Completed (Now in V1)

- ALIGN_POINT command (0x12) - Firmware v357
- PERFORM_ALIGNMENT command (0x13) - Firmware v357
- Alignment data GET variables (A16-A22) - Firmware v357

### Planned for V2

| Category | Feature | Description |
| -------- | ------- | ----------- |
| Firmware | A1-A15 variable access | Read/write alignment matrix directly |
| Decision | Multi-star error weighting | Weight errors by star brightness/confidence |
| Decision | Atmospheric refraction | Account for refraction in error calculations |
| Decision | Meridian flip awareness | Special handling around meridian crossings |
| Geometry | N-point alignment | Extend beyond 3-point alignment |
| Geometry | Pointing model fitting | Build pointing model from accumulated data |
| GUI | Error history graph | Time-series plot of pointing errors |
| GUI | Alignment point visualization | Sky map showing point positions |

---

## Claude Code Automation

### Skills (invoke with `/skill-name`)

| Skill | Description |
|-------|-------------|
| `/run-tests` | Run unit tests, integration tests, or all with coverage |

### Hooks

- **PreToolUse (Edit/Write)**: Blocks edits to `AlpycaDevice/`, `zwo_capture/sdk/`, `.venv/`

### Linting

- `.flake8` configured with `max-line-length = 120`
- `flake8` and `mypy` available in `requirements-dev.txt`

### GitHub Integration

- GitHub MCP plugin (`plugin:github`) is configured — use `mcp__plugin_github_github__*` tools instead of `gh` CLI
- Classic PAT with `repo` + `workflow` scopes covers both `rwsmythe/TTS160-Alpyca` and `astrodane/TTS-Central`
