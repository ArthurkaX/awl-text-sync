# project-knowledgebase — command examples

Paths are from the **repository root**. Use forward slashes.

## PowerShell: search section index

```powershell
Select-String -Path .cursor/knowledgebase/step7-stl-statement-list/indexes/sections.jsonl -Pattern '"OPN"' -SimpleMatch | Select-Object -First 5
```

```powershell
Select-String -Path .cursor/knowledgebase/step7-stl-statement-list/indexes/sections.jsonl -Pattern 'Increment ACCU' | Select-Object -First 3
```

## Narrow with mnemonics in title

```powershell
Select-String -Path .cursor/knowledgebase/step7-stl-statement-list/indexes/sections.jsonl -Pattern '"mnemonics":\s*\["OPN"\]' | Select-Object -First 5
```

After you identify `section_id` and `chapter_id` from the JSON line, open the human-readable file under:

`.cursor/knowledgebase/step7-stl-statement-list/chapters/<chapter_id>/sections/`

Look for filenames containing the section slug (e.g. `opn`).

## Aliases (optional)

```powershell
Get-Content .cursor/knowledgebase/step7-stl-statement-list/indexes/aliases.json
```
