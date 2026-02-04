# UX Redesign - Implementation Plan

## Overview

**Goal:** Complete from-scratch redesign of the TTS160 Alpaca Driver GUI following the UX Design Principles document. Implement a modern, user-centric interface that respects the observing context and supports light, dark, and astronomy (red) modes.

**Framework:** NiceGUI (retained after evaluation - best balance of cross-platform, lightweight, and theming capability)

**Scope:**
- Complete rewrite of GUI components
- Three visual modes (light, dark, astronomy)
- Progressive disclosure (3 layers)
- Real-time status updates
- Workflow-optimized layouts

**Out of Scope:**
- Mobile/responsive design
- Accessibility (screen readers, ARIA)
- Remote multi-user support

---

## Architecture Overview

### Component Structure

```
gui/
├── __init__.py              # GUI package initialization
├── app.py                   # NiceGUI app setup and routing
├── themes.py                # Theme definitions (light, dark, astronomy)
├── state.py                 # Reactive state management
├── components/
│   ├── __init__.py
│   ├── status/              # Status display components
│   │   ├── position.py      # RA/Dec, Alt/Az display
│   │   ├── tracking.py      # Tracking mode indicator
│   │   ├── connection.py    # Connection status
│   │   ├── hardware.py      # Motor/hardware status
│   │   └── alignment.py     # Alignment quality display
│   ├── controls/            # Interactive controls
│   │   ├── slew.py          # Slew controls (directional, goto)
│   │   ├── tracking.py      # Tracking controls
│   │   ├── alignment.py     # Alignment controls
│   │   └── park.py          # Park/unpark controls
│   ├── panels/              # Composite panels
│   │   ├── main_status.py   # Primary status panel
│   │   ├── control_panel.py # Main control panel
│   │   ├── diagnostics.py   # Layer 3 diagnostics
│   │   └── config.py        # Configuration panel
│   └── common/              # Shared components
│       ├── card.py          # Styled card container
│       ├── value_display.py # Numeric value with label
│       ├── indicator.py     # Status indicator (LED-style)
│       └── notification.py  # Toast/notification component
├── layouts/
│   ├── __init__.py
│   ├── main.py              # Main application layout
│   └── setup.py             # Initial setup wizard layout
└── services/
    ├── __init__.py
    ├── data_service.py      # Data fetching from backend
    └── websocket.py         # Real-time updates
```

---

## Phase 1: Foundation

### 1.1 Create Package Structure

Create the `gui/` package with initial files:
- `__init__.py` - Package exports
- `app.py` - NiceGUI application setup
- `state.py` - Reactive state container

### 1.2 Implement Theme System (`themes.py`)

**Three Themes:**

```python
THEMES = {
    'light': {
        'name': 'Light',
        'background': '#ffffff',
        'surface': '#f5f5f5',
        'primary': '#1976d2',
        'text': '#212121',
        'text_secondary': '#757575',
        'success': '#4caf50',
        'warning': '#ff9800',
        'error': '#f44336',
        'border': '#e0e0e0',
    },
    'dark': {
        'name': 'Dark',
        'background': '#121212',
        'surface': '#1e1e1e',
        'primary': '#90caf9',
        'text': '#ffffff',
        'text_secondary': '#b0b0b0',
        'success': '#81c784',
        'warning': '#ffb74d',
        'error': '#e57373',
        'border': '#333333',
    },
    'astronomy': {
        'name': 'Astronomy',
        'background': '#0a0000',
        'surface': '#1a0000',
        'primary': '#ff3333',
        'text': '#ff6666',
        'text_secondary': '#993333',
        'success': '#ff4444',
        'warning': '#ff5555',
        'error': '#ff2222',
        'border': '#330000',
        # Special: all colors are red-spectrum only
    },
}
```

**CSS Generation:**
- Generate CSS custom properties from theme
- Apply via NiceGUI's `ui.add_css()`
- Support runtime theme switching

### 1.3 Implement State Management (`state.py`)

Reactive state container for UI updates:

