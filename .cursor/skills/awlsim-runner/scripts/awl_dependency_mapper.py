#!/usr/bin/env python3
"""
awl_dependency_mapper.py — Map external dependencies in AWL source files.

Parses an AWL source file and produces a structured JSON inventory of all external
dependencies (DB references, I/O symbols, S5 timers, global memory), plus
auto-generates stub DATA_BLOCKs and M-area mappings for simulation.

Usage:
    python3 awl_dependency_mapper.py --source-file myblock.awl [options]

Options:
    --fb-number N       FB number for the rewritten block (default: 1)
    --instance-db N     Instance DB number (default: 100)
    --stub-db-start N   First DB number for stubs (default: 10)
    --m-input-start N   Start of M-area for input symbols (default: 200)
    --m-output-start N  Start of M-area for output symbols (default: 210)
    --m-discrete-start N Start of M-area for discrete signals (default: 220)
    --m-const-start N   Start of M-area for constants like Logic_one (default: 230)
    --timer-start N     Start of timer numbers for symbolic timers (default: 350)

Output: JSON to stdout with complete dependency inventory and stub generation data.
"""

import sys
import os
import re
import json
import argparse
from collections import OrderedDict

__version__ = "1.0.0"
SCHEMA_VERSION = "1.0"
TOOL = "awl_dependency_mapper"

# ─── Symbol classification patterns ───

# I/O symbols: "XX_Y_NNN.N" where the last part after dot is a single digit 0-7
# This catches patterns like "CR_I_388.0", "CR_Q_352.5"
RE_IO_SYMBOL = re.compile(r'^[A-Za-z_]\w*\.\d$')

# Input I/O: contains _I_ in the name
RE_INPUT_IO = re.compile(r'_I_', re.IGNORECASE)

# Output I/O: contains _Q_ in the name
RE_OUTPUT_IO = re.compile(r'_Q_', re.IGNORECASE)

# SFB type declarations (skip these — handled by sfb_rewriter)
SFB_TYPE_NAMES = {'TON', 'TOF', 'TP'}

# Multi-instance sub-field access pattern
RE_SUBFIELD_ACCESS = re.compile(r'#(\w+)\.(Q|IN|ET)')

# S5 timer instructions
S5_TIMER_INSTRUCTIONS = {'SD', 'SE', 'SS', 'SI', 'SV'}

# Absolute S5 timer reference: T nnn
RE_ABS_TIMER = re.compile(r'\bT\s+(\d+)')

# Global memory reference: MD/MW/MB nnn (not inside L nnn.n local bit patterns)
RE_GLOBAL_MEMORY = re.compile(r'\b(M[DWB])\s+(\d+)')

# DB-path reference: "DBName".Field.SubField
# Captures the DB name and the dotted field path, stopping at semicolons/whitespace
RE_DB_PATH = re.compile(r'"([^"]+)"\.([\w.]+)')

# Standalone quoted symbol: "SymbolName" used with an instruction
RE_QUOTED_SYMBOL = re.compile(r'"([^"]+)"')

# Instructions that indicate BOOL usage
BOOL_INSTRUCTIONS = {'A', 'AN', 'O', 'ON', 'S', 'R', 'FP', 'FN'}

# Instructions that indicate the symbol is being assigned/written
WRITE_INSTRUCTIONS = {'=', 'S', 'R', 'T'}

# REAL comparison/arithmetic instructions (appear AFTER the L instruction that loaded the value)
RE_REAL_CONTEXT = re.compile(r'[<>=!]+R\s*;|[+\-*/]R\s*;')

# Block declaration patterns
RE_FB_DECL = re.compile(r'^\s*FUNCTION_BLOCK\s+"([^"]+)"')
RE_FC_DECL = re.compile(r'^\s*FUNCTION\s+"([^"]+)"')
RE_OB_DECL = re.compile(r'^\s*ORGANIZATION_BLOCK\s+OB\s+(\d+)')


def detect_block_info(source_text):
    """Detect block type and name from the source."""
    for line in source_text.split('\n'):
        m = RE_FB_DECL.match(line)
        if m:
            return "FB", m.group(1)
        m = RE_FC_DECL.match(line)
        if m:
            return "FC", m.group(1)
        m = RE_OB_DECL.match(line)
        if m:
            return "OB", f"OB {m.group(1)}"
    return "UNKNOWN", "UNKNOWN"


