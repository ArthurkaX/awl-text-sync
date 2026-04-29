# Synthetic `plccheck` demo root

Non-proprietary minimal files so `plccheck check .` has at least one analyzable source.

- `.plc.json` — placeholder PLC metadata in Dynamic / `plccheck` style.
- `Main.scl` — trivial function block stub (not a full TIA export).

This does **not** model a real CPU or symbol table. It exists to exercise **D0_smoke** (CLI plumbing) only.
