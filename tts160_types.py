# File: tts160_types.py
"""Type definitions for TTS160 driver v357 binary protocol.

This module defines enumerations and constants for the v357 binary variable
protocol, replacing the legacy LX200 command system.

Protocol Overview:
- GET commands: `:*!G <category><id>[,<id>]...#` returns `BINARY:<format>\n<data>`
- SET commands: `:*!S <cmd_id>;<binary_data>#` returns binary response
- All multi-byte values are little-endian
- Coordinates are in radians
"""

from enum import IntEnum, Enum
from typing import Dict, List, Tuple


class CommandType(IntEnum):
    """Serial command response types."""
    BLIND = 0    # No response expected
    BOOL = 1     # Single character boolean response
    STRING = 2   # String response terminated with '#'
    AUTO = 3     # Auto-detect text vs binary response
    BINARY = 4   # Binary response with header


class V357Category(str, Enum):
    """v357 binary protocol variable categories."""
    TRACKING = 'T'    # Position, RA/Dec, alignment quaternion (max ID: 32)
    CONTROL = 'C'     # Park, location, date/time, speeds (max ID: 25)
    MOUNT = 'M'       # Motor config, ticks, field rotation (max ID: 22)
    ALIGNMENT = 'A'   # Star positions, alignment status (max ID: 15)
    LX200 = 'L'       # Slew state, sync, goto flags (max ID: 13)
    MOTOR = 'O'       # Jerk, position, numerator/denominator (max ID: 16)
    DISPLAY = 'D'     # Menu state, scroll flags (max ID: 5)
    COMPUTED = 'X'    # Real-time alt/az, free memory (max ID: 3)


class TrackingVar(IntEnum):
    """Tracking category (T) variable IDs."""
    H_TICKS = 1              # int32: Horizontal position ticks
    E_TICKS = 2              # int32: Elevation position ticks
    R_TICKS = 3              # int32: Rotator position ticks
    TRACKING_ON = 4          # uint8: Tracking enabled flag
    ROTATOR_ON = 5           # uint8: Rotator enabled flag
    MOTOR_H_ON = 6           # uint8: Horizontal motor enabled
    MOTOR_E_ON = 7           # uint8: Elevation motor enabled
    MOVING_H = 8             # uint8: Horizontal motor moving
    MOVING_E = 9             # uint8: Elevation motor moving
    DIRECTION_H = 10         # int8: Horizontal direction
    DIRECTION_E = 11         # int8: Elevation direction
    COLLISION = 12           # uint8: Collision detected flag
    TRACKING_MODE = 13       # uint8: Tracking mode
    TRACKING_RATE = 14       # uint8: Tracking rate
    CUSTOM_RATE_TRACK = 15   # uint8: Custom rate tracking flag
    RA = 16                  # float: Right ascension (radians)
    DEC = 17                 # float: Declination (radians)
    TARGET_RA = 18           # float: Target RA (radians)
    TARGET_DEC = 19          # float: Target DEC (radians)
    TARGET_H = 20            # int32: Target H ticks
    TARGET_E = 21            # int32: Target E ticks
    CUSTOM_RATE_RA = 22      # float: Custom RA rate
    CUSTOM_RATE_DEC = 23     # float: Custom DEC rate
    GOTO_H_TICKS = 24        # int32: Goto target H ticks
    GOTO_E_TICKS = 25        # int32: Goto target E ticks
    GOTO_R_TICKS = 26        # int32: Goto target R ticks
    MSECS = 27               # uint32: Millisecond counter
    START_TIME = 28          # uint32: Start tracking time
    SOUTH_ANGLE = 29         # float: South angle (radians)
    INITIAL_FIELD_ROT = 30   # float: Initial field rotation
    ALIGNMENT_QUAT = 31      # quat (4 floats): Alignment transformation quaternion
    INV_QUAT = 32            # quat (4 floats): Inverse transformation quaternion


