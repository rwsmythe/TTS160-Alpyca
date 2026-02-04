# ZWO Camera Integration - Implementation Plan

## Overview

**Goal:** Add native ZWO ASI camera support as an alternative to Alpaca cameras for the alignment monitor's plate solving workflow.

**Scope:**
- New `zwo_capture/` package with SDK binaries
- Camera source abstraction in alignment monitor
- Configuration schema updates
- Unit tests with mocked SDK

**Out of Scope:**
- Video capture, cooling control, filter wheels
- GUI components (deferred to UX redesign)
- Full camera control suite

---

## Phase 1: Package Structure & Exceptions

### 1.1 Create Package Directory Structure

```
zwo_capture/
├── __init__.py              # Public API exports
├── camera.py                # Main ZWOCamera class
├── sdk_loader.py            # Platform-specific SDK resolution
├── exceptions.py            # Custom exception hierarchy
├── config.py                # Default capture settings
└── sdk/                     # Bundled SDK binaries
    ├── windows/
    │   ├── x64/
    │   │   └── ASICamera2.dll
    │   └── x86/
    │       └── ASICamera2.dll
    ├── macos/
    │   └── libASICamera2.dylib
    └── linux/
        ├── x64/
        │   └── libASICamera2.so
        ├── armv7/
        │   └── libASICamera2.so
        └── armv8/
            └── libASICamera2.so
```

### 1.2 Implement `exceptions.py`

```python
class ZWOError(Exception):
    """Base exception for all ZWO camera errors."""
    pass

class ZWONotAvailable(ZWOError):
    """SDK cannot be loaded or no cameras found."""
    pass

class ZWOCameraError(ZWOError):
    """Camera operations failed."""
    pass

class ZWOTimeoutError(ZWOCameraError):
    """Capture timed out."""
    pass

class ZWOConfigurationError(ZWOCameraError):
    """Invalid configuration requested."""
    pass
```

### 1.3 Implement `config.py`

Default settings optimized for plate solving:
- 2 second exposure
- Gain 100
- 2x2 binning
- RAW16 format
- 30 second timeout

---

## Phase 2: SDK Loader

### 2.1 Implement `sdk_loader.py`

**Responsibilities:**
1. Detect platform and architecture
2. Locate SDK binary (bundled or system)
3. Initialize `zwoasi` library with correct path
4. Handle platform-specific quirks

**Platform Detection Matrix:**

| Platform | Architecture | SDK Path |
|----------|--------------|----------|
| Windows | x64 | `sdk/windows/x64/ASICamera2.dll` |
| Windows | x86 | `sdk/windows/x86/ASICamera2.dll` |
| macOS | any | `sdk/macos/libASICamera2.dylib` |
| Linux | x86_64 | `sdk/linux/x64/libASICamera2.so` |
| Linux | armv7l | `sdk/linux/armv7/libASICamera2.so` |
| Linux | aarch64 | `sdk/linux/armv8/libASICamera2.so` |

**Resolution Order:**
1. `ZWO_ASI_LIB` environment variable (user override)
2. Bundled SDK path
3. System library via `ctypes.util.find_library`
4. Raise `ZWONotAvailable` with descriptive message

**Key Functions:**
```python
def get_sdk_path() -> Optional[str]:
    """Resolve SDK library path for current platform."""

def initialize_sdk() -> None:
    """Initialize zwoasi with resolved SDK path."""

def is_sdk_available() -> bool:
    """Check if SDK can be loaded (non-throwing)."""
```

---

## Phase 3: Camera Class

### 3.1 Implement `camera.py`

**Class: `ZWOCamera`**

```python
class ZWOCamera:
    def __init__(self, camera_id: int = 0):
        """Store camera ID, defer opening."""

    def open(self) -> None:
        """Open camera, store properties."""

    def close(self) -> None:
        """Release resources (idempotent)."""

    def __enter__(self) -> 'ZWOCamera':
        """Context manager entry."""

    def __exit__(self, *args) -> None:
        """Context manager exit with cleanup."""

    def configure(self,
                  exposure_ms: int,
                  gain: int,
                  binning: int,
                  image_type: str = 'RAW16',
                  **kwargs) -> None:
        """Validate and apply capture settings."""

    def capture(self, timeout_ms: Optional[int] = None) -> np.ndarray:
        """Single-frame capture, returns NumPy array."""

    def get_camera_info(self) -> dict:
        """Return camera properties for plate solver."""
```

**Camera Info Dict:**
```python
{
    'name': str,              # Camera model
    'pixel_size_um': float,   # Pixel size in micrometers
    'sensor_width': int,      # Full sensor width
    'sensor_height': int,     # Full sensor height
    'is_color': bool,
    'bayer_pattern': str,     # If color
    'bit_depth': int,
    'current_binning': int,
    'current_width': int,     # After binning
    'current_height': int,    # After binning
}
```

---

## Phase 4: Public API

