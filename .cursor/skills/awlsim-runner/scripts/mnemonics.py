"""
Bilingual Mnemonics Database for Siemens STEP 7 STL/AWL.

Provides authoritative EN+DE mnemonic mappings used by:
- stl_precheck.py (mnemonic class detection, project-mode validation)
- awl-language-reference inlined content
- pattern_diff.py canonical-form normalization

Schema version: 1.0

Coverage:
- 61 instruction mnemonics (English STL ↔ German AWL pairs)
- 6 peripheral I/O operand prefixes (the FB 112 root-cause family — PED↔PID etc.)
- Mode detection: classify a file as EN | DE | MIXED_INSTRUCTIONS | MIXED_COMMENTS_ONLY

References:
- AWL Skills Audit (D1, D2, D3 — FB 112 saga)
- Modular pack instructions-german.md
- Deployed awl-step7_SKILL.md lines 218–226 (peripheral I/O table)
"""

from __future__ import annotations

import re
from typing import Iterable

SCHEMA_VERSION = "1.0"

# --------------------------------------------------------------------------
# 1. Instruction table
# --------------------------------------------------------------------------
# Each entry: (english, german, category)
# When english == german, the mnemonic is bilingually identical.
# Order roughly follows the German→English translation table for ease of audit.

_INSTRUCTION_TABLE: tuple[tuple[str, str, str], ...] = (
    # --- Bit logic ---
    ("A",      "U",      "bit_logic"),
    ("AN",     "UN",     "bit_logic"),
    ("O",      "O",      "bit_logic"),
    ("ON",     "ON",     "bit_logic"),
    ("X",      "X",      "bit_logic"),
    ("XN",     "XN",     "bit_logic"),
    ("A(",     "U(",     "bit_logic"),
    ("AN(",    "UN(",    "bit_logic"),
    ("O(",     "O(",     "bit_logic"),
    ("ON(",    "ON(",    "bit_logic"),
    (")",      ")",      "bit_logic"),
    ("=",      "=",      "bit_logic"),
    ("S",      "S",      "bit_logic"),
    ("R",      "R",      "bit_logic"),
    ("NOT",    "NOT",    "bit_logic"),
    ("SET",    "SET",    "bit_logic"),
    ("CLR",    "CLR",    "bit_logic"),
    ("SAVE",   "SAVE",   "bit_logic"),
    ("FP",     "FP",     "bit_logic"),
    ("FN",     "FN",     "bit_logic"),

    # --- Load / Transfer ---
    ("L",      "L",      "load_transfer"),
    ("T",      "T",      "load_transfer"),

    # --- Accumulator ---
    ("TAK",    "TAK",    "accumulator"),
    ("PUSH",   "PUSH",   "accumulator"),
    ("POP",    "POP",    "accumulator"),
    ("ENT",    "ENT",    "accumulator"),
    ("LEAVE",  "LEAVE",  "accumulator"),

    # --- Integer math ---
    ("+I",     "+I",     "math_int"),
    ("-I",     "-I",     "math_int"),
    ("*I",     "*I",     "math_int"),
    ("/I",     "/I",     "math_int"),
    ("+D",     "+D",     "math_dint"),
    ("-D",     "-D",     "math_dint"),
    ("*D",     "*D",     "math_dint"),
    ("/D",     "/D",     "math_dint"),
    ("MOD",    "MOD",    "math_dint"),

    # --- Real math ---
    ("+R",     "+R",     "math_real"),
    ("-R",     "-R",     "math_real"),
    ("*R",     "*R",     "math_real"),
    ("/R",     "/R",     "math_real"),
    ("ABS",    "ABS",    "math_real"),
    ("SQR",    "SQR",    "math_real"),
    ("SQRT",   "SQRT",   "math_real"),

    # --- Compare ---
    ("==I",    "==I",    "compare"),
    ("<>I",    "<>I",    "compare"),
    (">I",     ">I",     "compare"),
    ("<I",     "<I",     "compare"),
    (">=I",    ">=I",    "compare"),
    ("<=I",    "<=I",    "compare"),
    ("==D",    "==D",    "compare"),
    ("==R",    "==R",    "compare"),
    (">R",     ">R",     "compare"),
    ("<R",     "<R",     "compare"),
    (">=R",    ">=R",    "compare"),
    ("<=R",    "<=R",    "compare"),

    # --- Convert ---
    ("ITD",    "ITD",    "convert"),
    ("DTR",    "DTR",    "convert"),
    ("RND",    "RND",    "convert"),
    ("TRUNC",  "TRUNC",  "convert"),

    # --- Control ---
    ("BEU",    "BEA",    "control"),
    ("BEC",    "BEB",    "control"),
    ("BE",     "BE",     "control"),

    # --- Jumps ---
    ("JU",     "SPA",    "jump"),
    ("JC",     "SPB",    "jump"),
    ("JCN",    "SPBN",   "jump"),
    ("JCB",    "SPBB",   "jump"),
    ("JNB",    "SPBNB",  "jump"),
    ("JBI",    "SPBI",   "jump"),
    ("JNBI",   "SPNBI",  "jump"),
    ("JO",     "SPO",    "jump"),
    ("JOS",    "SPOS",   "jump"),
    ("JZ",     "SPZ",    "jump"),
    ("JN",     "SPN",    "jump"),
    ("JP",     "SPP",    "jump"),
    ("JM",     "SPM",    "jump"),
    ("JPZ",    "SPPZ",   "jump"),
    ("JMZ",    "SPMZ",   "jump"),
    ("JUO",    "SPUO",   "jump"),
    ("JL",     "SPL",    "jump"),
    ("LOOP",   "LOOP",   "jump"),

    # --- Timers (CRITICAL: real translation traps) ---
    # German SI = English SP (Pulse)
    # German SV = English SE (Extended Pulse) — NOT what English-only readers expect
    # German SE = English SD (On-Delay)        — NOT what English-only readers expect
    # German SA = English SF (Off-Delay)
    # German SS = English SS (Retentive On-Delay) — same in both
    ("SP",     "SI",     "timer"),
    ("SE",     "SV",     "timer"),
    ("SD",     "SE",     "timer"),
    ("SS",     "SS",     "timer"),
    ("SF",     "SA",     "timer"),

    # --- Counters ---
    ("CU",     "ZV",     "counter"),
    ("CD",     "ZR",     "counter"),

    # --- Data block ---
    ("OPN",    "AUF",    "data_block"),
    ("CDB",    "TDB",    "data_block"),

    # --- Word logic ---
    ("AW",     "UW",     "word_logic"),
    ("OW",     "OW",     "word_logic"),
    ("XOW",    "XOW",    "word_logic"),
    ("AD",     "UD",     "word_logic"),
    ("OD",     "OD",     "word_logic"),
    ("XOD",    "XOD",    "word_logic"),

    # --- Shift / Rotate ---
    ("SLW",    "SLW",    "shift"),
    ("SRW",    "SRW",    "shift"),
    ("SLD",    "SLD",    "shift"),
    ("SRD",    "SRD",    "shift"),
    ("SSI",    "SSI",    "shift"),
    ("SSD",    "SSD",    "shift"),
    ("RLD",    "RLD",    "rotate"),
    ("RRD",    "RRD",    "rotate"),

    # --- Block call ---
    ("CALL",   "CALL",   "block_call"),
    ("UC",     "UC",     "block_call"),
    ("CC",     "CC",     "block_call"),

    # --- Misc ---
    ("NOP",    "NOP",    "misc"),
    ("BLD",    "BLD",    "misc"),
)