def extract_code_section(source_text):
    """Extract lines between BEGIN and END_FUNCTION_BLOCK / END_FUNCTION / END_ORGANIZATION_BLOCK."""
    lines = source_text.split('\n')
    in_code = False
    code_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == 'BEGIN':
            in_code = True
            continue
        if stripped in ('END_FUNCTION_BLOCK', 'END_FUNCTION', 'END_ORGANIZATION_BLOCK'):
            break
        if in_code:
            code_lines.append((i + 1, line))  # (line_number, line_text)

    return code_lines


def extract_var_section(source_text):
    """Extract VAR declaration section text (for identifying SFB types to skip)."""
    lines = source_text.split('\n')
    var_lines = []
    in_var = False

    for line in lines:
        stripped = line.strip()
        if stripped in ('VAR', 'VAR_TEMP', 'VAR_INPUT', 'VAR_OUTPUT', 'VAR_IN_OUT'):
            in_var = True
            continue
        if stripped == 'END_VAR':
            in_var = False
            continue
        if stripped == 'BEGIN':
            break
        if in_var:
            var_lines.append(line)

    return '\n'.join(var_lines)


def is_comment_line(line_text):
    """Check if the line is a comment (starts with // after whitespace)."""
    stripped = line_text.strip()
    return stripped.startswith('//')


def strip_inline_comment(line_text):
    """Remove inline comments from a line, being careful not to strip inside quotes."""
    # Find // that's not inside quotes
    in_quote = False
    for i, ch in enumerate(line_text):
        if ch == '"':
            in_quote = not in_quote
        elif ch == '/' and not in_quote and i + 1 < len(line_text) and line_text[i + 1] == '/':
            return line_text[:i]
    return line_text


def get_instruction_before_symbol(line_text, symbol):
    """Extract the instruction keyword that precedes a symbol reference on a line."""
    # Find the symbol position
    idx = line_text.find(f'"{symbol}"')
    if idx < 0:
        # Try DB path form
        idx = line_text.find(f'"{symbol}".')
        if idx < 0:
            return None

    # Look backward for the instruction
    prefix = line_text[:idx].strip()
    # The instruction is the last whitespace-delimited word before the symbol
    parts = prefix.split()
    if parts:
        return parts[-1].rstrip(';').strip()
    return None


def infer_type_from_context(code_lines, symbol, is_db_field=False, field_path=""):
    """Infer the data type of a symbol from its instruction context.

    For DB fields, also checks for REAL comparison/arithmetic on nearby lines.
    """
    contexts = set()

    for line_num, line_text in code_lines:
        if is_comment_line(line_text):
            continue

        clean = strip_inline_comment(line_text)

        # Check if this symbol appears on this line
        if f'"{symbol}"' not in clean:
            continue

        instr = get_instruction_before_symbol(clean, symbol)
        if instr:
            contexts.add(instr)

    # Classify based on instruction context
    bool_ctx = contexts & BOOL_INSTRUCTIONS
    if bool_ctx:
        return "BOOL"

    # For L (load) — check if it's followed by REAL comparison/arithmetic
    if 'L' in contexts and is_db_field:
        # Search for REAL operations near lines that load this DB field
        for line_num, line_text in code_lines:
            if f'"{symbol}"' in line_text or (field_path and field_path in line_text):
                if 'L' in line_text.split('"')[0]:
                    # Check next few lines for REAL operations
                    for ln2, lt2 in code_lines:
                        if ln2 > line_num and ln2 <= line_num + 3:
                            if RE_REAL_CONTEXT.search(lt2):
                                return "REAL"
        return "DINT"  # Default for L/T context without REAL operations

    if 'L' in contexts or 'T' in contexts:
        return "INT"

    return "BOOL"  # Default


