# ZWO Camera Integration for Plate Solving - Implementation Plan

## Project Overview

### Context
This module is part of a Python Alpaca telescope mount driver. The purpose is to integrate ZWO ASI cameras to enable automated plate solving for alignment monitoring. The plate solving workflow requires capturing single-exposure images from the camera and passing them to a plate solver.

### Goals
1. Provide a clean, minimal Python interface for ZWO camera capture
2. Support Windows, macOS, and Linux (including Raspberry Pi armv7 and armv8)
3. Gracefully degrade when no camera is present
4. Bundle ZWO SDK binaries for user convenience
5. Expose only the functionality needed for plate solving (not full camera control)

### Non-Goals
- Video capture mode
- Cooling control
- Filter wheel integration
- GUI components
- Full camera control suite

---

## Technical Decision: Use `python-zwoasi`

After evaluating available options, the recommended approach is to use the `python-zwoasi` library as the foundation. This library:

- Is pure Python (ctypes-based) — no compilation required
- Handles cross-platform differences in library loading
- Has a mature, well-tested API
- Returns NumPy arrays directly (convenient for plate solver integration)
- Is MIT licensed

**PyPI Package:** `zwoasi`  
**Repository:** https://github.com/python-zwoasi/python-zwoasi  
**Documentation:** https://zwoasi.readthedocs.io/

---

## Architecture

### Module Structure

```
zwo_capture/
├── __init__.py              # Public API exports
├── camera.py                # Main camera interface class
├── sdk_loader.py            # Platform-specific SDK resolution
├── exceptions.py            # Custom exception hierarchy
├── config.py                # Default capture settings for plate solving
└── sdk/                     # Bundled SDK binaries (see below)
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

### Dependency on python-zwoasi

The module wraps `python-zwoasi` rather than reimplementing ctypes bindings. This provides:
- Proven cross-platform library loading
- Correct ctypes structure definitions
- Error code translation to exceptions

### Public API Design

```python
# Primary interface - context manager pattern
from zwo_capture import ZWOCamera, list_cameras, is_available

# Check if any cameras are available (non-throwing)
if is_available():
    cameras = list_cameras()  # Returns list of camera info dicts
    
    # Use context manager for automatic resource cleanup
    with ZWOCamera(camera_id=0) as cam:
        # Configure for plate solving
        cam.configure(
            exposure_ms=1000,
            gain=100,
            binning=2,
            image_type='RAW16'  # or 'RAW8', 'RGB24'
        )
        
        # Capture returns NumPy array
        image = cam.capture()
        
        # Get metadata for plate solver
        info = cam.get_camera_info()
        # Returns: pixel_size_um, sensor_width, sensor_height, etc.
```

---

## Detailed Implementation Specifications

### File: `exceptions.py`

Define a custom exception hierarchy:

```python
class ZWOError(Exception):
    """Base exception for all ZWO camera errors."""
    pass

class ZWONotAvailable(ZWOError):
    """Raised when ZWO SDK cannot be loaded or no cameras found."""
    pass

class ZWOCameraError(ZWOError):
    """Raised when camera operations fail."""
    pass

class ZWOTimeoutError(ZWOCameraError):
    """Raised when capture times out."""
    pass

class ZWOConfigurationError(ZWOCameraError):
    """Raised when invalid configuration is requested."""
    pass
```

### File: `sdk_loader.py`

Responsibilities:
1. Detect current platform and architecture
2. Locate SDK binary (bundled or system)
3. Initialize `zwoasi` library with correct path
4. Handle macOS quarantine attribute if needed

Platform detection logic:

| Platform | Architecture | SDK Path |
|----------|--------------|----------|
| Windows | x64 | `sdk/windows/x64/ASICamera2.dll` |
| Windows | x86 | `sdk/windows/x86/ASICamera2.dll` |
| macOS | any | `sdk/macos/libASICamera2.dylib` |
| Linux | x86_64 | `sdk/linux/x64/libASICamera2.so` |
| Linux | armv7l | `sdk/linux/armv7/libASICamera2.so` |
| Linux | aarch64 | `sdk/linux/armv8/libASICamera2.so` |

The loader should:
1. First check for `ZWO_ASI_LIB` environment variable (allows user override)
2. Then check bundled SDK path
3. Then attempt system library (via `ctypes.util.find_library`)
4. Raise `ZWONotAvailable` with descriptive message if all fail

**Important macOS consideration:** The SDK dylib may be quarantined by Gatekeeper. Document that users may need to run:
```bash
xattr -d com.apple.quarantine /path/to/libASICamera2.dylib
```

### File: `config.py`

Define sensible defaults for plate solving:

```python
# Default capture settings optimized for plate solving
DEFAULT_CONFIG = {
    'exposure_ms': 2000,      # 2 second exposure
    'gain': 100,              # Moderate gain
    'binning': 2,             # 2x2 binning for faster readout and smaller files
    'image_type': 'RAW16',    # 16-bit for better dynamic range
    'bandwidth': 80,          # USB bandwidth percentage
    'high_speed_mode': False, # Prioritize quality over speed
    'timeout_ms': 30000,      # 30 second timeout for long exposures
}