```python
@dataclass
class TelescopeState:
    # Connection
    connected: bool = False
    connection_error: Optional[str] = None

    # Position (updated at 1-2 Hz)
    ra_hours: float = 0.0
    dec_degrees: float = 0.0
    alt_degrees: float = 0.0
    az_degrees: float = 0.0
    sidereal_time: float = 0.0

    # Tracking
    tracking_enabled: bool = False
    tracking_rate: str = "sidereal"
    slewing: bool = False

    # Hardware
    at_park: bool = False
    at_home: bool = False

    # Alignment
    alignment_state: str = "disabled"
    alignment_error_arcsec: float = 0.0
    geometry_determinant: float = 0.0
    last_decision: str = "none"

    # UI State
    current_theme: str = "dark"
    disclosure_level: int = 1  # 1, 2, or 3
```

---

## Phase 2: Common Components

### 2.1 Card Component (`components/common/card.py`)

Styled container with consistent appearance:

```python
def card(title: Optional[str] = None,
         collapsible: bool = False,
         level: int = 1) -> ui.card:
    """
    Create a themed card container.

    Args:
        title: Optional card header
        collapsible: Allow collapse/expand
        level: Disclosure level (1=always, 2=expanded, 3=advanced)
    """
```

### 2.2 Value Display (`components/common/value_display.py`)

Numeric value with label, formatted appropriately:

```python
def value_display(label: str,
                  value: Union[str, float],
                  unit: Optional[str] = None,
                  format_spec: str = ".2f",
                  monospace: bool = True,
                  size: str = "normal") -> ui.element:
    """
    Display a labeled value with consistent styling.

    Args:
        label: Description text
        value: The value to display
        unit: Optional unit suffix
        format_spec: Python format specification
        monospace: Use monospace font for value
        size: "small", "normal", or "large"
    """
```

### 2.3 Status Indicator (`components/common/indicator.py`)

LED-style status indicator:

```python
def indicator(status: str,
              label: Optional[str] = None,
              pulse: bool = False) -> ui.element:
    """
    LED-style status indicator.

    Args:
        status: "ok", "warning", "error", "inactive"
        label: Optional label text
        pulse: Animate when active
    """
```

### 2.4 Notification Component (`components/common/notification.py`)

Toast notifications following severity levels:

```python
def notify(message: str,
           severity: str = "info",
           duration: Optional[int] = None,
           action: Optional[Callable] = None) -> None:
    """
    Show notification toast.

    Args:
        message: Notification text
        severity: "info", "warning", "error", "critical"
        duration: Auto-dismiss time (ms), None for persistent
        action: Optional action callback
    """
```

---

## Phase 3: Status Components

### 3.1 Position Display (`components/status/position.py`)

Primary status - highest visual priority:

```python
def position_display(state: TelescopeState) -> ui.element:
    """
    Display current telescope position.

    Shows:
    - RA/Dec in HMS/DMS format
    - Alt/Az in degrees
    - Local sidereal time
    - Pier side indicator

    Updates: 1-2 Hz for smooth perception
    """
```

**Layout:**
```
┌─────────────────────────────────────┐
│  RA   12h 34m 56.7s    Alt  45.2°  │
│  Dec  +12° 34' 56"     Az  123.4°  │
│                                     │
│  LST  08h 12m 34s      Pier: East  │
└─────────────────────────────────────┘
```

### 3.2 Tracking Display (`components/status/tracking.py`)

Secondary status:

```python
def tracking_display(state: TelescopeState) -> ui.element:
    """
    Display tracking status.

    Shows:
    - Tracking enabled/disabled indicator
    - Current tracking rate
    - Slewing indicator (when active)
    """
```

### 3.3 Connection Status (`components/status/connection.py`)

Tertiary status:

```python
def connection_status(state: TelescopeState) -> ui.element:
    """
    Display connection health.

    Shows:
    - Connected/disconnected indicator
    - Serial port info
    - Last communication timestamp
    - Error message (if any)
    """
```

### 3.4 Hardware Status (`components/status/hardware.py`)

Tertiary status (Layer 2):

```python
def hardware_status(state: TelescopeState) -> ui.element:
    """
    Display hardware state.

    Shows:
    - Park/Home status
    - Motor states (when available)
    - GPS fix status (if enabled)
    """
```

