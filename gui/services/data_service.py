# -*- coding: utf-8 -*-
"""
Data Service

Service for fetching telescope data from the backend device.
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional
import threading
import time

from ..state import TelescopeState, AlignmentState, DecisionResult


class DataService:
    """Service for fetching and updating telescope data.

    Polls the device at regular intervals and updates the state.
    Handles connection management and error recovery.
    """

    def __init__(
        self,
        state: TelescopeState,
        device: Any,
        config: Any,
        logger: logging.Logger,
    ):
        """Initialize data service.

        Args:
            state: Telescope state to update.
            device: TTS160Device instance.
            config: Configuration object.
            logger: Logger instance.
        """
        self._state = state
        self._device = device
        self._config = config
        self._logger = logger

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._update_interval = 0.5  # 2 Hz default

        # Command queue for sending to device
        self._command_queue: list = []
        self._command_lock = threading.Lock()

    def start(self) -> None:
        """Start the data service polling thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._polling_loop,
            daemon=True,
            name="DataService"
        )
        self._thread.start()
        self._logger.info("Data service started")

    def stop(self) -> None:
        """Stop the data service."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._logger.info("Data service stopped")

    def set_update_interval(self, interval_seconds: float) -> None:
        """Set the polling interval.

        Args:
            interval_seconds: Interval between updates (0.5-10 seconds).
        """
        self._update_interval = max(0.5, min(10.0, interval_seconds))

    def _polling_loop(self) -> None:
        """Main polling loop - runs in background thread."""
        while self._running:
            try:
                self._fetch_and_update()
                self._process_commands()
            except Exception as e:
                self._logger.error(f"Data service error: {e}")
                self._state.update(connection_error=str(e))

            time.sleep(self._update_interval)

    def _fetch_and_update(self) -> None:
        """Fetch data from device and update state."""
        if self._device is None:
            return

        try:
            # Connection status
            connected = getattr(self._device, 'Connected', False)

            updates = {
                'connected': connected,
                'last_communication': datetime.now() if connected else None,
            }

            if not connected:
                self._state.update(**updates)
                return

            # Position data
            try:
                updates['ra_hours'] = self._device.RightAscension
                updates['dec_degrees'] = self._device.Declination
            except Exception:
                pass

            try:
                updates['alt_degrees'] = self._device.Altitude
                updates['az_degrees'] = self._device.Azimuth
            except Exception:
                pass

            try:
                updates['sidereal_time'] = self._device.SiderealTime
            except Exception:
                pass

            # Tracking status
            try:
                updates['tracking_enabled'] = self._device.Tracking
            except Exception:
                pass

            try:
                updates['slewing'] = self._device.Slewing
            except Exception:
                pass

            # Hardware status
            try:
                updates['at_park'] = self._device.AtPark
            except Exception:
                pass

            try:
                updates['at_home'] = self._device.AtHome
            except Exception:
                pass

            # Pier side
            try:
                pier = self._device.SideOfPier
                updates['pier_side'] = 'east' if pier == 0 else 'west' if pier == 1 else 'unknown'
            except Exception:
                pass

            # Serial port from config
            try:
                updates['serial_port'] = getattr(self._config, 'serial_port', '')
            except Exception:
                pass

            # Clear any connection error
            updates['connection_error'] = None

            self._state.update(**updates)

        except Exception as e:
            self._logger.error(f"Error fetching device data: {e}")
            self._state.update(connection_error=str(e))

    def _process_commands(self) -> None:
        """Process any queued commands."""
        with self._command_lock:
            commands = self._command_queue.copy()
            self._command_queue.clear()

        for cmd_type, args in commands:
            try:
                self._execute_command(cmd_type, args)
            except Exception as e:
                self._logger.error(f"Command {cmd_type} failed: {e}")

    def _execute_command(self, cmd_type: str, args: Dict[str, Any]) -> None:
        """Execute a command on the device.

        Args:
            cmd_type: Command type identifier.
            args: Command arguments.
        """
        if self._device is None or not getattr(self._device, 'Connected', False):
            return

        if cmd_type == 'slew_start':
            direction = args.get('direction')
            speed = args.get('speed', 1)
            # Map to device method
            if hasattr(self._device, 'MoveAxis'):
                axis = 0 if direction in ('n', 's') else 1
                rate = speed * (1 if direction in ('n', 'e') else -1)
                self._device.MoveAxis(axis, rate)

        elif cmd_type == 'slew_stop':
            if hasattr(self._device, 'AbortSlew'):
                self._device.AbortSlew()

        elif cmd_type == 'goto':
            ra = args.get('ra')
            dec = args.get('dec')
            if hasattr(self._device, 'SlewToCoordinatesAsync'):
                self._device.SlewToCoordinatesAsync(ra, dec)

        elif cmd_type == 'tracking_toggle':
            enabled = args.get('enabled')
            if hasattr(self._device, 'Tracking'):
                self._device.Tracking = enabled

        elif cmd_type == 'park':
            if hasattr(self._device, 'Park'):
                self._device.Park()

        elif cmd_type == 'unpark':
            if hasattr(self._device, 'Unpark'):
                self._device.Unpark()

        elif cmd_type == 'home':
            if hasattr(self._device, 'FindHome'):
                self._device.FindHome()

        elif cmd_type == 'sync':
            ra = args.get('ra')
            dec = args.get('dec')
            if hasattr(self._device, 'SyncToCoordinates'):
                self._device.SyncToCoordinates(ra, dec)

    def queue_command(self, cmd_type: str, **args) -> None:
        """Queue a command for execution.

        Args:
            cmd_type: Command type identifier.
            **args: Command arguments.
        """
        with self._command_lock:
            self._command_queue.append((cmd_type, args))

    def get_status(self) -> Dict[str, Any]:
        """Get current status snapshot.

        Returns:
            Dict with current state values.
        """
        return self._state.get_status_dict()

    def send_command(self, cmd: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send command to device.

        Args:
            cmd: Command name.
            params: Command parameters.

        Returns:
            Result dict with success/error info.
        """
        params = params or {}
        try:
            self.queue_command(cmd, **params)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}


