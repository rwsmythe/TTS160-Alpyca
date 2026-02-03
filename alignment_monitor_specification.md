# Alignment Monitor Specification

**Version:** 1.0  
**Date:** February 2, 2026  
**Status:** Draft

## 1. Overview

The Alignment Monitor is a semi-autonomous subsystem within the telescope mount driver that continuously evaluates pointing accuracy and alignment model quality. It automatically initiates synchronization or alignment point replacement operations to maintain optimal pointing performance with minimal user intervention.

### 1.1 Design Goals

1. **Minimize disruption** - Actions should be infrequent and only taken when necessary
2. **Improve accuracy** - Achieve alignment quality equal to or better than careful manual alignment
3. **Transparent operation** - User should rarely need to think about alignment after initial setup
4. **Graceful degradation** - Poor conditions should result in warnings, not failures

### 1.2 Scope

**V1 Includes:**
- Decision logic for sync vs. align vs. no action
- Geometry evaluation via determinant metric
- Sync offset tracking for consistent evaluation
- Per-point weighted error tracking
- Point age as replacement tiebreaker
- Health monitoring with UX alerts
- Configurable thresholds via TOML

**Deferred to V2:**
- Auto-alignment slew mode (autonomous geometry optimization)

## 2. System Architecture

### 2.1 Dependencies

The Alignment Monitor requires:
- Plate solver providing current RA/Dec with ~1 second latency
- Mount position reporting (current ticks or alt/az)
- Ability to command sync operations
- Ability to command alignment point capture
- Access to current alignment point data (coordinates, ticks, timestamps)

### 2.2 Trigger Conditions

The evaluation cycle executes:
- After each goto operation settles
- On a periodic "drumbeat" interval during tracking (configurable, default 60 seconds)

The evaluation cycle does NOT execute:
- During slewing (goto or manual)
- When plate solver is unavailable or invalid
- During lockout periods following recent actions

## 3. Data Structures

### 3.1 Alignment Point Record

Each of the three alignment points maintains:

```
AlignmentPoint:
    index: int                     # 1, 2, or 3
    equatorial: (ra, dec)          # Radians
    ticks: (h_ticks, e_ticks)      # Encoder counts
    timestamp: datetime            # When captured
    manual: bool                   # User-selected vs. auto-captured
    weighted_error_sum: float      # Accumulated weighted error (arcsec)
    weighted_error_weight: float   # Accumulated weights
```

### 3.2 Sync Offset Tracker

Maintains cumulative sync adjustments for evaluation consistency:

```
SyncOffsetTracker:
    cumulative_h_ticks: int        # Total H-axis sync adjustments
    cumulative_e_ticks: int        # Total E-axis sync adjustments
    last_reset: datetime           # When last cleared (at alignment)
```

### 3.3 Health Monitor

Tracks high-error events for system health assessment:

```
HealthMonitor:
    events: list[(datetime, float)]  # (timestamp, error_magnitude)
    alert_active: bool               # Whether alert is currently raised
```

## 4. Configuration Parameters

All parameters are configurable via TOML file. Units are documented for each parameter.

```toml
[alignment_monitor]
# Enable/disable the alignment monitor
enabled = true

# Evaluation interval during tracking (seconds)
drumbeat_interval = 60

# Pointing error thresholds (arcseconds)
error_ignore = 30        # Below this, take no action
error_sync = 120         # Above this, sync if not aligning
error_concern = 300      # Above this, evaluate alignment replacement
error_max = 600          # Above this, force action and log health event

# Geometry thresholds (determinant absolute value, dimensionless)
det_excellent = 0.80     # Near-optimal; protect this geometry
det_good = 0.60          # Solid; be selective about changes
det_marginal = 0.40      # Weak; actively seek improvement
det_improvement_min = 0.10  # Minimum improvement to justify replacement

# Angular constraints (degrees)
min_separation = 15      # Minimum angle between any two alignment points
refresh_radius = 10      # Distance within which "refresh" logic applies
scale_radius = 30        # Per-point weighted error distance falloff

# Weighted error threshold for refresh eligibility (arcseconds)
refresh_error_threshold = 60

# Lockout periods (seconds)
lockout_post_align = 60  # After alignment point replacement
lockout_post_sync = 10   # After sync operation

# Health monitoring
health_window = 1800     # Window duration (seconds) - 30 minutes
health_alert_threshold = 5  # Events within window to trigger alert
```