### 4.1 Implement `__init__.py`

**Exports:**
```python
from .camera import ZWOCamera
from .exceptions import (
    ZWOError, ZWONotAvailable, ZWOCameraError,
    ZWOTimeoutError, ZWOConfigurationError
)

def is_available() -> bool:
    """Check if ZWO support is available (non-throwing)."""

def list_cameras() -> list[dict]:
    """List connected cameras. Empty if none."""

__all__ = [
    'ZWOCamera', 'is_available', 'list_cameras',
    'ZWOError', 'ZWONotAvailable', 'ZWOCameraError',
    'ZWOTimeoutError', 'ZWOConfigurationError'
]
```

---

## Phase 5: SDK Binaries

### 5.1 Download and Organize SDK

**Source:** https://www.zwoastro.com/software/ → "For Developers" → "ASI Camera SDK"

**Steps:**
1. Download SDK v1.41 (or latest)
2. Extract platform-specific binaries
3. Place in `zwo_capture/sdk/` structure
4. Verify file sizes and checksums

**Expected Files:**
| File | Approx Size |
|------|-------------|
| ASICamera2.dll (x64) | ~2.5 MB |
| ASICamera2.dll (x86) | ~2.0 MB |
| libASICamera2.dylib | ~3.0 MB |
| libASICamera2.so (x64) | ~2.5 MB |
| libASICamera2.so (armv7) | ~2.0 MB |
| libASICamera2.so (armv8) | ~2.5 MB |

### 5.2 Update LICENSE_THIRD_PARTY.md

Add ZWO SDK attribution:
```markdown
## ZWO ASI SDK
- **Source:** https://www.zwoastro.com/
- **License:** Freely redistributable with ZWO camera software
- **Usage:** Native camera control for plate solving
```

---

## Phase 6: Camera Source Abstraction

### 6.1 Create `camera_source.py`

Abstract interface for camera sources:

```python
from abc import ABC, abstractmethod
from typing import Optional
import numpy as np

class CameraSource(ABC):
    """Abstract camera source for alignment monitor."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to camera."""

    @abstractmethod
    def disconnect(self) -> None:
        """Release camera resources."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Check connection status."""

    @abstractmethod
    def capture(self, exposure_sec: float, binning: int) -> Optional[np.ndarray]:
        """Capture single frame."""

    @abstractmethod
    def get_info(self) -> dict:
        """Get camera info for plate solver."""
```

### 6.2 Refactor `camera_manager.py` → `alpaca_camera.py`

Rename and implement `CameraSource` interface:

```python
class AlpacaCamera(CameraSource):
    """Alpaca camera source (existing implementation)."""
    # Wrap existing CameraManager functionality
```

### 6.3 Create `zwo_camera_source.py`

```python
class ZWOCameraSource(CameraSource):
    """ZWO native camera source."""
    # Wrap ZWOCamera with CameraSource interface
```

### 6.4 Create `camera_factory.py`

```python
def create_camera_source(config: TTS160Config) -> CameraSource:
    """Factory function to create appropriate camera source."""
    source_type = config.alignment_camera_source  # "alpaca" or "zwo"

    if source_type == "zwo":
        return ZWOCameraSource(config)
    else:
        return AlpacaCamera(config)
```

---

## Phase 7: Configuration Updates

### 7.1 Update `TTS160Config.py`

Add new properties:

```python
# Camera source selection
@property
def alignment_camera_source(self) -> str:
    """Camera source: 'alpaca' or 'zwo'"""
    return self._get('alignment', 'camera_source', 'alpaca')

# ZWO-specific settings
@property
def zwo_camera_id(self) -> int:
    return self._get('alignment.zwo', 'camera_id', 0)

@property
def zwo_exposure_ms(self) -> int:
    return self._get('alignment.zwo', 'exposure_ms', 2000)

@property
def zwo_gain(self) -> int:
    return self._get('alignment.zwo', 'gain', 100)

@property
def zwo_binning(self) -> int:
    return self._get('alignment.zwo', 'binning', 2)

@property
def zwo_image_type(self) -> str:
    return self._get('alignment.zwo', 'image_type', 'RAW16')
```

### 7.2 Update `TTS160config.toml`

```toml
[alignment]
enabled = false
camera_source = "alpaca"      # "alpaca" or "zwo"

# ... existing settings ...

[alignment.alpaca]
address = "127.0.0.1"
port = 11111
device = 0

[alignment.zwo]
camera_id = 0                 # Camera index if multiple connected
exposure_ms = 2000            # Exposure time in milliseconds
gain = 100                    # Camera gain (0-500 typical)
binning = 2                   # 1, 2, or 4
image_type = "RAW16"          # RAW8, RAW16, or RGB24
```

---

## Phase 8: Alignment Monitor Integration

### 8.1 Update `alignment_monitor.py`

Replace direct `CameraManager` usage with factory:

```python
from camera_factory import create_camera_source

class AlignmentMonitor:
    def __init__(self, config, logger):
        # ...
        self._camera = create_camera_source(config)

    def _connect_camera(self):
        self._camera.connect()

    def _capture_image(self):
        return self._camera.capture(
            exposure_sec=self._config.alignment_exposure_time,
            binning=self._config.alignment_binning
        )
```

---

## Phase 9: Unit Tests

### 9.1 Create `tests/unit/test_zwo_capture.py`

**Test Categories:**

1. **SDK Loader Tests** (mocked)
   - Platform detection logic
   - Path resolution order
   - Graceful failure when SDK missing

2. **Exception Tests**
   - Exception hierarchy
   - Error message clarity

3. **Camera Class Tests** (mocked zwoasi)
   - Context manager behavior
   - Configuration validation
   - Capture returns correct shape
   - Close is idempotent

4. **Public API Tests**
   - `is_available()` returns bool
   - `list_cameras()` returns list

### 9.2 Create `tests/unit/test_camera_source.py`

- Factory creates correct source type
- AlpacaCamera implements interface
- ZWOCameraSource implements interface

---

## Phase 10: Documentation

### 10.1 Update `CLAUDE.md`

Add ZWO capture documentation:
- Module structure
- Configuration reference
- Platform-specific notes (udev rules, Gatekeeper)

### 10.2 Update `requirements.txt`

```
zwoasi>=0.2.0
```

### 10.3 Create `zwo_capture/README.md`

Platform setup instructions:
- Windows: Driver installation
- macOS: Gatekeeper quarantine removal
- Linux: udev rules, libusb

---

## Implementation Checklist

### Phase 1: Package Structure
- [ ] Create `zwo_capture/` directory
- [ ] Create `zwo_capture/__init__.py` (stub)
- [ ] Implement `zwo_capture/exceptions.py`
- [ ] Implement `zwo_capture/config.py`

### Phase 2: SDK Loader
- [ ] Implement `zwo_capture/sdk_loader.py`
- [ ] Test platform detection on Windows
- [ ] Test platform detection on current system

### Phase 3: Camera Class
- [ ] Implement `zwo_capture/camera.py`
- [ ] Handle all zwoasi exceptions
- [ ] Verify NumPy array shapes

### Phase 4: Public API
- [ ] Complete `zwo_capture/__init__.py`
- [ ] Implement `is_available()`
- [ ] Implement `list_cameras()`

### Phase 5: SDK Binaries
- [ ] Download ZWO SDK
- [ ] Extract and organize binaries
- [ ] Update `LICENSE_THIRD_PARTY.md`
- [ ] Add `.gitattributes` for binary files

### Phase 6: Camera Abstraction
- [ ] Create `camera_source.py` interface
- [ ] Refactor `camera_manager.py` → `alpaca_camera.py`
- [ ] Create `zwo_camera_source.py`
- [ ] Create `camera_factory.py`

### Phase 7: Configuration
- [ ] Update `TTS160Config.py` with new properties
- [ ] Update `TTS160config.toml` with new sections
- [ ] Update `tests/unit/test_config.py`

### Phase 8: Integration
- [ ] Update `alignment_monitor.py` to use factory
- [ ] Update `tests/unit/test_alignment_monitor.py`
- [ ] Run full test suite

### Phase 9: Unit Tests
- [ ] Create `tests/unit/test_zwo_capture.py`
- [ ] Create `tests/unit/test_camera_source.py`
- [ ] Achieve >80% coverage on new code

### Phase 10: Documentation
- [ ] Update `CLAUDE.md`
- [ ] Update `requirements.txt`
- [ ] Create `zwo_capture/README.md`

---

## Verification Criteria

1. **Unit Tests Pass:** All new and existing tests pass
2. **Import Validation:** `python -c "from zwo_capture import ZWOCamera, is_available"`
3. **Graceful Degradation:** When no ZWO camera present, `is_available()` returns `False`
4. **Config Validation:** New TOML sections parse correctly
5. **Backwards Compatibility:** Existing Alpaca camera workflow unchanged when `camera_source = "alpaca"`

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| SDK binary licensing | Verify ZWO redistribution terms; document in LICENSE_THIRD_PARTY.md |
| Platform-specific failures | Comprehensive platform detection; clear error messages |
| python-zwoasi API changes | Pin version in requirements.txt |
| Large binary files in repo | Use `.gitattributes` for LFS if needed; compress if possible |

---

## Estimated Effort

| Phase | Effort |
|-------|--------|
| Phase 1-4 (Core package) | 2-3 hours |
| Phase 5 (SDK binaries) | 1 hour |
| Phase 6 (Abstraction) | 2 hours |
| Phase 7 (Configuration) | 1 hour |
| Phase 8 (Integration) | 1-2 hours |
| Phase 9-10 (Tests/Docs) | 2 hours |
| **Total** | **9-12 hours** |
