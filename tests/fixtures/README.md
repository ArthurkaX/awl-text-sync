# Demo and plccheck fixtures

| Path | Role |
|------|------|
| [`classic_demo_workspace/`](classic_demo_workspace/) | STEP 7–style **split workspace**: `Exported/*.awl`, `Project/Blocks/*.awl`, `Project/Symbols/*.sdf`. Built from the same **numeric** monolith pattern as `tests/test_parser_and_naming.py` (**synthetic**, non-proprietary). |
| [`plccheck_demo_minimal/`](plccheck_demo_minimal/) | **TIA-oriented** stub: `.plc.json` + `Main.scl` so `plccheck check` has a supported file. **Not** logically paired 1:1 with Classic blocks—used for **D0_smoke** plumbing only. |

**Paired semantic demo (D1–D6):** use your own redacted **real** Classic export plus a **real** TIA/PLC export with `.plc.json`; see [`docs/siemens_plccheck_experiment.md`](../docs/siemens_plccheck_experiment.md).

Run **D0** from repo root:

```powershell
.\scripts\run_siemens_demo_D0.ps1
```
