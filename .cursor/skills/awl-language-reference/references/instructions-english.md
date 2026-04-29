# STL Instructions — English Mnemonics (S7-300/400)

> **Mnemonic policy**: this project handles BOTH English STL and German AWL mnemonics. Both are valid Siemens-supported syntax. `stl_precheck.py` auto-detects the mnemonic mode of each file. A file mixing EN and DE *instruction* mnemonics in the same block produces a `MIXED_INSTRUCTIONS` warning that requires `--accept-mixed-mnemonics` on the runner to bypass; the override is logged. EN instructions with DE-language *comments* (typical PCS7) are an INFO-only `MIXED_COMMENTS_ONLY`. See `instructions-german.md` for the complete EN↔DE translation table including the peripheral I/O family (PED↔PID, etc.) at the heart of the FB 112 saga.

---

## 1. Bit Logic

| Instruction | Operand | Effect |
|-------------|---------|--------|
| `A` | bit | AND: RLO = RLO AND operand |
| `AN` | bit | AND NOT: RLO = RLO AND (NOT operand) |
| `O` | bit | OR: RLO = RLO OR operand |
| `ON` | bit | OR NOT |
| `X` | bit | XOR |
| `XN` | bit | XOR NOT |
| `A(` | — | AND with bracket open |
| `AN(` | — | AND NOT with bracket open |
| `O(` | — | OR with bracket open |
| `ON(` | — | OR NOT with bracket open |
| `)` | — | Close bracket |
| `=` | bit | Assign RLO to operand |
| `S` | bit | Set (latch) if RLO=1 |
| `R` | bit | Reset (latch) if RLO=1 |
| `NOT` | — | Invert RLO |
| `SET` | — | Force RLO to 1 |
| `CLR` | — | Force RLO to 0 |
| `SAVE` | — | Copy RLO → BR bit |
| `FP` | bit | Positive (rising) edge; bit = previous state |
| `FN` | bit | Negative (falling) edge; bit = previous state |

**Bracket nesting example:**
```awl
      A(    ;
      O     M 0.0;
      O     M 0.1;
      )     ;
      A     M 0.2;
      =     Q 0.0;
```
Evaluates: `(M0.0 OR M0.1) AND M0.2 → Q0.0`

---

## 2. Load / Transfer

| Instruction | Description |
|-------------|-------------|
| `L <operand>` | Load operand → ACCU1 (old ACCU1 → ACCU2) |
| `T <operand>` | Transfer ACCU1 → operand |
| `L STW` | Load status word into ACCU1 |
| `T STW` | Transfer ACCU1 bits 0–8 → status word |
| `LAR1` | Load AR1 from ACCU1 |
| `LAR1 <D>` | Load AR1 from double-word or pointer constant |
| `LAR2` | Load AR2 from ACCU1 |
| `TAR1` | Transfer AR1 → ACCU1 |
| `TAR2` | Transfer AR2 → ACCU1 |
| `CAR` | Exchange AR1 and AR2 |

---

## 3. Comparisons

Both values loaded before compare: `L val1` then `L val2` → ACCU2 vs ACCU1.

| Integer | Double Int | Real | Condition |
|---------|-----------|------|-----------|
| `==I` | `==D` | `==R` | ACCU2 = ACCU1 |
| `<>I` | `<>D` | `<>R` | ACCU2 ≠ ACCU1 |
| `>I` | `>D` | `>R` | ACCU2 > ACCU1 |
| `<I` | `<D` | `<R` | ACCU2 < ACCU1 |
| `>=I` | `>=D` | `>=R` | ACCU2 ≥ ACCU1 |
| `<=I` | `<=D` | `<=R` | ACCU2 ≤ ACCU1 |

```awl
      L     "DB".Value;        // → ACCU1
      L     #SCADA.Setpoint;   // Value → ACCU2, Setpoint → ACCU1
      >R    ;                  // Is Value > Setpoint? (ACCU2 > ACCU1)
      =     M 0.0;
```

---

## 4. Arithmetic

### Integer (16-bit, result in ACCU1-L)
| Instruction | Operation |
|-------------|-----------|
| `+I` | ACCU2-L + ACCU1-L → ACCU1-L |
| `-I` | ACCU2-L − ACCU1-L → ACCU1-L |
| `*I` | ACCU2-L × ACCU1-L → ACCU1 (32-bit result) |
| `/I` | ACCU2-L ÷ ACCU1-L → quotient ACCU1-L, remainder ACCU1-H |
| `+ n` | Add 16/32-bit constant to ACCU1 |
| `INC n` | Increment ACCU1-LL by n |
| `DEC n` | Decrement ACCU1-LL by n |

### Double Integer (32-bit)
| Instruction | Operation |
|-------------|-----------|
| `+D` | Add DINT |
| `-D` | Subtract DINT |
| `*D` | Multiply DINT |
| `/D` | Divide DINT |
| `MOD` | Remainder DINT |

