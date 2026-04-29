---
name: project-knowledgebase
description: Queries local Siemens and technical manuals indexed under .cursor/knowledgebase for manual-backed STL and automation answers. Use when the user sends /KB, asks to search the knowledgebase or local manual, wants what the STL reference says about an instruction or topic, or needs primary manual evidence beyond short mnemonic lookup. Use for deep instruction semantics, status-word behavior, and chapter-level text; do not use for Python awl-text-sync tool internals.
---

# Local technical manuals (`/KB`)

Indexed manuals live under **`.cursor/knowledgebase/<manual_id>/`**. Each immediate subdirectory is one manual. **Discover** KBs by listing that folder; do not assume a fixed list.

## Knowledgebases (register new rows when you add a folder)

| manual_id | Description |
|-----------|-------------|
| `step7-stl-statement-list` | SIMATIC **Statement List (STL) for S7-300/S7-400** programming reference (A5E00068876), chapter/section structure |

## When to use / when not

- **Use `/KB` + this skill** when the user wants **manual-backed** answers: full instruction definition, status word bits, format/operands, or obscure sections from the indexed PDF-derived corpus.
- **Prefer** [.cursor/skills/awl-language-reference/SKILL.md](../awl-language-reference/SKILL.md) for **quick** EN/DE mnemonic tables, operand prefixes, and short syntax — less context than the full manual.
- **Do not** treat the KB as current Siemens product documentation online; it is a **local extract** (STL manual, edition noted in source).

## `/KB` workflow

1. **Parse the question** — instructions (e.g. `OPN`, `INC`, `A`), topics (“status word”, “nesting open”), or section hints.
2. **Discover manuals** — enumerate `.cursor/knowledgebase/*/`. If the user names STL/S7-300/400 statement list, prefer `step7-stl-statement-list` first; otherwise search **all** roots and label hits by `manual_id`.
3. **Normalize terms (optional)** — read [`aliases.json`](../../../.cursor/knowledgebase/step7-stl-statement-list/indexes/aliases.json) for small synonym expansions (e.g. German/English connectors, RLO/status).
4. **Search** — primary surface: **`indexes/sections.jsonl`** in each manual (one JSON object per line). Use workspace **grep/ripgrep** on that file for mnemonic, title substring, or keywords. Prefer lines where **`title`**, **`mnemonics`**, or **`format_tokens`** match the query over huge generic **`retrieval_terms`** noise.
5. **Read depth** — open the matching section under **`chapters/<chapter_id>/sections/*.md`** for clean prose. Use the sibling **`.json`** for `section_id`, `page_start`/`page_end`, anchors.
6. **Answer** — cite **manual_id**, **section_id**, **title**, and **repo path** to the `.md` you used. If **`text_quality_flags`** appears in JSONL and prose is garbled, prefer the `.md` body.

## Search order (per manual)

1. `indexes/sections.jsonl` (grep → pick best rows)
2. `chapters/.../*.md` (read for answer)
3. If weak hits: `indexes/chapter_section_map.json` for TOC ranges, then `pages/pages.jsonl` or `pages/toc.json` for page-oriented questions

## Multiple KBs

When more than one `manual_id` exists: run the same pipeline on each, or the subset the user scoped. Tag every excerpt with its **manual_id**.

## Limitations

- Text may show OCR/extraction artifacts; **`garbled_lines`** flags possible in section metadata.
- Manual scope is **STL reference** for classic S7-300/400 style programming — not TIA Portal-only topics unless they overlap.

## Extra examples

PowerShell-oriented grep patterns: [reference.md](reference.md)
