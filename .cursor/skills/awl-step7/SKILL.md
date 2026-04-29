---
name: awl-step7
description: Analyze and create Siemens STEP 7 STL/AWL code for S7-300/400 PLCs and PCS7 systems. Use whenever the user uploads .AWL files; asks what STL code does; requests a functional description; asks for edge case or safety review; asks to create, modify, refactor, or extend a Function Block (FB), Function (FC), Data Block (DB), or Organization Block (OB); or mentions SIMATIC Manager, PCS7, S7-300, or S7-400. Accepts English and German STL mnemonics, but analysis, generated code, and explanations are English-canonical with `stl_precheck.py` enforcement. Operates in Analysis Mode (existing code provided) or Authoring Mode (generative request). Always invokes `stl_precheck.py` before declaring code "fixed" or "ready" — a clean awlsim result alone is not sufficient (the FB 112 saga proved this).
---

# Siemens STEP 7 STL/AWL Analysis & Authoring Skill

## What this skill does

Primary workflow for STL/AWL code generation, review, refactor, and functional description. Operates in two explicit modes:

- **Analysis Mode** (existing code provided) — produces functional descriptions, edge-case reports, RCA analysis, improvement suggestions.
- **Authoring Mode** (generative request) — creates new FB/FC/DB blocks following project conventions, with mandatory safety patterns inserted.

Cross-skill role: this is the *workflow* skill. For passive checklists, see `awl-safety-critical`. For language lookup, see `awl-language-reference`. For execution, see `awlsim-runner`. For live debug snapshot parsing, see `awl-plc-debugger`.

---

## When to use / When NOT to use

| Situation                                         | Use THIS skill | Use instead          |
|---------------------------------------------------|----------------|----------------------|
| User uploads `.AWL` / `.STL` file                 | ✅              | —                    |
| User asks "what does this code do" / "explain"    | ✅              | —                    |
| User asks "find edge cases" / "what could go wrong" | ✅            | —                    |
| User asks "improve this" / "make it safer"         | ✅              | —                    |
| User asks "create a new FB / FC / DB / OB"         | ✅              | —                    |
| User asks "refactor this FB" / "modify this FC"    | ✅              | —                    |
| User asks "is this safe to download"               | ✅ (Analysis Mode + safety-critical rules) | — |
| User asks "what does instruction `XYZ` do"         | ❌              | `awl-language-reference` |
| User asks "PED vs PID — which is correct"          | ❌              | `awl-language-reference` |
| User asks "run / simulate / verify / test"         | ❌              | `awlsim-runner`      |
| User asks "decode this debug snapshot / register state" | ❌         | `awl-plc-debugger`   |
| User asks "why is this output OFF on the live PLC" | ❌              | `awl-plc-debugger`   |

---

## Mode routing rule

Apply this rule on every invocation:

1. **If the user provides existing AWL/STL code** (uploaded file or pasted) → enter **Analysis Mode FIRST**. Produce the analysis output (or at minimum a Block Overview) before proposing any modification.
2. **If the request is purely generative** ("create an FB for tank-level monitoring", "write an FC that does X") → enter **Authoring Mode**. Apply a template, fill in the placeholders, insert the mandatory safety patterns from `awl-safety-critical` (R0–R10).
3. **Hybrid requests** ("refactor this FB to add hysteresis", "fix the bug in this code, then add a fault-reset network") → run Analysis Mode first to establish baseline understanding, then transition to Authoring Mode for the changes. Do not propose changes before completing the Analysis baseline.

**Skipping the mode-routing rule must be logged in the response as `mode_routing: skipped` — never silent.**

---

## Diagnostic Discipline (mandatory before any fix proposal)

This checklist is the audit's E4 enhancement and exists to prevent the FB 112 saga (two wrong diagnoses before reaching ground truth). Apply it before proposing ANY fix:

1. **State the symptom verbatim.** Quote the user's words or the compiler's exact error message. Do not paraphrase.
2. **List ≥ 2 hypotheses.** Don't commit to one yet. Example for an FB 112-class compile error:
   - H1: missing semicolon
   - H2: wrong mnemonic (PED vs PID)
   - H3: address spacing
   - H4: wrong block type / declaration
3. **For each hypothesis, identify the cheapest distinguishing test.** Static (precheck) before dynamic (awlsim) before asking the user.
4. **Run the cheapest test first.** `stl_precheck.py --strict` is the first call. Often eliminates several hypotheses in one pass.
5. **Only after a hypothesis is confirmed** by a test, propose the fix. Cite which test confirmed it.
6. **If confidence < ~80% after testing,** ask the user one targeted clarifying question (e.g., "Is the project mnemonic mode EN or DE?") before applying any change.

**Skipping this checklist must be logged in the response as `diagnostic_discipline: skipped`.** A "compile clean" from awlsim alone is NOT sufficient evidence — the FB 112 saga proved this. Every fix proposal must cite both `stl_precheck.py` and `awlsim_runner.py` results.

---

## Analysis Mode protocol

Apply when existing AWL/STL is provided. Produce output in this order:

### Step 1 — Parse the block header

```
Block type:     FUNCTION_BLOCK / FUNCTION / DATA_BLOCK / OB
Symbolic name:  "T2O_CompressorControl"
TITLE:          [from TITLE = line]
Version:        [from VERSION : line]
Networks:       [count]
Lines:          [approximate]
```

### Step 2 — Map the interface

Read all VAR sections in order:

| Section      | What to document                            |
|--------------|---------------------------------------------|
| `VAR_INPUT`  | Each parameter: name, type, purpose         |
| `VAR_OUTPUT` | Each output: name, type                     |
| `VAR_IN_OUT` | Bidirectional parameters                    |
| `VAR` (FB)   | Static data grouped by STRUCT               |
| `VAR_TEMP`   | Temp vars (note any used before init — R6)  |

### Step 3 — Inventory networks

Build a quick table before deep-dive:

| Network | Title | Lines | Key ops    | Purpose (1 line) |
|---------|-------|-------|------------|------------------|
| 1       | …     | n     | SD, A, =   | …                |

### Step 4 — Trace control flow

- Map all jump labels and their sources.
- Identify unreachable paths.
- Note any `BEU` / `BEC` early exits.

### Step 5 — Resolve external symbols

List every symbolic reference:
```
"T2O_AnalogInputs".CR_10_PT_105.OUTV   → pressure input DB
"T2O_MCC_FieldData".P231A.Status.Running → motor run feedback
T 340                                   → on-delay timer (unique?)
```

If any symbol's purpose is unknown, **flag it** — never invent meaning.

### Step 6 — Network deep dive

For each network identify:
1. **Trigger** — what must be true to enter the logic
2. **Action** — what the network computes or sets
3. **Side effects** — timers started, latches set, outputs changed

### Step 7 — Compile output

Produce one of:
- **Functional Description** (default for "what does this do?") — see template below
- **Edge Case Report** (for "what could go wrong?") — apply Inlined Edge-Case Checklist
- **Improvement Suggestions** (for "improve this" / "review") — apply Inlined Improvement Patterns

### Functional Description output template

```
## Block Overview
- Type:                [FB/FC/OB/DB]
- Name:                "[symbolic name]"
- Title:               [from TITLE]
- Purpose:             [2–3 sentences in PROCESS terms, not PLC terms]
- Equipment / process: [what physical system this controls]

## Interface
### Inputs (VAR_INPUT)
[table: name | type | description]

### Outputs (VAR_OUTPUT)
[table: name | type | description]

### Static Data (FB only — VAR by STRUCT)
[per-struct table: SCADA / Control / Interlocks / Faults / others]

## External Dependencies
- Data Blocks (read):   [list]
- Data Blocks (write):  [list]
- Called Blocks:        [list with call type]
- Timers Used:          [list with type and preset]
- Direct I/O:           [list with address, direction, tag]

## Operating Modes
### Auto Mode
[Describe behaviour when #Control.AutoMode = TRUE]

### Manual Mode
[Describe SCADA-direct control behaviour]

### Fault / Safe State
[What happens when fault is active]

## Network-by-Network Analysis
### Network 1: [Title]
**Purpose:** [one sentence]
**Trigger:** [conditions to enter]
**Logic:** [plain English, not PLC mnemonics]
**Output:** [what gets set / reset / transferred]

[repeat for each network]

## Control Flow Summary
[paragraph or diagram of execution path]

## Summary: What This Block Controls
[5–8 sentences for a process engineer with no PLC knowledge]

## Known Gaps / Symbols Requiring Clarification
[anything that couldn't be determined from the code alone]
```

### Accuracy rules

1. Describe what the code **does**, not what comments claim it does.
2. If a jump makes code unreachable, state it explicitly.
3. If an external symbol's purpose is unknown, flag it — never invent.
4. S/R pairs — always identify which wins if both conditions are simultaneously true (last instruction in code wins).
5. `VAR_TEMP` variables have **undefined** values at block entry — flag any use before assignment.

---

## Equipment-Focused Edge Case Analysis

When the user asks about a **specific piece of equipment** (e.g., "find edge cases for K248"):

1. **Identify** all symbols related to the equipment tag across the entire FB
2. **Find** every network that reads or writes those symbols (primary networks)
3. **Trace upstream** dependencies — signals that feed into the equipment's logic
4. **Trace downstream** effects — what the equipment's outputs influence
5. **Apply the Inlined Edge-Case Checklist** to primary networks + dependency chain
6. **Apply Category 12 (Pattern Consistency)** explicitly — compare this equipment's logic against similar equipment in the same FB (e.g., K248 vs K201/K202/K209)

This produces a focused report ("3 issues affecting K248") rather than a survey ("12 issues across all equipment").

---

## Root Cause Analysis (RCA) Workflow

When the user has a specific live problem to investigate (e.g., "K248 didn't restart after a fault"):

1. **Identify the symptom** — which signal/output is wrong?
2. **Trace backward** from the symptom through the logic chain:
   - What sets/resets the relevant flag?
   - What conditions feed into that logic?
   - Follow each branch to its root (physical input, SCADA command, analog value).
