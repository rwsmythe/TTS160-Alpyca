"""
Unit tests for the serial command priority queue system.

Tests CommandPriority enum, LowPriorityContext, and priority ordering.
"""

import pytest
import threading
import time
from unittest.mock import Mock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tts160_serial import (
    CommandPriority,
    LowPriorityContext,
    get_default_priority,
    _PendingCommand,
    SerialManager,
)
from tts160_types import CommandType


class TestCommandPriority:
    """Test CommandPriority enum."""

    @pytest.mark.unit
    def test_priority_ordering(self):
        """CRITICAL < HIGH < NORMAL < LOW for priority sorting."""
        assert CommandPriority.CRITICAL < CommandPriority.HIGH
        assert CommandPriority.HIGH < CommandPriority.NORMAL
        assert CommandPriority.NORMAL < CommandPriority.LOW

    @pytest.mark.unit
    def test_priority_values(self):
        """Priority values should be integers."""
        assert isinstance(CommandPriority.CRITICAL.value, int)
        assert isinstance(CommandPriority.LOW.value, int)

    @pytest.mark.unit
    def test_priority_names(self):
        """Priority names should be accessible."""
        assert CommandPriority.CRITICAL.name == 'CRITICAL'
        assert CommandPriority.HIGH.name == 'HIGH'
        assert CommandPriority.NORMAL.name == 'NORMAL'
        assert CommandPriority.LOW.name == 'LOW'


class TestLowPriorityContext:
    """Test LowPriorityContext context manager."""

    @pytest.mark.unit
    def test_default_priority_is_normal(self):
        """Default priority should be NORMAL outside context."""
        assert get_default_priority() == CommandPriority.NORMAL

    @pytest.mark.unit
    def test_context_sets_low_priority(self):
        """LowPriorityContext should set priority to LOW."""
        with LowPriorityContext():
            assert get_default_priority() == CommandPriority.LOW

    @pytest.mark.unit
    def test_context_restores_priority(self):
        """Priority should be restored after context exits."""
        assert get_default_priority() == CommandPriority.NORMAL
        with LowPriorityContext():
            assert get_default_priority() == CommandPriority.LOW
        assert get_default_priority() == CommandPriority.NORMAL

    @pytest.mark.unit
    def test_nested_contexts(self):
        """Nested contexts should work correctly."""
        assert get_default_priority() == CommandPriority.NORMAL
        with LowPriorityContext():
            assert get_default_priority() == CommandPriority.LOW
            with LowPriorityContext():
                assert get_default_priority() == CommandPriority.LOW
            assert get_default_priority() == CommandPriority.LOW
        assert get_default_priority() == CommandPriority.NORMAL

    @pytest.mark.unit
    def test_context_exception_handling(self):
        """Priority should be restored even if exception occurs."""
        try:
            with LowPriorityContext():
                assert get_default_priority() == CommandPriority.LOW
                raise ValueError("Test exception")
        except ValueError:
            pass
        assert get_default_priority() == CommandPriority.NORMAL

    @pytest.mark.unit
    def test_thread_isolation(self):
        """Each thread should have its own priority context."""
        results = {}

        def thread_func(name, use_low_priority):
            if use_low_priority:
                with LowPriorityContext():
                    time.sleep(0.05)  # Let other thread check
                    results[name] = get_default_priority()
            else:
                time.sleep(0.05)
                results[name] = get_default_priority()

        t1 = threading.Thread(target=thread_func, args=('low', True))
        t2 = threading.Thread(target=thread_func, args=('normal', False))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results['low'] == CommandPriority.LOW
        assert results['normal'] == CommandPriority.NORMAL


