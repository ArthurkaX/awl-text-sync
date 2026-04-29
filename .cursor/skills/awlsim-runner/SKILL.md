---
name: awlsim-runner
description: Compile, simulate, and verify Siemens STEP 7 AWL/STL code using the vendored awlsim open-source PLC simulator. Use whenever the user asks to run, test, execute, simulate, or verify PLC code; wants to prove logic correctness; asks "does this code work"; "show me what happens when"; wants unit tests or assertions for PLC logic; or has just generated AWL via awl-step7 and needs verification before delivery. Step 0 of every run is mandatory stl_precheck.py — awlsim alone is not sufficient because it is more permissive than SIMATIC Manager (the FB 112 saga proved this). Accepts English and German STL mnemonics with auto-detection, but processing and generated output are English-canonical.
---

# awlsim-runner — Compile + Simulate + Verify

## What this skill does

Wraps the vendored awlsim simulator (SHA-pinned at `b02373bc`) to provide:

- **Compile** — parse AWL source, report errors with line numbers.
- **Simulate** — run OB1 cycles with pre-set inputs, read back M / I / Q / DB memory, decode REAL as IEEE 754.
- **Verify** — assertion checking with `--expect` and `--tolerance`, structured JSON output.
- **Test harness** — auto-generate OB1 wrapper + instance DB from FB interface for standalone testing.
- **Multi-instance SFB rewrite** — `sfb_rewriter.py` handles `#Timer.Q` paths that awlsim doesn't natively support.
- **External symbol stubbing** — `awl_dependency_mapper.py` maps and stubs external DBs / I/O symbols.
- **Round-trip pattern diff** — `pattern_diff.py` for canonical-form normalization across EN/DE.

This is the **dynamic verification** skill. For static analysis, route to `awl-step7`. For live debug snapshots, route to `awl-plc-debugger`.

## When to use / When NOT to use

| Situation                                                    | Use THIS skill | Use instead              |
|--------------------------------------------------------------|----------------|--------------------------|
| User asks "run / simulate / execute / test / verify"         | ✅              | —                        |
| User asks "does this code work" / "show what happens when"   | ✅              | —                        |
| User asks "prove this logic is correct"                      | ✅              | —                        |
| User asks for unit tests / assertions on PLC logic           | ✅              | —                        |
| User wants to verify a generated FB before delivering        | ✅              | —                        |
| User wants snapshot-to-simulation comparison                 | ✅ + `awl-plc-debugger` | combined                |
| User asks for static analysis without running code           | ❌              | `awl-step7`              |
| User has live debug snapshot to decode                       | ❌              | `awl-plc-debugger`       |
| User asks for instruction semantics                          | ❌              | `awl-language-reference` |
| User wants to write or refactor code                         | ❌              | `awl-step7`              |

---

## CRITICAL: Mandatory workflow order

**The audit's E3 enhancement: a clean awlsim result alone is NOT evidence of correctness. The FB 112 saga proved this. awlsim is more permissive than SIMATIC Manager — it accepts German mnemonics, missing semicolons, and looser address formatting that SIMATIC rejects.**

Every code execution follows this **exact** order:

### Step 0 — `stl_precheck.py` (MANDATORY GATE)

Before any awlsim call on user-supplied source:

```bash
python3 stl_precheck.py \
  --source-file <FILE.awl> \
  --mnemonics AUTO \
  --project-mode <EN|DE|MIXED> \
  --strict \
  --format json
```

**Halt rules:**
- If precheck exits non-zero (any FAIL) → **STOP**. Report FAILs to user. Do NOT call awlsim.
- If precheck reports `mnemonics: MIXED_INSTRUCTIONS` and the user has not passed `--accept-mixed-mnemonics` → **STOP**. Report the warning. Ask the user to confirm before passing the flag.
- If precheck reports `encoding != windows1252` → WARN but allow (fixture files in tests may be UTF-8).

