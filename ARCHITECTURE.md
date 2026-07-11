# TTS160 Alpaca Driver Architecture

## Directory Structure

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

| Mode | Command | Description |
|------|---------|-------------|
| Full GUI (default) | `python app.py` | API + GUI + browser |
| Headless | `python app.py --headless` | API only, no GUI |
| GUI-Available | `python app.py --gui-available` | API + GUI, no browser auto-open |

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

Access GUI at `http://localhost:8080`, Alpaca API at `http://localhost:5555`

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
4. Update GUI if user-facing (the `gui/` package: `gui/components/`, `gui/panels/`)

### Modifying Configuration

1. Add field to appropriate config class (`config.py` or `TTS160Config.py`)
2. Add default value
3. Update corresponding `.toml` file
4. Update GUI config tab if user-editable
