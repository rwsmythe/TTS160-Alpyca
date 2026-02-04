# -*- coding: utf-8 -*-
"""
Configuration Panel

Comprehensive settings interface for telescope, GPS, alignment, and GUI configuration.
Organizes settings into logical sections matching the TOML structure.
"""

from typing import Any, Callable, Dict, Optional
from nicegui import ui

from ...state import TelescopeState


def config_panel(
    config: Any,
    on_save: Callable[[Dict[str, Any]], None],
    on_theme_change: Callable[[str], None],
    on_disclosure_change: Callable[[int], None],
    state: Optional[TelescopeState] = None,
) -> ui.element:
    """Configuration settings panel.

    Sections:
    - Mount (device, site, driver settings)
    - GPS (GPS dongle configuration)
    - Alignment Monitor (plate solving and V1 decision engine)
    - GUI (appearance and behavior)

    Args:
        config: Configuration object with settings.
        on_save: Callback to save configuration changes.
        on_theme_change: Callback for theme changes.
        on_disclosure_change: Callback for disclosure level changes.
        state: Optional state for current theme/disclosure.

    Returns:
        Container element with configuration panel.
    """
    # Track pending changes
    pending_changes: Dict[str, Any] = {}

    with ui.column().classes('w-full gap-4') as container:
        with ui.tabs().classes('w-full') as tabs:
            mount_tab = ui.tab('Mount')
            gps_tab = ui.tab('GPS')
            align_tab = ui.tab('Alignment')
            gui_tab = ui.tab('GUI')

        with ui.tab_panels(tabs, value=mount_tab).classes('w-full'):
            # Mount settings (device + site + driver)
            with ui.tab_panel(mount_tab):
                _build_mount_section(config, pending_changes)

            # GPS settings
            with ui.tab_panel(gps_tab):
                _build_gps_section(config, pending_changes)

            # Alignment monitor settings
            with ui.tab_panel(align_tab):
                _build_alignment_section(config, pending_changes)

            # GUI settings
            with ui.tab_panel(gui_tab):
                _build_gui_section(
                    config,
                    state,
                    on_theme_change,
                    on_disclosure_change,
                    pending_changes,
                )

        # Save button
        ui.separator().classes('my-2')

        with ui.row().classes('w-full justify-between items-center'):
            ui.label('Changes are saved to TTS160config.toml').classes(
                'text-xs text-secondary'
            )

            def save_changes():
                if pending_changes:
                    on_save(pending_changes)
                    # Also save to file
                    try:
                        config.save()
                        ui.notify('Settings saved', type='positive')
                    except Exception as e:
                        ui.notify(f'Error saving: {e}', type='negative')
                    pending_changes.clear()
                else:
                    ui.notify('No changes to save', type='info')

            ui.button(
                'Save Changes',
                on_click=save_changes
            ).props('color=primary')

    return container


# =============================================================================
# Mount Section (device + site + driver)
# =============================================================================