3. **Build the fault tree** — document each branch as a potential cause.
4. **Check each branch against the Inlined Edge-Case Checklist** — especially:
   - Category 12 (Pattern Consistency) — is this equipment's logic inconsistent with similar equipment?
   - Category 4 (Boolean Logic) — S/R priority, RLO state at labels.
   - Category 5 (Control Flow) — unreachable code, missing jump targets.
5. **If simulation is available**, route to `awlsim-runner` to reproduce the scenario and verify which branch contains the fault.
6. **If a debug snapshot is available**, route to `awl-plc-debugger` to compare the code's expected behaviour with observed register state.

---

## Authoring Mode protocol

Apply when generating new code.

### Block type decision

| Request                                  | Block type            | Template                                  |
|------------------------------------------|-----------------------|-------------------------------------------|
| Stateful equipment control               | FB + Instance DB      | `templates/function_block.awl` + Instance DB |
| Stateless calculation or utility         | FC                    | `templates/function.awl`                  |
| Shared data / configuration              | Global DB             | `templates/data_block.awl`                |
| Extra instance of existing FB            | Instance DB only      | `templates/instance_db.awl`               |

### Authoring steps

1. **Confirm the block type** (table above).
2. **Confirm project mnemonic mode** (EN or DE) — ask the user if not specified.
3. **Open the appropriate template** from `templates/`.
4. **Replace every `[PLACEHOLDER]` token** before delivery — `stl_precheck.py` warns on any remaining.
5. **Apply VAR section convention**: `SCADA → Control → Interlocks → Faults → [Sequence] → PulseBits → [UDT instances]` (see Project Conventions below).
6. **Insert mandatory safety patterns** from `awl-safety-critical` rules R0–R10:
   - R1 overflow protection on every REAL arithmetic
   - R2 zero-guard before division
   - R3 hysteresis on analog interlocks
   - R4 edge detect on SCADA buttons + end-of-block reset
   - R5 fault-clear-conditional reset
   - R6 VAR_TEMP init before use
   - R7 SQRT/LN domain guard
   - R8 LOOP termination bound
7. **Add header comment block** with I/O assignments (see Project Conventions).
8. **Run `stl_precheck.py --strict`** before declaring code "ready". Cite output.
9. **Recommend `awlsim-runner` simulation** before download.
10. **Recommend Pre-Download Checklist** from `awl-safety-critical`.

### Compilation workflow

```
AWL Source → SIMATIC Manager → Compiled Block

Step 1: Create .AWL source file with block declaration.
Step 2: SIMATIC Manager → Sources → right-click → Insert New Object → External Source → Import .AWL.
Step 3: Compile (double-click source → menu Compile).
Step 4: Check output window — zero errors required.
Step 5: For FBs only — create Instance DB:
        Blocks → Insert New Object → Data Block → "Data block referencing a function block" → choose your FB.
Step 6: Add CALL statement in calling block (OB1 or parent FB):
        CALL "FBName", "InstanceDB_Name"
```

**Critical**: compiling a `FUNCTION_BLOCK` does **not** auto-create its Instance DB.

### Block types and what gets created

| AWL Declaration                | Compiles To  | Notes                                             |
|--------------------------------|--------------|---------------------------------------------------|
| `FUNCTION_BLOCK "Name"`        | FB           | Requires Instance DB for each call                |
| `FUNCTION "Name" : VOID`       | FC           | No instance data, stateless                       |
| `ORGANIZATION_BLOCK OB n`      | OB           | System-called blocks                              |
| `DATA_BLOCK DB n`              | Global DB    | Standalone data storage                           |
| `DATA_BLOCK DBn FBm`           | Instance DB  | Linked to specific FB                             |
| `TYPE "MyUDT"`                 | UDT          | User-defined type                                 |

### Symbol Table requirement

When using symbolic names (quoted), a Symbol Table entry must exist:

| Symbol           | Absolute | Data Type | Comment             |
|------------------|----------|-----------|---------------------|
| `"MyFB"`         | FB 100   | FB 100    | Description         |
| `"MyFB_Instance"`| DB 100   | FB 100    | Instance of MyFB    |
| `"MyFC"`         | FC 50    | FC 50     | Description         |

Without Symbol Table entries, fall back to absolute addressing: `CALL FB 100, DB 100`.

### Authoring Mode pre-delivery checklist

- [ ] Block name follows project naming convention
- [ ] TITLE line filled in (not template text)
- [ ] VERSION set to `0.1`
- [ ] VAR sections in correct order: `SCADA → Control → Interlocks → Faults → PulseBits`
- [ ] Spare variables included for future expansion
- [ ] SCADA pushbutton reset network is the LAST network of the FB
- [ ] All REAL literals in scientific notation (`5.000000e+000`)
- [ ] Timer pattern: SD/SE/etc. followed by 3× `NOP 0`
- [ ] Overflow protection on every REAL arithmetic (R1)
- [ ] Zero-guard before every division (R2)
- [ ] Jump labels follow `_NNN` hex sequence (4 chars max)
- [ ] No unreplaced `[PLACEHOLDER]` tokens
- [ ] Note delivered: "Compile, then manually create Instance DB"
- [ ] `stl_precheck.py --strict` exit 0

