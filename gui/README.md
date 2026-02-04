# TTS160 GUI Package

Web interface for the TTS160 Alpaca Driver with three themes and progressive disclosure.

## Features

- **Three Themes**: Light, Dark, and Astronomy (red-only for night vision)
- **Progressive Disclosure**: Three detail levels (Basic, Expanded, Advanced)
- **Real-time Updates**: Position and status update at 1-2 Hz
- **Modular Components**: Reusable UI components for easy customization

## Architecture

```
gui/
├── __init__.py          # Package exports
├── app.py               # Main application (TelescopeGUI class)
├── themes.py            # Theme definitions and CSS generation
├── state.py             # Reactive state management
├── components/
│   ├── common/          # Shared components (card, indicator, etc.)
│   ├── status/          # Status display components
│   ├── controls/        # Interactive controls
│   └── panels/          # Composite panels
├── layouts/
│   └── main.py          # Main page layout
└── services/
    ├── data_service.py  # Device data polling
    └── websocket.py     # Real-time updates
```

## Quick Start

```python
from gui import create_app, run_app

# Create and run the GUI
gui = create_app(config, device, logger)
run_app(gui, host='0.0.0.0', port=8080)
```

## Themes

Three built-in themes are available:

| Theme | Description |
|-------|-------------|
| `light` | Standard light mode |
| `dark` | Dark mode (default) |
| `astronomy` | Red-only colors for night vision preservation |

Switch themes programmatically:

```python
gui.set_theme('astronomy')
```

Or via the UI theme selector in the header.

### Astronomy Mode

The astronomy theme uses only red-spectrum colors (>620nm equivalent) to preserve night vision adaptation. All text, indicators, and UI elements use shades of red.

## Progressive Disclosure

Three disclosure levels control UI complexity:

| Level | Content |
|-------|---------|
| 1 - Basic | Essential controls and position display |
| 2 - Expanded | Additional status details, alignment info |
| 3 - Advanced | Diagnostics, raw data, command history |

Set via code:

```python
gui.set_disclosure_level(2)
```

Or via the footer controls.

## State Management

The `TelescopeState` class provides reactive state management:

```python
from gui import TelescopeState, create_state

state = create_state()

# Update values (triggers UI refresh)
state.update(
    ra_hours=12.5,
    dec_degrees=45.0,
    tracking_enabled=True
)

# Listen for changes
def on_change(field, value):
    print(f"{field} changed to {value}")

state.add_listener(on_change)
```

### State Fields

| Field | Type | Description |
|-------|------|-------------|
| `connected` | bool | Mount connection status |
| `ra_hours` | float | Right ascension (hours) |
| `dec_degrees` | float | Declination (degrees) |
| `alt_degrees` | float | Altitude (degrees) |
| `az_degrees` | float | Azimuth (degrees) |
| `tracking_enabled` | bool | Tracking active |
| `slewing` | bool | Slew in progress |
| `at_park` | bool | Parked position |
| `alignment_state` | AlignmentState | Alignment monitor state |
| `alignment_error_arcsec` | float | Pointing error |

## Components

### Common Components

```python
from gui.components.common import (
    card,           # Styled container
    value_display,  # Labeled value
    indicator,      # LED-style indicator
    notify,         # Toast notification
)
```

### Status Components

```python
from gui.components.status import (
    position_display,    # RA/Dec/Alt/Az
    tracking_display,    # Tracking status
    connection_status,   # Connection health
    alignment_status,    # Alignment monitor
)
```

### Control Components

```python
from gui.components.controls import (
    slew_controls,      # Directional pad + GoTo
    tracking_controls,  # Enable/rate
    park_controls,      # Park/unpark/home
    alignment_controls, # Sync/measure
)
```

## Services

### DataService

Polls device data and updates state:

```python
from gui.services import DataService

service = DataService(state, device, config, logger)
service.start()  # Begin polling
service.stop()   # Stop polling
```

### Command Handling

Register command handlers:

```python
gui.register_handler('park', my_park_function)
gui.register_handler('sync', my_sync_function)
```

## Customization

### Adding a New Component

1. Create component in appropriate subpackage
2. Use NiceGUI's reactive binding for state updates
3. Export from subpackage `__init__.py`

Example:

```python
# gui/components/status/custom.py
from nicegui import ui
from ...state import TelescopeState

def custom_display(state: TelescopeState) -> ui.element:
    with ui.card().classes('gui-card') as container:
        label = ui.label()
        label.bind_text_from(state, 'my_field')
    return container
```

### Adding a New Theme

Add to `themes.py`:

```python
THEMES['custom'] = Theme(
    name='Custom',
    background='#1a1a2e',
    surface='#16213e',
    primary='#e94560',
    # ... other colors
)
```

## CSS Classes

| Class | Purpose |
|-------|---------|
| `gui-card` | Themed card container |
| `gui-button` | Primary button |
| `gui-button-stop` | Stop/abort button (red) |
| `gui-input` | Text input |
| `indicator` | LED indicator base |
| `indicator-ok` | Green indicator |
| `indicator-warning` | Yellow indicator |
| `indicator-error` | Red indicator |
| `disclosure-2` | Hidden at level 1 |
| `disclosure-3` | Hidden at levels 1-2 |

## Testing

```bash
python -m pytest tests/unit/test_gui.py -v
```

## Dependencies

- `nicegui>=1.4.0` - Web framework
- No additional dependencies (uses project's existing requirements)
