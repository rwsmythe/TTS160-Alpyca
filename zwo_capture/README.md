# ZWO Camera Capture Module

Native ZWO ASI camera support for the TTS160 Alpaca Driver alignment monitor.

## Overview

This module provides a clean Python interface for capturing images from ZWO ASI cameras, optimized for plate solving workflows. It wraps the `python-zwoasi` library with additional validation, error handling, and cross-platform SDK management.

## Installation

### 1. Install Python Dependencies

```bash
pip install zwoasi numpy
```

### 2. SDK Setup

The ZWO ASI SDK must be available for the camera to function. The module searches for the SDK in this order:

1. `ZWO_ASI_LIB` environment variable (custom path)
2. Bundled SDK in `zwo_capture/sdk/` directory
3. System-installed library

#### Option A: Bundled SDK (Recommended)

SDK binaries are bundled in this repository for all supported platforms. Alternatively, download the SDK from [ZWO Software Downloads](https://www.zwoastro.com/software/) and extract the appropriate binary to the `sdk/` directory:

```
zwo_capture/sdk/
├── windows/
│   ├── x64/ASICamera2.dll      # 64-bit Windows
│   └── x86/ASICamera2.dll      # 32-bit Windows
├── macos/
│   └── libASICamera2.dylib     # macOS (Intel and Apple Silicon)
└── linux/
    ├── x64/libASICamera2.so    # 64-bit Linux (x86_64)
    ├── armv7/libASICamera2.so  # Raspberry Pi 32-bit
    └── armv8/libASICamera2.so  # Raspberry Pi 64-bit
```

#### Option B: Environment Variable

Set `ZWO_ASI_LIB` to the full path of the SDK library:

```bash
# Windows
set ZWO_ASI_LIB=C:\path\to\ASICamera2.dll

# Linux/macOS
export ZWO_ASI_LIB=/path/to/libASICamera2.so
```

## Platform-Specific Setup

### Windows

1. Install ZWO camera driver from [ZWO Downloads](https://www.zwoastro.com/software/)
2. Connect camera via USB
3. Verify camera appears in Device Manager

### macOS

1. No driver installation required (uses libusb)
2. Remove Gatekeeper quarantine from SDK:
   ```bash
   xattr -d com.apple.quarantine zwo_capture/sdk/macos/libASICamera2.dylib
   ```
3. Install libusb if not present:
   ```bash
   brew install libusb
   ```

### Linux

1. Install libusb:
   ```bash
   # Ubuntu/Debian
   sudo apt install libusb-1.0-0

   # Fedora/RHEL
   sudo dnf install libusb1
   ```

2. Create udev rules for non-root access. Create `/etc/udev/rules.d/99-asi-cameras.rules`:
   ```
   # ZWO ASI Cameras
   SUBSYSTEM=="usb", ATTR{idVendor}=="03c3", MODE="0666"
   ```

3. Reload udev rules:
   ```bash
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

4. Reconnect the camera

## Usage

### Basic Example

```python
from zwo_capture import ZWOCamera, is_available, list_cameras

# Check if ZWO support is available
if not is_available():
    print("ZWO cameras not available")
    exit(1)

# List connected cameras
cameras = list_cameras()
print(f"Found {len(cameras)} camera(s)")
for cam in cameras:
    print(f"  {cam['id']}: {cam['name']}")

# Capture an image
with ZWOCamera(camera_id=0) as cam:
    cam.configure(
        exposure_ms=2000,   # 2 second exposure
        gain=100,           # Moderate gain
        binning=2,          # 2x2 binning
        image_type='RAW16'  # 16-bit output
    )

    image = cam.capture()  # Returns NumPy array
    info = cam.get_camera_info()

    print(f"Captured: {image.shape}, dtype={image.dtype}")
    print(f"Camera: {info['name']}, {info['pixel_size_um']}um pixels")
```

### Graceful Degradation

```python
from zwo_capture import ZWOCamera, is_available, ZWONotAvailable

def capture_for_plate_solving():
    """Capture with graceful fallback if ZWO unavailable."""
    if not is_available():
        return None, None

    try:
        with ZWOCamera() as cam:
            cam.configure(exposure_ms=2000, gain=100, binning=2)
            return cam.capture(), cam.get_camera_info()
    except ZWONotAvailable:
        return None, None
```

## Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `exposure_ms` | int | 2000 | Exposure time in milliseconds |
| `gain` | int | 100 | Camera gain (0-500 typical) |
| `binning` | int | 2 | Pixel binning (1, 2, 3, or 4) |
| `image_type` | str | 'RAW16' | Image format (RAW8, RAW16, RGB24, Y8) |
| `bandwidth` | int | 80 | USB bandwidth percentage (40-100) |
| `high_speed_mode` | bool | False | Enable high-speed transfer mode |

## API Reference

### Functions

- `is_available() -> bool`: Check if ZWO SDK is available (non-throwing)
- `list_cameras() -> List[dict]`: List connected cameras
- `get_camera_count() -> int`: Get number of connected cameras

### ZWOCamera Class

- `ZWOCamera(camera_id=0)`: Create camera instance
- `open()`: Open camera (or use context manager)
- `close()`: Close camera (idempotent)
- `configure(...)`: Set capture parameters
- `capture(timeout_ms=30000) -> np.ndarray`: Capture single frame
- `get_camera_info() -> dict`: Get camera properties
- `get_temperature() -> float`: Get sensor temperature (Celsius)

### Exceptions

- `ZWOError`: Base exception for all ZWO errors
- `ZWONotAvailable`: SDK not loaded or no cameras found
- `ZWOCameraError`: Camera operation failed
- `ZWOTimeoutError`: Capture timed out
- `ZWOConfigurationError`: Invalid configuration

## Troubleshooting

### "ZWO ASI SDK not found"

- Verify SDK binary is in the correct location for your platform
- Check that the binary matches your Python architecture (32-bit vs 64-bit)
- Try setting `ZWO_ASI_LIB` environment variable

### "No ZWO cameras connected"

- Verify camera is connected and powered
- On Linux, check udev rules are installed
- On Windows, verify driver is installed
- Try a different USB port (preferably USB 3.0)

### "macOS Gatekeeper blocked SDK loading"

Run: `xattr -d com.apple.quarantine /path/to/libASICamera2.dylib`

### "libusb not found"

Install libusb for your platform (see Platform-Specific Setup above)

## License

The ZWO ASI SDK is provided by ZWO for free redistribution with ZWO camera software.

This wrapper module is part of the TTS160 Alpaca Driver project.
