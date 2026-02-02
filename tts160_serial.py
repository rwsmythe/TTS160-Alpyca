# File: tts160_serial.py
"""
Enhanced serial communication with binary support for TTS160 telescope.

This module provides robust serial communication capabilities supporting both
traditional text-based LX200 commands and efficient binary data transfers.

Example:
    Basic usage with context manager:
    
    >>> with SerialManager(logger) as serial_mgr:
    ...     serial_mgr.connect('/dev/ttyUSB0')
    ...     ra = serial_mgr.send_command(':GR#', CommandType.STRING)
    ...     case_data = serial_mgr.get_case_data(2)
"""

import logging
import queue
import re
import struct
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple, Union

import serial

from tts160_types import (
    CommandType,
    BINARY_TYPE_SPECS,
    VARIABLE_TYPES,
    QUERY_GROUPS,
    BINARY_MAX_VARS_PER_COMMAND,
    SetCommand,
    SlewType,
    GuideDirection,
    BinaryError,
    CmdResponseType,
)
import math


# -----------------
# COMMAND PRIORITY
# -----------------
class CommandPriority(IntEnum):
    """Priority levels for serial commands.

    Lower values = higher priority. Commands are processed in priority order,
    allowing critical operations to preempt background tasks.
    """
    CRITICAL = 0   # Abort, emergency stop - never wait
    HIGH = 1       # Position queries during active slew
    NORMAL = 2     # Regular API operations
    LOW = 3        # Background cache updates


@dataclass(order=True)
class _PendingCommand:
    """Internal class for queued commands with priority ordering.

    The order=True makes instances sortable by priority (lowest first).
    """
    priority: int
    sequence: int  # Tie-breaker for same priority (FIFO within priority)
    command: str = field(compare=False)
    command_type: 'CommandType' = field(compare=False)
    result_event: threading.Event = field(compare=False)
    result: Any = field(default=None, compare=False)
    error: Optional[Exception] = field(default=None, compare=False)


# Thread-local storage for default priority context
_priority_context = threading.local()


class LowPriorityContext:
    """Context manager for executing commands with LOW priority.

    Use this in background threads (like cache updates) to ensure their
    commands don't block higher-priority operations.

    Example:
        with LowPriorityContext():
            # All serial commands in this block use LOW priority
            device.RightAscension  # Uses LOW priority
    """

    def __enter__(self):
        self._previous = getattr(_priority_context, 'default_priority', None)
        _priority_context.default_priority = CommandPriority.LOW
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._previous is None:
            if hasattr(_priority_context, 'default_priority'):
                del _priority_context.default_priority
        else:
            _priority_context.default_priority = self._previous
        return False


def get_default_priority() -> CommandPriority:
    """Get the current thread's default command priority.

    Returns:
        The default priority from thread-local context, or NORMAL if not set.
    """
    return getattr(_priority_context, 'default_priority', CommandPriority.NORMAL)


# Constants
DEFAULT_BAUDRATE = 9600
DEFAULT_TIMEOUT = 0.5
DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_TIMEOUT = 0.5
BUFFER_CLEAR_TIMEOUT = 0.1
MAX_BUFFER_CLEAR_ATTEMPTS = 100
BINARY_HEADER_READ_SIZE = 50
BINARY_HEADER_TIMEOUT = 0.2
# Legacy LX200 :MS# command still used for slew start
MS_COMMAND = ":MS#"


class TTS160SerialError(Exception):
    """Base exception for TTS160 serial communication errors."""
    pass


class ConnectionError(TTS160SerialError):
    """Serial connection related errors."""
    pass


class BinaryFormatError(TTS160SerialError):
    """Binary format parsing and validation errors."""
    pass


class ResponseError(TTS160SerialError):
    """Command response parsing errors."""
    pass


@dataclass(frozen=True)
class BinaryFormat:
    """Immutable binary data structure definition."""
    name: str
    format_string: str
    struct_format: str
    byte_size: int
    field_names: Optional[List[str]] = None
    
    def __post_init__(self) -> None:
        """Validate format consistency after initialization."""
        if self.field_names:
            expected_count = BinaryParser.count_format_values(self.format_string)
            if len(self.field_names) != expected_count:
                raise BinaryFormatError(
                    f"Field names count ({len(self.field_names)}) doesn't match "
                    f"format values ({expected_count})"
                )


