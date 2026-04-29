# learnings.md — mistakes, RCAs, fixes

**Load on user request** (see [`AGENTS.md`](AGENTS.md)). Append new entries after incidents so the same mistake is not repeated.

## How to add an entry

Use this shape (newest first):

```markdown
### YYYY-MM-DD — short title

- **Symptom:** …
- **Root cause:** …
- **Fix:** …
- **Prevention:** …
```

---

## Log

### 2026-04-29 — `pip install -e .` fails: “Multiple top-level packages … `img`”

- **Symptom:** Editable install fails; setuptools reports multiple top-level packages in flat layout: `img`, `awl_text_sync`.
- **Root cause:** Repo root has a top-level `img/` (assets only). Modern setuptools auto-discovery treated more than one tree as package roots.
- **Fix:** In `pyproject.toml`, constrain discovery:

```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["awl_text_sync*"]
```

- **Prevention:** Keep non-Python asset dirs out of package discovery; if adding more Python packages, list them explicitly or use `src/` layout.
