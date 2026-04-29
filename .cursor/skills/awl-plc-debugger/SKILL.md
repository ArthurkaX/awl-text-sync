---
name: awl-plc-debugger
description: Analyze live PLC debug snapshots from SIMATIC Manager STL debug view. Parse register states (RLO, STA, ACCU1, ACCU2, AR1, AR2, DB1, DB2, STATUS), decode values, trace logic flow, and perform fault finding. Use when user uploads screenshots of PLC debug views, pastes register traces, asks "why is this output off", or needs root cause analysis of live PLC behavior. Also trigger on mentions of "snapshot", "debug view", "registers", "RLO", "ACCU", "status word", "fault find", "diagnose", or "compare with live PLC".
---

# awl-plc-debugger — PLC Debug Snapshot Analyzer

## What this skill does

Reads and analyzes live PLC debug data — the register-level view that engineers see in SIMATIC Manager's STL debug mode. Bridges the gap between what the code SHOULD do (static analysis via `awl-step7`) and what the PLC ACTUALLY did (live register state).

This skill can:
- Parse screenshots or text dumps of SIMATIC Manager STL debug views
- Decode register values: RLO, STA, ACCU1/ACCU2 (including IEEE 754 REAL), AR1/AR2, DB1/DB2, STATUS word
- Trace RLO flow instruction by instruction, identifying every transition point
- Explain WHY each RLO transition occurred (which bit, which value, which comparison)
- Perform fault finding: "why is this output OFF?" → trace backward to the blocking condition
- Compare live PLC register states against simulator output for verification
- Focus analysis on specific equipment within a snapshot

## When to use / When NOT to use

| Situation                                              | Use THIS skill | Use instead              |
|--------------------------------------------------------|----------------|--------------------------|
| User uploads a screenshot showing STL with register columns | ✅           | —                        |
| User pastes text from a PLC debug view or register trace | ✅            | —                        |
| User asks "what's happening here" with snapshot data    | ✅              | —                        |
| User asks "why is this output off / not working" + snapshot | ✅          | —                        |
| User mentions: snapshot, debug view, registers, RLO, ACCU, status word, trace | ✅ | —     |
| User asks for fault find / diagnose / RCA WITH register data | ✅           | —                        |
| User says "compare with live", "match the PLC"          | ✅              | —                        |
| User asks for static code analysis WITHOUT register data | ❌             | `awl-step7`              |
| User wants to simulate code                              | ❌              | `awlsim-runner`          |
| User wants to create or modify AWL code                  | ❌              | `awl-step7`              |
| User asks "what does instruction X do"                   | ❌              | `awl-language-reference` |

## CRITICAL: Before any analysis

Read both reference files via the file viewer BEFORE analyzing any snapshot. The references contain register decoding rules, the structured analysis process, and common patterns that are NOT repeated in this SKILL.md.

| MUST read first                              | Why                                                                          |
|----------------------------------------------|------------------------------------------------------------------------------|
| `references/snapshot-analysis-guide.md`      | The 5-step analysis process, common patterns, fault finding workflow, snapshot-to-simulation pipeline |
| `references/register-reference.md`           | STATUS word bit layout, ACCU value decoding (incl. IEEE 754), S5TIME BCD format, condition codes, AR1/AR2 pointer format |

If a tracer JSON is provided as input (Format 3 below), assert `schema_version` matches expected before parsing.

---

## Snapshot Analysis Workflow

Follow the **5-step process** documented in `references/snapshot-analysis-guide.md`:

1. **Parse** — Extract each instruction and its register state row. Identify network number, title, and yellow annotations (resolved absolute addresses).
2. **Decode** — Convert ACCU values to their actual types (REAL, INT, S5TIME) using `register-reference.md`. Decode the STATUS word binary into individual flag meanings.
3. **Trace RLO** — Follow RLO row by row. Identify every transition (1→0 or 0→1). These transitions are the KEY to understanding the logic.
4. **Explain Transitions** — For each RLO change, explain WHY: which instruction, which bit/value, what the actual comparison was.
5. **Diagnose** — Identify the final output state, trace backward to find the blocking/enabling condition, determine if this is expected or a fault.

---

## Input Formats

### Format 1: Screenshot (Image)