### 3.5 Alignment Status (`components/status/alignment.py`)

Tertiary status (Layer 2/3):

```python
def alignment_status(state: TelescopeState) -> ui.element:
    """
    Display alignment monitor status.

    Layer 2:
    - Current state
    - Total error (color-coded)
    - Geometry quality

    Layer 3:
    - Detailed error breakdown
    - Decision history
    - Health alerts
    """
```

---

## Phase 4: Control Components

### 4.1 Slew Controls (`components/controls/slew.py`)

```python
def slew_controls(state: TelescopeState,
                  on_slew: Callable,
                  on_stop: Callable,
                  on_goto: Callable) -> ui.element:
    """
    Directional slew controls.

    Shows:
    - N/S/E/W directional buttons
    - Speed selector (Guide, Center, Find, Max)
    - Stop button (prominent)
    - GoTo input (RA/Dec or object name)
    """
```

**Layout:**
```
        [N]
    [W] [■] [E]     Speed: [▾ Center]
        [S]

    RA:  [____________]
    Dec: [____________]
    [   Go To   ] [  STOP  ]
```

### 4.2 Tracking Controls (`components/controls/tracking.py`)

```python
def tracking_controls(state: TelescopeState,
                      on_toggle: Callable,
                      on_rate_change: Callable) -> ui.element:
    """
    Tracking enable/disable and rate selection.

    Shows:
    - Track On/Off toggle
    - Rate selector (Sidereal, Lunar, Solar, King)
    """
```

### 4.3 Park Controls (`components/controls/park.py`)

```python
def park_controls(state: TelescopeState,
                  on_park: Callable,
                  on_unpark: Callable,
                  on_set_park: Callable,
                  on_home: Callable) -> ui.element:
    """
    Park and home controls.

    Shows:
    - Park / Unpark button
    - Set Park Position button
    - Find Home button
    """
```

### 4.4 Alignment Controls (`components/controls/alignment.py`)

```python
def alignment_controls(state: TelescopeState,
                       on_sync: Callable,
                       on_measure: Callable) -> ui.element:
    """
    Alignment operations.

    Shows:
    - Sync to coordinates
    - Manual measure (trigger plate solve)
    - Camera source indicator
    """
```

---

## Phase 5: Panels

### 5.1 Main Status Panel (`components/panels/main_status.py`)

Combines status components with proper hierarchy:

```python
def main_status_panel(state: TelescopeState) -> ui.element:
    """
    Primary status panel - always visible.

    Contains:
    - Position display (Layer 1)
    - Tracking display (Layer 1)
    - Connection indicator (Layer 1)

    Expandable:
    - Hardware status (Layer 2)
    - Alignment status (Layer 2)
    """
```

### 5.2 Control Panel (`components/panels/control_panel.py`)

Combines control components:

```python
def control_panel(state: TelescopeState,
                  handlers: dict) -> ui.element:
    """
    Main control panel.

    Contains:
    - Slew controls (Layer 1)
    - Tracking controls (Layer 1)
    - Park controls (Layer 1)

    Expandable:
    - Alignment controls (Layer 2)
    """
```

### 5.3 Diagnostics Panel (`components/panels/diagnostics.py`)

Layer 3 advanced information:

```python
def diagnostics_panel(state: TelescopeState) -> ui.element:
    """
    Advanced diagnostics (Layer 3).

    Contains:
    - Log viewer (filterable)
    - Command history
    - Raw motor data
    - Communication trace
    - Performance metrics
    """
```

### 5.4 Configuration Panel (`components/panels/config.py`)

Settings interface:

```python
def config_panel(config: Config,
                 on_save: Callable) -> ui.element:
    """
    Configuration settings panel.

    Sections:
    - Connection (serial port)
    - Site (lat/lon/elevation)
    - Alignment monitor settings
    - Camera source selection
    - GUI preferences (theme, disclosure level)
    """
```

---

## Phase 6: Main Layout

### 6.1 Application Layout (`layouts/main.py`)

