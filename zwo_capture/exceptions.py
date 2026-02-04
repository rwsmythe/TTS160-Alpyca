"""
ZWO Camera Exception Hierarchy

Custom exceptions for ZWO camera operations, providing clear error
categorization for graceful degradation and error handling.
"""


class ZWOError(Exception):
    """Base exception for all ZWO camera errors.

    All ZWO-related exceptions inherit from this class, allowing
    callers to catch all ZWO errors with a single except clause.
    """
    pass


class ZWONotAvailable(ZWOError):
    """Raised when ZWO SDK cannot be loaded or no cameras are found.

    This exception indicates that ZWO camera support is not available
    on the current system. Possible causes:
    - SDK library not found (not bundled or not in system path)
    - SDK library failed to load (missing dependencies, wrong architecture)
    - No ZWO cameras connected to the system

    Callers should catch this exception to gracefully fall back to
    alternative camera sources.
    """
    pass


class ZWOCameraError(ZWOError):
    """Raised when camera operations fail.

    This exception indicates that a camera operation failed after
    the SDK was successfully loaded. Possible causes:
    - Camera disconnected during operation
    - Camera in use by another application
    - Hardware communication error
    - Invalid camera ID
    """
    pass


class ZWOTimeoutError(ZWOCameraError):
    """Raised when capture times out.

    This exception indicates that an exposure did not complete
    within the specified timeout period. Possible causes:
    - Exposure time longer than timeout
    - Camera stalled or unresponsive
    - USB communication issues
    """
    pass


class ZWOConfigurationError(ZWOCameraError):
    """Raised when invalid configuration is requested.

    This exception indicates that the requested camera settings
    are invalid or unsupported. Possible causes:
    - Exposure time out of range
    - Gain value not supported by camera
    - Binning mode not available
    - Image type not supported
    - ROI dimensions invalid
    """
    pass