def _build_mount_section(
    config: Any,
    pending: Dict[str, Any],
) -> None:
    """Build mount settings section combining device, site, and driver."""
    with ui.column().classes('w-full gap-4'):
        # Connection Settings
        with ui.expansion('Connection', icon='usb').classes('w-full'):
            with ui.column().classes('w-full gap-3 p-2'):
                # Serial port (required)
                _field_input(
                    'Serial Port *',
                    'dev_port',
                    config,
                    pending,
                    placeholder='COM5 or /dev/ttyUSB0',
                    hint='Mount serial port (required)'
                )

        # Site Location
        with ui.expansion('Site Location', icon='location_on').classes('w-full'):
            with ui.column().classes('w-full gap-3 p-2'):
                ui.label(
                    'Coordinates are synced from mount on connect'
                ).classes('text-xs text-secondary italic')

                with ui.row().classes('w-full gap-4'):
                    with ui.column().classes('flex-1'):
                        lat_input = _field_number(
                            'Latitude',
                            'site_latitude',
                            config,
                            pending,
                            min_val=-90,
                            max_val=90,
                            precision=6,
                            suffix='° (+ North)'
                        )
                    with ui.column().classes('flex-1'):
                        lon_input = _field_number(
                            'Longitude',
                            'site_longitude',
                            config,
                            pending,
                            min_val=-180,
                            max_val=180,
                            precision=6,
                            suffix='° (+ East)'
                        )

                elev_input = _field_number(
                    'Elevation',
                    'site_elevation',
                    config,
                    pending,
                    min_val=0,
                    max_val=10000,
                    precision=1,
                    suffix='meters'
                )

                # Copy from GPS button
                def copy_from_gps():
                    """Copy GPS coordinates to site location fields."""
                    try:
                        from TTS160Global import get_gps_manager
                        import logging
                        gps_mgr = get_gps_manager(logging.getLogger('config'))
                        if gps_mgr:
                            status = gps_mgr.get_status()
                            if status and status.position and status.position.valid:
                                lat_input.value = status.position.latitude
                                lon_input.value = status.position.longitude
                                elev_input.value = status.position.altitude
                                # Update config and pending changes
                                pending['site_latitude'] = status.position.latitude
                                pending['site_longitude'] = status.position.longitude
                                pending['site_elevation'] = status.position.altitude
                                setattr(config, 'site_latitude', status.position.latitude)
                                setattr(config, 'site_longitude', status.position.longitude)
                                setattr(config, 'site_elevation', status.position.altitude)
                                ui.notify('Copied GPS coordinates', type='positive')
                            else:
                                ui.notify('GPS fix not available', type='warning')
                    except Exception as e:
                        ui.notify(f'Error: {e}', type='negative')

                def check_gps_available() -> bool:
                    """Check if GPS has a valid fix."""
                    try:
                        from TTS160Global import get_gps_manager
                        import logging
                        gps_mgr = get_gps_manager(logging.getLogger('config'))
                        if gps_mgr:
                            status = gps_mgr.get_status()
                            if status and status.position:
                                return status.position.valid
                    except Exception:
                        pass
                    return False

                with ui.row().classes('w-full justify-end mt-2'):
                    gps_btn = ui.button(
                        'Copy from GPS',
                        icon='gps_fixed',
                        on_click=copy_from_gps
                    ).props('outline')

                    # Update button state based on GPS availability
                    def update_gps_button():
                        if check_gps_available():
                            gps_btn.enable()
                            gps_btn.props(remove='disable')
                        else:
                            gps_btn.disable()

                    update_gps_button()

                    # Set up periodic refresh of button state
                    ui.timer(2.0, update_gps_button)

        # Driver Settings
        with ui.expansion('Driver Settings', icon='settings').classes('w-full'):
            with ui.column().classes('w-full gap-3 p-2'):
                _field_switch(
                    'Sync time on connect *',
                    'sync_time_on_connect',
                    config,
                    pending,
                    hint='Set mount time from computer when connecting'
                )

                _field_number(
                    'Slew settle time *',
                    'slew_settle_time',
                    config,
                    pending,
                    min_val=0,
                    max_val=30,
                    precision=0,
                    suffix='seconds'
                )

                ui.separator()
                ui.label('Pulse Guide Settings').classes('text-sm font-medium')

                _field_switch(
                    'Equatorial frame',
                    'pulse_guide_equatorial_frame',
                    config,
                    pending,
                    hint='Move mount in equatorial frame for pulse guides'
                )

                _field_switch(
                    'Altitude compensation',
                    'pulse_guide_altitude_compensation',
                    config,
                    pending,
                    hint='Compensate azimuth pulse length for mount altitude'
                )

                with ui.row().classes('w-full gap-4'):
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Max compensation',
                            'pulse_guide_max_compensation',
                            config,
                            pending,
                            min_val=0,
                            max_val=5000,
                            precision=0,
                            suffix='ms'
                        )
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Compensation buffer',
                            'pulse_guide_compensation_buffer',
                            config,
                            pending,
                            min_val=0,
                            max_val=500,
                            precision=0,
                            suffix='ms'
                        )


# =============================================================================
# GPS Section
# =============================================================================

