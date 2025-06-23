# TTS160 Serial Communications Module

## Overview

The `tts160_serial` module provides enhanced serial communication capabilities for TTS160 telescope devices, supporting both traditional text-based commands and high-efficiency binary data transfers.

## Requirements

- Python 3.7+
- pyserial
- logging (standard library)
- threading (standard library)

## Quick Start

```python
from tts160_serial import SerialManager
from tts160_types import CommandType
import logging

# Initialize
logger = logging.getLogger(__name__)
serial_mgr = SerialManager(logger)

# Connect and use
serial_mgr.connect('/dev/ttyUSB0')
response = serial_mgr.send_command(':GR#', CommandType.STRING)
serial_mgr.disconnect()
```

## Classes

### SerialManager

Thread-safe serial communication manager with automatic binary/text detection and retry logic.

#### Constructor

```python
SerialManager(logger: Optional[Logger] = None)
```

**Parameters:**
- `logger`: Optional logger instance. Creates module logger if None.

#### Context Manager Support

```python
with SerialManager(logger) as serial_mgr:
    serial_mgr.connect('/dev/ttyUSB0')
    result = serial_mgr.send_command(':GR#')
    # Automatic cleanup on exit
```

#### Connection Management

##### connect(port: str, baudrate: int = 9600) -> None
Establishes serial connection with reference counting.

```python
serial_mgr.connect('/dev/ttyUSB0', 19200)  # Custom baudrate
```

**Raises:**
- `ValueError`: Invalid port or baudrate
- `ConnectionError`: Connection failure

##### disconnect() -> None
Decrements connection count, closes when reaching zero.

##### cleanup() -> None
Forces immediate connection cleanup.

##### is_connected -> bool
Property returning current connection status.

##### connection_count -> int  
Property returning current reference count.

#### Command Interface

##### send_command(command: str, command_type: CommandType = CommandType.AUTO) -> Union[str, bool, List[Any], Dict[str, Any]]

Sends command with automatic retry and response parsing.

**Parameters:**
- `command`: Command string (e.g., ':GR#')
- `command_type`: Response handling mode

**Raises:**
- `ValueError`: Invalid command format or parameters
- `ConnectionError`: Communication failures, not connected  
- `ResponseError`: Response parsing failures

**Example:**
```python
# Boolean command
tracking = serial_mgr.send_command(':GS#', CommandType.BOOL)

# String command
ra = serial_mgr.send_command(':GR#', CommandType.STRING)

# Binary case data
case_data = serial_mgr.send_command(':*!2#', CommandType.AUTO)
```

#### Binary Format Management

##### register_binary_format(name: str, format_string: str, field_names: List[str] = None) -> None

Registers custom binary data format for parsing.

**Parameters:**
- `name`: Format identifier (e.g., 'case2')
- `format_string`: Format specification (e.g., '5i2f')
- `field_names`: Optional field names for dictionary output

#### Format Characters
- `i`: 32-bit signed integer (4 bytes)
- `f`: 32-bit float (4 bytes)  
- `h`: 16-bit signed integer (2 bytes)
- `b`: 8-bit signed integer (1 byte)
- `I`: 32-bit unsigned integer (4 bytes)
- `H`: 16-bit unsigned integer (2 bytes)
- `B`: 8-bit unsigned integer (1 byte)

**Example:**
```python
# Register format for case 2: 5 ints + 2 floats
serial_mgr.register_binary_format(
    'case2', 
    '5i2f',
    ['goto_speed_h', 'goto_speed_e', 'guide_speed_h', 
     'guide_speed_e', 'park_flag', 'park_az', 'park_alt']
)
```

#### Convenience Methods

##### get_case_data(case_number: int) -> Union[List[Any], Dict[str, Any]]

Retrieves binary case data using the `:*!n#` command format.

```python
# Get case 2 binary data
case_data = serial_mgr.get_case_data(2)
```

##### clear_buffers() -> None

Clears serial input/output buffers and purges queued responses.

### CommandType (Enum)

Response handling modes for serial commands.

```python
class CommandType(IntEnum):
    BLIND = 0    # No response expected
    BOOL = 1     # Single character boolean ('0'/'1')  
    STRING = 2   # String terminated with '#'
    AUTO = 3     # Auto-detect text vs binary
```

