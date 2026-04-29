# AWL Instructions — German Mnemonics (Bilingual Reference)

> **Mnemonic policy**: both German AWL and English STL are valid Siemens-supported syntax. This file is the canonical **EN↔DE translation reference** — useful both for translating imported German code and for understanding existing German blocks left in place. The lenient project policy permits either mnemonic set per file; what is NOT permitted (without explicit `--accept-mixed-mnemonics` override) is mixing EN and DE instruction mnemonics in a single block. Peripheral I/O operands (PED↔PID family) are documented at the bottom of this file — these were the FB 112 saga root cause.

---

## Complete German → English Translation Table

| German (AWL) | English (STL) | Category | Description |
|--------------|---------------|----------|-------------|
| `U` | `A` | Bit logic | AND |
| `UN` | `AN` | Bit logic | AND NOT |
| `O` | `O` | Bit logic | OR (same) |
| `ON` | `ON` | Bit logic | OR NOT (same) |
| `X` | `X` | Bit logic | XOR (same) |
| `XN` | `XN` | Bit logic | XOR NOT (same) |
| `U(` | `A(` | Bit logic | AND bracket open |
| `UN(` | `AN(` | Bit logic | AND NOT bracket |
| `O(` | `O(` | Bit logic | OR bracket (same) |
| `ON(` | `ON(` | Bit logic | OR NOT bracket (same) |
| `)` | `)` | Bit logic | Close bracket (same) |
| `=` | `=` | Bit logic | Assign (same) |
| `S` | `S` | Bit logic | Set (same) |
| `R` | `R` | Bit logic | Reset (same) |
| `NOT` | `NOT` | Bit logic | Invert RLO (same) |
| `SET` | `SET` | Bit logic | Force RLO=1 (same) |
| `CLR` | `CLR` | Bit logic | Force RLO=0 (same) |
| `SAVE` | `SAVE` | Bit logic | Save RLO to BR (same) |
| `FP` | `FP` | Bit logic | Positive edge (same) |
| `FN` | `FN` | Bit logic | Negative edge (same) |
| `L` | `L` | Load/Transfer | Load (same) |
| `T` | `T` | Load/Transfer | Transfer (same) |
| `TAK` | `TAK` | Accumulator | Exchange ACCU1/ACCU2 (same) |
| `PUSH` | `PUSH` | Accumulator | Push accumulators (same) |
| `POP` | `POP` | Accumulator | Pop accumulators (same) |
| `ENT` | `ENT` | Accumulator | Enter (same) |
| `LEAVE` | `LEAVE` | Accumulator | Leave (same) |
| `+I` | `+I` | Integer math | Add INT (same) |
| `-I` | `-I` | Integer math | Subtract INT (same) |
| `*I` | `*I` | Integer math | Multiply INT (same) |
| `/I` | `/I` | Integer math | Divide INT (same) |
| `+D` | `+D` | Integer math | Add DINT (same) |
| `-D` | `-D` | Integer math | Subtract DINT (same) |
| `*D` | `*D` | Integer math | Multiply DINT (same) |
| `/D` | `/D` | Integer math | Divide DINT (same) |
| `MOD` | `MOD` | Integer math | Modulo (same) |
| `+R` | `+R` | Real math | Add REAL (same) |
| `-R` | `-R` | Real math | Subtract REAL (same) |
| `*R` | `*R` | Real math | Multiply REAL (same) |
| `/R` | `/R` | Real math | Divide REAL (same) |
| `ABS` | `ABS` | Real math | Absolute value (same) |
| `SQR` | `SQR` | Real math | Square (same) |
| `SQRT` | `SQRT` | Real math | Square root (same) |
| `==I` | `==I` | Compare | Equal INT (same) |
| `<>I` | `<>I` | Compare | Not equal INT (same) |
| `>I` | `>I` | Compare | Greater INT (same) |
| `<I` | `<I` | Compare | Less INT (same) |
| `>=I` | `>=I` | Compare | Greater or equal INT (same) |
| `<=I` | `<=I` | Compare | Less or equal INT (same) |
| `==D` | `==D` | Compare | Equal DINT (same) |
| `==R` | `==R` | Compare | Equal REAL (same) |
| `>R` | `>R` | Compare | Greater REAL (same) |
| `<R` | `<R` | Compare | Less REAL (same) |
| `>=R` | `>=R` | Compare | Greater or equal REAL (same) |
| `<=R` | `<=R` | Compare | Less or equal REAL (same) |
| `ITD` | `ITD` | Convert | INT to DINT (same) |
| `DTR` | `DTR` | Convert | DINT to REAL (same) |
| `RND` | `RND` | Convert | Round REAL to DINT (same) |
| `TRUNC` | `TRUNC` | Convert | Truncate REAL to DINT (same) |
| `BEA` | `BEU` | Control | Block End Unconditional |
| `BEB` | `BEC` | Control | Block End Conditional |
| `BE` | `BE` | Control | Block End (same) |
| `SPA` | `JU` | Jump | Jump Unconditional |
| `SPB` | `JC` | Jump | Jump if RLO=1 |
| `SPBN` | `JCN` | Jump | Jump if RLO=0 |
| `SPBB` | `JCB` | Jump | Jump if RLO=1 (copy to BR) |
| `SPBNB` | `JNB` | Jump | Jump if RLO = 0, copy RLO → BR |
| `SPBI` | `JBI` | Jump | Jump if BR = 1 |
| `SPNBI` | `JNBI` | Jump | Jump if BR = 0 |
| `SPO` | `JO` | Jump | Jump if overflow |
| `SPOS` | `JOS` | Jump | Jump if overflow stored |
| `SPZ` | `JZ` | Jump | Jump if zero |
| `SPN` | `JN` | Jump | Jump if not zero |
| `SPP` | `JP` | Jump | Jump if positive |
| `SPM` | `JM` | Jump | Jump if negative |
| `SPPZ` | `JPZ` | Jump | Jump if ≥ 0 |
| `SPMZ` | `JMZ` | Jump | Jump if ≤ 0 |
| `SPUO` | `JUO` | Jump | Jump if unordered |
| `SPL` | `JL` | Jump | Jump via list |
| `LOOP` | `LOOP` | Jump | Loop (same) |
| `TAI` | `ITD` | Convert | Also INT to DINT in some versions |
| `SI` | `SP` | Timer | Pulse timer |
| `SV` | `SE` | Timer | Extended pulse timer |
| `SE` | `SD` | Timer | On-delay timer |
| `SS` | `SS` | Timer | Retentive on-delay (same) |
| `SA` | `SF` | Timer | Off-delay timer |
| `ZV` | `CU` | Counter | Count up |
| `ZR` | `CD` | Counter | Count down |
| `AUF` | `OPN` | Data block | Open DB |
| `TDB` | `CDB` | Data block | Exchange DB/DI |
| `UW` | `AW` | Word logic | AND Word |
| `OW` | `OW` | Word logic | OR Word (same) |
| `XOW` | `XOW` | Word logic | XOR Word (same) |
| `UD` | `AD` | Word logic | AND DWord |
| `OD` | `OD` | Word logic | OR DWord (same) |
| `XOD` | `XOD` | Word logic | XOR DWord (same) |
| `SLW` | `SLW` | Shift | Shift left word (same) |
| `SRW` | `SRW` | Shift | Shift right word (same) |
| `SLD` | `SLD` | Shift | Shift left dword (same) |
| `SRD` | `SRD` | Shift | Shift right dword (same) |
| `SSI` | `SSI` | Shift | Shift signed INT (same) |
| `SSD` | `SSD` | Shift | Shift signed DINT (same) |
| `RLD` | `RLD` | Rotate | Rotate left dword (same) |
| `RRD` | `RRD` | Rotate | Rotate right dword (same) |
| `CALL` | `CALL` | Block call | Call FB/FC (same) |
| `UC` | `UC` | Block call | Unconditional call (same) |
| `CC` | `CC` | Block call | Conditional call (same) |
| `NOP 0` | `NOP 0` | Misc | No operation (same) |
| `BLD` | `BLD` | Misc | Display directive (same) |