The user uploads a screenshot of SIMATIC Manager's STL debug view. Read:
- **Left panel:** STL code with instructions
- **Right panel:** Register columns — RLO, STA, STANDARD (ACCU1), ACCU2, AR1, AR2, DB1, DB2, STATUS
- **Yellow annotations:** Resolved absolute addresses for symbolic references
- **Green highlighting:** Lines where RLO = 1

### Format 2: Text Dump (Copy-Paste)

The user copies the debug view as text:
```
      A     #T255_Xfer          | 1 | 1 |    50 |   1600 | 12.4 | 0.0 | 105 | 173 | 1000 0111
      L     S5T#500MS           | 1 | 1 |    50 |     50 | 12.4 | 0.0 | 105 | 173 | 1000 0110
```

### Format 3: Simulator Trace (JSON)

Output from `awlsim_tracer.py` — already structured with all register fields decoded. Use for snapshot-to-simulation comparison.

**Schema version assertion (audit A8 — MANDATORY):** before parsing, check the JSON's `schema_version` field. This skill is compatible with `awlsim_tracer.py` schema `v1.0`. If the input declares a different schema, halt with explicit error rather than guessing — version drift between skills is a known audit risk.

```python
# Pseudo-code for the assertion:
import json
data = json.loads(tracer_output)
expected = "1.0"
got = data.get("schema_version")
if got != expected:
    raise ValueError(
        f"awlsim_tracer schema mismatch: expected {expected}, got {got}. "
        "Halting per Skill System Map compatibility rule."
    )
```

---

## Equipment-Focused Snapshot Analysis

When the user provides a snapshot and says "focus on K248" or similar:

1. **Identify** all instructions in the snapshot that reference the equipment's symbols.
2. **Trace** the register state through those instructions specifically.
3. **Identify** boundary signals — inputs from other equipment that affect this one.
4. **Explain** what the equipment is doing based on the register state.
5. **Diagnose** — if there's a problem, trace to the root cause within the visible snapshot.

If the snapshot doesn't show enough of the logic chain:
- Ask the user for additional networks / screenshots, OR
- Suggest using `awlsim-runner` Mode 2 (follow to root) to simulate the full dependency chain.

---

## Fault Finding Workflow

When the user says "this output should be ON but it's OFF":

1. **Find the output instruction** — look for `= "OutputName"` or `= Q x.y`.
2. **Check RLO** at that instruction — if RLO=0, the output is correctly OFF from the CPU's perspective.
3. **Trace backward** from the output:
   - Find the nearest RLO transition (1→0).
   - That instruction "killed" the output.
4. **Explain the killing instruction:**
   - What bit/value caused it?
   - Is that bit/value correct for the current process state?
5. **Continue tracing upstream** if needed:
   - The blocking condition itself may depend on other logic.
   - Follow the dependency chain until reaching a physical input, SCADA command, or analog value.
6. **Diagnose:**
   - "The valve is OFF because [signal X] is [TRUE/FALSE] at [instruction N]"
   - "Signal X comes from [DB.field] which represents [physical meaning]"
   - "This is [normal/abnormal] because [process context]"

---

## Snapshot-to-Simulation Pipeline

This bridges live PLC data with the `awlsim-runner` simulator:

1. **User provides** a debug snapshot (screenshot or text).
2. **Claude parses** the register states using this skill.
3. **Claude extracts** key values as trace assertions:
   - RLO at critical decision points
   - ACCU1 values for analog comparisons (decoded as REAL via `register-reference.md`)
   - DB numbers at CALL boundaries
4. **Claude builds** a test using `awlsim_tracer.py` (from `awlsim-runner`):
   - Set the same input conditions shown in the snapshot.
   - Run the code with `--trace-format json`.
   - Add `--expect-trace` with assertions extracted from the snapshot.
5. **Claude reports** differences:
   - Simulator matches → snapshot is consistent with the code.
   - Simulator differs → possible causes: timing, external data changes, code version mismatch.

---