# --------------------------------------------------------------------------
# 2. Peripheral I/O operand prefixes (FB 112 root-cause family)
# --------------------------------------------------------------------------
# These are OPERAND prefixes (used as `L PID 1628`), not standalone instructions.
# They are bilingually distinct, and the wrong choice silently compiles in
# awlsim while SIMATIC Manager rejects it. This is the D1/D2 saga.
#
# Rule: For a 32-bit peripheral input, EN uses "PID", DE uses "PED".
# Address spacing is irrelevant — both `L PID 1628` and `L PID1628` compile.

_PERIPHERAL_TABLE: tuple[tuple[str, str, str, str], ...] = (
    # (english, german, direction, width)
    ("PIB",  "PEB",  "input",  "byte"),
    ("PIW",  "PEW",  "input",  "word"),
    ("PID",  "PED",  "input",  "dword"),
    ("PQB",  "PAB",  "output", "byte"),
    ("PQW",  "PAW",  "output", "word"),
    ("PQD",  "PAD",  "output", "dword"),
)


# --------------------------------------------------------------------------
# 3. Derived lookup structures
# --------------------------------------------------------------------------

# Mnemonics that exist ONLY in English (DE form differs)
EN_ONLY_INSTRUCTIONS = frozenset(en for en, de, _ in _INSTRUCTION_TABLE if en != de)
DE_ONLY_INSTRUCTIONS = frozenset(de for en, de, _ in _INSTRUCTION_TABLE if en != de)

