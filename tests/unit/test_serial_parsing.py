"""
Unit tests for the TTS160 serial parsing module.

Tests binary format parsing, format string interpretation, and data unpacking
without requiring actual serial hardware.
"""

import pytest
import struct
from unittest.mock import Mock

# Import module under test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tts160_serial import (
    BinaryParser,
    BinaryFormat,
    BinaryFormatError,
    SerialManager,
    TTS160SerialError,
    ResponseError,
    V357Protocol,
)
from tts160_types import SetCommand, CmdResponseType, BinaryError


class TestBinaryParserFormatString:
    """Test format string parsing."""

    @pytest.mark.unit
    def test_parse_single_integer(self):
        """Parse single integer format."""
        struct_fmt, byte_size = BinaryParser.parse_format_string('i')

        # Parser normalizes to explicit count (1i)
        assert struct_fmt == '<1i'
        assert byte_size == 4

    @pytest.mark.unit
    def test_parse_multiple_integers(self):
        """Parse multiple integers format."""
        struct_fmt, byte_size = BinaryParser.parse_format_string('5i')

        assert struct_fmt == '<5i'
        assert byte_size == 20  # 5 * 4 bytes

    @pytest.mark.unit
    def test_parse_single_float(self):
        """Parse single float format."""
        struct_fmt, byte_size = BinaryParser.parse_format_string('f')

        # Parser normalizes to explicit count (1f)
        assert struct_fmt == '<1f'
        assert byte_size == 4

    @pytest.mark.unit
    def test_parse_mixed_types(self):
        """Parse mixed integer and float format."""
        struct_fmt, byte_size = BinaryParser.parse_format_string('5i2f')

        assert struct_fmt == '<5i2f'
        assert byte_size == 28  # (5*4) + (2*4)

    @pytest.mark.unit
    def test_parse_short_integers(self):
        """Parse 16-bit integer format."""
        struct_fmt, byte_size = BinaryParser.parse_format_string('3h')

        assert struct_fmt == '<3h'
        assert byte_size == 6  # 3 * 2 bytes

    @pytest.mark.unit
    def test_parse_bytes(self):
        """Parse 8-bit integer format."""
        struct_fmt, byte_size = BinaryParser.parse_format_string('4b')

        assert struct_fmt == '<4b'
        assert byte_size == 4  # 4 * 1 byte

    @pytest.mark.unit
    def test_parse_unsigned_types(self):
        """Parse unsigned integer formats."""
        # Unsigned 32-bit
        struct_fmt, byte_size = BinaryParser.parse_format_string('2I')
        assert struct_fmt == '<2I'
        assert byte_size == 8

        # Unsigned 16-bit
        struct_fmt, byte_size = BinaryParser.parse_format_string('2H')
        assert struct_fmt == '<2H'
        assert byte_size == 4

        # Unsigned 8-bit
        struct_fmt, byte_size = BinaryParser.parse_format_string('2B')
        assert struct_fmt == '<2B'
        assert byte_size == 2

    @pytest.mark.unit
    def test_parse_complex_format(self):
        """Parse complex mixed format string."""
        # 3 ints, 2 floats, 1 short, 4 bytes
        struct_fmt, byte_size = BinaryParser.parse_format_string('3i2fh4b')

        # Parser normalizes 'h' to '1h'
        assert struct_fmt == '<3i2f1h4b'
        expected_size = (3*4) + (2*4) + (1*2) + (4*1)  # 26 bytes
        assert byte_size == expected_size

    @pytest.mark.unit
    def test_parse_empty_string_raises(self):
        """Empty format string should raise error."""
        with pytest.raises(BinaryFormatError):
            BinaryParser.parse_format_string('')

    @pytest.mark.unit
    def test_parse_invalid_type_raises(self):
        """Invalid type character should raise error."""
        with pytest.raises(BinaryFormatError):
            BinaryParser.parse_format_string('5x')  # 'x' is not valid

    @pytest.mark.unit
    def test_little_endian_prefix(self):
        """Format should use little-endian byte order."""
        struct_fmt, _ = BinaryParser.parse_format_string('i')
        assert struct_fmt.startswith('<')