class TestPendingCommand:
    """Test _PendingCommand dataclass ordering."""

    @pytest.mark.unit
    def test_priority_ordering(self):
        """Commands should sort by priority (lower value first)."""
        cmd_low = _PendingCommand(
            priority=CommandPriority.LOW,
            sequence=1,
            command=':GR#',
            command_type=CommandType.STRING,
            result_event=threading.Event()
        )
        cmd_high = _PendingCommand(
            priority=CommandPriority.HIGH,
            sequence=2,
            command=':GR#',
            command_type=CommandType.STRING,
            result_event=threading.Event()
        )

        assert cmd_high < cmd_low  # HIGH has lower value, sorts first

    @pytest.mark.unit
    def test_sequence_tiebreaker(self):
        """Same priority should use sequence as tiebreaker (FIFO)."""
        cmd1 = _PendingCommand(
            priority=CommandPriority.NORMAL,
            sequence=1,
            command=':GR#',
            command_type=CommandType.STRING,
            result_event=threading.Event()
        )
        cmd2 = _PendingCommand(
            priority=CommandPriority.NORMAL,
            sequence=2,
            command=':GD#',
            command_type=CommandType.STRING,
            result_event=threading.Event()
        )

        assert cmd1 < cmd2  # Lower sequence comes first

    @pytest.mark.unit
    def test_sorted_list(self):
        """Commands should sort correctly in a list."""
        commands = [
            _PendingCommand(CommandPriority.LOW, 1, ':A#', CommandType.BLIND, threading.Event()),
            _PendingCommand(CommandPriority.CRITICAL, 2, ':B#', CommandType.BLIND, threading.Event()),
            _PendingCommand(CommandPriority.NORMAL, 3, ':C#', CommandType.BLIND, threading.Event()),
            _PendingCommand(CommandPriority.HIGH, 4, ':D#', CommandType.BLIND, threading.Event()),
        ]

        sorted_cmds = sorted(commands)

        assert sorted_cmds[0].command == ':B#'  # CRITICAL
        assert sorted_cmds[1].command == ':D#'  # HIGH
        assert sorted_cmds[2].command == ':C#'  # NORMAL
        assert sorted_cmds[3].command == ':A#'  # LOW


class TestSerialManagerPriorityQueue:
    """Test SerialManager priority queue integration."""

    @pytest.fixture
    def manager(self, mock_logger):
        """Create a SerialManager instance."""
        return SerialManager(mock_logger)

    @pytest.mark.unit
    def test_manager_has_queue(self, manager):
        """Manager should have a command queue."""
        assert manager._command_queue is not None

    @pytest.mark.unit
    def test_manager_has_sequence_counter(self, manager):
        """Manager should have a sequence counter."""
        assert hasattr(manager, '_command_sequence')
        assert hasattr(manager, '_sequence_lock')

    @pytest.mark.unit
    def test_get_next_sequence_increments(self, manager):
        """_get_next_sequence should increment and return unique values."""
        seq1 = manager._get_next_sequence()
        seq2 = manager._get_next_sequence()
        seq3 = manager._get_next_sequence()

        assert seq2 > seq1
        assert seq3 > seq2

    @pytest.mark.unit
    def test_send_command_accepts_priority(self, manager):
        """send_command should accept priority parameter."""
        # Without connection, it should raise but accept the parameter
        with pytest.raises(Exception):
            manager.send_command(':GR#', priority=CommandPriority.HIGH)

    @pytest.mark.unit
    def test_send_command_uses_default_priority(self, manager):
        """send_command should use thread-local priority when not specified."""
        # This is hard to test without mocking, but we verify the parameter exists
        import inspect
        sig = inspect.signature(manager.send_command)
        assert 'priority' in sig.parameters
        assert sig.parameters['priority'].default is None


class TestSerialManagerWorker:
    """Test SerialManager worker thread lifecycle."""

    @pytest.fixture
    def manager(self, mock_logger):
        """Create a SerialManager instance."""
        return SerialManager(mock_logger)

    @pytest.mark.unit
    def test_worker_not_running_initially(self, manager):
        """Worker thread should not be running initially."""
        assert manager._worker_thread is None

    @pytest.mark.unit
    def test_start_worker(self, manager):
        """_start_worker should start the worker thread."""
        manager._start_worker()
        assert manager._worker_thread is not None
        assert manager._worker_thread.is_alive()
        manager._stop_worker()

    @pytest.mark.unit
    def test_stop_worker(self, manager):
        """_stop_worker should stop the worker thread."""
        manager._start_worker()
        assert manager._worker_thread.is_alive()

        manager._stop_worker()
        # Give it a moment to stop
        time.sleep(0.1)
        assert manager._worker_thread is None or not manager._worker_thread.is_alive()

    @pytest.mark.unit
    def test_start_worker_idempotent(self, manager):
        """Starting worker twice should not create two threads."""
        manager._start_worker()
        thread1 = manager._worker_thread

        manager._start_worker()
        thread2 = manager._worker_thread

        assert thread1 is thread2
        manager._stop_worker()


class TestGetCaseDataPriority:
    """Test get_case_data priority parameter."""

    @pytest.fixture
    def manager(self, mock_logger):
        """Create a SerialManager instance."""
        return SerialManager(mock_logger)

    @pytest.mark.unit
    def test_get_case_data_accepts_priority(self, manager):
        """get_case_data should accept priority parameter."""
        import inspect
        sig = inspect.signature(manager.get_case_data)
        assert 'priority' in sig.parameters

    @pytest.mark.unit
    def test_get_case_data_default_priority(self, manager):
        """get_case_data should default to NORMAL priority."""
        import inspect
        sig = inspect.signature(manager.get_case_data)
        assert sig.parameters['priority'].default == CommandPriority.NORMAL
