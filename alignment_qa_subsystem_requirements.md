# Requirements Specification: Alignment QA Subsystem

## 1. Overview

### 1.1 Purpose
This subsystem extends the Alignment Monitor module to provide independent verification of the mount's alignment model. It calculates an alignment quaternion using known alignment point data and provides coordinate transformation capabilities for quality assurance and diagnostic purposes.

### 1.2 Scope
The Alignment QA Subsystem shall:
- Independently calculate the alignment transformation quaternion from alignment point data
- Convert mount tick positions to celestial coordinates (RA/Dec) and horizon coordinates (Alt/Az)
- Provide comparison metrics between driver-calculated and firmware-reported values
- Display QA information to the user in real-time
- Anticipate future capability to feed alignment corrections to the mount

### 1.3 Definitions and Abbreviations
| Term | Definition |
|------|------------|
| Quaternion | A 4-component mathematical object (w, x, y, z) representing 3D rotation |
| Q-method | Davenport's algorithm for optimal attitude determination from vector observations |
| H-ticks | Mount horizontal axis encoder counts (azimuth-like) |
| E-ticks | Mount elevation axis encoder counts (altitude-like) |
| IS_MSECS | Firmware internal time counter (960 ticks/second due to CLOCKSCALER, not true milliseconds) |
| Sidereal Time | Time scale based on Earth's rotation relative to stars |
| sat | Firmware flag: 1 = alignment point captured by user, 0 = not captured or synthetic |
| manual | Firmware flag: 1 = user-entered coordinates, 0 = auto-selected or synthetic |

---

## 2. Functional Requirements

### 2.1 Quaternion Calculation