def _build_gps_section(
    config: Any,
    pending: Dict[str, Any],
) -> None:
    """Build GPS settings section."""
    with ui.column().classes('w-full gap-4'):
        # Core GPS Settings
        with ui.expansion('GPS Dongle', icon='gps_fixed', value=True).classes(
            'w-full'
        ):
            with ui.column().classes('w-full gap-3 p-2'):
                _field_switch(
                    'Enable GPS',
                    'gps_enabled',
                    config,
                    pending,
                    hint='Enable GPS dongle for automatic location updates'
                )

                _field_input(
                    'Serial Port',
                    'gps_port',
                    config,
                    pending,
                    placeholder='auto or COM3',
                    hint='"auto" to scan for GPS, or specific port'
                )

                with ui.row().classes('w-full gap-4'):
                    with ui.column().classes('flex-1'):
                        _field_select(
                            'Baud Rate',
                            'gps_baudrate',
                            config,
                            pending,
                            options={
                                4800: '4800',
                                9600: '9600',
                                19200: '19200',
                                38400: '38400'
                            }
                        )
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Read timeout',
                            'gps_read_timeout',
                            config,
                            pending,
                            min_val=0.5,
                            max_val=10,
                            precision=1,
                            suffix='sec'
                        )

        # GPS Quality Settings
        with ui.expansion('Fix Requirements', icon='signal_cellular_alt').classes(
            'w-full'
        ):
            with ui.column().classes('w-full gap-3 p-2'):
                _field_select(
                    'Minimum fix quality',
                    'gps_min_fix_quality',
                    config,
                    pending,
                    options={1: 'GPS (1)', 2: 'DGPS (2)', 4: 'RTK Fixed (4)'}
                )

                _field_number(
                    'Minimum satellites',
                    'gps_min_satellites',
                    config,
                    pending,
                    min_val=1,
                    max_val=20,
                    precision=0
                )

        # GPS Behavior
        with ui.expansion('Behavior', icon='tune').classes('w-full'):
            with ui.column().classes('w-full gap-3 p-2'):
                _field_switch(
                    'Push location on connect',
                    'gps_push_on_connect',
                    config,
                    pending,
                    hint='Send GPS location to mount when telescope connects'
                )

                _field_input(
                    'Location name',
                    'gps_location_name',
                    config,
                    pending,
                    placeholder='GPS',
                    hint='Name sent to mount (max 10 chars)'
                )

                _field_switch(
                    'Verbose logging',
                    'gps_verbose_logging',
                    config,
                    pending,
                    hint='Log NMEA sentences for debugging'
                )


# =============================================================================
# Alignment Monitor Section
# =============================================================================

