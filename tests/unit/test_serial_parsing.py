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
)


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