def classify_symbol(symbol, line_text, code_lines, var_text):
    """Classify a quoted symbol into its category."""

    # Skip SFB type names (handled by sfb_rewriter)
    if symbol in SFB_TYPE_NAMES:
        return "sfb_type", None

    # Skip if it appears in VAR declarations as a type
    if f': "{symbol}"' in var_text:
        return "sfb_type", None

    # Check if it's part of a DB path on this line
    db_match = RE_DB_PATH.search(line_text)
    if db_match and db_match.group(1) == symbol:
        field_path = db_match.group(2)
        return "db_reference", field_path

    # Check if it's an I/O symbol (has .N suffix where N is 0-7)
    if RE_IO_SYMBOL.match(symbol):
        if RE_INPUT_IO.search(symbol):
            return "io_input", None
        elif RE_OUTPUT_IO.search(symbol):
            return "io_output", None
        else:
            return "io_unknown", None

    # Check if it's used as an S5 timer (SD "name", SE "name", A "name" after SD/SE)
    for ln, lt in code_lines:
        clean = strip_inline_comment(lt).strip()
        for timer_instr in S5_TIMER_INSTRUCTIONS:
            if f'{timer_instr}    "{symbol}"' in clean or f'{timer_instr}  "{symbol}"' in clean:
                return "s5_timer_symbol", None
        # Also check: A "name" where name was previously used with SD/SE
        if f'A     "{symbol}"' in clean or f'AN    "{symbol}"' in clean:
            # Check if this symbol was used with SD/SE elsewhere
            for ln2, lt2 in code_lines:
                c2 = strip_inline_comment(lt2).strip()
                for ti in S5_TIMER_INSTRUCTIONS:
                    if f'{ti}' in c2 and f'"{symbol}"' in c2:
                        return "s5_timer_symbol", None

    # Otherwise it's a discrete signal
    return "discrete", None


def find_absolute_s5_timers(code_lines):
    """Find all absolute S5 timer references (T nnn) in the code."""
    timers = set()
    for line_num, line_text in code_lines:
        if is_comment_line(line_text):
            continue
        clean = strip_inline_comment(line_text)
        # Match T nnn in various contexts: SD T 340, SE T 341, A T 340, AN T 341
        for m in RE_ABS_TIMER.finditer(clean):
            # Make sure it's actually a timer reference (preceded by timer instruction or A/AN/L)
            prefix = clean[:m.start()].strip().split()
            if prefix:
                last_word = prefix[-1]
                if last_word in S5_TIMER_INSTRUCTIONS or last_word in ('A', 'AN', 'O', 'ON', 'L', 'LC', 'R'):
                    timers.add(int(m.group(1)))
    return sorted(timers)


def find_global_memory(code_lines):
    """Find global memory references (MD/MW/MB nnn)."""
    refs = set()
    for line_num, line_text in code_lines:
        if is_comment_line(line_text):
            continue
        clean = strip_inline_comment(line_text)
        for m in RE_GLOBAL_MEMORY.finditer(clean):
            area = m.group(1)
            addr = m.group(2)
            refs.add(f"{area} {addr}")
    return sorted(refs)


def find_subfield_accesses(code_lines):
    """Find all multi-instance SFB sub-field accesses (#Timer.Q etc)."""
    accesses = []
    for line_num, line_text in code_lines:
        if is_comment_line(line_text):
            continue
        for m in RE_SUBFIELD_ACCESS.finditer(line_text):
            accesses.append({
                "timer": m.group(1),
                "field": m.group(2),
                "line": line_num,
            })
    return accesses


