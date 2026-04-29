# Rules For Editing This Project

This repository is a STEP 7 AWL text-sync workspace. Edit it so that `awl-text-sync validate` still passes and STEP 7 can still import and compile the generated output.

## Scope

- Edit AWL block files only in `Project/Blocks/` unless the task explicitly requires Python code changes.
- Treat `Project/Symbols/*.sdf` as the source of truth for symbolic block names.
- Import the symbols file together with the blocks before validating or compiling.
- Do not edit generated output in `build/` or `dist/`.

## Keep Every AWL File Parseable

- Each `Project/Blocks/*.awl` file must contain exactly one block.
- Keep the original block kind and block number unchanged.
- Keep the first header line valid for that block kind:
  - `TYPE UDT n`
  - `DATA_BLOCK DB n`
  - `FUNCTION_BLOCK FB n`
  - `FUNCTION FC n : ...`
  - `ORGANIZATION_BLOCK OB n`
- Keep the correct closing line:
  - `END_TYPE`
  - `END_DATA_BLOCK`
  - `END_FUNCTION_BLOCK`
  - `END_FUNCTION`
  - `END_ORGANIZATION_BLOCK`
- Do not place non-empty text outside the single block.

## Filename Rules

- Do not rename block files casually.
- Filename type and number must match the internal block header.
- Preferred filename format is canonical: `<type><number>_<name>.awl`, for example `fb68_FB_Std_Deviation.awl`.
- Build the filename suffix from the block symbol or internal `NAME` by replacing punctuation and spaces with underscores.
- Example: `FC 1` with `NAME : FACTORY_RESET` becomes `fc1_factoryreset.awl`.
- If a block already has a symbol or internal `NAME`, keep the filename, symbol, and block identity aligned.

## Symbols And Names

- If a block has a symbolic identity in `Project/Symbols/*.sdf`, keep the symbol name and filename aligned with that identity.
- Do not invent a second spelling for the same symbol. For example, `OB1_MAX_CYCLE` is valid, but `OB1 MAX CYCLE` is not.
- Do not use reserved words as symbol names. `COUNTER` is a STEP 7 keyword, so prefer names like `LeftCounter` and `RightCounter`.
- Do not change `Symbols.sdf` unless the task explicitly requires a coordinated symbol rename.
- If you rename a symbol, update all three together:
  - the block content
  - the filename
  - the matching entry in `Project/Symbols/*.sdf`

## STL Safety Rules

- Preserve valid STEP 7 STL syntax.
- Do not mix symbolic and absolute DB access in one reference.
  - Allowed: `DB1.DBW2`
  - Allowed: `HMI.Number`
  - Not allowed: `DB1.Number`
  - Not allowed: `HMI.DBW2`
- Keep pointer literals absolute.
- Bare pointer assignments like `P#P 0.0` are allowed when the source uses a pointer value, not a sized transfer.
- Bare pointer offsets like `P#0.0` are allowed in indirect addressing.
- Local pointer references like `P##s_Msg_Statistical` are allowed.
  - Allowed: `P#DB1.DBX0.0 WORD 1`
  - Allowed: `P#P 0.0`
  - Allowed: `DBW [AR1,P#0.0]`
  - Allowed: `L     P##s_Msg_Statistical`
  - Allowed: `P#I1000.0 BYTE 12`
  - Not allowed: `P#DB1.Number WORD 1`
  - Not allowed: `P#HMI.DBW2 WORD 1`
- If you add or change jump instructions like `JU`, `JC`, `JCN`, `JZ`, `JN`, `JP`, `JM`, or `LOOP`, make sure the target label exists in the same block.
- Do not duplicate labels inside a block.

## CALL Rules

- `CALL FB n` needs an instance DB unless it calls a declared local instance such as `CALL #LOADINGINST (...)`.
- Only FB calls may carry an instance DB.
- Local instances belong in `VAR` or `VAR_TEMP`, for example `LOADINGINST : FB 1 ;`.
- The declaration name and the `CALL #...` target must match exactly.
- Do not place local instance declarations in `VAR_INPUT`, `VAR_OUTPUT`, or `VAR_IN_OUT`.
- When calling a workspace block, use only interface parameter names that really exist in that block.
- Do not remove required instance DB relationships when editing FB calls.

## Editing Discipline

- Make the smallest safe change that solves the task.
- Preserve existing formatting and line structure when possible.
- Do not mass-normalize headers, comments, or spacing unless the task requires it.
- Do not convert symbolic headers to numeric headers or numeric headers to symbolic headers unless the task explicitly requires it and the symbols file is updated consistently.

## Before Finishing

- Re-check the edited files for:
  - matching filename and block header
  - correct end keyword
  - valid jump labels
  - valid `CALL` form
  - no mixed symbolic/absolute DB access
  - absolute-only `P#...` pointer targets
- If the project uses `Project/Symbols/*.sdf`, confirm the file was imported and the names still match.
- If Python code was changed, keep the CLI commands and workspace layout behavior compatible with the current README.
