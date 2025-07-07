# TTS160 Serial Communications Module

## Overview

The `tts160_serial` module provides enhanced serial communication capabilities for TTS160 telescope devices, supporting both traditional text-based LX200 commands and high-efficiency binary data transfers. The module implements dual binary protocols: a legacy case-based system for predefined data sets and a modern variable-based system for flexible multi-variable queries.

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
case_data = serial_mgr.get_case_data(2)
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
- `command`: Command string (e.g., ':GR#', ':*!2#', ':*!G T1,2#')
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

# Multi-variable query
data = serial_mgr.send_command(':*!G T1,2,C5#', CommandType.AUTO)
```

#### Binary Format Management

##### register_binary_format(name: str, format_string: str, field_names: List[str] = None) -> None

Registers custom binary data format for parsing.

**Parameters:**
- `name`: Format identifier (e.g., 'case2', 'multi_vars')
- `format_string`: Format specification (e.g., '5i2f', '2i3fB')
- `field_names`: Optional field names for dictionary output

#### Format Characters
- `i`: 32-bit signed integer (4 bytes)
- `f`: 32-bit float (4 bytes)  
- `h`: 16-bit signed integer (2 bytes)
- `b`: 8-bit signed integer (1 byte)
- `I`: 32-bit unsigned integer (4 bytes)
- `H`: 16-bit unsigned integer (2 bytes)
- `B`: 8-bit unsigned integer (1 byte)
- `m`: 3x3 transformation matrix (36 bytes, 9 doubles) **Note: sizeof(double) = sizeof(float) = 4 bytes in firmware**

**Example:**
```python
# Register format for case 2: 5 ints + 2 floats
serial_mgr.register_binary_format(
    'case2', 
    '5i2f',
    ['goto_speed_h', 'goto_speed_e', 'guide_speed_h', 
     'guide_speed_e', 'park_flag', 'park_az', 'park_alt']
)

# Register format for multi-variable response
serial_mgr.register_binary_format(
    'tracking_basic',
    '2i1f',
    ['h_ticks', 'e_ticks', 'ra_position']
)
```

#### Convenience Methods

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

### BinaryParser

Static utility class for binary format operations.

##### parse_format_string(format_str: str) -> Tuple[str, int]

Converts format string to struct format and byte count.

```python
struct_fmt, bytes_needed = BinaryParser.parse_format_string('5i2f')
# Returns: ('<5i2f', 28)

# Matrix format
struct_fmt, bytes_needed = BinaryParser.parse_format_string('1m')
# Returns: ('<9d', 72)  # 9 doubles for 3x3 matrix
```

##### create_format(name: str, format_string: str, field_names: List[str] = None) -> BinaryFormat

Creates validated BinaryFormat instance.

##### unpack_data(binary_format: BinaryFormat, data: bytes) -> Union[List[Any], Dict[str, Any]]

Unpacks binary data according to format specification.

## Binary Response Protocols

The TTS160 firmware implements a binary protocol for sending arbitrary data elements:

### Multi-Variable Protocol

Flexible variable queries via `:*!G <variables>#` commands.

```
Command: ":*!G T1,2,C5#"
Response: "BINARY:2i1B\n" + [9 bytes of binary data]
```

**Variable Categories:**
- **T**: Tracking subsystem (positions, motors, status)
- **C**: Control subsystem (speeds, settings, location)
- **M**: Mount subsystem (hardware configuration)
- **A**: Alignment subsystem (star positions, matrices)
- **L**: LX200 subsystem (protocol state)
- **O**: Motor subsystem (control parameters)
- **D**: Display subsystem (UI state)
- **X**: Computed variables (real-time calculations)

**Command Format:**
```
:*!G <category><id>[,<category><id>]...#

Examples:
:*!G T1#          - Get tracking variable 1 (H ticks)
:*!G T1,2,17#     - Get H ticks, E ticks, RA position
:*!G C1,2,M12#    - Get goto speeds and ticks per round
:*!G X1,2#        - Get computed altitude and azimuth
```

**Firmware Implementation:**
```c
// Handles flexible variable queries in GF_Lx200_Process_Binary_Command()
format_response_header(requests, var_count, header);
pack_response_data(requests, var_count, response_buffer, &data_size);
printf("%s", header);  // e.g., "BINARY:2i1f\n"
fwrite(response_buffer, 1, data_size, stdout);
```

