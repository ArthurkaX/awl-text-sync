# Common misconceptions: IL, Structured Text, Siemens STL

| Term | What people confuse | Reality for this workflow |
|------|---------------------|---------------------------|
| **IEC 61131-3 IL** | “IL = Siemens STL” | Different standard vs vendor mnemonic STL; tooling overlap is **not** automatic. |
| **Structured Text (ST)** | “AWL is ST” | **ST** is high-level IEC text; **Classic AWL/STL** is **Statement List** mnemonics and SIMATIC block structure. |
| **truST / `trust-lsp`** | “Use it for `.awl`” | Scoped to **IEC ST** (e.g. **StLanguage**); **not** a STEP 7 Classic STL compiler substitute. |
| **“Siemens LSP colors my .awl”** | “So the LSP proves Classic correctness” | You may get **fast feedback** in **their** text model; **false positives/negatives** are possible on Classic-only patterns. |
| **LSP in the IDE** | “The coding agent sees the same diagnostics” | Default agents run **outside** the LSP client — use **CLI validators** unless you built a bridge. |

**Honesty rule:** Do not claim **open**, **standalone** LSP equals **SIMATIC STL** semantics without evidence. Prefer **`awl-text-sync validate`** + **SIMATIC compile** for Classic AWL.