### Real (IEEE 754 single precision)
| Instruction | Operation |
|-------------|-----------|
| `+R` | Add REAL |
| `-R` | Subtract REAL |
| `*R` | Multiply REAL |
| `/R` | Divide REAL |
| `ABS` | Absolute value |
| `SQR` | Square (x²) |
| `SQRT` | Square root |
| `LN` | Natural logarithm |
| `EXP` | Exponential (eˣ) |
| `SIN` | Sine (radians) |
| `COS` | Cosine (radians) |
| `TAN` | Tangent (radians) |
| `ASIN` | Arc sine |
| `ACOS` | Arc cosine |
| `ATAN` | Arc tangent |

> **Always check OV after REAL arithmetic** — see `awl-safety-critical` skill.

---

## 5. Conversion

| Instruction | Conversion |
|-------------|-----------|
| `ITD` | INT → DINT (sign extend) |
| `DTR` | DINT → REAL |
| `RND` | REAL → DINT (rounds to nearest; when exactly 0.5, rounds to nearest **even** integer) |
| `RND+` | REAL → DINT (ceiling: smallest integer **≥** the value; IEEE round-to-+infinity) |
| `RND-` | REAL → DINT (floor: largest integer **≤** the value; IEEE round-to-−infinity) |
| `TRUNC` | REAL → DINT (truncate toward zero — drops fractional part) |
| `ITB` | INT → BCD |
| `BTI` | BCD → INT |
| `BTD` | BCD → DINT |
| `DTB` | DINT → BCD |
| `NEGI` | Negate INT (two's complement) |
| `NEGD` | Negate DINT |
| `NEGR` | Negate REAL |
| `INVI` | Invert INT (one's complement) |
| `INVD` | Invert DINT |
| `CAW` | Swap bytes in ACCU1-L (word) |
| `CAD` | Swap bytes in ACCU1 (dword) |

---

## 6. Jumps

| Instruction | Condition |
|-------------|-----------|
| `JU label` | Unconditional |
| `JC label` | If RLO = 1 |
| `JCN label` | If RLO = 0 |
| `JCB label` | If RLO = 1 — also copies RLO → BR |
| `JNB label` | If RLO = 0 — also copies RLO → BR |
| `JBI label` | If BR = 1 |
| `JNBI label` | If BR = 0 |
| `JO label` | If OV = 1 (overflow set) |
| `JOS label` | If OS = 1 (overflow stored, sticky) |
| `JZ label` | If result = 0 (CC1=0, CC0=0) |
| `JN label` | If result ≠ 0 |
| `JP label` | If result > 0 (CC1=1, CC0=0) |
| `JM label` | If result < 0 (CC1=0, CC0=1) |
| `JPZ label` | If result ≥ 0 |
| `JMZ label` | If result ≤ 0 |
| `JUO label` | If unordered (invalid REAL) |
| `JL label` | Jump via list (ACCU1-LL = index) |
| `LOOP label` | Decrement ACCU1-L, jump if ≠ 0 |

> **JCB / JNB note**: These are not "jump if BR" instructions. They jump based on RLO (1 or 0 respectively) AND simultaneously copy RLO into BR. The project uses JNB extensively in the overflow-protection pattern: after a closing `)`, the bracket result is in the RLO; JNB jumps if the bracket evaluated false AND stores that result in BR for subsequent `A BR` checks.

**Label syntax:**
```awl
_001: NOP   0;    // definition
      JU    _001; // reference
```

---

## 7. Timers

### Types
| Type | Instruction | Behaviour |
|------|-------------|-----------|
| Pulse | `SP T n` | Rising edge starts; output on for preset time; early enable removal cancels it |
| Extended Pulse | `SE T n` | Rising edge starts; output on for preset time; enable removal does NOT cancel; retriggerable |
| On-Delay | `SD T n` | Rising edge starts delay; output after delay elapses; enable removal before timeout cancels |
| Retentive On-Delay | `SS T n` | Rising edge starts delay; enable removal does NOT cancel; retriggerable; only R resets |
| Off-Delay | `SF T n` | FALLING edge starts; output on during timing; rising edge before timeout cancels it |

### Timer Operations
```awl
      A     [enable condition];
      L     S5T#10S;           // Load preset (must come before SD/SE/etc)
      SD    T 340;             // Start on-delay timer
      NOP   0;                 // Project convention: 3× NOP after timer
      NOP   0;
      NOP   0;
      A     T 340;             // Check timer output (true when elapsed)
      R     T 340;             // Reset timer
      L     T 340;             // Load elapsed time value (INT, 10ms units)
      LC    T 340;             // Load elapsed time (BCD)
      FR    T 340;             // Free-run / enable timer
```

**S5TIME ranges:**
- Resolution 10ms: 0.01s – 9.99s
- Resolution 100ms: 0.1s – 99.9s
- Resolution 1s: 1s – 999s
- Resolution 10s: 10s – 9990s (max ~2h46m)

---

## 8. Counters

```awl
      L     C#100;             // Load preset value
      A     [set enable];
      S     C 1;               // Set counter to preset
      A     [count up trigger];
      CU    C 1;               // Count up (on rising edge of RLO)
      A     [count dn trigger];
      CD    C 1;               // Count down (on rising edge of RLO)
      A     C 1;               // Counter status (true if value > 0)
      L     C 1;               // Load counter value (INT)
      LC    C 1;               // Load counter value (BCD)
      R     C 1;               // Reset counter to 0
```
Counter range: 0 – 999. Does not wrap.

---

## 9. Data Blocks

```awl
      OPN   DB 10;             // Open shared DB (sets DB register)
      OPN   DI 20;             // Open instance DB (sets DI register)
      CDB   ;                  // Exchange DB ↔ DI registers
      L     DBNO;              // Load current DB number
      L     DINO;              // Load current DI number
      L     DBLG;             // Load DB length in bytes
```

After `OPN DB n`, access with relative addressing:
```awl
      L     DBW 0;             // Word at offset 0
      L     DBD 4;             // Dword at offset 4
      A     DBX 0.0;           // Bit 0.0
      T     DBW 2;             // Transfer to offset 2
```

---

## 10. Word Logic

| Instruction | Operation |
|-------------|-----------|
| `AW` | AND word: ACCU1-L AND ACCU2-L → ACCU1-L |
| `OW` | OR word |
| `XOW` | XOR word |
| `AD` | AND dword: ACCU1 AND ACCU2 → ACCU1 |
| `OD` | OR dword |
| `XOD` | XOR dword |
| `AW W#16#mask` | AND immediate constant |

---

## 11. Shift / Rotate

| Instruction | Operation |
|-------------|-----------|
| `SLW n` | Shift left word n bits |
| `SRW n` | Shift right word n bits (zero fill) |
| `SLD n` | Shift left dword |
| `SRD n` | Shift right dword |
| `SSI n` | Shift signed INT (arithmetic, sign fill) |
| `SSD n` | Shift signed DINT |
| `RLW n` | Rotate left word |
| `RRW n` | Rotate right word |
| `RLD n` | Rotate left dword |
| `RRD n` | Rotate right dword |

---

## 12. Program Control

| Instruction | Description |
|-------------|-------------|
| `CALL FB, DB` | Call FB with instance DB (absolute) |
| `CALL "Name","DB"` | Call FB with instance DB (symbolic) |
| `CALL #inst` | Call local multi-instance FB |
| `CALL FC` | Call function (no DB) |
| `UC FC` | Unconditional call (no parameters) |
| `CC FC` | Conditional call (RLO=1, no parameters) |
| `BE` | Block end |
| `BEU` | Block end unconditional |
| `BEC` | Block end conditional (if RLO=1) |
| `NOP 0` | No operation (standard) |
| `NOP 1` | No operation (alternate) |
| `BLD n` | Display hint for LAD/FBD view (no logic effect) |
| `MCRA` | Activate master control relay area |
| `MCRD` | Deactivate MCR area |
| `MCR(` | MCR on |
| `)MCR` | MCR off |

---

## 13. Accumulator

| Instruction | Description |
|-------------|-------------|
| `TAK` | Exchange ACCU1 and ACCU2 |
| `PUSH` | S7-300 (2 ACCUs): copies ACCU1→ACCU2; ACCU1 unchanged. S7-400 (4 ACCUs): ACCU3→4, ACCU2→3, ACCU1→2; ACCU1 unchanged |
| `POP` | S7-300 (2 ACCUs): copies ACCU2→ACCU1; ACCU2 unchanged. S7-400 (4 ACCUs): ACCU2→1, ACCU3→2, ACCU4→3; ACCU4 unchanged |
| `ENT` | S7-400 only: copies ACCU3→ACCU4, then ACCU2→ACCU3; ACCU1/ACCU4 unchanged |
| `LEAVE` | S7-400 only: copies ACCU3→ACCU2, ACCU4→ACCU3; ACCU1/ACCU4 unchanged |

---

## 14. Status Word Bits

| Bit | Name | Set By |
|-----|------|--------|
| 0 | /FC | First check (new logic string) |
| 1 | RLO | Result of logic operation |
| 2 | STA | Status |
| 3 | OR | OR bit |
| 4 | OS | Overflow stored (sticky) |
| 5 | OV | Overflow (current) |
| 6 | CC0 | Condition code 0 |
| 7 | CC1 | Condition code 1 |
| 8 | BR | Binary result |

**CC codes:**
| CC1 | CC0 | Meaning |
|-----|-----|---------|
| 0 | 0 | Result = 0 |
| 0 | 1 | Result < 0 |
| 1 | 0 | Result > 0 |
| 1 | 1 | Unordered / invalid REAL |