---

## Key Differences Summary

The most commonly confused German→English pairs:

| German | English | Trap |
|--------|---------|------|
| `U` | `A` | Most common — AND |
| `UN` | `AN` | AND NOT |
| `BEA` | `BEU` | Block End Unconditional |
| `BEB` | `BEC` | Block End Conditional |
| `SPA` | `JU` | Jump Unconditional |
| `SPB` | `JC` | Jump if True |
| `SPBN` | `JCN` | Jump if False |
| `SPBNB` | `JNB` | Jump if RLO = 0 (copies RLO → BR) |
| `AUF` | `OPN` | Open Data Block |
| `TDB` | `CDB` | Exchange DB/DI |
| `ZV` | `CU` | Counter Up |
| `ZR` | `CD` | Counter Down |
| `SI` | `SP` | Timer — Pulse |
| `SV` | `SE` | Timer — Extended Pulse |
| `SE` | `SD` | Timer — On-Delay (confusingly, German SE = English SD) |
| `SA` | `SF` | Timer — Off-Delay |
| `SS` | `SS` | Timer — Retentive On-Delay (same in both) |

> **Timer mnemonic trap**: The German timer mnemonics bear no relation to the English ones. In particular, German `SE` = English `SD` (On-Delay), NOT Extended Pulse. German `SV` = English `SE` (Extended Pulse). This is a frequent source of confusion.

