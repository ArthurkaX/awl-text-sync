#!/usr/bin/env python3
"""
stl_precheck.py — Static linter for Siemens STEP 7 STL/AWL source files.

The Tier-1 mechanical guard from the AWL Skills Audit (E1, A2, A3).

Catches what awlsim silently accepts but SIMATIC Manager rejects.
Most prominently: the FB 112 saga's missing semicolons, German↔English mnemonic
mixing, and unreplaced template placeholders.

Schema version: 1.0

Usage:
  python3 stl_precheck.py
    --source-file FB112.AWL
    --mnemonics EN|DE|AUTO          # default AUTO (auto-detect per file)
    --project-mode EN|DE|MIXED      # default MIXED (no enforcement); EN/DE will hard-fail mismatch
    --strict                        # treat WARN as FAIL
    --format human|json             # default human
    --audit-log PATH                # default ~/.awl/precheck_audit.jsonl

Exit codes:
  0 = clean
  1 = at least one FAIL (or WARN under --strict)
  2 = parse error
  3 = file not found
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

# Local import — runs from the same scripts/ directory
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import mnemonics  # noqa: E402

SCHEMA_VERSION = "1.0"


# --------------------------------------------------------------------------
# Finding model
# --------------------------------------------------------------------------

@dataclass
class Finding:
    severity: str  # "FAIL" | "WARN" | "INFO"
    rule: str
    line: int
    msg: str
    snippet: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Source preprocessing
# --------------------------------------------------------------------------

# Lines that mark block boundaries
_BLOCK_OPEN_RE = re.compile(
    r"^\s*(FUNCTION_BLOCK|FUNCTION|DATA_BLOCK|ORGANIZATION_BLOCK|TYPE)\b"
)
_BLOCK_CLOSE_RE = re.compile(
    r"^\s*(END_FUNCTION_BLOCK|END_FUNCTION|END_DATA_BLOCK|END_ORGANIZATION_BLOCK|END_TYPE)\b"
)
_BEGIN_RE = re.compile(r"^\s*BEGIN\b")
_NETWORK_RE = re.compile(r"^\s*NETWORK\b")
_TITLE_RE = re.compile(r"^\s*TITLE\s*=(.*)$")
_LINE_COMMENT_RE = re.compile(r"//.*$")
_PLACEHOLDER_RE = re.compile(r"\[[A-Z][A-Za-z0-9_]*\]")
_LABEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]{0,15}):\s*(.*)$")

# Declaration-section keywords (no semicolon expected on standalone declarations)
_DECL_KEYWORDS = {
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_TEMP",
    "END_VAR", "STRUCT", "END_STRUCT", "BEGIN", "NETWORK",
}

# Block keywords that don't take a semicolon
_BLOCK_KEYWORDS = {
    "FUNCTION_BLOCK", "FUNCTION", "DATA_BLOCK", "ORGANIZATION_BLOCK", "TYPE",
    "END_FUNCTION_BLOCK", "END_FUNCTION", "END_DATA_BLOCK",
    "END_ORGANIZATION_BLOCK", "END_TYPE",
    "TITLE", "VERSION", "AUTHOR", "NAME",
}


def _strip_line_comment(line: str) -> str:
    """Return the line with any // comment removed."""
    return _LINE_COMMENT_RE.sub("", line)


# --------------------------------------------------------------------------
# Encoding detection
# --------------------------------------------------------------------------

def _detect_encoding(raw_bytes: bytes) -> tuple[str, str | None]:
    """
    Return (decoded_text, warning_or_none).

    SIMATIC Manager exports as windows1252. UTF-8 BOM is rejected by SIMATIC.
    """
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        text = raw_bytes[3:].decode("utf-8", errors="replace")
        return text, "utf-8 BOM detected - SIMATIC Manager rejects UTF-8 BOM"
    # Try windows1252 first (SIMATIC native)
    try:
        return raw_bytes.decode("cp1252"), None
    except UnicodeDecodeError:
        pass
    # Fall back to utf-8 lossy
    return raw_bytes.decode("utf-8", errors="replace"), \
        "non-windows1252 encoding - SIMATIC Manager expects cp1252/windows1252"


