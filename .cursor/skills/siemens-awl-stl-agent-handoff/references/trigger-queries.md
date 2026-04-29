# Trigger queries — should vs should-not route to this skill

Use **`siemens-awl-stl-agent-handoff`** when the user needs **workflow / authority ordering / tooling reality** for **STEP 7 Classic AWL** plus optional **TIA/plccheck**. Use **other** skills for pure code review (`awl-step7`), simulation (`awlsim-runner`), or mnemonics (`awl-language-reference`).

## Should trigger (examples)

1. “We use Cursor on `.awl` — what ‘LSP’ actually checks Siemens STL?”
2. “Should I use **trust-lsp** for our AWL blocks?”
3. “Agent loop: edit AWL then what CLI do I run before STEP 7?”
4. “Does **plccheck** replace `awl-text-sync validate`?”
5. “Wire **Dynamic Siemens** / **plccheck** into CI for Classic exports.”
6. “`.awl` shares `siemens` language id with SCL — is that safe to trust?”
7. “Hybrid shop: Classic STEP 7 + TIA export — what order of validators?”
8. “Why does `plccheck` do nothing on empty folder / blocks-only copy?”
9. “Headless agent: how do I get diagnostics without VS Code?”
10. “Is there a pure-AWL SEMANTICS LSP equal to STEP 7 compiler?”
11. “CC-BY-NC — can we run `plccheck` in production CI?”
12. “Repair loop: subprocess vs `textDocument/publishDiagnostics` for AWL.”
13. “Split workspace **Project/Blocks** — what’s authoritative vs auxiliary?”
14. “IEC IL vs Siemens STL — which LSP applies?”
15. “Document gates: validate → build → import for agents.”

## Should NOT trigger alone (use other skills / docs)

1. “What does **AUF** do in STL?” → **`awl-language-reference`** or **`/KB`**
2. “Refactor this FB for hysteresis.” → **`awl-step7`**
3. “Run awlsim on this block.” → **`awlsim-runner`**
4. “Parse this RLO/ACCU snapshot.” → **`awl-plc-debugger`**
5. “Prime handoff / update progress.md.” → **`project-session-handoff`**
6. “Pure Python bug in `awl_text_sync` package.” → repo **AGENTS.md** + code — not this skill’s focus

## Edge cases

- User mentions **IEC ST file** (`.st` from CODESYS-style) **and** Classic **`.awl`** → clarify toolchain; this skill covers **Classic path** + **honesty** about ST LSPs.
- User insists **“Siemens LSP said it’s fine”** → cite **authority pyramid**; require **SIMATIC** for sign-off.
