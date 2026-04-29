---
name: project-session-handoff
description: Primes fresh chats, compacts handoffs for the next session, and audits project agent docs on sign-off for awl-text-sync. Use when the user sends /prime, /debrief, or /sign-off; asks for a new chat, handoff, carry-over, end-of-session wrap-up, or an audit of AGENTS.md, progress.md, learnings.md, or decisions.md.
---

# Project session handoff (prime / debrief / sign-off)

Repo root docs: [`AGENTS.md`](../../../AGENTS.md), [`identity.md`](../../../identity.md), [`progress.md`](../../../progress.md), [`learnings.md`](../../../learnings.md), [`decisions.md`](../../../decisions.md). Use **forward slashes** in examples. (Paths relative to this `SKILL.md`: three levels up to repo root.)

## When to use

Apply this skill when the user:

- Starts **`/prime`** or asks for **fresh context** / **new feature** priming.
- Sends **`/debrief`** and describes work to **carry into the next chat**.
- Sends **`/sign-off`**, **done for today**, **feature complete**, or asks to **audit** / **sync** agent docs.

Natural phrases (“hand off”, “compact this for the next session”, “update progress and learnings”) map to **/debrief** or **/sign-off** as appropriate.

---

## /prime — new chat / new feature

**Goal:** Load minimum project state without bloating context.

1. Read [`AGENTS.md`](../../../AGENTS.md) and [`identity.md`](../../../identity.md).
2. **If `AGENTS.md` is stub-only, empty, or self-referential** (no workspace layout / CLI): treat as defect. Read [`README.md`](../../../README.md) and [`docs/working_rules.md`](../../../docs/working_rules.md) for operational truth; tell the user `AGENTS.md` must be restored and offer to fix or run **`/sign-off`**.
3. If the user says **continue previous work**, read **Current focus** in [`progress.md`](../../../progress.md) (optional: newest session log entry).
4. Do **not** auto-load [`learnings.md`](../../../learnings.md) or [`decisions.md`](../../../decisions.md) unless the user asks or the topic clearly needs them (same policy as [`.cursor/rules/project-prime.mdc`](../../../.cursor/rules/project-prime.mdc)).
5. **Output:** A short **Session prime summary**: assumed goal (or ask one clarifying question), constraints, stack (Python tool vs STEP 7), sensible **next action** (e.g. branch, command, file).

---

## /debrief — compact handoff for the next chat

**Goal:** One copy-paste block for the **next** conversation plus durable updates in `progress.md`.

1. From the user message, extract: goal, what was done, what is left, blockers, branches/PRs, files that matter, **mistakes to avoid**, and **decisions** that must not be reversed informally.
2. Emit a single markdown **HandoffPackage** using this template (fill all applicable sections):

```markdown
## HandoffPackage — <short title>

- **Goal:** …
- **Context:** …
- **Files / areas:** `path/one`, `path/two`, …
- **Done:** …
- **Left:** …
- **Mistakes to avoid / pitfalls:** …
- **Open questions:** …
- **Suggested next step:** (command or edit) …
- **Branch / PR:** …
```

3. **Write** to repo:
   - Insert a **new** entry at the **top** of **Session log** in [`progress.md`](../../../progress.md) (after the template / `---` before older entries). Use heading `### YYYY-MM-DD — <title>` and bullets: **Outcome**, **Done**, **Next**, **Notes** (mirror HandoffPackage).
   - Update **Current focus** in [`progress.md`](../../../progress.md) (**Active goal**, **Plan / ticket**, **In flight**, **Blockers**) to match carry-over.
4. If the debrief exposes a **recurring mistake** not in [`learnings.md`](../../../learnings.md), ask whether to append a dated learning; add only if the user confirms.

---

## /sign-off — audit agent docs + revision trail

**Goal:** Agent-facing docs reflect reality; avoid drift; leave a **timestamped** revision record.

1. **Read:** [`AGENTS.md`](../../../AGENTS.md), [`identity.md`](../../../identity.md), [`progress.md`](../../../progress.md), [`learnings.md`](../../../learnings.md), [`decisions.md`](../../../decisions.md), [`.cursor/rules/project-prime.mdc`](../../../.cursor/rules/project-prime.mdc). Skim **this** skill for consistency.
2. **Reconcile:**
   - Fix stale **Current focus** or contradictions in [`progress.md`](../../../progress.md).
   - Ensure [`AGENTS.md`](../../../AGENTS.md) still matches [`README.md`](../../../README.md) for workflow / CLI / encoding (update `AGENTS.md` if it drifted).
   - If the session added **decisions** or **failures**, append [`decisions.md`](../../../decisions.md) ADR(s) or [`learnings.md`](../../../learnings.md) entries (with user confirmation for sensitive production details).
3. **Versioning — [`AGENTS.md`](../../../AGENTS.md) footer** **Agent docs revision** table:
   - Increment **revision** by 1 from current value.
   - Set **last_reviewed** to `YYYY-MM-DD` (authoritative calendar date for the review).
   - Set **summary** to **one line** describing this sign-off only.
4. **Append** to [`progress.md`](../../../progress.md) Session log (newest first):

```markdown
### Sign-off audit — YYYY-MM-DD

- **Agent docs revision:** N
- **Files touched:** AGENTS.md, progress.md, …
- **Summary:** …
```

5. **Output:** Short checklist to the user: what was updated, new revision number, anything still missing.

---

## Cross-links

- On-demand log policy: [`AGENTS.md`](../../../AGENTS.md) — Extended context.
- PLC / STL skills: [`identity.md`](../../../identity.md) skill router.
