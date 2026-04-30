# Working Rules

This repository is a STEP 7 AWL text workspace. Keep it editable outside STEP 7, and keep `awl-text-sync validate` green before import.

## How The Project Works

- Export one `.AWL` source and one `.sdf` symbol file from STEP 7.
- Prefer `Absolute` export for the smoothest automation path; `Symbolic` export also works if the symbol table is complete and consistent.
- Run `split` to create the editable workspace under `Project/Blocks/` and `Project/Symbols/`.
- Edit block text files in `Project/Blocks/`.
- Run `validate` before `build-split`, `build-monolith`, or STEP 7 import.
- Keep `docs/validate_stl_rules.md` for detailed STL validation rules.

## Creating A New Block

- Create exactly one block per `.awl` file.
- Use the canonical filename pattern: `<type><number>_<name>.awl`.
- Keep the file header, filename, and symbol name aligned.
- Use the correct STEP 7 header and footer for the block kind:
  - `TYPE UDT n` ... `END_TYPE`
  - `DATA_BLOCK DB n` ... `END_DATA_BLOCK`
  - `FUNCTION_BLOCK FB n` ... `END_FUNCTION_BLOCK`
  - `FUNCTION FC n : ...` ... `END_FUNCTION`
  - `ORGANIZATION_BLOCK OB n` ... `END_ORGANIZATION_BLOCK`
- If the block needs a public symbol, add or update the matching entry in `Project/Symbols/*.sdf`.
- Do not create two spellings for the same identity.

## Editing An Existing Block

- Keep the block kind and number unchanged.
- Make the smallest safe change that solves the task.
- Preserve the original structure and formatting unless the edit requires a wider rewrite.
- If you rename a block or symbol, update all three together:
  - block content
  - filename
  - symbol entry in `Project/Symbols/*.sdf`
- One block equals one file.
- The block type and block number must not change.
- The filename must match the block header, for example `fb68_FB_Std_Deviation.awl`.
- Do not mix symbolic and absolute DB access in one reference.
- Keep pointer literals absolute.
- End each STL statement with `;`, including simple instructions and `CALL` statements.
- Boolean opcodes such as `A`, `AN`, `O`, `ON`, `X`, `XN`, `S`, `R`, `=`, `FP`, and `FN` should use bit-compatible operands.
- Jump labels must exist in the same block and must not be duplicated.
- `CALL` targets, instance DBs, and parameter names must match the workspace block interface.
- `FB` calls require an instance DB.
- Local instances must use `#` where the block interface expects them.
- Parameters must come from the real target interface, not guessed names.

## Core Editing Rules

These are the formal constraints that keep the workspace stable:

- one block equals one file;
- block type and number are immutable;
- filename, block header, and `Project/Symbols/*.sdf` entry must stay in sync;
- symbolic and absolute DB access must not be mixed in the same reference;
- pointer handling must stay absolute and syntactically valid;
- jump labels must be defined in the same block and must be unique;
- `FB` calls require an instance DB;
- local instances use `#` syntax where applicable;
- `CALL` parameters must match the real interface exactly;
- keep formatting intact unless the task explicitly requires a wider rewrite.

**Goal**: Neither a human nor an AI should break the project with a random
rename or a syntax error.

## Before You Finish

- Re-run `validate`.
- If the change touched symbols, confirm `Project/Symbols/*.sdf` still matches the blocks.
- If the change touched Python code, keep the workspace layout and CLI behavior compatible with the current README.