# --------------------------------------------------------------------------
# Main precheck class
# --------------------------------------------------------------------------

class Precheck:
    def __init__(
        self,
        source_path: Path,
        project_mode: str = "MIXED",
        mnemonics_mode: str = "AUTO",
    ) -> None:
        self.source_path = source_path
        self.project_mode = project_mode  # EN | DE | MIXED
        self.mnemonics_mode = mnemonics_mode  # EN | DE | AUTO
        self.findings: list[Finding] = []
        self.encoding_warning: str | None = None
        self.detected_mode_info: dict | None = None
        self.lines: list[str] = []
        self.text: str = ""

    def emit(self, severity: str, rule: str, line: int, msg: str, snippet: str = "") -> None:
        self.findings.append(Finding(severity, rule, line, msg, snippet.strip()))

    # ---- public entry point ----
    def run(self) -> int:
        if not self.source_path.exists():
            return 3

        try:
            raw = self.source_path.read_bytes()
        except OSError as e:
            print(f"ERROR: cannot read {self.source_path}: {e}", file=sys.stderr)
            return 3

        text, encoding_warning = _detect_encoding(raw)
        self.text = text
        self.lines = text.splitlines()
        self.encoding_warning = encoding_warning

        # Run all checks
        self._check_encoding()
        self._check_mnemonics()
        self._check_semicolons_and_brackets()
        self._check_template_placeholders()
        self._check_titles_and_networks()
        self._check_label_format()
        self._check_indent()
        self._check_block_declaration_form()
        self._check_arithmetic_safety()

        return 0  # caller computes exit code from findings

    # ---- individual checks ----

    def _check_encoding(self) -> None:
        if self.encoding_warning:
            self.emit("WARN", "encoding", 1, self.encoding_warning)

    def _check_mnemonics(self) -> None:
        info = mnemonics.detect_file_mode(self.text)
        self.detected_mode_info = info
        detected = info["mode"]

        # MIXED_INSTRUCTIONS is always WARN with citations
        if detected == "MIXED_INSTRUCTIONS":
            en_lines = ", ".join(
                f"line {ln} ({tok})" for ln, tok in info["en_only_tokens"][:5]
            )
            de_lines = ", ".join(
                f"line {ln} ({tok})" for ln, tok in info["de_only_tokens"][:5]
            )
            self.emit(
                "WARN", "mixed_mnemonics", 0,
                f"file mixes English and German STL mnemonics. "
                f"EN-only tokens: {en_lines}. DE-only tokens: {de_lines}. "
                "Use --accept-mixed-mnemonics on the runner to bypass; "
                "this will be logged to precheck_audit.jsonl.",
            )

        # MIXED_COMMENTS_ONLY is INFO only — normal for PCS7 plants
        if detected == "MIXED_COMMENTS_ONLY":
            self.emit(
                "INFO", "comments_german_in_en_file", 0,
                "instructions are English STL but comments contain German diacritics. "
                "This is normal for PCS7 plants and not an error.",
            )

        # Project-mode enforcement
        pm = self.project_mode
        if pm == "EN" and detected in ("DE", "MIXED_INSTRUCTIONS"):
            self.emit(
                "FAIL", "project_mode_mismatch", 0,
                f"project mode is EN but file detected as {detected}. "
                "Translate German mnemonics to English or change --project-mode.",
            )
        elif pm == "DE" and detected in ("EN", "MIXED_INSTRUCTIONS"):
            self.emit(
                "FAIL", "project_mode_mismatch", 0,
                f"project mode is DE but file detected as {detected}.",
            )

    def _check_semicolons_and_brackets(self) -> None:
        """
        Walk every line inside a BEGIN…END_* block and verify each instruction
        line ends with `;`. Also balance bracket-open `A(`/`O(` etc. with `)`.

        This is the FB 112 D3 root-cause check.
        """
        in_code = False
        in_call_params = False
        bracket_depth = 0
        bracket_open_lines: list[int] = []

        for lineno, raw in enumerate(self.lines, start=1):
            # Track BEGIN…END_* boundary
            if _BEGIN_RE.match(raw):
                in_code = True
                continue
            if _BLOCK_CLOSE_RE.match(raw):
                in_code = False
                # End-of-block: residual bracket depth = unclosed
                if bracket_depth != 0:
                    self.emit(
                        "FAIL", "unmatched_brackets", lineno,
                        f"reached end of block with bracket depth {bracket_depth}; "
                        f"unclosed open(s) at line(s) {bracket_open_lines}",
                    )
                bracket_depth = 0
                bracket_open_lines = []
                continue
            if not in_code:
                continue

            # Skip blank lines, NETWORK, TITLE, declaration keywords
            stripped = raw.strip()
            if not stripped:
                continue
            if _NETWORK_RE.match(raw) or _TITLE_RE.match(raw):
                continue
            if any(stripped.startswith(kw) for kw in _DECL_KEYWORDS):
                continue
            if _LINE_COMMENT_RE.match(stripped):
                continue
            # Skip pure label-only line: "_001:" with nothing after
            label_match = _LABEL_RE.match(stripped)
            if label_match and not label_match.group(2).strip():
                continue

            code = _strip_line_comment(raw).rstrip()
            if not code.strip():
                continue
            compact = code.strip()

            if in_call_params:
                if compact.startswith(")") or compact.endswith(");"):
                    in_call_params = False
                    if not compact.rstrip().endswith(";"):
                        self.emit(
                            "FAIL", "missing_semicolon", lineno,
                            "CALL parameter list missing terminating ;",
                            snippet=compact,
                        )
                continue

            if re.match(r'^\s*CALL\b.*\(\s*$', code, re.IGNORECASE):
                in_call_params = True
                continue

            # Bracket counting (A(, O(, AN(, ON( → +1; ) → -1)
            # We strip strings/comments and then count.
            opens = len(re.findall(r"\b[AO]N?\(", compact)) + compact.count("A(") + compact.count("O(")
            # The above can double-count (e.g. "AN(" matches both `[AO]N?\(` and `A(` substring).
            # Re-do correctly:
            opens = 0
            for token in re.findall(r"[AO]N?\(", compact):
                opens += 1
            closes = compact.count(")")
            # Subtract close-parens that are part of `A(` etc. — there are none, since `A(` has no `)`
            bracket_depth += opens - closes
            if bracket_depth < 0:
                self.emit(
                    "FAIL", "unmatched_brackets", lineno,
                    "close bracket ) without matching open A( / O( / AN( / ON(",
                    snippet=compact,
                )
                bracket_depth = 0
            elif opens > 0:
                bracket_open_lines.append(lineno)

            # Semicolon check
            if not compact.rstrip().endswith(";"):
                self.emit(
                    "FAIL", "missing_semicolon", lineno,
                    "instruction missing terminating ; "
                    "(SIMATIC Manager source compiler requires semicolons; "
                    "awlsim and the online STL editor do not - this is the FB 112 D3 trap)",
                    snippet=compact,
                )

    def _check_template_placeholders(self) -> None:
        for lineno, raw in enumerate(self.lines, start=1):
            for m in _PLACEHOLDER_RE.finditer(raw):
                tok = m.group(0)
                self.emit(
                    "WARN", "unreplaced_placeholder", lineno,
                    f"unreplaced template placeholder {tok} - "
                    "templates ship with [PLACEHOLDER] tokens that must be substituted before compile",
                    snippet=raw.strip(),
                )

    def _check_titles_and_networks(self) -> None:
        """TITLE > 254 chars (SIMATIC truncates silently); empty NETWORK."""
        last_network_line: int | None = None
        last_network_had_code = False

        for lineno, raw in enumerate(self.lines, start=1):
            tm = _TITLE_RE.match(raw)
            if tm and len(tm.group(1)) > 254:
                self.emit(
                    "INFO", "title_too_long", lineno,
                    f"TITLE line is {len(tm.group(1))} chars; SIMATIC truncates at 254",
                )

            if _NETWORK_RE.match(raw):
                if last_network_line is not None and not last_network_had_code:
                    self.emit(
                        "WARN", "empty_network", last_network_line,
                        "NETWORK with TITLE only and no instructions",
                    )
                last_network_line = lineno
                last_network_had_code = False
                continue

            if last_network_line is None:
                continue

            stripped = raw.strip()
            # Skip blank and TITLE lines
            if not stripped or _TITLE_RE.match(raw):
                continue
            # Anything else inside a network counts
            last_network_had_code = True

    def _check_label_format(self) -> None:
        """
        Project conventions accept: `_NNN` hex sequence (4 chars max) and
        named labels like `SKP1`, `Exit`, `TOUT`, `EINT`. Reject longer names.
        """
        for lineno, raw in enumerate(self.lines, start=1):
            stripped = _strip_line_comment(raw).strip()
            m = _LABEL_RE.match(stripped)
            if not m:
                continue
            label = m.group(1)
            # Project rule: max 16 chars but typically ≤ 4
            if len(label) > 16:
                self.emit(
                    "WARN", "label_too_long", lineno,
                    f"label '{label}' is {len(label)} chars; "
                    "project convention prefers ≤ 4 chars (`_NNN` hex sequence) or short names",
                )

    def _check_indent(self) -> None:
        """Project convention: instruction lines indented with 6 spaces."""
        in_code = False
        for lineno, raw in enumerate(self.lines, start=1):
            if _BEGIN_RE.match(raw):
                in_code = True
                continue
            if _BLOCK_CLOSE_RE.match(raw):
                in_code = False
                continue
            if not in_code or not raw.strip():
                continue
            if _NETWORK_RE.match(raw) or _TITLE_RE.match(raw):
                continue
            stripped = raw.strip()
            if any(stripped.startswith(kw) for kw in _DECL_KEYWORDS):
                continue
            label_match = _LABEL_RE.match(stripped)
            if label_match and not label_match.group(2).strip():
                continue
            # Check leading whitespace
            leading_ws = len(raw) - len(raw.lstrip(" "))
            # Skip lines starting with TAB (mixed indent — separately warned would be noise)
            if raw.startswith("\t"):
                continue
            # Allow label-prefixed lines (column 0)
            if _LABEL_RE.match(raw):
                continue
            if leading_ws not in (0, 6):
                self.emit(
                    "INFO", "non_standard_indent", lineno,
                    f"line indented with {leading_ws} spaces; "
                    "project convention is 6 spaces for instruction lines",
                )

    def _check_block_declaration_form(self) -> None:
        """
        INFO: block declaration uses symbolic name without absolute number,
        e.g. `FUNCTION_BLOCK "Motor"` with no `FB n`.
        """
        for lineno, raw in enumerate(self.lines, start=1):
            m = _BLOCK_OPEN_RE.match(raw)
            if not m:
                continue
            kind = m.group(1)
            rest = raw.strip()[len(kind):].strip()
            # Symbolic form: "Name"     vs.   absolute form: FB 100
            if rest.startswith('"'):
                # Symbolic — check it's not paired with absolute-number suffix
                if not re.search(r"\b(FB|FC|DB|OB|UDT)\s*\d+", rest):
                    self.emit(
                        "INFO", "symbolic_no_absolute", lineno,
                        f"{kind} declared with symbolic name only; "
                        "Symbol Table must contain the mapping or compile will fail",
                    )

    def _check_arithmetic_safety(self) -> None:
        """
        WARN: arithmetic op without subsequent `AN OV` overflow check.
        WARN: division (`/R`, `/I`, `/D`) without preceding zero-guard.
        WARN: SAVE without preceding instruction that affects RLO.

        These are heuristic — false positives possible. Severity is WARN
        so they don't block; they prompt review.
        """
        # Walk through code lines in order
        in_code = False
        # Track: when we see arithmetic, look forward N lines for `AN OV`
        # When we see /R, look backward N lines for `==R` / `<>R` / zero-guard
        WINDOW = 8

        # Build list of (lineno, mnemonic, raw) for instruction lines
        inst_list: list[tuple[int, str, str]] = []
        for lineno, raw in enumerate(self.lines, start=1):
            if _BEGIN_RE.match(raw):
                in_code = True
                continue
            if _BLOCK_CLOSE_RE.match(raw):
                in_code = False
                continue
            if not in_code:
                continue
            stripped = _strip_line_comment(raw).strip().rstrip(";").strip()
            if not stripped:
                continue
            if _NETWORK_RE.match(raw) or _TITLE_RE.match(raw):
                continue
            if any(stripped.startswith(kw) for kw in _DECL_KEYWORDS):
                continue
            # Strip label prefix
            label_m = _LABEL_RE.match(stripped)
            if label_m:
                stripped = label_m.group(2).strip()
            if not stripped:
                continue
            # First whitespace-separated token
            parts = stripped.split()
            if not parts:
                continue
            mnem = parts[0]
            inst_list.append((lineno, mnem, stripped))

        ARITH_OPS = {"+R", "-R", "*R", "/R"}
        DIV_OPS = {"/R", "/I", "/D"}
        ZERO_COMPARE = {"==R", "<>R", "==I", "==D"}

        for idx, (lineno, mnem, body) in enumerate(inst_list):
            # Arithmetic without OV check
            if mnem in ARITH_OPS:
                window = inst_list[idx + 1: idx + 1 + WINDOW]
                if not any(w[1] == "AN" and "OV" in w[2] for w in window):
                    self.emit(
                        "WARN", "arithmetic_no_overflow_check", lineno,
                        f"{mnem} not followed (within {WINDOW} lines) by `AN OV; SAVE; CLR; A BR` "
                        "- overflow may go undetected (safety-critical R1)",
                        snippet=body,
                    )

            # Division without zero-guard
            if mnem in DIV_OPS:
                window = inst_list[max(0, idx - WINDOW): idx]
                if not any(w[1] in ZERO_COMPARE for w in window):
                    self.emit(
                        "WARN", "division_no_zero_guard", lineno,
                        f"{mnem} not preceded (within {WINDOW} lines) by `==R 0` zero-guard "
                        "- divide-by-zero will send CPU to STOP (safety-critical R2)",
                        snippet=body,
                    )

            # SAVE without preceding instruction that affects RLO
            if mnem == "SAVE":
                if idx == 0:
                    self.emit(
                        "WARN", "save_no_rlo_setter", lineno,
                        "SAVE at start of code with no preceding RLO-affecting instruction",
                    )

    # ---- output formatting ----

    def to_dict(self) -> dict:
        info = self.detected_mode_info or {}
        encoding = "utf-8-bom" if (self.encoding_warning and "BOM" in self.encoding_warning) \
            else "windows1252"
        return {
            "schema_version": SCHEMA_VERSION,
            "file": str(self.source_path),
            "mnemonics": info.get("mode", "UNKNOWN"),
            "encoding": encoding,
            "fails": [f.to_dict() for f in self.findings if f.severity == "FAIL"],
            "warns": [f.to_dict() for f in self.findings if f.severity == "WARN"],
            "infos": [f.to_dict() for f in self.findings if f.severity == "INFO"],
            "summary": {
                "fail_count": sum(1 for f in self.findings if f.severity == "FAIL"),
                "warn_count": sum(1 for f in self.findings if f.severity == "WARN"),
                "info_count": sum(1 for f in self.findings if f.severity == "INFO"),
            },
        }

    def to_human(self) -> str:
        out: list[str] = []
        d = self.to_dict()
        out.append(f"stl_precheck v{SCHEMA_VERSION}")
        out.append(f"  file:       {d['file']}")
        out.append(f"  mnemonics:  {d['mnemonics']}")
        out.append(f"  encoding:   {d['encoding']}")
        out.append(f"  summary:    {d['summary']['fail_count']} FAIL, "
                   f"{d['summary']['warn_count']} WARN, "
                   f"{d['summary']['info_count']} INFO")
        for label, key in (("FAIL", "fails"), ("WARN", "warns"), ("INFO", "infos")):
            for f in d[key]:
                out.append(f"  [{label}] line {f['line']:>4}: {f['rule']}")
                out.append(f"          {f['msg']}")
                if f.get("snippet"):
                    out.append(f"          > {f['snippet']}")
        return "\n".join(out)


