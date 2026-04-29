#!/usr/bin/env python3
"""
sfb_rewriter.py — Rewrite multi-instance SFB sub-field accesses for awlsim.

awlsim cannot compile #TimerName.Q, #TimerName.IN, or #TimerName.ET when the
timer is a multi-instance SFB variable inside an FB. This script rewrites those
accesses to absolute instance DB addresses that awlsim can compile.

Usage:
    $env:AWLSIM_DIR = "C:\\projects\\awlsim\\awl-sim-repo"
    C:\\projects\\awlsim\\.venv\\Scripts\\python.exe sfb_rewriter.py \\
        --source-file myblock.awl \\
        --instance-db 100 \\
        --fb-number 1 \\
        --output rewritten.awl

Output:
    - Rewritten AWL file at --output path
    - JSON summary to stdout

Requires awlsim installed and awlsim_runner.py in the same directory.
"""

import sys
import os
import re
import json
import argparse
import subprocess
import tempfile

__version__ = "1.0.0"
SCHEMA_VERSION = "1.0"
TOOL = "sfb_rewriter"

# SFB sub-field offsets within a multi-instance (verified by simulation)
# All IEC timer SFBs (TP, TON, TOF) share the same 22-byte layout
SFB_SUBFIELD_OFFSETS = {
    "IN": (0, "bit"),   # base + 0, bit 0
    "PT": (2, "time"),  # base + 2, TIME (4 bytes)
    "Q":  (6, "bit"),   # base + 6, bit 0
    "ET": (8, "time"),  # base + 8, TIME (4 bytes)
}

# Map symbolic SFB type names to awlsim-compatible declarations
SFB_TYPE_MAP = {
    '"TON"': "SFB 4",
    '"TOF"': "SFB 5",
    '"TP"':  "SFB 3",
    "SFB 4": "SFB 4",
    "SFB 5": "SFB 5",
    "SFB 3": "SFB 3",
}

S5_TIMER_FAMILIES = ("S_PULSE", "S_PEXT", "S_ODT", "S_ODTS", "S_OFFDT")
S5_WRAPPER_INSTRUCTIONS = {
    "S_PULSE": "SP",
    "S_PEXT": "SE",
    "S_ODT": "SD",
    "S_ODTS": "SS",
    "S_OFFDT": "SF",
}
S5_AWARENESS_TOKENS = ("S5TIME", "SD", "SE", "SS", "SI", "SV")

# Regex: match SFB-typed variable in VAR section
# Handles both "TON" style and SFB 4 style
RE_VAR_SFB = re.compile(
    r'^\s*(\w+)\s*:\s*(?:"TON"|"TOF"|"TP"|SFB\s+[345])\s*;',
    re.IGNORECASE
)

# Regex: match sub-field access in code
# e.g., "      A     #PulseTimer_1.Q; "
#        "      AN    #Step2_TimerPressOff_PA.IN; "
#        "      L     #K248_TimerOn.ET; "
RE_SUBFIELD = re.compile(
    r'^(\s*)(A|AN|O|ON|L|=)\s+#(\w+)\.(Q|IN|ET)\s*;(.*)$'
)

# Regex: match FB declaration
RE_FB_DECL = re.compile(
    r'^(\s*)FUNCTION_BLOCK\s+"([^"]+)"'
)

# Regex: match SFB type in VAR declaration for replacement
RE_TON_DECL = re.compile(r':\s*"TON"\s*;')
RE_TOF_DECL = re.compile(r':\s*"TOF"\s*;')
RE_TP_DECL  = re.compile(r':\s*"TP"\s*;')
RE_TIMER_REF = re.compile(r"\bT\s*(\d+)\b", re.IGNORECASE)
RE_S5_CALL_START = re.compile(
    r'^(\s*)CALL\s+"?(S_PULSE|S_PEXT|S_ODT|S_ODTS|S_OFFDT)"?\s*(?:\(|$)',
    re.IGNORECASE,
)
RE_PARAM_ASSIGN = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)\s*:=\s*([^,);]+)")