class ControlVar(IntEnum):
    """Control category (C) variable IDs."""
    GOTO_SPEED_H = 1         # uint8: Horizontal goto speed
    GOTO_SPEED_E = 2         # uint8: Elevation goto speed
    GUIDE_SPEED_H = 3        # uint8: Horizontal guide speed
    GUIDE_SPEED_E = 4        # uint8: Elevation guide speed
    PARK_FLAG = 5            # uint8: Park status flag
    CUSTOM_PARK_POS = 6      # uint8: Custom park position flag
    LANGUAGE = 7             # uint8: Language setting
    CHOSEN_LOCATION = 8      # uint8: Location index
    GOTO_ABORT = 9           # uint8: Goto abort flag
    SPEED_MODE = 10          # uint8: Speed/step mode flag
    DRIFT_MODE = 11          # uint8: Current drift mode
    CATALOG_CHOICE = 12      # uint8: Catalog selection
    COORD_CHOICE = 13        # uint8: Coordinate system choice
    ERROR_CODE = 14          # uint8: Current error code
    PARK_AZ = 15             # float: Park azimuth (radians)
    PARK_ALT = 16            # float: Park altitude (radians)
    LONGITUDE = 17           # float: Site longitude (radians, converted from DMS)
    LATITUDE = 18            # float: Site latitude (radians, converted from DMS)
    TIMEZONE = 19            # int8: Timezone offset (hours)
    DATE_YEAR = 20           # uint16: Date year
    DATE_MONTH = 21          # uint8: Date month
    DATE_DAY = 22            # uint8: Date day
    TIME_HOUR = 23           # uint8: Time hour
    TIME_MINUTE = 24         # uint8: Time minute
    TIME_SECOND = 25         # uint8: Time second


class MountVar(IntEnum):
    """Mount category (M) variable IDs."""
    TELESCOPE_MOUNTING = 1   # uint8: Mount type
    GUIDE_CORR_H = 2         # int16: H guide correction ticks
    GUIDE_CORR_E = 3         # int16: E guide correction ticks
    CABLE_TWIST_ALARM = 4    # uint8: Cable twist alarm flag
    AZ_NORM_COUNTER = 5      # int8: AZ normalization counter
    MOTOR_DIR_H = 6          # uint8: H motor direction
    MOTOR_DIR_E = 7          # uint8: E motor direction
    TICKS_PER_ROUND_H = 8    # int32: H ticks per revolution
    TICKS_PER_ROUND_E = 9    # int32: E ticks per revolution
    WORMGEAR_TICKS_H = 10    # int32: H wormgear ticks
    WORMGEAR_TICKS_E = 11    # int32: E wormgear ticks
    FIELD_ROT_TICKS = 12     # int32: Field rotation ticks
    FIELD_ROT_RANGE = 13     # int32: Field rotation tick range
    FIELD_ROT_ANGLE = 14     # float: Field rotation angle (radians)
    FIELD_ROT_DIRECTION = 15 # uint8: Field rotation direction
    CLOCK_FREQ = 16          # uint32: Clock frequency (Hz)


class AlignmentVar(IntEnum):
    """Alignment category (A) variable IDs."""
    ALIGN_STATUS = 1         # uint8: Alignment status
    START_SID_TIME = 2       # float: Start sidereal time
    ALIGN_SID_TIME = 3       # float: Alignment sidereal time
    STAR1_H_TICKS = 4        # int32: Star 1 H ticks
    STAR1_E_TICKS = 5        # int32: Star 1 E ticks
    STAR2_H_TICKS = 6        # int32: Star 2 H ticks
    STAR2_E_TICKS = 7        # int32: Star 2 E ticks
    STAR3_H_TICKS = 8        # int32: Star 3 H ticks
    STAR3_E_TICKS = 9        # int32: Star 3 E ticks
    STAR1_RA = 10            # float: Star 1 RA (radians)
    STAR1_DEC = 11           # float: Star 1 DEC (radians)
    STAR2_RA = 12            # float: Star 2 RA (radians)
    STAR2_DEC = 13           # float: Star 2 DEC (radians)
    STAR3_RA = 14            # float: Star 3 RA (radians)
    STAR3_DEC = 15           # float: Star 3 DEC (radians)


class LX200Var(IntEnum):
    """LX200 category (L) variable IDs."""
    GOTO_OBJECT = 1          # uint8: Goto object flag
    STOP_GOTO = 2            # uint8: Stop goto flag
    SLEW_SPEED = 3           # uint8: Slew speed
    SLEW_DIRECTION = 4       # uint8: Slew direction
    SLEWING = 5              # uint8: Slewing status
    GOTO_ACTIVE = 6          # uint8: Goto active flag
    SYNC = 7                 # uint8: Sync flag
    PARK_CMD = 8             # uint8: Park command flag
    OBJECT_RA = 9            # float: Object RA (radians, converted from HMS)
    OBJECT_DEC = 10          # float: Object DEC (radians, converted from DMS)
    SYNC_TARGET_RA = 11      # float: Sync target RA (radians)
    SYNC_TARGET_DEC = 12     # float: Sync target DEC (radians)


