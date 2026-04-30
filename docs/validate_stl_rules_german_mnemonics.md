# AWL/STL Reference for `validate`

This document is the English reference for STEP 7 AWL/STL with German
SIMATIC mnemonics. It covers the instruction names, peripheral I/O forms, and
the core language elements used for data types and declarations.

## 1. Purpose

`validate` should catch invalid AWL/STL sources early without executing the
program or simulating SCL logic.

The check should cover at least:

- invalid STL commands;
- wrong operand counts and shapes;
- addressing errors;
- invalid block calls;
- label and jump errors;
- basic mismatches between a block and its interface.

SCL text is out of scope. If SCL appears in a source, STL rules must be ignored
there.

## 2. Mnemonic Mode

STEP 7 can switch between German SIMATIC mnemonics and English IEC mnemonics.
In the symbol table and in AWL, address areas and instructions are spelled
differently depending on the selected language mode.

The key address pairs are:

- `E` <-> `I` for inputs;
- `A` <-> `Q` for outputs;
- `PEB` <-> `PIB`, `PEW` <-> `PIW`, `PED` <-> `PID` for peripheral inputs;
- `PAB` <-> `PQB`, `PAW` <-> `PQW`, `PAD` <-> `PQD` for peripheral outputs.

## 3. EN <-> DE Core Mnemonics

The table below covers the 61 core instructions relevant to this project. It is
kept conservative and focuses on the most common forms that matter for
`validate`.

| English | German | Meaning |
| --- | --- | --- |
| `A` | `U` | Boolean AND |
| `AN` | `UN` | Boolean AND NOT |
| `O` | `O` | Boolean OR |
| `ON` | `ON` | Boolean OR NOT |
| `X` | `X` | Exclusive OR |
| `XN` | `XN` | Exclusive OR NOT |
| `=` | `=` | Assign |
| `S` | `S` | Set |
| `R` | `R` | Reset |
| `NOT` | `NOT` | Negate RLO |
| `SET` | `SET` | Set RLO to 1 |
| `CLR` | `CLR` | Clear RLO to 0 |
| `FP` | `FP` | positive edge |
| `FN` | `FN` | negative edge |
| `L` | `L` | Load |
| `T` | `T` | Transfer |
| `OPN` | `AUF` | Open DB |
| `CDB` | `TDB` | Swap shared and instance DBs |
| `BE` | `BE` | Block end |
| `BEU` | `BEA` | unconditional block end |
| `BEC` | `BEB` | conditional block end |
| `CALL` | `CALL` | Block call |
| `UC` | `UC` | unconditional call |
| `CC` | `CC` | conditional call |
| `JU` | `SPA` | unconditional jump |
| `JC` | `SPB` | jump if RLO = 1 |
| `JCN` | `SPBN` | jump if RLO = 0 |
| `JBI` | `SPBI` | jump if BR = 1 |
| `JNBI` | `SPBIN` | jump if BR = 0 |
| `JZ` | `SPZ` | jump if zero |
| `JN` | `SPN` | jump if not zero |
| `JP` | `SPP` | jump if positive |
| `JM` | `SPM` | jump if negative |
| `JL` | `SPL` | jump to label |
| `JO` | `SPO` | jump if OV = 1 |
| `JUO` | `SPU` | jump if unordered |
| `JMZ` | `SPMZ` | jump if negative or zero |
| `JPZ` | `SPPZ` | jump if positive or zero |
| `LAR1` | `LAR1` | Load AR1 |
| `LAR2` | `LAR2` | Load AR2 |
| `+AR1` | `+AR1` | Add offset to AR1 |
| `+AR2` | `+AR2` | Add offset to AR2 |
| `+I` | `+I` | Add integer |
| `-I` | `-I` | Subtract integer |
| `*I` | `*I` | Multiply integer |
| `/I` | `/I` | Divide integer |
| `?I` | `?I` | Compare integer |
| `+D` | `+D` | Add DINT |
| `-D` | `-D` | Subtract DINT |
| `*D` | `*D` | Multiply DINT |
| `/D` | `/D` | Divide DINT |
| `?D` | `?D` | Compare DINT |
| `+R` | `+R` | Add REAL |
| `-R` | `-R` | Subtract REAL |
| `*R` | `*R` | Multiply REAL |
| `/R` | `/R` | Divide REAL |
| `?R` | `?R` | Compare REAL |
| `ABS` | `ABS` | Absolute value |
| `ACOS` | `ACOS` | Arc cosine |
| `ASIN` | `ASIN` | Arc sine |
| `ATAN` | `ATAN` | Arc tangent |

### 3.1 Related Mnemonics

These forms are common in real AWL sources and are useful when the validator is
extended:

- `BLD`, `NOP 0`, `NOP 1`;
- `BTI`, `BTD`, `DTB`, `DTR`, `ITB`, `ITD`;
- `DEC`, `INC`, `INVD`, `INVI`, `NEGD`, `NEGI`, `NEGR`;
- `COS`, `EXP`, `LN`, `SIN`, `SQR`, `SQRT`, `TAN`, `TRUNC`;
- `MOD`, `RND`, `RND+`, `RND-`;
- `RLD`, `RRD`, `RLDA`, `RRDA`, `SLD`, `SRD`, `SLW`, `SRW`, `SSD`, `SSI`;
- `JOS`, `SPS`;
- `MCR(`, `)MCR`, `MCRA`, `MCRD`, `SAVE`;
- `POP`, `PUSH`, `ENT`, `LEAVE`, `TAK`, `TAD`, `TAW`, `TDB`, `T STW`, `L STW`;
- `FR`, `SE`, `SA`, `SI`, `SS`, `SV`;
- `L C`, `R C`, `S C`, `L T`;
- `OD`, `OW`, `UD`, `UW`, `XOD`, `XOW`, `TAR`, `TAR1`, `TAR2`, `CAW`, `CAD`, `CDB`.

## 4. Peripheral I/O

The six standard peripheral input/output pairs are:

| English | German | Meaning |
| --- | --- | --- |
| `PIB` | `PEB` | peripheral input byte |
| `PIW` | `PEW` | peripheral input word |
| `PID` | `PED` | peripheral input double word |
| `PQB` | `PAB` | peripheral output byte |
| `PQW` | `PAW` | peripheral output word |
| `PQD` | `PAD` | peripheral output double word |

## 5. Data Types and Composite Types

### 5.1 `STRUCT`

`STRUCT` describes a composite data structure with fields of different types.
It is useful when related data should be transported or stored as one logical
unit in a DB.

Key points:

- fields can be elementary types, `ARRAY`, or other `STRUCT` elements;
- structures can be nested;
- anonymous structures are possible, but `UDT` is clearer for repeated use;
- for deeper or broader data models, prefer `UDT`.

### 5.2 `ARRAY`

`ARRAY` is a field with a fixed number of elements of the same type.

Rules:

- all elements have the same data type;
- index limits are written in square brackets;
- the lower limit must be less than or equal to the upper limit;
- STEP 7 supports multiple dimensions;
- `ARRAY` limits can be defined with constants or formal parameters of a block;
- block interfaces can also use `ARRAY[*]` for variable limits.

### 5.3 `UDT`

`UDT` is a reusable user-defined data type. It centralizes a structure and
makes the same data definition available in multiple places.

It is the right choice when:

- the same data structure should be reused multiple times;
- block interfaces should stay cleaner;
- you do not want to copy `STRUCT` definitions across the project.

### 5.4 `VAR` Sections

The textual block interface is split into declarative sections. The order is not
strict, and sections may appear more than once.

| Section | Purpose |
| --- | --- |
| `VAR_INPUT` | input parameters, read-only |
| `VAR_OUTPUT` | output values, write-only |
| `VAR_IN_OUT` | in/out parameters, readable and writable |
| `VAR_TEMP` | temporary local data |
| `VAR` | static local data |
| `VAR CONSTANT` | constants in the block interface |

Attributes for declaration sections:

- `RETAIN` for retentive values;
- `DB_SPECIFIC` for retentivity in the instance DB.

### 5.5 Data Blocks (`DB`)

A `DB` stores values that are written during runtime. Unlike code blocks, a DB
contains no networks or instructions, only declarations.

DB types:

- **Global DB**: freely structured, reachable from any code block;
- **Instance DB**: bound directly to an `FB`, with structure defined by the
  `FB` interface;
- **ARRAY DB**: a global DB consisting of exactly one `ARRAY`.

Rules to keep in mind:

- the global DB structure is defined in the declaration;
- the instance DB structure comes from the `FB` interface;
- start values can be assigned to declared elements;
- an instance DB is not freely modelled.

### 5.6 Constants

Constants have a fixed value and are not modified at runtime.

There are two forms:

- **untyped**: the type is inferred from context;
- **typed**: the type is written explicitly, for example `INT#12345` or
  `REAL#1.5`.

Practical rules:

- constants can be read, but not overwritten;
- untyped constants are enough for many expressions;
- typed constants are better when the data type must be explicit;
- BOOL constants in AWL should only be used where the language mode clearly
  supports them.

## 6. Practical Writing Rules

- Every STL statement should end with `;`.
- Boolean instructions such as `A/U`, `AN/UN`, `O`, `ON`, `X`, `XN`, `S`, `R`,
  `=`, `FP`, and `FN` should use bit-compatible operands only.
- `L` and `T` should not take obvious bit operands.
- Do not mix absolute and symbolic DB addressing.
- Pointer forms and `P#...` literals must be syntactically valid.
- Jump labels must be defined inside the same block and must be unique.
- `FB` calls need a matching instance; `FC` calls do not.

## 7. Source References

This reference is aligned with Siemens STEP 7 and the official manuals and
TIA Portal documentation:

- STEP 7 STL / Statement List manual;
- STEP 7 Programming with STEP 7;
- STEP 7 declaration sections;
- STEP 7 basic principles for `STRUCT`, `ARRAY`, `UDT`, and `DB`.