```python
def main_layout(state: TelescopeState,
                handlers: dict) -> None:
    """
    Main application layout.

    Structure:
    ┌─────────────────────────────────────────┐
    │ Header: Title, Theme Toggle, Settings   │
    ├────────────────────┬────────────────────┤
    │                    │                    │
    │   Status Panel     │   Control Panel    │
    │   (Left, 60%)      │   (Right, 40%)     │
    │                    │                    │
    ├────────────────────┴────────────────────┤
    │ Footer: Connection, Disclosure Toggle   │
    └─────────────────────────────────────────┘
    """
```

### 6.2 Header Component

```python
def header(state: TelescopeState,
           on_theme_change: Callable,
           on_settings: Callable) -> ui.element:
    """
    Application header.

    Contains:
    - App title/logo
    - Theme selector (Light/Dark/Astronomy)
    - Settings button
    - Notification area
    """
```

### 6.3 Footer Component

```python
def footer(state: TelescopeState,
           on_disclosure_change: Callable) -> ui.element:
    """
    Application footer.

    Contains:
    - Connection status summary
    - Disclosure level toggle (1/2/3)
    - Version info
    """
```

---

## Phase 7: Services

### 7.1 Data Service (`services/data_service.py`)

Fetch data from backend:

```python
class DataService:
    """
    Service for fetching telescope data.

    Methods:
    - get_status() -> dict
    - send_command(cmd, params) -> dict
    - get_config() -> dict
    - save_config(config) -> bool
    """
```

### 7.2 WebSocket Service (`services/websocket.py`)

Real-time updates:

```python
class WebSocketService:
    """
    Real-time update service.

    Provides:
    - Position updates at 1-2 Hz
    - State change notifications
    - Error/warning propagation
    """
```

---

## Phase 8: Integration

### 8.1 Replace `telescope_gui.py`

Refactor entry point to use new GUI package:

```python
# telescope_gui.py (new)
from gui import create_app

def start_gui(config, device, logger):
    """Start the NiceGUI application."""
    app = create_app(config, device, logger)
    app.run()
```

### 8.2 Update `app.py` (main)

Update GUI initialization in main application.

### 8.3 Deprecate Old Files

Mark for removal:
- `telescope_gui.py` (old implementation)
- `telescope_data.py` (replaced by services)
- `telescope_commands.py` (integrated into handlers)

---

## Phase 9: Testing

### 9.1 Component Tests

Test individual components in isolation:
- Theme application
- Value formatting
- State reactivity

### 9.2 Integration Tests

Test component composition:
- Layout renders correctly
- Data flows through components
- Theme switching works

### 9.3 Visual Testing

Manual verification:
- All three themes render correctly
- Astronomy mode uses only red spectrum
- Information hierarchy is clear
- Real-time updates are smooth

---

## Phase 10: Documentation

### 10.1 Update `CLAUDE.md`

Document new GUI architecture:
- Component structure
- Theme system
- State management
- Development patterns

### 10.2 Create `gui/README.md`

Developer documentation:
- Component creation guide
- Theme customization
- Adding new panels

---

## Implementation Checklist

### Phase 1: Foundation
- [ ] Create `gui/` package structure
- [ ] Implement `gui/themes.py`
- [ ] Implement `gui/state.py`
- [ ] Implement `gui/app.py` (skeleton)

### Phase 2: Common Components
- [ ] Implement `card` component
- [ ] Implement `value_display` component
- [ ] Implement `indicator` component
- [ ] Implement `notification` component

### Phase 3: Status Components
- [ ] Implement `position_display`
- [ ] Implement `tracking_display`
- [ ] Implement `connection_status`
- [ ] Implement `hardware_status`
- [ ] Implement `alignment_status`

### Phase 4: Control Components
- [ ] Implement `slew_controls`
- [ ] Implement `tracking_controls`
- [ ] Implement `park_controls`
- [ ] Implement `alignment_controls`

### Phase 5: Panels
- [ ] Implement `main_status_panel`
- [ ] Implement `control_panel`
- [ ] Implement `diagnostics_panel`
- [ ] Implement `config_panel`

### Phase 6: Layout
- [ ] Implement `main_layout`
- [ ] Implement `header`
- [ ] Implement `footer`
- [ ] Wire up all panels

