# STL Validation Rules for `validate`

This document defines the rules worth checking in `validate` for STEP 7 STL
sources.

## 1. Goal

`validate` should catch:

- invalid STL commands;
- wrong operand counts and shapes;
- addressing errors;
- invalid block calls;
- label and jump errors;
- basic mismatch between a block and its interface.

The check should stay STL-only, with no SCL logic and no full program execution.
If SCL text appears in a source, `validate` must ignore it and not try to apply
STL command rules to it.

## 2. What Already Exists

The current validator already checks:

- file name, block type, and block number;
- closing `END_*`;
- consistency between absolute and symbolic DB addressing;
- absolute `P#` literals;
- duplicate blocks.

That is a good base, but it is not enough for STL-only validation of commands
and block calls.

## 3. Rule Sources

The main STL rules come from:

- Siemens STEP 7 STL manual, especially data block instructions and the STL
  operation overview;
- Berger STL/SCL, especially addressing variables, indirect addressing,
  pointers, block calls, and jump labels.

## 4. Required Checks

### 4.1 STL Commands

Check that:

- the opcode is known;
- the opcode is valid in STL;
- the operand count matches the instruction;
- operand categories are valid for that instruction.

For the first implementation step, keep this conservative:

- bit-style opcodes like `A`, `AN`, `O`, `ON`, `X`, `XN`, `S`, `R`, `=`, `FP`, and `FN` should reject clearly non-bit operands;
- `L` and `T` should reject clearly bit operands;
- do not try to fully type-check the accumulator or arithmetic chains.

Minimal first set of commands to cover:

- `A`, `AN`, `O`, `ON`, `X`, `XN`;
- `=`, `S`, `R`, `NOT`, `SET`, `CLR`;
- `L`, `T`;
- `OPN`, `CDB`, `BE`, `BEC`;
- `JU`, `JC`, `JCN`, `JBI`, `JNBI`, `JZ`, `JN`, `JP`, `JM`;
- `CALL`, `UC`, `CC`.

### 4.2 Addressing

Check:

- absolute addresses `I`, `Q`, `M`, `L`;
- `DBX`, `DBB`, `DBW`, `DBD`;
- validity of `DB n.DBX/DBB/DBW/DBD`;
- no mixing of absolute and symbolic DB addressing;
- no symbol-based addressing inside indirect addressing;
- correctness of `P#...` pointer literals;
- correctness of `ANY`-like forms if they appear in target blocks.

### 4.3 Indirect Addressing

Check:

- indirect addressing is used only with absolute addressing;
- `P#` target must be absolute;
- register-indirect offset must be a constant;
- digital addresses must use bit address `0`;
- indirect-address form must match STL syntax;
- if `AR1/AR2` is used, the address form must be valid for STL.

### 4.4 DB Instructions

Check:

- `OPN` accepts only `DB` or `DI`;
- `DB`/`DI` number is within the valid range;
- `CDB` has no operands;
- `L DBLG`, `L DBNO`, `L DILG`, `L DINO` have no extra operands;
- `DB` and `DI` usage is compatible with the block type.

### 4.5 Block Calls

Check:

- the target block exists;
- the target block type is valid for the call form;
- `FB` calls are consistent with instance DB or local instance usage;
- `FC` calls do not require an instance DB;
- actual parameters match the target block interface;
- simple actual/formal type combinations are compatible for `CALL`;
- there are no extra or unknown parameters;
- `VAR_OUTPUT` parameters may be omitted unless a future rule needs them.
- quoted targets and quoted instance DB names that resolve to workspace blocks are validated the same way as numeric references.
- `ANY`, `POINTER`, and `BLOCK_DB` parameters should be treated as pointer-like categories.
- `CALL` arguments that start with `P#` must be valid pointer literals; malformed pointer-like shapes should be rejected before import.
- Direct addresses such as `DB1.DBX0.0` should not be passed to pointer-like `CALL` parameters unless they are rewritten as valid `P#...` literals.

### 4.6 Labels and Jumps

Check:

- the label is declared in the same block;
- the label is not duplicated inside the block;
- the jump instruction points to an existing label;
- the label name follows valid STL naming rules.

## 5. Implementation Stages

### Stage 1. Normalize STL Lines

Build one shared line parser:

- remove comments;
- extract the opcode;
- extract operands;
- detect labels or calls when applicable.

### Stage 2. Command Registry

Create a table of the form:

- `opcode -> descriptor`

The descriptor should store:

- operand count;
- allowed operand types;
- special restrictions.

### Stage 3. Operand Validators

Create reusable helpers for:

- addresses;
- `P#` literals;
- indirect addressing;
- jump targets;
- block references.

### Stage 4. Block Call Validation

Add checks for:

- block existence;
- block type;
- parameter interface;
- instance/local-instance compatibility.

### Stage 5. Label and Jump Validation

Do this in two passes:

1. collect labels;
2. validate jump targets.

### Stage 6. Tests

For every rule, add:

- one valid example;
- one invalid example;
- a clear error message.

## 6. DRY Rules

To avoid duplicating the same logic:

- use one shared STL line parser;
- use one shared address parser;
- use one shared parser for `P#` and indirect forms;
- use one shared opcode registry;
- use one shared error format;
- use one shared block-body scan;
- use one shared mechanism for labels and jump targets.

Do not:

- duplicate regexes across validators;
- repeat `split("//")`, `strip()`, or opcode/operand extraction in multiple
  places;
- write separate ad-hoc code for every command when a shared descriptor works.

## 7. Out of Scope

Do not add yet:

- full STL semantic simulation;
- instruction result evaluation;
- SCL rules or SCL-specific validation;
- STEP 7 runtime checks;
- timestamp or consistency checks from the STEP 7 editor.

## 8. Done Criteria

`validate` is good enough for STL when it:

- catches unknown commands;
- catches invalid operands;
- catches addressing errors;
- catches invalid block calls;
- catches label/jump errors;
- avoids duplicated logic;
- reports clear file and line information.