def generate_stub_db(db_name, fields, db_number):
    """Generate AWL source for a stub DATA_BLOCK.

    Fields is a list of {"name": ..., "type": ...} dicts.
    Returns the AWL source and a field-to-address mapping.
    """
    # Sanitize field names for AWL (replace dots and spaces with underscores)
    safe_fields = []
    offset = 0
    field_addresses = []

    for f in fields:
        safe_name = re.sub(r'[.\s\-]', '_', f["path"])
        ftype = f["inferred_type"]

        # Align to even byte for WORD/DWORD/REAL
        if ftype in ("REAL", "DINT", "DWORD", "TIME"):
            if offset % 2 != 0:
                offset += 1  # pad to even
            addr = f"DB{db_number}.DBD {offset}"
            awl_type = ftype if ftype != "TIME" else "TIME"
            size = 4
        elif ftype in ("INT", "WORD"):
            if offset % 2 != 0:
                offset += 1
            addr = f"DB{db_number}.DBW {offset}"
            awl_type = ftype
            size = 2
        elif ftype == "BOOL":
            # Pack bools — but for simplicity, give each its own byte
            # with bit 0 addressable
            addr = f"DB{db_number}.DBX {offset}.0"
            awl_type = "BOOL"
            size = 0  # bools share bytes
        else:
            addr = f"DB{db_number}.DBW {offset}"
            awl_type = "INT"
            size = 2

        safe_fields.append({
            "safe_name": safe_name,
            "original_path": f["path"],
            "awl_type": awl_type,
            "stub_address": addr,
        })

        if ftype == "BOOL":
            # Use bit addressing within current byte
            bit = offset % 8 if False else 0  # simplified: 1 bool per byte
            offset += 1
        else:
            offset += size

    # Generate AWL source
    awl_lines = [
        f"DATA_BLOCK DB {db_number}",
        f'TITLE = {db_name}',
        "STRUCT",
    ]
    for sf in safe_fields:
        awl_lines.append(f"  {sf['safe_name']} : {sf['awl_type']};")
    awl_lines.extend([
        "END_STRUCT;",
        "BEGIN",
        "END_DATA_BLOCK",
    ])

    return {
        "db_number": db_number,
        "title": db_name,
        "fields": [
            {
                "name": sf["safe_name"],
                "original_path": sf["original_path"],
                "type": sf["awl_type"],
                "stub_address": sf["stub_address"],
            }
            for sf in safe_fields
        ],
        "awl_source": '\n'.join(awl_lines),
    }


def assign_m_area(symbols, start_byte):
    """Assign M-area addresses to a list of symbol names.

    Returns dict: {symbol: "M byte.bit"}
    """
    mapping = {}
    current_byte = start_byte
    current_bit = 0

    for sym in sorted(symbols):
        mapping[sym] = f"M {current_byte}.{current_bit}"
        current_bit += 1
        if current_bit > 7:
            current_bit = 0
            current_byte += 1

    return mapping


