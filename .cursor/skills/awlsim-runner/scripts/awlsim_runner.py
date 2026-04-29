#!/usr/bin/env python3
"""
awlsim_runner.py - Core runner for the awlsim-runner skill.

Compiles AWL/STL source, runs OB1 for N cycles with configurable inputs,
and returns structured JSON results with memory state after each cycle.

Supports type-aware memory access (REAL, INT, DINT, etc.) and optional
assertion checking with pass/fail reporting.

Usage:
    python3 awlsim_runner.py --source "AWL code" [options]
    python3 awlsim_runner.py --source-file path.awl [options]
    python3 awlsim_runner.py --source-files file1.awl file2.awl [options]

Options:
    --cycles N              Number of OB1 cycles (default: 1)
    --set-inputs JSON       Inputs to set before EVERY cycle: {"I0.0": true, "IW2": 1500}
    --set-before-cycle JSON Per-cycle input changes: [{"I0.0": true}, {"I0.0": false}]
    --read JSON             Addresses to read after each cycle (see Read Formats below)
    --read-status-word      Include status word (OV, OS, CC0, CC1, BR) in results
    --cpu-type TYPE         "S7-300" (2 accus, default) or "S7-400" (4 accus)
    --mnemonics LANG        "EN" (default), "DE", or "AUTO"
    --cycle-delay-ms N      Delay between cycles in ms (for timer testing)
    --set-db JSON           Override DB initial values: {"DB1.DBW0": 100, "DB1.DBX0.0": true}
    --expect JSON           Per-cycle expected values for assertion checking
    --tolerance FLOAT       Tolerance for REAL comparisons (default: 1e-6)
    --version               Print version and exit

Read Formats (--read):
    Plain (backward compatible):  ["Q0.0", "MW10", "DB1.DBW0"]
    Typed (for REAL support):     [{"addr": "MD100", "type": "REAL"}, "MW10"]
    Mixed:                        ["Q0.0", {"addr": "MD20", "type": "REAL"}]

Expect Format (--expect):
    {"cycles": [
        {"read": {"Q0.0": true}},
        {"read": {"MW10": 42}},
        {"read": {"MD20": 12.5}}
    ]}

Output: JSON to stdout with compile status, cycle results, memory state,
        and optional assertion results.
"""

import sys
import os
import json
import argparse
import re
import time
import struct
import math
import subprocess
import tempfile
import contextlib
from datetime import datetime
from pathlib import Path

__version__ = "1.2.0"
SCHEMA_VERSION = "2.0"
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import mnemonics as mnemonic_db

_AWLSIM_LOADED = False


def _default_awlsim_dir():
    repo_runtime = SCRIPT_DIR.parents[2] / "awl-sim-repo"
    if (repo_runtime / "awlsim").exists():
        return str(repo_runtime)
    bundled_runtime = SCRIPT_DIR.parents[2] / ".awlsim-runtime"
    if (bundled_runtime / "awlsim").exists():
        return str(bundled_runtime)
    return os.environ.get("AWLSIM_DIR", "")


def _load_awlsim():
    """Import awlsim lazily so CLI help and argument validation do not need AWLSIM_DIR."""
    global _AWLSIM_LOADED
    global AwlSim, AwlParser, make_AwlMemoryObject_fromScalar1
    global make_AwlMemoryObject_fromScalar8, make_AwlMemoryObject_fromScalar16
    global make_AwlMemoryObject_fromScalar32, make_AwlMemoryObject_fromGeneric
    global AwlMemoryObject_asScalar, AwlMemoryObject_asScalar1
    global make_AwlOperator, makeAwlOperatorWidthMask, AwlOperatorTypes
    global make_AwlOffset, AwlSimError, S7CPUConfig, monotonic_time

    if _AWLSIM_LOADED:
        return

    awlsim_dir = os.environ.get("AWLSIM_DIR") or _default_awlsim_dir()
    if awlsim_dir and awlsim_dir not in sys.path:
        sys.path.insert(0, awlsim_dir)

    with contextlib.redirect_stdout(sys.stderr):
        from awlsim.common.util import Logging
        Logging.setLoglevel(Logging.LOG_WARNING)
        from awlsim.core.main import AwlSim
        from awlsim.awlcompiler import (
            AwlParser,
            make_AwlMemoryObject_fromScalar1,
            make_AwlMemoryObject_fromScalar8,
            make_AwlMemoryObject_fromScalar16,
            make_AwlMemoryObject_fromScalar32,
            make_AwlMemoryObject_fromGeneric,
            AwlMemoryObject_asScalar,
            AwlMemoryObject_asScalar1,
        )
        from awlsim.core.operators import make_AwlOperator, makeAwlOperatorWidthMask
        from awlsim.core.operatortypes import AwlOperatorTypes
        from awlsim.core.offset import make_AwlOffset
        from awlsim.common import AwlSimError, S7CPUConfig
        from awlsim.common.monotonic import monotonic_time

    _AWLSIM_LOADED = True


# ============================================================
# REAL / Float Encoding Helpers
# ============================================================

def encode_real(value):
    """Encode a Python float as a 32-bit unsigned integer (IEEE 754 big-endian bits).

    This is what you need to store a REAL value into PLC memory:
    the float 12.5 becomes 0x41480000 (unsigned int 1095237632).
    """
    return struct.unpack(">I", struct.pack(">f", float(value)))[0]


def decode_real(raw):
    """Decode a 32-bit unsigned integer back to a Python float (IEEE 754 big-endian).

    This is what you need to read a REAL value from PLC memory:
    the unsigned int 1095237632 (0x41480000) becomes 12.5.
    """
    return struct.unpack(">f", struct.pack(">I", raw & 0xFFFFFFFF))[0]


# ============================================================
# Type System for Typed Read/Write
# ============================================================

# Known S7 scalar types and their properties
S7_TYPES = {
    "BOOL":   {"width": 1,  "signed": False, "float": False},
    "BYTE":   {"width": 8,  "signed": False, "float": False},
    "WORD":   {"width": 16, "signed": False, "float": False},
    "INT":    {"width": 16, "signed": True,  "float": False},
    "DWORD":  {"width": 32, "signed": False, "float": False},
    "DINT":   {"width": 32, "signed": True,  "float": False},
    "REAL":   {"width": 32, "signed": False, "float": True},
    "TIME":   {"width": 32, "signed": True,  "float": False},
    "S5TIME": {"width": 16, "signed": False, "float": False},
}

