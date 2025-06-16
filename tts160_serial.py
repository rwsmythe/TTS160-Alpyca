# File: tts160_serial.py  
"""Serial communication management for TTS160."""

import threading
import time
from typing import Optional, Union
import serial
from logging import Logger
from tts160_types import CommandType


class SerialManager:
    """Manages serial connection for TTS160 device with retry logic and robust error handling."""
    
    # Class constants
    BUFFER_CLEAR_ATTEMPTS = 100
    BUFFER_CLEAR_TIMEOUT = 0.1
    BLIND_COMMAND_DELAY = 0.01
    DEFAULT_MAX_RETRIES = 5
    DEFAULT_RETRY_TIMEOUT = 0.5
    
    def __init__(self, logger: Logger, max_retries: int = DEFAULT_MAX_RETRIES, 
                 retry_timeout: float = DEFAULT_RETRY_TIMEOUT):
        """Initialize the SerialManager.
        
        Args:
            logger: Logger instance for status and error reporting
            max_retries: Maximum number of command retry attempts
            retry_timeout: Delay between retry attempts in seconds
        """
        self._logger = logger
        self._lock = threading.RLock()
        self._serial: Optional[serial.Serial] = None
        self.connection_count = 0
        self._max_retries = max_retries
        self._retry_timeout = retry_timeout
        # Flag indicating next command should flush buffers due to previous failure
        self._flush_buffer = False
    
    def connect(self, port: str) -> None:
        """Connect to serial port with reference counting.
        
        Args:
            port: Serial port identifier (e.g., 'COM3', '/dev/ttyUSB0')
            
        Raises:
            RuntimeError: If serial connection fails
        """
        with self._lock:
            if self.connection_count == 0:
                self._initialize_connection(port)
            self.connection_count += 1
            self._logger.info(f"Serial connection count: {self.connection_count}")
    
    def disconnect(self) -> None:
        """Disconnect from serial port with reference counting.
        
        Notes:
            Connection is only closed when reference count reaches zero.
        """
        with self._lock:
            self.connection_count -= 1
            self._logger.info(f"Serial connection count: {self.connection_count}")
            if self.connection_count <= 0:
                self._cleanup_connection()
    
    def _initialize_connection(self, port: str) -> None:
        """Initialize the serial connection with TTS160 parameters.
        
        Args:
            port: Serial port identifier
            
        Raises:
            RuntimeError: If connection cannot be established
        """
        start_time = time.time()
        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.5
            )
            if not self._serial.is_open:
                self._serial.open()
            
            connection_time = time.time() - start_time
            self._logger.info(f"Serial connection opened on {port} in {connection_time:.3f}s")
            
        except Exception as ex:
            self._logger.error(f"Failed to open serial connection on {port}: {ex}")
            raise RuntimeError(f"Serial connection failed: {ex}") from ex
    
    def _cleanup_connection(self) -> None:
        """Clean up the serial connection safely.
        
        Notes:
            Suppresses cleanup errors to ensure clean shutdown.
        """
        try:
            if self._serial and self._serial.is_open:
                port_name = self._serial.port
                self._serial.close()
                self._logger.info(f"Serial connection closed on {port_name}")
        except Exception as ex:
            self._logger.warning(f"Error during connection cleanup: {ex}")
        finally:
            self._serial = None
    
    def cleanup(self) -> None:
        """Force cleanup of connection, bypassing reference counting.
        
        Notes:
            Used for emergency cleanup scenarios.
        """
        with self._lock:
            self.connection_count = 0
            self._cleanup_connection()
    
    @property
    def is_connected(self) -> bool:
        """Check if serial connection is active.
        
        Returns:
            True if connection is open and functional
        """
        with self._lock:
            return self._serial is not None and self._serial.is_open
    
    def send_command(self, command: str, command_type: CommandType) -> Union[str, bool]:
        """Send command with retry logic and automatic error recovery.
        
        Args:
            command: Command string to send (e.g., ':GR#')
            command_type: Type of expected response (BLIND, BOOL, STRING)
            
        Returns:
            For BLIND commands: empty string
            For BOOL commands: boolean response 
            For STRING commands: response string with terminator
            
        Raises:
            RuntimeError: If command fails after all retry attempts
        """
        # Clear buffers if previous failure occurred
        if self._flush_buffer:
            self._logger.debug(f"Previous failure detected, flushing receive buffer before {command}")
            self.clear_buffers()
            self._flush_buffer = False
        
        for attempt in range(self._max_retries + 1):
            try:
                start_time = time.time()
                result = self._send_command_once(command, command_type)
                exec_time = time.time() - start_time
                
                self._logger.debug(f"Command {command} completed in {exec_time:.3f}s, result: {result}")
                return result
                
            except Exception as ex:
                if not self._flush_buffer:
                    self._flush_buffer = True
                    
                if attempt == self._max_retries:
                    self._logger.error(f"Command {command} failed after {self._max_retries + 1} attempts: {ex}")
                    raise
                else:
                    self._logger.warning(f"Command {command} failed (attempt {attempt + 1}/{self._max_retries + 1}): {ex}")
                    time.sleep(self._retry_timeout)
        
        # Should not reach here due to raise in loop
        raise RuntimeError(f"Unexpected execution path in send_command for {command}")
    
    def _send_command_once(self, command: str, command_type: CommandType) -> Union[str, bool]:
        """Execute single command attempt without retry logic.
        
        Args:
            command: Command string to send
            command_type: Expected response type
            
        Returns:
            Command response based on command_type
            
        Raises:
            RuntimeError: For communication errors or invalid command types
        """
        with self._lock:
            if not self.is_connected:
                raise RuntimeError("Serial port not open")
            
            try:
                # Clear buffers before sending
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                
                # Send command
                self._logger.debug(f"Sending command: {command}")
                self._serial.write(command.encode('ascii'))
                self._serial.flush()
                
                # Handle response based on type
                if command_type == CommandType.BLIND:
                    time.sleep(self.BLIND_COMMAND_DELAY)
                    return ""
                
                elif command_type == CommandType.BOOL:
                    response = self._serial.read(1).decode('ascii')
                    if not response:
                        raise RuntimeError("No boolean response received")
                    
                    ret_bool: bool = response == '1'
                    self._logger.debug(f"Boolean response: '{response}' -> {ret_bool}")
                    
                    # Handle special case for :MS# command which sends extra data
                    if ret_bool and command == ":MS#":
                        try:
                            extra = self._serial.read_until(b'#').decode('ascii')
                            self._logger.debug(f"Cleared extra :MS# response: {extra}")
                        except Exception as ex:
                            self._logger.warning(f"Failed to clear extra :MS# response: {ex}")
                    
                    return ret_bool
                
                elif command_type == CommandType.STRING:
                    response = self._serial.read_until(b'#').decode('ascii')
                    if not response:
                        raise RuntimeError("No string response received")
                    self._logger.debug(f"String response: {response}")
                    return response
                
                else:
                    raise RuntimeError(f"Invalid command type: {command_type}")
                    
            except (serial.SerialException, UnicodeDecodeError) as ex:
                raise RuntimeError(f"Serial communication error for {command}: {ex}") from ex
    
    def clear_buffers(self) -> None:
        """Clear serial input/output buffers and drain any lingering data.
        
        Notes:
            Uses temporary timeout to avoid blocking on empty buffers.
        """
        with self._lock:
            if not self.is_connected:
                self._logger.debug("Cannot clear buffers - not connected")
                return
            
            try:
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                self._logger.debug("Input and output buffers reset")

                # Drain any lingering data with temporary timeout
                old_timeout = self._serial.timeout
                self._serial.timeout = self.BUFFER_CLEAR_TIMEOUT
                
                self._logger.debug("Draining any remaining queued responses")
                bytes_cleared = 0
                
                for attempt in range(self.BUFFER_CLEAR_ATTEMPTS):
                    data = self._serial.read(1)
                    if not data:
                        break
                    bytes_cleared += 1
                    self._logger.debug(f"Cleared byte #{bytes_cleared}: {data}")
                    
                if bytes_cleared > 0:
                    self._logger.info(f"Cleared {bytes_cleared} lingering bytes from buffer")
                else:
                    self._logger.debug("No lingering data found in buffer")
                    
                self._serial.timeout = old_timeout
                
            except Exception as ex:
                self._logger.warning(f"Error clearing buffers: {ex}")