### 3. Inline Binary Format

Direct format specification in response header.

```
Command: Custom commands
Response: "BINARY:5i2f\n" + [28 bytes of binary data]
```

### 4. String Fallback

Traditional text responses work unchanged:

```
Response: "123;456;789#"
```

### Error Responses

All binary protocols support standardized error reporting:

```
Response: "ERROR:<message>\n"

Examples:
ERROR:INVALID_CMD\n
ERROR:PARSE_ERROR\n
ERROR:VAR_ERROR\n
ERROR:RESPONSE_TOO_LARGE\n
```

**Protocol Requirements:**
- Binary data must be little-endian
- Headers must end with '\n'  
- String responses must end with '#'
- No mixing of binary and text in single response
- Matrix data stored as 9 consecutive floats (row-major)

## Variable Reference

### Tracking Variables (T1-T31)

| ID | Name | Type | Description |
|----|------|------|-------------|
| T1 | H_TICKS | int32 | Horizontal position ticks |
| T2 | E_TICKS | int32 | Elevation position ticks |
| T3 | R_TICKS | int32 | Rotator position ticks |
| T4 | TRACKING_ON | uint8 | Tracking enabled flag |
| T5 | ROTATOR_ON | uint8 | Rotator enabled flag |
| T6 | MOTOR_H_ON | uint8 | H motor enabled |
| T7 | MOTOR_E_ON | uint8 | E motor enabled |
| T8 | MOVING_H | uint8 | H motor moving |
| T9 | MOVING_E | uint8 | E motor moving |
| T10 | DIRECTION_H | int8 | H direction |
| T11 | DIRECTION_E | int8 | E direction |
| T12 | COLLISION | uint8 | Collision detected |
| T13 | MERIDIAN_FLIP | uint8 | Meridian flip needed |
| T14 | TRACKING_MODE | uint8 | Tracking mode |
| T15 | TRACKING_RATE | uint8 | Tracking rate |
| T16 | CUSTOM_RATE_TRACK | uint8 | Custom rate tracking |
| T17 | RA | float | Right ascension |
| T18 | DEC | float | Declination |
| T19 | TARGET_RA | float | Target RA |
| T20 | TARGET_DEC | float | Target DEC |
| T21 | CUSTOM_RATE_RA | float | Custom RA rate |
| T22 | CUSTOM_RATE_DEC | float | Custom DEC rate |
| T23 | GOTO_H_TICKS | int32 | Goto target H ticks |
| T24 | GOTO_E_TICKS | int32 | Goto target E ticks |
| T25 | GOTO_R_TICKS | int32 | Goto target R ticks |
| T26 | MSECS | uint32 | Millisecond counter |
| T27 | START_TIME | uint32 | Start tracking time |
| T28 | SOUTH_ANGLE | float | South angle |
| T29 | INITIAL_FIELD_ROT | float | Initial field rotation |
| T30 | ALIGNMENT_MATRIX | matrix | 3x3 alignment matrix |
| T31 | INV_MATRIX | matrix | 3x3 inverse matrix |

### Control Variables (C1-C25)

| ID | Name | Type | Description |
|----|------|------|-------------|
| C1 | GOTO_SPEED_H | uint8 | H goto speed |
| C2 | GOTO_SPEED_E | uint8 | E goto speed |
| C3 | GUIDE_SPEED_H | uint8 | H guide speed |
| C4 | GUIDE_SPEED_E | uint8 | E guide speed |
| C5 | PARK_FLAG | uint8 | Park status |
| C6 | CUSTOM_PARK_POS | uint8 | Custom park position |
| C7 | LANGUAGE | uint8 | Language setting |
| C8 | CHOSEN_LOCATION | uint8 | Location index |
| C9 | GOTO_ABORT | uint8 | Goto abort flag |
| C10 | SPEED_MODE | uint8 | Speed/step mode |
| C11 | DRIFT_MODE | uint8 | Drift mode |
| C12 | CATALOG_CHOICE | uint8 | Catalog selection |
| C13 | COORD_CHOICE | uint8 | Coordinate system |
| C14 | ERROR_CODE | uint8 | Error code |
| C15 | PARK_AZ | float | Park azimuth |
| C16 | PARK_ALT | float | Park altitude |
| C17 | LONGITUDE | float | Site longitude (radians) |
| C18 | LATITUDE | float | Site latitude (radians) |
| C19 | TIMEZONE | int8 | Timezone offset |
| C20 | DATE_YEAR | uint16 | Date year |
| C21 | DATE_MONTH | uint8 | Date month |
| C22 | DATE_DAY | uint8 | Date day |
| C23 | TIME_HOUR | uint8 | Time hour |
| C24 | TIME_MINUTE | uint8 | Time minute |
| C25 | TIME_SECOND | uint8 | Time second |