## 5. Algorithms

### 5.1 Pointing Error Calculation

Angular separation between plate-solved position and mount-reported position:

```
error = angular_separation(plate_solve_radec, mount_reported_radec)
```

Where `angular_separation` uses the haversine formula or equivalent for spherical distance.

Result is converted to arcseconds for threshold comparison.

### 5.2 Geometry Quality Metric

The quality of the three-point alignment configuration is measured by the absolute determinant of the 3×3 matrix formed by the three unit direction vectors.

Given three alignment points with alt/az coordinates, compute unit vectors:

```
v_i = [cos(alt_i) * cos(az_i), cos(alt_i) * sin(az_i), sin(alt_i)]
```

Form matrix M with columns v_1, v_2, v_3:

```
det = |det(M)|
```

Properties:
- `det = 0`: Points are coplanar through origin (degenerate)
- `det → 1`: Points are maximally spread (optimal)

For candidate evaluation, compute the determinant that would result from replacing each existing point with the current mount position.

### 5.3 Per-Point Weighted Error Accumulation

For each plate solve observation, update the weighted error for each alignment point:

```
distance_i = angular_separation(current_position, alignment_point_i)
weight_i = 1 / (1 + (distance_i / scale_radius)^2)

point_i.weighted_error_sum += weight_i * pointing_error
point_i.weighted_error_weight += weight_i

point_i.mean_weighted_error = weighted_error_sum / weighted_error_weight
```

This attributes higher error weight to the alignment point(s) closest to where the error was observed.

**Reset condition:** When an alignment point is replaced, its `weighted_error_sum` and `weighted_error_weight` are reset to zero.

### 5.4 Minimum Separation Check

Before accepting a candidate replacement, verify that no two points in the resulting configuration are closer than `min_separation`:

```
for each pair (i, j) in resulting configuration:
    if angular_separation(point_i, point_j) < min_separation:
        reject candidate
```

### 5.5 Sync Offset Management

When a sync is performed:

```
sync_offset.cumulative_h_ticks += (new_h_ticks - old_h_ticks)
sync_offset.cumulative_e_ticks += (new_e_ticks - old_e_ticks)
```

When evaluating pointing error for decision-making, the cumulative offset is used to normalize comparisons.

When an alignment is performed:

```
sync_offset.cumulative_h_ticks = 0
sync_offset.cumulative_e_ticks = 0
sync_offset.last_reset = now()
```

### 5.6 Health Event Tracking

When `pointing_error > error_max`:

```
health.events.append((now(), pointing_error))
health.events = [e for e in health.events if e.timestamp > now() - health_window]

if len(health.events) > health_alert_threshold:
    raise_ux_alert()
```

## 6. Decision Logic

The following pseudocode describes the complete evaluation cycle:

```
function evaluate():
    # Step 1: Check lockout
    if in_lockout_period():
        return NO_ACTION
    
    # Step 2: Check mount state
    if not mount_is_static():
        return NO_ACTION
    
    # Step 3: Get positions
    plate_solve = get_plate_solve_position()
    if plate_solve is None or plate_solve.is_stale():
        return NO_ACTION
    
    mount_position = get_mount_reported_position()
    pointing_error = angular_separation(plate_solve, mount_position)
    
    # Step 4: Update per-point weighted errors
    for point in alignment_points:
        update_weighted_error(point, mount_position, pointing_error)
    
    # Step 5: Check if error is ignorable
    if pointing_error < config.error_ignore:
        return NO_ACTION
    
    # Step 6: Compute geometry metrics
    current_det = compute_determinant(alignment_points)
    
    candidates = []
    for point in alignment_points:
        candidate_det = compute_determinant_with_replacement(point, mount_position)
        min_sep = compute_min_separation_with_replacement(point, mount_position)
        distance = angular_separation(mount_position, point)
        
        if min_sep >= config.min_separation:
            det_improvement = candidate_det - current_det
            
            if det_improvement >= config.det_improvement_min:
                candidates.append({
                    point: point,
                    det: candidate_det,
                    improvement: det_improvement,
                    reason: "geometry"
                })
            elif distance < config.refresh_radius and point.mean_weighted_error > config.refresh_error_threshold:
                candidates.append({
                    point: point,
                    det: candidate_det,
                    improvement: det_improvement,
                    reason: "refresh"
                })
    
    # Step 7: Handle no candidates
    if len(candidates) == 0:
        if pointing_error > config.error_sync:
            perform_sync()
            start_lockout(config.lockout_post_sync)
            return SYNC
        else:
            return NO_ACTION
    
    # Step 8: Select replacement point
    selected = select_replacement(candidates, current_det)
    
    # Step 9: Health monitoring
    if pointing_error > config.error_max:
        log_health_event(pointing_error)
        check_health_alert()
    
    # Step 10: Perform alignment
    perform_alignment(selected.point, mount_position, plate_solve)
    reset_weighted_error(selected.point)
    start_lockout(config.lockout_post_align)
    return ALIGN


function select_replacement(candidates, current_det):
    # Priority 1: Refresh candidates (fixing bad data)
    refresh_candidates = [c for c in candidates if c.reason == "refresh"]
    if len(refresh_candidates) > 0:
        # If multiple refresh candidates, pick oldest point
        return oldest_point(refresh_candidates)
    
    # Priority 2: Geometry improvement
    # Check if multiple candidates cross the same threshold
    thresholds = [config.det_excellent, config.det_good, config.det_marginal]
    
    def highest_crossed_threshold(det):
        for t in thresholds:
            if det >= t:
                return t
        return 0
    
    candidate_thresholds = [(c, highest_crossed_threshold(c.det)) for c in candidates]
    max_threshold = max(ct[1] for ct in candidate_thresholds)
    
    top_candidates = [ct[0] for ct in candidate_thresholds if ct[1] == max_threshold]
    
    if len(top_candidates) > 1:
        # Multiple candidates at same threshold level: pick oldest
        return oldest_point(top_candidates)
    else:
        # Single best candidate
        return top_candidates[0]


function oldest_point(candidates):
    return min(candidates, key=lambda c: c.point.timestamp)
```

## 7. State Transitions

```
                    ┌─────────────┐
                    │   IDLE      │
                    │  (waiting)  │
                    └──────┬──────┘
                           │
                           │ trigger (drumbeat or goto settle)
                           ▼
                    ┌─────────────┐
              ┌─────│  EVALUATE   │─────┐
              │     └──────┬──────┘     │
              │            │            │
     lockout/ │   error <  │  error >   │ no candidates,
     no solve │   ignore   │  ignore    │ error > sync
              │            │            │
              ▼            ▼            ▼
        ┌─────────┐  ┌─────────┐  ┌─────────┐
        │ NO_ACT  │  │ NO_ACT  │  │  SYNC   │
        └─────────┘  └─────────┘  └────┬────┘
                                       │
                           candidates  │ lockout
                           found       │
                           │           ▼
                           │     ┌─────────┐
                           │     │ LOCKOUT │
                           │     └─────────┘
                           ▼
                    ┌─────────────┐
                    │   ALIGN     │
                    └──────┬──────┘
                           │
                           │ lockout
                           ▼
                    ┌─────────────┐
                    │   LOCKOUT   │
                    └─────────────┘
```

## 8. Firmware Interface

### 8.1 Required Commands

The driver must be able to issue the following commands to the firmware:

