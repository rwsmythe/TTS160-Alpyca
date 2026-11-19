"""Read firmware variables into timestamped CSV rows without changing mount state.

The [debug_logger] directory is relative to the driver process's working
directory and must already exist. When run from source, this is the repo root,
where TTS160config.toml is read.
T31 and T32 are rejected because their quaternion decoding is unsupported.
C17 and C18 (site longitude and latitude) are rejected and must never be logged.
"""

from collections.abc import Callable, Mapping, Sequence
import csv
from datetime import datetime, timezone
import logging
import math
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Optional

from tts160_types import BINARY_MAX_VARS_PER_COMMAND


DEFAULT_VARIABLES: tuple[str, ...] = (
    "T1", "T2", "T3", "T4", "T6", "T7", "T8", "T9", "T12", "T27",
    "M5", "C5", "C14", "L2", "L5", "L6", "O3", "O4", "O11", "O12",
)
MAX_VARIABLES = 20
MIN_INTERVAL_S = 1.0
BACKOFF_S = 30.0
FAILURES_BEFORE_BACKOFF = 2


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
        if variable in ("C17", "C18"):
            raise VariableListError(f"site coordinate variable must never be logged: {variable}")
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


class VariableLogger:
    """Poll an injected read function on a daemon thread and flush each CSV row."""

    def __init__(self, query: Callable[[list[str]], Mapping[str, Any]], variables: Sequence[str],
                 interval_s: float, directory: str, logger: logging.Logger,
                 clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 wait: Optional[Callable[[float], bool]] = None):
        self._query = query
        self._variables = variables
        self._interval_s = interval_s
        self._directory = directory
        self._logger = logger
        self._clock = clock
        self._utcnow = utcnow
        self._stop = threading.Event()
        self._wait = wait if wait is not None else self._stop.wait
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._file = None
        self._writer = None
        self._path: Optional[str] = None
        self._running = False
        self._started_at = 0.0
        self._next_due = 0.0
        self._after_backoff = False
        self._consecutive_failures = 0

    @property
    def path(self) -> Optional[str]:
        """The current or most recent CSV path, if opened successfully."""
        return self._path

    @property
    def running(self) -> bool:
        """Whether the logger is accepting polls (False immediately after stop)."""
        return self._running

    def start(self) -> bool:
        """Validate settings and open the CSV before starting a polling thread."""
        if self._thread is not None and self._thread.is_alive():
            return self._running
        with self._lock:
            try:
                self._variables = validate_variables(self._variables)
                if (isinstance(self._interval_s, bool) or not isinstance(self._interval_s, (float, int))
                        or not math.isfinite(self._interval_s) or self._interval_s < MIN_INTERVAL_S):
                    raise ValueError(f"interval_s must be finite and at least {MIN_INTERVAL_S}")
                stamp = self._utcnow().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                directory = os.path.abspath(self._directory)
                path = Path(directory) / f"variables-{stamp}.csv"
                try:
                    self._file = path.open("x", newline="", encoding="utf-8")
                except FileNotFoundError as ex:
                    raise OSError(f"Cannot open CSV in {directory}; directory must already exist: {ex}") from ex
                except OSError as ex:
                    raise OSError(f"Cannot open CSV {path}: {ex}") from ex
                self._writer = csv.writer(self._file)
                self._writer.writerow(header_row(self._variables))
                self._file.flush()
                self._path = str(path)
                self._started_at = self._clock()
                self._next_due = self._started_at
                self._after_backoff = False
                self._stop.clear()
                self._running = True
                self._thread = threading.Thread(target=self._run, name="variable-logger", daemon=True)
                self._thread.start()
                self._logger.info("Variable logger writing %s", self._path)
                return True
            except Exception as ex:
                self._running = False
                self._stop.set()
                self._close_file()
                self._logger.warning("Variable logger could not start: %s", ex)
                return False

    def stop(self, timeout: float = 2.0) -> None:
        """Stop promptly; a blocked query's thread closes its own file on return."""
        self._stop.set()
        self._running = False
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        if thread is None or not thread.is_alive():
            with self._lock:
                self._close_file()

    def poll_once(self) -> None:
        """Read each chunk once when due, preserving partial values on a failure."""
        with self._lock:
            if not self._running or self._stop.is_set() or self._clock() < self._next_due:
                return
            poll_started = self._clock()
            utc = self._utcnow()
            elapsed_s = poll_started - self._started_at
            values: dict[str, Any] = {}
            error = ""
            for chunk in chunk_variables(self._variables):
                if self._stop.is_set():
                    return
                try:
                    values.update(self._query(chunk))
                except Exception as ex:
                    error = f"{type(ex).__name__}: {ex}"
                    break
            if self._stop.is_set():
                return
            try:
                self._writer.writerow(format_row(utc, elapsed_s, self._variables, values, error))
                self._file.flush()
            except Exception as ex:
                self._running = False
                self._stop.set()
                self._logger.error("Variable logger write failed: %s", ex)
                self._close_file()
                return
            now = self._clock()
            if error:
                self._consecutive_failures += 1
            else:
                self._consecutive_failures = 0
            if self._consecutive_failures >= FAILURES_BEFORE_BACKOFF:
                self._next_due = now + BACKOFF_S
                self._after_backoff = True
            else:
                slot = math.floor((now - self._started_at) / self._interval_s) + 1
                # Subtraction at a large clock origin can round an exact slot down.
                if self._started_at + slot * self._interval_s <= now:
                    slot += 1
                if self._after_backoff:
                    earliest_slot = math.ceil((poll_started + self._interval_s - self._started_at) / self._interval_s)
                    slot = max(slot, earliest_slot)
                    self._after_backoff = False
                self._next_due = self._started_at + slot * self._interval_s

    def _run(self) -> None:
        """Sleep to the next scheduled poll without replaying missed slots."""
        try:
            while not self._stop.is_set():
                delay = max(0.0, self._next_due - self._clock())
                if self._wait(delay) or self._stop.is_set():
                    break
                self.poll_once()
        finally:
            self._running = False
            with self._lock:
                self._close_file()

    def _close_file(self) -> None:
        """Close once, containing cleanup errors so shutdown remains best effort."""
        if self._file is not None and not self._file.closed:
            try:
                self._file.close()
            except OSError:
                pass