---

## Inlined Edge-Case Checklist

Severity ratings:

| Rating   | Definition                                                       |
|----------|------------------------------------------------------------------|
| CRITICAL | Could cause injury, equipment damage, or CPU STOP                |
| HIGH     | Could cause process failure or extended unplanned downtime       |
| MEDIUM   | Incorrect behaviour under specific conditions                    |
| LOW      | Code quality, readability, maintainability                       |

### Category 1: Startup & First Scan

- [ ] **Uninitialised VAR_TEMP** — any `L #TempVar` before `T #TempVar`? → HIGH (R6)
- [ ] **Instance DB initial values** — are critical setpoints set to safe defaults in DB BEGIN section?
- [ ] **Output state on cold restart** — do outputs power up in a safe state? (R0)
- [ ] **OB1_SCAN_1** — is one-time initialisation guarded by first-scan flag if needed?

### Category 2: Arithmetic

- [ ] **Division by zero** — every `/R`, `/I`, `/D` — divisor checked for ≠ 0? → CRITICAL (R2)
- [ ] **Overflow after `+R/-R/*R//R`** — `AN OV; SAVE; CLR; A BR` present after every REAL op? → HIGH (R1)
- [ ] **INT overflow** — counter or accumulator could reach ±32767?
- [ ] **REAL precision** — subtraction of near-equal values causes precision loss?
- [ ] **Negative REAL into SQRT / LN** — result is invalid (unordered); `JUO` needed? → HIGH (R7)
- [ ] **TRUNC/RND range** — REAL value could be outside DINT range before conversion?

### Category 3: Timers & Counters

- [ ] **Timer number conflicts** — `T 340` used in this block AND another block? (Global resource)
- [ ] **Timer preset in range** — S5T max is 9990s; does preset exceed?
- [ ] **SD vs SE/SS** — SD cancels if enable removed before timeout; SE and SS do not (retentive). Correct timer type?
- [ ] **Counter at limits** — CU at 999 stays at 999; CD at 0 stays at 0. Does logic depend on wrap?
- [ ] **SS never resets automatically** — SS requires explicit `R T n` to clear. Reset path present?

### Category 4: Boolean Logic

- [ ] **4.1 — S/R priority** — if both Set and Reset conditions are simultaneously true, which wins? (Last instruction wins.)
- [ ] **4.2 — FP on noisy signal** — input debounced? FP fires on every glitch.
- [ ] **4.3 — RLO state at label** — after a label, RLO is the value from before the jump. Code after label safe regardless of RLO?
- [ ] **4.4 — OR before AND** — `O; A ...` creates implicit OR group. Intended precedence?
- [ ] **4.5 — Missing CLR** — after complex bracket expressions, RLO may be 1 from a previous path. Is CLR or SET used when needed?

### Category 5: Control Flow

- [ ] **5.1 — Unreachable code** — any code after `JU` / `BEU` with no label pointing into it?
- [ ] **5.2 — Missing jump target** — every `JC _xxx` has a corresponding `_xxx: NOP 0`?
- [ ] **5.3 — JNB path** — code up to `_001` is skipped if BR=0. Is the skipped code safe to bypass?
- [ ] **5.4 — BEC in wrong place** — `BEC` exits the block if RLO=1. Premature exit leaves outputs in undefined state?
- [ ] **5.5 — LOOP termination** — ACCU1-L value guaranteed to eventually reach 0? (R8)

### Category 6: Analog Signals

- [ ] **Sensor fail low** — 4–20mA at 0mA (broken wire) reads as 0%. Safe value for this process?
- [ ] **Sensor fail high** — saturated at max. Control logic handles?
- [ ] **No deadband on interlock** — analog interlocks without hysteresis chatter at threshold. ±5 unit deadband applied? → CRITICAL (R3)
- [ ] **Invalid input propagates** — bad sensor → bad calculation → wrong actuator command?
- [ ] **Scale limits** — raw analog could produce physically impossible engineering units?

### Category 7: Data Blocks

- [ ] **DB not open** — `DBW 0` accessed without prior `OPN DB n`? (Symbolic access is fine.)
- [ ] **Wrong DB open** — OPN DB called with wrong number?
- [ ] **Instance DB mismatch** — was FB modified since last Instance DB regeneration? Mismatched DB causes wrong data offset.
- [ ] **Array out of bounds** — `#Array[n]` where n could be 0 or > declared upper bound?
- [ ] **DB length** — accessing offset beyond DB length causes CPU fault.

### Category 8: Multi-block Interaction

- [ ] **Timer shared between blocks** — same `T n` used in FB called multiple times? Each call overwrites the same timer.
- [ ] **Global memory race** — M area bits written by this block and read by another OB-level block? Read mid-update?
- [ ] **Output written by two blocks** — two FBs writing the same Q bit or DB field?
- [ ] **SCADA write race** — WinCC can write SCADA struct; block can overwrite same scan. Are buttons reset at end of block? (R4)