def find_native_s5_constructs(source_text):
    """Return native S5/S5TIME constructs that do not need wrapper rewrite."""
    found = []
    for token in S5_AWARENESS_TOKENS:
        if re.search(rf"\b{re.escape(token)}\b", source_text, re.IGNORECASE):
            found.append(token)
    return found


def native_s5_warnings(source_text):
    constructs = find_native_s5_constructs(source_text)
    if not constructs:
        return []
    return [{
        "code": "native_s5_not_rewritten",
        "message": (
            "Native S5/S5TIME constructs are already awlsim-compatible and were left unchanged."
        ),
        "constructs": constructs,
    }]


def scan_used_timers(source_text):
    return {int(m.group(1)) for m in RE_TIMER_REF.finditer(source_text)}


def allocate_timer(used_timers, next_timer):
    while next_timer in used_timers:
        next_timer += 1
    used_timers.add(next_timer)
    return next_timer, next_timer + 1


def _clean_param_value(value):
    value = value.strip()
    if value.endswith(";"):
        value = value[:-1].rstrip()
    return value


def _strip_hash(value):
    return value[1:] if value.startswith("#") else value


def _emit_bool_load(value):
    value = _clean_param_value(value)
    upper = value.upper()
    if upper in ("TRUE", "1"):
        return ["      SET;"]
    if upper in ("FALSE", "0"):
        return ["      CLR;"]
    return [f"      A     {value};"]


def _emit_s5_wrapper(wrapper, params, timer_num, source_line):
    family = wrapper.upper()
    instruction = S5_WRAPPER_INSTRUCTIONS[family]
    if "S" not in params or "TV" not in params:
        missing = [name for name in ("S", "TV") if name not in params]
        return None, {
            "code": "unsupported_s5_wrapper",
            "line": source_line,
            "wrapper": family,
            "message": f"S5 wrapper {family} missing required parameter(s): {', '.join(missing)}",
        }

    lines = [
        f"      // Rewritten {family} wrapper to native S5 timer T {timer_num}",
    ]
    lines.extend(_emit_bool_load(params["S"]))
    lines.append(f"      L     {_clean_param_value(params['TV'])};")
    lines.append(f"      {instruction}    T {timer_num};")

    if params.get("R"):
        lines.extend(_emit_bool_load(params["R"]))
        lines.append(f"      R     T {timer_num};")

    if params.get("Q"):
        lines.append(f"      A     T {timer_num};")
        lines.append(f"      =     {_clean_param_value(params['Q'])};")
    if params.get("BI"):
        lines.append(f"      L     T {timer_num};")
        lines.append(f"      T     {_clean_param_value(params['BI'])};")
    if params.get("BCD"):
        lines.append(f"      LC    T {timer_num};")
        lines.append(f"      T     {_clean_param_value(params['BCD'])};")

    detail = {
        "line": source_line,
        "wrapper": family,
        "native_instruction": instruction,
        "timer": f"T {timer_num}",
        "params": params,
    }
    return lines, detail


def rewrite_s5_wrappers(source_lines, start_timer=350):
    """Rewrite supported S5 timer wrapper CALL blocks into native S5 instructions."""
    rewritten = []
    details = []
    warnings = []
    used_timers = scan_used_timers("\n".join(source_lines))
    next_timer = start_timer
    i = 0

    while i < len(source_lines):
        line = source_lines[i]
        m = RE_S5_CALL_START.match(line)
        if not m:
            rewritten.append(line)
            i += 1
            continue

        call_start_line = i + 1
        wrapper = m.group(2).upper()
        call_lines = [line]
        i += 1
        while i < len(source_lines):
            call_lines.append(source_lines[i])
            stripped = source_lines[i].strip()
            i += 1
            if stripped.startswith(")") or stripped.endswith(");") or stripped == ");":
                break

        params = {}
        for call_line in call_lines:
            code = call_line.split("//", 1)[0]
            for pm in RE_PARAM_ASSIGN.finditer(code):
                params[pm.group(1).upper()] = _clean_param_value(pm.group(2))

        timer_num, next_timer = allocate_timer(used_timers, next_timer)
        emitted, detail_or_warning = _emit_s5_wrapper(wrapper, params, timer_num, call_start_line)
        if emitted is None:
            warnings.append(detail_or_warning)
            rewritten.extend(call_lines)
            continue
        rewritten.extend(emitted)
        details.append(detail_or_warning)

    return rewritten, details, warnings


