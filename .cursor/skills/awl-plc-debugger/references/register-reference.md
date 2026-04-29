# Register Reference — Siemens S7-300/400 STL Debug View

Authoritative decoding tables for every register and flag visible in SIMATIC Manager's STL debug mode. The SKILL.md and `snapshot-analysis-guide.md` reference this file for value-decoding rules.

---

## STATUS Word — Bit Layout

The STATUS word is 9 bits (sometimes shown as a 16-bit value with bits 9–15 unused). SIMATIC Manager often displays it as binary, e.g. `1000 0111`.

| Bit | Name  | Meaning                                                          |
|-----|-------|------------------------------------------------------------------|
| 0   | /FC   | First Check — set when RLO is being established (new logic string) |
| 1   | RLO   | Result of Logic Operation — primary diagnostic register           |
| 2   | STA   | Status — secondary state bit, mostly used internally              |
| 3   | OR    | OR bit — used during nested OR evaluation in bracket logic         |
| 4   | OS    | Overflow Stored — sticky overflow flag (cleared only by JOS or new block) |
| 5   | OV    | Overflow — current arithmetic operation overflowed                |
| 6   | CC0   | Condition Code 0 — combined with CC1 to indicate compare/arithmetic result |
| 7   | CC1   | Condition Code 1                                                  |
| 8   | BR    | Binary Result — for FB/FC return value, also used in JNB/SAVE chains |

### Condition Code (CC1, CC0) decoding

| CC1 | CC0 | Meaning                                  |
|-----|-----|------------------------------------------|
| 0   | 0   | Result = 0 / Equal                       |
| 0   | 1   | Result < 0 / Less than                   |
| 1   | 0   | Result > 0 / Greater than                |
| 1   | 1   | Unordered / Invalid REAL (NaN, ±Inf)     |

### Reading binary STATUS

If snapshot shows `1000 0111`, that's bits 0-8 left-to-right or right-to-left depending on display convention. Standard SIMATIC display:

```
Bit:    8 7 6 5 4 3 2 1 0
Field:  BR CC1 CC0 OV OS OR STA RLO /FC
```

Example `1000 0111`:
- Bit 8 (BR) = 1
- Bits 7–6 (CC1, CC0) = 0, 0  → result = 0 / equal
- Bits 5–4 (OV, OS) = 0, 0  → no overflow
- Bit 3 (OR) = 0
- Bit 2 (STA) = 1
- Bit 1 (RLO) = 1
- Bit 0 (/FC) = 1  → start of a new logic string

---

## ACCU1 / ACCU2 — Value Decoding by Type

ACCU1 and ACCU2 are 32-bit registers (with sub-fields ACCU1-L = lower word, ACCU1-LL = lower byte). The display shows the raw 32-bit value as either decimal or hex; you must decode it based on what the surrounding code is doing.

### ACCU shows BOOL

A BOOL operand loads only into the LSB. ACCU1 may show 0 or 1, but the previous bits remain from the prior load. `A` / `O` etc. don't actually use ACCU — they use RLO.

### ACCU shows INT (16-bit)

ACCU1-L is the 16-bit signed integer. Range: −32768 to +32767.

If display shows `1600`, that's INT 1600.
If display shows `65535` for an INT context, that's −1 (two's complement: `0xFFFF`).

### ACCU shows DINT (32-bit)

ACCU1 is the 32-bit signed integer. Range: ±2,147,483,647.

### ACCU shows REAL (IEEE 754 single precision)

The 32-bit ACCU value, when reinterpreted as IEEE 754, is a REAL.

#### IEEE 754 Quick-Reference Table

| ACCU1 (decimal) | ACCU1 (hex)   | REAL value         | Notes                       |
|-----------------|---------------|--------------------|-----------------------------|
| 0               | `0x00000000`  | 0.0                |                             |
| 1065353216      | `0x3F800000`  | 1.0                |                             |
| 1073741824      | `0x40000000`  | 2.0                |                             |
| 1077936128      | `0x40400000`  | 3.0                |                             |
| 1082130432      | `0x40800000`  | 4.0                |                             |
| 1095237632      | `0x41480000`  | 12.5               | Common test value           |
| 1101004800      | `0x41A00000`  | 20.0               |                             |
| 1120403456      | `0x42C80000`  | 100.0              |                             |
| 1148846080      | `0x447A0000`  | 1000.0             |                             |
| 0x7F800000      | —             | +Infinity          | Math overflow result        |
| 0xFF800000      | —             | −Infinity          |                             |
| 0x7FC00000      | —             | NaN (any payload)  | Invalid result; CC=11       |
| `0x80000000`    | —             | -0.0               | Special — equals 0.0 in compare |

#### Manual decoding

Bit layout: `S EEEEEEEE MMMMMMMMMMMMMMMMMMMMMMM`

- S (bit 31) = sign (0 = positive, 1 = negative)
- E (bits 30–23) = exponent (8 bits, biased by 127)
- M (bits 22–0) = mantissa (23 bits, with implicit leading 1)

```
value = (-1)^S × 2^(E - 127) × (1 + M / 2^23)
```

For `0x41480000`:
- S = 0 (positive)
- E = `10000010` = 130; 130 − 127 = 3
- M = `10010000000000000000000` = 0x480000 = 4718592
- 1 + 4718592 / 8388608 = 1.5625
- value = 1 × 2^3 × 1.5625 = 12.5 ✓

### ACCU shows S5TIME

S5TIME is a 16-bit BCD value with a time-base in the upper nibble:

