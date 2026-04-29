#!/usr/bin/env python3
"""detect_block.py - Detect STEP 7 AWL/STL block metadata and runner pipeline.

Output schema_version: 1.0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import mnemonics

SCHEMA_VERSION = "1.0"

BLOCK_RE = re.compile(
    r"^\s*(FUNCTION_BLOCK|FUNCTION|DATA_BLOCK|ORGANIZATION_BLOCK|TYPE)\s+(?:(FB|FC|DB|OB|UDT)\s*)?(\d+)?(?:\s+\"([^\"]+)\")?",
    re.IGNORECASE | re.MULTILINE,
)
EXTERNAL_DB_RE = re.compile(r'"([^"]+)"\s*\.|(?:\bDB\s*\d+\b|\bDB\d+\.DB[XBWD])', re.IGNORECASE)
SFB_RE = re.compile(r":\s*(?:\"(?:TON|TOF|TP)\"|SFB\s+[345])\s*;", re.IGNORECASE)
SFB_NAME_RE = re.compile(r"^\s*(\w+)\s*:\s*(\"(?:TON|TOF|TP)\"|SFB\s+[345])\s*;", re.IGNORECASE | re.MULTILINE)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="cp1252")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def detect(text: str) -> dict:
    block_type = None
    block_number = None
    symbolic = None
    m = BLOCK_RE.search(text)
    if m:
        keyword = m.group(1).upper()
        explicit = (m.group(2) or "").upper()
        number = m.group(3)
        symbolic = m.group(4)
        if keyword == "FUNCTION_BLOCK":
            block_type = "FB"
        elif keyword == "FUNCTION":
            block_type = "FC"
        elif keyword == "DATA_BLOCK":
            block_type = "DB"
        elif keyword == "ORGANIZATION_BLOCK":
            block_type = "OB"
        elif keyword == "TYPE":
            block_type = "UDT"
        if explicit:
            block_type = explicit
        block_number = int(number) if number else None

    sfb_locations = []
    for sm in SFB_NAME_RE.finditer(text):
        sfb_locations.append({"name": sm.group(1), "type": sm.group(2).replace('"', '').upper()})

    external_refs = []
    for dm in EXTERNAL_DB_RE.finditer(text):
        ref = dm.group(1) or dm.group(0).strip()
        if ref.upper().startswith(("FUNCTION_BLOCK", "DATA_BLOCK")):
            continue
        if ref not in external_refs:
            external_refs.append(ref)

    mode = mnemonics.detect_file_mode(text)["mode"]
    pipeline = ["stl_precheck", "detect_block"]
    if external_refs:
        pipeline.append("awl_dependency_mapper")
    if sfb_locations:
        pipeline.append("sfb_rewriter")
    if block_type in ("FB", "FC"):
        pipeline.append("test_harness_generator")
    pipeline.append("awlsim_runner")

    return {
        "schema_version": SCHEMA_VERSION,
        "block_type": block_type,
        "block_number": block_number,
        "block_symbolic_name": symbolic,
        "has_var_in_out": bool(re.search(r"^\s*VAR_IN_OUT\b", text, re.IGNORECASE | re.MULTILINE)),
        "has_sfb_timers": bool(SFB_RE.search(text)),
        "sfb_timer_locations": sfb_locations,
        "has_external_db_refs": bool(external_refs),
        "external_db_refs": external_refs,
        "has_obs": bool(re.search(r"^\s*ORGANIZATION_BLOCK\b", text, re.IGNORECASE | re.MULTILINE)),
        "mnemonic_hint": "MIXED" if mode.startswith("MIXED") else mode,
        "recommended_pipeline": pipeline,
    }


def selftest() -> int:
    fb112 = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "fb112_clean_en.awl"
    d = detect(_read(fb112))
    if d["block_type"] != "FB" or d["has_sfb_timers"]:
        print("FAIL - detect_block FB112 fixture mismatch")
        return 1
    compressor = '''FUNCTION_BLOCK FB 200
VAR
      T_On : "TON";
END_VAR
BEGIN
      CALL "ExternalDB".Valve;
      A     #T_On.Q;
END_FUNCTION_BLOCK
'''
    c = detect(compressor)
    pipeline = c["recommended_pipeline"]
    if c["block_type"] != "FB" or not c["has_sfb_timers"] or "sfb_rewriter" not in pipeline:
        print("FAIL - detect_block SFB timer pipeline mismatch")
        return 1
    if pipeline.index("awl_dependency_mapper") > pipeline.index("sfb_rewriter"):
        print("FAIL - detect_block mapper must precede rewriter")
        return 1
    print("OK - detect_block.py selftest passed (3 tests)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if not args.source or not args.source.exists():
        print("source file required", file=sys.stderr)
        return 2
    print(json.dumps(detect(_read(args.source)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
