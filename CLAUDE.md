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
├── telescope_gui.py         # NiceGUI web interface
├── telescope_data.py        # GUI data management
├── telescope_commands.py    # GUI command handlers
│
├── alignment_monitor.py     # Alignment quality monitoring orchestrator
├── camera_manager.py        # Alpaca camera control (alpyca wrapper)
├── star_detector.py         # Star detection (SEP wrapper)
├── plate_solver.py          # Plate solving (tetra3 wrapper)
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
| `telescope_gui.py`     | NiceGUI web interface                                          |
| `exceptions.py`        | Alpaca-compliant exception classes                             |
| `alignment_monitor.py` | Alignment quality monitoring with plate solving                |
| `camera_manager.py`    | Alpaca camera control via alpyca library                       |
| `star_detector.py`     | Star detection and centroid extraction via SEP                 |
| `plate_solver.py`      | Astrometric plate solving via tetra3                           |

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
│   └── test_alignment_monitor.py  # Alignment monitor tests
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

**Current Status (as of 2026-02-02):**

- 9 tests passing
- 32 tests skipped (firmware/configuration incomplete)
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

## Alignment Monitor

The alignment monitor is a background subsystem that continuously evaluates pointing accuracy by capturing images, detecting stars, plate solving, and comparing the solved position against the mount's reported position.

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
```

### State Machine

```text
DISABLED → DISCONNECTED → CONNECTING → CONNECTED → CAPTURING → SOLVING → MONITORING
                                                                              ↓
                                                                           ERROR
```

### Configuration (`TTS160config.toml`)

```toml
[alignment]
enabled = false                 # Enable alignment monitoring
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

### Usage

1. Configure an Alpaca-compatible camera server (e.g., NINA, SharpCap)
2. Set `enabled = true` in `[alignment]` section of `TTS160config.toml`
3. Configure camera address, port, and exposure settings
4. Provide a tetra3 star database file (or use default path)
5. Connect the telescope - alignment monitor starts automatically

### Alignment Module Files

| File                     | Purpose                              |
| ------------------------ | ------------------------------------ |
| `alignment_monitor.py`   | Main orchestrator with state machine |
| `camera_manager.py`      | Alpyca camera wrapper                |
| `star_detector.py`       | SEP star detection wrapper           |
| `plate_solver.py`        | tetra3 plate solving wrapper         |
| `LICENSE_THIRD_PARTY.md` | License attributions                 |