def _build_alignment_section(
    config: Any,
    pending: Dict[str, Any],
) -> None:
    """Build alignment monitor settings section."""
    with ui.column().classes('w-full gap-4'):
        # Core Settings
        with ui.expansion(
            'Alignment Monitor', icon='center_focus_strong', value=True
        ).classes('w-full'):
            with ui.column().classes('w-full gap-3 p-2'):
                _field_switch(
                    'Enable alignment monitor',
                    'alignment_enabled',
                    config,
                    pending,
                    hint='Enable plate solving for pointing accuracy monitoring'
                )

                _field_number(
                    'Measurement interval',
                    'alignment_interval',
                    config,
                    pending,
                    min_val=5,
                    max_val=600,
                    precision=0,
                    suffix='seconds'
                )

                _field_number(
                    'Error warning threshold',
                    'alignment_error_threshold',
                    config,
                    pending,
                    min_val=1,
                    max_val=600,
                    precision=0,
                    suffix='arcsec'
                )

                _field_switch(
                    'Verbose logging',
                    'alignment_verbose_logging',
                    config,
                    pending
                )

        # Camera Settings
        with ui.expansion('Camera Source', icon='camera').classes('w-full'):
            with ui.column().classes('w-full gap-3 p-2'):
                _field_select(
                    'Camera source',
                    'alignment_camera_source',
                    config,
                    pending,
                    options={'alpaca': 'Alpaca', 'zwo': 'ZWO Native'}
                )

                ui.separator()
                ui.label('Alpaca Camera Settings').classes('text-sm font-medium')

                with ui.row().classes('w-full gap-4'):
                    with ui.column().classes('flex-1'):
                        _field_input(
                            'Server address',
                            'alignment_camera_address',
                            config,
                            pending,
                            placeholder='127.0.0.1'
                        )
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Port',
                            'alignment_camera_port',
                            config,
                            pending,
                            min_val=1,
                            max_val=65535,
                            precision=0
                        )

                _field_number(
                    'Device number',
                    'alignment_camera_device',
                    config,
                    pending,
                    min_val=0,
                    max_val=10,
                    precision=0
                )

                ui.separator()
                ui.label('ZWO Native Settings').classes('text-sm font-medium')

                _field_number(
                    'Camera ID',
                    'zwo_camera_id',
                    config,
                    pending,
                    min_val=0,
                    max_val=10,
                    precision=0,
                    hint='Camera index (0 for first ZWO camera)'
                )

                with ui.row().classes('w-full gap-4'):
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Exposure',
                            'zwo_exposure_ms',
                            config,
                            pending,
                            min_val=1,
                            max_val=60000,
                            precision=0,
                            suffix='ms'
                        )
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Gain',
                            'zwo_gain',
                            config,
                            pending,
                            min_val=0,
                            max_val=500,
                            precision=0
                        )

                with ui.row().classes('w-full gap-4'):
                    with ui.column().classes('flex-1'):
                        _field_select(
                            'Binning',
                            'zwo_binning',
                            config,
                            pending,
                            options={1: '1x1', 2: '2x2', 4: '4x4'}
                        )
                    with ui.column().classes('flex-1'):
                        _field_select(
                            'Image type',
                            'zwo_image_type',
                            config,
                            pending,
                            options={
                                'RAW8': 'RAW8',
                                'RAW16': 'RAW16',
                                'RGB24': 'RGB24',
                                'Y8': 'Y8'
                            }
                        )

        # Capture Settings
        with ui.expansion('Capture Settings', icon='photo_camera').classes('w-full'):
            with ui.column().classes('w-full gap-3 p-2'):
                _field_number(
                    'Exposure time',
                    'alignment_exposure_time',
                    config,
                    pending,
                    min_val=0.1,
                    max_val=60,
                    precision=1,
                    suffix='seconds'
                )

                _field_select(
                    'Binning',
                    'alignment_binning',
                    config,
                    pending,
                    options={1: '1x1', 2: '2x2', 4: '4x4'}
                )

        # Plate Solving Settings
        with ui.expansion('Plate Solving', icon='auto_fix_high').classes('w-full'):
            with ui.column().classes('w-full gap-3 p-2'):
                _field_number(
                    'Field of view estimate',
                    'alignment_fov_estimate',
                    config,
                    pending,
                    min_val=0.1,
                    max_val=30,
                    precision=2,
                    suffix='degrees'
                )

                _field_number(
                    'Detection threshold',
                    'alignment_detection_threshold',
                    config,
                    pending,
                    min_val=1,
                    max_val=20,
                    precision=1,
                    suffix='sigma'
                )

                _field_number(
                    'Maximum stars',
                    'alignment_max_stars',
                    config,
                    pending,
                    min_val=10,
                    max_val=200,
                    precision=0
                )

                _field_input(
                    'Database path',
                    'alignment_database_path',
                    config,
                    pending,
                    placeholder='tetra3_database.npz',
                    hint='Path to tetra3 star pattern database'
                )

        # V1 Decision Engine Thresholds
        with ui.expansion('V1 Decision Thresholds', icon='rule').classes('w-full'):
            with ui.column().classes('w-full gap-3 p-2'):
                ui.label('Error Thresholds (arcseconds)').classes(
                    'text-sm font-medium'
                )

                with ui.row().classes('w-full gap-4'):
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Ignore below',
                            'alignment_error_ignore',
                            config,
                            pending,
                            min_val=0,
                            max_val=120,
                            precision=0,
                            hint='No action taken'
                        )
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Sync above',
                            'alignment_error_sync',
                            config,
                            pending,
                            min_val=30,
                            max_val=300,
                            precision=0,
                            hint='Trigger sync'
                        )

                with ui.row().classes('w-full gap-4'):
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Concern above',
                            'alignment_error_concern',
                            config,
                            pending,
                            min_val=60,
                            max_val=600,
                            precision=0,
                            hint='Evaluate alignment'
                        )
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Max error',
                            'alignment_error_max',
                            config,
                            pending,
                            min_val=120,
                            max_val=1200,
                            precision=0,
                            hint='Force action + health event'
                        )

        # V1 Geometry Thresholds
        with ui.expansion('V1 Geometry Thresholds', icon='category').classes(
            'w-full'
        ):
            with ui.column().classes('w-full gap-3 p-2'):
                ui.label('Determinant Quality (0-1)').classes('text-sm font-medium')

                with ui.row().classes('w-full gap-4'):
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Excellent',
                            'alignment_det_excellent',
                            config,
                            pending,
                            min_val=0,
                            max_val=1,
                            precision=2,
                            hint='Protect this geometry'
                        )
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Good',
                            'alignment_det_good',
                            config,
                            pending,
                            min_val=0,
                            max_val=1,
                            precision=2,
                            hint='Be selective'
                        )

                with ui.row().classes('w-full gap-4'):
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Marginal',
                            'alignment_det_marginal',
                            config,
                            pending,
                            min_val=0,
                            max_val=1,
                            precision=2,
                            hint='Seek improvement'
                        )
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Min improvement',
                            'alignment_det_improvement_min',
                            config,
                            pending,
                            min_val=0,
                            max_val=0.5,
                            precision=2,
                            hint='To justify replacement'
                        )

        # V1 Angular Constraints
        with ui.expansion('V1 Angular Constraints', icon='straighten').classes(
            'w-full'
        ):
            with ui.column().classes('w-full gap-3 p-2'):
                ui.label('Distances (degrees)').classes('text-sm font-medium')

                _field_number(
                    'Minimum separation',
                    'alignment_min_separation',
                    config,
                    pending,
                    min_val=1,
                    max_val=90,
                    precision=0,
                    hint='Between alignment points'
                )

                with ui.row().classes('w-full gap-4'):
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Refresh radius',
                            'alignment_refresh_radius',
                            config,
                            pending,
                            min_val=1,
                            max_val=45,
                            precision=0,
                            hint='For refresh logic'
                        )
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'Scale radius',
                            'alignment_scale_radius',
                            config,
                            pending,
                            min_val=1,
                            max_val=90,
                            precision=0,
                            hint='Error weight falloff'
                        )

                _field_number(
                    'Refresh error threshold',
                    'alignment_refresh_error_threshold',
                    config,
                    pending,
                    min_val=10,
                    max_val=300,
                    precision=0,
                    suffix='arcsec'
                )

        # V1 Lockout and Health
        with ui.expansion('V1 Lockout & Health', icon='timer').classes('w-full'):
            with ui.column().classes('w-full gap-3 p-2'):
                ui.label('Lockout Periods (seconds)').classes('text-sm font-medium')

                with ui.row().classes('w-full gap-4'):
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'After alignment',
                            'alignment_lockout_post_align',
                            config,
                            pending,
                            min_val=0,
                            max_val=300,
                            precision=0
                        )
                    with ui.column().classes('flex-1'):
                        _field_number(
                            'After sync',
                            'alignment_lockout_post_sync',
                            config,
                            pending,
                            min_val=0,
                            max_val=60,
                            precision=0
                        )

                ui.separator()
                ui.label('Health Monitoring').classes('text-sm font-medium')

                _field_number(
                    'Health window',
                    'alignment_health_window',
                    config,
                    pending,
                    min_val=60,
                    max_val=7200,
                    precision=0,
                    suffix='seconds'
                )

                _field_number(
                    'Alert threshold',
                    'alignment_health_alert_threshold',
                    config,
                    pending,
                    min_val=1,
                    max_val=20,
                    precision=0,
                    hint='Events in window to trigger alert'
                )


