# Classic STL / AWL split workspace

**Context:** STEP 7 exports **.AWL** monoliths (and **.sdf** symbols). Tools like **awl-text-sync** split them into **UTF-8** `Project/Blocks/*.awl` and validate **round-trip** safety toward **cp1252** **Build/** import artifacts.

**Primary gate:** `awl-text-sync --workspace <root> validate` (`--workspace` before the subcommand) — encodes repo-specific STL rules (`stl_validation.py`, `validator.py`) aligned with **STEP 7–oriented** text, not IEC ST.

**After validate:** `build-split` / `build-monolith` → engineer imports into SIMATIC → **compile** remains authoritative.

**Encoding:** `Project/` is UTF-8; **Build/** outputs are cp1252 for import — do not assume every editor default matches SIMATIC import encoding.
