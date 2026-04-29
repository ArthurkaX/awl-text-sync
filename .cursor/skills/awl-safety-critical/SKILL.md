---
name: awl-safety-critical
description: Safety-critical patterns for Siemens STEP 7 STL/AWL code in live manufacturing environments. Use when the user asks about safety interlocks, alarm logic, arithmetic guards, hysteresis, edge detection, fault reset behavior, watchdog patterns, pre-download checklists, actuator control, or any code where a defect could cause equipment damage or injury. This is a passive checklist module — it provides mandatory rules to be applied by awl-step7's Analysis and Authoring modes. It does not run analyses or write code on its own; it supplies the rule set.
---

# AWL Safety-Critical Skill

## Role declaration

**I am a passive checklist module.** When loaded, I provide a fixed rule set that `awl-step7` (and the human operator) consult during Analysis Mode and Authoring Mode. I do not analyse code, run simulations, or write code on my own. If the user request is to *do something*, route to `awl-step7` or `awlsim-runner`. If the user request is to *check against the rules*, that's me.

## Context

This is a **live manufacturing plant**. Code runs on real equipment 24/7. A single defect can cause: equipment damage, unplanned downtime, personal injury, or CPU STOP. Every rule below is non-negotiable for production code.

---

## MANDATORY RULES — Non-Negotiable

These rules apply to **every** new or modified block delivered to the live PLC. Their numbering is stable; downstream skills (especially `awl-step7`) cite them by ID.

### R0 — No code that can cause uncontrolled actuator movement

Every output that drives a physical actuator (valve, motor, heater, drive, contactor) must have an **explicit run-permit chain**. Outputs default to de-energized on CPU STOP — verify this is the safe state for *that specific actuator*.

**Pattern:**
```awl
      A     #SCADA.RunCommand;        // Operator wants to run
      A     #Control.AutoMode;        // Mode is AUTO
      AN    #Faults.GeneralFault;     // No active fault
      AN    #Interlocks.SafetyTrip;   // No safety interlock
      A     #Permissives.AllReady;    // Upstream ready
      =     "Motor.K248.RunCmd";
```

**Document fail-safe behavior** for every actuator inline:
```awl
// Fail-safe state for K248: STOPPED (de-energized).
// On CPU STOP, motor coil de-energizes via hardware → motor coasts to stop.
// This is safe for downstream conveyor — no material accumulation.
```

---

### R1 — Overflow protection after every REAL operation

Every `+R`, `-R`, `*R`, `/R` MUST be followed by `AN OV; SAVE; CLR; A BR`:

```awl
      L     #ValueA;
      L     #ValueB;
      -R    ;
      T     #Temp_Real;
      AN    OV;            // MANDATORY — check no overflow
      SAVE  ;              // MANDATORY — save validity to BR
      CLR   ;              // MANDATORY
      A     BR;            // MANDATORY — continue only if valid
```

For chained operations, each layer is bracketed and checked:
```awl
      A(    ;              // outer
      A(    ;              // inner
      L     #A;
      L     #B;
      -R    ;
      T     #Temp_Real;
      AN    OV;
      SAVE  ;
      CLR   ;
      A     BR;
      )     ;
      JNB   _001;          // skip if inner invalid (RLO=0 → BR=0)
      L     #Temp_Real;
      L     #C;
      *R    ;
      T     #Temp_Real;
      AN    OV;
      SAVE  ;
      CLR   ;
_001: A     BR;
      )     ;
      JNB   _002;          // skip if either invalid
      L     #Temp_Real;
      T     #Result;
_002: NOP   0;
```

Same applies to `+I/-I/*I//I/+D/-D/*D//D` (INT/DINT) where overflow is possible. INT operations overflow at ±32767, DINT at ±2,147,483,647.

---

### R2 — Division — always guard against zero

`/R`, `/I`, `/D` divide-by-zero sends the CPU to STOP. Always guard:

```awl
// BEFORE dividing:
      A(    ;
      L     #Divisor;
      L     0.000000e+000;
      ==R   ;
      )     ;
      JC    Skip_Div;       // Skip if divisor is zero

      L     #Numerator;
      L     #Divisor;
      /R    ;
      T     #Result;
      AN    OV;             // Then check overflow per R1
      SAVE  ;
      CLR   ;
      A     BR;
      JNB   Skip_Div;

      // ... use #Result ...

Skip_Div: NOP   0;
```

---

### R3 — Analog interlocks — always use hysteresis

Direct analog comparison chatters at threshold (output toggles every scan when the value sits at setpoint). Always use S/R latch with deadband:

