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
import re
import struct
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import serial

from tts160_types import CommandType


# Constants
DEFAULT_BAUDRATE = 9600
DEFAULT_TIMEOUT = 0.5
DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_TIMEOUT = 0.5
BUFFER_CLEAR_TIMEOUT = 0.1
MAX_BUFFER_CLEAR_ATTEMPTS = 100
BINARY_HEADER_READ_SIZE = 50
BINARY_HEADER_TIMEOUT = 0.2
MIN_CASE_NUMBER = 0
MAX_CASE_NUMBER = 9
BINARY_COMMAND_PREFIX = ":*!"
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
        
        # Binary format registry
        self._binary_formats: Dict[str, BinaryFormat] = {}
        self._setup_default_formats()
        
        self._logger.info("TTS160 SerialManager initialized with binary support")
    
    def __enter__(self) -> 'SerialManager':
        """Context manager entry - connection must be established separately."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup all connections."""
        self.cleanup()
    
    def _setup_default_formats(self) -> None:
        """Setup predefined binary formats for standard cases."""
        default_formats = {
            '0': (
                '13i4f',
                 ['h_ticks', 'e_ticks', 'tracking',
                  'h_motor_on', 'e_motor_on', 'h_motor_moving','e_motor_moving',
                  'h_dir', 'e_dir', 'align_status', 'error', 'slewing','collision',
                  'ra','dec','az','alt']
            ),
            '1': (
                '3i9f', 
                ['tracking_mode', 'tracking_rate', 'custom_track_rate',
                 'align_time', 'lx200_object_ra', 'lx200_object_dec',
                 'last_goto_ra', 'last_goto_dec', 'custom_rate_ra', 'custom_rate_dec',
                 'current_obj_ra', 'current_obj_de']
            ), 
            '2': (
                '5i2f', 
                ['goto_speed_h', 'goto_speed_e', 'guide_speed_h', 
                 'guide_speed_e', 'park_flag', 'park_az', 'park_alt']
            ),
            '3': (
                '6i3f',
                 ['month', 'day','year','hrs','mins','secs',
                  'longitude','latitude','timezone'] 
            ),
            '4': (
                '7i', 
                ['ticks_per_round_h', 'ticks_per_round_e', 'guide_corr_h', 'guide_corr_e', 
                 'cable_twist_alarm', 'south_angle', 'az_counter']
            ),
            '5': ('9f', None),
            '6': ('9f', None),
            '7': (
                '13i4f',
                ['clock_freq', 'h_jerk', 'e_jerk', 'h_speed_active','e_speed_active',
                 'h_posit_active', 'e_posit_active', 'h_den', 'h_num_final', 'h_num_curr',
                 'e_den', 'e_num_final', 'e_num_curr',
                 'h_pos_init', 'h_pos_final', 'e_pos_init', 'e_pos_final']
            ),
            '8': (
                '5i2f',
                ['rotator_on', 'rotator_ticks', 'field_rot_ticks',
                 'field_rot_ticks_range', 'field_rot_direction',
                 'field_rot_full_angle', 'initial_field_rot']
            )
        }
        
        for name, (format_string, field_names) in default_formats.items():
            try:
                self.register_binary_format(name, format_string, field_names)
                self._logger.debug(f"Registered default format: {name}")
            except BinaryFormatError as ex:
                self._logger.warning(f"Failed to register default format {name}: {ex}")
    
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
            
            self._connection_count += 1
            self._logger.info(f"Serial connection count: {self._connection_count}")
    
    def disconnect(self) -> None:
        """Decrement connection count and close when reaching zero."""
        with self._lock:
            if self._connection_count > 0:
                self._connection_count -= 1
                self._logger.info(f"Serial connection count: {self._connection_count}")
                
                if self._connection_count == 0:
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
        command_type: CommandType = CommandType.AUTO
    ) -> Union[str, bool, List[Any], Dict[str, Any]]:
        """
        Send command with automatic retry and response parsing.
        
        Args:
            command: Command string (e.g., ':GR#' or ':*!2#')
            command_type: Expected response type
            
        Returns:
            Parsed response based on command type
            
        Raises:
            ValueError: If command is invalid
            ConnectionError: If not connected or communication fails
            ResponseError: If response parsing fails
        """
        if not command or not isinstance(command, str):
            raise ValueError("Command must be a non-empty string")
        
        if not command.startswith(':') or not command.endswith('#'):
            raise ValueError("Command must start with ':' and end with '#'")
        
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
        
        # Should never reach here
        raise ConnectionError("Unexpected retry loop exit")
    
    def get_case_data(self, case_number: int) -> Union[List[Any], Dict[str, Any]]:
        """
        Retrieve binary case data using :*!n# command format.
        
        Args:
            case_number: Case number (0-9)
            
        Returns:
            Parsed binary data as list or named dictionary
            
        Raises:
            ValueError: If case number is invalid
            ConnectionError: If communication fails
            ResponseError: If response parsing fails
        """
        if not MIN_CASE_NUMBER <= case_number <= MAX_CASE_NUMBER:
            raise ValueError(
                f"Invalid case number: {case_number}. "
                f"Must be between {MIN_CASE_NUMBER} and {MAX_CASE_NUMBER}."
            )
        
        command = f"{BINARY_COMMAND_PREFIX}{case_number}#"
        self._logger.debug(f"Requesting case {case_number} binary data")
        
        result = self.send_command(command, CommandType.AUTO)
        
        if isinstance(result, str):
            raise ResponseError(
                f"Expected binary response for case {case_number}, got text: {result}"
            )
        
        return result
    
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
                
                elif text_header.startswith('CASE:'):
                    return self._parse_case_binary_response(text_header)
                
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
    
    def _parse_case_binary_response(self, text_header: str) -> Union[List[Any], Dict[str, Any]]:
        """Parse binary response using predefined case format."""
        if '\n' not in text_header:
            raise ResponseError("Invalid case header: missing newline")
        
        case_name = text_header.split('\n')[0][5:].lower()  # Remove 'CASE:' prefix
        self._logger.debug(f"Parsing case binary format: {case_name}")
        
        with self._lock:
            if case_name not in self._binary_formats:
                raise ResponseError(f"Unknown binary case: {case_name}")
            
            binary_format = self._binary_formats[case_name]
        
        try:
            binary_data = self._serial.read(binary_format.byte_size)
            
            if len(binary_data) != binary_format.byte_size:
                raise ResponseError(
                    f"Binary read failed: expected {binary_format.byte_size} bytes, "
                    f"got {len(binary_data)}"
                )
            
            result = BinaryParser.unpack_data(binary_format, binary_data)
            value_count = len(result) if isinstance(result, list) else len(result.keys())
            self._logger.debug(f"Parsed case {case_name} binary data: {value_count} values")
            return result
            
        except Exception as ex:
            raise ResponseError(f"Failed to parse case binary ({case_name}): {ex}") from ex
    
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