# Default type inference from address width (backward-compatible behavior)
DEFAULT_TYPE_BY_WIDTH = {
    1:  "BOOL",
    8:  "BYTE",
    16: "INT",
    32: "DINT",
}

_PERIPHERAL_SPACE_RE = re.compile(r"\b(PEB|PEW|PED|PAB|PAW|PAD)\s+(\d+)\b", re.IGNORECASE)
_PERIPHERAL_COMPACT_RE = re.compile(r"\b(PEB|PEW|PED|PAB|PAW|PAD)(\d+)\b", re.IGNORECASE)
_GERMAN_AREA_RE = re.compile(r"\b(EB|EW|ED|AB|AW|AD|E|A)(\s*\d+(?:\.\d+)?)\b", re.IGNORECASE)


def canonicalize_source_to_english(source):
    """Translate German mnemonic spellings to English STL for awlsim execution."""
    out_lines = []
    area_map = {
        "E": "I", "EB": "IB", "EW": "IW", "ED": "ID",
        "A": "Q", "AB": "QB", "AW": "QW", "AD": "QD",
    }

    for line in source.splitlines():
        code, sep, comment = line.partition("//")

        def periph_space(m):
            token = mnemonic_db.PERIPHERAL_DE_TO_EN.get(m.group(1).upper(), m.group(1).upper())
            return f"{token} {m.group(2)}"

        def periph_compact(m):
            token = mnemonic_db.PERIPHERAL_DE_TO_EN.get(m.group(1).upper(), m.group(1).upper())
            return f"{token}{m.group(2)}"

        code = _PERIPHERAL_SPACE_RE.sub(periph_space, code)
        code = _PERIPHERAL_COMPACT_RE.sub(periph_compact, code)

        leading = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\b(.*)$", code)
        if leading:
            indent, token, rest = leading.groups()
            upper = token.upper()
            translated = mnemonic_db.DE_TO_EN.get(upper, upper)
            code = f"{indent}{translated}{rest}"

        parts = code.strip().split(None, 1)
        if len(parts) == 2:
            instr, operands = parts

            def area_repl(m):
                return area_map.get(m.group(1).upper(), m.group(1).upper()) + m.group(2).replace(" ", "")

            converted = _GERMAN_AREA_RE.sub(area_repl, operands)
            prefix = code[:len(code) - len(code.lstrip())]
            code = f"{prefix}{instr} {converted}"

        out_lines.append(code + (sep + comment if sep else ""))
    return "\n".join(out_lines)


def max_timer_index_in_sources(sources):
    max_timer = -1
    for source in sources or []:
        for match in re.finditer(r"\bT\s*(\d+)\b", source, re.IGNORECASE):
            max_timer = max(max_timer, int(match.group(1)))
    return max_timer


def infer_type_from_address(addr_str):
    """Infer a default S7 type from the address format.

    This provides backward-compatible behavior: plain string addresses
    are read as signed integers (INT/DINT), not REAL.
    """
    addr_str = addr_str.strip().upper()
    _, _, _, width, _ = parse_address(addr_str)
    return DEFAULT_TYPE_BY_WIDTH.get(width, "BYTE")