def parse_source(source_text):
    """Parse AWL source into sections: header, var, code, trailer."""
    lines = source_text.split('\n')

    # Find the FB name
    fb_name = None
    for line in lines:
        m = RE_FB_DECL.match(line)
        if m:
            fb_name = m.group(2)
            break

    # Find section boundaries
    # VAR section: first standalone VAR after FUNCTION_BLOCK, up to the matching END_VAR
    # There may be multiple VAR/END_VAR pairs (VAR, VAR_TEMP, VAR_INPUT, etc.)
    # We need to find the static VAR section (not VAR_TEMP, VAR_INPUT, etc.)
    begin_idx = None
    end_fb_idx = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == 'BEGIN':
            begin_idx = i
        if stripped == 'END_FUNCTION_BLOCK':
            end_fb_idx = i

    if begin_idx is None or end_fb_idx is None:
        return None, None, None, None, fb_name

    header_and_var = '\n'.join(lines[:begin_idx])
    code_section = lines[begin_idx:end_fb_idx + 1]

    return lines, header_and_var, code_section, begin_idx, fb_name


def find_sfb_instances(header_text):
    """Find all SFB-typed static variables in the VAR section.

    Returns dict: {timer_name: sfb_type_string}
    Only looks in VAR sections (not VAR_TEMP, VAR_INPUT, VAR_OUTPUT, VAR_IN_OUT).
    """
    timers = {}
    in_static_var = False
    in_other_var = False

    for line in header_text.split('\n'):
        stripped = line.strip()

        # Track which VAR section we're in
        if stripped in ('VAR_TEMP', 'VAR_INPUT', 'VAR_OUTPUT', 'VAR_IN_OUT'):
            in_other_var = True
            in_static_var = False
            continue
        if stripped == 'VAR':
            in_static_var = True
            in_other_var = False
            continue
        if stripped == 'END_VAR':
            in_static_var = False
            in_other_var = False
            continue

        if not in_static_var:
            continue

        m = RE_VAR_SFB.match(line)
        if m:
            timer_name = m.group(1)
            # Determine the SFB type
            if '"TON"' in line or 'SFB 4' in line:
                timers[timer_name] = "SFB 4"
            elif '"TOF"' in line or 'SFB 5' in line:
                timers[timer_name] = "SFB 5"
            elif '"TP"' in line or 'SFB 3' in line:
                timers[timer_name] = "SFB 3"

    return timers


def build_layout_source(header_text, fb_number):
    """Create a layout-only version of the FB for compilation.

    Keeps VAR declarations, replaces code with NOP 0, fixes FB name and SFB types.
    """
    result_lines = []

    for line in header_text.split('\n'):
        # Fix FB declaration
        m = RE_FB_DECL.match(line)
        if m:
            result_lines.append(f'{m.group(1)}FUNCTION_BLOCK FB {fb_number}')
            continue

        # Fix SFB type declarations
        new_line = line
        new_line = RE_TON_DECL.sub(': SFB 4;', new_line)
        new_line = RE_TOF_DECL.sub(': SFB 5;', new_line)
        new_line = RE_TP_DECL.sub(': SFB 3;', new_line)
        result_lines.append(new_line)

    # Add minimal code body
    result_lines.append('BEGIN')
    result_lines.append('NETWORK')
    result_lines.append('TITLE =Layout only')
    result_lines.append('      NOP   0;')
    result_lines.append('END_FUNCTION_BLOCK')

    return '\n'.join(result_lines)


