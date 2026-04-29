---
name: awl-language-reference
description: Look up Siemens STEP 7 STL/AWL language details — instruction semantics, German↔English mnemonic mapping (including peripheral I/O like PED↔PID), data types, addressing modes (I/Q/M/L/DB/DI/PIW/PQW/T/C), and constant formats. Use when the user asks "what does <instruction> do", asks about STL syntax, asks about a German mnemonic, or needs the IEC vs Siemens addressing equivalence. This is a reference-lookup skill, not a workflow skill — it does not analyze, run, or modify code.
---

# AWL Language Reference

## Role

Reference-lookup skill. Answers questions like:
- "What does `UC` do?"
- "How do I write a REAL comparison?"
- "What's the German equivalent of `JNB`?"
- "What's the range of DINT?"
- "How do I open a DB symbolically?"
- "PED or PID — which one is German?"

For analysis, code authoring, or simulation, route to `awl-step7` / `awlsim-runner` / `awl-plc-debugger`.

## Mnemonic policy (project default)

The Siemens STL toolchain accepts two mnemonic sets:
- **English STL** (PID, A, AN, JU, JC, OPN, …)
- **German AWL** (PED, U, UN, SPA, SPB, AUF, …)

**Both are valid Siemens-supported syntax.** Real production codebases sometimes contain both — typically because code blocks were imported from a German-language SIMATIC installation. This project's policy is **English-canonical**:
- A file using consistent EN mnemonics: OK and already canonical.
- A file using consistent DE mnemonics: OK as input; translate/canonicalize references and generated output to English STL.
- A file mixing EN and DE *instruction* mnemonics in the same block: WARNed by `stl_precheck.py` as `MIXED_INSTRUCTIONS`. Runner requires `--accept-mixed-mnemonics` to proceed; the override is logged.
- A file with EN instructions and DE-language *comments* (with diacritics): INFO only — this is normal for PCS7 plants.

For the canonical translation table, see `instructions-german.md`. Use English STL in explanations and generated code unless quoting an original source line.

## Quick lookup tables

### Operand prefixes (addressing)

| Area             | Bit       | Byte  | Word  | DWord |
|------------------|-----------|-------|-------|-------|
| Input            | `I x.x`   | `IB x` | `IW x` | `ID x` |
| Output           | `Q x.x`   | `QB x` | `QW x` | `QD x` |
| Memory           | `M x.x`   | `MB x` | `MW x` | `MD x` |
| Local (temp)     | `L x.x`   | `LB x` | `LW x` | `LD x` |
| DB (shared)      | `DBX x.x` | `DBB x`| `DBW x`| `DBD x` |
| DI (instance)    | `DIX x.x` | `DIB x`| `DIW x`| `DID x` |
| Peripheral In  (EN) | —      | `PIB x`| `PIW x`| `PID x` |
| Peripheral In  (DE) | —      | `PEB x`| `PEW x`| `PED x` |
| Peripheral Out (EN) | —      | `PQB x`| `PQW x`| `PQD x` |
| Peripheral Out (DE) | —      | `PAB x`| `PAW x`| `PAD x` |
| Timer            | `T n`     | —     | —     | —     |
| Counter          | `C n`     | —     | —     | —     |

> **The peripheral I/O pairs (PIB↔PEB, PIW↔PEW, PID↔PED, PQB↔PAB, PQW↔PAW, PQD↔PAD) are the FB 112 saga root cause.** Both forms are valid Siemens syntax. Use whichever matches your project's mnemonic mode. `stl_precheck.py` flags mixed usage in a single file.

### Symbolic addressing (project standard)

```awl
"SymbolicDB".StructName.Member        // Shared DB via Symbol Table
#LocalVar                             // This block's VAR/VAR_TEMP
#StructName.Member                    // Nested struct member
#ArrayName[index]                     // Array element
"GlobalSymbol"                        // Global bit / FB / FC / DB by symbolic name
```

### Constant formats

| Type        | Example                       |
|-------------|-------------------------------|
| BOOL        | `TRUE`, `FALSE`               |
| INT         | `100`, `-32`                  |
| DINT        | `L#100000`                    |
| REAL        | `5.000000e+000` (project standard: scientific, 6 decimals) |
| WORD (hex)  | `W#16#00FF`                   |
| BYTE (hex)  | `B#16#0F`                     |
| S5TIME      | `S5T#10S`, `S5T#2H`, `S5T#500MS` |
| IEC TIME    | `T#15S`, `T#10M`              |
| STRING      | `'text'`                      |

## When to search this skill

- "What does [instruction] do?" / "What does `UC` do?"
- "How do I write a REAL comparison?"
- "PED vs PID — which is which?"
- "What's the range of DINT?"
- "How do I access a DB symbolically?"
- "What's the German equivalent of `JCN`?"
- Any pure syntax / language question about STL/AWL

## Reference files in this skill

- `references/instructions-english.md` — full English STL instruction set with semantics, ACCU effects, examples
- `references/instructions-german.md` — German AWL mnemonics + complete EN↔DE translation table (61 instruction pairs + 6 peripheral I/O pairs)
- `references/data-types.md` — all data types (BOOL, INT, DINT, REAL, S5TIME, etc.), STRUCT/ARRAY syntax, addressing modes, constant formats

## Skill System Map

This skill is part of the AWL/STL package (v1.2.0). Routing:

| User signal                          | Route to                | Why                                  |
|--------------------------------------|-------------------------|--------------------------------------|
| "what does <instruction> do"         | THIS skill              | Language lookup                      |
| "PED vs PID"                         | THIS skill              | Mnemonic mapping                     |
| ".AWL file uploaded; what does this do" | awl-step7            | Static analysis                      |
| "create new FB"                      | awl-step7 Authoring     | Code authoring                       |
| "is this safe"                       | awl-safety-critical     | Rules consultation                   |
| "run / simulate"                     | awlsim-runner           | Dynamic verification                 |
| "decode debug snapshot"              | awl-plc-debugger        | Live state                           |

### Shared artifacts

| Artifact                              | Owner          | Schema |
|---------------------------------------|----------------|--------|
| `mnemonics.py` (61+ instructions, 6 peripheral pairs) | awlsim-runner  | v1.0   |

When THIS skill cites instruction semantics, the authoritative spelling and EN↔DE mapping comes from `mnemonics.py` schema v1.0.