```awl
// SET when above high limit:
      A(    ;
      L     #AnalogInput;
      L     #SCADA.HighSetpoint;
      >=R   ;
      )     ;
      S     #Interlocks.HighAlarm;

// RESET when sufficiently below (5 unit hysteresis):
      A(    ;
      L     #SCADA.HighSetpoint;
      L     5.000000e+000;
      -R    ;
      T     #Temp_Real;
      AN    OV;
      SAVE  ;
      CLR   ;
      A     BR;
      )     ;
      A(    ;
      L     #AnalogInput;
      L     #Temp_Real;
      <R    ;
      )     ;
      R     #Interlocks.HighAlarm;
      NOP   0;
```

Choose deadband to match process units: pressure in kPa, temperature in °C, level in %, etc.

---

### R4 — SCADA pushbuttons — edge detect + end-of-block reset

SCADA BOOL tags from WinCC stay TRUE for multiple scans while the operator holds the button. Without edge detection, the action triggers every scan.

```awl
// Edge detect so action fires once per press:
      A     #SCADA.StartButton;
      FP    #PulseBits[1];          // Rising edge only
      S     #Control.StartLatched;
```

**MANDATORY reset at end of every FB:**
```awl
NETWORK
TITLE =Reset SCADA Pushbuttons

      SET   ;
      R     #SCADA.StartButton;
      R     #SCADA.StopButton;
      R     #SCADA.FaultReset_PB;
```

Each `FP`/`FN` requires its **own** `PulseBits[n]` element — never reuse one for two signals.

---

### R5 — Fault reset only when fault condition has cleared

```awl
// WRONG — can reset fault while fault condition still active:
      A     #SCADA.FaultReset_PB;
      R     #Faults.HighPressure;

// CORRECT — fault condition must clear first:
      A     #SCADA.FaultReset_PB;
      AN    #Interlocks.PressureHigh;   // Not in fault condition
      R     #Faults.HighPressure;
```

This prevents "click-through" reset where the operator silences an alarm while the underlying condition is still present.

---

### R6 — VAR_TEMP — initialise before use

`VAR_TEMP` values are **undefined** at block entry. Reading before writing yields garbage from the previous stack frame.

```awl
// WRONG:
      L     #Temp_Real;        // DANGER: undefined value

// CORRECT:
      L     0.000000e+000;
      T     #Temp_Real;        // Initialise first
      L     #Temp_Real;        // Now safe
```

**Instance DB startup state safety**: declared initial values in the FB's VAR section appear in newly-created Instance DBs but **not** in pre-existing Instance DBs after a re-compile. After modifying an FB, regenerate the Instance DB or run a one-shot init in OB100.

---

### R7 — SQRT and LN — guard against invalid input

`SQRT` of negative or `LN` of non-positive produces an invalid REAL (unordered). Always guard the input AND check the result with `JUO` (Jump Unordered):

```awl
// SQRT must have non-negative input:
      A(    ;
      L     #Value;
      L     0.000000e+000;
      >=R   ;
      )     ;
      JCN   Skip_Sqrt;        // Skip if negative

      L     #Value;
      SQRT  ;
      T     #Result;
      JUO   Skip_Sqrt;        // Skip if unordered result

      // ... use #Result ...

Skip_Sqrt: NOP   0;
```

`LN` requires input strictly > 0 (not ≥ 0).

---

### R8 — Loop watchdog / scan-time patterns

Every `LOOP` instruction must have a guaranteed termination — the bound is in `ACCU1-L` and decrements each iteration. Long synchronous calculations must not exceed the CPU's configured watchdog time.

```awl
// SAFE — bounded LOOP:
      L     10;                // 10 iterations max
loop_start: NOP 0;
      [body]
      LOOP  loop_start;        // Decrements ACCU1-L; jumps if ≠ 0
```

**Cycle-time-overflow path**: configure CPU watchdog (typically 150 ms for S7-300, 300 ms for S7-400). On overflow, OB80 (Time Error OB) is called. Always provide an OB80 that puts critical outputs to safe state — the default behavior is CPU STOP.

**Long calculations**: split across cycles using a state variable in VAR static. Don't run a 200-iteration filter inside a single OB1 call.

---

### R9 — Symbol-table completeness

Pre-download check verifies every symbolic reference (`"DBName".field`, `"FB Name"`, etc.) resolves to a defined entry in the project's Symbol Table. A missing symbol fails at compile time but is a real risk after Symbol Table edits — block download must fail loudly if any symbol is unresolved, not silently fall back to absolute addressing.

---

### R10 — Hardwired vs soft interlock distinction

Safety-critical interlocks (ESTOP, guard doors, light curtains, two-hand operation) **must be hardwired in hardware first**. PLC logic is the secondary, monitoring layer — never the primary protection.

**Document for every interlock** which layer owns it:
```awl
// Interlock: 10-LSL-102 Crystalliser Seal Water Level Low
// Hardware: hardwired into K248 starter circuit (cuts coil)
// Software: this block monitors and alarms; it does NOT prevent run command
```