## Working with other skills

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│    awl-step7        │     │  awl-plc-debugger    │     │   awlsim-runner     │
│                     │     │  (this skill)        │     │                     │
│ Static Analysis     │     │ Live State Analysis  │     │ Simulation          │
│ - Code review       │────→│ - Snapshot parsing   │────→│ - Compile & run     │
│ - Edge cases        │     │ - Register decoding  │     │ - Instruction trace │
│ - Pattern compare   │     │ - Fault finding      │     │ - Test assertions   │
│ - RCA fault tree    │     │ - RLO flow tracing   │     │ - Trace comparison  │
│                     │←────│ - Diagnosis          │←────│                     │
└─────────────────────┘     └──────────────────────┘     └─────────────────────┘
```

- **`awl-step7`** — Use for understanding what the code SHOULD do. Static analysis, edge case identification, pattern comparison across similar equipment.
- **`awlsim-runner`** — Use for simulating code and reproducing scenarios. The `awlsim_tracer.py` script produces per-instruction register traces that can be directly compared against snapshots analyzed by THIS skill. The `sfb_rewriter.py` and `awl_dependency_mapper.py` scripts handle mechanical preparation of real-world AWL code for simulation.

### Combined workflows

**Workflow 1: Diagnose a Live Fault**
```
User uploads snapshot → THIS skill analyzes → identifies blocking condition
→ awl-step7 checks if it's a code bug → awlsim-runner reproduces with trace
```

**Workflow 2: Compare Live vs Simulated**
```
THIS skill parses snapshot → extracts register states as assertions
→ awlsim_tracer runs same code → compares trace instruction-by-instruction
→ differences reveal timing issues, code changes, or unexpected conditions
```

**Workflow 3: Equipment-Focused RCA**
```
User: "K248 didn't start — here's the debug view"
→ THIS skill: parses snapshot, finds RLO drops at AN K248_FAULT
→ awl-step7: compares K248 fault pattern against K201/K202/K209 (Cat 12 Pattern Consistency)
→ awlsim-runner: simulates with K248_FAULT=TRUE → confirms fault is hidden
→ Diagnosis: "K248's fault logic uses AND instead of OR — hardware faults are invisible"
```

**Workflow 4: Prove an Edge Case from Static Analysis**
```
awl-step7 identifies potential issue → awlsim-runner simulates → trace confirms
→ THIS skill compares against live PLC to verify it happens in production
```

---

## Acceptance fixtures

Three snapshot fixtures ship with this skill at `fixtures/`:
- `snapshot_motor_off.txt` — single-network analysis: motor commanded ON but output OFF; trace identifies blocking interlock.
- `snapshot_overflow.txt` — REAL overflow case: ACCU shows out-of-range value; OV bit set in STATUS word.
- `snapshot_mixed_db.txt` — multi-DB context switch: DB1/DB2 register values change across CALL boundary.

Each fixture has a sibling `.expected.json` documenting the expected analysis output. These are the AC-DBG-1 acceptance gate.

A `tracer_v1.json` sample is also shipped — used by AC-DBG-2 (schema_version assertion test).

---

## Skill System Map

This skill is part of the AWL/STL package (v1.2.0). Routing:

| User signal                                     | Route to                | Why                                |
|-------------------------------------------------|-------------------------|------------------------------------|
| "snapshot / debug view / register trace"        | THIS skill              | Live state analysis                |
| "why is output X off / why did K248 fail"       | THIS skill              | Fault finding                      |
| "what does this code do"                        | `awl-step7`             | Static analysis                    |
| "create new FB / FC"                            | `awl-step7`             | Authoring                          |
| "is this safe / what could go wrong"            | `awl-step7` + `awl-safety-critical` | Edge case + rules     |
| "run / simulate / verify"                       | `awlsim-runner`         | Dynamic verification               |
| "what does instruction X do"                    | `awl-language-reference`| Reference lookup                   |

### Shared artifacts and schema versions

| Artifact                              | Owner          | Schema | THIS skill must check |
|---------------------------------------|----------------|--------|------------------------|
| `awlsim_tracer.py` JSON output        | awlsim-runner  | v1.0   | YES — assert before parsing (audit A8) |
| `awlsim_runner.py` JSON output        | awlsim-runner  | v2.0   | NO (consumed by step7 instead) |
| `mnemonics.py` schema                 | awlsim-runner  | v1.0   | NO (used during code analysis) |

### Package version compatibility

| Skill                     | Compatible package versions       |
|---------------------------|------------------------------------|
| awl-plc-debugger@1.0.x    | awlsim-runner@1.2.x (tracer schema v1.0) |
