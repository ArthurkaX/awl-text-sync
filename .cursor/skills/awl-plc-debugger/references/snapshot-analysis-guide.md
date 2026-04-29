# Snapshot Analysis Guide

The 5-step process for analyzing live PLC debug snapshots from SIMATIC Manager's STL debug view. Read this BEFORE attempting any snapshot analysis.

This file is the canonical authority for the analysis protocol. The SKILL.md summarizes; this file provides the full walk-through, common patterns, and decision rules.

---

## The 5-Step Protocol

### Step 1 — Parse

Extract structured data from the snapshot:

| Field                       | Where to find it                                         |
|-----------------------------|----------------------------------------------------------|
| Network number              | "NETWORK n" header above the code                        |
| Network title               | `TITLE = ...` line                                       |
| Instruction lines           | Left panel, monospace STL                                |
| Register columns            | Right panel — RLO, STA, STANDARD (=ACCU1), ACCU2, AR1, AR2, DB1, DB2, STATUS |
| Yellow annotations          | Resolved absolute addresses for symbolic references      |
| Green-highlighted lines     | Instructions where RLO = 1                               |

**Output a normalized table** before proceeding:

| # | Instruction              | RLO | STA | ACCU1     | ACCU2  | AR1 | AR2 | DB1 | DB2 | STATUS    |
|---|--------------------------|-----|-----|-----------|--------|-----|-----|-----|-----|-----------|
| 1 | `A     #T255_Xfer`       | 1   | 1   | 50        | 1600   | 12.4| 0.0 | 105 | 173 | 1000 0111 |
| 2 | `L     S5T#500MS`        | 1   | 1   | 50        | 50     | 12.4| 0.0 | 105 | 173 | 1000 0110 |

### Step 2 — Decode

Convert raw register values to their actual types using `register-reference.md`:
- ACCU1 / ACCU2 — examine context: REAL? INT? S5TIME? BCD?
- STATUS word — decode binary into individual flags (BR, OR, OS, OV, CC0, CC1, FC, RLO, STA)
- AR1 / AR2 — pointer format (Area-crossing or Area-internal)

### Step 3 — Trace RLO

RLO (Result of Logic Operation) is the most diagnostic register. Walk row-by-row and identify every transition:

| Transition | What it means                                          |
|------------|--------------------------------------------------------|
| 1 → 0      | Some condition evaluated FALSE; logic chain "broken"   |
| 0 → 1      | New logic chain started, or condition evaluated TRUE   |
| 1 → 1      | RLO unchanged (instruction succeeded with TRUE input)  |
| 0 → 0      | RLO unchanged (instruction did not change RLO)         |

The 1→0 transitions are the **diagnostic signal** — these are where outputs get killed.

### Step 4 — Explain Transitions

For every RLO transition, name:
1. The instruction at that row
2. The operand (resolved to absolute address from yellow annotation)
3. The actual value of the operand (from ACCU or from another row)
4. Why this transition occurred

Example:
```
Row 7: AN #Faults.HighPressure   RLO 1→0
  Operand:  M 105.3 (yellow annotation)
  Value:    M 105.3 = 1 (TRUE)
  Reason:   AN sets RLO = previous_RLO AND NOT operand. Since M 105.3 was TRUE,
            AN forces RLO to 0. The fault flag is active.
```

### Step 5 — Diagnose

After all transitions explained, produce a diagnosis:

```
Final output state: <RLO at the = instruction>

Trace-back:
  Output X is OFF because RLO=0 at = "Output_X" (line N)
  RLO went 1→0 at line M because <condition>
  <condition> is <TRUE/FALSE> because <upstream cause>
  <upstream cause> represents <physical meaning>

Verdict:
  [Normal / Abnormal / Unable to determine without more data]

If Abnormal:
  - Suspected root cause: <description>
  - Recommended next step: <ask user / route to awl-step7 / route to awlsim-runner>
```

---

## Common Patterns

### Pattern A: Output blocked by single fault flag

```
Line N: A     "RunCmd"          RLO  1
Line N+1: AN  "Faults.K248"     RLO  1→0     ← here
Line N+2: =   "K248.RunOutput"  RLO  0
```

Trace-back: K248 is not running because `Faults.K248` is TRUE. Next: route to `awl-step7` to find which network sets that flag, and what conditions feed in.

### Pattern B: Analog interlock chattering at threshold

If you see RLO oscillating 1↔0 every scan around an analog comparison (`>=R`, `<=R`), the interlock lacks hysteresis (rule R3 violated). Recommend `awl-step7` review for hysteresis pattern.

### Pattern C: Unreachable code after BEC/BEU

If the snapshot shows code after a `BEC` or `BEU` that never executes (you can confirm by absence of expected register changes downstream), the block is exiting prematurely. Trace upward to find where RLO=1 triggered the exit.

### Pattern D: ACCU shows unexpected REAL value

If ACCU1 displayed as a small integer where the surrounding logic uses REALs, the value is the IEEE 754 bit pattern shown as an unsigned integer. Decode using `register-reference.md` IEEE 754 table.

Example: ACCU1 = 1095237632 → 32-bit IEEE 754 → 12.5 REAL.

### Pattern E: CALL boundary changes DB context

Note DB1/DB2 register values before and after `CALL "FB_Name", "DB_Instance"`. After CALL, DB1 = the called FB's instance DB number, and the previous DB1 is preserved by CALL/BE bookkeeping. If subsequent instructions reference symbols from the original DB context but DB1 has changed, that's a code bug — `OPN` should be reissued or the symbolic access should resolve via Symbol Table.

### Pattern F: STATUS word OV bit set

If STATUS word shows OV=1 after arithmetic, the operation overflowed. The result in ACCU1 is invalid. Downstream `AN OV; SAVE; CLR; A BR` (rule R1) should have caught it — if the snapshot shows the code skipped that pattern, that's a R1 violation.

---

## Snapshot-to-Simulation Pipeline

When the user wants to verify the snapshot reflects the code (not a stale binary or external state change):

1. Extract the code (the FB shown in the snapshot — get from user or project knowledge).
2. Extract the input conditions (analog values, SCADA states, DB values shown in ACCU/DB columns).
3. Build a trace-assertion test:
   - Set the inputs in `awlsim_runner.py --set-inputs`.
   - Run with `awlsim_tracer.py --trace-format json`.
   - Compare the simulator's trace against the snapshot's register table.
4. Differences imply:
   - **Same input + different output**: likely code version mismatch — confirm download timestamp.
   - **Same code + different output**: external state change between scan cycles, or timer-state difference.

This pipeline closes the gap between "what the engineer thinks the code does" and "what the live PLC actually did".

---

## When to escalate

If after Step 5 the diagnosis is "Unable to determine without more data":

- **Need additional networks?** Ask the user for screenshots showing the upstream logic chain.
- **Need code context?** Route to `awl-step7` Analysis Mode with the .AWL file.
- **Need to reproduce live behavior?** Route to `awlsim-runner` Mode 2 (follow to root).
- **Need Symbol Table?** Ask the user.

Never invent a diagnosis. If the visible data does not support a conclusion, name what's missing and ask for it.
