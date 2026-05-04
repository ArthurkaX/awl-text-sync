# awl-text-sync

Turn exported STEP 7 AWL projects into a clean, git-friendly workspace you can actually work with.

`awl-text-sync` splits monolithic STEP 7 exports into editable per-block files, validates changes before import, and rebuilds STEP 7-ready output from the same workspace. If you maintain legacy PLC code, review changes in git, or need a safer way to edit and analyze exported projects on Windows, this tool removes a lot of friction.

## What You Get

- Faster review and search across individual blocks instead of one giant `.AWL` file.
- A repeatable `split -> edit -> validate -> build` workflow.
- Git-friendly files for diffing, code review, and history.
- Safer round trips back into STEP 7.
- Optional desktop UI for local maintenance work near the equipment.
- Workspace files that are easier to feed into automation or analysis tools.

## Important

- This tool works on exported STEP 7 text sources. It does not replace STEP 7 itself.
- The safest workflow is still: export from STEP 7, edit in the workspace, validate, rebuild, import back, then compile in STEP 7.
- For the most reliable `split -> validate -> build` round trip, prefer `Absolute` export.
- `Symbolic` export is supported, but it depends more heavily on a complete and consistent `Symbols.sdf`.

## Why Use It

- Split one large exported AWL source into editable per-block files.
- Keep blocks and symbols in a predictable workspace layout.
- Safely translate comments into a language your team can read, without rewriting the surrounding STEP 7 structure by hand.
- Describe a fault or observed behavior to an LLM and get a fast surface-level analysis against readable per-block sources instead of one monolithic export.
- Validate changes before import back into STEP 7.
- Make review, search, and history easier when the project is stored in git.

## Why People Adopt It

Most STEP 7 export workflows are optimized for import, not for real work:

- Large exports are hard to diff, hard to review, and unpleasant to navigate.
- Small edits are risky when they happen inside a monolithic file.
- Encoding mistakes and manual re-save steps cause avoidable import failures.

`awl-text-sync` gives you a structured workspace so the project becomes easier to understand, safer to change, and more practical to keep under version control.

## Installation

For normal Windows use, download the latest `awl-text-sync.exe` from GitHub Releases.

Current release: `v1.1.0`

SHA256:

```text
531021C93D798F888E19148F617E4729842EECEB63C2C3C84BE7292FB96243A1
```

If you want the fastest path to a working setup, install the release binary and point it at an exported STEP 7 workspace.

For local development from this repository:

```powershell
python -m pip install -e .
```

To run the UI directly from a cloned checkout:

```powershell
python -m awl_text_sync ui
```

## Quick Start

1. Export from STEP 7:
   - one `.AWL` source
   - one `.sdf` symbols file
   - place both files in `Exported/`
2. Split the exported project into editable files:

```powershell
awl-text-sync split --workspace .
```

3. Edit the generated files in `Project/Blocks/` and `Project/Symbols/`.
4. Validate the workspace before rebuilding:

```powershell
awl-text-sync validate --workspace .
```

5. Build STEP 7 import output when needed:

```powershell
awl-text-sync build-split --workspace .
awl-text-sync build-monolith --workspace .
```

6. Import the rebuilt output back into STEP 7 and compile there.

If you already know STEP 7 exports, this is the shortest path from “hard-to-read dump” to “editable project workspace”.

## Round Trip Workflow

The intended cycle is:

`STEP 7 export -> split -> edit -> validate -> build -> STEP 7 import -> STEP 7 compile`

![Round-trip workflow](./img/export-edit-import-compile.gif)

For the detailed flow, see [docs/workflow.mermaid](./docs/workflow.mermaid).

## Desktop UI Preview

For local maintenance work on Windows, the desktop UI exposes the same workspace flow from one root folder.

![Desktop UI preview](./img/view.png)

Available actions in the UI:

- `Split`
- `Validate`
- `Call Graph`
- `Build Split`
- `Build Monolith`

The UI is intended for quick local operation near the equipment, without requiring routine CLI use.

## Best Fit

This tool is a good fit if you:

- work with STEP 7 exports on Windows;
- want smaller files and cleaner diffs in git;
- need to validate round trips before import;
- maintain legacy PLC projects where readability matters;
- want to inspect or analyze code without constantly opening STEP 7.

It is not a replacement for STEP 7. It is the layer that makes STEP 7 exports much easier to work with.

## Commands

```powershell
awl-text-sync split --workspace .
awl-text-sync validate --workspace .
awl-text-sync validate --workspace . --call-graph
awl-text-sync validate --workspace . --call-graph --open-call-graph
awl-text-sync build-split --workspace .
awl-text-sync build-monolith --workspace .
awl-text-sync init-agent-docs --workspace .
awl-text-sync ui
```

GUI entry points:

```powershell
awl-text-sync-ui
s7p-sync-ui
```

## Workspace Layout

```text
workspace/
  Exported/
  Project/
    Blocks/
    Symbols/
  Build/
    Monolith/
    SplitImport/
    Reports/
```

- `Exported/` contains the original STEP 7 handoff files.
- `Project/Blocks/` contains editable AWL block files in `UTF-8`.
- `Project/Symbols/` contains the copied `.sdf` used during validate and build, also normalized to `UTF-8`.
- `Build/Monolith/` contains generated monolithic STEP 7 import output in `cp1252`.
- `Build/SplitImport/` contains generated split import output in `cp1252`.
- `Build/Reports/` contains optional reports such as call graph HTML output.

## Encoding Policy

- `split` auto-detects the source encoding of exported `.AWL` and `.sdf` files.
- Editable project files are normalized to `UTF-8`.
- `build-monolith` and `build-split` always write STEP 7 import output in `cp1252`.
- `validate` checks whether project files can round-trip safely back to STEP 7-compatible output.
- Treat `Build/*` as generated output. Do not edit or re-save those files unless you intentionally want to change the generated result.

## Agent Bootstrap Docs

Create agent-facing workspace instructions when a workspace should be edited by Codex, Cursor, Claude Code, or another AI assistant:

```powershell
awl-text-sync init-agent-docs --workspace .
```

This writes:

- `AGENTS.md`
- `docs/working_rules.md`
- `docs/awl_reference.md`

Existing files are skipped by default. Use `--force` only when you intentionally want to overwrite the generated agent docs.

## Editing Rules

- One block per `.awl` file.
- Keep the filename, block header, and symbol entry aligned.
- Keep pointer literals absolute.
- Do not mix symbolic and absolute DB access in one reference.
- Make the smallest safe change that solves the task.

Short working rules: [`docs/working_rules.md`](./docs/working_rules.md)  
Detailed STL validation rules: [`docs/validate_stl_rules.md`](./docs/validate_stl_rules.md)

## STEP 7 Import Notes

1. Import the rebuilt AWL source from `Build/Monolith/`, or use the files from `Build/SplitImport/`.
2. Import the matching symbols file from the same `Build/` output set.
3. Compile in STEP 7 only after both the block source and symbols are in sync.

If the symbols file and block text disagree, or if generated files were re-saved with the wrong encoding, STEP 7 may reject the import or fail to compile.
