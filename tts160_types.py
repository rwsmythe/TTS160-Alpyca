# File: tts160_types.py
"""Minimal type definitions for TTS160 driver."""

from enum import IntEnum
#from dataclasses import dataclass


class CommandType(IntEnum):
    """Serial command response types."""
    BLIND = 0    # No response expected
    BOOL = 1     # Single character boolean response  
    STRING = 2   # String response terminated with '#'
    AUTO = 3     # Auto-detect text vs binary response