def get_db_layout(layout_source, fb_number, instance_db, runner_path):
    """Compile the layout-only FB and extract db_layouts from the runner."""

    # Add instance DB and OB1
    full_source = layout_source + f"""

DATA_BLOCK DB {instance_db}
FB {fb_number}
BEGIN
END_DATA_BLOCK

ORGANIZATION_BLOCK OB 1
VAR_TEMP
  OB1_EV_CLASS : BYTE;
  OB1_SCAN1 : BYTE;
  OB1_PRIORITY : BYTE;
  OB1_OB_NUMBR : BYTE;
  OB1_RESERVED_1 : BYTE;
  OB1_RESERVED_2 : BYTE;
  OB1_PREV_CYCLE : INT;
  OB1_MIN_CYCLE : INT;
  OB1_MAX_CYCLE : INT;
  OB1_DATE_TIME : DATE_AND_TIME;
END_VAR
BEGIN
NETWORK
TITLE =Layout compile
      CALL FB {fb_number}, DB {instance_db} (
      );
END_ORGANIZATION_BLOCK
"""

    # Write to temp file and run
    with tempfile.NamedTemporaryFile(mode='w', suffix='.awl', delete=False) as f:
        f.write(full_source)
        temp_path = f.name

    try:
        cmd = [
            sys.executable, runner_path,
            '--source-file', temp_path,
            '--cycles', '1',
            '--read', f'["DB{instance_db}.DBX0.0"]'
        ]
        env = os.environ.copy()
        awlsim_dir = env.get("AWLSIM_DIR")
        if not awlsim_dir:
            for candidate in (r"C:\projects\awlsim\awl-sim-repo", r"C:\projects\awlsim\.awlsim-runtime"):
                if os.path.isdir(os.path.join(candidate, "awlsim")):
                    awlsim_dir = candidate
                    break
        if not awlsim_dir:
            awlsim_dir = r"C:\projects\awlsim\awl-sim-repo"
        pythonpath = env.get("PYTHONPATH", "")
        if awlsim_dir not in pythonpath:
            env["PYTHONPATH"] = awlsim_dir + (os.pathsep + pythonpath if pythonpath else "")

        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
        output = json.loads(result.stdout)

        if output.get("status") not in ("success", "ok"):
            return None, output.get("error", "Unknown compilation error")

        db_key = f"DB{instance_db}"
        layouts = output.get("db_layouts", {}).get(db_key, [])
        return layouts, None

    except subprocess.TimeoutExpired:
        return None, "Compilation timed out (30s)"
    except json.JSONDecodeError as e:
        return None, f"Failed to parse runner output: {e}"
    except FileNotFoundError:
        return None, f"Runner not found at {runner_path}"
    finally:
        os.unlink(temp_path)


def build_offset_map(db_layouts, timer_names, instance_db):
    """Build the replacement map from db_layouts and known SFB sub-field offsets.

    Returns dict: {timer_name: {field: absolute_address}}
    """
    # Build name → offset lookup from layouts
    layout_offsets = {}
    for field in db_layouts:
        name = field["name"]
        offset_str = field["offset"]  # e.g., "132.0"
        base_byte = int(offset_str.split('.')[0])
        layout_offsets[name] = base_byte

    offset_map = {}
    for timer_name in timer_names:
        if timer_name not in layout_offsets:
            continue

        base = layout_offsets[timer_name]
        offset_map[timer_name] = {
            "base_offset": base,
            "Q":  f"DB{instance_db}.DBX {base + SFB_SUBFIELD_OFFSETS['Q'][0]}.0",
            "IN": f"DB{instance_db}.DBX {base + SFB_SUBFIELD_OFFSETS['IN'][0]}.0",
            "ET": f"DB{instance_db}.DBD {base + SFB_SUBFIELD_OFFSETS['ET'][0]}",
        }

    return offset_map