#### REQ-QA-001: Independent Quaternion Calculation
The subsystem shall independently calculate an alignment transformation quaternion using the same general algorithm as the firmware (Davenport's Q-method), without requiring a line-by-line code replication.

#### REQ-QA-002: Alignment Point Data Retrieval
The subsystem shall retrieve alignment point data from the mount via the binary protocol, including:
- Encoder ticks for each point (A4-A9: H and E ticks for stars 1-3)
- Equatorial coordinates for each point (A10-A15: RA and Dec in radians)
- Capture timestamps for each point (A18-A20: IS_MSECS values)
- Point validity flags (A17: sat and manual flags bitfield)
- Point count (A16)

#### REQ-QA-003: Sidereal Time Compensation
The subsystem shall replicate the firmware's time-adjustment logic to account for Earth's rotation between alignment point captures. Specifically:
- Retrieve `Start_Sid_Time` (A2) and `Align_Sid_Time` (A3) from the mount
- Retrieve star capture timestamps (A18, A19, A20) in IS_MSECS units
- Apply sidereal rate correction factor (`SolarToSid = 1.002737908`, matching firmware)
- Calculate time deltas using: `delta_rad = (Time.N - Time.One) * MSecToRad * SolarToSid`
  - Where `MSecToRad = SecToRad / CLOCKSCALER` and `CLOCKSCALER = 960.0`
- Adjust star 2 RA: `ra2_adjusted = ra2 - delta_rad` (subtract to account for Earth rotation)
- Similarly adjust star 3 RA if present
- Rotate reference vectors appropriately before quaternion calculation

#### REQ-QA-004: Synthetic Point Detection and Replication
The subsystem shall detect and handle synthetic alignment points:

**Detection (Required):**
- Query A16 (point count) to determine how many real points exist (0-3)
- Query A17 (point flags) to identify which specific points have sat=1 (user-captured)
- Points with sat=0 that have valid coordinate data are synthetic

**Replication for QA Comparison (Optional):**
When replicating the firmware's synthetic generation for diagnostic purposes:
- For 1-star alignment: Firmware generates synthetic second star at 90° azimuth offset at the same altitude
- For 2-star alignment: Third point generated via cross-product in `make_transform_quaternion()` (ALIGN3=false)
- Synthetic ticks are calculated as: `Star2.H = Star1.H + (Ticks_Per_Round_H / 4)`, `Star2.E = Star1.E`

**QA Implications:**
When synthetic points are detected, the subsystem shall:
- Flag the alignment model as "synthetic-assisted" in QA status
- Note that quaternion comparison may show larger deltas due to synthetic point positioning
- Consider geometry quality metrics less meaningful when using synthetic points

#### REQ-QA-005: Firmware Quaternion Retrieval
The subsystem shall retrieve the firmware-calculated alignment quaternion via the binary protocol (T31: T_ALIGNMENT_QUAT, 4 floats: w, x, y, z).

#### REQ-QA-006: Quaternion Comparison
The subsystem shall calculate and report the difference between the driver-calculated quaternion and the firmware-reported quaternion. The comparison metric shall be expressed as an angular difference (in arcseconds or degrees).

#### REQ-QA-007: Quaternion Update Trigger
The subsystem shall recalculate the driver quaternion only when:
- The alignment monitor orders the mount to update alignment, OR
- The user explicitly requests a recalculation, OR
- New alignment point data is detected from the mount

---

### 2.2 Coordinate Transformation

#### REQ-QA-010: Tick to Alt/Az Conversion
The subsystem shall convert mount encoder ticks to horizon coordinates (altitude/azimuth) using:
- Ticks-per-revolution values retrieved from the mount (M8: H ticks, M9: E ticks)
- Linear conversion: `angle_rad = ticks * (2π / ticks_per_revolution)`
- Any applicable offset corrections

#### REQ-QA-011: Alt/Az to RA/Dec Conversion
The subsystem shall convert horizon coordinates to equatorial coordinates using:
- Observer location (latitude/longitude) retrieved from mount (C17, C18) or driver configuration
- Current local sidereal time
- Standard spherical trigonometry transformations
- A recognized astronomical library may be used for this conversion as a cross-check against firmware calculations

#### REQ-QA-012: Tick to RA/Dec Conversion
The subsystem shall provide a complete tick-to-equatorial conversion pipeline:
1. Convert ticks to Alt/Az (REQ-QA-010)
2. Convert Alt/Az to RA/Dec (REQ-QA-011)

This shall serve as an independent cross-check against the firmware's quaternion-based transformation.

#### REQ-QA-013: Coordinate Comparison
The subsystem shall compare driver-calculated coordinates against mount-reported coordinates and express the difference as angular separation in arcseconds.

#### REQ-QA-014: Calculation Precision
All calculations shall use the maximum reasonable precision provided by Python (IEEE 754 double precision, ~15-17 significant digits). The subsystem shall document that firmware calculations use single-precision floats, which will inherently cause small deltas between driver and mount values.

---

### 2.3 Data Display

#### REQ-QA-020: Real-Time Update
The subsystem shall update displayed QA information in real-time, synchronized with the interface update rate.

#### REQ-QA-021: User-Facing Display
The subsystem shall provide QA information suitable for user-facing display. The specific UI implementation is outside the scope of this subsystem, but the subsystem shall expose data through a well-defined interface.

#### REQ-QA-022: Displayed Information
The subsystem shall make the following information available for display:
- Driver-calculated quaternion components (w, x, y, z)
- Firmware-reported quaternion components (w, x, y, z)
- Angular difference between quaternions
- For current mount position:
  - Driver-calculated Alt/Az
  - Driver-calculated RA/Dec
  - Mount-reported RA/Dec (for comparison)
  - Position delta in arcseconds
- Alignment point residuals (error at each alignment point)
- Alignment model validity status

#### REQ-QA-023: Alignment Point Information
The subsystem shall make the following per-point information available:
- Point index (0, 1, 2)
- Validity status (real vs. synthetic)
- Encoder ticks (H, E)
- Equatorial coordinates (RA, Dec)
- Capture timestamp
- Residual error (if calculable)

---

### 2.4 Interface Requirements

#### REQ-QA-030: Data Access Interface
The subsystem shall expose a programmatic interface for other modules to query:
- Current quaternion comparison results
- Current coordinate transformation results
- Alignment point data and residuals
- QA status and health indicators

#### REQ-QA-031: Integration with Alignment Monitor
The subsystem shall integrate with the existing Alignment Monitor module. The architectural approach (separate class vs. integrated) is left to the implementation agent's discretion, provided the functional requirements are met.

#### REQ-QA-032: Thread Safety
All public interfaces shall be thread-safe, consistent with the existing Alignment Monitor's use of RLock protection.

#### REQ-QA-033: Mount Communication
The subsystem shall use the existing binary protocol communication infrastructure. It shall not implement redundant communication channels.

---

### 2.5 Future Extensibility

#### REQ-QA-040: Alignment Update Capability (Future)
The subsystem architecture shall anticipate future capability to feed alignment corrections to the mount using:
- ALIGN_POINT command (0x12) to add/replace alignment points
- PERFORM_ALIGNMENT command (0x13) to trigger mount recalculation

This capability shall NOT be implemented in the initial version but the architecture shall not preclude it.

#### REQ-QA-041: Interface Placeholder
The subsystem may define placeholder interfaces or abstract methods for the future alignment update capability, clearly marked as not-yet-implemented.

#### REQ-QA-042: Post-Implementation Review
After initial implementation is complete, a review shall be conducted to assess whether additional protocol commands or firmware modifications are needed to fully support bidirectional alignment updates.

---

## 3. Non-Functional Requirements

### 3.1 Performance

#### REQ-QA-050: Update Latency
Coordinate transformation calculations shall complete within 50ms to support real-time display updates.

#### REQ-QA-051: Quaternion Calculation Time
Full quaternion recalculation (including data retrieval) shall complete within 500ms.

#### REQ-QA-052: Resource Usage
The subsystem shall not significantly impact the performance of existing Alignment Monitor functions or mount communication.

---

### 3.2 Reliability

#### REQ-QA-060: Graceful Degradation
If mount communication fails or returns invalid data, the subsystem shall:
- Report the error condition clearly
- Continue operating with last-known-good data where appropriate
- Not crash or corrupt other subsystem state

#### REQ-QA-061: Data Validation
The subsystem shall validate all data received from the mount before use:
- Check quaternion normalization (magnitude ≈ 1.0)
- Verify coordinate ranges (RA: 0-2π, Dec: -π/2 to +π/2, etc.)
- Validate point flags and counts for consistency

---

### 3.3 Maintainability

#### REQ-QA-070: Code Documentation
All functions and classes shall include docstrings describing purpose, parameters, return values, and any assumptions.

#### REQ-QA-071: Algorithm Documentation
The quaternion calculation algorithm (Davenport Q-method) shall be documented with references to the mathematical basis and any adaptations made for this application.

#### REQ-QA-072: Unit Testability
The subsystem shall be designed to support unit testing of:
- Quaternion calculation with known inputs
- Coordinate transformations with known inputs
- Comparison metrics

#### REQ-QA-073: QA History Logging
The subsystem shall log QA comparison results at configurable intervals for post-session analysis:
- Timestamp of each comparison
- Quaternion angular difference
- Position delta in arcseconds
- Synthetic point status
- Alignment model validity

This data enables trend detection and diagnosis of alignment drift patterns over an observing session.

---

## 4. Data Requirements

### 4.1 Input Data (from Mount via Binary Protocol)

**Note:** All variables listed below exist in current firmware (v357). Variable IDs are verified against `binary.h`.

| Data Item | Protocol Variable | Type | Units | Notes |
|-----------|------------------|------|-------|-------|
| H-axis ticks | T1 (T_H_TICKS) | int32 | ticks | Current position |
| E-axis ticks | T2 (T_E_TICKS) | int32 | ticks | Current position |
| Firmware quaternion | T31 (T_ALIGNMENT_QUAT) | 4×float | (w,x,y,z) | Telescope→equatorial transform |
| Inverse quaternion | T32 (T_INV_QUAT) | 4×float | (w,x,y,z) | Equatorial→telescope transform |
| Mount RA | T16 (T_RA) | float | radians | Current RA |
| Mount Dec | T17 (T_DEC) | float | radians | Current Dec |
| IS_MSECS | T27 (T_MSECS) | uint32 | IS_MSECS | 960 ticks/sec (not true ms) |
| Alignment status | A1 (A_ALIGN_STATUS) | uint8 | enum | 0=none, 1=star1, 2=star2 |
| Start sidereal time | A2 (A_START_SID_TIME) | float | radians | Sidereal time at startup |
| Align sidereal time | A3 (A_ALIGN_SID_TIME) | float | radians | Sidereal time at alignment |
| Star 1 H ticks | A4 (A_STAR1_H_TICKS) | int32 | ticks | |
| Star 1 E ticks | A5 (A_STAR1_E_TICKS) | int32 | ticks | |
| Star 2 H ticks | A6 (A_STAR2_H_TICKS) | int32 | ticks | |
| Star 2 E ticks | A7 (A_STAR2_E_TICKS) | int32 | ticks | |
| Star 3 H ticks | A8 (A_STAR3_H_TICKS) | int32 | ticks | |
| Star 3 E ticks | A9 (A_STAR3_E_TICKS) | int32 | ticks | |
| Star 1 RA | A10 (A_STAR1_RA) | float | radians | |
| Star 1 Dec | A11 (A_STAR1_DEC) | float | radians | |
| Star 2 RA | A12 (A_STAR2_RA) | float | radians | |
| Star 2 Dec | A13 (A_STAR2_DEC) | float | radians | |
| Star 3 RA | A14 (A_STAR3_RA) | float | radians | |
| Star 3 Dec | A15 (A_STAR3_DEC) | float | radians | |
| Point count | A16 (A_POINT_COUNT) | uint8 | count | Computed: count of sat=1 points |
| Point flags | A17 (A_POINT_FLAGS) | uint8 | bitfield | See format below |
| Star 1 timestamp | A18 (A_STAR1_TIMESTAMP) | uint32 | IS_MSECS | Capture time |
| Star 2 timestamp | A19 (A_STAR2_TIMESTAMP) | uint32 | IS_MSECS | Capture time |
| Star 3 timestamp | A20 (A_STAR3_TIMESTAMP) | uint32 | IS_MSECS | Capture time |
| RMS error | A21 (A_RMS_ERROR) | float | radians | Alignment model error |
| Model valid | A22 (A_MODEL_VALID) | uint8 | boolean | 1 if model calculated |
| H ticks per revolution | M8 (M_TICKS_PER_ROUND_H) | int32 | ticks | |
| E ticks per revolution | M9 (M_TICKS_PER_ROUND_E) | int32 | ticks | |
| Longitude | C17 (C_LONGITUDE) | float | radians | |
| Latitude | C18 (C_LATITUDE) | float | radians | |

**A17 (A_POINT_FLAGS) Bitfield Format:**

| Bit | Meaning |
|-----|---------|
| 0 | Star 1 sat flag (1 = user-captured, 0 = not captured or synthetic) |
| 1 | Star 2 sat flag |
| 2 | Star 3 sat flag |
| 3 | Reserved |
| 4 | Star 1 manual flag (1 = user-entered coords, 0 = catalog/auto) |
| 5 | Star 2 manual flag |
| 6 | Star 3 manual flag |
| 7 | Reserved |

**Synthetic Point Detection Logic:**

The firmware does not have an explicit "simulated" flag. Synthetic points are identified by:
- `sat=0` (bit not set in A17) indicates the point was NOT captured by the user
- If A16 (point count) < 3, the firmware generates synthetic points to complete the model
- Synthetic points have valid coordinate data in A4-A15 but sat=0

Detection algorithm:
1. Read A16 (real point count) and A17 (flags)
2. For each star position (1-3):
   - If sat bit is 1: Real user-captured point
   - If sat bit is 0 AND real_count > 0: Synthetic point (firmware-generated)
   - If sat bit is 0 AND real_count == 0: No alignment performed yet

### 4.2 Output Data (for Display/API)

| Data Item | Type | Units |
|-----------|------|-------|
| Driver quaternion (w, x, y, z) | 4×float | dimensionless |
| Firmware quaternion (w, x, y, z) | 4×float | dimensionless |
| Quaternion angular difference | float | arcseconds |
| Driver-calculated altitude | float | degrees |
| Driver-calculated azimuth | float | degrees |
| Driver-calculated RA | float | hours |
| Driver-calculated Dec | float | degrees |
| Position delta | float | arcseconds |
| Per-point residuals | 3×float | arcseconds |
| QA status | enum | valid/invalid/stale |

---

## 5. Constants and Conversions

The following constants shall be used, consistent with firmware definitions in `align.h`:

| Constant | Value | Description |
|----------|-------|-------------|
| SolarToSid | 1.002737908 | Solar to sidereal time ratio (firmware precision) |
| CLOCKSCALER | 960.0 | IS_MSECS ticks per second (not 1000) |
| MSecToRad | SecToRad / CLOCKSCALER | IS_MSECS to radians (sidereal) |
| SecToRad | π / (12 × 3600) | Seconds to radians |
| HrToRad | π / 12 | Hours to radians |
| RadToHr | 12 / π | Radians to hours |
| DegToRad | π / 180 | Degrees to radians |
| RadToDeg | 180 / π | Radians to degrees |
| ArcsecToRad | π / (180 × 3600) | Arcseconds to radians |
| RadToArcsec | (180 × 3600) / π | Radians to arcseconds |

**Important Timing Note:**

The firmware uses `CLOCKSCALER = 960.0`, meaning IS_MSECS are NOT true milliseconds. One second equals 960 IS_MSECS ticks. When converting time deltas from firmware timestamps:

```python
# Correct conversion from IS_MSECS delta to radians
CLOCKSCALER = 960.0
SecToRad = math.pi / (12 * 3600)
MSecToRad = SecToRad / CLOCKSCALER
delta_rad = (time2 - time1) * MSecToRad * SolarToSid
```

---

## 6. Dependencies

### 6.1 Internal Dependencies
- Alignment Monitor module (`alignment_monitor.py`)
- Alignment Geometry module (`alignment_geometry.py`)
- Binary protocol communication infrastructure
- Driver configuration system

### 6.2 External Dependencies
- NumPy (for linear algebra operations)
- Optionally: Astropy or similar library for coordinate transformations (as cross-check)

---

## 7. Acceptance Criteria

### 7.1 Quaternion Calculation
- Given identical alignment point inputs, the driver-calculated quaternion shall produce coordinate transformations within 10 arcseconds of firmware results under these conditions:
  - Altitude between 20° and 85°
  - Within 60° of an alignment point
  - Using real (non-synthetic) alignment points only
- Larger deltas (up to 30 arcseconds) are acceptable when:
  - Near horizon (altitude < 20°) due to refraction effects
  - Far from alignment points (> 60° separation)
  - Using synthetic alignment points
- Deltas due to single vs. double precision (typically < 1 arcsecond) shall be documented

### 7.2 Coordinate Transformation
- Tick-to-RA/Dec conversion shall match mount-reported values within 10 arcseconds under nominal conditions
- Alt/Az intermediate values shall be verifiable against known test cases
- Near-zenith positions (altitude > 85°) may show larger azimuth deltas due to coordinate singularity

### 7.3 Real-Time Display
- Display data shall update at the configured interface refresh rate without visible lag or stuttering

### 7.4 Error Handling
- Communication failures shall be reported without crashing
- Invalid data shall be rejected with appropriate error messages

---

## 8. Open Items and Future Considerations

1. **Delta Thresholds**: Initial thresholds defined in Section 7.1/7.2; may need adjustment after field testing
2. **Bidirectional Alignment**: Full implementation of alignment update capability pending firmware validation
   - ALIGN_POINT (0x12) and PERFORM_ALIGNMENT (0x13) commands exist in binary.h but require testing
3. **UI Design**: Specific display layout and user interaction patterns to be defined separately
4. **Post-Implementation Review**: Per REQ-QA-042, assess need for additional protocol commands after initial implementation
5. **Synthetic Point Edge Cases**: Behavior when user has 0 real alignment points (Reset_Alignment state) needs verification

## 8.1 Firmware Protocol Status

All protocol variables referenced in this document exist in current firmware (v357):

| Category | Variables | Status |
|----------|-----------|--------|
| Alignment (A1-A22) | All 22 variables | ✅ Implemented in binary.h/binary.c |
| Tracking quaternions (T31-T32) | T_ALIGNMENT_QUAT, T_INV_QUAT | ✅ Implemented |
| Mount parameters (M8-M9) | Ticks per revolution | ✅ Implemented |
| Control (C17-C18) | Longitude, Latitude | ✅ Implemented |
| SET commands | ALIGN_POINT (0x12), PERFORM_ALIGNMENT (0x13) | ✅ Defined, needs integration testing |

No firmware modifications are required to implement this QA subsystem.

---

## 9. References

1. Firmware source: `align.c` - Alignment calculation implementation
2. Firmware source: `quaternion.c` - Quaternion operations (referenced but not provided)
3. Binary Protocol Reference - Command and variable definitions
4. Davenport, P.B. (1968) - "A Vector Approach to the Algebra of Rotations with Applications" (Q-method algorithm)
5. Existing driver modules: `alignment_monitor.py`, `alignment_geometry.py`

---

## Appendix A: Related Source Files

The following source files were reviewed during requirements development and should be provided to the implementation agent:

- `alignment_monitor.py` - Existing alignment monitor implementation
- `alignment_geometry.py` - Geometry calculations for alignment quality
- `align.c` (firmware) - Firmware alignment implementation
- Binary Protocol Reference document

---

## Appendix B: Firmware Algorithm Summary

### B.1 Quaternion Calculation Flow (from align.c)

1. **Input vectors**:
   - Reference: Equatorial coordinates (RA/Dec) converted to direction cosines via `eq_to_vec()`
   - Observed: Telescope ticks converted to direction cosines via `horiz_to_vec()`

2. **Time adjustment** (in `Perform_Alignment()`):
   - Time delta calculated: `t = (Time.Two - Time.One) * MSecToRad` where `MSecToRad = SecToRad / 960.0`
   - Second star RA adjusted in `make_transform_quaternion()` using `SolarToSid = 1.002737908`
   - Third star similarly adjusted if present (t3 parameter)

3. **Synthetic point generation** (in `Alignment_Point_Reduction()`):
   - 1-star alignment (case 1): Synthetic second star at 90° azimuth offset, same altitude
     - `Star_Ticks.Two.H = IS_POS_Ticks.H + (Ticks_Per_Round.H / 4)`
     - `Star_Ticks.Two.E = IS_POS_Ticks.E`
     - `Alignment_Stars.Two.sat` remains 0 (not set)
     - `Alignment_Stars.Two.manual = false`
   - 2-star alignment (case 2): Third point via cross-product in `make_transform_quaternion()` when `ALIGN3=false`
     - `Alignment_Stars.Three.sat = 0` explicitly set

4. **Altitude fitting**:
   - `fit_eticks()` uses ternary search to find optimal E-tick offset
   - Minimizes angular separation error between coordinate systems
   - Target accuracy: 1 arcsecond

5. **Quaternion calculation**:
   - `make_transform_quaternion()` computes optimal rotation quaternion using Davenport Q-method
   - Forward transform stored in `Global_Tracking.T_Alignment_quat` (telescope → equatorial)
   - Inverse transform stored in `Global_Tracking.Tinv_quat` (equatorial → telescope)
   - South angle stored in `Global_Tracking.South_Angle`

### B.2 Coordinate Transformation Flow

1. **Equatorial to telescope** (for goto):
   ```
   eq_to_vec(eq, v1)           // RA/Dec → direction cosines
   quatvec_mul(quat, v1, v2)   // Apply alignment rotation
   vec_to_horiz(v2, &h)        // Direction cosines → Alt/Az
   h.az * RadToHticks → H ticks
   h.alt * RadToEticks → E ticks
   ```

2. **Telescope to equatorial** (for display):
   - Inverse of above using inverse quaternion (T32)

---

*End of Requirements Specification*