class TestBinaryParserCountValues:
    """Test format value counting."""

    @pytest.mark.unit
    def test_count_single_value(self):
        """Count single value format."""
        count = BinaryParser.count_format_values('i')
        assert count == 1

    @pytest.mark.unit
    def test_count_multiple_same_type(self):
        """Count multiple values of same type."""
        count = BinaryParser.count_format_values('5i')
        assert count == 5

    @pytest.mark.unit
    def test_count_mixed_types(self):
        """Count mixed type values."""
        count = BinaryParser.count_format_values('3i2f')
        assert count == 5

    @pytest.mark.unit
    def test_count_complex_format(self):
        """Count complex format values."""
        count = BinaryParser.count_format_values('2i3f4h')
        assert count == 9


class TestBinaryFormatCreation:
    """Test BinaryFormat creation and validation."""

    @pytest.mark.unit
    def test_create_simple_format(self):
        """Create simple binary format."""
        fmt = BinaryParser.create_format('test', '3i')

        assert fmt.name == 'test'
        assert fmt.format_string == '3i'
        assert fmt.byte_size == 12

    @pytest.mark.unit
    def test_create_format_with_field_names(self):
        """Create format with field names."""
        fmt = BinaryParser.create_format(
            'test',
            '3i',
            field_names=['a', 'b', 'c']
        )

        assert fmt.field_names == ['a', 'b', 'c']

    @pytest.mark.unit
    def test_create_format_mismatched_names_raises(self):
        """Mismatched field name count should raise error."""
        with pytest.raises(BinaryFormatError):
            BinaryParser.create_format(
                'test',
                '3i',
                field_names=['a', 'b']  # Only 2 names for 3 values
            )

    @pytest.mark.unit
    def test_binary_format_immutable(self):
        """BinaryFormat should be immutable (frozen dataclass)."""
        fmt = BinaryParser.create_format('test', '2i')

        with pytest.raises(Exception):  # FrozenInstanceError
            fmt.name = 'changed'


class TestBinaryParserUnpack:
    """Test binary data unpacking."""

    @pytest.mark.unit
    def test_unpack_integers(self, sample_binary_data):
        """Unpack integer data correctly."""
        fmt = BinaryParser.create_format('test', '3i')
        result = BinaryParser.unpack_data(fmt, sample_binary_data['integers'])

        assert result == [1, 2, 3]

    @pytest.mark.unit
    def test_unpack_floats(self, sample_binary_data):
        """Unpack float data correctly."""
        fmt = BinaryParser.create_format('test', '2f')
        result = BinaryParser.unpack_data(fmt, sample_binary_data['floats'])

        assert len(result) == 2
        assert abs(result[0] - 1.5) < 0.0001
        assert abs(result[1] - 2.5) < 0.0001

    @pytest.mark.unit
    def test_unpack_mixed_types(self, sample_binary_data):
        """Unpack mixed type data correctly."""
        fmt = BinaryParser.create_format('test', '2if')
        result = BinaryParser.unpack_data(fmt, sample_binary_data['mixed'])

        assert result[0] == 10
        assert result[1] == 20
        assert abs(result[2] - 3.14159) < 0.0001

    @pytest.mark.unit
    def test_unpack_with_field_names(self, sample_binary_data):
        """Unpack with field names returns dictionary."""
        fmt = BinaryParser.create_format(
            'test',
            '3i',
            field_names=['first', 'second', 'third']
        )
        result = BinaryParser.unpack_data(fmt, sample_binary_data['integers'])

        assert isinstance(result, dict)
        assert result['first'] == 1
        assert result['second'] == 2
        assert result['third'] == 3

    @pytest.mark.unit
    def test_unpack_size_mismatch_raises(self):
        """Data size mismatch should raise error."""
        fmt = BinaryParser.create_format('test', '3i')
        wrong_size_data = struct.pack('<2i', 1, 2)  # Only 2 ints, need 3

        with pytest.raises(BinaryFormatError):
            BinaryParser.unpack_data(fmt, wrong_size_data)

    @pytest.mark.unit
    def test_unpack_case2_format(self, sample_binary_data):
        """Unpack case 2 format data (real world example)."""
        fmt = BinaryParser.create_format(
            'case2',
            '5i2f',
            field_names=[
                'goto_speed_h', 'goto_speed_e', 'guide_speed_h',
                'guide_speed_e', 'park_flag', 'park_az', 'park_alt'
            ]
        )
        result = BinaryParser.unpack_data(fmt, sample_binary_data['case2'])

        assert isinstance(result, dict)
        assert result['goto_speed_h'] == 100
        assert result['goto_speed_e'] == 200
        assert result['park_flag'] == 1
        assert abs(result['park_az'] - 180.0) < 0.0001
        assert abs(result['park_alt'] - 45.0) < 0.0001


