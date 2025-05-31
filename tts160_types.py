# File: tts160_types.py
"""Minimal type definitions for TTS160 driver."""

from enum import IntEnum
#from dataclasses import dataclass


class CommandType(IntEnum):
    """Serial command response types."""
    BLIND = 0    # No response expected
    BOOL = 1     # Single character boolean response  
    STRING = 2   # String response terminated with '#'


#class Rate:
#    """Represents a rate range for telescope movement."""
#    def __init__(self, minimum: float, maximum: float):
#        self.Minimum = float(minimum)
#        self.Maximum = float(maximum)
#    
#    def __repr__(self):
#        return f"Rate({self.Minimum}, {self.Maximum})"


#@dataclass
#class EquatorialCoordinates:
#    """Equatorial coordinate pair."""
#    right_ascension: float  # hours
#    declination: float      # degrees


#@dataclass
#class HorizontalCoordinates:
#    """Horizontal coordinate pair."""
#    azimuth: float     # degrees
#    altitude: float    # degrees