class MotorVar(IntEnum):
    """Motor category (O) variable IDs."""
    H_JERK = 1               # uint16: H motor jerk
    E_JERK = 2               # uint16: E motor jerk
    H_ACTIVE = 3             # uint8: H motor active
    E_ACTIVE = 4             # uint8: E motor active
    H_POSIT_ACTIVE = 5       # uint8: H position active
    E_POSIT_ACTIVE = 6       # uint8: E position active
    H_DENOMINATOR = 7        # uint16: H denominator
    E_DENOMINATOR = 8        # uint16: E denominator
    H_NUM_FINAL = 9          # uint16: H final numerator
    E_NUM_FINAL = 10         # uint16: E final numerator
    H_NUM_CURR = 11          # uint16: H current numerator
    E_NUM_CURR = 12          # uint16: E current numerator
    H_POSIT_INIT = 13        # float: H initial position
    E_POSIT_INIT = 14        # float: E initial position
    H_POSIT_FINAL = 15       # float: H final position
    E_POSIT_FINAL = 16       # float: E final position


class DisplayVar(IntEnum):
    """Display category (D) variable IDs."""
    DISPLAY_SCROLL = 1       # uint8: Display scroll flag
    UPDATE_SCREEN = 2        # uint8: Update screen flag
    CURRENT_MENU_ITEM = 3    # uint8: Current menu item
    OLD_MENU_ITEM = 4        # uint8: Old menu item
    ARROW_ON_HANDPAD = 5     # uint8: Arrow on handpad flag


class ComputedVar(IntEnum):
    """Computed category (X) variable IDs.

    Note: These trigger real-time calculations on the mount.
    """
    CURRENT_ALT = 1          # float: Current altitude (radians, computed on demand)
    CURRENT_AZ = 2           # float: Current azimuth (radians, computed on demand)
    FREE_MEM = 3             # uint16: Available RAM (bytes)


class SetCommand(IntEnum):
    """SET command IDs for :*!S commands."""
    SET_AXIS_RATE = 0x00     # Set axis tracking rate: axis_index (uint8) + rate (float)
    SET_GUIDE_RATE = 0x01    # Set guide rate: rate_index (uint8) [0-3 = 1x,3x,5x,10x sidereal]
    SET_SLEW_RATE = 0x02     # Set slew rate: rate_index (uint8) [0=Center,1=Guide,2=Find,3=Max]
    MOVE_AXIS = 0x03         # Move axis: direction (uint8) + speed (float) [0-3.5 deg/s]
    SLEW_TO_TARGET = 0x04    # Slew to target: slew_type (uint8) + [coords]
    GUIDE = 0x05             # Pulse guide: direction (uint8) + duration_ms (uint16)
    HALT_ALL = 0x06          # Emergency stop: no parameters
    SET_TARGET = 0x07        # Set target coords: ra (float) + dec (float) [radians]
    SET_DATE = 0x08          # Set date: month + day + year (uint16)
    SET_LOCAL_TIME = 0x09    # Set time: hour + minute + second (uint16)
    SET_PARK_LOCATION = 0x0A # Set park: position (uint8) + [az (float) + alt (float)]
    PARK_UNPARK = 0x0B       # Park/unpark: action (uint8) [0=park, 1=unpark]
    ROTATOR_OPS = 0x0C       # Rotator operations: operation (uint8)
    SET_TRACK_RATE = 0x0D    # Set track rate: rate_index (uint8) [0=Sidereal,1=Lunar,2=Solar]
    SET_TRACKING = 0x0E      # Enable/disable tracking: state (uint8)
    SYNC_FUNCTIONS = 0x0F    # Sync: sync_type (uint8) + [points (uint8)]
    INITIALIZE = 0x10        # Initialize mount: no parameters
    SET_LOCATION = 0x11      # Set site location: 22-byte payload


class SlewType(IntEnum):
    """Slew type indices for SLEW_TO_TARGET command."""
    TARGET = 0      # Use preset target coordinates
    RA_DEC = 1      # RA/Dec coordinates (radians)
    ALT_AZ = 2      # Alt/Az coordinates (radians)
    HOME = 3        # Home position


