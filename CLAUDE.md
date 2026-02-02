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
├── config.toml              # Server configuration
├── TTS160config.toml        # Telescope configuration
└── requirements.txt         # Python dependencies
```

## Key Modules

| Module              | Responsibility                                                 |
| ------------------- | -------------------------------------------------------------- |
| `app.py`            | Main entry point, HTTP server, route registration              |
| `TTS160Device.py`   | Hardware control, coordinate transforms, slewing, tracking     |
| `tts160_serial.py`  | Serial port communication, LX200 commands, binary parsing      |
| `tts160_cache.py`   | Background property updates (0.5s interval), thread-safe cache |
| `telescope.py`      | Alpaca API endpoint responders                                 |
| `telescope_gui.py`  | NiceGUI web interface                                          |
| `exceptions.py`     | Alpaca-compliant exception classes                             |

## Dependencies

Core dependencies from `requirements.txt`:

- `astropy` - Coordinate transformations and astronomical calculations
- `falcon` - Web framework for Alpaca API
- `nicegui` - Web-based GUI framework
- `pyserial` - Serial port communication
- `toml` - Configuration file parsing
- `psutil` - System monitoring

## Building

Run PyInstaller via the build script:

```bash
pyinstaller TTS160_pyinstaller
```

GitHub Actions builds for Windows, Linux, macOS, and Raspberry Pi automatically on workflow dispatch.

## Configuration

**Server Config (`config.toml`):**

- Network: IP address, API port (5555), GUI port (8080)
- Logging: level, rotation, stdout output

**Telescope Config (`TTS160config.toml`):**

- Device: serial port (e.g., "COM5" or "/dev/ttyUSB0")
- Site: latitude, longitude, elevation
- Driver: time sync, pulse guide settings

## Running

```bash
python app.py
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

### Manual Testing

- Use ConformU (ASCOM validation tool) to validate Alpaca compliance
- Test GUI functionality in browser at `http://localhost:8080`
- Verify serial communication with actual or simulated mount

### Import Validation

```bash
python -c "import app"
```

### No Formal Test Suite

Currently, no automated test suite exists. Consider adding:

- Unit tests for coordinate transformations
- Mock-based tests for serial communication
- Integration tests for Alpaca endpoints

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