### Mount Variables (M1-M22)

| ID | Name | Type | Description |
|----|------|------|-------------|
| M1 | TELESCOPE_MOUNTING | uint8 | Mount type |
| M2 | BACKLASH_H | int16 | H backlash ticks |
| M3 | BACKLASH_E | int16 | E backlash ticks |
| M4 | GUIDE_CORR_H | int16 | H guide correction |
| M5 | GUIDE_CORR_E | int16 | E guide correction |
| M6 | BACKLASH_ON | uint8 | Backlash enabled |
| M7 | PEC_ON | uint8 | PEC enabled |
| M8 | CABLE_TWIST_ALARM | uint8 | Cable twist alarm |
| M9 | AZ_NORM_COUNTER | int8 | AZ normalization |
| M10 | MOTOR_DIR_H | uint8 | H motor direction |
| M11 | MOTOR_DIR_E | uint8 | E motor direction |
| M12 | TICKS_PER_ROUND_H | int32 | H ticks per revolution |
| M13 | TICKS_PER_ROUND_E | int32 | E ticks per revolution |
| M14 | WORMGEAR_TICKS_H | int32 | H wormgear ticks |
| M15 | WORMGEAR_TICKS_E | int32 | E wormgear ticks |
| M16 | FLIP_LIMIT_WEST | int32 | West flip limit |
| M17 | FLIP_LIMIT_EAST | int32 | East flip limit |
| M18 | FIELD_ROT_TICKS | int32 | Field rotation ticks |
| M19 | FIELD_ROT_RANGE | int32 | Field rotation range |
| M20 | FIELD_ROT_ANGLE | float | Field rotation angle |
| M21 | FIELD_ROT_DIRECTION | uint8 | Field rotation direction |
| M22 | CLOCK_FREQ | uint32 | Clock frequency |

### Computed Variables (X1-X2)

| ID | Name | Type | Description |
|----|------|------|-------------|
| X1 | CURRENT_ALT | float | Current altitude ⚠️ **Triggers position update** |
| X2 | CURRENT_AZ | float | Current azimuth ⚠️ **Triggers position update** |
| X3 | FreeMem | uint16 | RAM Available |

**Performance Note**: Computed variables execute `GF_Force_Position_Update()` and coordinate transformations, adding ~10ms latency per query.

*Note: Additional variable categories (A, L, O, D) available - see firmware source for complete listings.*

## Error Handling

### Exception Hierarchy
- `TTS160SerialError`: Base exception
  - `ConnectionError`: Port/communication issues
  - `BinaryFormatError`: Format validation errors
  - `ResponseError`: Response parsing failures

### Error Sources
- `connect()`: `ValueError`, `ConnectionError` for port/parameter issues
- `send_command()`: `ValueError` for command format, `ConnectionError` for communication
- `register_binary_format()`: `ValueError`, `BinaryFormatError` for format validation
- Binary parsing: `ResponseError` with graceful fallback to string

### Automatic Recovery
- Retry with exponential backoff (5 attempts)
- Buffer flushing on communication failures
- Graceful fallback to string parsing on binary errors

## Best Practices

1. **Use multi-variable queries** for related data to minimize round trips
2. **Use AUTO detection** for mixed command sequences  
3. **Register formats once** during initialization
4. **Handle connection cleanup** with context managers
5. **Leverage computed variables** (X1, X2) for real-time coordinate transforms
6. **Cache transformation matrices** (T32, T33) rather than repeated queries