class GuideDirection(IntEnum):
    """Guide/slew direction indices."""
    NORTH = 0
    SOUTH = 1
    EAST = 2
    WEST = 3


class TrackingRate(IntEnum):
    """Tracking rate indices for SET_TRACK_RATE command."""
    SIDEREAL = 0
    LUNAR = 1
    SOLAR = 2


class GuideRate(IntEnum):
    """Guide rate indices for SET_GUIDE_RATE command."""
    RATE_1X = 0     # 1x sidereal
    RATE_3X = 1     # 3x sidereal
    RATE_5X = 2     # 5x sidereal
    RATE_10X = 3    # 10x sidereal


class SlewRate(IntEnum):
    """Slew rate indices for SET_SLEW_RATE command."""
    CENTERING = 0
    GUIDING = 1
    FIND = 2
    MAX = 3


class BinaryError(IntEnum):
    """Binary protocol error codes."""
    SUCCESS = 0
    PARSE_FAILED = -1
    VAR_NOT_FOUND = -2
    CMD_NOT_FOUND = -3
    TOO_MANY_VARS = -4   # Max 10 variables per command
    TOO_MANY_CMDS = -5   # Max 2 commands per command
    CMD_FAILURE = -6


class CmdResponseType(IntEnum):
    """SET command response types."""
    NONE = 0
    INT = 1
    FLOAT = 2
    STRING = 3
    ERROR = 4


# Binary format type specifications
# Format: (struct_format, byte_size)
BINARY_TYPE_SPECS: Dict[str, Tuple[str, int]] = {
    'b': ('b', 1),   # int8_t
    'B': ('B', 1),   # uint8_t
    'h': ('h', 2),   # int16_t
    'H': ('H', 2),   # uint16_t
    'i': ('i', 4),   # int32_t
    'I': ('I', 4),   # uint32_t
    'f': ('f', 4),   # float
    'q': ('4f', 16), # quaternion (4 floats)
}