**Override (logged):** `--bypass-precheck` skips Step 0. Every override appends to `~/.awl/precheck_audit.jsonl`. Use only when the user has explicitly acknowledged the risk.

### Step 1 — `detect_block.py`

Identify what the file is and recommend the pipeline:

```bash
python3 detect_block.py <FILE.awl>
# → returns JSON: { block_type: "FB", block_number: 112, has_sfb_timers: false, ...,
#                   recommended_pipeline: ["stl_precheck", "detect_block",
#                                          "awl_dependency_mapper",
#                                          "sfb_rewriter",
#                                          "test_harness_generator", "awlsim_runner"] }
```

Follow `recommended_pipeline`. Don't manually choose tools when this script can route them deterministically.

### Step 2 — Dependency stubbing (when external refs exist)

```bash
python3 awl_dependency_mapper.py --source <FILE.awl> --emit-stubs
# Generates stub DBs and I/O symbol shims for awlsim
```

### Step 3 — SFB rewrite (when multi-instance timers exist)

```bash
python3 sfb_rewriter.py --source <FILE.awl> --output <FILE_rewritten.awl>
# Rewrites #Timer.Q → absolute DB.DBX offsets
```

### Step 4 — Test harness generation (for standalone FB/FC)

```bash
python3 test_harness_generator.py --source <FB.awl> --emit-ob1
# Generates OB1 wrapper + instance DB for standalone simulation
```

### Step 5 — Smoke pre-flight (first run per session)

```bash
python3 test_wrapper.py --smoke
# 3 fast tests: compile / BOOL roundtrip / REAL roundtrip. <2s.
# Halt if smoke fails — awlsim has drifted upstream.
```

### Step 6 — Run

```bash
python3 awlsim_runner.py \
  --source <FILE.awl> \
  --cycles 10 \
  --set-inputs '{"M0.0": true, "MD100": {"type": "REAL", "value": 25.0}}' \
  --read 'MD200:REAL,Q4.0:BOOL' \
  --expect '{"MD200": 50.0}' --tolerance 0.001 \
  --format json
```

### Step 7 — Pattern diff (when round-trip validation requested)

```bash
python3 pattern_diff.py --left <FILE.awl> --right <FILE_after_compile.awl>
# Compares two .AWL files semantically (ignoring whitespace, label renumbering, etc.)
```

---

## CLI surface — `awlsim_runner.py`

Frozen by PRD G1–G7 + locked-in additions:

```
--source FILE
--cycles N                      # default 10
--set-inputs JSON               # implicit-typed (legacy)
--set-inputs-typed JSON         # explicit-typed: [{"addr":"MD100","type":"REAL","value":12.5}, ...]
--set-db JSON | --set-db-typed JSON
--read SPEC                     # comma-separated, e.g. "MD200:REAL,Q4.0:BOOL"
--read-typed JSON               # equivalent typed form
--cpu-type S7-300|S7-400        # default S7-300
--mnemonics EN|DE|AUTO          # default AUTO (precheck detects)
--accept-mixed-mnemonics        # required if precheck reports MIXED_INSTRUCTIONS
--bypass-precheck               # skips Step 0 — every use logged to precheck_audit.jsonl
--expect JSON --tolerance N
--test-scenario JSON            # multi-step set→run→assert sequence
--format human|json|table       # default json
--virtual-time-ms-per-cycle N   # advance simulator clock by N ms per cycle (no real sleep)
--version
```

## JSON output schema (v2.0 — bumped from v1.x)