# Mnemonics identical in both languages
BILINGUAL_INSTRUCTIONS = frozenset(en for en, de, _ in _INSTRUCTION_TABLE if en == de)

# All known instructions (union)
ALL_INSTRUCTIONS = EN_ONLY_INSTRUCTIONS | DE_ONLY_INSTRUCTIONS | BILINGUAL_INSTRUCTIONS

# Translation maps (only for bilingually-distinct entries)
EN_TO_DE: dict[str, str] = {en: de for en, de, _ in _INSTRUCTION_TABLE if en != de}
DE_TO_EN: dict[str, str] = {de: en for en, de, _ in _INSTRUCTION_TABLE if en != de}

# Categorization (for explanation in precheck output)
INSTRUCTION_CATEGORY: dict[str, str] = {}
for _en, _de, _cat in _INSTRUCTION_TABLE:
    INSTRUCTION_CATEGORY[_en] = _cat
    INSTRUCTION_CATEGORY[_de] = _cat

# Peripheral I/O lookup
PERIPHERAL_EN: frozenset[str] = frozenset(en for en, _, _, _ in _PERIPHERAL_TABLE)
PERIPHERAL_DE: frozenset[str] = frozenset(de for _, de, _, _ in _PERIPHERAL_TABLE)
PERIPHERAL_EN_TO_DE: dict[str, str] = {en: de for en, de, _, _ in _PERIPHERAL_TABLE}
PERIPHERAL_DE_TO_EN: dict[str, str] = {de: en for en, de, _, _ in _PERIPHERAL_TABLE}

# Combined "EN-only" and "DE-only" tokens (instructions + peripheral prefixes)
EN_ONLY_TOKENS: frozenset[str] = EN_ONLY_INSTRUCTIONS | PERIPHERAL_EN
DE_ONLY_TOKENS: frozenset[str] = DE_ONLY_INSTRUCTIONS | PERIPHERAL_DE


# --------------------------------------------------------------------------
# 4. Token classification
# --------------------------------------------------------------------------

def classify_token(token: str) -> str:
    """
    Classify a single token.

    Returns one of:
      "en_only"     — token is English-only (e.g., "A", "JU", "PID", "SD")
      "de_only"     — token is German-only  (e.g., "U", "SPA", "PED", "SE" as on-delay)
      "bilingual"   — token spelling is identical in EN and DE (e.g., "L", "T", "S5T")
      "unknown"     — not a recognized instruction or peripheral prefix
    """
    if token in EN_ONLY_TOKENS and token in DE_ONLY_TOKENS:
        # Some tokens (e.g., "SE", "SS") appear in both EN-only and DE-only
        # tables with DIFFERENT meanings. These are ambiguous-on-spelling.
        # Caller must consider context. We mark them as "ambiguous".
        return "ambiguous"
    if token in EN_ONLY_TOKENS:
        return "en_only"
    if token in DE_ONLY_TOKENS:
        return "de_only"
    if token in BILINGUAL_INSTRUCTIONS:
        return "bilingual"
    return "unknown"