# Image type mapping
IMAGE_TYPES = {
    'RAW8': 0,    # ASI_IMG_RAW8
    'RGB24': 1,   # ASI_IMG_RGB24  
    'RAW16': 2,   # ASI_IMG_RAW16
    'Y8': 3,      # ASI_IMG_Y8
}

# Supported binning modes (camera-dependent, these are common)
SUPPORTED_BINNING = [1, 2, 3, 4]
```

### File: `camera.py`

Main camera interface class. Key methods:

#### `__init__(self, camera_id: int = 0)`
- Store camera ID
- Do NOT open camera yet (defer to `open()` or context manager)

#### `open(self) -> None`
- Call `zwoasi.Camera(camera_id)`
- Store camera properties (max width, height, pixel size, etc.)
- Set default ROI to full frame

#### `close(self) -> None`
- Release camera resources
- Safe to call multiple times (idempotent)

#### `__enter__` / `__exit__`
- Context manager support
- `__exit__` must handle exceptions and still close camera

#### `configure(self, exposure_ms, gain, binning, image_type, **kwargs) -> None`
- Validate parameters against camera capabilities
- Set ROI format (apply binning)
- Set control values (exposure, gain, bandwidth)
- Raise `ZWOConfigurationError` for invalid settings

#### `capture(self, timeout_ms: int = None) -> numpy.ndarray`
- Perform single-frame capture
- Return image as NumPy array
- Raise `ZWOTimeoutError` if exposure doesn't complete
- Array shape depends on binning and image type:
  - RAW8/RAW16: (height, width)
  - RGB24: (height, width, 3)

#### `get_camera_info(self) -> dict`
- Return camera properties needed for plate solving:
  - `name`: Camera model name
  - `pixel_size_um`: Pixel size in micrometers
  - `sensor_width`: Full sensor width in pixels
  - `sensor_height`: Full sensor height in pixels
  - `is_color`: Boolean
  - `bayer_pattern`: Bayer pattern if color camera
  - `bit_depth`: Native bit depth
  - `current_binning`: Current binning setting
  - `current_width`: Current ROI width (after binning)
  - `current_height`: Current ROI height (after binning)

### File: `__init__.py`

Public API exports:

```python
from .camera import ZWOCamera
from .exceptions import (
    ZWOError,
    ZWONotAvailable, 
    ZWOCameraError,
    ZWOTimeoutError,
    ZWOConfigurationError,
)

def is_available() -> bool:
    """
    Check if ZWO camera support is available.
    
    Returns True if SDK can be loaded. Does not check for connected cameras.
    This is a non-throwing function suitable for feature detection.
    """
    ...

def list_cameras() -> list[dict]:
    """
    List all connected ZWO cameras.
    
    Returns list of dicts with camera info (id, name, etc.)
    Returns empty list if no cameras connected.
    Raises ZWONotAvailable if SDK cannot be loaded.
    """
    ...

__all__ = [
    'ZWOCamera',
    'is_available',
    'list_cameras',
    'ZWOError',
    'ZWONotAvailable',
    'ZWOCameraError', 
    'ZWOTimeoutError',
    'ZWOConfigurationError',
]
```

---

## Error Handling Strategy

### Graceful Degradation

The module must support graceful degradation at multiple levels:

1. **SDK not available**: `is_available()` returns `False`, other functions raise `ZWONotAvailable`
2. **No cameras connected**: `list_cameras()` returns `[]`, `ZWOCamera()` raises `ZWOCameraError`
3. **Camera disconnected mid-operation**: Raise `ZWOCameraError` with descriptive message
4. **Invalid configuration**: Raise `ZWOConfigurationError` before attempting operation

### Logging

Use Python's `logging` module with a named logger:

```python
import logging
logger = logging.getLogger('zwo_capture')
```

Log levels:
- `DEBUG`: All SDK calls and their results
- `INFO`: Camera open/close, capture start/complete
- `WARNING`: Recoverable issues (e.g., requested setting adjusted to valid range)
- `ERROR`: Failed operations

---

## Platform-Specific Considerations

### Windows
- SDK requires native driver installation for camera to be recognized
- DLL must match Python architecture (x64 vs x86)
- Use `ctypes.WinDLL` or let `zwoasi` handle it

### macOS
- No native driver required (uses libusb)
- Gatekeeper quarantine must be removed from dylib
- Apple Silicon (M1/M2/M3) runs x64 code via Rosetta; use the same dylib

### Linux
- No native driver required (uses libusb)  
- udev rules required for non-root camera access
- Must install: `libusb-1.0-0` (or equivalent)
- RPi 4/5 in 64-bit mode uses armv8; 32-bit mode uses armv7

#### Linux udev Rules

Document that users need to install udev rules. Create a file `99-asi-cameras.rules`:

```
# ZWO ASI Cameras
SUBSYSTEM=="usb", ATTR{idVendor}=="03c3", MODE="0666"
```

Install with:
```bash
sudo cp 99-asi-cameras.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