def parse_read_argument(value):
    """Parse --read/--read-typed values.

    Accepts JSON arrays/objects plus comma shorthand:
        MD200:REAL,Q4.0:BOOL
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    text = str(value).strip()
    if not text:
        return []
    if text[0] in "[{":
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else [parsed]
    specs = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            addr, dtype = item.split(":", 1)
            specs.append({"addr": addr.strip(), "type": dtype.strip().upper()})
        else:
            specs.append(item)
    return specs


def parse_typed_write_argument(value):
    if value is None:
        return []
    parsed = json.loads(value)
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise ValueError("typed write JSON must be an object or array")
    return parsed


def normalize_read_spec(read_item):
    """Normalize a read spec into {"addr": str, "type": str}.

    Accepts either:
        "MW10"                            -> {"addr": "MW10", "type": "INT"}
        {"addr": "MD100", "type": "REAL"} -> as-is
    """
    if isinstance(read_item, str):
        return {"addr": read_item, "type": infer_type_from_address(read_item)}
    elif isinstance(read_item, dict):
        addr = read_item.get("addr", "")
        dtype = read_item.get("type", infer_type_from_address(addr)).upper()
        return {"addr": addr, "type": dtype}
    else:
        raise ValueError(f"Invalid read spec: {read_item}")


def normalize_typed_write_specs(items):
    """Normalize --set-db-typed entries into (addr, type, value) tuples."""
    typed = []
    for item in items or []:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid typed write spec: {item}")
        addr = item.get("addr")
        dtype = item.get("type")
        if not addr or not dtype or "value" not in item:
            raise ValueError(f"Typed write requires addr, type, and value: {item}")
        typed.append((addr, dtype.upper(), item["value"]))
    return typed


def _audit_log(event, detail):
    audit_dir = Path.home() / ".awl"
    audit_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "tool": "awlsim_runner",
        "event": event,
        "detail": detail,
    }
    with (audit_dir / "precheck_audit.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def run_precheck_for_file(source_file, mnemonics="AUTO"):
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "stl_precheck.py"),
        "--source-file",
        str(source_file),
        "--mnemonics",
        mnemonics,
        "--strict",
        "--format",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {
            "schema_version": "1.0",
            "file": str(source_file),
            "mnemonics": "UNKNOWN",
            "fails": [],
            "warns": [],
            "infos": [],
            "summary": {"fail_count": 0, "warn_count": 0, "info_count": 0},
            "error": proc.stderr.strip() or proc.stdout.strip(),
        }
    return proc.returncode, payload


def run_precheck_for_sources(source_paths, source_texts, mnemonics="AUTO"):
    """Run stl_precheck.py on every source and return a combined summary."""
    temp_paths = []
    paths = list(source_paths or [])
    try:
        if not paths:
            for text in source_texts:
                fd, name = tempfile.mkstemp(suffix=".awl", text=True)
                with os.fdopen(fd, "w", encoding="cp1252", errors="replace") as f:
                    f.write(text)
                temp_paths.append(Path(name))
            paths = temp_paths

        checks = []
        worst_rc = 0
        for path in paths:
            rc, payload = run_precheck_for_file(path, mnemonics=mnemonics)
            checks.append(payload)
            worst_rc = max(worst_rc, rc)

        if len(checks) == 1:
            return worst_rc, checks[0]

        return worst_rc, {
            "schema_version": "1.0",
            "files": checks,
            "mnemonics": "MULTI",
            "summary": {
                "fail_count": sum(c.get("summary", {}).get("fail_count", 0) for c in checks),
                "warn_count": sum(c.get("summary", {}).get("warn_count", 0) for c in checks),
                "info_count": sum(c.get("summary", {}).get("info_count", 0) for c in checks),
            },
        }
    finally:
        for path in temp_paths:
            try:
                path.unlink()
            except OSError:
                pass


# ============================================================
# Address Parser
# ============================================================

# Regex patterns for S7 memory addresses
ADDR_PATTERNS = [
    # DB bit:   DB1.DBX0.0
    (r'^DB(\d+)\.DBX\s*(\d+)\.(\d+)$', 'db_bit'),
    # DB byte:  DB1.DBB0
    (r'^DB(\d+)\.DBB\s*(\d+)$', 'db_byte'),
    # DB word:  DB1.DBW0
    (r'^DB(\d+)\.DBW\s*(\d+)$', 'db_word'),
    # DB dword: DB1.DBD0
    (r'^DB(\d+)\.DBD\s*(\d+)$', 'db_dword'),
    # Input bit:  I0.0 or E0.0
    (r'^[IE]\s*(\d+)\.(\d+)$', 'input_bit'),
    # Input byte: IB0 or EB0
    (r'^[IE]B\s*(\d+)$', 'input_byte'),
    # Input word: IW0 or EW0
    (r'^[IE]W\s*(\d+)$', 'input_word'),
    # Input dword: ID0 or ED0
    (r'^[IE]D\s*(\d+)$', 'input_dword'),
    # Output bit:  Q0.0 or A0.0
    (r'^[QA]\s*(\d+)\.(\d+)$', 'output_bit'),
    # Output byte: QB0 or AB0
    (r'^[QA]B\s*(\d+)$', 'output_byte'),
    # Output word: QW0 or AW0
    (r'^[QA]W\s*(\d+)$', 'output_word'),
    # Output dword: QD0 or AD0
    (r'^[QA]D\s*(\d+)$', 'output_dword'),
    # Merker bit:  M0.0
    (r'^M\s*(\d+)\.(\d+)$', 'merker_bit'),
    # Merker byte: MB0
    (r'^MB\s*(\d+)$', 'merker_byte'),
    # Merker word: MW0
    (r'^MW\s*(\d+)$', 'merker_word'),
    # Merker dword: MD0
    (r'^MD\s*(\d+)$', 'merker_dword'),
    # Timer: T0
    (r'^T\s*(\d+)$', 'timer'),
    # Counter: C0 or Z0
    (r'^[CZ]\s*(\d+)$', 'counter'),
]

COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), t) for p, t in ADDR_PATTERNS]


def parse_address(addr_str):
    """Parse a user-friendly S7 address string into (mem_type, byte_off, bit_off, width, db_num)."""
    _load_awlsim()
    addr_str = addr_str.strip()
    for pattern, addr_type in COMPILED_PATTERNS:
        m = pattern.match(addr_str)
        if not m:
            continue
        groups = m.groups()

        if addr_type == 'db_bit':
            return (AwlOperatorTypes.MEM_DB, int(groups[1]), int(groups[2]), 1, int(groups[0]))
        elif addr_type == 'db_byte':
            return (AwlOperatorTypes.MEM_DB, int(groups[1]), 0, 8, int(groups[0]))
        elif addr_type == 'db_word':
            return (AwlOperatorTypes.MEM_DB, int(groups[1]), 0, 16, int(groups[0]))
        elif addr_type == 'db_dword':
            return (AwlOperatorTypes.MEM_DB, int(groups[1]), 0, 32, int(groups[0]))
        elif addr_type == 'input_bit':
            return (AwlOperatorTypes.MEM_E, int(groups[0]), int(groups[1]), 1, None)
        elif addr_type == 'input_byte':
            return (AwlOperatorTypes.MEM_E, int(groups[0]), 0, 8, None)
        elif addr_type == 'input_word':
            return (AwlOperatorTypes.MEM_E, int(groups[0]), 0, 16, None)
        elif addr_type == 'input_dword':
            return (AwlOperatorTypes.MEM_E, int(groups[0]), 0, 32, None)
        elif addr_type == 'output_bit':
            return (AwlOperatorTypes.MEM_A, int(groups[0]), int(groups[1]), 1, None)
        elif addr_type == 'output_byte':
            return (AwlOperatorTypes.MEM_A, int(groups[0]), 0, 8, None)
        elif addr_type == 'output_word':
            return (AwlOperatorTypes.MEM_A, int(groups[0]), 0, 16, None)
        elif addr_type == 'output_dword':
            return (AwlOperatorTypes.MEM_A, int(groups[0]), 0, 32, None)
        elif addr_type == 'merker_bit':
            return (AwlOperatorTypes.MEM_M, int(groups[0]), int(groups[1]), 1, None)
        elif addr_type == 'merker_byte':
            return (AwlOperatorTypes.MEM_M, int(groups[0]), 0, 8, None)
        elif addr_type == 'merker_word':
            return (AwlOperatorTypes.MEM_M, int(groups[0]), 0, 16, None)
        elif addr_type == 'merker_dword':
            return (AwlOperatorTypes.MEM_M, int(groups[0]), 0, 32, None)
        elif addr_type == 'timer':
            return (AwlOperatorTypes.MEM_T, int(groups[0]), 0, 16, None)
        elif addr_type == 'counter':
            return (AwlOperatorTypes.MEM_Z, int(groups[0]), 0, 16, None)

    raise ValueError(f"Cannot parse address: '{addr_str}'")


def make_op(mem_type, byte_off, bit_off, width, db_num=None):
    """Create an AwlOperator for the given memory address."""
    _load_awlsim()
    offset = make_AwlOffset(byte_off, bit_off)
    if db_num is not None:
        offset.dbNumber = db_num
    return make_AwlOperator(mem_type, width, offset, None)


# ============================================================
# Type-Aware Store / Fetch
# ============================================================

def store_value(cpu, addr_str, value, dtype=None):
    """Store a value to a memory address with optional type awareness.

    Args:
        cpu: awlsim CPU object
        addr_str: S7 address string (e.g., "MD100", "MW10", "M0.0")
        value: Python value to store
        dtype: optional S7 type string ("REAL", "INT", "DINT", etc.)
               If None, type is inferred from the address width and value type.
    """
    _load_awlsim()
    mem_type, byte_off, bit_off, width, db_num = parse_address(addr_str)
    op = make_op(mem_type, byte_off, bit_off, width, db_num)
    mask = makeAwlOperatorWidthMask(width)

    if width == 1:
        memObj = make_AwlMemoryObject_fromScalar1(1 if value else 0)
    elif width == 8:
        memObj = make_AwlMemoryObject_fromScalar8(int(value) & 0xFF)
    elif width == 16:
        v = int(value)
        if v < 0:
            v = v & 0xFFFF
        memObj = make_AwlMemoryObject_fromScalar16(v)
    elif width == 32:
        # Determine if this is a REAL value
        is_real = False
        if dtype and dtype.upper() == "REAL":
            is_real = True
        elif dtype is None and isinstance(value, float):
            # Auto-detect: if user passed a Python float and no explicit type,
            # treat as REAL. This is a convenience heuristic.
            is_real = True

        if is_real:
            # Encode float as IEEE 754 bits
            v = encode_real(value)
        else:
            v = int(value)
            if v < 0:
                v = v & 0xFFFFFFFF
        memObj = make_AwlMemoryObject_fromScalar32(v)
    else:
        raise ValueError(f"Unsupported width {width} for store to '{addr_str}'")

    cpu.store(op, memObj, mask)


def fetch_value(cpu, addr_str, dtype=None):
    """Fetch a value from a memory address with optional type awareness.

    Args:
        cpu: awlsim CPU object
        addr_str: S7 address string (e.g., "MD100", "MW10", "Q0.0", "T0", "C0")
        dtype: optional S7 type string ("REAL", "INT", "DINT", etc.)
               If None, defaults to backward-compatible signed integer behavior.

    Returns:
        Python bool, int, or float depending on width and dtype.
    """
    _load_awlsim()
    mem_type, byte_off, bit_off, width, db_num = parse_address(addr_str)

    # Special handling for timers and counters — awlsim's cpu.fetch() doesn't
    # work for T/C operands without an instruction context, so we read directly
    # from the timer/counter objects.
    if mem_type == AwlOperatorTypes.MEM_T:
        timer_idx = byte_off
        try:
            timer_obj = cpu.timers[timer_idx]
            return timer_obj.getTimevalBin()
        except (IndexError, AttributeError) as e:
            raise ValueError(f"Cannot read timer T{timer_idx}: {e}")

    if mem_type == AwlOperatorTypes.MEM_Z:
        counter_idx = byte_off
        try:
            counter_obj = cpu.counters[counter_idx]
            return counter_obj.getValueBin()
        except (IndexError, AttributeError) as e:
            raise ValueError(f"Cannot read counter C{counter_idx}: {e}")

    op = make_op(mem_type, byte_off, bit_off, width, db_num)
    mask = makeAwlOperatorWidthMask(width)

    memObj = cpu.fetch(op, mask)

    if width == 1:
        return bool(AwlMemoryObject_asScalar1(memObj))
    else:
        raw = AwlMemoryObject_asScalar(memObj)

        # Type-aware decoding
        if dtype:
            dtype_upper = dtype.upper()
            type_info = S7_TYPES.get(dtype_upper)
            if type_info and type_info["float"]:
                # REAL: decode IEEE 754 bits to float
                return decode_real(raw)
            elif type_info and type_info["signed"]:
                # Signed integer (INT, DINT, TIME)
                if width == 16 and raw > 32767:
                    raw -= 65536
                elif width == 32 and raw > 2147483647:
                    raw -= 4294967296
                return raw
            else:
                # Unsigned (BYTE, WORD, DWORD, S5TIME)
                return raw
        else:
            # Backward-compatible: signed integer interpretation
            if width == 16 and raw > 32767:
                raw -= 65536
            elif width == 32 and raw > 2147483647:
                raw -= 4294967296
            return raw


def read_status_word(cpu):
    """Read the CPU status word bits."""
    stw = cpu.statusWord
    return {
        "OV": stw.OV,
        "OS": stw.OS,
        "CC1": stw.A1,
        "CC0": stw.A0,
        "BR": stw.BIE,
        "OR": stw.OR,
        "STA": stw.STA,
        "RLO": stw.VKE,
        "FC": stw.NER,
    }


# ============================================================
# Assertion Engine
# ============================================================

def check_assertion(addr, expected, actual, dtype, tolerance):
    """Compare an expected value against an actual value, type-aware.

    Returns:
        dict with "addr", "expected", "actual", "pass", and optionally "delta"
    """
    result = {
        "addr": addr,
        "expected": expected,
        "actual": actual,
    }

    # Boolean comparison
    if isinstance(expected, bool) or (dtype and dtype.upper() == "BOOL"):
        result["pass"] = bool(expected) == bool(actual)
        return result

    # Float/REAL comparison with tolerance
    if isinstance(expected, float) or (dtype and dtype.upper() == "REAL"):
        try:
            exp_f = float(expected)
            act_f = float(actual)
            # Handle NaN: NaN != NaN, but if both are NaN, consider it a pass
            if math.isnan(exp_f) and math.isnan(act_f):
                result["pass"] = True
                return result
            delta = abs(exp_f - act_f)
            result["delta"] = delta
            result["pass"] = delta <= tolerance
        except (TypeError, ValueError):
            result["pass"] = False
        return result

    # Integer comparison (exact)
    try:
        result["pass"] = int(expected) == int(actual)
    except (TypeError, ValueError):
        result["pass"] = expected == actual
    return result


def run_assertions(cycle_num, memory_state, expect_cycle, read_specs, tolerance):
    """Run assertions for a single cycle.

    Args:
        cycle_num: 1-based cycle number
        memory_state: dict of addr -> actual value (from this cycle's reads)
        expect_cycle: dict with "read" key containing addr -> expected value
        read_specs: list of normalized read specs (for type lookup)
        tolerance: float tolerance for REAL comparisons

    Returns:
        list of assertion result dicts
    """
    assertions = []
    expected_reads = expect_cycle.get("read", {})

    # Build a type lookup from read specs
    type_lookup = {}
    for spec in read_specs:
        type_lookup[spec["addr"]] = spec["type"]

    for addr, expected_val in expected_reads.items():
        actual_val = memory_state.get(addr)
        if actual_val is not None and isinstance(actual_val, str) and actual_val.startswith("ERROR"):
            assertions.append({
                "cycle": cycle_num,
                "addr": addr,
                "expected": expected_val,
                "actual": actual_val,
                "pass": False,
            })
            continue

        dtype = type_lookup.get(addr)
        assertion = check_assertion(addr, expected_val, actual_val, dtype, tolerance)
        assertion["cycle"] = cycle_num
        assertions.append(assertion)

    return assertions


# ============================================================
# Main Runner
# ============================================================

def run_simulation(sources, cycles=1, set_inputs=None, set_before_cycle=None,
                   read_addrs=None, read_stw=False, cpu_type="S7-300",
                   mnemonics="EN", cycle_delay_ms=0, set_db=None,
                   set_db_typed=None, set_inputs_typed=None,
                   virtual_time_ms_per_cycle=None,
                   expect=None, tolerance=1e-6, precheck=None):
    """
    Compile and run AWL/STL source code in the awlsim simulator.

    Args:
        sources: list of AWL source strings
        cycles: number of OB1 cycles to run
        set_inputs: dict of address->value to set before EVERY cycle
        set_before_cycle: list of dicts, per-cycle input overrides
        read_addrs: list of read specs (strings or {"addr":..,"type":..} dicts)
        read_stw: if True, include status word in results
        cpu_type: "S7-300" or "S7-400"
        mnemonics: "EN", "DE", or "AUTO"
        cycle_delay_ms: delay between cycles in milliseconds
        set_db: dict of DB address->value to set before first cycle
        expect: dict with "cycles" key containing per-cycle expected values
        tolerance: float tolerance for REAL comparisons (default: 1e-6)

    Returns:
        dict with status, compile_messages, results, optional assertions, etc.
    """
    _load_awlsim()
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "success",
        "canonical_mnemonics": "EN",
        "precheck": precheck,
        "compile_messages": [],
        "cycles_executed": 0,
        "results": [],
        "error": None,
        "db_layouts": {},
    }

    # Normalize read specs to typed format
    read_specs = []
    if read_addrs:
        for item in read_addrs:
            read_specs.append(normalize_read_spec(item))

    # If assertions are requested, add assertion tracking
    has_assertions = expect is not None and "cycles" in (expect or {})
    if has_assertions:
        result["assertions"] = []
        result["test_result"] = "pass"  # optimistic; flipped on first failure

    try:
        # ---- Compile ----
        sim = AwlSim()
        cpu = sim.getCPU()

        # Configure mnemonics
        conf = cpu.getConf()
        mnem_map = {
            "EN": S7CPUConfig.MNEMONICS_EN,
            "DE": S7CPUConfig.MNEMONICS_DE,
            "AUTO": S7CPUConfig.MNEMONICS_AUTO,
        }
        conf.setConfiguredMnemonics(mnem_map.get(mnemonics.upper(), S7CPUConfig.MNEMONICS_AUTO))

        # Configure CPU type (accu count)
        specs = cpu.getSpecs()
        if cpu_type == "S7-400":
            specs.setNrAccus(4)
        max_timer = max_timer_index_in_sources(sources)
        if max_timer >= 0 and max_timer >= specs.nrTimers:
            specs.setNrTimers(max_timer + 1)

        # Parse and load all sources
        for i, src in enumerate(sources):
            try:
                parser = AwlParser()
                parser.parseText(src)
                sim.load(parser.getParseTree())
                result["compile_messages"].append(f"Source {i+1}: parsed OK")
            except AwlSimError as e:
                result["status"] = "compile_error"
                result["error"] = str(e).strip()
                result["compile_messages"].append(f"Source {i+1}: PARSE ERROR")
                if has_assertions:
                    result["test_result"] = "error"
                return result

        # Build
        try:
            sim.build()
            result["compile_messages"].append("Build: OK")
        except AwlSimError as e:
            result["status"] = "compile_error"
            result["error"] = str(e).strip()
            result["compile_messages"].append("Build: FAILED")
            if has_assertions:
                result["test_result"] = "error"
            return result

        # Startup
        try:
            sim.startup()
            result["compile_messages"].append("Startup: OK")
        except AwlSimError as e:
            result["status"] = "compile_error"
            result["error"] = str(e).strip()
            result["compile_messages"].append("Startup: FAILED")
            if has_assertions:
                result["test_result"] = "error"
            return result

        cpu = sim.getCPU()

        virtual_raw_time = None
        if virtual_time_ms_per_cycle is not None:
            original_update_timestamp = cpu.updateTimestamp
            virtual_raw_time = [monotonic_time()]

            def update_virtual_timestamp(_getTime=None):
                return original_update_timestamp(lambda: virtual_raw_time[0])

            cpu.updateTimestamp = update_virtual_timestamp

        # ---- Extract DB layouts for reference ----
        try:
            # allDBs() is a method that returns an iterable of DB objects
            all_dbs = cpu.allDBs
            if callable(all_dbs):
                all_dbs = all_dbs()
            for db_obj in all_dbs:
                db_num = db_obj.index
                if db_num == 0:
                    continue
                fields = []
                for field in db_obj.struct.fields:
                    if field.name:
                        fields.append({
                            "name": field.name,
                            "offset": f"{field.offset.byteOffset}.{field.offset.bitOffset}",
                            "type": str(field.dataType) if field.dataType else "BYTE",
                            "bits": field.bitSize,
                        })
                if fields:
                    result["db_layouts"][f"DB{db_num}"] = fields
        except Exception:
            pass  # DB layout extraction is informational, don't fail on it

        # ---- Set DB initial overrides ----
        if set_db:
            for addr, val in set_db.items():
                try:
                    store_value(cpu, addr, val)
                except Exception as e:
                    result["compile_messages"].append(f"Warning: set-db {addr}={val} failed: {e}")

        if set_db_typed:
            for addr, dtype, val in set_db_typed:
                try:
                    store_value(cpu, addr, val, dtype=dtype)
                except Exception as e:
                    result["compile_messages"].append(
                        f"Warning: set-db-typed {addr}:{dtype}={val} failed: {e}"
                    )

        # ---- Build expect lookup for quick access ----
        expect_cycles = []
        if has_assertions:
            expect_cycles = expect.get("cycles", [])

        # ---- Run Cycles ----
        for cycle_num in range(1, cycles + 1):
            cycle_result = {
                "cycle": cycle_num,
                "inputs_set": {},
                "memory_state": {},
            }

            # Set global inputs (applied every cycle)
            if set_inputs:
                for addr, val in set_inputs.items():
                    try:
                        store_value(cpu, addr, val)
                        cycle_result["inputs_set"][addr] = val
                    except Exception as e:
                        cycle_result["inputs_set"][addr] = f"ERROR: {e}"

            if set_inputs_typed:
                for addr, dtype, val in set_inputs_typed:
                    try:
                        store_value(cpu, addr, val, dtype=dtype)
                        cycle_result["inputs_set"][addr] = val
                    except Exception as e:
                        cycle_result["inputs_set"][addr] = f"ERROR: {e}"

            # Set per-cycle overrides
            if set_before_cycle and cycle_num <= len(set_before_cycle):
                per_cycle = set_before_cycle[cycle_num - 1]
                if per_cycle:
                    for addr, val in per_cycle.items():
                        try:
                            store_value(cpu, addr, val)
                            cycle_result["inputs_set"][addr] = val
                        except Exception as e:
                            cycle_result["inputs_set"][addr] = f"ERROR: {e}"

            # Run one OB1 cycle
            try:
                if virtual_raw_time is not None and cycle_num > 1:
                    virtual_raw_time[0] += virtual_time_ms_per_cycle / 1000.0
                sim.runCycle()
            except AwlSimError as e:
                result["status"] = "runtime_error"
                result["error"] = str(e).strip()
                result["cycles_executed"] = cycle_num - 1
                result["results"].append(cycle_result)
                if has_assertions:
                    result["test_result"] = "error"
                return result

            # Read back requested addresses (type-aware)
            if read_specs:
                for spec in read_specs:
                    addr = spec["addr"]
                    dtype = spec["type"]
                    try:
                        cycle_result["memory_state"][addr] = fetch_value(cpu, addr, dtype)
                    except Exception as e:
                        cycle_result["memory_state"][addr] = f"ERROR: {e}"

            # Read status word if requested
            if read_stw:
                cycle_result["status_word"] = read_status_word(cpu)

            # Run assertions for this cycle if expected values exist
            if has_assertions and cycle_num <= len(expect_cycles):
                expect_cycle = expect_cycles[cycle_num - 1]
                if expect_cycle:
                    cycle_assertions = run_assertions(
                        cycle_num, cycle_result["memory_state"],
                        expect_cycle, read_specs, tolerance
                    )
                    result["assertions"].extend(cycle_assertions)
                    # Check for failures
                    for a in cycle_assertions:
                        if not a["pass"]:
                            result["test_result"] = "fail"

            result["results"].append(cycle_result)
            result["cycles_executed"] = cycle_num

            # Delay between cycles (for timer testing)
            if virtual_time_ms_per_cycle is not None:
                result.setdefault("virtual_time", {
                    "ms_per_cycle": virtual_time_ms_per_cycle,
                    "elapsed_ms": 0,
                    "mode": "cpu_timestamp_injection",
                })
                result["virtual_time"]["elapsed_ms"] = (cycle_num - 1) * virtual_time_ms_per_cycle
            elif cycle_delay_ms > 0 and cycle_num < cycles:
                time.sleep(cycle_delay_ms / 1000.0)

        sim.shutdown()

    except AwlSimError as e:
        result["status"] = "error"
        result["error"] = str(e).strip()
        if has_assertions:
            result["test_result"] = "error"
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {str(e)}"
        if has_assertions:
            result["test_result"] = "error"

    return result


# ============================================================
# Table Formatter
# ============================================================

def format_table(result):
    """Format simulation results as a human-readable table."""
    lines = []

    if result["status"] != "success":
        lines.append(f"Status: {result['status']}")
        if result.get("error"):
            lines.append(f"Error: {result['error']}")
        return "\n".join(lines)

    # Collect all input and output addresses across cycles
    input_addrs = []
    output_addrs = []
    for r in result["results"]:
        for addr in r.get("inputs_set", {}):
            if addr not in input_addrs:
                input_addrs.append(addr)
        for addr in r.get("memory_state", {}):
            if addr not in output_addrs:
                output_addrs.append(addr)

    # Build header
    cols = ["Cycle"] + [f">{a}" for a in input_addrs] + [f"{a}" for a in output_addrs]
    has_assertions = "assertions" in result and result["assertions"]
    if has_assertions:
        cols.append("Result")

    # Build assertion lookup: (cycle, addr) -> pass/fail
    assert_lookup = {}
    if has_assertions:
        for a in result["assertions"]:
            assert_lookup[(a["cycle"], a["addr"])] = a["pass"]

    # Build rows
    rows = []
    for r in result["results"]:
        cycle = r["cycle"]
        row = [str(cycle)]
        for addr in input_addrs:
            val = r.get("inputs_set", {}).get(addr, "")
            row.append(_fmt_val(val))
        all_pass = True
        for addr in output_addrs:
            val = r.get("memory_state", {}).get(addr, "")
            row.append(_fmt_val(val))
            if (cycle, addr) in assert_lookup and not assert_lookup[(cycle, addr)]:
                all_pass = False
        if has_assertions:
            # Check if this cycle had any assertions
            cycle_asserts = [a for a in result["assertions"] if a["cycle"] == cycle]
            if cycle_asserts:
                row.append("PASS" if all_pass else "FAIL")
            else:
                row.append("-")
        rows.append(row)

    # Calculate column widths
    widths = [max(len(str(c)), max((len(r[i]) for r in rows), default=0))
              for i, c in enumerate(cols)]

    # Format
    header = " | ".join(str(c).ljust(w) for c, w in zip(cols, widths))
    sep = "-+-".join("-" * w for w in widths)
    lines.append(header)
    lines.append(sep)
    for row in rows:
        lines.append(" | ".join(str(v).ljust(w) for v, w in zip(row, widths)))

    # Summary
    lines.append("")
    lines.append(f"Cycles: {result['cycles_executed']}, Status: {result['status']}")
    if has_assertions:
        passed = sum(1 for a in result["assertions"] if a["pass"])
        total = len(result["assertions"])
        lines.append(f"Assertions: {passed}/{total} passed — {result.get('test_result', 'n/a').upper()}")

    return "\n".join(lines)


def _fmt_val(val):
    """Format a value for table display."""
    if val == "" or val is None:
        return ""
    if isinstance(val, bool):
        return "T" if val else "F"
    if isinstance(val, float):
        if val == int(val) and abs(val) < 1e10:
            return str(int(val)) + ".0"
        return f"{val:.4g}"
    return str(val)


def _flatten_precheck(precheck):
    if not isinstance(precheck, dict):
        return precheck
    flat = dict(precheck)
    if "files" in precheck:
        files = precheck.get("files") or []
        flat["fail_count"] = sum(f.get("summary", {}).get("fail_count", 0) for f in files)
        flat["warn_count"] = sum(f.get("summary", {}).get("warn_count", 0) for f in files)
        flat["info_count"] = sum(f.get("summary", {}).get("info_count", 0) for f in files)
        return flat
    summary = precheck.get("summary", {})
    flat["fail_count"] = summary.get("fail_count", 0)
    flat["warn_count"] = summary.get("warn_count", 0)
    flat["info_count"] = summary.get("info_count", 0)
    return flat


def public_result(result):
    """Return the v2 public JSON contract while keeping legacy fields as aliases."""
    out = dict(result)
    legacy_status = result.get("status")
    out["legacy_status"] = legacy_status
    if legacy_status == "success":
        out["status"] = "fail" if result.get("test_result") == "fail" else "ok"
    elif legacy_status == "precheck_failed":
        out["status"] = "fail"
    else:
        out["status"] = "error"
    out["schema_version"] = SCHEMA_VERSION
    out["canonical_mnemonics"] = "EN"
    out["precheck"] = _flatten_precheck(result.get("precheck"))
    normalized_results = []
    for cycle_result in result.get("results", []):
        item = dict(cycle_result)
        reads = dict(item.get("reads") or item.get("memory_state") or {})
        item["reads"] = reads
        item.setdefault("memory_state", reads)
        normalized_results.append(item)
    out["results"] = normalized_results
    return out


def failure_result(status, precheck, error):
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "canonical_mnemonics": "EN",
        "precheck": _flatten_precheck(precheck),
        "compile_messages": [],
        "cycles_executed": 0,
        "results": [],
        "error": error,
        "db_layouts": {},
    }


# ============================================================
# Test Scenario Runner
# ============================================================

def run_test_scenario(scenario_path, sources):
    """Run a multi-step test scenario from a JSON file.

    Scenario format:
    {
        "name": "Motor starter tests",
        "tests": [
            {
                "name": "Start sequence",
                "cycles": 3,
                "set_before_cycle": [{"I0.0": true}, {}, {}],
                "read": ["Q0.0", "Q0.1"],
                "expect": {"cycles": [
                    {"read": {"Q0.0": true}},
                    {"read": {"Q0.0": true}},
                    {"read": {"Q0.0": true}}
                ]}
            },
            {
                "name": "Stop sequence",
                "cycles": 2,
                ...
            }
        ],
        "options": {
            "cpu_type": "S7-300",
            "tolerance": 0.001
        }
    }

    Returns a summary dict with per-test results.
    """
    with open(scenario_path, "r") as f:
        scenario = json.load(f)

    options = scenario.get("options", {})
    summary = {
        "scenario": scenario.get("name", scenario_path),
        "tests": [],
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
    }

    for test_def in scenario.get("tests", []):
        test_name = test_def.get("name", f"test_{summary['total'] + 1}")
        summary["total"] += 1

        result = run_simulation(
            sources=sources,
            cycles=test_def.get("cycles", 1),
            set_inputs=test_def.get("set_inputs"),
            set_before_cycle=test_def.get("set_before_cycle"),
            read_addrs=test_def.get("read"),
            read_stw=test_def.get("read_status_word", False),
            cpu_type=options.get("cpu_type", "S7-300"),
            mnemonics=options.get("mnemonics", "EN"),
            cycle_delay_ms=test_def.get("cycle_delay_ms", 0),
            set_db=test_def.get("set_db"),
            expect=test_def.get("expect"),
            tolerance=options.get("tolerance", 1e-6),
        )

        test_result = {
            "name": test_name,
            "status": result["status"],
            "test_result": result.get("test_result", "n/a"),
            "cycles_executed": result["cycles_executed"],
            "assertions": result.get("assertions", []),
        }

        if result["status"] != "success":
            test_result["error"] = result.get("error")
            summary["errors"] += 1
        elif result.get("test_result") == "fail":
            summary["failed"] += 1
        elif result.get("test_result") == "pass":
            summary["passed"] += 1
        else:
            # No assertions, just ran successfully
            summary["passed"] += 1

        summary["tests"].append(test_result)

    summary["overall"] = "PASS" if (summary["failed"] == 0 and summary["errors"] == 0) else "FAIL"
    return summary


def public_scenario_result(summary, precheck):
    status = "ok" if summary.get("overall") == "PASS" else "fail"
    if summary.get("errors", 0):
        status = "error"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "canonical_mnemonics": "EN",
        "precheck": _flatten_precheck(precheck),
        "scenario": summary.get("scenario"),
        "total": summary.get("total", 0),
        "passed": summary.get("passed", 0),
        "failed": summary.get("failed", 0),
        "errors": summary.get("errors", 0),
        "overall": summary.get("overall"),
        "tests": summary.get("tests", []),
        "test_result": "pass" if summary.get("overall") == "PASS" else "fail",
        "error": None if summary.get("overall") == "PASS" else "one or more scenario tests failed",
    }


def run_smoke_preflight(precheck):
    """Run the smoke suite once per runner version unless explicitly skipped."""
    if os.environ.get("AWLSIM_RUNNER_SKIP_SMOKE") == "1":
        return None

    audit_dir = Path.home() / ".awl"
    marker = audit_dir / f"awlsim_runner_smoke_{__version__}.ok"
    if marker.exists():
        return None

    cmd = [sys.executable, str(SCRIPT_DIR / "test_wrapper.py"), "--smoke"]
    env = os.environ.copy()
    env["AWLSIM_RUNNER_SKIP_SMOKE"] = "1"
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    if proc.returncode != 0:
        return failure_result(
            "error",
            precheck,
            "awlsim-runner smoke preflight failed:\n"
            + (proc.stdout.strip() or proc.stderr.strip() or f"exit {proc.returncode}"),
        )

    audit_dir.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.utcnow().isoformat(timespec="seconds") + "Z\n", encoding="ascii")
    return None


# ============================================================
# CLI Interface
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="AWL/STL PLC Simulator Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"awlsim_runner {__version__}")

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source", type=str, help="Inline AWL/STL source code or existing .awl path")
    source_group.add_argument("--source-file", type=str, help="Path to .awl source file")
    source_group.add_argument("--source-files", nargs="+", help="Multiple .awl source files")

    parser.add_argument("--cycles", type=int, default=1, help="Number of OB1 cycles (default: 1)")
    parser.add_argument("--set-inputs", type=str, help='JSON: {"I0.0": true, "IW2": 1500}')
    parser.add_argument("--set-inputs-typed", type=str,
                        help='JSON array: [{"addr":"MD100","type":"REAL","value":12.5}]')
    parser.add_argument("--set-before-cycle", type=str, help='JSON array of per-cycle inputs')
    parser.add_argument("--read", type=str,
                        help='JSON specs or comma shorthand: MD200:REAL,Q4.0:BOOL')
    parser.add_argument("--read-typed", type=str,
                        help='JSON typed read spec: [{"addr":"MD200","type":"REAL"}]')
    parser.add_argument("--read-status-word", action="store_true", help="Include status word in results")
    parser.add_argument("--cpu-type", type=str, default="S7-300", choices=["S7-300", "S7-400"])
    parser.add_argument("--mnemonics", type=str, default="AUTO", choices=["EN", "DE", "AUTO"])
    parser.add_argument("--cycle-delay-ms", type=int, default=0, help="Delay between cycles (ms)")
    parser.add_argument("--set-db", type=str, help='JSON: {"DB1.DBW0": 100}')
    parser.add_argument("--set-db-typed", type=str,
                        help='JSON array: [{"addr":"MD100","type":"REAL","value":12.5}]')
    parser.add_argument("--accept-mixed-mnemonics", action="store_true",
                        help="Proceed when precheck reports MIXED_INSTRUCTIONS; logged to precheck_audit.jsonl")
    parser.add_argument("--bypass-precheck", action="store_true",
                        help="Skip mandatory stl_precheck.py Step 0; logged to precheck_audit.jsonl")
    parser.add_argument("--virtual-time-ms-per-cycle", type=int,
                        help="Advance virtual elapsed time per cycle without wall-clock sleeping")
    parser.add_argument("--expect", type=str,
                        help='JSON with per-cycle expected values for assertion checking')
    parser.add_argument("--tolerance", type=float, default=1e-6,
                        help="Tolerance for REAL comparisons (default: 1e-6)")
    parser.add_argument("--format", type=str, default="json", choices=["human", "json", "table"],
                        help="Output format: json (default), table, or human")
    parser.add_argument("--test-scenario", type=str,
                        help="Path to JSON test scenario file (runs multiple test cases)")

    args = parser.parse_args()

    # Collect sources
    sources = []
    source_paths = []
    if args.source:
        source_candidate = Path(args.source)
        if source_candidate.exists():
            source_paths = [source_candidate]
            with source_candidate.open("r") as f:
                sources = [f.read()]
        else:
            sources = [args.source]
    elif args.source_file:
        source_paths = [Path(args.source_file)]
        with open(args.source_file, "r") as f:
            sources = [f.read()]
    elif args.source_files:
        source_paths = [Path(fp) for fp in args.source_files]
        for fp in args.source_files:
            with open(fp, "r") as f:
                sources.append(f.read())

    # Mandatory Step 0 precheck
    if args.bypass_precheck:
        _audit_log("bypass_precheck", {"sources": [str(p) for p in source_paths] or ["<inline>"]})
        precheck = {
            "schema_version": "1.0",
            "status": "bypassed",
            "mnemonics": "UNKNOWN",
            "fails": [],
            "warns": [],
            "infos": [],
            "summary": {"fail_count": 0, "warn_count": 0, "info_count": 0},
        }
    else:
        precheck_rc, precheck = run_precheck_for_sources(
            source_paths=source_paths,
            source_texts=sources,
            mnemonics=args.mnemonics,
        )
        detected = precheck.get("mnemonics")
        if detected == "MIXED_INSTRUCTIONS" and args.accept_mixed_mnemonics:
            _audit_log("accept_mixed_mnemonics", {
                "sources": [str(p) for p in source_paths] or ["<inline>"],
                "mnemonics": detected,
            })
        elif detected == "MIXED_INSTRUCTIONS":
            print(json.dumps(failure_result(
                "fail",
                precheck,
                "MIXED_INSTRUCTIONS detected; use --accept-mixed-mnemonics to proceed",
            ), indent=2))
            sys.exit(1)
        if precheck_rc != 0 and not (detected == "MIXED_INSTRUCTIONS" and args.accept_mixed_mnemonics):
            print(json.dumps(failure_result(
                "fail",
                precheck,
                "stl_precheck.py failed; awlsim was not run",
            ), indent=2))
            sys.exit(1)

    execution_sources = [canonicalize_source_to_english(src) for src in sources]

    smoke_failure = run_smoke_preflight(precheck)
    if smoke_failure:
        print(json.dumps(smoke_failure, indent=2))
        sys.exit(1)

    # Test scenario mode
    if args.test_scenario:
        summary = run_test_scenario(args.test_scenario, execution_sources)
        if args.format in ("table", "human"):
            print(f"Scenario: {summary['scenario']}")
            print(f"{'='*50}")
            for t in summary["tests"]:
                icon = "✓" if t["test_result"] == "pass" else "✗" if t["test_result"] == "fail" else "!"
                print(f"  {icon} {t['name']}: {t['test_result'].upper()}")
                if t.get("error"):
                    print(f"    Error: {t['error']}")
            print(f"{'='*50}")
            print(f"Total: {summary['total']} | Passed: {summary['passed']} | Failed: {summary['failed']} | Errors: {summary['errors']}")
            print(f"Overall: {summary['overall']}")
        else:
            print(json.dumps(public_scenario_result(summary, precheck), indent=2))
        sys.exit(0 if summary["overall"] == "PASS" else 1)

    # Parse JSON arguments
    set_inputs = json.loads(args.set_inputs) if args.set_inputs else None
    set_before_cycle = json.loads(args.set_before_cycle) if args.set_before_cycle else None
    read_addrs = parse_read_argument(args.read) + parse_read_argument(args.read_typed)
    set_db = json.loads(args.set_db) if args.set_db else None
    set_db_typed = normalize_typed_write_specs(json.loads(args.set_db_typed)) if args.set_db_typed else None
    set_inputs_typed = normalize_typed_write_specs(parse_typed_write_argument(args.set_inputs_typed))
    expect = json.loads(args.expect) if args.expect else None

    # Run simulation
    result = run_simulation(
        sources=execution_sources,
        cycles=args.cycles,
        set_inputs=set_inputs,
        set_before_cycle=set_before_cycle,
        read_addrs=read_addrs,
        read_stw=args.read_status_word,
        cpu_type=args.cpu_type,
        mnemonics="EN",
        cycle_delay_ms=args.cycle_delay_ms,
        set_db=set_db,
        set_db_typed=set_db_typed,
        set_inputs_typed=set_inputs_typed,
        virtual_time_ms_per_cycle=args.virtual_time_ms_per_cycle,
        expect=expect,
        tolerance=args.tolerance,
        precheck=precheck,
    )

    # Output
    if args.format in ("table", "human"):
        print(format_table(result))
    else:
        print(json.dumps(public_result(result), indent=2))

    # Exit code: nonzero on simulation error OR assertion failure
    if result["status"] != "success":
        sys.exit(1)
    if result.get("test_result") == "fail":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
