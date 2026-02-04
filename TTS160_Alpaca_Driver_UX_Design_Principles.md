# TTS160 Alpaca Driver UX Design Principles

## 1. Core UX Philosophy

### 1.1 User-Centric Simplicity
The interface serves users across a spectrum of technical expertise. Design decisions favor clarity over feature density. Every element must justify its presence by serving a clear user need.

### 1.2 Respect for Context
Users operate this interface during observing sessions where attention is divided between software, hardware, and the sky. The UX must minimize cognitive load and support quick comprehension at a glance.

### 1.3 Trust Through Transparency
The mount is a precision instrument. Users need confidence that commands are received, actions are executing, and the system state is accurately represented. Never leave users guessing.

---

## 2. Information Hierarchy

### 2.1 Priority Order
Status information follows this priority (highest to lowest):
1. **Pointing** — Current coordinates (RA/Dec, Alt/Az)
2. **Tracking** — Current tracking mode and state
3. **Hardware** — Motor status, physical state
4. **Connection** — Communication health
5. **Alignment Quality** — Accuracy metrics and recommendations

### 2.2 Spatial Hierarchy
- Primary status (pointing, tracking) occupies persistent, prominent screen real estate
- Secondary status (hardware, connection) remains visible but subordinate
- Tertiary information (alignment quality, diagnostics) available on demand

### 2.3 Visual Weight
More important information receives greater visual weight through size, contrast, and positioning. Less critical information recedes visually without disappearing.

---

## 3. Progressive Disclosure

### 3.1 Layered Complexity
Present the interface in layers:
- **Layer 1 (Default):** Essential controls and status for routine operation
- **Layer 2 (Expanded):** Additional details and less-common controls
- **Layer 3 (Advanced):** Diagnostics, raw data, developer-level access

### 3.2 User-Controlled Depth
Users choose their depth of engagement. The interface never forces advanced information on users who don't want it, nor hides it from those who do.

### 3.3 Contextual Revelation
Some advanced information surfaces automatically when relevant (e.g., motor diagnostics appear when a motor fault occurs) but can be dismissed.

### 3.4 Persistent Preferences
User choices about disclosure level persist across sessions where practical.

---

## 4. Visual Design Principles

### 4.1 Mode Support
The interface supports three visual modes:
- **Light Mode** — Standard daytime/indoor use
- **Dark Mode** — Reduced eye strain, general nighttime use
- **Astronomy Mode** — Red-only illumination preserving night vision

### 4.2 Astronomy Mode Constraints
In astronomy mode:
- All illumination uses red wavelengths only (no blue/green components)
- Brightness levels are minimized while maintaining readability
- Contrast relies on brightness variation within the red spectrum
- No white or bright colored elements

### 4.3 Consistency Across Modes
Information hierarchy, layout, and interaction patterns remain identical across modes. Only color rendering changes.

### 4.4 Typography
- Use clear, readable fonts at sizes appropriate for arms-length viewing
- Numeric data (coordinates, values) uses monospace fonts for alignment and quick scanning
- Adequate line height and spacing for low-light readability

### 4.5 Iconography
Icons supplement but do not replace text labels for critical functions. Icons must be unambiguous and distinguishable in all color modes.

---

## 5. Real-Time Feedback

### 5.1 Update Philosophy
Real-time displays update at rates that convey responsiveness without creating visual noise or system burden. Position displays should feel "alive" without appearing jittery.

### 5.2 Suggested Update Rates
- Position coordinates: 1-2 Hz (smooth perception without excess load)
- Tracking status: On change, or 1 Hz confirmation
- Connection status: On change, with periodic heartbeat indication
- Alignment metrics: On change or on demand

### 5.3 State Transitions
All state changes animate briefly to draw attention without disrupting workflow. Transitions should be quick (100-200ms) and purposeful.

### 5.4 Staleness Indication
If real-time data becomes stale (communication interruption), the interface clearly indicates this. Never display potentially outdated information as current.

---

## 6. Workflow Design

### 6.1 Initial Setup Workflow
Guide users through connection and initial configuration with clear sequencing. Validate each step before proceeding. Provide clear feedback on success/failure.

### 6.2 Alignment Workflow (Semi-Autonomous)
The alignment monitor workflow:
- Clearly display current alignment state and quality
- Present plate-solve results with recommended action (sync vs. new alignment point)
- Explain reasoning for recommendations at user's chosen detail level
- Allow user override of recommendations
- Track alignment history within session

### 6.3 Monitoring Workflow
During imaging sessions:
- Persistent, glanceable status display
- Minimal interaction required when operating normally
- Immediate visibility of any anomalies
- Quick access to detailed diagnostics when needed

### 6.4 Troubleshooting Workflow
Provide structured access to diagnostic information:
- Logs (filterable by severity, component, time)
- Motor state and command history
- Communication traces
- Current and recent error states

---

## 7. Status and Notification Principles

### 7.1 Severity Levels
Define clear severity levels:
- **Info** — Normal operational messages
- **Warning** — Attention needed, operation continues
- **Error** — Operation failed or blocked, user action required
- **Critical** — Immediate attention required, potential equipment/safety concern

### 7.2 Notification Behavior by Severity
- **Info:** Subtle inline display, no interruption
- **Warning:** Visible indicator, persists until acknowledged or resolved
- **Error:** Prominent display, may interrupt workflow, requires acknowledgment
- **Critical:** Modal or high-visibility alert, blocks unrelated actions until addressed

### 7.3 Notification Persistence
- Transient notifications auto-dismiss after appropriate duration
- Persistent notifications remain until underlying condition resolves
- All notifications logged for later review

### 7.4 Notification Location
- Context-specific notifications appear near relevant UI elements
- System-wide notifications appear in consistent, predictable location
- Critical notifications command central attention

### 7.5 Avoiding Alert Fatigue
Be judicious with notifications. Frequent low-value alerts train users to ignore all alerts. Reserve interrupting notifications for genuinely important events.

---

## 8. Interaction Principles

### 8.1 Confirmation for Consequential Actions
Actions with significant consequences (stop tracking, disconnect, clear alignment) require confirmation. Routine actions do not.

### 8.2 Responsive Feedback
Every user action receives immediate feedback—at minimum, acknowledgment that input was received. If processing takes time, indicate progress.

### 8.3 Error Recovery
When errors occur, provide clear guidance on resolution. Never leave users at a dead end.

---

## 9. Performance Principles

### 9.1 Perceived Responsiveness
The interface should feel responsive even when waiting for mount communication. Use optimistic updates where safe, with correction if needed.

### 9.2 Resource Efficiency
UX updates should not compete with mount communication or burden the firmware. Batch requests where possible. Avoid polling when event-driven updates are available.

### 9.3 Graceful Degradation
If communication degrades, the interface remains functional with clear indication of reduced capability. Never freeze or become unresponsive due to backend issues.

---

## 10. Extensibility Principles

### 10.1 Modular Architecture
Design UI as composable modules that can be arranged, shown, or hidden based on user preference and context.

### 10.2 Future-Proofing
Design decisions should accommodate likely future features (e.g., additional hardware support, remote operation) without requiring fundamental restructuring.

### 10.3 Configuration Over Code
Where practical, behavior variations driven by configuration rather than code changes facilitate customization and testing.

---

*Document Version: 1.0*
*For use with Claude Code during TTS160 Alpaca Driver UX implementation*
