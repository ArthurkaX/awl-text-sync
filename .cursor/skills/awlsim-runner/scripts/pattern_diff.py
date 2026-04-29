#!/usr/bin/env python3
"""pattern_diff.py - Canonical semantic-ish comparison for STEP 7 AWL/STL.

Schema: canonical_form_v1
Exit codes: 0 identical, 1 semantic difference, 2 parse/input error.
"""

from __future__ import annotations

import argparse
import re
import sys
import json
import subprocess
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import mnemonics

CANONICAL_FORM = "canonical_v1"

_LABEL_DEF_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:")
_JUMP_RE = re.compile(r"\b(JU|JC|JCN|JNB|JBI|JO|JOS|JZ|JN|JP|JM|JPZ|JMZ|JUO)\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_REAL_RE = re.compile(r"\b([+-]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?)\b")
_ADDR_SPACE_RE = re.compile(r"\b(PID|PIW|PIB|PQD|PQW|PQB|PED|PEW|PEB|PAD|PAW|PAB)\s+(\d+)\b")
_ADDR_COMPACT_RE = re.compile(r"\b(PID|PIW|PIB|PQD|PQW|PQB|PED|PEW|PEB|PAD|PAW|PAB)(\d+)\b")
_OPERAND_AREA_RE = re.compile(r"\b(EB|EW|ED|AB|AW|AD|E|A)(\s*\d+(?:\.\d+)?)\b")
_DECL_LABEL_RE = re.compile(r"^\s*(STRUCT|END_STRUCT|VAR|VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR_TEMP|BEGIN|END_VAR)\b", re.IGNORECASE)


def _strip_block_comments(text: str) -> str:
    return re.sub(r"\(\*.*?\*\)", "", text, flags=re.DOTALL)


def _normalize_real(match: re.Match[str]) -> str:
    token = match.group(1)
    try:
        return f"{float(token):.6e}"
    except ValueError:
        return token


def _canonical_token(token: str) -> str:
    upper = token.upper()
    if upper in mnemonics.DE_TO_EN:
        return mnemonics.DE_TO_EN[upper]
    if upper in mnemonics.PERIPHERAL_DE_TO_EN:
        return mnemonics.PERIPHERAL_DE_TO_EN[upper]
    return upper


def _canonical_operand_areas(code: str) -> str:
    parts = code.strip().split(None, 1)
    if len(parts) < 2:
        return code

    def repl(m: re.Match[str]) -> str:
        token = m.group(1).upper()
        suffix = m.group(2).replace(" ", "")
        mapped = {
            "E": "I", "EB": "IB", "EW": "IW", "ED": "ID",
            "A": "Q", "AB": "QB", "AW": "QW", "AD": "QD",
        }.get(token, token)
        return mapped + suffix

    return f"{parts[0]} {_OPERAND_AREA_RE.sub(repl, parts[1])}"


def canonicalize(text: str, include_comments: bool = False) -> str:
    text = _strip_block_comments(text)
    lines = []
    label_map: dict[str, str] = {}
    in_code = False

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue

        comment = ""
        code = line
        if "//" in line:
            code, comment = line.split("//", 1)
            comment = "//" + comment.strip()
        if not include_comments:
            comment = ""

        code = _ADDR_SPACE_RE.sub(lambda m: f"{_canonical_token(m.group(1))}{m.group(2)}", code)
        code = _ADDR_COMPACT_RE.sub(lambda m: f"{_canonical_token(m.group(1))}{m.group(2)}", code)
        code = _REAL_RE.sub(_normalize_real, code)
        code = _canonical_operand_areas(code)
        if code.strip().upper().startswith("TITLE"):
            continue

        def label_repl(m: re.Match[str]) -> str:
            name = m.group(1)
            label_map.setdefault(name, f"_LBL{len(label_map) + 1:03d}")
            return label_map[name] + ":"

        stripped_code = code.strip().upper()
        if stripped_code == "BEGIN":
            in_code = True
        elif stripped_code.startswith("END_"):
            in_code = False

        if in_code and not _DECL_LABEL_RE.match(code):
            code = _LABEL_DEF_RE.sub(label_repl, code)

        def jump_repl(m: re.Match[str]) -> str:
            target = m.group(2)
            label_map.setdefault(target, f"_LBL{len(label_map) + 1:03d}")
            return f"{_canonical_token(m.group(1))} {label_map[target]}"

        code = _JUMP_RE.sub(jump_repl, code)
        parts = code.strip().split(None, 1)
        if parts:
            first = _canonical_token(parts[0])
            code = first if len(parts) == 1 else f"{first} {parts[1].strip()}"
        code = re.sub(r"\s+", " ", code).strip()
        code = code[:-1].rstrip() if code.endswith(";") else code

        if include_comments and comment:
            lines.append(f"      {code} {comment}".rstrip())
        else:
            lines.append(f"      {code}".rstrip())

    return "\n".join(lines) + ("\n" if lines else "")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="cp1252")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def selftest() -> int:
    en = """FUNCTION_BLOCK FB 1
BEGIN
_010: NOP 0;
      L     PID 1628;
      JU    _020;
_020: L     1.0;
END_FUNCTION_BLOCK
"""
    de = """FUNCTION_BLOCK FB 1
BEGIN
abc: NOP 0;
      L     PED1628;
      JU    done;
done: L     1.000000e+000;
END_FUNCTION_BLOCK
"""
    if canonicalize(en) != canonicalize(de):
        print("FAIL - pattern_diff selftest D1/D2 EN/DE canonical mismatch")
        return 1
    if canonicalize(canonicalize(en)) != canonicalize(en):
        print("FAIL - pattern_diff selftest canonicalization is not idempotent")
        return 1
    changed = en.replace("PID 1628", "PID 1632")
    if canonicalize(en) == canonicalize(changed):
        print("FAIL - pattern_diff selftest did not detect changed address")
        return 1
    if canonicalize("BEGIN\n      L PED 1628;\nEND_FUNCTION_BLOCK\n") != canonicalize("BEGIN\n      L PID1628;\nEND_FUNCTION_BLOCK\n"):
        print("FAIL - pattern_diff selftest D1/D2 peripheral normalization mismatch")
        return 1
    if canonicalize("BEGIN\n      A E0.0; // one\nEND_FUNCTION_BLOCK\n") != canonicalize("BEGIN\n      A I0.0; // two\nEND_FUNCTION_BLOCK\n"):
        print("FAIL - pattern_diff selftest operand/comment normalization mismatch")
        return 1
    if canonicalize("STRUCT\n  Valve : BOOL;\nEND_STRUCT\n") != "      STRUCT\n      VALVE : BOOL\n      END_STRUCT\n":
        print("FAIL - pattern_diff selftest declaration label false positive")
        return 1
    with tempfile.NamedTemporaryFile("w", suffix=".awl", delete=False, encoding="cp1252") as f:
        f.write("FUNCTION_BLOCK FB 1\nBEGIN\n      NOP 0\nEND_FUNCTION_BLOCK\n")
        temp_name = f.name
    try:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "stl_precheck.py"), "--source-file", temp_name, "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(proc.stdout)
        if payload.get("summary", {}).get("fail_count", 0) == 0:
            print("FAIL - pattern_diff selftest D3 missing semicolon was not rejected by precheck")
            return 1
    finally:
        Path(temp_name).unlink(missing_ok=True)
    print("OK - pattern_diff.py selftest passed (7 tests)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", type=Path)
    parser.add_argument("--right", type=Path)
    parser.add_argument("--canonical-form", default=CANONICAL_FORM)
    parser.add_argument("--include-comments", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if args.canonical_form != CANONICAL_FORM:
        print(f"Unsupported canonical form: {args.canonical_form}", file=sys.stderr)
        return 2
    if not args.left or not args.right or not args.left.exists() or not args.right.exists():
        print("Both --left and --right must exist", file=sys.stderr)
        return 2
    try:
        left = canonicalize(_read(args.left), include_comments=args.include_comments)
        right = canonicalize(_read(args.right), include_comments=args.include_comments)
    except OSError as e:
        print(str(e), file=sys.stderr)
        return 2
    if left == right:
        print("semantic-identical")
        return 0
    print("semantic-different")
    return 1


if __name__ == "__main__":
    sys.exit(main())
