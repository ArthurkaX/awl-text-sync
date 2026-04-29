# identity.md — environment, role, skill routing

Read this together with [`AGENTS.md`](AGENTS.md) at the start of each conversation about this project.

## Environment

- **Workstation:** Windows; prefer **PowerShell** for commands.
- **This repository:** Python **3.11+** application — split / validate / rebuild **exported** STEP 7 text (`.AWL`, `.sdf`). Source: [`awl_text_sync/`](awl_text_sync/).
- **User PLC toolchain (maintenance context):** Siemens **STEP 7 V5.6 Classic**; **S7-300 / S7-400**; exports are **.AWL** (+ symbols **.sdf**). *Adjust this line if the real installation differs.*

## Two layers (do not confuse them)

1. **awl-text-sync (this repo):** File layout, UTF-8 project files, validation, generating **cp1252** import artifacts under `Build/`.
2. **STEP 7:** Authoritative **import, compile, and download**. If `validate` passes but STEP 7 rejects an import, STEP 7 wins — sync symbols, encoding, and block headers.

## Role of the agent

- **For Python in this repo:** Maintain CLI/UI behavior, tests, and packaging; match existing style in `awl_text_sync/`.
- **For AWL/STL content** the user edits under `Project/Blocks/`: treat STEP 7 and [`docs/working_rules.md`](docs/working_rules.md) as binding; use skills below for analysis, simulation, safety, and language questions.
- **Before claiming AWL is “fixed” or “ready”** when skills require it: follow **awl-step7** / **awlsim-runner** workflows (e.g. `stl_precheck.py` gate before awlsim — see that skill).

## Skill router (project `.cursor/skills/`)

Load the skill by reading `SKILL.md` under the folder when the request matches.

| User intent (examples) | Skill folder | Notes |
|------------------------|--------------|--------|
| **`/KB`**; search local technical manuals; “what does the STL manual say”; manual-backed instruction semantics | `.cursor/skills/project-knowledgebase/` | Query `.cursor/knowledgebase/` via `indexes/sections.jsonl` then section `.md` |
| **`/prime`**, **`/debrief`**, **`/sign-off`**; fresh chat priming; handoff; end-of-session doc audit | `.cursor/skills/project-session-handoff/` | Read `SKILL.md`; updates `progress.md` / `AGENTS.md` revision on sign-off |
| Explain / refactor / create FB, FC, DB, OB; uploads `.awl`; “what does this STL do”; SIMATIC / PCS7 maintenance style | `.cursor/skills/awl-step7/` | Workflow + modes; pairs with safety for production logic |
| Run / simulate / test / verify PLC logic; “does this work”; assertions on outputs | `.cursor/skills/awlsim-runner/` | Step 0: `stl_precheck.py` before awlsim |
| Safety interlocks, fault reset, overflow guards, pre-download checklist language | `.cursor/skills/awl-safety-critical/` | Passive rules; apply via **awl-step7** analysis/authoring |
| Debug snapshot, RLO/ACCU trace, “why is this output OFF” with register data | `.cursor/skills/awl-plc-debugger/` | Needs snapshot or trace |
| “What does instruction X mean”; EN↔DE mnemonic; addressing syntax | `.cursor/skills/awl-language-reference/` | Reference only — no simulation |

## Local knowledgebase

- **Indexed manuals:** `.cursor/knowledgebase/<manual_id>/` — start chats with **`/KB`** + your question, or read [.cursor/skills/project-knowledgebase/SKILL.md](.cursor/skills/project-knowledgebase/SKILL.md) for search order (`sections.jsonl` → chapter `.md`).
- Currently **one** bundle: `step7-stl-statement-list` (STL reference for S7-300/S7-400). Quick mnemonic tables: **awl-language-reference**; deep manual text: **`/KB`**.

## Logs (on user request)

See [`AGENTS.md`](AGENTS.md): load [`learnings.md`](learnings.md), [`decisions.md`](decisions.md), [`progress.md`](progress.md) only when the user asks or during explicit handoff.