The PLC-only interlock pattern is only acceptable for **process protection** (preventing equipment damage), never for **personnel protection**.

---

## Documentation Rule — All assumptions in comments

Every non-obvious sequencing dependency, every magic number, every unit assumption (kPa vs PSI, °C vs °F, seconds vs minutes), every priority decision (which S/R wins) must be commented inline. The reviewer must be able to verify the assumption without re-reading the entire block.

```awl
// Hysteresis = 5.0 kPa (NOT bar) — matches PT-205 calibration range 0–500 kPa
      L     5.000000e+000;
```

---

## Interlock Design Principles

### Interlock chain (positive logic)

All conditions must be TRUE for the device to run:
```awl
      A     [Condition1];          // Normal state
      A     [Condition2];          // Normal state
      AN    [FaultCondition1];     // Fault must be FALSE
      AN    [FaultCondition2];     // Fault must be FALSE
      =     #DeviceRunPermit;
```

### Never use OR where AND is required for safety:
```awl
// DANGEROUS — single TRUE input bypasses all faults:
      O     [Safety_Bypass];
      AN    [Fault1];
      AN    [Fault2];
      =     #Permit;            // WRONG — bypass overrides faults

// SAFE — bypass must be a separate, explicit, audited path
```

### Fail-safe state — document per output

For every output, document:
- **Required state on CPU STOP** (typically 0 / de-energized — but verify per actuator)
- **Required state on CPU power loss** (same)
- **Required state on watchdog overflow** (programmed in OB80)
- **Behavior on OB STOP→RUN transition** (cold restart vs warm restart implications)

---

## Pre-Download Checklist

Before downloading any code to the live PLC:

**Code review (apply rules R0–R10):**
- [ ] R0: Every actuator output has an explicit run-permit chain; fail-safe state documented
- [ ] R1: All REAL arithmetic has overflow protection (`AN OV; SAVE; CLR; A BR`)
- [ ] R2: All division operations have explicit zero-divisor guards
- [ ] R3: All analog interlocks use hysteresis (S/R latch with deadband)
- [ ] R4: All SCADA buttons use edge detection AND are reset at end of block
- [ ] R5: Fault reset is gated on fault condition having cleared
- [ ] R6: No VAR_TEMP read before initialise; Instance DB regenerated after FB edit
- [ ] R7: SQRT/LN inputs validated; outputs checked with `JUO`
- [ ] R8: All `LOOP` instructions have bounded iteration; CPU watchdog configured; OB80 present
- [ ] R9: All symbolic references resolve in Symbol Table; no missing tags
- [ ] R10: Safety-critical interlocks documented as hardware-vs-software per item
- [ ] All assumptions in comments (units, magic numbers, priority decisions)
- [ ] `stl_precheck.py --strict --project-mode <EN|DE>` passes
- [ ] `awlsim-runner` smoke test passes

**Process review:**
- [ ] Safe state of all new/modified outputs is documented
- [ ] New code does not interfere with existing interlock chains
- [ ] Setpoint initial values in Instance DB are safe for the process
- [ ] Tested in `awlsim-runner` and (where possible) S7-PLCSIM before going live
- [ ] Change-impact analysis covers all calling blocks

**Operational:**
- [ ] Code reviewed by a second person
- [ ] Change communicated to operations team
- [ ] Time of download chosen to minimise production impact
- [ ] Rollback plan documented (which previous version, which DBs to restore)

---

## Skill System Map

This skill is part of the AWL/STL package (v1.2.0). Routing:

| User signal                         | Route to                                | Why                              |
|-------------------------------------|-----------------------------------------|----------------------------------|
| "is this safe", "review for safety" | awl-step7 (consults THIS skill's rules) | Workflow lives in step7          |
| "what does R3 say"                  | THIS skill                              | Rule lookup                      |
| "create a new FB"                   | awl-step7 Authoring Mode                | THIS skill is consulted, not run |
| "run / simulate / verify"           | awlsim-runner                           | Dynamic verification             |
| "decode this snapshot"              | awl-plc-debugger                        | Live state analysis              |
| "what does instruction X do"        | awl-language-reference                  | Reference lookup                 |

### Shared artifacts and schema versions

| Artifact                       | Owner          | Schema | Consumer must check |
|--------------------------------|----------------|--------|---------------------|
| `stl_precheck.py` JSON output  | awlsim-runner  | v1.0   | awl-step7           |
| `mnemonics.py` schema          | awlsim-runner  | v1.0   | awl-step7, awlsim-runner |
| Rules R0–R10 + Documentation Rule | THIS skill   | v1.0   | awl-step7           |

### Package version compatibility

| Skill                     | Compatible with                   |
|---------------------------|-----------------------------------|
| awl-safety-critical@1.0   | awl-step7@1.2.x                   |

THIS skill provides the rule SET; downstream skills are responsible for *applying* the rules.