### Category 9: SCADA / HMI Interface

- [ ] **Pushbuttons not reset** — SCADA buttons must be reset at end of FB. → CRITICAL (R4)
- [ ] **Setpoint range not checked** — operator could enter 0 as setpoint for a divide?
- [ ] **Manual mode output range** — in manual, can operator drive output to a damaging value?
- [ ] **Fault reset without checking fault cleared** — `FaultReset_PB` clears latch without verifying condition gone? → CRITICAL (R5)

### Category 10: Safety Interlocks

- [ ] **OR bypass** — interlock chain uses OR where AND was intended? Single TRUE bypasses protection.
- [ ] **Latching interlock** — can interlock reset automatically without operator acknowledgement?
- [ ] **Power loss state** — outputs on STOP go to 0 (or last value)? Safe state? (R0)
- [ ] **Interlock on wrong signal type** — latching interlock driven by momentary signal that may not be present when fault occurs?
- [ ] **ESTOP path** — emergency stop hardwired (hardware) AND represented in software? (R10)

### Category 11: Code Quality (LOW severity)

- [ ] Comments match code behaviour (outdated comments after edits)
- [ ] Network TITLE accurately describes the network
- [ ] Dead code present (networks that can never execute)
- [ ] Duplicate logic across networks (same condition evaluated twice)
- [ ] Temp variable named misleadingly
- [ ] Spare variables declared but never used or documented
- [ ] BLD instructions consistent with local bit pattern

### Category 12: Pattern Consistency (NEW — closes validation H3)

When a single FB controls multiple instances of the same equipment class (e.g., compressors K201/K202/K209/K248), every instance should follow the same patterns. Inconsistencies are a strong RCA signal.

- [ ] **12.1 — Identical signal handling across instances** — is every K-unit's `_FAULT` signal handled with the SAME instruction (`A` vs `O`, `AN` vs `ON`)? Mixed `A` and `O` for similar fault aggregation across instances is a CRITICAL bug. (This is the K248 fault inversion class — found in CONTEXT-3.)
- [ ] **12.2 — Consistent timer presets across same-class equipment** — if K201 uses `S5T#10S` for run-feedback timeout, do K202/K209/K248 use the same preset? Mismatches without documentation are MEDIUM.
- [ ] **12.3 — Consistent edge-detect vs level-trigger** — every SCADA pushbutton across all instances uses `FP` (edge), not bare `A` (level)? Mixing is a HIGH bug.
- [ ] **12.4 — Consistent reset-condition gating** — every fault reset uses the same `AN <fault_condition>` guard pattern from R5? Mismatches across instances are HIGH.

### Reporting format

For each issue found:

```
### [SEVERITY]: Short Description

**Location:** Network [N], Lines [X]–[Y]
**Code:**
      [snippet]

**Issue:** What the problem is.
**Scenario:** When/how this edge case is triggered.
**Impact:** What happens when triggered.
**Rule violated:** [R0–R10 if applicable]
**Recommendation:** How to fix it (with example code if needed).
```

---

## Inlined Improvement Patterns (selected)

Drawn from the modular pack `improvement-patterns.md`. Common improvements found in S7-300/400 STL code:

1. **Missing overflow protection** — wrap REAL arithmetic with R1 pattern.
2. **Analog interlock without hysteresis** — apply R3 S/R latch with deadband.
3. **SCADA pushbutton not reset** — apply R4 `FP #PulseBits[n]` + end-of-block reset.
4. **Division by zero risk** — apply R2 explicit zero-guard.
5. **Uninitialised VAR_TEMP** — apply R6 `L 0.0; T #Temp` init.
6. **S/R priority ambiguity** — restructure to make priority explicit, document inline (Documentation Rule).
7. **Timer number may conflict** — prefer symbolic timer names or IEC TON multi-instance.
8. **Missing fault acknowledgement guard** — apply R5 `AN <condition>` before reset.
9. **Complex nested bracket — readability** — use local bit (`= L 22.0`) to store intermediate result.

For each, see `awl-safety-critical` for the canonical pattern. This skill applies them; it does not redocument them.

### Improvement report format

```
### Improvement: [Short Name]

**Severity:** LOW / MEDIUM / HIGH
**Location:** Network [N]
**Issue:** Description of current problem.
**Risk:** What could happen if left unchanged.
**Suggested change:**

      [before code snippet]

→ Replace with:

      [after code snippet]

**Rule applied:** [R0–R10 if applicable]
```

---

## Project Conventions (inlined — replaces broken `project-style-guide.md`)

### Rule #1
**Always match existing project style.** When editing existing code, mirror the patterns already in that block exactly — spacing, label format, comment style, STRUCT layout. Never introduce new patterns without explicit direction.

### Block naming