# --------------------------------------------------------------------------
# 5. File mode detection
# --------------------------------------------------------------------------

# Regex for extracting candidate mnemonics from an instruction line.
# AWL instruction lines start with whitespace; we extract the FIRST
# non-whitespace token after stripping line comments.
_LINE_COMMENT_RE = re.compile(r"//.*$")
_TOKEN_RE = re.compile(r"^\s*([A-Za-z=<>+\-*/()][A-Za-z0-9=<>+\-*/()_]*)")
_PERIPHERAL_TOKEN_RE = re.compile(r"\b(PIB|PIW|PID|PQB|PQW|PQD|PEB|PEW|PED|PAB|PAW|PAD)\b")

# Lines that are NOT instruction lines (declarations, control structure)
_NON_INSTRUCTION_PREFIXES = (
    "FUNCTION_BLOCK", "FUNCTION", "DATA_BLOCK", "ORGANIZATION_BLOCK", "TYPE",
    "END_FUNCTION_BLOCK", "END_FUNCTION", "END_DATA_BLOCK", "END_ORGANIZATION_BLOCK", "END_TYPE",
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_TEMP", "END_VAR",
    "STRUCT", "END_STRUCT",
    "BEGIN", "TITLE", "VERSION", "AUTHOR", "NAME", "NETWORK",
    "//", "(*",
)

# German diacritics — strong signal of German-language content
_GERMAN_DIACRITICS_RE = re.compile(r"[äöüÄÖÜß]")


def _is_instruction_line(stripped_line: str) -> bool:
    """True if the line appears to contain an STL instruction."""
    if not stripped_line:
        return False
    for prefix in _NON_INSTRUCTION_PREFIXES:
        if stripped_line.startswith(prefix):
            return False
    # Block declaration / structure keywords already filtered.
    # Lines like `_001: NOP 0;` start with a label — strip and re-check.
    if ":" in stripped_line.split(maxsplit=1)[0]:
        # Likely "_001: NOP 0;" — pass through to mnemonic extraction.
        pass
    return True


def _extract_mnemonics(line: str) -> list[str]:
    """
    Extract candidate mnemonic tokens from a single line.

    Returns a list because instruction lines may contain a peripheral prefix
    AS AN OPERAND in addition to the leading instruction.

    Example: "      L     PED 1628;" → ["L", "PED"]
    """
    # Strip trailing line comment
    code_part = _LINE_COMMENT_RE.sub("", line).rstrip(";").strip()
    if not code_part:
        return []

    tokens: list[str] = []

    # Strip a label prefix like "_001:" or "Skip:"
    if ":" in code_part:
        head, _, rest = code_part.partition(":")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,15}", head.strip()):
            code_part = rest.strip()

    # First token = candidate instruction
    m = _TOKEN_RE.match(code_part)
    if m:
        tokens.append(m.group(1))

    # Plus any peripheral I/O tokens anywhere in the operand
    for pm in _PERIPHERAL_TOKEN_RE.finditer(code_part):
        tokens.append(pm.group(1))

    return tokens