---

## Notes on Exported AWL Files

SIMATIC Manager exports AWL using **German mnemonics** when the STEP 7 installation
language is German. When you import these files into English STL projects:

1. `U` and `UN` are the most frequent — translate to `A` and `AN`
2. `SPA`/`SPB`/`SPBN` jump instructions — translate to `JU`/`JC`/`JCN`
3. `AUF` for data block open — translate to `OPN`
4. Timer/counter instructions may vary — verify with documentation

Many instructions (`O`, `S`, `R`, `L`, `T`, comparisons, math) are **identical** in both
languages.

---

## Peripheral I/O Operand Prefixes — EN ↔ DE (CRITICAL)

These are operand prefixes (used as `L PID 1628`), not standalone instructions, but they have **distinct EN and DE forms** that are the most common source of silent compile failures. awlsim accepts both forms; SIMATIC Manager accepts only the form that matches the project's mnemonic mode.

This is the FB 112 saga root cause family.

| Direction | Width | English (STL) | German (AWL) | Example |
|-----------|-------|---------------|--------------|---------|
| Input     | Byte  | `PIB`         | `PEB`        | `L PIB 100;`   ↔   `L PEB 100;` |
| Input     | Word  | `PIW`         | `PEW`        | `L PIW 200;`   ↔   `L PEW 200;` |
| Input     | DWord | `PID`         | `PED`        | `L PID 1628;`  ↔   `L PED 1628;` |
| Output    | Byte  | `PQB`         | `PAB`        | `T PQB 100;`   ↔   `T PAB 100;` |
| Output    | Word  | `PQW`         | `PAW`        | `T PQW 200;`   ↔   `T PAW 200;` |
| Output    | DWord | `PQD`         | `PAD`        | `T PQD 300;`   ↔   `T PAD 300;` |

**Address spacing is irrelevant** — both `L PID 1628;` (with space) and `L PID1628;` (no space) are accepted by SIMATIC Manager. (This was the FB 112 D2 phantom diagnosis.)

**Mnemonic mode rule:**
- An EN file uses `PID/PIW/PIB` etc. throughout.
- A DE file uses `PED/PEW/PEB` etc. throughout.
- A file mixing both (e.g., one network uses `PID`, another uses `PED`) is `MIXED_INSTRUCTIONS` per `stl_precheck.py` and requires explicit override.

**The FB 112 trap**: Claude initially diagnosed `PID` as wrong (D1), then diagnosed the address spacing as wrong (D2). Both were wrong diagnoses. The actual problem was missing semicolons (D3). `stl_precheck.py` now catches D3 directly without reaching for the mnemonic.