| Block             | Pattern                            | Examples                                    |
|-------------------|------------------------------------|---------------------------------------------|
| FB (equipment)    | `"[Area]_[Equipment][Tag]"`        | `"T2O_CrystaliserT209A"`                    |
| FB (interface)    | `"[Area]_[System]Interface"`       | `"T2O_MCCInterface"`                        |
| FB (control)      | `"[Area]_[Tag]_[Function]"`        | `"T2O_T261_pH_Control"`                     |
| FC                | Action + subject                   | `"Transport_product"`                       |
| DB (data)         | Descriptive shared name            | `"T2O_AnalogInputs"`, `"T2O_MCC_FieldData"` |
| DB (instance)     | FB name + tag                      | `"T2O_CompressorControl_DB"`                |
| SCADA tags        | `[Area].[Tag].[Property]`          | `T2OldPlant.T209A_FaultReset`               |

### VAR section layout (every FB)

```awl
VAR
  SCADA : STRUCT          // 1st: HMI setpoints, buttons, display values
  Control : STRUCT        // 2nd: Internal mode flags, commands
  Interlocks : STRUCT     // 3rd: Safety interlock conditions
  Faults : STRUCT         // 4th: Alarm and fault flags
  [Sequence : STRUCT]     // 5th: Sequential state (if used)
  PulseBits : ARRAY [1..n] OF BOOL   // Last: edge detection storage
  [UDT instances]         // Multi-instance FBs
END_VAR
VAR_TEMP
  Temp_Real : REAL;
  Temp_Int  : INT;
  TEMP_Dint : DINT;
END_VAR
```

Always include **Spare variables** for future expansion (`Spare1_4 : BOOL;`, `SpareReal_1 : REAL;`).

### Jump label conventions

- **Hex sequence (primary)** — used for arithmetic/logic flow control: `_001, _002, ..., _009, _00a, _00b, _00f, _010, _011, ...`
- **Named labels (major flow)** — used for significant control flow points: `SKP1`, `SKP2`, `Exit`, `TOUT`, `EINT`. Max 4 chars preferred; precheck WARNs > 16.

### Local bit pattern (BLD 102/103)

Store intermediate Boolean result for reuse and LAD/FBD display:
```awl
      [condition logic];
      =     L     22.0;        // Store to local byte 22, bit 0
      A     L     22.0;
      BLD   102;               // Display hint (no logic effect)
      =     #Output1;
```

Common local bit addresses: `L 22.0`, `L 22.1`, `L 23.0`, `L 23.4`, `L 10.0`, `L 8.0`. `BLD 102` is the standard display directive; `BLD 103` is used before CALL instructions.

### S5 timer pattern (project convention — 3× NOP 0 after SD/SE)

```awl
      A     [enable];
      L     S5T#10S;
      SD    T 340;
      NOP   0;
      NOP   0;
      NOP   0;
      A     T 340;
      =     #TimedOutput;
```

### IEC timer multi-instance pattern (preferred over absolute T-numbers — see Improvement Pattern #7)

```awl
VAR
  K208_TimerOn : "TON";
END_VAR

      A     #Enable;
      =     L     8.0;
      BLD   103;
      CALL  #K208_TimerOn (
           IN                       := L      8.0,
           PT                       := T#15S);
      A     #K208_TimerOn.Q;
```

### Pulse edge detection

```awl
      A     #SCADA.AutoMode_PB;
      FP    #PulseBits[1];       // Rising edge
      S     #Control.AutoMode;
```

Each `FP`/`FN` needs its own `PulseBits[n]` element — never reuse for two signals.

### CALL parameter formatting

Parameters column-aligned at position 33 before `:=`:
```awl
      CALL  #P228 (
           STP_PB                   := "P228.STP",
           STR_PB                   := "P228.STR",
           ESTOP                    := TRUE,
           Reset                    := "SCADAData".T2OldPlant.PlantReset);

```
Blank line after closing parenthesis.

### Symbolic addressing

Always prefer symbolic over absolute:
```awl
"T2O_AnalogInputs".CR_10_TT_103.OUTV     // DB.struct.member
"T2O_MCC_FieldData".P231A.Status.Running  // Nested struct
"Flash_5"                                  // Global bit (system clock)
"SCADAData".T2OldPlant.T209A_FaultReset   // WinCC tag reference
#SCADA.AutoMode_PB                         // This FB's instance data
#PulseBits[3]                              // Array element
```

### Numeric literal formats

| Type     | Format               | Examples                                              |
|----------|----------------------|-------------------------------------------------------|
| REAL     | Scientific 6 decimal | `5.000000e+000`, `1.000000e+002`, `-2.500000e+001`    |
| WORD hex | `W#16#`              | `W#16#00FF`, `W#16#8010`                              |
| BYTE hex | `B#16#`              | `B#16#0`, `B#16#FF`                                   |
| S5TIME   | `S5T#`               | `S5T#10S`, `S5T#2H`, `S5T#500MS`                      |
| IEC TIME | `T#`                 | `T#15S`, `T#10M`                                      |

### Network organisation (typical FB)