class AlignmentDataService:
    """Service for fetching alignment monitor data."""

    def __init__(
        self,
        state: TelescopeState,
        alignment_monitor: Any,
        logger: logging.Logger,
    ):
        """Initialize alignment data service.

        Args:
            state: Telescope state to update.
            alignment_monitor: AlignmentMonitor instance.
            logger: Logger instance.
        """
        self._state = state
        self._monitor = alignment_monitor
        self._logger = logger

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start alignment data updates."""
        if self._running or self._monitor is None:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._update_loop,
            daemon=True,
            name="AlignmentDataService"
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop alignment data updates."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _update_loop(self) -> None:
        """Alignment data update loop."""
        while self._running:
            try:
                self._fetch_alignment_data()
            except Exception as e:
                self._logger.error(f"Alignment data error: {e}")

            time.sleep(1.0)  # 1 Hz update rate

    def _fetch_alignment_data(self) -> None:
        """Fetch alignment monitor data and update state."""
        if self._monitor is None:
            return

        try:
            # Get monitor state
            monitor_state = getattr(self._monitor, 'state', None)
            if monitor_state:
                self._state.update(
                    alignment_state=AlignmentState(monitor_state.value)
                )

            # Get error measurements
            if hasattr(self._monitor, 'last_measurement'):
                meas = self._monitor.last_measurement
                if meas:
                    self._state.update(
                        alignment_error_arcsec=getattr(meas, 'total_error', 0.0),
                        alignment_error_ra=getattr(meas, 'ra_error', 0.0),
                        alignment_error_dec=getattr(meas, 'dec_error', 0.0),
                    )

            # Get geometry
            if hasattr(self._monitor, 'geometry_determinant'):
                self._state.update(
                    geometry_determinant=self._monitor.geometry_determinant
                )

            # Get decision info
            if hasattr(self._monitor, 'last_decision'):
                decision = self._monitor.last_decision
                if decision:
                    self._state.update(
                        last_decision=DecisionResult(decision.value)
                    )

            # Get lockout
            if hasattr(self._monitor, 'lockout_remaining'):
                self._state.update(
                    lockout_remaining_sec=self._monitor.lockout_remaining
                )

            # Get health alert
            if hasattr(self._monitor, 'health_alert_active'):
                self._state.update(
                    health_alert=self._monitor.health_alert_active
                )

            # Get camera source
            if hasattr(self._monitor, 'camera_source_type'):
                self._state.update(
                    camera_source=self._monitor.camera_source_type
                )

        except Exception as e:
            self._logger.error(f"Error fetching alignment data: {e}")