# Variable type mappings by category
# Maps (category, var_id) to type specifier
VARIABLE_TYPES: Dict[Tuple[str, int], str] = {
    # Tracking variables
    ('T', 1): 'i',    # H_TICKS
    ('T', 2): 'i',    # E_TICKS
    ('T', 3): 'i',    # R_TICKS
    ('T', 4): 'B',    # TRACKING_ON
    ('T', 5): 'B',    # ROTATOR_ON
    ('T', 6): 'B',    # MOTOR_H_ON
    ('T', 7): 'B',    # MOTOR_E_ON
    ('T', 8): 'B',    # MOVING_H
    ('T', 9): 'B',    # MOVING_E
    ('T', 10): 'b',   # DIRECTION_H
    ('T', 11): 'b',   # DIRECTION_E
    ('T', 12): 'B',   # COLLISION
    ('T', 13): 'B',   # TRACKING_MODE
    ('T', 14): 'B',   # TRACKING_RATE
    ('T', 15): 'B',   # CUSTOM_RATE_TRACK
    ('T', 16): 'f',   # RA
    ('T', 17): 'f',   # DEC
    ('T', 18): 'f',   # TARGET_RA
    ('T', 19): 'f',   # TARGET_DEC
    ('T', 20): 'i',   # TARGET_H
    ('T', 21): 'i',   # TARGET_E
    ('T', 22): 'f',   # CUSTOM_RATE_RA
    ('T', 23): 'f',   # CUSTOM_RATE_DEC
    ('T', 24): 'i',   # GOTO_H_TICKS
    ('T', 25): 'i',   # GOTO_E_TICKS
    ('T', 26): 'i',   # GOTO_R_TICKS
    ('T', 27): 'I',   # MSECS
    ('T', 28): 'I',   # START_TIME
    ('T', 29): 'f',   # SOUTH_ANGLE
    ('T', 30): 'f',   # INITIAL_FIELD_ROT
    ('T', 31): 'q',   # ALIGNMENT_QUAT
    ('T', 32): 'q',   # INV_QUAT

    # Control variables
    ('C', 1): 'B',    # GOTO_SPEED_H
    ('C', 2): 'B',    # GOTO_SPEED_E
    ('C', 3): 'B',    # GUIDE_SPEED_H
    ('C', 4): 'B',    # GUIDE_SPEED_E
    ('C', 5): 'B',    # PARK_FLAG
    ('C', 6): 'B',    # CUSTOM_PARK_POS
    ('C', 7): 'B',    # LANGUAGE
    ('C', 8): 'B',    # CHOSEN_LOCATION
    ('C', 9): 'B',    # GOTO_ABORT
    ('C', 10): 'B',   # SPEED_MODE
    ('C', 11): 'B',   # DRIFT_MODE
    ('C', 12): 'B',   # CATALOG_CHOICE
    ('C', 13): 'B',   # COORD_CHOICE
    ('C', 14): 'B',   # ERROR_CODE
    ('C', 15): 'f',   # PARK_AZ
    ('C', 16): 'f',   # PARK_ALT
    ('C', 17): 'f',   # LONGITUDE
    ('C', 18): 'f',   # LATITUDE
    ('C', 19): 'b',   # TIMEZONE
    ('C', 20): 'H',   # DATE_YEAR
    ('C', 21): 'B',   # DATE_MONTH
    ('C', 22): 'B',   # DATE_DAY
    ('C', 23): 'B',   # TIME_HOUR
    ('C', 24): 'B',   # TIME_MINUTE
    ('C', 25): 'B',   # TIME_SECOND

    # Mount variables
    ('M', 1): 'B',    # TELESCOPE_MOUNTING
    ('M', 2): 'h',    # GUIDE_CORR_H
    ('M', 3): 'h',    # GUIDE_CORR_E
    ('M', 4): 'B',    # CABLE_TWIST_ALARM
    ('M', 5): 'b',    # AZ_NORM_COUNTER
    ('M', 6): 'B',    # MOTOR_DIR_H
    ('M', 7): 'B',    # MOTOR_DIR_E
    ('M', 8): 'i',    # TICKS_PER_ROUND_H
    ('M', 9): 'i',    # TICKS_PER_ROUND_E
    ('M', 10): 'i',   # WORMGEAR_TICKS_H
    ('M', 11): 'i',   # WORMGEAR_TICKS_E
    ('M', 12): 'i',   # FIELD_ROT_TICKS
    ('M', 13): 'i',   # FIELD_ROT_RANGE
    ('M', 14): 'f',   # FIELD_ROT_ANGLE
    ('M', 15): 'B',   # FIELD_ROT_DIRECTION
    ('M', 16): 'I',   # CLOCK_FREQ

    # Alignment variables
    ('A', 1): 'B',    # ALIGN_STATUS
    ('A', 2): 'f',    # START_SID_TIME
    ('A', 3): 'f',    # ALIGN_SID_TIME
    ('A', 4): 'i',    # STAR1_H_TICKS
    ('A', 5): 'i',    # STAR1_E_TICKS
    ('A', 6): 'i',    # STAR2_H_TICKS
    ('A', 7): 'i',    # STAR2_E_TICKS
    ('A', 8): 'i',    # STAR3_H_TICKS
    ('A', 9): 'i',    # STAR3_E_TICKS
    ('A', 10): 'f',   # STAR1_RA
    ('A', 11): 'f',   # STAR1_DEC
    ('A', 12): 'f',   # STAR2_RA
    ('A', 13): 'f',   # STAR2_DEC
    ('A', 14): 'f',   # STAR3_RA
    ('A', 15): 'f',   # STAR3_DEC

    # LX200 variables
    ('L', 1): 'B',    # GOTO_OBJECT
    ('L', 2): 'B',    # STOP_GOTO
    ('L', 3): 'B',    # SLEW_SPEED
    ('L', 4): 'B',    # SLEW_DIRECTION
    ('L', 5): 'B',    # SLEWING
    ('L', 6): 'B',    # GOTO_ACTIVE
    ('L', 7): 'B',    # SYNC
    ('L', 8): 'B',    # PARK_CMD
    ('L', 9): 'f',    # OBJECT_RA
    ('L', 10): 'f',   # OBJECT_DEC
    ('L', 11): 'f',   # SYNC_TARGET_RA
    ('L', 12): 'f',   # SYNC_TARGET_DEC

    # Motor variables
    ('O', 1): 'H',    # H_JERK
    ('O', 2): 'H',    # E_JERK
    ('O', 3): 'B',    # H_ACTIVE
    ('O', 4): 'B',    # E_ACTIVE
    ('O', 5): 'B',    # H_POSIT_ACTIVE
    ('O', 6): 'B',    # E_POSIT_ACTIVE
    ('O', 7): 'H',    # H_DENOMINATOR
    ('O', 8): 'H',    # E_DENOMINATOR
    ('O', 9): 'H',    # H_NUM_FINAL
    ('O', 10): 'H',   # E_NUM_FINAL
    ('O', 11): 'H',   # H_NUM_CURR
    ('O', 12): 'H',   # E_NUM_CURR
    ('O', 13): 'f',   # H_POSIT_INIT
    ('O', 14): 'f',   # E_POSIT_INIT
    ('O', 15): 'f',   # H_POSIT_FINAL
    ('O', 16): 'f',   # E_POSIT_FINAL

    # Display variables
    ('D', 1): 'B',    # DISPLAY_SCROLL
    ('D', 2): 'B',    # UPDATE_SCREEN
    ('D', 3): 'B',    # CURRENT_MENU_ITEM
    ('D', 4): 'B',    # OLD_MENU_ITEM
    ('D', 5): 'B',    # ARROW_ON_HANDPAD

    # Computed variables
    ('X', 1): 'f',    # CURRENT_ALT
    ('X', 2): 'f',    # CURRENT_AZ
    ('X', 3): 'H',    # FREE_MEM
}