### BinaryFormat (Dataclass)

Immutable binary data structure definition with validation.

```python
@dataclass(frozen=True)
class BinaryFormat:
    name: str                    # Format identifier
    format_string: str          # Format specification (e.g., '5i2f')
    struct_format: str          # Python struct format ('<5i2f')
    byte_size: int              # Total bytes required
    field_names: Optional[List[str]]  # Optional field names
```

### BinaryFormat (Dataclass)

Binary data structure definition.

```python
@dataclass
class BinaryFormat:
    name: str                    # Format identifier
    format_string: str          # Format specification (e.g., '5i2f')
    struct_format: str          # Python struct format ('<5i2f')
    byte_size: int              # Total bytes required
    field_names: List[str]      # Optional field names
```

### BinaryParser

Static utility class for binary format operations.

##### parse_format_string(format_str: str) -> Tuple[str, int]

Converts format string to struct format and byte count.

```python
struct_fmt, bytes_needed = BinaryParser.parse_format_string('5i2f')
# Returns: ('<5i2f', 28)
```

##### create_format(name: str, format_string: str, field_names: List[str] = None) -> BinaryFormat

Creates validated BinaryFormat instance.

##### unpack_data(binary_format: BinaryFormat, data: bytes) -> Union[List[Any], Dict[str, Any]]

Unpacks binary data according to format specification.

## Binary Response Protocols

The module supports multiple binary response formats for efficient data transfer:

### Header-Prefixed Binary

Firmware sends format specification in header:

```
"BINARY:5i2f\n" + [20 bytes of binary data]
```

**Firmware Implementation:**
```c
// Send header first
printf("BINARY:5i2f\n");
// Send binary data directly to stdout
fwrite(binary_data, 1, data_size, stdout);
```

### Case-Based Binary (Primary Protocol)

The `:*!n#` command format for predefined case data:

```
Command: ":*!2#"
Response: "CASE:2B\n" + [28 bytes of binary data]
```

**Firmware Implementation:**
```c
// Detect :*!n# command
if (command[1] == '*' && command[2] == '!') {
    int case_num = command[3] - '0';
    printf("CASE:%dB\n", case_num);
    fwrite(&case_data[case_num], 1, case_sizes[case_num], stdout);
    fflush(stdout);
}
```

### String Fallback

Traditional text responses work unchanged:

```
"123;456;789#"
```

**Protocol Requirements:**
- Binary data must be little-endian
- Headers must end with '\n'  
- String responses must end with '#'
- No mixing of binary and text in single response

## Error Handling

### Connection Errors
- `ValueError`: Invalid parameters (port, baudrate, command format)
- `ConnectionError`: Port access, communication failures, retry exhaustion
- `BinaryFormatError`: Invalid formats, data size mismatches  
- `ResponseError`: Response parsing failures
- Automatic retry with exponential backoff (5 attempts)
- Buffer flushing on communication failures

**Exception Sources:**
- `connect()`: `ValueError`, `ConnectionError` for port/parameter issues
- `send_command()`: `ValueError` for command format, `ConnectionError` for communication
- `register_binary_format()`: `ValueError`, `BinaryFormatError` for format validation
- Binary parsing: `ResponseError` with graceful fallback to string

### Binary Parse Errors
- Graceful fallback to string parsing
- Size validation for binary data
- Format validation for registered formats

### Usage Pattern
```python
try:
    response = serial_mgr.send_command(':GCS2B#')
except RuntimeError as e:
    logger.error(f"Communication failed: {e}")
    # Handle error
```

## Predefined Binary Formats

The module includes predefined formats for common cases:

| Format | Description | Size | Fields |
|--------|-------------|------|--------|
| case0 | 15 integers + 4 floats | 76 bytes | Position/status data |
| case1 | 9 floats + 3 integers | 48 bytes | Coordinate data |  
| case2 | 5 integers + 2 floats | 28 bytes | Motor speeds/park data |
| case4 | 7 integers | 28 bytes | Mount configuration |

## Performance Considerations

### Binary vs Text Transmission