# --------------------------------------------------------------------------
# Audit log
# --------------------------------------------------------------------------

def _append_audit_log(audit_log_path: Path, entry: dict) -> None:
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="stl_precheck — static linter for Siemens STEP 7 STL/AWL"
    )
    parser.add_argument("--source-file", required=False)
    parser.add_argument("--mnemonics", choices=["EN", "DE", "AUTO"], default="AUTO")
    parser.add_argument("--project-mode", choices=["EN", "DE", "MIXED"], default="MIXED")
    parser.add_argument("--strict", action="store_true",
                        help="treat WARN as FAIL")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    parser.add_argument("--audit-log",
                        default=str(Path.home() / ".awl" / "precheck_audit.jsonl"))
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--selftest", action="store_true",
                        help="run internal self-tests; exits 0 on pass")
    args = parser.parse_args(argv)

    if args.version:
        print(f"stl_precheck schema {SCHEMA_VERSION}; mnemonics schema {mnemonics.SCHEMA_VERSION}")
        return 0

    if args.selftest:
        return _run_selftests()

    if not args.source_file:
        parser.error("--source-file required (or use --selftest)")

    pc = Precheck(
        source_path=Path(args.source_file),
        project_mode=args.project_mode,
        mnemonics_mode=args.mnemonics,
    )
    rc = pc.run()
    if rc != 0:
        print(f"ERROR: file not found: {args.source_file}", file=sys.stderr)
        return rc

    output = pc.to_dict()

    # Compute exit code
    exit_code = 0
    if output["summary"]["fail_count"] > 0:
        exit_code = 1
    if args.strict and output["summary"]["warn_count"] > 0:
        exit_code = 1

    # Audit log entry (always)
    _append_audit_log(
        Path(args.audit_log),
        {
            "ts": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "tool": "stl_precheck",
            "schema_version": SCHEMA_VERSION,
            "file": output["file"],
            "mnemonics": output["mnemonics"],
            "summary": output["summary"],
            "exit_code": exit_code,
        },
    )

    # Output
    if args.format == "json":
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(pc.to_human())

    return exit_code