# =============================================================================
# GUI Section
# =============================================================================

def _build_gui_section(
    config: Any,
    state: Optional[TelescopeState],
    on_theme_change: Callable[[str], None],
    on_disclosure_change: Callable[[int], None],
    pending: Dict[str, Any],
) -> None:
    """Build GUI preferences section."""
    with ui.column().classes('w-full gap-4'):
        # Appearance
        with ui.expansion('Appearance', icon='palette', value=True).classes('w-full'):
            with ui.column().classes('w-full gap-3 p-2'):
                # Theme
                with ui.column().classes('gap-1'):
                    ui.label('Theme').classes('text-sm')
                    current_theme = state.current_theme if state else 'dark'
                    ui.select(
                        options={
                            'light': 'Light',
                            'dark': 'Dark',
                            'astronomy': 'Astronomy (Red)',
                        },
                        value=current_theme,
                        on_change=lambda e: on_theme_change(e.value)
                    ).classes('w-full')

                # Disclosure level
                with ui.column().classes('gap-1'):
                    ui.label('Detail Level').classes('text-sm')
                    current_level = state.disclosure_level.value if state else 1
                    ui.select(
                        options={
                            1: 'Basic',
                            2: 'Expanded',
                            3: 'Advanced',
                        },
                        value=current_level,
                        on_change=lambda e: on_disclosure_change(e.value)
                    ).classes('w-full')


