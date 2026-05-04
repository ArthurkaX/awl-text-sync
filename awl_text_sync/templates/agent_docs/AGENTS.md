# Agent Instructions

This is a STEP 7 AWL text workspace managed by `awl-text-sync`.

## Read First

Before editing, read:

- `docs/working_rules.md`
- `docs/awl_reference.md`

## CLI Overview

The `awl-text-sync` executable works both as a GUI app and a CLI tool.
Run it without arguments to launch the desktop GUI, or pass a command for headless use.

For full help:

```
awl-text-sync --help
awl-text-sync <command> --help
```

### Commands

| Command | Description |
|---|---|
| `split` | Split `Exported/*.AWL` into individual block files under `Project/Blocks/` and copy the `.sdf` symbols file to `Project/Symbols/` |
| `validate` | Parse all `.awl` blocks in `Project/Blocks/` and the `.sdf` symbols file in `Project/Symbols/` for syntax errors and consistency issues |
| `build-split` | Build a set of individual `.awl` files and a `.sdf` file under `Build/SplitImport/`, ready for import into STEP 7 |
| `build-monolith` | Combine all `Project/Blocks/*.awl` files into a single `ALL_BLOCKS.AWL` under `Build/Monolith/` |
| `init-agent-docs` | Create `AGENTS.md` and documentation files in the workspace root for AI coding agents |
| `ui` | Launch the desktop GUI |

### Options

- `--workspace <path>` — workspace root containing `Exported/`, `Project/`, and `Build/` (default: `.`)
- `--version` — print version and exit
- `--help` — print help and exit

### Validate Options

- `--call-graph` — write an interactive call graph HTML report under `Build/Reports/`
- `--open-call-graph` — open the call graph report in the default browser

### Init-Agent-Docs Options

- `--force` — overwrite existing agent docs instead of skipping them

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

## Typical Workflow

1. **Split** the export into editable files:

   ```
   awl-text-sync split --workspace .
   ```

2. Edit files under `Project/Blocks/`.

3. **Validate** after edits:

   ```
   awl-text-sync validate --workspace .
   ```

4. **Build** output for STEP 7 import:

   ```
   awl-text-sync build-monolith --workspace .
   # or
   awl-text-sync build-split --workspace .
   ```

## Safety

Make minimal changes. Do not rewrite generated files, exported originals, or unrelated blocks.