def main():
    parser = argparse.ArgumentParser(
        description="Map external dependencies in AWL source files and generate simulation stubs."
    )
    parser.add_argument("--source-file", required=True,
                        help="Path to the AWL source file")
    parser.add_argument("--fb-number", type=int, default=1,
                        help="FB number for the rewritten block (default: 1)")
    parser.add_argument("--instance-db", type=int, default=100,
                        help="Instance DB number (default: 100)")
    parser.add_argument("--stub-db-start", type=int, default=10,
                        help="First DB number for stub DBs (default: 10)")
    parser.add_argument("--m-input-start", type=int, default=200,
                        help="Start M-byte for input I/O symbols (default: 200)")
    parser.add_argument("--m-output-start", type=int, default=210,
                        help="Start M-byte for output I/O symbols (default: 210)")
    parser.add_argument("--m-discrete-start", type=int, default=220,
                        help="Start M-byte for discrete signals (default: 220)")
    parser.add_argument("--m-const-start", type=int, default=230,
                        help="Start M-byte for constants like Logic_one (default: 230)")
    parser.add_argument("--timer-start", type=int, default=350,
                        help="Start timer number for symbolic S5 timers (default: 350)")
    parser.add_argument("--version", action="version",
                        version=f"awl_dependency_mapper {__version__}")

    args = parser.parse_args()

    # Read source
    try:
        with open(args.source_file, 'r') as f:
            source_text = f.read()
    except FileNotFoundError:
        print(json.dumps({"tool": TOOL, "version": __version__, "schema_version": SCHEMA_VERSION, "status": "error", "error": f"File not found: {args.source_file}", "errors": [{"code": "file-not-found", "message": f"File not found: {args.source_file}"}], "warnings": []}))
        sys.exit(1)

    # Normalize line endings
    source_text = source_text.replace('\r\n', '\n').replace('\r', '\n')

    # Detect block info
    block_type, block_name = detect_block_info(source_text)

    # Extract sections
    code_lines = extract_code_section(source_text)
    var_text = extract_var_section(source_text)

    if not code_lines:
        print(json.dumps({"tool": TOOL, "version": __version__, "schema_version": SCHEMA_VERSION, "status": "error", "error": "No code section found (missing BEGIN)", "errors": [{"code": "no-code-section", "message": "No code section found (missing BEGIN)"}], "warnings": []}))
        sys.exit(1)

    # ─── Phase 1: Find all quoted symbols in code and classify them ───

    external_dbs = OrderedDict()       # db_name → [{"path": ..., "inferred_type": ...}]
    io_inputs = set()
    io_outputs = set()
    io_unknown = set()
    discrete_signals = set()
    s5_timer_symbols = set()
    seen_symbols = set()

    for line_num, line_text in code_lines:
        if is_comment_line(line_text):
            continue

        clean = strip_inline_comment(line_text)

        # Find all quoted symbols on this line
        for m in RE_QUOTED_SYMBOL.finditer(clean):
            symbol = m.group(1)

            category, extra = classify_symbol(symbol, clean, code_lines, var_text)

            if category == "sfb_type":
                continue
            elif category == "db_reference":
                field_path = extra
                if symbol not in external_dbs:
                    external_dbs[symbol] = []
                # Deduplicate field paths
                existing_paths = [f["path"] for f in external_dbs[symbol]]
                if field_path not in existing_paths:
                    # Infer type from the DB field's usage context
                    # Look for REAL comparisons on lines that reference this DB path
                    ftype = "BOOL"  # default
                    full_ref = f'"{symbol}".{field_path}'
                    for ln, lt in code_lines:
                        if full_ref in lt:
                            # Check surrounding lines for REAL ops
                            for ln2, lt2 in code_lines:
                                if abs(ln2 - ln) <= 2:
                                    if RE_REAL_CONTEXT.search(lt2):
                                        ftype = "REAL"
                                        break
                            # Check if this line has L (load) — likely numeric
                            instr = lt.strip().split()[0] if lt.strip() else ""
                            if instr == 'L' and ftype != "REAL":
                                ftype = "INT"
                            # Check if line has T (transfer) — likely numeric output
                            if instr == 'T' and ftype != "REAL":
                                ftype = "INT"
                            if ftype != "BOOL":
                                break

                    external_dbs[symbol].append({
                        "path": field_path,
                        "inferred_type": ftype,
                    })
            elif category == "io_input":
                io_inputs.add(symbol)
            elif category == "io_output":
                io_outputs.add(symbol)
            elif category == "io_unknown":
                io_unknown.add(symbol)
            elif category == "s5_timer_symbol":
                s5_timer_symbols.add(symbol)
            elif category == "discrete":
                discrete_signals.add(symbol)

    # ─── Phase 2: Find other references ───

    abs_s5_timers = find_absolute_s5_timers(code_lines)
    global_memory = find_global_memory(code_lines)
    subfield_accesses = find_subfield_accesses(code_lines)

    # Detect SFB types used in VAR
    sfb_types = set()
    if '"TON"' in var_text or 'SFB 4' in var_text:
        sfb_types.add("TON")
    if '"TOF"' in var_text or 'SFB 5' in var_text:
        sfb_types.add("TOF")
    if '"TP"' in var_text or 'SFB 3' in var_text:
        sfb_types.add("TP")

    # ─── Phase 3: Generate stubs ───

    # Stub DBs
    stub_dbs = []
    db_num = args.stub_db_start
    replacement_map = {}  # "DBName".Field.Path → stub address

    for db_name, fields in external_dbs.items():
        stub = generate_stub_db(db_name, fields, db_num)
        stub_dbs.append(stub)

        # Build replacement map: full original path → stub address
        for sf in stub["fields"]:
            original_ref = f'"{db_name}".{sf["original_path"]}'
            replacement_map[original_ref] = sf["stub_address"]

        db_num += 1

    # I/O mapping
    io_mapping = {}
    io_mapping.update(assign_m_area(io_inputs, args.m_input_start))
    io_mapping.update(assign_m_area(io_outputs, args.m_output_start))

    # Discrete signals — separate constants (like Logic_one) from regular signals
    constants = set()
    regular_discrete = set()
    for sig in discrete_signals:
        if 'logic' in sig.lower() or 'one' in sig.lower() or 'true' in sig.lower():
            constants.add(sig)
        else:
            regular_discrete.add(sig)

    io_mapping.update(assign_m_area(regular_discrete, args.m_discrete_start))
    io_mapping.update(assign_m_area(io_unknown, args.m_discrete_start + 5))
    io_mapping.update(assign_m_area(constants, args.m_const_start))

    # Timer mapping
    timer_mapping = {}
    timer_num = args.timer_start
    for tsym in sorted(s5_timer_symbols):
        timer_mapping[tsym] = f"T {timer_num}"
        timer_num += 1

    # ─── Phase 4: Build output ───

    output = {
        "tool": TOOL,
        "version": __version__,
        "schema_version": SCHEMA_VERSION,
        "status": "success",
        "warnings": [],
        "errors": [],
        "source_file": args.source_file,
        "block_type": block_type,
        "block_name": block_name,

        "external_dbs": [
            {
                "symbolic_name": db_name,
                "fields_referenced": fields,
            }
            for db_name, fields in external_dbs.items()
        ],

        "symbolic_io": (
            [{"symbol": s, "direction": "input", "type": "BOOL"} for s in sorted(io_inputs)] +
            [{"symbol": s, "direction": "output", "type": "BOOL"} for s in sorted(io_outputs)] +
            [{"symbol": s, "direction": "unknown", "type": "BOOL"} for s in sorted(io_unknown)]
        ),

        "discrete_signals": sorted(discrete_signals),
        "constants": sorted(constants),

        "s5_timers_absolute": [f"T {t}" for t in abs_s5_timers],
        "s5_timer_symbols": sorted(s5_timer_symbols),

        "global_memory": global_memory,

        "sfb_types_used": sorted(sfb_types),

        "multi_instance_subfield_accesses": subfield_accesses,

        "summary": {
            "external_db_count": len(external_dbs),
            "external_db_fields": sum(len(f) for f in external_dbs.values()),
            "io_symbol_count": len(io_inputs) + len(io_outputs) + len(io_unknown),
            "discrete_signal_count": len(discrete_signals),
            "s5_timer_count": len(abs_s5_timers) + len(s5_timer_symbols),
            "global_memory_count": len(global_memory),
            "subfield_access_count": len(subfield_accesses),
        },

        "stub_generation": {
            "stub_dbs": stub_dbs,
            "io_mapping": io_mapping,
            "timer_mapping": timer_mapping,
            "replacement_map": replacement_map,
            "instance_db": {
                "db_number": args.instance_db,
                "fb_number": args.fb_number,
                "awl_source": f"DATA_BLOCK DB {args.instance_db}\nFB {args.fb_number}\nBEGIN\nEND_DATA_BLOCK",
            },
            "ob1": {
                "awl_source": (
                    f"ORGANIZATION_BLOCK OB 1\n"
                    f"VAR_TEMP\n"
                    f"  OB1_EV_CLASS : BYTE;\n"
                    f"  OB1_SCAN1 : BYTE;\n"
                    f"  OB1_PRIORITY : BYTE;\n"
                    f"  OB1_OB_NUMBR : BYTE;\n"
                    f"  OB1_RESERVED_1 : BYTE;\n"
                    f"  OB1_RESERVED_2 : BYTE;\n"
                    f"  OB1_PREV_CYCLE : INT;\n"
                    f"  OB1_MIN_CYCLE : INT;\n"
                    f"  OB1_MAX_CYCLE : INT;\n"
                    f"  OB1_DATE_TIME : DATE_AND_TIME;\n"
                    f"END_VAR\n"
                    f"BEGIN\n"
                    f"NETWORK\n"
                    f"TITLE =Main\n"
                ),
            },
        },
    }

    # Add constant initialization to OB1
    const_init_lines = []
    for sym, addr in io_mapping.items():
        if sym in constants:
            const_init_lines.append(f"      SET   ;")
            const_init_lines.append(f"      =     {addr};")
            break  # Only need SET once, then = for each

    if len(constants) > 1:
        for sym in sorted(constants):
            if sym == sorted(constants)[0]:
                continue
            const_init_lines.append(f"      =     {io_mapping[sym]};")

    ob1_source = output["stub_generation"]["ob1"]["awl_source"]
    if const_init_lines:
        ob1_source += '\n'.join(const_init_lines) + '\n'
    ob1_source += (
        f"      CALL FB {args.fb_number}, DB {args.instance_db} (\n"
        f"      );\n"
        f"END_ORGANIZATION_BLOCK\n"
    )
    output["stub_generation"]["ob1"]["awl_source"] = ob1_source

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