# =============================================================================
# Field Builder Helpers
# =============================================================================

def _field_input(
    label: str,
    prop_name: str,
    config: Any,
    pending: Dict[str, Any],
    placeholder: str = '',
    hint: str = '',
) -> ui.input:
    """Create a text input field bound to config property."""
    with ui.column().classes('w-full gap-1'):
        ui.label(label).classes('text-sm')
        inp = ui.input(
            value=str(getattr(config, prop_name, '')),
            placeholder=placeholder,
        ).classes('w-full')
        if hint:
            ui.label(hint).classes('text-xs text-secondary')

        def on_change():
            pending[prop_name] = inp.value
            setattr(config, prop_name, inp.value)

        inp.on('change', on_change)
        return inp


def _field_number(
    label: str,
    prop_name: str,
    config: Any,
    pending: Dict[str, Any],
    min_val: float = None,
    max_val: float = None,
    precision: int = 1,
    suffix: str = '',
    hint: str = '',
) -> ui.number:
    """Create a number input field bound to config property."""
    with ui.column().classes('w-full gap-1'):
        display_label = f'{label} ({suffix})' if suffix else label
        ui.label(display_label).classes('text-sm')
        fmt = f'%.{precision}f'
        inp = ui.number(
            value=getattr(config, prop_name, 0),
            format=fmt,
            min=min_val,
            max=max_val,
        ).classes('w-full')
        if hint:
            ui.label(hint).classes('text-xs text-secondary')

        def on_change():
            val = inp.value
            if precision == 0:
                val = int(val) if val is not None else 0
            pending[prop_name] = val
            setattr(config, prop_name, val)

        inp.on('change', on_change)
        return inp


def _field_switch(
    label: str,
    prop_name: str,
    config: Any,
    pending: Dict[str, Any],
    hint: str = '',
) -> ui.switch:
    """Create a switch field bound to config property."""
    with ui.row().classes('w-full items-center justify-between'):
        with ui.column().classes('gap-0'):
            ui.label(label).classes('text-sm')
            if hint:
                ui.label(hint).classes('text-xs text-secondary')
        sw = ui.switch(value=getattr(config, prop_name, False))

        def on_change(e):
            pending[prop_name] = e.value
            setattr(config, prop_name, e.value)

        sw.on('update:model-value', on_change)
        return sw


def _field_select(
    label: str,
    prop_name: str,
    config: Any,
    pending: Dict[str, Any],
    options: Dict[Any, str],
    hint: str = '',
) -> ui.select:
    """Create a select field bound to config property."""
    with ui.column().classes('w-full gap-1'):
        ui.label(label).classes('text-sm')
        sel = ui.select(
            options=options,
            value=getattr(config, prop_name, list(options.keys())[0]),
        ).classes('w-full')
        if hint:
            ui.label(hint).classes('text-xs text-secondary')

        def on_change(e):
            pending[prop_name] = e.value
            setattr(config, prop_name, e.value)

        sel.on('update:model-value', on_change)
        return sel