---

## SDK Binary Acquisition

The ZWO SDK must be downloaded from ZWO's official site:
- URL: https://www.zwoastro.com/software/ → "For Developers" → "ASI Camera SDK"
- Current version: 1.41 (as of January 2026)

The SDK ZIP contains pre-built binaries for all platforms. Extract the appropriate files into the `sdk/` directory structure defined above.

**Licensing:** The ZWO SDK is provided for free redistribution with ZWO camera software. Include appropriate attribution in your project's documentation.

---

## Testing Strategy

### Unit Tests (No Hardware)

Mock the `zwoasi` module to test:
- SDK loader platform detection logic
- Configuration validation
- Exception handling
- Context manager behavior

### Integration Tests (Hardware Required)

These tests require a physical ZWO camera:
- Camera enumeration
- Open/close cycle
- Capture with various settings
- Verify NumPy array dimensions match expected values

Mark hardware tests with pytest marker:
```python
@pytest.mark.hardware
def test_capture_raw16():
    ...
```

### Test Matrix

| Test | Windows | macOS | Linux x64 | RPi |
|------|---------|-------|-----------|-----|
| SDK loader | ✓ | ✓ | ✓ | ✓ |
| No camera graceful | ✓ | ✓ | ✓ | ✓ |
| Capture RAW8 | HW | HW | HW | HW |
| Capture RAW16 | HW | HW | HW | HW |
| Capture RGB24 | HW | HW | HW | HW |
| Binning 1x/2x/4x | HW | HW | HW | HW |

---

## Integration with Plate Solver

The captured NumPy array can be passed directly to plate solvers. Common interfaces:

### ASTAP
Requires saving to FITS file first:
```python
from astropy.io import fits
fits.writeto('temp.fits', image, overwrite=True)
# Then call ASTAP CLI
```

### Astrometry.net (local)
Can accept NumPy array via `solve_from_source` if using Python bindings, or save to FITS.

### Astrometry.net (web API)
Requires saving to PNG/FITS and uploading.

**Recommendation:** The camera module should return the raw NumPy array. A separate utility function can handle FITS export if needed:

```python
def save_fits(image: np.ndarray, path: str, camera_info: dict) -> None:
    """Save captured image as FITS with appropriate headers."""
    ...
```

---

## Implementation Checklist

- [ ] Create package structure
- [ ] Implement `exceptions.py`
- [ ] Implement `config.py`  
- [ ] Implement `sdk_loader.py` with platform detection
- [ ] Implement `camera.py` with ZWOCamera class
- [ ] Implement `__init__.py` with public API
- [ ] Download and organize SDK binaries
- [ ] Write unit tests with mocked SDK
- [ ] Test on Windows (if available)
- [ ] Test on macOS (if available)
- [ ] Test on Linux x64
- [ ] Test on Raspberry Pi
- [ ] Write user documentation
- [ ] Add FITS export utility (optional)

---

## Dependencies

Add to `pyproject.toml` or `requirements.txt`:

```
zwoasi>=0.2.0
numpy>=1.20.0
```

Optional (for FITS export):
```
astropy>=5.0
```

---

## Example Usage

```python
"""
Example: Capture image for plate solving
"""
from zwo_capture import ZWOCamera, is_available, list_cameras

def capture_for_plate_solving(exposure_ms: int = 2000) -> tuple:
    """
    Capture an image suitable for plate solving.
    
    Returns:
        tuple: (image_array, camera_info) or (None, None) if unavailable
    """
    if not is_available():
        return None, None
    
    cameras = list_cameras()
    if not cameras:
        return None, None
    
    with ZWOCamera(camera_id=0) as cam:
        cam.configure(
            exposure_ms=exposure_ms,
            gain=100,
            binning=2,
            image_type='RAW16'
        )
        
        image = cam.capture()
        info = cam.get_camera_info()
        
        return image, info
```

---

## Open Questions / Future Considerations

1. **ROI Support**: Should we allow specifying a sub-region for faster capture? Not needed for initial implementation but may be useful.

2. **Temperature Monitoring**: Some plate solvers use sensor temperature for focus compensation. Consider exposing `get_temperature()` method.

3. **Dark Frame Subtraction**: The SDK supports dark frame subtraction. May improve plate solving accuracy but adds complexity.

4. **Async Capture**: For integration with async Alpaca drivers, consider adding `async capture()` variant using `asyncio.to_thread()`.

---

## References

- ZWO ASI SDK Documentation: Included in SDK download as PDF
- python-zwoasi Documentation: https://zwoasi.readthedocs.io/
- python-zwoasi Source: https://github.com/python-zwoasi/python-zwoasi
- ZWO Software Downloads: https://www.zwoastro.com/software/
