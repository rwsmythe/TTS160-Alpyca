# File: tts160_serial.py  
"""Serial communication management for TTS160."""

import threading
import time
from typing import Optional
import serial
from logging import Logger
from .tts160_types import CommandType


class SerialManager:
    """Manages serial connection for TTS160 device with retry logic."""
    
    def __init__(self, logger: Logger):
        self._logger = logger
        self._lock = threading.RLock()
        self._serial: Optional[serial.Serial] = None
        self._connection_count = 0
        self._max_retries = 5
        self._retry_timeout = 0.5
    
    def connect(self, port: str) -> None:
        """Connect to serial port."""
        with self._lock:
            if self._connection_count == 0:
                self._initialize_connection(port)
            self._connection_count += 1
            self._logger.info(f"Serial connection count: {self._connection_count}")
    
    def disconnect(self) -> None:
        """Disconnect from serial port."""
        with self._lock:
            self._connection_count -= 1
            self._logger.info(f"Serial connection count: {self._connection_count}")
            if self._connection_count <= 0:
                self._cleanup_connection()
    
    def _initialize_connection(self, port: str) -> None:
        """Initialize the serial connection."""
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
            
            self._logger.info(f"Serial connection opened on {port}")
            
        except Exception as ex:
            self._logger.error(f"Failed to open serial connection: {ex}")
            raise RuntimeError(f"Serial connection failed: {ex}") from ex
    
    def _cleanup_connection(self) -> None:
        """Clean up the serial connection."""
        try:
            if self._serial and self._serial.is_open:
                self._serial.close()
        except Exception:
            pass  # Ignore cleanup errors
        finally:
            self._serial = None
    
    def cleanup(self) -> None:
        """Force cleanup of connection."""
        with self._lock:
            self._connection_count = 0
            self._cleanup_connection()
    
    @property
    def is_connected(self) -> bool:
        """Check if serial connection is active."""
        with self._lock:
            return self._serial is not None and self._serial.is_open
    
    def send_command(self, command: str, command_type: CommandType) -> str:
        """Send command with retry logic."""
        for attempt in range(self._max_retries + 1):
            try:
                return self._send_command_once(command, command_type)
            except Exception as ex:
                if attempt == self._max_retries:
                    self._logger.error(f"Command {command} failed after {self._max_retries + 1} attempts")
                    raise
                else:
                    self._logger.warning(f"Command {command} failed (attempt {attempt + 1}), retrying: {ex}")
                    time.sleep(self._retry_timeout)
        
        return ""  # Should not reach here
    
    def _send_command_once(self, command: str, command_type: CommandType) -> str:
        """Send single command attempt."""
        with self._lock:
            if not self.is_connected:
                raise RuntimeError("Serial port not open")
            
            try:
                # Clear buffers
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                
                # Send command
                self._serial.write(command.encode('ascii'))
                self._serial.flush()
                
                # Handle response
                if command_type == CommandType.BLIND:
                    time.sleep(0.01)  # Small delay
                    return ""
                
                elif command_type == CommandType.BOOL:
                    response = self._serial.read(1).decode('ascii')
                    if not response:
                        raise RuntimeError("No boolean response received")
                    
                    ret_bool = response == '1'
                    
                    # Handle special case for :MS# command
                    if ret_bool and command == ":MS#":
                        try:
                            extra = self._serial.read_until(b'#').decode('ascii')
                            self._logger.debug(f"Cleared extra response: {extra}")
                        except Exception:
                            pass
                    
                    return str(ret_bool)
                
                elif command_type == CommandType.STRING:
                    response = self._serial.read_until(b'#').decode('ascii')
                    if not response:
                        raise RuntimeError("No string response received")
                    return response
                
                else:
                    raise RuntimeError(f"Invalid command type: {command_type}")
                    
            except (serial.SerialException, UnicodeDecodeError) as ex:
                raise RuntimeError(f"Serial communication error: {ex}") from ex
    
    def clear_buffers(self) -> None:
        """Clear serial buffers."""
        with self._lock:
            if not self.is_connected:
                return
            
            try:
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                
                # Clear any lingering data
                old_timeout = self._serial.timeout
                self._serial.timeout = 0.1
                
                for _ in range(100):  # Safety limit
                    data = self._serial.read(1)
                    if not data:
                        break
                
                self._serial.timeout = old_timeout
                
            except Exception as ex:
                self._logger.warning(f"Error clearing buffers: {ex}")