# Query groups for efficient batched queries
QUERY_GROUPS: Dict[str, List[str]] = {
    # Position data - all coordinates in single query
    'position': ['T16', 'T17', 'X1', 'X2'],  # RA, Dec, Alt, Az (radians)

    # Target coordinates
    'target': ['T18', 'T19'],  # Target RA, Target Dec (radians)

    # Status flags
    'status': ['T4', 'L5', 'L6', 'C5'],  # Tracking, Slewing, GotoActive, Parked

    # Motion state
    'motion': ['T8', 'T9', 'T10', 'T11'],  # Moving H/E, Direction H/E

    # Site location
    'site': ['C17', 'C18', 'C19'],  # Longitude, Latitude, Timezone

    # Date and time
    'datetime': ['C20', 'C21', 'C22', 'C23', 'C24', 'C25'],  # Y/M/D H:M:S

    # Speeds configuration
    'speeds': ['C1', 'C2', 'C3', 'C4'],  # Goto H/E, Guide H/E speeds

    # Park status
    'park': ['C5', 'C6', 'C15', 'C16'],  # Flag, Custom, Az, Alt

    # Alignment quaternion
    'alignment': ['T31'],  # Alignment quaternion (4 floats)

    # Motor ticks per revolution
    'mount_config': ['M8', 'M9', 'M16'],  # Ticks H/E, Clock freq

    # Full position update for cache
    'cache_position': ['T16', 'T17', 'X1', 'X2', 'T4', 'L5', 'C5'],

    # Alignment stars
    'alignment_stars': ['A10', 'A11', 'A12', 'A13', 'A14', 'A15'],  # Star RA/Dec
}


# Protocol constants
BINARY_MAX_VARS_PER_COMMAND = 10
BINARY_MAX_CMDS_PER_COMMAND = 2
BINARY_RESPONSE_BUFFER_SIZE = 300
BINARY_MIN_VAR_ID = 1
BINARY_MAX_VAR_ID = 99
QUAT_SIZE = 4
QUAT_TOTAL_SIZE = 16  # 4 floats * 4 bytes


# ASCOM DriveRates enum for compatibility
class DriveRate(IntEnum):
    """ASCOM DriveRates enumeration."""
    SIDEREAL = 0
    LUNAR = 1
    SOLAR = 2
    KING = 3


# ASCOM EquatorialCoordinateType enum
class EquatorialCoordinateType(IntEnum):
    """ASCOM EquatorialCoordinateType enumeration."""
    OTHER = 0
    TOPOCENTRIC = 1
    J2000 = 2
    J2050 = 3
    B1950 = 4


# ASCOM AlignmentModes enum
class AlignmentMode(IntEnum):
    """ASCOM AlignmentModes enumeration."""
    ALT_AZ = 0
    POLAR = 1
    GERMAN_POLAR = 2


# ASCOM PierSide enum
class PierSide(IntEnum):
    """ASCOM PierSide enumeration."""
    UNKNOWN = -1
    EAST = 0
    WEST = 1


# ASCOM GuideDirections enum (maps to GuideDirection)
class GuideDirections(IntEnum):
    """ASCOM GuideDirections enumeration."""
    NORTH = 0
    SOUTH = 1
    EAST = 2
    WEST = 3
