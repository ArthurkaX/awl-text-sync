# TIA-oriented tooling: Dynamic Siemens, `plccheck`, `.plc.json`

**What it is:** The **Dynamic Siemens Language Support** ecosystem (VS Code extension, bundled **`siemens-lsp`**, npm **`plccheck`**) targets **SCL/ST** and **TIA-style** project trees — artifacts like **`.plc.json`**, **`.scl`**, **`.st`**, **`.s7res`**, **`.s7dcl`**, etc.

**`.awl` in VS Code:** Files may share a **Siemens** language id with SCL/ST; **operational attachment** of LSP ≠ **advertised Classic STL semantic parity**.

**`plccheck check`:** Analyzes **folders with supported sources** and project metadata — not “an empty PLC root” or a bare **awl-text-sync** `Project/Blocks` folder copied alone.

**Integration in this repo:** Optional **`--plccheck-root`** on `validate` runs native validate first, then **`plccheck`** when you supply a valid TIA-style path. See **`docs/siemens_plccheck_experiment.md`** for layout diagrams, D0 smoke, and license (**CC-BY-NC-4.0**).

**Agent pattern:** Spawn **`plccheck`** as subprocess; parse stdout/stderr. Treat results as **hints** that never override SIMATIC compile.

**Headless LSP:** Whether a long-running **`plccheck serve`** or equivalent exposes **LSP** to non-IDE clients is **[Unverified]** unless your environment documents it — do not assume Cursor agents receive the same diagnostics as the VS Code UI.