class TestSerialManagerFormatRegistry:
    """Test SerialManager binary format registry."""

    @pytest.mark.unit
    def test_default_formats_registered(self, mock_logger):
        """Default formats should be registered on init."""
        manager = SerialManager(mock_logger)

        # Check some default formats exist
        assert '0' in manager._binary_formats
        assert '2' in manager._binary_formats

    @pytest.mark.unit
    def test_register_custom_format(self, mock_logger):
        """Custom formats can be registered."""
        manager = SerialManager(mock_logger)
        manager.register_binary_format('custom', '4i2f', ['a', 'b', 'c', 'd', 'e', 'f'])

        assert 'custom' in manager._binary_formats
        assert manager._binary_formats['custom'].byte_size == 24

    @pytest.mark.unit
    def test_register_format_empty_name_raises(self, mock_logger):
        """Empty format name should raise error."""
        manager = SerialManager(mock_logger)

        with pytest.raises(ValueError):
            manager.register_binary_format('', '3i')

    @pytest.mark.unit
    def test_register_format_empty_string_raises(self, mock_logger):
        """Empty format string should raise error."""
        manager = SerialManager(mock_logger)

        with pytest.raises(ValueError):
            manager.register_binary_format('test', '')

    @pytest.mark.unit
    def test_register_overwrites_existing(self, mock_logger):
        """Re-registering format should overwrite."""
        manager = SerialManager(mock_logger)

        manager.register_binary_format('test', '2i')
        assert manager._binary_formats['test'].byte_size == 8

        manager.register_binary_format('test', '4i')
        assert manager._binary_formats['test'].byte_size == 16


class TestSerialManagerValidation:
    """Test SerialManager command validation."""

    @pytest.mark.unit
    def test_command_must_start_with_colon(self, mock_serial_manager):
        """Commands must start with colon."""
        with pytest.raises(ValueError, match="start with ':'"):
            mock_serial_manager.send_command('GR#')

    @pytest.mark.unit
    def test_command_must_end_with_hash(self, mock_serial_manager):
        """Commands must end with hash."""
        with pytest.raises(ValueError, match="end with '#'"):
            mock_serial_manager.send_command(':GR')

    @pytest.mark.unit
    def test_empty_command_raises(self, mock_serial_manager):
        """Empty command should raise error."""
        with pytest.raises(ValueError):
            mock_serial_manager.send_command('')

    @pytest.mark.unit
    def test_non_string_command_raises(self, mock_serial_manager):
        """Non-string command should raise error."""
        with pytest.raises(ValueError):
            mock_serial_manager.send_command(123)


class TestTypeMap:
    """Test BinaryParser TYPE_MAP completeness."""

    @pytest.mark.unit
    def test_type_map_contains_integers(self):
        """TYPE_MAP should contain integer types."""
        assert 'i' in BinaryParser.TYPE_MAP  # int32
        assert 'h' in BinaryParser.TYPE_MAP  # int16
        assert 'b' in BinaryParser.TYPE_MAP  # int8

    @pytest.mark.unit
    def test_type_map_contains_unsigned(self):
        """TYPE_MAP should contain unsigned types."""
        assert 'I' in BinaryParser.TYPE_MAP  # uint32
        assert 'H' in BinaryParser.TYPE_MAP  # uint16
        assert 'B' in BinaryParser.TYPE_MAP  # uint8

    @pytest.mark.unit
    def test_type_map_contains_float(self):
        """TYPE_MAP should contain float type."""
        assert 'f' in BinaryParser.TYPE_MAP

    @pytest.mark.unit
    def test_type_map_sizes_correct(self):
        """TYPE_MAP sizes should be correct."""
        assert BinaryParser.TYPE_MAP['i'][1] == 4  # int32 = 4 bytes
        assert BinaryParser.TYPE_MAP['h'][1] == 2  # int16 = 2 bytes
        assert BinaryParser.TYPE_MAP['b'][1] == 1  # int8 = 1 byte
        assert BinaryParser.TYPE_MAP['f'][1] == 4  # float32 = 4 bytes