| Bits 15–14 (time base) | Resolution | Range          |
|------------------------|------------|----------------|
| `00`                   | 10 ms      | 0.01 s – 9.99 s |
| `01`                   | 100 ms     | 0.1 s – 99.9 s  |
| `10`                   | 1 s        | 1 s – 999 s     |
| `11`                   | 10 s       | 10 s – 9990 s   |

Bits 11–0 are the BCD-encoded value (3 BCD digits, each 4 bits).

Example: ACCU1 = `0x0050` = `0000 0000 0101 0000`
- Time base = `00` → 10 ms resolution
- BCD value = `0 5 0` = 50 → 50 × 10 ms = 500 ms

Example: ACCU1 = `0x2123` = `0010 0001 0010 0011`
- Time base = `10` → 1 s resolution
- BCD value = `1 2 3` = 123 → 123 s

### ACCU shows BCD

BCD-coded decimal: each nibble holds a digit 0–9.

`0x1234` = decimal 1234. (Don't confuse with hex 0x1234 = 4660.)

---

## Address Registers (AR1, AR2)

32-bit pointer registers used for indirect addressing.

### Format 1: Area-internal pointer

```
0000 0000 0000 0000 0000 0bbb bbbb bxxx
                       ^^^^^^^^^^^^^ ^^^
                       byte offset    bit
```

Bits 0–2 = bit offset (0–7).
Bits 3–18 = byte offset.
Bits 19–31 = 0.

Example: AR1 = `0x000000C8` = byte 25, bit 0. (Byte 25 = 0x19, but stored as `0xC8` because of the 3-bit shift for the bit offset).

Actually for clarity: `0xC8` = `1100 1000` = byte offset `11001` = 25, bit offset `000` = 0. So pointer `P#25.0`.

Sometimes displayed as `12.4` in the SIMATIC view — this is the dotted format `byte.bit`, where 12.4 means byte 12 bit 4 (`P#12.4`).

### Format 2: Area-crossing pointer

```
1aaa 0000 0000 0000 0000 0bbb bbbb bxxx
^^^^                   ^^^^^^^^^^^^^ ^^^
area code              byte offset    bit
```

Bits 24–26 = area code:
| Code | Area      |
|------|-----------|
| 000  | (no area) |
| 001  | I (input) |
| 010  | Q (output)|
| 011  | M (memory)|
| 100  | DB        |
| 101  | DI (instance DB) |
| 110  | L (local) |
| 111  | V (previous local) |

Bit 31 = 1 (area-crossing flag).

---

## DB1 / DB2 Registers

These show the currently-open data block numbers.

- DB1 = current shared DB (set by `OPN DB n`)
- DB2 = current instance DB (set by `OPN DI n` or by FB CALL)

After `CALL "FB", "DB"`:
- DB2 is set to the called FB's instance DB number.
- DB1 may also change depending on FB internals.
- On `BE` / `BEU` from the called FB, DB1 and DB2 are restored to their pre-CALL values.

---

## Common Snapshot Anomalies

| Anomaly                                     | Likely cause                                           |
|---------------------------------------------|--------------------------------------------------------|
| RLO toggling every scan around comparison   | Missing hysteresis (rule R3)                           |
| OV bit set, ACCU shows garbage REAL         | Arithmetic overflow; rule R1 violated                  |
| CC1=1, CC0=1 (unordered) after SQRT         | Negative input to SQRT; rule R7 violated               |
| DB1/DB2 unchanged across CALL boundary      | CALL not actually executed (RLO=0 + CC?), or CALL UC vs CC |
| Multiple FP edges in same scan              | Pulse-bit array reused for two signals; rule R4 violated |
| Timer SE/SD shows S5TIME=0                  | Timer expired or never enabled                         |
| ACCU value far outside expected range       | VAR_TEMP read before init; rule R6 violated            |

---

## Quick lookup: instruction effects on RLO and ACCU

For full instruction set, see `awl-language-reference/references/instructions-english.md`. This table is the subset most often needed during debug snapshot analysis:

| Instruction        | Effect on RLO                  | Effect on ACCU            |
|--------------------|--------------------------------|---------------------------|
| `A op` / `AN op`   | RLO = RLO AND [NOT] op         | unchanged                 |
| `O op` / `ON op`   | RLO = RLO OR [NOT] op          | unchanged                 |
| `=  op`            | op := RLO                      | unchanged                 |
| `S  op`            | if RLO=1 then op:=1            | unchanged                 |
| `R  op`            | if RLO=1 then op:=0            | unchanged                 |
| `L  op`            | unchanged                      | ACCU2:=ACCU1; ACCU1:=op   |
| `T  op`            | unchanged                      | op := ACCU1               |
| `+R / -R / *R / /R`| unchanged                      | ACCU1 := ACCU2 op ACCU1 (REAL) |
| `==R` / `<R` / `>R`| RLO := compare result          | unchanged                 |
| `JU label`         | unchanged (always jumps)       | unchanged                 |
| `JC label`         | unchanged (jumps if RLO=1)     | unchanged                 |
| `JNB label`        | unchanged; copies RLO→BR       | unchanged                 |
| `SAVE`             | unchanged; copies RLO→BR       | unchanged                 |
| `SET` / `CLR`      | RLO := 1 / 0                   | unchanged                 |
| `NOT`              | RLO := NOT RLO                 | unchanged                 |
| `FP op`            | RLO := previous RLO AND rising edge of op; updates op | unchanged |
| `FN op`            | RLO := previous RLO AND falling edge of op; updates op | unchanged |
| `NOP 0`            | unchanged                      | unchanged                 |
| `BLD n`            | unchanged                      | unchanged                 |