class BinaryParser:
    """Utility class for parsing binary data formats with comprehensive validation."""
    
    # Type mapping: char -> (struct_char, size_bytes, description)
    TYPE_MAP = {
        'i': ('i', 4, 'int32'),    # 32-bit signed integer
        'f': ('f', 4, 'float32'),  # 32-bit float
        'm': ('m', 36, 'matrix'),  # 3x3 matrix of floats -> 9 x 4 bytes
        'h': ('h', 2, 'int16'),    # 16-bit signed integer
        'b': ('b', 1, 'int8'),     # 8-bit signed integer
        'I': ('I', 4, 'uint32'),   # 32-bit unsigned integer
        'H': ('H', 2, 'uint16'),   # 16-bit unsigned integer
        'B': ('B', 1, 'uint8')     # 8-bit unsigned integer
    }
    
    @classmethod
    def parse_format_string(cls, format_str: str) -> Tuple[str, int]:
        """
        Parse format string like '5i2f' into struct format and byte count.
        
        Args:
            format_str: Format specification (e.g., '5i2f')
            
        Returns:
            Tuple of (struct_format, total_bytes)
            
        Raises:
            BinaryFormatError: If format string is invalid
        """
        if not format_str:
            raise BinaryFormatError("Empty format string")
        
        # Parse format: optional digits followed by type character
        pattern = r'(\d*)([ifhbIHBm])'
        matches = re.findall(pattern, format_str)
        
        if not matches:
            raise BinaryFormatError(f"Invalid format string: {format_str}")
        
        struct_fmt = '<'  # Little endian
        total_bytes = 0
        
        for count_str, type_char in matches:
            count = int(count_str) if count_str else 1
            
            if type_char == 'm':
                # Matrix: count * 9 floats (each matrix is 9 floats)
                matrix_floats = count * 9
                struct_fmt += f"{matrix_floats}f"
                total_bytes += matrix_floats * 4
                continue
            else:
                if type_char not in cls.TYPE_MAP:
                    raise BinaryFormatError(f"Unknown type character: {type_char}")
            
            struct_char, type_size, _ = cls.TYPE_MAP[type_char]
            struct_fmt += f"{count}{struct_char}"
            total_bytes += count * type_size
        
        return struct_fmt, total_bytes
    
    @classmethod
    def count_format_values(cls, format_str: str) -> int:
        """
        Count the number of values a format string will produce.
        
        Args:
            format_str: Format specification
            
        Returns:
            Total number of values that will be unpacked
        """
        pattern = r'(\d*)([ifhbIHB])'
        matches = re.findall(pattern, format_str)
        return sum(int(count_str) if count_str else 1 for count_str, _ in matches)
    
    @classmethod
    def create_format(
        cls, 
        name: str, 
        format_string: str, 
        field_names: Optional[List[str]] = None
    ) -> BinaryFormat:
        """
        Create a validated BinaryFormat instance.
        
        Args:
            name: Format identifier
            format_string: Format specification (e.g., '5i2f')
            field_names: Optional field names for dictionary output
            
        Returns:
            Validated BinaryFormat instance
            
        Raises:
            BinaryFormatError: If format is invalid or field names don't match
        """
        try:
            struct_format, byte_size = cls.parse_format_string(format_string)
            return BinaryFormat(name, format_string, struct_format, byte_size, field_names)
        except Exception as ex:
            raise BinaryFormatError(f"Failed to create format '{name}': {ex}") from ex
    
    @staticmethod
    def unpack_data(binary_format: BinaryFormat, data: bytes) -> Union[List[Any], Dict[str, Any]]:
        """
        Unpack binary data according to format specification.
        
        Args:
            binary_format: Format definition
            data: Binary data to unpack
            
        Returns:
            List of values or dictionary with named fields
            
        Raises:
            BinaryFormatError: If data size doesn't match format
        """
        if len(data) != binary_format.byte_size:
            raise BinaryFormatError(
                f"Data size mismatch: expected {binary_format.byte_size} bytes, "
                f"got {len(data)} bytes"
            )
        
        try:
            values = list(struct.unpack(binary_format.struct_format, data))
        except struct.error as ex:
            raise BinaryFormatError(f"Failed to unpack binary data: {ex}") from ex
        
        # Return named dictionary if field names provided
        if binary_format.field_names:
            return dict(zip(binary_format.field_names, values))

        return values