def rewrite_source(source_lines, begin_idx, fb_number, fb_name, offset_map):
    """Apply all rewrites to the original source.

    Returns (rewritten_lines, replacement_details, declaration_fixes).
    """
    rewritten = []
    replacement_details = []
    declaration_fixes = {
        "fb_name_rewritten": False,
        "original_name": fb_name,
        "ton_replacements": 0,
        "tof_replacements": 0,
        "tp_replacements": 0,
    }

    in_code = False

    for line_num, line in enumerate(source_lines, 1):
        original_line = line

        # Fix FB declaration
        m = RE_FB_DECL.match(line)
        if m:
            line = f'{m.group(1)}FUNCTION_BLOCK FB {fb_number}'
            declaration_fixes["fb_name_rewritten"] = True
            rewritten.append(line)
            continue

        # Fix SFB type declarations (before BEGIN)
        if not in_code:
            if RE_TON_DECL.search(line):
                line = RE_TON_DECL.sub(': SFB 4;', line)
                declaration_fixes["ton_replacements"] += 1
            elif RE_TOF_DECL.search(line):
                line = RE_TOF_DECL.sub(': SFB 5;', line)
                declaration_fixes["tof_replacements"] += 1
            elif RE_TP_DECL.search(line):
                line = RE_TP_DECL.sub(': SFB 3;', line)
                declaration_fixes["tp_replacements"] += 1

        # Track when we enter the code section
        if line.strip() == 'BEGIN':
            in_code = True
            rewritten.append(line)
            continue

        # Rewrite sub-field accesses in code section
        if in_code:
            m = RE_SUBFIELD.match(line)
            if m:
                indent, instruction, timer_name, field, trailing = m.groups()
                if timer_name in offset_map and field in offset_map[timer_name]:
                    addr = offset_map[timer_name][field]
                    new_line = f"      {instruction}     {addr};{trailing}"
                    replacement_details.append({
                        "line": line_num,
                        "original": line.rstrip(),
                        "rewritten": new_line.rstrip(),
                        "timer": timer_name,
                        "field": field,
                        "address": addr,
                    })
                    rewritten.append(new_line)
                    continue

        rewritten.append(line)

    return rewritten, replacement_details, declaration_fixes