1. Mode selection (Auto/Manual from SCADA pushbuttons)
2. Auto-mode device parameter setup
3. Interlock calculations (with hysteresis — R3)
4. Control logic
5. Fault detection
6. Output assignments
7. Alarm / siren handling
8. **SCADA pushbutton resets — always last network** (R4)

### End-of-block reset pattern (mandatory — R4)

Last network of every FB:
```awl
NETWORK
TITLE =Reset SCADA Pushbuttons

      SET   ;
      R     #SCADA.AutoMode_PB;
      R     #SCADA.FaultReset_PB;
      R     #SCADA.ManualStart_PB;


END_FUNCTION_BLOCK
```
Two blank lines before `END_FUNCTION_BLOCK`.

### Header comment block (I/O-intensive FBs)

```awl
//
// Equipment I/O Assignment:
// I 330.0   10-LSL-102   Seal water level low
// I 330.1   10-ST-106    Agitator speed pulse
//
// PIW 572   10-TT-103    Temperature input
// PQW 568   10-TV-103    Temperature control valve output
//
// Q 329.0   10-TXY-103   Temperature plug control valve
//
```

### Encoding & whitespace

- **Encoding**: windows1252 / cp1252 (SIMATIC native). UTF-8 BOM is rejected — `stl_precheck.py` WARNs.
- **Indent**: instruction lines indented 6 spaces. Precheck INFOs other indents.
- **Trailing whitespace**: do NOT trim — column alignment matters in CALL parameters.

---

## Most-Used Instructions Quick Reference

For full instruction set with semantics and ACCU effects, see `awl-language-reference`.

| Instruction          | Description                                       |
|----------------------|---------------------------------------------------|
| `A` / `AN`           | AND / AND NOT (German: `U` / `UN`)                |
| `O` / `ON`           | OR / OR NOT (same in DE)                          |
| `=`                  | Assign RLO to operand                             |
| `S` / `R`            | Set / Reset                                       |
| `L` / `T`            | Load / Transfer                                   |
| `JU` / `JC` / `JCN`  | Jump Unconditional / Conditional / Conditional Not (German: `SPA` / `SPB` / `SPBN`) |
| `JNB`                | Jump if Not BR (German: `SPBNB`)                  |
| `FP` / `FN`          | Positive / Negative edge detection                |
| `A(` / `)`           | Open / Close bracket (nested logic)               |
| `CALL`               | Call FB/FC with parameters                        |
| `BLD`                | Compiler directive (display in LAD/FBD)           |
| `NOP 0`              | No operation                                      |
| `SET` / `CLR`        | Set RLO to 1 / 0                                  |
| `SAVE`               | Save RLO to BR                                    |

---

## Peripheral I/O Mnemonics — English vs German (CRITICAL — FB 112 trap)

The peripheral input/output area has **two completely different mnemonic sets**. Both are valid Siemens-supported syntax. This is the FB 112 saga's D1 confusion point.

| Width      | English (STL) | German (AWL) |
|------------|---------------|--------------|
| Byte (input)  | `PIB`      | `PEB`        |
| Word (input)  | `PIW`      | `PEW`        |
| DWord (input) | `PID`      | `PED`        |
| Byte (output) | `PQB`      | `PAB`        |
| Word (output) | `PQW`      | `PAW`        |
| DWord (output)| `PQD`      | `PAD`        |

**Address spacing**: Both `L PID 1628;` (with space) and `L PID1628;` (no space) are valid — SIMATIC Manager accepts either form. (This was the FB 112 D2 phantom diagnosis.)

**Mnemonic policy**: per project English-canonical policy, accept German input when encountered but normalize processing, explanations, and generated code to English STL. `stl_precheck.py` flags MIXED_INSTRUCTIONS in a single file. See Project Mnemonic Mode below and the canonical EN↔DE peripheral table in `awl-language-reference/references/instructions-german.md`.

---

## Project Mnemonic Mode

This skill handles BOTH English STL and German AWL mnemonics as input, with English-canonical output.

- **EN-only file** (e.g., `PID`, `A`, `AN`, `JU`, `OPN`): supported. Default project mode.
- **DE-only file** (e.g., `PED`, `U`, `UN`, `SPA`, `AUF`): supported. Equally valid Siemens syntax.
- **MIXED_INSTRUCTIONS** (EN and DE in same block): `stl_precheck.py` emits a WARN with line citations. `awlsim_runner.py` halts with `--accept-mixed-mnemonics` required to bypass; the override is logged to `~/.awl/precheck_audit.jsonl`. step7 Analysis Mode must surface this warning prominently before proposing any fix.
- **MIXED_COMMENTS_ONLY** (EN instructions, DE diacritics in comments): INFO only — normal for PCS7 plants where the engineering installation is German but the project standard is English STL.

To set project mode: pass `--project-mode EN|DE|MIXED` to `stl_precheck.py`. Default is `MIXED` (no enforcement). For new code authoring, ask the user which mode the project uses before generating.

---

## Important Reminders

These reminders are the audit's E3 enhancement — promoted from documentation warnings to mandatory workflow rules.

