# CLAUDE.md - TTS160 Alpaca Driver

## Project Overview

**TTS160 Alpaca Driver** - Python-based, multi-platform ASCOM Alpaca driver for the TTS-160 Panther telescope mount. Provides native cross-platform support (Windows, Linux, macOS, Raspberry Pi) without requiring ASCOM.

- **Repository:** <https://github.com/rwsmythe/TTS160-Alpyca>
- **Firmware Compatibility:** TTS-160 firmware v356+
- **Protocol:** ASCOM Alpaca v1 (Telescope API v4)
- **GUI:** Web-based (NiceGUI, port 8080) | **API Port:** 5555

Part of a **multi-repo firmware ecosystem**. When propagating fixes, check all relevant projects:

| Project             | Repository                                      | Description          |
| ------------------- | ----------------------------------------------- | -------------------- |
| TTS-Central         | <https://github.com/astrodane/TTS-Central>      | Mount firmware (C)   |
| TTS160-Test-Harness | (local)                                         | Integration tests    |
| TTS160 Alpyca       | <https://github.com/rwsmythe/TTS160-Alpyca>     | This driver (Python) |

## Reference Documents

Detailed reference material has been extracted to keep this file concise:

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Directory structure, module table, configuration examples, operating modes, CLI arguments, common tasks
- **[ALIGNMENT_MONITOR.md](ALIGNMENT_MONITOR.md)** - V1 alignment monitor: data flow, state machine, configuration, decision logic, camera sources, geometry, V2 roadmap

## Dependencies

Core: `astropy`, `falcon`, `nicegui`, `pyserial`, `toml`, `psutil`

Alignment Monitor: `alpyca` (MIT), `zwoasi` (MIT), `sep` (LGPLv3/BSD/MIT), `tetra3` (Apache 2.0)

## Building

```bash
pyinstaller TTS160_pyinstaller
```

GitHub Actions builds for Windows, Linux, macOS, and Raspberry Pi on workflow dispatch.

## Code Change Guidelines

### Pythonic Code Requirements

1. **Pythonic** - Comprehensions, `with` statements, `enumerate()`, f-strings, unpacking
2. **PEP 8 Compliant** - 4-space indent, 120-char lines, `snake_case` functions, `PascalCase` classes
3. **Well-Documented** - Docstrings (Google/NumPy style), type hints, inline comments for complex logic only
4. **Best Practices:**
   - Thread safety: Use `RLock` (see `TTS160Global.py` pattern)
   - Exceptions: Use project hierarchy in `exceptions.py`
   - Logging: Use project logger, not print
   - Config: Use existing patterns, not hardcoded values
   - No global mutable state outside `TTS160Global.py` singletons

### Thread Safety

Multi-threaded application: cache runs in background thread, GUI in separate thread from Alpaca server, serial communication must be serialized. Use `RLock` for shared state.

### Alpaca Protocol Compliance

Follow ASCOM Alpaca specs. Use `PropertyResponse`/`MethodResponse` from `shr.py`. Raise exceptions from `exceptions.py`. Maintain ClientID/ClientTransactionID handling.

## Iterative Code Review Process

**Key principle:** Prioritize **functional correctness** (does the behavior match intent?) over surface-level consistency. When scope is ambiguous, ask clarifying questions.

**Cycle:** Review changes -> Collect deficiencies -> Filter false positives -> Fix -> Re-analyze until clean.

**Checklist:** Code imports cleanly, type hints present, docstrings follow conventions, thread safety maintained, exceptions use hierarchy, logging uses project logger, no hardcoded config, consistent naming, edge cases handled, Alpaca compliance (if applicable).

## Testing

```bash
py -m pytest tests/                          # All tests
py -m pytest tests/unit/ -v                  # Unit tests only
py -m pytest tests/integration/ -v           # Integration tests
py -m pytest tests/ --cov=. --cov-report=html  # With coverage
```

**Import validation:** `py -c "import app"`

### Integration Test Harness

Located at `C:\Users\astronomy\TTS160\TTS160-Test-Harness`. Check `TODO.md` periodically for test failures requiring driver fixes. Items marked `### Driver (TTS160-Alpyca)` need changes here.

**Status (2026-02-04):** 68 tests passing, 0 failures.

## Alignment Monitor

Background subsystem for continuous pointing accuracy evaluation. See **[ALIGNMENT_MONITOR.md](ALIGNMENT_MONITOR.md)** for full documentation including V1 decision engine, configuration, camera sources, and V2 roadmap.

**Quick reference:** Enable with `enabled = true` in `[alignment]` section of `TTS160config.toml`. Firmware v357 supports ad-hoc alignment commands (0x12, 0x13); older firmware falls back to SYNC-only.

## Documentation Updates

- Always **read a file before claiming it is up to date**. Never skip diffing against actual content.
- When updating documentation, acknowledge what has changed before proceeding.
- Keep documentation files concise. Split into linked sub-documents rather than appending indefinitely.

## Git Workflow

- After completing code changes, commit and push to the appropriate branch unless told not to.
- Use descriptive commit messages referencing the issue or TODO item resolved.
- When changes affect firmware compatibility, check the test harness for corresponding updates.

## Claude Code Automation

### Skills (invoke with `/skill-name`)

| Skill            | Description                                          |
| ---------------- | ---------------------------------------------------- |
| `/run-tests`     | Run unit tests, integration tests, or all            |
| `/commit-push`   | Commit and push changes with descriptive messages    |

### Hooks

- **PreToolUse (Edit/Write)**: Blocks edits to `AlpycaDevice/`, `zwo_capture/sdk/`, `.venv/`
- **PreToolUse (Read)**: Warns if CLAUDE.md exceeds 50KB

### Linting

- `.flake8` configured with `max-line-length = 120`
- `flake8` and `mypy` available in `requirements-dev.txt`

### GitHub Integration

- GitHub MCP plugin (`plugin:github`) configured - use `mcp__plugin_github_github__*` tools instead of `gh` CLI
- Classic PAT with `repo` + `workflow` scopes covers both `rwsmythe/TTS160-Alpyca` and `astrodane/TTS-Central`
