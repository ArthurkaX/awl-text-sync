# Agent Instructions

This is a STEP 7 AWL text workspace managed by `awl-text-sync`.

## Read First

Before editing, read:

- `docs/working_rules.md`
- `docs/awl_reference.md`

## Workspace Layout

- `Exported/` contains original STEP 7 exports. Do not edit it.
- `Project/Blocks/` contains editable AWL block files.
- `Project/Symbols/` contains the active symbol table.
- `Build/` contains generated output. Do not edit it.

## Editing Rules

- Edit AWL block files only under `Project/Blocks/` unless the task explicitly requires symbol changes.
- Keep one block per file.
- Do not change block type or block number unless explicitly requested.
- Keep filename, block header, and symbol table entry aligned.
- Do not mix symbolic and absolute DB addressing in one reference.
- Keep pointer literals absolute and syntactically valid.
- Keep jump labels local to the block and unique.
- Match `CALL` parameters to the real target block interface.
- Preserve formatting unless the task requires a wider rewrite.

## Validation

After edits, run:

```powershell
awl-text-sync validate --workspace .
```

Before producing STEP 7 import output, run one of:

```powershell
awl-text-sync build-monolith --workspace .
awl-text-sync build-split --workspace .
```

## Safety

Make minimal changes. Do not rewrite generated files, exported originals, or unrelated blocks.