def detect_file_mode(content: str) -> dict:
    """
    Classify the mnemonic mode of an AWL/STL source file.

    Returns a dict:
      {
        "mode":              "EN" | "DE" | "MIXED_INSTRUCTIONS" | "MIXED_COMMENTS_ONLY",
        "en_only_tokens":    [(line_no, token), ...],   # EN-only tokens found
        "de_only_tokens":    [(line_no, token), ...],   # DE-only tokens found
        "bilingual_tokens":  count,                     # informational
        "unknown_tokens":    [(line_no, token), ...],   # may indicate parse error
        "comment_german":    bool,                      # diacritics found in any comment
        "schema_version":    "1.0",
      }

    Mode semantics:
      EN                    — only EN-compatible tokens (en_only or bilingual)
      DE                    — only DE-compatible tokens (de_only or bilingual)
      MIXED_INSTRUCTIONS    — both en_only AND de_only tokens present in the same file (HARD WARN)
      MIXED_COMMENTS_ONLY   — instructions are unanimously one language, but comments
                              contain German diacritics in an EN file (informational only)
    """
    en_only: list[tuple[int, str]] = []
    de_only: list[tuple[int, str]] = []
    bilingual_count = 0
    unknown: list[tuple[int, str]] = []
    comment_german = False

    for lineno, raw in enumerate(content.splitlines(), start=1):
        # Track diacritics in comment portion of the line
        comment_match = re.search(r"//(.*)$", raw)
        if comment_match and _GERMAN_DIACRITICS_RE.search(comment_match.group(1)):
            comment_german = True

        stripped = raw.strip()
        if not _is_instruction_line(stripped):
            continue

        for tok in _extract_mnemonics(raw):
            cls = classify_token(tok)
            if cls == "en_only":
                en_only.append((lineno, tok))
            elif cls == "de_only":
                de_only.append((lineno, tok))
            elif cls == "bilingual":
                bilingual_count += 1
            elif cls == "ambiguous":
                # Spelling appears in both EN and DE tables with different meanings.
                # Don't classify; treat as bilingual for mode-detection purposes.
                bilingual_count += 1
            else:
                unknown.append((lineno, tok))

    has_en = bool(en_only)
    has_de = bool(de_only)

    if has_en and has_de:
        mode = "MIXED_INSTRUCTIONS"
    elif has_de and not has_en:
        mode = "DE"
    elif has_en and not has_de:
        # Pure EN. Check if comments are German.
        mode = "MIXED_COMMENTS_ONLY" if comment_german else "EN"
    else:
        # No disambiguating mnemonics found — file uses only bilingual tokens.
        # Default to EN; comments may still flag as MIXED_COMMENTS_ONLY.
        mode = "MIXED_COMMENTS_ONLY" if comment_german else "EN"

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "en_only_tokens": en_only,
        "de_only_tokens": de_only,
        "bilingual_tokens": bilingual_count,
        "unknown_tokens": unknown,
        "comment_german": comment_german,
    }


# --------------------------------------------------------------------------
# 6. Self-check (run as `python mnemonics.py --selftest`)
# --------------------------------------------------------------------------