| Command | Description | Parameters |
|---------|-------------|------------|
| `GET_POSITION` | Current mount position | None |
| `SYNC` | Adjust reported position | target_ra, target_dec |
| `ALIGN_POINT` | Capture alignment point | point_index (1-3), ra, dec |
| `PERFORM_ALIGNMENT` | Recalculate alignment model | None |
| `GET_ALIGNMENT_DATA` | Retrieve current alignment points | None |

### 8.2 Alignment Sequence

To replace alignment point N:

1. Ensure mount is static
2. Issue `ALIGN_POINT(N, ra, dec)` with plate-solved coordinates
3. Issue `PERFORM_ALIGNMENT`
4. Reset sync offset tracker
5. Start post-alignment lockout

## 9. Error Handling

### 9.1 Plate Solve Failures

If the plate solver fails or returns invalid data:
- Skip the current evaluation cycle
- Do not accumulate weighted errors
- Log the failure for diagnostics

### 9.2 Command Failures

If a sync or alignment command fails:
- Log the failure
- Do not start lockout (allow retry on next cycle)
- Consider incrementing a failure counter for health monitoring

### 9.3 Inconsistent State

If alignment point data from firmware is inconsistent with driver's records:
- Log a warning
- Refresh driver's alignment point cache from firmware
- Reset weighted error accumulators

## 10. Logging and Diagnostics

### 10.1 Standard Logging

Each evaluation cycle should log (at DEBUG level):
- Pointing error magnitude
- Current geometry determinant
- Action taken (if any)

Each action (SYNC or ALIGN) should log (at INFO level):
- Action type
- Pointing error that triggered it
- For ALIGN: which point was replaced, old and new determinant

### 10.2 Health Alerts

When health alert threshold is crossed, emit a WARNING level log and set a flag for UX display:

```
WARNING: Alignment health alert - {N} high-error events in past {window} minutes.
         Possible causes: loose plate solver, mechanical issues, unstable mount.
```

## 11. Testing Considerations

### 11.1 Unit Tests

- Determinant calculation with known geometries
- Weighted error accumulation
- Candidate selection logic
- Threshold boundary conditions

### 11.2 Integration Tests

- Full evaluation cycle with mock plate solver
- Sync offset tracking across multiple syncs
- Alignment replacement sequence
- Lockout timing

### 11.3 Simulation

Consider a simulation mode that:
- Uses synthetic plate solve data with configurable error injection
- Runs accelerated time to observe long-term behavior
- Validates convergence to optimal geometry

## 12. Future Considerations (V2)

### 12.1 Auto-Alignment Slew Mode

User-initiated mode where the mount autonomously slews to positions that would optimize alignment geometry:

- Compute optimal target positions given current geometry
- Slew to each target, plate solve, capture alignment point
- Handle obstructions (clouds, physical baffles) via timeout and retry
- Provide progress feedback to UX

### 12.2 Adaptive Thresholds

Consider automatically adjusting thresholds based on:
- Observed plate solve noise floor
- Historical pointing accuracy for this mount
- Current atmospheric conditions (if available)

---

## Appendix A: Determinant Calculation Reference

For three unit vectors v1, v2, v3 forming matrix M = [v1 | v2 | v3]:

```
det(M) = v1 · (v2 × v3)
       = v1x(v2y*v3z - v2z*v3y) - v1y(v2x*v3z - v2z*v3x) + v1z(v2x*v3y - v2y*v3x)
```

Absolute value gives volume of parallelepiped, ranging from 0 (coplanar) to ~1 (well-spread).

## Appendix B: Angular Separation Formula

For two positions (ra1, dec1) and (ra2, dec2) in radians:

```
cos(sep) = sin(dec1)*sin(dec2) + cos(dec1)*cos(dec2)*cos(ra1 - ra2)
sep = acos(cos(sep))
```

Or using the numerically stable haversine formula:

```
a = sin((dec2-dec1)/2)^2 + cos(dec1)*cos(dec2)*sin((ra2-ra1)/2)^2
sep = 2 * atan2(sqrt(a), sqrt(1-a))
```

Convert to arcseconds: `sep_arcsec = sep * 206264.806`
