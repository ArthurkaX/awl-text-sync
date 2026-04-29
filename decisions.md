# decisions.md — architecture and design log

**Load on user request** (see [`AGENTS.md`](AGENTS.md)). Use ADR-style entries to prevent agent drift. Newest first.

## Template

```markdown
### ADR-XXX: Short title

- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Deprecated
- **Context:** …
- **Decision:** …
- **Consequences:** …
```

---

## Decisions

### ADR-004: Project session-handoff skill lives under `.cursor/skills/project-session-handoff/`

- **Date:** 2026-04-29
- **Status:** Accepted
- **Context:** Need consistent `/prime`, `/debrief`, `/sign-off` behavior and doc audit/version trail without bloating always-on rules.
- **Decision:** Add `project-session-handoff` Cursor skill with `SKILL.md`; `AGENTS.md` holds **Agent docs revision** table updated on `/sign-off`; `progress.md` holds sign-off audit entries.
- **Consequences:** Agents load the skill when user invokes slash commands or handoff language; `identity.md` routes to this folder.

### ADR-003: setuptools package discovery limited to `awl_text_sync`

- **Date:** 2026-04-29
- **Status:** Accepted
- **Context:** Editable installs failed when setuptools discovered `img/` at repo root alongside `awl_text_sync/`.
- **Decision:** Set `[tool.setuptools.packages.find] include = ["awl_text_sync*"]` in `pyproject.toml`.
- **Consequences:** Releases and `pip install -e .` only package `awl_text_sync`; `img/` remains documentation assets only.

### ADR-002: Generated build output uses cp1252

- **Date:** (documented upstream); recorded here 2026-04-29
- **Status:** Accepted — see [`README.md`](README.md)
- **Context:** STEP 7 import expects Windows ANSI-style encoding for handoff files.
- **Decision:** `build-monolith` and `build-split` write import artifacts in **cp1252**; editable `Project/` files stay **UTF-8**.
- **Consequences:** Do not re-save `Build/*` in wrong encoding; validation checks round-trip expectations.

### ADR-001: Prefer absolute STEP 7 export for round trip

- **Date:** (documented upstream); recorded here 2026-04-29
- **Status:** Accepted — see [`README.md`](README.md)
- **Context:** Symbolic exports depend on a complete, consistent symbol table.
- **Decision:** Prefer **Absolute** export for the most reliable `split → validate → build` cycle; symbolic supported when `Symbols.sdf` is trustworthy.
- **Consequences:** Agents should not advise symbolic-only workflows without symbol-table caveats.