def _selftest() -> int:
    """Verify table integrity. Returns 0 on success, 1 on failure."""
    errors: list[str] = []

    # 1. No duplicate EN tokens
    en_tokens = [en for en, _, _ in _INSTRUCTION_TABLE]
    if len(en_tokens) != len(set(en_tokens)):
        dupes = [t for t in en_tokens if en_tokens.count(t) > 1]
        errors.append(f"Duplicate EN tokens: {set(dupes)}")

    # 2. No duplicate DE tokens
    de_tokens = [de for _, de, _ in _INSTRUCTION_TABLE]
    if len(de_tokens) != len(set(de_tokens)):
        dupes = [t for t in de_tokens if de_tokens.count(t) > 1]
        errors.append(f"Duplicate DE tokens: {set(dupes)}")

    # 3. Translation roundtrip for non-bilingual entries
    for en, de in EN_TO_DE.items():
        if DE_TO_EN.get(de) != en:
            errors.append(f"Roundtrip failure: {en} → {de} → {DE_TO_EN.get(de)}")

    # 4. Peripheral I/O exhaustive (6 pairs)
    if len(_PERIPHERAL_TABLE) != 6:
        errors.append(f"Peripheral table size {len(_PERIPHERAL_TABLE)}, expected 6")

    # 5. FB 112 saga regression: PID is EN-only, PED is DE-only
    if "PID" not in PERIPHERAL_EN:
        errors.append("PID missing from PERIPHERAL_EN")
    if "PED" not in PERIPHERAL_DE:
        errors.append("PED missing from PERIPHERAL_DE")
    if classify_token("PID") != "en_only":
        errors.append(f"PID classify_token = {classify_token('PID')}, expected en_only")
    if classify_token("PED") != "de_only":
        errors.append(f"PED classify_token = {classify_token('PED')}, expected de_only")

    # 6. Timer trap regression
    if EN_TO_DE.get("SD") != "SE":
        errors.append(f"Timer trap: EN SD → DE {EN_TO_DE.get('SD')}, expected SE")
    if EN_TO_DE.get("SE") != "SV":
        errors.append(f"Timer trap: EN SE → DE {EN_TO_DE.get('SE')}, expected SV")

    # 7. Sample EN file detection
    en_sample = """
FUNCTION_BLOCK FB 1
BEGIN
NETWORK
TITLE = test
      A     M 0.0;
      AN    M 0.1;
      L     PID 1628;
      JU    _001;
_001: NOP 0;
END_FUNCTION_BLOCK
""".strip()
    result = detect_file_mode(en_sample)
    if result["mode"] != "EN":
        errors.append(f"EN sample detected as {result['mode']}, expected EN")

    # 8. Sample DE file detection
    de_sample = """
FUNCTION_BLOCK FB 1
BEGIN
NETWORK
TITLE = test
      U     M 0.0;
      UN    M 0.1;
      L     PED 1628;
      SPA   _001;
_001: NOP 0;
END_FUNCTION_BLOCK
""".strip()
    result = detect_file_mode(de_sample)
    if result["mode"] != "DE":
        errors.append(f"DE sample detected as {result['mode']}, expected DE")

    # 9. MIXED_INSTRUCTIONS detection (PID + U)
    mixed_sample = """
FUNCTION_BLOCK FB 1
BEGIN
NETWORK
TITLE = test
      U     M 0.0;
      AN    M 0.1;
      L     PID 1628;
END_FUNCTION_BLOCK
""".strip()
    result = detect_file_mode(mixed_sample)
    if result["mode"] != "MIXED_INSTRUCTIONS":
        errors.append(f"Mixed sample detected as {result['mode']}, expected MIXED_INSTRUCTIONS")

    # 10. MIXED_COMMENTS_ONLY (EN instructions + German diacritics in comments)
    en_with_de_comments = """
FUNCTION_BLOCK FB 1
BEGIN
NETWORK
TITLE = test
      A     M 0.0;       // Prüfdruck Hochalarm
      AN    M 0.1;       // Rückmeldung
END_FUNCTION_BLOCK
""".strip()
    result = detect_file_mode(en_with_de_comments)
    if result["mode"] != "MIXED_COMMENTS_ONLY":
        errors.append(f"EN+DE-comments sample detected as {result['mode']}, expected MIXED_COMMENTS_ONLY")

    if errors:
        print("FAIL — mnemonics.py selftest:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK — mnemonics.py selftest passed ({len(_INSTRUCTION_TABLE)} instructions, "
          f"{len(_PERIPHERAL_TABLE)} peripheral pairs)")
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        sys.exit(_selftest())
    print(__doc__)
    print(f"Schema version: {SCHEMA_VERSION}")
    print(f"Instructions: {len(_INSTRUCTION_TABLE)}")
    print(f"Peripheral I/O pairs: {len(_PERIPHERAL_TABLE)}")
    print(f"EN-only tokens: {len(EN_ONLY_TOKENS)}")
    print(f"DE-only tokens: {len(DE_ONLY_TOKENS)}")
    print(f"Bilingual tokens: {len(BILINGUAL_INSTRUCTIONS)}")