class TestV357ProtocolCategoryValidation:
    """Regression tests for the build_query category allow-list (C1 fix).

    The allow-list at tts160_serial.py:345 must equal the 8 valid V357Category
    values (T,C,M,A,L,O,D,X). A prior typo ('TCMALODK') dropped the real X
    (COMPUTED = real-time alt/az) and admitted a bogus 'K', which broke every
    X-category query and the position/cache_position groups on the alt-az mount.
    """

    @pytest.mark.unit
    def test_x_category_variable_accepted(self):
        """An X-category variable (COMPUTED alt/az) must validate, not raise."""
        assert V357Protocol.build_query(['X1']) == ':*!G X1#'

    @pytest.mark.unit
    def test_position_group_builds_without_raising(self):
        """The position group ['T16','T17','X1','X2'] must build (includes X)."""
        assert (
            V357Protocol.build_query(['T16', 'T17', 'X1', 'X2'])
            == ':*!G T16,T17,X1,X2#'
        )

    @pytest.mark.unit
    def test_bogus_k_category_rejected(self):
        """The bogus 'K' category (from the old typo) must be rejected."""
        with pytest.raises(ValueError, match="Invalid category"):
            V357Protocol.build_query(['K5'])


class TestV357ProtocolSetHeadEncoding:
    """Regression tests for the binary-SET command-head encoding (X1 fix).

    The firmware (central/binary.c:517-523) reads ONE base-36 char per command
    in a loop until ';' ('0'-'9' -> 0-9, 'A'-'Z' -> 10-35). The driver formerly
    emitted the head as two hex chars (f"{cmd_id:02X}"), so e.g. SET_LOCATION
    (0x11) went out as "11" and the firmware mis-parsed it as TWO separate
    commands [1, 1]. The head must be a SINGLE base-36 char (0x11 -> 'H').
    Frames below carry the Arc-7 counted-length byte after ';'.
    """

    @pytest.mark.unit
    def test_set_location_head_is_single_base36_char(self):
        """SET_LOCATION (0x11) frame head must be the single char 'H', not '11'."""
        payload = bytes(range(22))  # a 22-byte location payload, all distinct
        frame = V357Protocol.build_set_command_bytes(SetCommand.SET_LOCATION, payload)

        # Exact frame: ':*!S H;' + <LEN=22> + payload + '#'
        assert frame == b':*!S H;' + bytes([22]) + payload + b'#'
        # Explicitly reject the old two-hex-char head.
        assert b':*!S 11;' not in frame

    @pytest.mark.unit
    def test_single_digit_id_head(self):
        """A single-digit id (GUIDE = 0x05) encodes as '5' (not '05')."""
        payload = struct.pack('<BH', 1, 35)  # direction=1, duration_ms=35
        frame = V357Protocol.build_set_command_bytes(SetCommand.GUIDE, payload)

        assert frame == b':*!S 5;' + bytes([len(payload)]) + payload + b'#'
        assert b':*!S 05;' not in frame

    @pytest.mark.unit
    def test_encode_set_head_matches_firmware_decode(self):
        """The head encoder matches the firmware base-36 decode across the range."""
        # 0-9 -> '0'-'9'; 10-35 -> 'A'-'Z'
        assert V357Protocol._encode_set_head(0) == '0'
        assert V357Protocol._encode_set_head(9) == '9'
        assert V357Protocol._encode_set_head(10) == 'A'
        assert V357Protocol._encode_set_head(SetCommand.SET_TRACK_RATE) == 'D'  # 0x0D
        assert V357Protocol._encode_set_head(SetCommand.SET_LOCATION) == 'H'   # 0x11
        assert V357Protocol._encode_set_head(SetCommand.PERFORM_ALIGNMENT) == 'J'  # 0x13
        assert V357Protocol._encode_set_head(35) == 'Z'

    @pytest.mark.unit
    def test_out_of_range_head_raises(self):
        """An id outside the base-36 head range (0-35) must raise, not truncate."""
        with pytest.raises(ValueError):
            V357Protocol._encode_set_head(36)
        with pytest.raises(ValueError):
            V357Protocol._encode_set_head(-1)

    @pytest.mark.unit
    def test_build_set_command_str_head(self):
        """The str builder (build_set_command) also emits the single-char head."""
        payload = bytes(range(22))
        frame = V357Protocol.build_set_command(SetCommand.SET_LOCATION, payload)
        assert frame == b':*!S H;' + bytes([22]) + payload + b'#'