class V357Protocol:
    """v357 binary variable protocol handler.

    Provides methods for building GET/SET commands and parsing binary responses
    for the v357 binary variable protocol.

    Protocol Overview:
        - GET: `:*!G <vars>#` returns `BINARY:<format>\n<data>`
        - SET: `:*!S <cmd>[,<cmd>];<data>#` returns binary response

    All coordinates are in radians. Multi-byte values are little-endian.
    """

    # Sidereal rate in degrees per second
    SIDEREAL_RATE_DEG_SEC = 15.0 / 3600.0  # ~0.00417 deg/sec

    @staticmethod
    def build_query(variables: List[str]) -> str:
        """Build a :*!G query command for multiple variables.

        Args:
            variables: List of variable IDs (e.g., ['T16', 'T17', 'C5'])

        Returns:
            Command string (e.g., ':*!G T16,T17,C5#')

        Raises:
            ValueError: If too many variables or invalid format
        """
        if not variables:
            raise ValueError("At least one variable must be specified")

        if len(variables) > BINARY_MAX_VARS_PER_COMMAND:
            raise ValueError(
                f"Too many variables ({len(variables)}). "
                f"Maximum is {BINARY_MAX_VARS_PER_COMMAND}."
            )

        # Validate variable format
        for var in variables:
            if not var or len(var) < 2:
                raise ValueError(f"Invalid variable format: {var}")
            category = var[0].upper()
            if category not in 'TCMALODK':
                raise ValueError(f"Invalid category in variable: {var}")
            try:
                var_id = int(var[1:])
                if var_id < 1 or var_id > 99:
                    raise ValueError(f"Variable ID out of range: {var}")
            except ValueError:
                raise ValueError(f"Invalid variable ID in: {var}")

        return f":*!G {','.join(variables)}#"

    @staticmethod
    def build_format_string(variables: List[str]) -> str:
        """Build expected format string for a list of variables.

        Args:
            variables: List of variable IDs

        Returns:
            Format string (e.g., 'ffB' for two floats and one uint8)
        """
        format_chars = []
        for var in variables:
            category = var[0].upper()
            var_id = int(var[1:])
            type_spec = VARIABLE_TYPES.get((category, var_id), 'B')
            format_chars.append(type_spec)
        return ''.join(format_chars)

    @staticmethod
    def parse_response(
        variables: List[str],
        format_spec: str,
        data: bytes
    ) -> Dict[str, Any]:
        """Parse binary response data into a dictionary.

        Args:
            variables: List of variable IDs that were queried
            format_spec: Format specification from response header
            data: Binary data bytes

        Returns:
            Dictionary mapping variable IDs to their values

        Raises:
            BinaryFormatError: If parsing fails
        """
        # Build struct format from format_spec
        struct_fmt = '<'  # Little endian
        expected_size = 0
        value_count = 0

        for char in format_spec:
            if char in BINARY_TYPE_SPECS:
                fmt, size = BINARY_TYPE_SPECS[char]
                struct_fmt += fmt
                expected_size += size
                # Quaternion produces 4 values
                value_count += 4 if char == 'q' else 1
            else:
                raise BinaryFormatError(f"Unknown type specifier: {char}")

        if len(data) != expected_size:
            raise BinaryFormatError(
                f"Data size mismatch: expected {expected_size} bytes, "
                f"got {len(data)} bytes"
            )

        try:
            values = list(struct.unpack(struct_fmt, data))
        except struct.error as ex:
            raise BinaryFormatError(f"Failed to unpack binary data: {ex}") from ex

        # Map values to variable names
        result = {}
        value_idx = 0

        for var in variables:
            category = var[0].upper()
            var_id = int(var[1:])
            type_spec = VARIABLE_TYPES.get((category, var_id), 'B')

            if type_spec == 'q':
                # Quaternion: extract 4 floats
                result[var] = tuple(values[value_idx:value_idx + 4])
                value_idx += 4
            else:
                result[var] = values[value_idx]
                value_idx += 1

        return result

    @staticmethod
    def build_set_command(cmd_id: int, data: bytes = b'') -> str:
        """Build a :*!S SET command.

        Args:
            cmd_id: SET command ID (from SetCommand enum)
            data: Binary parameter data

        Returns:
            Command string with embedded binary data
        """
        # Format: :*!S <cmd_hex>;<binary>#
        cmd_hex = f"{cmd_id:02X}"
        if data:
            # Encode binary data as part of command
            return f":*!S {cmd_hex};".encode('ascii') + data + b'#'
        else:
            return f":*!S {cmd_hex};#"

    @staticmethod
    def build_set_command_bytes(cmd_id: int, data: bytes = b'') -> bytes:
        """Build a :*!S SET command as bytes.

        Args:
            cmd_id: SET command ID (from SetCommand enum)
            data: Binary parameter data

        Returns:
            Command bytes with embedded binary data
        """
        cmd_hex = f"{cmd_id:02X}"
        return f":*!S {cmd_hex};".encode('ascii') + data + b'#'

    @staticmethod
    def pack_guide_command(direction: int, duration_ms: int) -> bytes:
        """Pack parameters for GUIDE (0x05) command.

        Args:
            direction: GuideDirection enum value (0-3)
            duration_ms: Duration in milliseconds (0-10000)

        Returns:
            Packed binary data
        """
        return struct.pack('<BH', direction, duration_ms)

    @staticmethod
    def pack_slew_target(ra_rad: float, dec_rad: float) -> bytes:
        """Pack parameters for SLEW_TO_TARGET with RA/Dec.

        Args:
            ra_rad: Right ascension in radians
            dec_rad: Declination in radians

        Returns:
            Packed binary data (slew_type + ra + dec)
        """
        return struct.pack('<Bff', SlewType.RA_DEC, ra_rad, dec_rad)

    @staticmethod
    def pack_slew_altaz(az_rad: float, alt_rad: float) -> bytes:
        """Pack parameters for SLEW_TO_TARGET with Alt/Az.

        Args:
            az_rad: Azimuth in radians
            alt_rad: Altitude in radians

        Returns:
            Packed binary data (slew_type + az + alt)
        """
        return struct.pack('<Bff', SlewType.ALT_AZ, az_rad, alt_rad)

    @staticmethod
    def pack_target_coords(ra_rad: float, dec_rad: float) -> bytes:
        """Pack parameters for SET_TARGET command.

        Args:
            ra_rad: Right ascension in radians
            dec_rad: Declination in radians

        Returns:
            Packed binary data
        """
        return struct.pack('<ff', ra_rad, dec_rad)

    @staticmethod
    def pack_move_axis(direction: int, speed_deg_sec: float) -> bytes:
        """Pack parameters for MOVE_AXIS command.

        Args:
            direction: GuideDirection enum value
            speed_deg_sec: Speed in degrees per second (0-3.5)

        Returns:
            Packed binary data
        """
        return struct.pack('<Bf', direction, speed_deg_sec)

    @staticmethod
    def pack_location(
        name: str,
        longitude_deg: float,
        latitude_deg: float,
        timezone_hours: float,
        min_horizon: int = 0
    ) -> bytes:
        """Pack 22-byte location payload for SET_LOCATION command.

        Args:
            name: Location name (max 10 chars, will be padded)
            longitude_deg: Longitude in degrees (-180 to 180, negative = West)
            latitude_deg: Latitude in degrees (-90 to 90, negative = South)
            timezone_hours: Timezone offset in hours from UTC
            min_horizon: Minimum horizon angle (0-89 degrees)

        Returns:
            22-byte packed location data
        """
        # Pad/truncate name to 10 chars
        name_bytes = name[:10].ljust(10).encode('ascii')

        # Timezone as half-hour offset (-24 to +28)
        tz_half_hours = int(timezone_hours * 2)

        # Longitude
        lon_sign = 1 if longitude_deg < 0 else 0
        lon_abs = abs(longitude_deg)
        lon_degs = int(lon_abs)
        lon_mins = int((lon_abs - lon_degs) * 60)
        lon_secs = int(((lon_abs - lon_degs) * 60 - lon_mins) * 60)

        # Latitude
        lat_sign = 1 if latitude_deg < 0 else 0
        lat_abs = abs(latitude_deg)
        lat_degs = int(lat_abs)
        lat_mins = int((lat_abs - lat_degs) * 60)
        lat_secs = int(((lat_abs - lat_degs) * 60 - lat_mins) * 60)

        return struct.pack(
            '<10sbBHBBBHBBB',
            name_bytes,
            tz_half_hours,
            lon_sign,
            lon_degs,
            lon_mins,
            lon_secs,
            lat_sign,
            lat_degs,
            lat_mins,
            lat_secs,
            min_horizon
        )

    @staticmethod
    def parse_set_response(data: bytes) -> List[Tuple[int, Any]]:
        """Parse SET command response.

        Args:
            data: Binary response data

        Returns:
            List of (response_type, value) tuples
        """
        if not data:
            return []

        results = []
        count = data[0]
        offset = 1

        for _ in range(count):
            if offset >= len(data):
                break

            resp_type = data[offset]
            offset += 1

            if resp_type == CmdResponseType.NONE:
                results.append((resp_type, None))
            elif resp_type == CmdResponseType.INT:
                if offset + 4 <= len(data):
                    value = struct.unpack_from('<i', data, offset)[0]
                    offset += 4
                    results.append((resp_type, value))
            elif resp_type == CmdResponseType.FLOAT:
                if offset + 4 <= len(data):
                    value = struct.unpack_from('<f', data, offset)[0]
                    offset += 4
                    results.append((resp_type, value))
            elif resp_type == CmdResponseType.ERROR:
                if offset + 4 <= len(data):
                    error_code = struct.unpack_from('<i', data, offset)[0]
                    offset += 4
                    results.append((resp_type, BinaryError(error_code)))

        return results

    # Coordinate conversion helpers

    @staticmethod
    def rad_to_hours(radians: float) -> float:
        """Convert radians to hours (for RA)."""
        hours = (radians * 12.0 / math.pi) % 24.0
        return hours

    @staticmethod
    def hours_to_rad(hours: float) -> float:
        """Convert hours to radians (for RA)."""
        return (hours % 24.0) * math.pi / 12.0

    @staticmethod
    def rad_to_deg(radians: float) -> float:
        """Convert radians to degrees."""
        return radians * 180.0 / math.pi

    @staticmethod
    def deg_to_rad(degrees: float) -> float:
        """Convert degrees to radians."""
        return degrees * math.pi / 180.0

    @staticmethod
    def normalize_ra_rad(ra_rad: float) -> float:
        """Normalize RA to [0, 2*pi) range."""
        two_pi = 2.0 * math.pi
        return ra_rad % two_pi

    @staticmethod
    def normalize_dec_rad(dec_rad: float) -> float:
        """Clamp declination to [-pi/2, pi/2] range."""
        half_pi = math.pi / 2.0
        return max(-half_pi, min(half_pi, dec_rad))

    @staticmethod
    def quaternion_to_matrix(quat: Tuple[float, float, float, float]) -> List[float]:
        """Convert quaternion (w, x, y, z) to 3x3 rotation matrix.

        Args:
            quat: Quaternion as (w, x, y, z) tuple

        Returns:
            List of 9 floats representing row-major 3x3 matrix
        """
        w, x, y, z = quat

        # Normalize quaternion
        norm = math.sqrt(w*w + x*x + y*y + z*z)
        if norm < 1e-10:
            # Return identity matrix for zero quaternion
            return [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]

        w, x, y, z = w/norm, x/norm, y/norm, z/norm

        # Compute rotation matrix elements
        xx, yy, zz = x*x, y*y, z*z
        xy, xz, yz = x*y, x*z, y*z
        wx, wy, wz = w*x, w*y, w*z

        return [
            1.0 - 2.0*(yy + zz), 2.0*(xy - wz), 2.0*(xz + wy),
            2.0*(xy + wz), 1.0 - 2.0*(xx + zz), 2.0*(yz - wx),
            2.0*(xz - wy), 2.0*(yz + wx), 1.0 - 2.0*(xx + yy)
        ]