### Phase 7: Services
- [ ] Implement `DataService`
- [ ] Implement `WebSocketService`
- [ ] Connect to existing backend

### Phase 8: Integration
- [ ] Refactor `telescope_gui.py`
- [ ] Update `app.py` initialization
- [ ] Remove deprecated files

### Phase 9: Testing
- [ ] Unit tests for components
- [ ] Integration tests
- [ ] Visual verification (all themes)

### Phase 10: Documentation
- [ ] Update `CLAUDE.md`
- [ ] Create `gui/README.md`

---

## Visual Design Specifications

### Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Title | System | 24px | 600 |
| Section Header | System | 18px | 500 |
| Label | System | 14px | 400 |
| Value (numeric) | Monospace | 16px | 400 |
| Value (large) | Monospace | 24px | 500 |
| Small text | System | 12px | 400 |

### Spacing

| Element | Value |
|---------|-------|
| Card padding | 16px |
| Component gap | 12px |
| Section gap | 24px |
| Border radius | 8px |

### Astronomy Mode Colors (Red Spectrum Only)

All colors must be within the red spectrum (>620nm wavelength equivalent):

| Purpose | Color | Hex |
|---------|-------|-----|
| Background | Very dark red | `#0a0000` |
| Surface | Dark red | `#1a0000` |
| Primary | Bright red | `#ff3333` |
| Text | Light red | `#ff6666` |
| Text secondary | Dim red | `#993333` |
| Border | Dark red | `#330000` |
| Success | Red (brightness) | `#ff4444` |
| Warning | Brighter red | `#ff5555` |
| Error | Intense red | `#ff2222` |

---

## Update Rates

| Data | Rate | Method |
|------|------|--------|
| Position | 1-2 Hz | WebSocket push |
| Tracking status | On change | WebSocket push |
| Connection status | On change + 5s heartbeat | WebSocket push |
| Alignment metrics | On change | WebSocket push |
| Hardware status | 1 Hz | Polling |
| Diagnostics | On demand | Polling |

---

## Progressive Disclosure Implementation

### Layer 1 (Default)
Always visible, essential for routine operation:
- Position display
- Tracking status/controls
- Basic slew controls
- Connection indicator
- Park/Unpark

### Layer 2 (Expanded)
Additional details, toggle via footer:
- Hardware status details
- Alignment monitor status
- Alignment controls
- Speed selection
- GoTo coordinates

### Layer 3 (Advanced)
Diagnostics/developer access:
- Log viewer
- Command history
- Raw data display
- Performance metrics
- Configuration editing

**Toggle Implementation:**
Footer contains disclosure selector (1/2/3). Components check `state.disclosure_level` and render conditionally.

---

## Estimated Effort

| Phase | Effort |
|-------|--------|
| Phase 1 (Foundation) | 3-4 hours |
| Phase 2 (Common Components) | 2-3 hours |
| Phase 3 (Status Components) | 3-4 hours |
| Phase 4 (Control Components) | 3-4 hours |
| Phase 5 (Panels) | 2-3 hours |
| Phase 6 (Layout) | 2-3 hours |
| Phase 7 (Services) | 2-3 hours |
| Phase 8 (Integration) | 2-3 hours |
| Phase 9-10 (Testing/Docs) | 3-4 hours |
| **Total** | **22-31 hours** |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| NiceGUI limitations | Prototype critical components early |
| Astronomy mode color accuracy | Test on actual display in dark; adjust as needed |
| Real-time performance | Profile early; optimize WebSocket payload |
| State management complexity | Keep state flat; avoid deep nesting |
| Theme switching glitches | Test thoroughly; use CSS transitions |

---

## Success Criteria

1. **Information Hierarchy:** Position/tracking clearly dominant
2. **Theme Switching:** All three themes work correctly
3. **Astronomy Mode:** No blue/green light leakage
4. **Progressive Disclosure:** All three layers functional
5. **Real-time Updates:** Position updates feel smooth (no jitter)
6. **Staleness Indication:** Clear indication when data is stale
7. **Error Recovery:** Clear guidance on errors
8. **Performance:** No perceptible lag on Raspberry Pi