1. **Mnemonic mode**: this skill accepts both English (`PID/PIW/PIB`) and German (`PED/PEW/PEB`) mnemonics as input, but generated code and explanations use English STL canonical form. `stl_precheck.py` auto-detects per file; mixed *instruction* mnemonics in a single block emit a WARN that requires explicit `--accept-mixed-mnemonics` to bypass. EN instructions with DE comments (containing diacritics like ä/ö/ü/ß) are normal PCS7 — INFO only. See "Project Mnemonic Mode" and the Peripheral I/O table above.

2. **Instance DBs are separate** — Compiling an FB does NOT auto-create its Instance DB. Manually create via `Insert New Object → Data Block → "Data block referencing a function block"`.

3. **Symbolic names require Symbol Table** — Absolute addresses work without it.

4. **BLD instructions are display hints** — They don't affect logic execution.

5. **NOP 0 after timers** — Project convention uses 3× NOP after S5 timer SD/SE/etc.

6. **Check overflow after arithmetic** — Real number operations can overflow → CPU STOP. Apply R1 pattern.

7. **Source file semicolons are mandatory** — Every instruction line in a `.AWL`/`.STL` source file MUST end with `;`. The SIMATIC Manager online STL editor tolerates omission; the source file compiler does not. Missing semicolons cause cascading syntax errors. **`stl_precheck.py` catches this directly — this was the true FB 112 root cause (D3).**

8. **awlsim is more permissive than SIMATIC Manager** — awlsim accepts German mnemonics, missing semicolons, and looser address formatting without error. **A clean awlsim compile does NOT guarantee a clean SIMATIC Manager compile.** **The mandatory rule** (audit E3): before claiming an AWL source is "compile-clean" or "fixed", run BOTH `stl_precheck.py --strict` AND `awlsim_runner.py`. A clean awlsim result alone is not sufficient evidence — the FB 112 incident proved this. If precheck reports FAIL, do not even attempt the awlsim run.

---

## File Locations in Project Knowledge

The following Siemens documentation may be available in project knowledge:
- `Siemens_Step7_STL_Statement_List.md` — Official STL reference
- `Siemens_Getting_Started_with_STEP_7.md` — Block creation tutorials
- `STEP_7_-_Configuring_Hardware_with_STEP_7.md` — Hardware configuration
- `STEP_7_V5_7_SP1_README.md` — Version notes and known issues
- `PCS7_Open_OS_Workflow_Guide_en.md` — PCS7 OS integration

Search project knowledge for specific Siemens documentation when needed.

---

## Getting Help

If analysis seems incomplete or uncertain:

1. Ask user for Symbol Table entries for unknown symbols.
2. Ask user for related DB structures.
3. Ask user for context about the process being controlled.
4. Search project knowledge for Siemens documentation.
5. Route to `awl-language-reference` for mnemonic/syntax questions.
6. Route to `awlsim-runner` for "does this run" / "what happens when X" questions.
7. Route to `awl-plc-debugger` for live debug snapshot interpretation.

---

## Skill System Map

This skill is part of the AWL/STL package (v1.2.0). Routing:

| User signal                                  | Route to                                | Why                                         |
|----------------------------------------------|-----------------------------------------|---------------------------------------------|
| "what does this code do" / .AWL upload       | THIS skill (Analysis Mode)              | Static analysis                             |
| "create / write / refactor FB / FC / DB"     | THIS skill (Authoring Mode)             | Code generation                             |
| "find edge cases / safety review"            | THIS skill (Analysis Mode + safety-critical rules) | Edge-case checklist + R0–R10 |
| "RCA: why did K248 not start"                | THIS skill (RCA Workflow)               | Backward trace from symptom                 |
| "is this safe to download to plant"          | THIS skill + `awl-safety-critical` Pre-Download Checklist | Combined |
| "run / simulate / verify code"               | `awlsim-runner`                         | Dynamic verification                        |
| "decode debug snapshot / RLO trace"          | `awl-plc-debugger`                      | Live register-state analysis                |
| "what does <instruction> do"                 | `awl-language-reference`                | Reference lookup                            |
| "PED vs PID — which is correct"              | `awl-language-reference`                | Mnemonic mapping                            |

### Shared artifacts and schema versions

| Artifact                                     | Owner          | Schema | THIS skill must check |
|----------------------------------------------|----------------|--------|------------------------|
| `stl_precheck.py` JSON output                | awlsim-runner  | v1.0   | YES — before any fix proposal |
| `awlsim_runner.py` JSON output               | awlsim-runner  | v2.0   | YES — before "ready" claim |
| `mnemonics.py` schema                        | awlsim-runner  | v1.0   | YES — peripheral I/O table source |
| Rules R0–R10 + Documentation Rule            | awl-safety-critical | v1.0 | YES — cited by ID in fix proposals |

### Package version compatibility

| Skill                | Compatible package versions                                         |
|----------------------|----------------------------------------------------------------------|
| awl-step7@1.2.x      | awlsim-runner@1.2.x, awl-language-reference@1.x, awl-safety-critical@1.x |