## Migration Guide

### From Legacy Case System

```python
# New flexible approach  
motor_data = serial_mgr.send_command(':*!G C1,2,3,4,5#')
# Gets goto_speed_h, goto_speed_e, guide_speed_h, guide_speed_e, park_flag

# Mix with real-time data
current_state = serial_mgr.send_command(':*!G T1,2,17,18,X1,2#')
# Gets h_ticks, e_ticks, ra, dec, current_alt, current_az
```

### Enhanced Error Handling

```python
try:
    with SerialManager(logger) as serial_mgr:
        serial_mgr.connect('/dev/ttyUSB0')
        
        # Multi-variable query
        tracking_data = serial_mgr.send_command(':*!G T1,2,4,17,18#')
            
except BinaryFormatError as e:
    logger.error(f"Format error: {e}")
    # Handle format registration issues
    
except ResponseError as e:
    logger.error(f"Response parsing error: {e}")
    # Handle malformed responses
    
except ConnectionError as e:
    logger.error(f"Communication error: {e}")
    # Implement retry logic or fallback
```

## Threading

Thread-safe design with internal locking:
- Connection reference counting with concurrent access
- Binary format registry protection
- Atomic command execution

Multiple SerialManager instances can operate independently on different ports or the same port with automatic connection sharing.

## Examples

### Basic Multi-Variable Query
```python
import logging
from tts160_serial import SerialManager

logger = logging.getLogger(__name__)

with SerialManager(logger) as serial_mgr:
    serial_mgr.connect('/dev/ttyUSB0')
    
    # Get current position and status in one command
    status = serial_mgr.send_command(':*!G T1,2,4,17,18,X1,2#')
    # Returns: [h_ticks, e_ticks, tracking_on, ra, dec, alt, az]
    
    print(f"Position: RA={status[3]:.4f}, DEC={status[4]:.4f}")
    print(f"Alt/Az: {status[5]:.2f}°, {status[6]:.2f}°")
```

### Matrix Data Access
```python
# Get alignment transformation matrices
matrices = serial_mgr.send_command(':*!G T32,33#')
alignment_matrix = matrices[0]  # 9-element transformation matrix
inverse_matrix = matrices[1]    # 9-element inverse matrix
```

### Custom Format Registration
```python
# Register format for specific variable combination
serial_mgr.register_binary_format(
    'position_status',
    '2i2fB',  # 2 ints, 2 floats, 1 byte
    ['h_ticks', 'e_ticks', 'ra', 'dec', 'tracking']
)

# Use with corresponding multi-variable query
pos_data = serial_mgr.send_command(':*!G T1,2,17,18,4#')
# Returns: {'h_ticks': 12345, 'e_ticks': 67890, 'ra': 1.23, 'dec': 0.45, 'tracking': 1}
```
## Troubleshooting

### Common Issues

**Multi-variable parsing fails**
- Check variable category/ID validity (T1-T31, C1-C25, etc.)
- Verify firmware supports requested variables
- Use single variable queries to isolate issues

**Binary format registration errors**
- Ensure format string matches expected data layout
- Check field name count matches format values
- Review `BinaryFormatError` details for specific validation failures

**Matrix data corruption**
- Verify 36-byte matrix size in responses
- Check double precision handling in format registration
- Ensure matrix variables (T32, T33) are properly aligned

**Connection timeout with complex queries**  
- Break large multi-variable queries into smaller chunks
- Check firmware memory limits for variable count
- Use timeout adjustments for compute-intensive variables (X1, X2)

**:MS# command anomalies**
- Returns '1' followed by additional data that must be cleared
- Driver automatically handles this, but manual parsing requires extra read

### Debug Techniques

```python
# Enable verbose logging
logging.basicConfig(level=logging.DEBUG)

# Test individual variables
for var_id in range(1, 32):
    try:
        result = serial_mgr.send_command(f':*!G T{var_id}#')
        print(f"T{var_id}: {result}")
    except Exception as e:
        print(f"T{var_id} failed: {e}")

# Validate binary format parsing
raw_response = serial_mgr.send_command(':*!2#', CommandType.AUTO)
manual_parse = BinaryParser.unpack_data(binary_format, raw_data)
```