def selftest():
    source = '''FUNCTION_BLOCK "TimerHost"
VAR
      TonA : "TON";
      TofA : "TOF";
      TpA  : "TP";
END_VAR
BEGIN
      A     #TonA.Q;
      AN    #TofA.IN;
      L     #TpA.ET;
      CALL  "S_ODT" (
        S   := M 0.0,
        TV  := S5T#100MS,
        R   := M 0.1,
        Q   := M 1.0,
        BI  := MW 10,
        BCD := MW 12
      );
END_FUNCTION_BLOCK
'''
    lines, header, _code, begin_idx, fb_name = parse_source(source)
    timers = find_sfb_instances(header)
    if set(timers.values()) != {"SFB 3", "SFB 4", "SFB 5"}:
        print("FAIL - sfb_rewriter selftest did not detect IEC TP/TON/TOF")
        return 1
    offset_map = {
        "TonA": {"Q": "DB100.DBX 0.6", "IN": "DB100.DBX 0.0", "ET": "DB100.DBD 8"},
        "TofA": {"Q": "DB100.DBX 22.6", "IN": "DB100.DBX 22.0", "ET": "DB100.DBD 30"},
        "TpA": {"Q": "DB100.DBX 44.6", "IN": "DB100.DBX 44.0", "ET": "DB100.DBD 52"},
    }
    rewritten, details, decl_fixes = rewrite_source(lines, begin_idx, 1, fb_name, offset_map)
    joined = "\n".join(rewritten)
    if "SFB 3" not in joined or "SFB 4" not in joined or "SFB 5" not in joined:
        print("FAIL - sfb_rewriter selftest did not normalize IEC declarations")
        return 1
    if len(details) != 3:
        print("FAIL - sfb_rewriter selftest replacement count mismatch")
        return 1
    for family in S5_TIMER_FAMILIES:
        if family not in ("S_PULSE", "S_PEXT", "S_ODT", "S_ODTS", "S_OFFDT"):
            print("FAIL - sfb_rewriter selftest S5 family list mismatch")
            return 1
    s5_lines, s5_details, s5_warnings = rewrite_s5_wrappers(source.split("\n"), start_timer=350)
    s5_joined = "\n".join(s5_lines)
    if s5_warnings or len(s5_details) != 1 or "SD    T 350" not in s5_joined:
        print("FAIL - sfb_rewriter selftest S5 wrapper rewrite mismatch")
        return 1
    family_source = "\n".join(
        f'''      CALL "{family}" (
        S := M 0.0,
        TV := S5T#100MS,
        Q := M 1.0
      );'''
        for family in S5_TIMER_FAMILIES
    )
    family_lines, family_details, family_warnings = rewrite_s5_wrappers(family_source.split("\n"), start_timer=10)
    family_joined = "\n".join(family_lines)
    for native in ("SP    T 10", "SE    T 11", "SD    T 12", "SS    T 13", "SF    T 14"):
        if native not in family_joined:
            print(f"FAIL - sfb_rewriter selftest missing native S5 rewrite {native}")
            return 1
    collision_lines, collision_details, _collision_warnings = rewrite_s5_wrappers(
        ["      A     T 350;"] + source.split("\n"),
        start_timer=350,
    )
    if not collision_details or collision_details[0]["timer"] != "T 351":
        print("FAIL - sfb_rewriter selftest S5 timer allocation collision mismatch")
        return 1
    incomplete = '''      CALL "S_ODT" (
        S := M 0.0,
        Q := M 1.0
      );'''
    _bad_lines, _bad_details, bad_warnings = rewrite_s5_wrappers(incomplete.split("\n"))
    if not bad_warnings or bad_warnings[0]["code"] != "unsupported_s5_wrapper":
        print("FAIL - sfb_rewriter selftest unsupported S5 wrapper warning mismatch")
        return 1
    print("OK - sfb_rewriter.py selftest passed (IEC TP/TON/TOF + S5 wrapper rewrite)")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Rewrite multi-instance SFB sub-field accesses to absolute DB addresses for awlsim."
    )
    parser.add_argument("--source-file",
                        help="Path to the AWL source file")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--instance-db", type=int, default=100,
                        help="Instance DB number for the FB (default: 100)")
    parser.add_argument("--fb-number", type=int, default=1,
                        help="FB number to assign (default: 1)")
    parser.add_argument("--s5-start-timer", type=int, default=350,
                        help="First absolute timer number to allocate for S5 wrapper rewrites (default: 350)")
    parser.add_argument("--output", default=None,
                        help="Output path for rewritten AWL (default: <source>_rewritten.awl)")
    parser.add_argument("--runner-path", default=None,
                        help="Path to awlsim_runner.py (default: same directory as this script)")
    parser.add_argument("--version", action="version", version=f"sfb_rewriter {__version__}")

    args = parser.parse_args()

    if args.selftest:
        sys.exit(selftest())

    if not args.source_file:
        parser.error("--source-file is required unless --selftest is used")

    # Resolve paths
    if args.runner_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        args.runner_path = os.path.join(script_dir, "awlsim_runner.py")

    if args.output is None:
        base, ext = os.path.splitext(args.source_file)
        args.output = f"{base}_rewritten{ext}"

    # Read source
    try:
        with open(args.source_file, 'r') as f:
            source_text = f.read()
    except FileNotFoundError:
        print(json.dumps({
            "tool": TOOL,
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "status": "error",
            "errors": [{"code": "file-not-found", "message": f"Source file not found: {args.source_file}"}],
            "warnings": [],
            "error": f"Source file not found: {args.source_file}"
        }))
        sys.exit(1)

    # Phase 1: Parse and find SFB instances
    source_lines, header_text, code_section, begin_idx, fb_name = parse_source(source_text)

    if header_text is None:
        print(json.dumps({
            "tool": TOOL,
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "status": "error",
            "errors": [{"code": "parse-error", "message": "Could not parse AWL source — missing BEGIN or END_FUNCTION_BLOCK"}],
            "warnings": [],
            "error": "Could not parse AWL source — missing BEGIN or END_FUNCTION_BLOCK"
        }))
        sys.exit(1)

    timer_instances = find_sfb_instances(header_text)
    native_warnings = native_s5_warnings(source_text)
    s5_rewritten_lines, s5_rewrite_details, s5_warnings = rewrite_s5_wrappers(
        source_lines,
        start_timer=args.s5_start_timer,
    )
    warnings = s5_warnings + native_warnings

    if not timer_instances:
        # No SFB instances found — nothing to rewrite, just fix declarations
        rewritten, details, decl_fixes = rewrite_source(
            s5_rewritten_lines, begin_idx, args.fb_number, fb_name, {}
        )
        with open(args.output, 'w') as f:
            f.write('\n'.join(rewritten))
        print(json.dumps({
            "tool": TOOL,
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "status": "success",
            "errors": [],
            "warnings": warnings,
            "message": "No multi-instance SFB variables found. S5 wrapper rewrites applied if present.",
            "source_file": args.source_file,
            "output_file": args.output,
            "timers_found": 0,
            "replacements_made": len(details),
            "s5_wrappers_found": len(s5_rewrite_details) + len(s5_warnings),
            "s5_wrappers_rewritten": len(s5_rewrite_details),
            "s5_timer_allocations": [
                {"wrapper": d["wrapper"], "timer": d["timer"], "line": d["line"]}
                for d in s5_rewrite_details
            ],
        }))
        sys.exit(0)

    # Phase 2: Get DB layout by compiling a layout-only version
    layout_source = build_layout_source(header_text, args.fb_number)
    db_layouts, error = get_db_layout(
        layout_source, args.fb_number, args.instance_db, args.runner_path
    )

    if error:
        print(json.dumps({
            "tool": TOOL,
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "status": "error",
            "errors": [{"code": "layout-compilation-failed", "message": error}],
            "warnings": [],
            "error": f"Layout compilation failed: {error}",
            "hint": "Ensure awlsim is installed and AWLSIM_DIR points at the runtime"
        }))
        sys.exit(1)

    # Phase 3: Build offset map
    offset_map = build_offset_map(db_layouts, timer_instances, args.instance_db)

    missing_timers = [t for t in timer_instances if t not in offset_map]
    if missing_timers:
        print(json.dumps({
            "status": "warning",
            "message": f"Could not find offsets for {len(missing_timers)} timer(s): {missing_timers}",
            "found_timers": list(offset_map.keys()),
        }), file=sys.stderr)

    # Phase 4: Rewrite source
    rewritten_lines, replacement_details, declaration_fixes = rewrite_source(
        s5_rewritten_lines, begin_idx, args.fb_number, fb_name, offset_map
    )

    # Write output
    with open(args.output, 'w') as f:
        f.write('\n'.join(rewritten_lines))

    # Summary
    summary = {
        "tool": TOOL,
        "version": __version__,
        "schema_version": SCHEMA_VERSION,
        "status": "success",
        "warnings": warnings,
        "errors": [],
        "source_file": args.source_file,
        "output_file": args.output,
        "instance_db": args.instance_db,
        "fb_number": args.fb_number,
        "timers_found": len(timer_instances),
        "timers_with_offsets": len(offset_map),
        "replacements_made": len(replacement_details),
        "s5_wrappers_found": len(s5_rewrite_details) + len(s5_warnings),
        "s5_wrappers_rewritten": len(s5_rewrite_details),
        "s5_timer_allocations": [
            {"wrapper": d["wrapper"], "timer": d["timer"], "line": d["line"]}
            for d in s5_rewrite_details
        ],
        "s5_replacement_details": s5_rewrite_details,
        "declaration_fixes": declaration_fixes,
        "timer_offset_map": offset_map,
        "replacement_details": replacement_details,
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