# --------------------------------------------------------------------------
# Self-tests (smoke level — full corpus is in tests/precheck_acceptance.py)
# --------------------------------------------------------------------------

def _run_selftests() -> int:
    """Internal smoke tests. Full acceptance suite is tests/precheck_acceptance.py."""
    import tempfile

    failures: list[str] = []

    def _run(content: str, **kwargs) -> dict:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".awl", delete=False, encoding="cp1252"
        ) as f:
            f.write(content)
            path = f.name
        pc = Precheck(Path(path), **kwargs)
        pc.run()
        return pc.to_dict()

    # Test 1: clean EN file should pass
    clean_en = """
FUNCTION_BLOCK FB 1
TITLE = test
VERSION : 0.1
VAR_TEMP
  Temp_Real : REAL;
END_VAR
BEGIN
NETWORK
TITLE = test net
      A     M 0.0;
      L     PID 1628;
      T     #Temp_Real;
END_FUNCTION_BLOCK
""".strip()
    r = _run(clean_en, project_mode="EN")
    if r["summary"]["fail_count"] != 0:
        failures.append(f"clean EN had {r['summary']['fail_count']} FAILs: {r['fails']}")
    if r["mnemonics"] != "EN":
        failures.append(f"clean EN detected as {r['mnemonics']}")

    # Test 2: missing semicolons (FB 112 D3 reproduction)
    missing_semis = """
FUNCTION_BLOCK FB 112
TITLE = test
BEGIN
NETWORK
TITLE = test net
      A     M 0.0
      L     PID 1628
      T     #x
END_FUNCTION_BLOCK
""".strip()
    r = _run(missing_semis, project_mode="EN")
    semi_fails = [f for f in r["fails"] if f["rule"] == "missing_semicolon"]
    if len(semi_fails) < 3:
        failures.append(f"missing_semis got {len(semi_fails)} FAILs, expected ≥ 3")

    # Test 3: mixed mnemonics (PID + U)
    mixed = """
FUNCTION_BLOCK FB 1
BEGIN
NETWORK
TITLE = test
      U     M 0.0;
      A     M 0.1;
      L     PID 1628;
END_FUNCTION_BLOCK
""".strip()
    r = _run(mixed, project_mode="MIXED")
    mixed_warns = [f for f in r["warns"] if f["rule"] == "mixed_mnemonics"]
    if len(mixed_warns) != 1:
        failures.append(f"mixed sample got {len(mixed_warns)} WARNs, expected 1")
    if r["mnemonics"] != "MIXED_INSTRUCTIONS":
        failures.append(f"mixed detected as {r['mnemonics']}")

    # Test 4: project_mode EN rejects DE file
    de_file = """
FUNCTION_BLOCK FB 1
BEGIN
NETWORK
TITLE = test
      U     M 0.0;
      L     PED 1628;
END_FUNCTION_BLOCK
""".strip()
    r = _run(de_file, project_mode="EN")
    pm_fails = [f for f in r["fails"] if f["rule"] == "project_mode_mismatch"]
    if len(pm_fails) != 1:
        failures.append(f"project_mode EN/DE-file: {len(pm_fails)} FAILs, expected 1")

    # Test 5: unreplaced placeholder
    placeholder = """
FUNCTION_BLOCK "[AREA]_Compressor"
BEGIN
NETWORK
TITLE = test
      A     M 0.0;
END_FUNCTION_BLOCK
""".strip()
    r = _run(placeholder, project_mode="EN")
    ph_warns = [f for f in r["warns"] if f["rule"] == "unreplaced_placeholder"]
    if len(ph_warns) < 1:
        failures.append(f"placeholder got {len(ph_warns)} WARNs, expected ≥ 1")

    # Test 6: UTF-8 BOM detection
    with tempfile.NamedTemporaryFile(suffix=".awl", delete=False) as f:
        f.write(b"\xef\xbb\xbfFUNCTION_BLOCK FB 1\nBEGIN\nEND_FUNCTION_BLOCK\n")
        path = f.name
    pc = Precheck(Path(path), project_mode="EN")
    pc.run()
    r = pc.to_dict()
    bom_warns = [f for f in r["warns"] if f["rule"] == "encoding"]
    if len(bom_warns) != 1:
        failures.append(f"UTF-8 BOM got {len(bom_warns)} WARNs, expected 1")

    # Test 7: division without zero guard
    div = """
FUNCTION_BLOCK FB 1
VAR_TEMP
  Result : REAL;
END_VAR
BEGIN
NETWORK
TITLE = test
      L     #Numerator;
      L     #Denominator;
      /R    ;
      T     #Result;
      AN    OV;
      SAVE  ;
      CLR   ;
END_FUNCTION_BLOCK
""".strip()
    r = _run(div, project_mode="EN")
    dz_warns = [f for f in r["warns"] if f["rule"] == "division_no_zero_guard"]
    if len(dz_warns) != 1:
        failures.append(f"division_no_zero_guard: {len(dz_warns)} WARNs, expected 1")

    # Test 8: arithmetic without overflow check
    no_ov = """
FUNCTION_BLOCK FB 1
VAR_TEMP
  Result : REAL;
END_VAR
BEGIN
NETWORK
TITLE = test
      L     #A;
      L     #B;
      +R    ;
      T     #Result;
END_FUNCTION_BLOCK
""".strip()
    r = _run(no_ov, project_mode="EN")
    ov_warns = [f for f in r["warns"] if f["rule"] == "arithmetic_no_overflow_check"]
    if len(ov_warns) != 1:
        failures.append(f"arithmetic_no_overflow_check: {len(ov_warns)} WARNs, expected 1")

    if failures:
        print("FAIL - stl_precheck.py self-tests:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("OK - stl_precheck.py self-tests passed (8 tests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
