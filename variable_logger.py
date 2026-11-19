"""Read firmware variables into timestamped CSV rows without changing mount state."""

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import re
from typing import Any

from tts160_types import BINARY_MAX_VARS_PER_COMMAND


DEFAULT_VARIABLES: tuple[str, ...] = (
    "T1", "T2", "T3", "T4", "T6", "T7", "T8", "T9", "T12", "T27",
    "M5", "C5", "C14", "L2", "L5", "L6", "O3", "O4", "O11", "O12",
)
MAX_VARIABLES = 20
MIN_INTERVAL_S = 1.0


class VariableListError(ValueError):
    """The configured variable list cannot safely be queried."""


def validate_variables(variables: Sequence[str]) -> tuple[str, ...]:
    """Validate identifiers, uniqueness, length and decoder exclusions."""
    if isinstance(variables, (str, bytes)) or not isinstance(variables, Sequence):
        raise VariableListError("variables must be a sequence of identifiers")
    if not 1 <= len(variables) <= MAX_VARIABLES:
        raise VariableListError(f"variables must contain 1 to {MAX_VARIABLES} identifiers")
    seen: set[str] = set()
    for variable in variables:
        if not isinstance(variable, str) or re.fullmatch(r"[TCMALODX][1-9][0-9]?", variable) is None:
            raise VariableListError(f"invalid variable: {variable!r}")
        if variable in ("T31", "T32"):
            raise VariableListError(f"unsupported quaternion variable: {variable}")
        if variable in seen:
            raise VariableListError(f"duplicate variable: {variable}")
        seen.add(variable)
    return tuple(variables)


def chunk_variables(variables: Sequence[str], size: int = BINARY_MAX_VARS_PER_COMMAND) -> list[list[str]]:
    """Split identifiers into ordered query-sized lists."""
    if size < 1:
        raise ValueError("chunk size must be positive")
    return [list(variables[i:i + size]) for i in range(0, len(variables), size)]


def header_row(variables: Sequence[str]) -> list[str]:
    """Return the fixed-width CSV header."""
    return ["utc", "elapsed_s", *variables, "error"]


def format_row(utc: datetime, elapsed_s: float, variables: Sequence[str],
               values: Mapping[str, Any], error: str = "") -> list[str]:
    """Format values for csv.writer, retaining missing columns and unusual values."""
    row = [utc.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
           f"{elapsed_s:.3f}"]
    for variable in variables:
        value = values.get(variable)
        if value is None:
            row.append("")
        elif isinstance(value, bool):
            row.append(str(int(value)))
        elif isinstance(value, float):
            row.append(repr(value))
        else:
            row.append(str(value) if isinstance(value, (str, int)) else repr(value))
    return [*row, error]