class SerialManager:
    """
    Thread-safe serial communication manager for TTS160 with binary support.
    
    Provides robust serial communication with automatic retry logic, binary data
    parsing, and comprehensive error handling. Supports both traditional LX200
    text commands and efficient binary data transfers.
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize serial manager with optional logger.

        Args:
            logger: Optional logger instance. If None, creates module logger.
        """
        self._logger = logger or logging.getLogger(__name__)
        self._lock = threading.RLock()
        self._serial: Optional[serial.Serial] = None
        self._client_list = None
        self._connection_count = 0
        self._max_retries = DEFAULT_MAX_RETRIES
        self._retry_timeout = DEFAULT_RETRY_TIMEOUT
        self._flush_buffer_on_next_command = False

        # Priority queue for commands
        self._command_queue: queue.PriorityQueue[_PendingCommand] = queue.PriorityQueue()
        self._command_sequence = 0  # For FIFO ordering within same priority
        self._sequence_lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_stop_event = threading.Event()

        # Binary format registry (for custom formats if needed)
        self._binary_formats: Dict[str, BinaryFormat] = {}

        self._logger.info("TTS160 SerialManager initialized with v357 protocol support")
    
    def __enter__(self) -> 'SerialManager':
        """Context manager entry - connection must be established separately."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup all connections."""
        self.cleanup()
    
    # ----------------------
    # PRIORITY QUEUE METHODS
    # ----------------------

    def _start_worker(self) -> None:
        """Start the command processing worker thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._worker_stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._command_worker,
            name='SerialCommandWorker',
            daemon=True
        )
        self._worker_thread.start()
        self._logger.info("Serial command worker thread started")

    def _stop_worker(self) -> None:
        """Stop the command processing worker thread."""
        if not self._worker_thread or not self._worker_thread.is_alive():
            return

        self._worker_stop_event.set()
        # Put a sentinel to unblock the queue
        with self._sequence_lock:
            self._command_sequence += 1
            seq = self._command_sequence
        sentinel = _PendingCommand(
            priority=CommandPriority.CRITICAL,
            sequence=seq,
            command='',
            command_type=CommandType.BLIND,
            result_event=threading.Event()
        )
        self._command_queue.put(sentinel)

        self._worker_thread.join(timeout=2.0)
        if self._worker_thread.is_alive():
            self._logger.warning("Serial command worker did not stop gracefully")
        else:
            self._logger.info("Serial command worker thread stopped")
        self._worker_thread = None

    def _command_worker(self) -> None:
        """Worker thread that processes commands from the priority queue."""
        self._logger.debug("Command worker started")

        while not self._worker_stop_event.is_set():
            try:
                # Wait for a command with timeout to allow stop checks
                try:
                    pending = self._command_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                # Check for sentinel/stop
                if self._worker_stop_event.is_set() or not pending.command:
                    self._command_queue.task_done()
                    break

                # Execute the command
                try:
                    result = self._execute_command_with_retry(
                        pending.command,
                        pending.command_type
                    )
                    pending.result = result
                    pending.error = None
                except Exception as ex:
                    pending.result = None
                    pending.error = ex

                # Signal completion
                pending.result_event.set()
                self._command_queue.task_done()

            except Exception as ex:
                self._logger.error(f"Error in command worker: {ex}")

        self._logger.debug("Command worker stopped")

    def _get_next_sequence(self) -> int:
        """Get the next sequence number for command ordering."""
        with self._sequence_lock:
            self._command_sequence += 1
            return self._command_sequence

    def _execute_command_with_retry(
        self,
        command: str,
        command_type: CommandType
    ) -> Union[str, bool, List[Any], Dict[str, Any]]:
        """Execute command with retry logic (called by worker thread).

        Args:
            command: Command string
            command_type: Expected response type

        Returns:
            Parsed response

        Raises:
            ConnectionError: If all retries fail
        """
        if self._flush_buffer_on_next_command:
            self._logger.info("Failure detected, flushing receive buffer")
            self.clear_buffers()
            self._flush_buffer_on_next_command = False

        for attempt in range(self._max_retries + 1):
            try:
                result = self._send_command_once(command, command_type)
                if attempt > 0:
                    self._logger.info(f"Command {command} succeeded on attempt {attempt + 1}")
                return result

            except Exception as ex:
                self._flush_buffer_on_next_command = True

                if attempt == self._max_retries:
                    self._logger.error(
                        f"Command {command} failed after {self._max_retries + 1} attempts: {ex}"
                    )
                    raise ConnectionError(
                        f"Command failed after {self._max_retries + 1} attempts"
                    ) from ex
                else:
                    self._logger.warning(
                        f"Command {command} failed (attempt {attempt + 1}), retrying: {ex}"
                    )
                    time.sleep(self._retry_timeout)

        raise ConnectionError("Unexpected retry loop exit")

    def register_binary_format(
        self, 
        name: str, 
        format_string: str, 
        field_names: Optional[List[str]] = None
    ) -> None:
        """
        Register a binary format for parsing responses.
        
        Args:
            name: Format identifier (e.g., 'case2')
            format_string: Format specification (e.g., '5i2f')
            field_names: Optional field names for dictionary output
            
        Raises:
            ValueError: If parameters are invalid
            BinaryFormatError: If format is invalid
        """
        if not name or not isinstance(name, str):
            raise ValueError("Format name must be a non-empty string")
        
        if not format_string or not isinstance(format_string, str):
            raise ValueError("Format string must be a non-empty string")
        
        binary_format = BinaryParser.create_format(name, format_string, field_names)
        
        with self._lock:
            if name in self._binary_formats:
                self._logger.warning(f"Overwriting existing binary format: {name}")
            self._binary_formats[name] = binary_format
        
        self._logger.info(
            f"Registered binary format '{name}': {format_string} "
            f"({binary_format.byte_size} bytes)"
        )
    
    def connect(self, port: str, baudrate: int = DEFAULT_BAUDRATE) -> None:
        """
        Establish serial connection with reference counting.
        
        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0' or 'COM3')
            baudrate: Communication baud rate
            
        Raises:
            ValueError: If parameters are invalid
            ConnectionError: If connection fails
        """
        if not port or not isinstance(port, str):
            raise ValueError("Port must be a non-empty string")
        
        if not isinstance(baudrate, int) or baudrate <= 0:
            raise ValueError("Baudrate must be a positive integer")
        
        with self._lock:
            if self._connection_count == 0:
                self._establish_connection(port, baudrate)
                self._start_worker()  # Start command processing thread

            self._connection_count += 1
            self._logger.info(f"Serial connection count: {self._connection_count}")

    def disconnect(self) -> None:
        """Decrement connection count and close when reaching zero."""
        with self._lock:
            if self._connection_count > 0:
                self._connection_count -= 1
                self._logger.info(f"Serial connection count: {self._connection_count}")

                if self._connection_count == 0:
                    self._stop_worker()  # Stop command processing thread
                    self._close_connection()
    
    def add_client(self, client: dict) -> None:
        """
        Add a client to the connection tracking.
        
        Args:
            client: Dictionary containing client_id as key and remote_addr as value
            
        Raises:
            ValueError: If client is invalid
        """
        if not isinstance(client, dict) or not client:
            raise ValueError("Client must be a non-empty dictionary")
        
        client_id = list(client.keys())[0]
        remote_addr = client[client_id]
        
        with self._lock:
            if self._client_list is None:
                self._client_list = []
            if client not in self._client_list:
                self._client_list.append(client)
            self._connection_count = len(self._client_list)
            self._logger.info(f"Added client {client_id} ({remote_addr}). Total clients: {len(self._client_list)}")

    def remove_client(self, client: dict) -> None:
        """
        Remove a client from the connection tracking.
        
        Args:
            client: Dictionary containing client_id as key and remote_addr as value
            
        Raises:
            ValueError: If client is invalid or not found
        """
        if not isinstance(client, dict) or not client:
            raise ValueError("Client must be a non-empty dictionary")
        
        client_id = list(client.keys())[0]
        remote_addr = client[client_id]
        
        with self._lock:
            if self._client_list and client in self._client_list:
                self._client_list.remove(client)
                self._logger.info(f"Removed client {client_id} ({remote_addr}). Remaining clients: {len(self._client_list)}")
            else:
                raise ValueError(f"Client {client_id} not found in client list")
            self._connection_count = len(self._client_list)

    def check_client(self, client: dict) -> bool:
        """
        Check if a client is currently connected.
        
        Args:
            client: Dictionary containing client_id as key and remote_addr as value
            
        Returns:
            True if client is connected, False otherwise
            
        Raises:
            ValueError: If client is invalid
        """
        if not isinstance(client, dict) or not client:
            raise ValueError("Client must be a non-empty dictionary")
        
        with self._lock:
            return self._client_list is not None and client in self._client_list

    def cleanup(self) -> None:
        """Force immediate connection cleanup regardless of reference count."""
        self._stop_worker()  # Stop worker first (outside lock to avoid deadlock)
        with self._lock:
            self._connection_count = 0
            self._close_connection()
            self._logger.info("Serial connection forcibly cleaned up")
    
    @property
    def is_connected(self) -> bool:
        """Check if serial connection is active."""
        with self._lock:
            return self._serial is not None and self._serial.is_open
    
    @property
    def connection_count(self) -> int:
        """Get current connection reference count."""
        with self._lock:
            return self._connection_count
    
    def send_command(
        self,
        command: str,
        command_type: CommandType = CommandType.AUTO,
        priority: Optional[CommandPriority] = None,
        timeout: float = 30.0
    ) -> Union[str, bool, List[Any], Dict[str, Any]]:
        """
        Send command with priority queuing and automatic retry.

        Commands are queued and processed by a worker thread in priority order.
        Higher priority commands (lower enum value) are processed first.

        Args:
            command: Command string (e.g., ':GR#' or ':*!2#')
            command_type: Expected response type
            priority: Command priority (CRITICAL, HIGH, NORMAL, LOW).
                     If None, uses thread-local default (set by LowPriorityContext).
            timeout: Maximum time to wait for result in seconds

        Returns:
            Parsed response based on command type

        Raises:
            ValueError: If command is invalid
            ConnectionError: If not connected or communication fails
            ResponseError: If response parsing fails
            TimeoutError: If command times out waiting for execution
        """
        if not command or not isinstance(command, str):
            raise ValueError("Command must be a non-empty string")

        if not command.startswith(':') or not command.endswith('#'):
            raise ValueError("Command must start with ':' and end with '#'")

        # Resolve priority from thread-local context if not explicitly set
        effective_priority = priority if priority is not None else get_default_priority()

        # Check if worker is running; fall back to direct execution if not
        if not self._worker_thread or not self._worker_thread.is_alive():
            self._logger.debug(f"Worker not running, executing {command} directly")
            return self._execute_command_with_retry(command, command_type)

        # Create pending command
        pending = _PendingCommand(
            priority=effective_priority,
            sequence=self._get_next_sequence(),
            command=command,
            command_type=command_type,
            result_event=threading.Event()
        )

        # Queue the command
        self._command_queue.put(pending)
        self._logger.debug(
            f"Queued command {command} with priority {effective_priority.name}"
        )

        # Wait for result
        if not pending.result_event.wait(timeout=timeout):
            raise TimeoutError(
                f"Command {command} timed out after {timeout}s waiting for execution"
            )

        # Check for error
        if pending.error:
            raise pending.error

        return pending.result
    
    # ----------------------
    # V357 PROTOCOL METHODS
    # ----------------------

    def query_variables(
        self,
        variables: List[str],
        priority: Optional[CommandPriority] = None
    ) -> Dict[str, Any]:
        """Query multiple v357 variables in a single command.

        This is the primary method for reading mount state using the v357
        binary variable protocol. Variables are specified as category+ID
        strings (e.g., 'T16' for RA, 'T17' for Dec).

        Args:
            variables: List of variable IDs (e.g., ['T16', 'T17', 'C5'])
            priority: Command priority (defaults to thread-local context)

        Returns:
            Dictionary mapping variable IDs to their values

        Raises:
            ValueError: If variables list is invalid
            ConnectionError: If communication fails
            ResponseError: If response parsing fails

        Example:
            >>> result = serial_mgr.query_variables(['T16', 'T17', 'X1', 'X2'])
            >>> ra_rad = result['T16']  # RA in radians
            >>> dec_rad = result['T17']  # Dec in radians
        """
        command = V357Protocol.build_query(variables)
        self._logger.debug(f"Querying v357 variables: {variables}")

        result = self.send_command(command, CommandType.AUTO, priority=priority)

        if isinstance(result, str):
            raise ResponseError(
                f"Expected binary response for v357 query, got text: {result}"
            )

        # Result should be a list from _parse_inline_binary_response
        if isinstance(result, list):
            # Map list values to variable names
            return self._map_query_result(variables, result)

        # Already a dictionary
        return result

    def query_variable_group(
        self,
        group_name: str,
        priority: Optional[CommandPriority] = None
    ) -> Dict[str, Any]:
        """Query a predefined group of variables.

        Args:
            group_name: Name of predefined group (e.g., 'position', 'status')
            priority: Command priority

        Returns:
            Dictionary mapping variable IDs to their values

        Raises:
            ValueError: If group name is not recognized
        """
        if group_name not in QUERY_GROUPS:
            raise ValueError(
                f"Unknown query group: {group_name}. "
                f"Available groups: {list(QUERY_GROUPS.keys())}"
            )

        variables = QUERY_GROUPS[group_name]
        return self.query_variables(variables, priority=priority)

    def execute_set_command(
        self,
        cmd_id: int,
        data: bytes = b'',
        priority: Optional[CommandPriority] = None
    ) -> List[Tuple[int, Any]]:
        """Execute a v357 SET command.

        Args:
            cmd_id: SET command ID (from SetCommand enum)
            data: Binary parameter data
            priority: Command priority

        Returns:
            List of (response_type, value) tuples

        Raises:
            ConnectionError: If communication fails
            ResponseError: If response parsing fails

        Example:
            >>> # Enable tracking
            >>> result = serial_mgr.execute_set_command(SetCommand.SET_TRACKING, b'\\x01')
        """
        command_bytes = V357Protocol.build_set_command_bytes(cmd_id, data)
        self._logger.debug(f"Executing v357 SET command: 0x{cmd_id:02X}")

        # Send raw bytes command
        result = self._send_set_command_bytes(command_bytes, priority)

        return V357Protocol.parse_set_response(result)

    def _send_set_command_bytes(
        self,
        command_bytes: bytes,
        priority: Optional[CommandPriority] = None  # Reserved for future queue integration
    ) -> bytes:
        """Send raw bytes command and return raw response.

        This is used for SET commands that have embedded binary data.
        Note: Priority parameter is reserved for future queue integration.
        """
        _ = priority  # Reserved for future use

        # For SET commands, we need direct serial access
        # since we're sending binary data
        with self._lock:
            if not self.is_connected:
                raise ConnectionError("Serial port not connected")

            try:
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()

                self._logger.debug(f"Sending SET command bytes: {command_bytes.hex()}")
                self._serial.write(command_bytes)
                self._serial.flush()

                # Read response - SET commands return binary response
                response = self._serial.read(50)  # Max expected response size
                self._logger.debug(f"SET command response: {response.hex()}")
                return response

            except (serial.SerialException, UnicodeDecodeError) as ex:
                raise ConnectionError(f"Serial communication error: {ex}") from ex

    def _map_query_result(
        self,
        variables: List[str],
        values: List[Any]
    ) -> Dict[str, Any]:
        """Map query result list to variable dictionary.

        Handles special cases like quaternions that expand to multiple values.
        """
        result = {}
        value_idx = 0

        for var in variables:
            category = var[0].upper()
            var_id = int(var[1:])
            type_spec = VARIABLE_TYPES.get((category, var_id), 'B')

            if type_spec == 'q':
                # Quaternion: extract 4 floats
                if value_idx + 4 <= len(values):
                    result[var] = tuple(values[value_idx:value_idx + 4])
                    value_idx += 4
                else:
                    self._logger.warning(f"Insufficient values for quaternion {var}")
                    result[var] = (0.0, 0.0, 0.0, 1.0)  # Identity quaternion
            else:
                if value_idx < len(values):
                    result[var] = values[value_idx]
                    value_idx += 1
                else:
                    self._logger.warning(f"Missing value for variable {var}")
                    result[var] = 0

        return result

    # Convenience methods for common v357 operations

    def get_position(
        self,
        priority: Optional[CommandPriority] = None
    ) -> Tuple[float, float, float, float]:
        """Get current position (RA, Dec, Alt, Az) in radians.

        Returns:
            Tuple of (ra_rad, dec_rad, alt_rad, az_rad)
        """
        result = self.query_variables(['T16', 'T17', 'X1', 'X2'], priority)
        return (
            result.get('T16', 0.0),
            result.get('T17', 0.0),
            result.get('X1', 0.0),
            result.get('X2', 0.0)
        )

    def get_status(
        self,
        priority: Optional[CommandPriority] = None
    ) -> Dict[str, Any]:
        """Get current mount status flags.

        Returns:
            Dictionary with 'tracking', 'slewing', 'goto_active', 'parked' keys
        """
        result = self.query_variables(['T4', 'L5', 'L6', 'C5'], priority)
        return {
            'tracking': bool(result.get('T4', 0)),
            'slewing': bool(result.get('L5', 0)),
            'goto_active': bool(result.get('L6', 0)),
            'parked': bool(result.get('C5', 0))
        }

    def halt(self, priority: CommandPriority = CommandPriority.CRITICAL) -> bool:
        """Emergency stop - halt all motion.

        Returns:
            True if successful
        """
        result = self.execute_set_command(SetCommand.HALT_ALL, b'', priority)
        return len(result) > 0 and result[0][1] == 0

    def set_tracking(
        self,
        enabled: bool,
        priority: Optional[CommandPriority] = None
    ) -> bool:
        """Enable or disable tracking.

        Args:
            enabled: True to enable, False to disable

        Returns:
            True if successful
        """
        data = struct.pack('<B', 1 if enabled else 0)
        result = self.execute_set_command(SetCommand.SET_TRACKING, data, priority)
        return len(result) > 0 and result[0][1] == 0

    def pulse_guide(
        self,
        direction: int,
        duration_ms: int,
        priority: Optional[CommandPriority] = None
    ) -> bool:
        """Send pulse guide command.

        Args:
            direction: GuideDirection enum value (0=N, 1=S, 2=E, 3=W)
            duration_ms: Duration in milliseconds (0-10000)

        Returns:
            True if successful
        """
        data = V357Protocol.pack_guide_command(direction, duration_ms)
        result = self.execute_set_command(SetCommand.GUIDE, data, priority)
        return len(result) > 0 and result[0][1] == 0

    def slew_to_coordinates(
        self,
        ra_rad: float,
        dec_rad: float,
        priority: Optional[CommandPriority] = None
    ) -> bool:
        """Slew to RA/Dec coordinates.

        Args:
            ra_rad: Right ascension in radians
            dec_rad: Declination in radians

        Returns:
            True if slew started successfully
        """
        data = V357Protocol.pack_slew_target(ra_rad, dec_rad)
        result = self.execute_set_command(SetCommand.SLEW_TO_TARGET, data, priority)
        return len(result) > 0 and result[0][1] == 0

    def set_target(
        self,
        ra_rad: float,
        dec_rad: float,
        priority: Optional[CommandPriority] = None
    ) -> bool:
        """Set target coordinates without slewing.

        Args:
            ra_rad: Right ascension in radians
            dec_rad: Declination in radians

        Returns:
            True if successful
        """
        data = V357Protocol.pack_target_coords(ra_rad, dec_rad)
        result = self.execute_set_command(SetCommand.SET_TARGET, data, priority)
        return len(result) > 0 and result[0][1] == 0

    def park(self, priority: Optional[CommandPriority] = None) -> bool:
        """Park the mount.

        Returns:
            True if park command accepted
        """
        data = struct.pack('<B', 0)  # 0 = park
        result = self.execute_set_command(SetCommand.PARK_UNPARK, data, priority)
        return len(result) > 0 and result[0][1] == 0

    def unpark(self, priority: Optional[CommandPriority] = None) -> bool:
        """Unpark the mount.

        Returns:
            True if unpark command accepted
        """
        data = struct.pack('<B', 1)  # 1 = unpark
        result = self.execute_set_command(SetCommand.PARK_UNPARK, data, priority)
        return len(result) > 0 and result[0][1] == 0

    def clear_buffers(self) -> None:
        """Clear serial input/output buffers and purge queued responses."""
        with self._lock:
            if not self.is_connected:
                self._logger.warning("Cannot clear buffers: not connected")
                return
            
            try:
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                self._logger.debug("Serial buffers reset")

                # Clear any lingering data
                original_timeout = self._serial.timeout
                self._serial.timeout = BUFFER_CLEAR_TIMEOUT
                
                cleared_bytes = 0
                for _ in range(MAX_BUFFER_CLEAR_ATTEMPTS):
                    data = self._serial.read(1)
                    if not data:
                        break
                    cleared_bytes += 1
                
                self._serial.timeout = original_timeout
                
                if cleared_bytes > 0:
                    self._logger.info(f"Cleared {cleared_bytes} bytes from response queue")
                else:
                    self._logger.debug("No queued responses to clear")
                
            except Exception as ex:
                self._logger.warning(f"Error clearing buffers: {ex}")
    
    def _establish_connection(self, port: str, baudrate: int) -> None:
        """Establish the physical serial connection."""
        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=DEFAULT_TIMEOUT
            )
            
            if not self._serial.is_open:
                self._serial.open()
            
            self._logger.info(f"Serial connection opened: {port} @ {baudrate} baud")
            
        except Exception as ex:
            self._logger.error(f"Failed to open serial connection on {port}: {ex}")
            raise ConnectionError(f"Serial connection failed: {ex}") from ex
    
    def _close_connection(self) -> None:
        """Close the physical serial connection."""
        if self._serial:
            try:
                if self._serial.is_open:
                    self._serial.close()
                    self._logger.info("Serial connection closed")
            except Exception as ex:
                self._logger.warning(f"Error closing serial connection: {ex}")
            finally:
                self._serial = None
    
    def _send_command_once(
        self, 
        command: str, 
        command_type: CommandType
    ) -> Union[str, bool, List[Any], Dict[str, Any]]:
        """Send single command attempt with response parsing."""
        with self._lock:
            if not self.is_connected:
                raise ConnectionError("Serial port not connected")
            
            try:
                # Clear buffers and send command
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                
                self._logger.debug(f"Sending command: {command}")
                self._serial.write(command.encode('ascii'))
                self._serial.flush()
                
                # Parse response based on command type
                return self._parse_response(command, command_type)
                
            except (serial.SerialException, UnicodeDecodeError) as ex:
                raise ConnectionError(f"Serial communication error: {ex}") from ex
    
    def _parse_response(
        self, 
        command: str, 
        command_type: CommandType
    ) -> Union[str, bool, List[Any], Dict[str, Any]]:
        """Parse command response based on expected type."""
        if command_type == CommandType.BLIND:
            time.sleep(0.01)  # Small delay for command processing
            return ""
        
        elif command_type == CommandType.BOOL:
            return self._parse_boolean_response(command)
        
        elif command_type == CommandType.STRING:
            return self._parse_string_response()
        
        elif command_type == CommandType.AUTO:
            return self._parse_auto_response()
        
        else:
            raise ResponseError(f"Invalid command type: {command_type}")
    
    def _parse_boolean_response(self, command: str) -> bool:
        """Parse single character boolean response."""
        response = self._serial.read(1).decode('ascii')
        if not response:
            raise ResponseError("No boolean response received")
        
        result = response == '1'
        self._logger.debug(f"Boolean response: {response} -> {result}")
        
        # Handle special case for :MS# command
        if result and command == MS_COMMAND:
            try:
                extra = self._serial.read_until(b'#').decode('ascii')
                self._logger.debug(f"Cleared extra {MS_COMMAND} response: {extra}")
            except Exception as ex:
                self._logger.warning(f"Failed to clear extra {MS_COMMAND} response: {ex}")
        
        return result
    
    def _parse_string_response(self) -> str:
        """Parse string response terminated with '#'."""
        response = self._serial.read_until(b'#').decode('ascii')
        if not response:
            raise ResponseError("No string response received")
        
        self._logger.debug(f"String response: {response}")
        return response
    
    def _read_until_delimiter(self) -> bytes:
        """Read until newline (binary) or # (text)."""
        buffer = b''
        while True:
            byte = self._serial.read(1)
            if not byte:  # Timeout
                break
            buffer += byte
            if byte in (b'\n', b'#'):
                break
        return buffer

    def _parse_auto_response(self) -> Union[str, List[Any], Dict[str, Any]]:
        """Auto-detect and parse text vs binary responses."""
        original_timeout = self._serial.timeout
        header_chunk = b''
        
        try:
            # Read initial chunk for analysis
            self._serial.timeout = BINARY_HEADER_TIMEOUT
            #header_chunk = self._serial.read(BINARY_HEADER_READ_SIZE)
            header_chunk = self._read_until_delimiter()

            if not header_chunk:
                raise ResponseError("No response received")
            
            self._serial.timeout = original_timeout
            
            # Attempt to decode as text header
            try:
                text_header = header_chunk.decode('ascii')

                if text_header.startswith('BINARY:'):
                    return self._parse_inline_binary_response(text_header)

                # Regular string response - read until #
                remaining = self._serial.read_until(b'#')
                full_response = (header_chunk + remaining).decode('ascii')
                self._logger.debug(f"Text response: {full_response}")
                return full_response
                
            except UnicodeDecodeError:
                # Binary data without text header - fallback to string with error handling
                remaining = self._serial.read_until(b'#')
                full_response = (header_chunk + remaining).decode('ascii', errors='replace')
                self._logger.warning(f"Non-ASCII response, decoded with replacement: {full_response}")
                return full_response
            
        except Exception as ex:
            # Graceful fallback on any parsing error
            self._logger.warning(f"Auto-response parsing failed, attempting string fallback: {ex}")
            return self._attempt_string_fallback(header_chunk)
        
        finally:
            # Ensure timeout is always restored
            self._serial.timeout = original_timeout
    
    def _parse_inline_binary_response(self, text_header: str) -> List[Any]:
        """Parse binary response with inline format specification."""
        if '\n' not in text_header:
            raise ResponseError("Invalid binary header: missing newline")
        
        format_spec = text_header.split('\n')[0][7:]  # Remove 'BINARY:' prefix
        self._logger.debug(f"Parsing inline binary format: {format_spec}")
        
        try:
            struct_format, byte_size = BinaryParser.parse_format_string(format_spec)
            binary_data = self._serial.read(byte_size)
            
            if len(binary_data) != byte_size:
                raise ResponseError(
                    f"Binary read failed: expected {byte_size} bytes, got {len(binary_data)}"
                )
            
            result = list(struct.unpack(struct_format, binary_data))
            self._logger.debug(f"Parsed inline binary data: {len(result)} values")
            return result
            
        except Exception as ex:
            raise ResponseError(f"Failed to parse inline binary ({format_spec}): {ex}") from ex

    def _attempt_string_fallback(self, initial_data: bytes) -> str:
        """Attempt to recover by reading as string response."""
        try:
            remaining = self._serial.read_until(b'#')
            full_response = (initial_data + remaining).decode('ascii', errors='replace')
            self._logger.debug(f"String fallback successful: {full_response}")
            return full_response
        except Exception:
            self._logger.error("Complete response parsing failure")
            return ""