| Data Type | ASCII Size | Binary Size | Savings |
|-----------|------------|-------------|---------|
| Case 2 (5i+2f) | ~37 bytes | 28 bytes | 24% |
| Case 4 (7i) | ~48 bytes | 28 bytes | 42% |
| Case 5 (9f) | ~85 bytes | 36 bytes | 58% |

### Best Practices

1. **Use binary for data-heavy operations** (matrices, arrays)
2. **Use AUTO detection** for mixed command sequences  
3. **Register formats once** during initialization
4. **Handle connection cleanup** in finally blocks

## Migration from Original Module

The enhanced module is a drop-in replacement:

```python
# Import change only
from tts160_serial import SerialManager

# All existing code works unchanged  
serial_mgr = SerialManager(logger)
result = serial_mgr.send_command(':GR#', CommandType.STRING)
```

**Enhancements:**
- Custom exception hierarchy for better error handling
- Input validation for all parameters
- Context manager support for automatic cleanup
- Enhanced logging throughout operations
- Immutable format definitions with validation

## Threading

The module is thread-safe with internal locking:
- Connection reference counting
- Binary format registry protection  
- Atomic command execution

## Examples

### Basic Usage
```python
import logging
from tts160_serial import SerialManager
from tts160_types import CommandType

logger = logging.getLogger(__name__)
serial_mgr = SerialManager(logger)

try:
    serial_mgr.connect('/dev/ttyUSB0')
    
    # Text command
    ra = serial_mgr.send_command(':GR#', CommandType.STRING)
    print(f"RA: {ra}")
    
    # Binary status (auto-detected)
    status = serial_mgr.send_command(':GCS2B#', CommandType.AUTO)
    if isinstance(status, dict):
        print(f"Park status: {status['park_flag']}")
    
finally:
    serial_mgr.disconnect()
```

### Custom Binary Format
```python
# Register custom format
serial_mgr.register_binary_format(
    'motor_data',
    '4i2f',  # 4 ints, 2 floats
    ['step_h', 'step_e', 'active_h', 'active_e', 'speed_h', 'speed_e']
)

# Use with custom command
motor_status = serial_mgr.send_command(':GMOT#', CommandType.AUTO)
print(f"Motor H speed: {motor_status['speed_h']}")
```

### Error Handling
```python
try:
    with SerialManager(logger) as serial_mgr:
        serial_mgr.connect('/dev/ttyUSB0')
        case_data = serial_mgr.get_case_data(2)
        process_motor_data(case_data)
        
except ValueError as e:
    logger.error(f"Parameter error: {e}")
    # Handle invalid parameters
    
except ConnectionError as e:
    logger.error(f"Communication error: {e}")
    # Implement fallback strategy
    
except BinaryFormatError as e:
    logger.error(f"Format error: {e}")
    # Handle malformed format
    
except ResponseError as e:
    logger.error(f"Response parsing error: {e}")
    # Handle malformed response
```

### Context Manager (Recommended)
```python
# Automatic connection management and cleanup
with SerialManager(logger) as serial_mgr:
    serial_mgr.connect('/dev/ttyUSB0')
    result = serial_mgr.send_command(':*!0#')
    case_data = serial_mgr.get_case_data(2)
    # Connection automatically cleaned up on exit
```

### Multi-Threading Support
```python
import threading

def worker_thread(port, logger, results, thread_id):
    """Each thread gets its own SerialManager instance."""
    serial_mgr = SerialManager(logger)
    try:
        serial_mgr.connect(port)
        result = serial_mgr.get_case_data(thread_id)
        results[thread_id] = result
    finally:
        serial_mgr.disconnect()

# Safe concurrent access
results = {}
threads = []
for i in range(3):
    t = threading.Thread(target=worker_thread, 
                        args=('/dev/ttyUSB0', logger, results, i))
    threads.append(t)
    t.start()

for t in threads:
    t.join()
```

## Troubleshooting

### Common Issues

**Binary parsing fails**
- Check format registration matches firmware output
- Verify byte counts and field names in format string
- Use `BinaryFormatError` exception details for debugging

**Connection errors**  
- Verify port permissions and device availability
- Check cable connections and baud rate settings
- Review `ConnectionError` messages for specific issues

**Parameter validation errors**
- Ensure command format (starts with ':', ends with '#')
- Validate case numbers (0-9) and format strings
- Check `ValueError` messages for specific parameter issues