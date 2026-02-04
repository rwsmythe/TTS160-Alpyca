# -*- coding: utf-8 -*-
"""
WebSocket Service

Real-time update service using NiceGUI's built-in WebSocket support.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
import threading

from nicegui import ui

from ..state import TelescopeState


class WebSocketService:
    """Real-time update service using NiceGUI's built-in capabilities.

    NiceGUI handles WebSocket connections automatically. This service
    manages state updates and broadcasts to connected clients.
    """

    def __init__(
        self,
        state: TelescopeState,
        logger: logging.Logger,
    ):
        """Initialize WebSocket service.

        Args:
            state: Telescope state for updates.
            logger: Logger instance.
        """
        self._state = state
        self._logger = logger

        # Update rate control
        self._position_rate = 2.0  # Hz
        self._status_rate = 1.0   # Hz

        # Timers for rate limiting
        self._last_position_update = 0.0
        self._last_status_update = 0.0

        # State change listeners
        self._listeners: List[Callable[[str, Any], None]] = []

        # Register as state listener
        self._state.add_listener(self._on_state_change)

    def _on_state_change(self, field: str, value: Any) -> None:
        """Handle state changes and broadcast to UI.

        Args:
            field: Changed field name.
            value: New value.
        """
        # Rate limit position updates
        now = datetime.now().timestamp()

        if field in ('ra_hours', 'dec_degrees', 'alt_degrees', 'az_degrees'):
            if now - self._last_position_update < 1.0 / self._position_rate:
                return
            self._last_position_update = now

        # Notify all listeners
        for listener in self._listeners:
            try:
                listener(field, value)
            except Exception as e:
                self._logger.error(f"WebSocket listener error: {e}")

    def add_listener(self, callback: Callable[[str, Any], None]) -> None:
        """Add a state change listener.

        Args:
            callback: Function called with (field, value) on changes.
        """
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str, Any], None]) -> None:
        """Remove a state change listener.

        Args:
            callback: Previously registered callback.
        """
        if callback in self._listeners:
            self._listeners.remove(callback)

    def set_position_rate(self, rate_hz: float) -> None:
        """Set position update rate.

        Args:
            rate_hz: Updates per second (1-10 Hz).
        """
        self._position_rate = max(1.0, min(10.0, rate_hz))

    def set_status_rate(self, rate_hz: float) -> None:
        """Set status update rate.

        Args:
            rate_hz: Updates per second (0.5-5 Hz).
        """
        self._status_rate = max(0.5, min(5.0, rate_hz))


class UpdateBroadcaster:
    """Broadcasts updates to connected NiceGUI clients.

    Uses NiceGUI's built-in reactivity for automatic UI updates.
    """

    def __init__(
        self,
        state: TelescopeState,
        logger: logging.Logger,
    ):
        """Initialize broadcaster.

        Args:
            state: Telescope state.
            logger: Logger instance.
        """
        self._state = state
        self._logger = logger
        self._running = False
        self._update_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the update broadcaster."""
        if self._running:
            return

        self._running = True
        self._update_task = asyncio.create_task(self._broadcast_loop())
        self._logger.info("Update broadcaster started")

    async def stop(self) -> None:
        """Stop the update broadcaster."""
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            self._update_task = None
        self._logger.info("Update broadcaster stopped")

    async def _broadcast_loop(self) -> None:
        """Broadcast loop for periodic updates."""
        while self._running:
            try:
                # Check for stale data
                self._state.mark_stale(threshold_seconds=5.0)

                # Trigger UI update (NiceGUI handles the actual broadcast)
                ui.update()

                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Broadcast error: {e}")
                await asyncio.sleep(1.0)


class CommandHandler:
    """Handles commands received from the UI.

    Processes commands and forwards them to the appropriate handlers.
    """

    def __init__(
        self,
        logger: logging.Logger,
    ):
        """Initialize command handler.

        Args:
            logger: Logger instance.
        """
        self._logger = logger
        self._handlers: Dict[str, Callable] = {}

    def register_handler(self, command: str, handler: Callable) -> None:
        """Register a command handler.

        Args:
            command: Command name.
            handler: Handler function.
        """
        self._handlers[command] = handler

    def handle_command(self, command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Handle a command.

        Args:
            command: Command name.
            params: Command parameters.

        Returns:
            Result dict with success/error info.
        """
        params = params or {}

        if command not in self._handlers:
            return {'success': False, 'error': f'Unknown command: {command}'}

        try:
            handler = self._handlers[command]
            result = handler(**params)
            return {'success': True, 'result': result}
        except Exception as e:
            self._logger.error(f"Command {command} failed: {e}")
            return {'success': False, 'error': str(e)}

    def get_available_commands(self) -> List[str]:
        """Get list of available commands.

        Returns:
            List of command names.
        """
        return list(self._handlers.keys())