class TestV357ProtocolParseSetResponse:
    """Regression tests for the binary-SET RESPONSE parser (G1 fix).

    The firmware packs a SET response as [count] then, per response,
    [type][length][data...] (pack_cmd_response_data, central/binary.c:2441-2480):
    NONE(0)=len0, INT(1)=len1 int8, FLOAT(2)=len4, STRING(3)=strlen ascii,
    ERROR(4)=len4 int32. The old parser read NO length byte and unpacked a fixed
    4-byte int for INT, so the real success frame (01 01 01 00) parsed to [] and
    EVERY SET (align/sync/GPS push) read as failed. These lock the wire format:
    an INT status of 0 == success; a non-empty ERROR/reject list == failure.
    """

    @pytest.mark.unit
    def test_success_frame_parses_to_int_zero(self):
        """The real SET success frame 01 01 01 00 -> [(INT, 0)] (was [])."""
        result = V357Protocol.parse_set_response(bytes([0x01, 0x01, 0x01, 0x00]))
        assert result == [(CmdResponseType.INT, 0)]
        # The success check every consumer uses must now pass.
        assert result[0][1] == 0

    @pytest.mark.unit
    def test_int_reject_code_detected_as_failure(self):
        """An INT reject (code 2 / code 5) is non-empty but its VALUE != 0."""
        for code in (2, 5):
            frame = bytes([0x01, CmdResponseType.INT, 0x01, code])
            result = V357Protocol.parse_set_response(frame)
            assert result == [(CmdResponseType.INT, code)]
            # Truthy list, but the value-based check correctly reports failure.
            assert bool(result) is True
            assert (result[0][1] == 0) is False

    @pytest.mark.unit
    def test_error_response_detected_as_failure(self):
        """An ERROR response (int32) is decoded and its value is not 0."""
        # ERROR type, length 4, int32 = -1 (PARSE_FAILED)
        frame = bytes([0x01, CmdResponseType.ERROR, 0x04]) + struct.pack('<i', -1)
        result = V357Protocol.parse_set_response(frame)
        assert len(result) == 1
        assert result[0][0] == CmdResponseType.ERROR
        assert result[0][1] == BinaryError.PARSE_FAILED
        assert (result[0][1] == 0) is False

    @pytest.mark.unit
    def test_multi_response_frame(self):
        """A multi-response frame decodes each [type][length][data] in order."""
        frame = (
            bytes([0x03])                                   # count = 3
            + bytes([CmdResponseType.INT, 0x01, 0x00])      # INT 0
            + bytes([CmdResponseType.FLOAT, 0x04]) + struct.pack('<f', 1.5)
            + bytes([CmdResponseType.NONE, 0x00])           # NONE
        )
        result = V357Protocol.parse_set_response(frame)
        assert len(result) == 3
        assert result[0] == (CmdResponseType.INT, 0)
        assert result[1][0] == CmdResponseType.FLOAT
        assert abs(result[1][1] - 1.5) < 1e-6
        assert result[2] == (CmdResponseType.NONE, None)

    @pytest.mark.unit
    def test_string_response(self):
        """A STRING response (length N ascii) decodes to the text."""
        msg = b'OK'
        frame = bytes([0x01, CmdResponseType.STRING, len(msg)]) + msg
        result = V357Protocol.parse_set_response(frame)
        assert result == [(CmdResponseType.STRING, 'OK')]

    @pytest.mark.unit
    def test_truncated_frame_logs_and_stops(self, caplog):
        """A truncated frame is logged and yields only what was fully decoded."""
        # Header claims 2 responses; the second INT is missing its data byte.
        frame = bytes([0x02, CmdResponseType.INT, 0x01, 0x00,
                       CmdResponseType.INT, 0x01])  # last data byte missing
        import logging
        with caplog.at_level(logging.WARNING):
            result = V357Protocol.parse_set_response(frame)
        # First response decoded; truncated second dropped (not a silent []).
        assert result == [(CmdResponseType.INT, 0)]
        assert any('truncated' in rec.message.lower() for rec in caplog.records)

    @pytest.mark.unit
    def test_empty_frame_logs_warning(self, caplog):
        """An empty frame returns [] but logs (never a silent success/failure)."""
        import logging
        with caplog.at_level(logging.WARNING):
            result = V357Protocol.parse_set_response(b'')
        assert result == []
        assert any('empty' in rec.message.lower() for rec in caplog.records)
