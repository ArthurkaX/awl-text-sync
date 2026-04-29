# AGENTS.md — awl-text-sync

Instructions for AI agents and developers working in this repository. Read this file and [`identity.md`](identity.md) at the **start of each new chat** or before substantive work (use the Read tool or `@AGENTS.md` / `@identity.md`).

## What this repo is

`awl-text-sync` is a **Python** tool that splits exported Siemens STEP 7 **.AWL** sources (+ **.sdf** symbols) into a **git-friendly workspace**, validates the workspace, and rebuilds STEP 7–importable output. It does **not** replace STEP 7: export → edit here → validate → build → import → compile still happens in STEP 7.

## Workspace layout

```text
workspace/
  Exported/          # Original export: one .AWL, symbols .sdf
  Project/
    Blocks/          # One block per .awl file (UTF-8)
    Symbols/         # .sdf copy (UTF-8)
  Build/
    Monolith/        # Generated monolith (cp1252)
    SplitImport/     # Generated split import (cp1252)
    Reports/         # e.g. call_graph.html
```

Treat **`Build/*` as generated**; edit **`Project/`** and keep **`Exported/`** as the audit trail of the handoff.

## CLI (workspace root = `.`)

| Command | Purpose |
|---------|---------|
| `awl-text-sync split --workspace .` | Create `Project/Blocks/` + `Project/Symbols/` from `Exported/` |
| `awl-text-sync validate --workspace .` | Validate blocks + symbols |
| `awl-text-sync validate --workspace . --call-graph` | Also write `Build/Reports/call_graph.html` |
| `awl-text-sync validate --workspace . --call-graph --open-call-graph` | Open report in browser |
| `awl-text-sync build-split --workspace .` | Write split import under `Build/SplitImport/` |
| `awl-text-sync build-monolith --workspace .` | Write `Build/Monolith/` monolith |
| `awl-text-sync ui` | Desktop UI (same actions) |

Aliases: `s7p-sync`, `awl-text-sync-ui`, `s7p-sync-ui` (see `pyproject.toml`).

## Development setup

- **OS:** Windows (primary); shell: **PowerShell**.
- **Python:** ≥ 3.11 (`pyproject.toml`).
- Venv at repo root: `python -m venv .venv` then `.\.venv\Scripts\Activate.ps1`.
- Editable install: `python -m pip install -e .`
- Tests: `python -m pytest` from repo root (install `pytest` in the venv if needed).

Python package code lives under [`awl_text_sync/`](awl_text_sync/).

## Encoding

- **split:** auto-detects export encoding for `Exported/*.AWL` and `.sdf`.
- **Project files:** UTF-8.
- **build-split / build-monolith:** output **cp1252** for STEP 7 import.
- **validate:** checks round-trip safety toward STEP 7–compatible output.

## Editing AWL in this workspace

Follow [`docs/working_rules.md`](docs/working_rules.md). Detailed validator design and STL rules: [`docs/validate_stl_rules.md`](docs/validate_stl_rules.md). Flow diagram: [`docs/workflow.mermaid`](docs/workflow.mermaid). Product overview: [`README.md`](README.md).

## Session workflows (`/prime`, `/debrief`, `/sign-off`)

For fresh context, handoff to a new chat, or end-of-session doc audit, follow [`.cursor/skills/project-session-handoff/SKILL.md`](.cursor/skills/project-session-handoff/SKILL.md).

## Local technical manuals (`/KB`)

Indexed PDF-derived manuals live under [`.cursor/knowledgebase/`](.cursor/knowledgebase/). Start a question with **`/KB`** (or see [`.cursor/skills/project-knowledgebase/SKILL.md`](.cursor/skills/project-knowledgebase/SKILL.md)) so the agent searches `indexes/sections.jsonl` then opens the matching chapter section `.md`.

## Extended context (on user request only)

Do **not** load these unless the **user asks** (e.g. “check learnings”, “read decisions”, “hand off / update progress”) or a handoff workflow explicitly requires it:

| File | Use |
|------|-----|
| [`learnings.md`](learnings.md) | Past mistakes, RCAs, fixes — avoid repeating errors |
| [`decisions.md`](decisions.md) | Architecture / design decisions — reduce agent drift |
| [`progress.md`](progress.md) | What was done, current plan slice, blockers — session handoff |

When the user **signs off** or runs **`/sign-off`**, update agent docs per the session-handoff skill and bump **Agent docs revision** below.

## Skills and PLC context

Skill routing, STEP 7 environment assumptions, and paths to `.cursor/skills/` are in [`identity.md`](identity.md).

---

## Agent docs revision

Updated on **`/sign-off`** (see `project-session-handoff` skill). Increment **revision** monotonically; set **last_reviewed** to ISO date `YYYY-MM-DD`; **summary** is one line for this review only.

| Field | Value |
|-------|-------|
| revision | 2 |
| last_reviewed | 2026-04-29 |
| summary | Added project-session-handoff skill; restored full AGENTS.md; wired identity.md skill router. |