```json
{
  "schema_version": "2.0",
  "status": "ok|fail|error",
  "precheck": {
    "schema_version": "1.0",
    "mnemonics": "EN|DE|MIXED_INSTRUCTIONS|MIXED_COMMENTS_ONLY",
    "fail_count": 0,
    "warn_count": 0,
    "info_count": 0
  },
  "compile_messages": [],
  "cycles_executed": 10,
  "results": [
    {"cycle": 1, "reads": {"MD200": 50.0, "Q4.0": true}}
  ],
  "assertions": [
    {"name": "totalizer_correct", "addr": "MD200", "expected": 50.0, "actual": 50.0, "tolerance": 0.001, "pass": true}
  ],
  "db_layouts": {
    "DB1": [
      {"name": "Voltage_L1", "offset": "+0", "type": "REAL"},
      {"name": "Status",     "offset": "+4", "type": "DWORD"}
    ]
  },
  "test_result": "pass|fail|error",
  "error": null
}
```

Consumers (`awl-step7`, `awl-plc-debugger`) MUST check `schema_version` before parsing.

---

## Pinned dependencies and reproducibility

- awlsim source: `https://github.com/mbuesch/awlsim.git` at SHA `b02373bc`.
- Install via `install_awlsim.sh` — clones, verifies, sets `PYTHONPATH=/home/claude/awlsim`.
- VERSION file at the skill root pins our own runner version (currently `1.2.0`).
- Python ≥ 3.8 required.

---

## Known limitations (locked-in by PRD NG1–NG6)

| Limitation                                    | Status   | Workaround                                   |
|------------------------------------------------|----------|----------------------------------------------|
| STRING / ARRAY / STRUCT readback                | Deferred | Read leaf scalar fields with typed reads    |
| Real-time guarantees                            | Out      | `--virtual-time-ms-per-cycle` advances simulator timestamps for tests, not wall-clock PLC time |
| Hardware I/O simulation                         | Out      | Use stubs from `awl_dependency_mapper.py`    |
| Persistent PLC server                           | Out      | Each run is fresh; use `--test-scenario` for state |
| FUP/FBD direct                                  | Out      | Convert via SIMATIC, then run STL form      |
| GUI                                              | Out      | Headless only                                |

---

## Acceptance criteria (mapped from plan)

| AC ID    | Criterion                                                              | Status |
|----------|------------------------------------------------------------------------|--------|
| AC-RUN-1 | Refuses to run awlsim without first calling stl_precheck.py            | Wired in Step 0 |
| AC-RUN-2 | REAL values returned as IEEE 754 floats, never raw integer bit patterns | v1.1.0 (pre-existing) |
| AC-RUN-3 | `--mnemonics AUTO` correctly identifies EN, DE, MIXED_INSTRUCTIONS, MIXED_COMMENTS_ONLY | Mnemonic DB v1.0 |
| AC-RUN-4 | All 232 existing wrapper tests still pass after Tier 1 changes          | Verify by `test_wrapper.py` |
| AC-RUN-5 | Output JSON includes `schema_version: "2.0"` and `precheck` block       | Schema bump |
| AC-RUN-6 | `--virtual-time-ms-per-cycle 100` advances awlsim CPU timestamps without `time.sleep()` | New flag |
| AC-RUN-7 | `pattern_diff.py` round-trip is idempotent                              | Tier 2 |
| AC-SFB-2 | S5 wrapper calls rewrite to native S5 timer instructions                | `tests/sfb_rewriter_acceptance.py` |

---

## Permissiveness rule (audit E3 — promoted from warning to mandatory)

**Rule.** Before claiming an AWL source is "compile-clean" or "fixed", Claude must run *both* `stl_precheck.py` (strict mode) *and* `awlsim_runner.py` against it. A clean awlsim result alone is not sufficient evidence — the FB 112 incident proved this. If precheck says FAIL, do not even attempt the awlsim run.

This rule is encoded in Step 0 above and is non-negotiable. The `--bypass-precheck` flag exists for explicit override only and is always logged to the audit trail.

---

## Working with `awl-step7`

When `awl-step7` is performing an Analysis Mode review and identifies a candidate edge case (e.g., "this division could divide by zero"), the next step is to **prove** it with simulation:

1. `awl-step7` identifies the scenario (e.g., "K248_FAULT goes TRUE but K248_Fault stays FALSE").
2. Route to THIS skill.
3. Run `awl_dependency_mapper.py` to generate stubs when external references exist.
4. Run `sfb_rewriter.py` if IEC multi-instance timers or S5 wrapper calls are present.
5. Build a test harness via `test_harness_generator.py`.
6. Set inputs to reproduce the scenario via `awlsim_runner.py --set-inputs`.
7. Run with assertions; report whether the edge case occurs.

This is the standard "static analysis → dynamic verification" pipeline.

---

## Working with `awl-plc-debugger`

When the user has a debug snapshot and wants to verify it matches the code:

1. `awl-plc-debugger` parses the snapshot and extracts register values as assertions.
2. Route to THIS skill.
3. Run `awlsim_tracer.py` with `--trace-format json` (schema v1.0).
4. `awl-plc-debugger` compares trace to snapshot; report differences.

The tracer's JSON output includes `schema_version: "1.0"` and `awl-plc-debugger` asserts compatibility.

---

## File tree

```
awlsim-runner/
├── SKILL.md                            # this file
├── VERSION                             # 1.2.0
├── references/
│   ├── runner-api-reference.md
│   ├── memory-map-reference.md
│   └── supported-instructions.md
└── scripts/
    ├── mnemonics.py                    # v1.0 — bilingual mnemonic DB (T1.3a)
    ├── stl_precheck.py                 # v1.0 — Step 0 mandatory linter (T1.3b)
    ├── awlsim_runner.py                # v1.2.0 — schema v2.0 output
    ├── test_harness_generator.py       # auto-generate OB1 + instance DB
    ├── sfb_rewriter.py                 # IEC multi-instance + S5 wrapper timer rewrite
    ├── awl_dependency_mapper.py        # external symbol stubbing
    ├── awlsim_tracer.py                # tracer JSON schema v1.0
    ├── pattern_diff.py                 # canonical-form round-trip diff (Tier 2)
    ├── detect_block.py                 # block type / pipeline routing (Tier 2)
    ├── test_wrapper.py                 # 232-check wrapper test suite + --smoke
    └── install_awlsim.sh               # SHA-pinned awlsim clone
```

---

## Skill System Map

This skill is part of the AWL/STL package (v1.2.0). Routing:

| User signal                                  | Route to                | Why                                  |
|----------------------------------------------|-------------------------|--------------------------------------|
| "run / simulate / execute / verify / test"   | THIS skill              | Dynamic verification                 |
| "does this code work"                        | THIS skill              | Compile + execute                    |
| "prove this edge case"                       | THIS skill (after `awl-step7` identifies it) | Reproduce via simulation |
| "what does this code do"                     | `awl-step7`             | Static analysis                      |
| "is this safe / interlock review"            | `awl-step7` + `awl-safety-critical` | Edge case + rules    |
| "decode debug snapshot"                      | `awl-plc-debugger`      | Live state                           |
| "what does instruction X do"                 | `awl-language-reference`| Reference lookup                     |

### Shared artifacts and schema versions

| Artifact                       | Owner          | Schema | Consumer must check |
|--------------------------------|----------------|--------|---------------------|
| `mnemonics.py`                 | THIS skill     | v1.0   | THIS skill (precheck), awl-step7 (peripheral I/O table) |
| `stl_precheck.py` JSON output  | THIS skill     | v1.0   | awl-step7 (fix-validation gate) |
| `awlsim_runner.py` JSON output | THIS skill     | v2.0   | awl-step7, awl-plc-debugger |
| `awlsim_tracer.py` JSON output | THIS skill     | v1.0   | awl-plc-debugger    |
| `detect_block.py` JSON output  | THIS skill     | v1.0   | THIS skill workflow |

### Package version compatibility

| Skill                 | Compatible with                                    |
|-----------------------|----------------------------------------------------|
| awlsim-runner@1.2.x   | awl-step7@1.2.x, awl-plc-debugger@1.0.x (tracer v1.0) |
