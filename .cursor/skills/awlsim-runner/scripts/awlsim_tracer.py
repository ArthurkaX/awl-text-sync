#!/usr/bin/env python3
"""
awlsim_tracer.py — Per-instruction register tracing for AWL/STL simulation.

Hooks into awlsim's post-instruction callback to capture the full CPU register
state after every instruction, producing a trace that matches the SIMATIC Manager
STL debug view.

Usage:
    $env:AWLSIM_DIR = "C:\\projects\\awlsim\\awl-sim-repo"
    C:\\projects\\awlsim\\.venv\\Scripts\\python.exe awlsim_tracer.py \\
        --source-file myblock.awl \\
        --cycles 1 \\
        --trace-format simatic \\
        [--set-inputs '{"I0.0": true}'] \\
        [--set-db '{"DB10.DBD0": 700.0}'] \\
        [--trace-filter "network:27"] \\
        [--output-trace trace.json] \\
        [--expect-trace assertions.json]

Trace Formats:
    simatic  — Matches SIMATIC Manager debug view columns (default)
    table    — Compact table with decoded REAL values
    json     — Full structured JSON with all register details

Requires awlsim installed and awlsim_runner.py in the same directory.
"""

import sys
import os
import json
import argparse
import struct
import re
import time

__version__ = "1.1.0"
SCHEMA_VERSION = "1.0"
TOOL = "awlsim_tracer"

if "--version" in sys.argv[1:]:
    print(f"awlsim_tracer {__version__}")
    sys.exit(0)

AWLSIM_DIR = os.environ.get("AWLSIM_DIR")
if not AWLSIM_DIR:
    for candidate in (r"C:\projects\awlsim\awl-sim-repo", r"C:\projects\awlsim\.awlsim-runtime"):
        if os.path.isdir(os.path.join(candidate, "awlsim")):
            AWLSIM_DIR = candidate
            break
if not AWLSIM_DIR:
    AWLSIM_DIR = r"C:\projects\awlsim\awl-sim-repo"
if AWLSIM_DIR not in sys.path:
    sys.path.insert(0, AWLSIM_DIR)

from awlsim.core.main import AwlSim
from awlsim.awlcompiler import AwlParser
from awlsim.common import AwlSimError, S7CPUConfig


# ─── Utility functions ───

def dword_to_float(dw):
    """Convert 32-bit unsigned int to IEEE 754 float."""
    try:
        return struct.unpack('>f', struct.pack('>I', dw & 0xFFFFFFFF))[0]
    except:
        return None

def is_plausible_real(value):
    """Check if a 32-bit value looks like a plausible IEEE 754 REAL (not NaN/Inf, reasonable range)."""
    if value == 0:
        return False
    try:
        f = dword_to_float(value)
        if f is None:
            return False
        import math
        if math.isnan(f) or math.isinf(f):
            return False
        if abs(f) > 1e15 or (abs(f) < 1e-15 and abs(f) > 0):
            return False
        return True
    except:
        return False

def format_ar(ar):
    """Format an address register as byte.bit."""
    raw = ar.get()
    byte_off = (raw >> 3) & 0xFFFF
    bit_off = raw & 0x7
    return f"{byte_off}.{bit_off}"

def format_status_word(sw):
    """Format status word as 'XXXX XXXX' (OV OS CC1 CC0 BR OR STA RLO)."""
    bits = [
        sw.OV & 1,   # bit 7
        sw.OS & 1,   # bit 6
        sw.A1 & 1,   # CC1, bit 5
        sw.A0 & 1,   # CC0, bit 4
        sw.BIE & 1,  # BR, bit 3
        sw.OR & 1,   # bit 2
        sw.STA & 1,  # bit 1
        sw.VKE & 1,  # RLO, bit 0
    ]
    s = ''.join(str(b) for b in bits)
    return f"{s[:4]} {s[4:]}"

def parse_set_values(json_str, cpu):
    """Parse and apply --set-inputs or --set-db values to the CPU.
    Reuses the same format as awlsim_runner.py."""
    if not json_str:
        return
    values = json.loads(json_str)
    for addr, val in values.items():
        addr_upper = addr.upper().replace(" ", "")
        # Input bits
        m = re.match(r'^I(\d+)\.(\d+)$', addr_upper)
        if m:
            byte_off, bit_off = int(m.group(1)), int(m.group(2))
            raw = cpu.inputs.getRawDataBytes()
            if val:
                raw[byte_off] = raw[byte_off] | (1 << bit_off)
            else:
                raw[byte_off] = raw[byte_off] & ~(1 << bit_off)
            continue
        # Input bytes
        m = re.match(r'^IB(\d+)$', addr_upper)
        if m:
            cpu.storeInputByte(int(m.group(1)), int(val))
            continue
        # Merker bits
        m = re.match(r'^M(\d+)\.(\d+)$', addr_upper)
        if m:
            byte_off, bit_off = int(m.group(1)), int(m.group(2))
            raw = cpu.flags.getRawDataBytes()
            if val:
                raw[byte_off] = raw[byte_off] | (1 << bit_off)
            else:
                raw[byte_off] = raw[byte_off] & ~(1 << bit_off)
            continue
        # Merker dword (REAL support)
        m = re.match(r'^MD(\d+)$', addr_upper)
        if m:
            off = int(m.group(1))
            raw = cpu.flags.getRawDataBytes()
            if isinstance(val, float):
                bs = struct.pack('>f', val)
            else:
                bs = struct.pack('>I', int(val) & 0xFFFFFFFF)
            raw[off:off+4] = bs
            continue
        # Merker word
        m = re.match(r'^MW(\d+)$', addr_upper)
        if m:
            off = int(m.group(1))
            raw = cpu.flags.getRawDataBytes()
            bs = struct.pack('>H', int(val) & 0xFFFF)
            raw[off:off+2] = bs
            continue
        # DB values
        m = re.match(r'^DB(\d+)\.DB([XBWD])(\d+)(?:\.(\d+))?$', addr_upper)
        if m:
            db_num = int(m.group(1))
            width = m.group(2)
            offset = int(m.group(3))
            bit = int(m.group(4)) if m.group(4) else 0
            try:
                db = cpu.dbs[db_num]
                raw = db.getDataBytes()
                if width == 'X':
                    if val:
                        raw[offset] = raw[offset] | (1 << bit)
                    else:
                        raw[offset] = raw[offset] & ~(1 << bit)
                elif width == 'B':
                    raw[offset] = int(val) & 0xFF
                elif width == 'W':
                    bs = struct.pack('>H', int(val) & 0xFFFF)
                    raw[offset:offset+2] = bs
                elif width == 'D':
                    if isinstance(val, float):
                        bs = struct.pack('>f', val)
                    else:
                        bs = struct.pack('>I', int(val) & 0xFFFFFFFF)
                    raw[offset:offset+4] = bs
            except (KeyError, IndexError):
                pass
            continue


# ─── Trace capture ───

class InstructionTracer:
    """Captures per-instruction register state via awlsim's postInsn callback."""

    def __init__(self, cpu, trace_filter=None, trace_depth="all-blocks"):
        self.cpu = cpu
        self.trace = []
        self.trace_filter = trace_filter  # {"network": set(), "block": set(), "lines": (start,end)}
        self.trace_depth = trace_depth
        self.current_network = 0
        self.current_network_title = ""
        self._prev_rlo = None

    def callback(self, cse, data):
        """Post-instruction callback — called after every instruction."""
        cpu = cse.cpu
        sw = cpu.statusWord

        # Get the instruction that just executed
        insn_ip = cse.ip - cpu.relativeJump
        if insn_ip < 0 or insn_ip >= cse.nrInsns:
            return
        insn = cse.insns[insn_ip]

        # Get instruction text
        insn_text = insn.getStr(compact=False)
        line_nr = insn.getLineNr()

        # Detect NETWORK TITLE from NOP-like boundaries or track via instruction type
        # awlsim doesn't directly expose network numbers in the callback,
        # but we can detect them from the instruction stream

        # Get block info
        block_name = str(cse.block) if cse.block else "OB1"

        # Apply filters
        if self.trace_filter:
            if "block" in self.trace_filter:
                if not any(b.lower() in block_name.lower() for b in self.trace_filter["block"]):
                    return
            if "network" in self.trace_filter:
                # awlsim does not expose STEP 7 NETWORK numbers through this callback.
                # Treat network:N as line:N for a deterministic, documented filter.
                if line_nr not in self.trace_filter["network"]:
                    return
        if self.trace_depth == "current-block" and self.trace:
            first_block = self.trace[0]["block"]
            if block_name != first_block:
                return

        # Get DB numbers
        db1 = cpu.dbRegister.index if cpu.dbRegister else 0
        db2 = cpu.diRegister.index if cpu.diRegister else 0

        # Capture register state
        rlo = sw.VKE
        entry = {
            "index": len(self.trace) + 1,
            "line": line_nr,
            "block": block_name,
            "instruction": insn_text,
            "RLO": rlo,
            "STA": sw.STA,
            "ACCU1": cpu.accu1.get(),
            "ACCU2": cpu.accu2.get(),
            "AR1": format_ar(cpu.ar1),
            "AR2": format_ar(cpu.ar2),
            "DB1": db1,
            "DB2": db2,
            "OV": sw.OV,
            "OS": sw.OS,
            "CC1": sw.A1,
            "CC0": sw.A0,
            "BR": sw.BIE,
            "OR": sw.OR,
            "FC": sw.NER,
            "STATUS": format_status_word(sw),
        }

        # Track RLO transitions
        if self._prev_rlo is not None and rlo != self._prev_rlo:
            entry["rlo_transition"] = {"from": self._prev_rlo, "to": rlo}
        self._prev_rlo = rlo

        self.trace.append(entry)

    def get_rlo_transitions(self):
        """Extract all RLO transitions from the trace."""
        transitions = []
        for e in self.trace:
            if "rlo_transition" in e:
                transitions.append({
                    "index": e["index"],
                    "from": e["rlo_transition"]["from"],
                    "to": e["rlo_transition"]["to"],
                    "instruction": e["instruction"].strip(),
                    "line": e["line"],
                })
        return transitions

    def format_simatic(self):
        """Format trace like SIMATIC Manager STL debug view."""
        lines = []
        hdr = f"{'Instr':>5} | {'Line':>4} | {'Code':<45} | {'RLO':>3} | {'STA':>3} | {'ACCU1':>11} | {'ACCU2':>11} | {'AR1':>7} | {'AR2':>7} | {'DB1':>3} | {'DB2':>3} | STATUS"
        lines.append(hdr)
        lines.append("-" * len(hdr))

        for e in self.trace:
            accu1 = str(e["ACCU1"])
            accu2 = str(e["ACCU2"])
            code = e["instruction"]
            # Truncate long instructions
            if len(code) > 45:
                code = code[:42] + "..."

            marker = " *" if "rlo_transition" in e else "  "
            lines.append(
                f"{e['index']:>5} | {e['line']:>4} | {code:<45} |{marker}{e['RLO']} | {e['STA']:>3} | {accu1:>11} | {accu2:>11} | {e['AR1']:>7} | {e['AR2']:>7} | {e['DB1']:>3} | {e['DB2']:>3} | {e['STATUS']}"
            )

        return '\n'.join(lines)

    def format_table(self):
        """Format trace as a compact table with decoded REAL values."""
        lines = []
        hdr = f"{'#':>4} | {'Line':>4} | {'Code':<40} | {'RLO'} | {'ACCU1':>12} | {'ACCU1 (REAL)':>14} | {'ACCU2':>12} | {'DB1':>3} | {'DB2':>3} | STATUS"
        lines.append(hdr)
        lines.append("-" * len(hdr))

        for e in self.trace:
            accu1_val = e["ACCU1"]
            accu1_str = str(accu1_val)
            accu1_real = ""
            if is_plausible_real(accu1_val):
                f = dword_to_float(accu1_val)
                if f is not None:
                    accu1_real = f"{f:.4f}"

            accu2_str = str(e["ACCU2"])
            code = e["instruction"].strip()
            if len(code) > 40:
                code = code[:37] + "..."

            marker = "*" if "rlo_transition" in e else " "

            lines.append(
                f"{e['index']:>4} | {e['line']:>4} | {code:<40} | {marker}{e['RLO']}  | {accu1_str:>12} | {accu1_real:>14} | {accu2_str:>12} | {e['DB1']:>3} | {e['DB2']:>3} | {e['STATUS']}"
            )

        return '\n'.join(lines)

    def format_json(self):
        """Format trace as structured JSON."""
        # Enrich each entry with hex and REAL decode
        enriched = []
        for e in self.trace:
            entry = dict(e)
            entry["ACCU1_hex"] = f"0x{e['ACCU1']:08X}"
            entry["ACCU2_hex"] = f"0x{e['ACCU2']:08X}"
            if is_plausible_real(e["ACCU1"]):
                entry["ACCU1_real"] = dword_to_float(e["ACCU1"])
            if is_plausible_real(e["ACCU2"]):
                entry["ACCU2_real"] = dword_to_float(e["ACCU2"])
            enriched.append(entry)

        output = {
            "tool": TOOL,
            "status": "success",
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "warnings": [],
            "errors": [],
            "trace": enriched,
            "summary": {
                "total_instructions": len(self.trace),
                "rlo_transitions": self.get_rlo_transitions(),
                "rlo_transition_count": len(self.get_rlo_transitions()),
            }
        }
        return json.dumps(output, indent=2)

    def check_assertions(self, assertions, tolerance=1e-6):
        """Check trace assertions against captured register states.

        assertions format:
        [
            {"at": 5, "check": {"RLO": 1, "ACCU1": 50}},
            {"at": 12, "check": {"RLO": 0, "DB1": 173}},
            {"at": 15, "check": {"ACCU1_real": 6.0}}
        ]

        Returns (all_pass, results_list).
        """
        results = []
        all_pass = True

        for assertion in assertions:
            at_idx = assertion["at"]
            checks = assertion["check"]
            note = assertion.get("note", "")

            # Find the trace entry at this index
            entry = None
            for e in self.trace:
                if e["index"] == at_idx:
                    entry = e
                    break

            if entry is None:
                results.append({
                    "at": at_idx, "pass": False,
                    "error": f"No trace entry at index {at_idx}",
                    "note": note,
                })
                all_pass = False
                continue

            for key, expected in checks.items():
                actual = None
                passed = False

                if key == "ACCU1_real":
                    actual = dword_to_float(entry["ACCU1"])
                    if actual is not None:
                        passed = abs(actual - expected) <= tolerance
                    else:
                        passed = False
                elif key == "ACCU2_real":
                    actual = dword_to_float(entry["ACCU2"])
                    if actual is not None:
                        passed = abs(actual - expected) <= tolerance
                    else:
                        passed = False
                elif key == "ACCU1_hex":
                    actual = f"0x{entry['ACCU1']:08X}"
                    passed = actual.lower() == expected.lower()
                elif key == "ACCU2_hex":
                    actual = f"0x{entry['ACCU2']:08X}"
                    passed = actual.lower() == expected.lower()
                elif key in entry:
                    actual = entry[key]
                    passed = actual == expected
                else:
                    actual = None
                    passed = False

                result = {
                    "at": at_idx,
                    "register": key,
                    "expected": expected,
                    "actual": actual,
                    "pass": passed,
                }
                if note:
                    result["note"] = note
                if key.endswith("_real") and actual is not None:
                    result["delta"] = abs(actual - expected)

                results.append(result)
                if not passed:
                    all_pass = False

        return all_pass, results


# ─── Main execution ───

def compile_and_setup(source_text, mnemonics="EN", cpu_type="S7-300"):
    """Compile AWL source and return (sim, cpu)."""
    sim = AwlSim()
    sim.reset()

    cpu = sim.getCPU()
    cpuConf = cpu.getConf()

    mnem_map = {
        "EN": S7CPUConfig.MNEMONICS_EN,
        "DE": S7CPUConfig.MNEMONICS_DE,
        "AUTO": S7CPUConfig.MNEMONICS_AUTO,
    }
    cpuConf.setConfiguredMnemonics(mnem_map.get(mnemonics, S7CPUConfig.MNEMONICS_EN))

    if cpu_type == "S7-400":
        cpuConf.setConfiguredNrAccus(4)

    parser = AwlParser()
    parser.parseText(source_text)
    sim.load(parser.getParseTree())
    sim.build()
    sim.startup()

    return sim, cpu


def main():
    ap = argparse.ArgumentParser(
        description="Per-instruction register tracing for AWL/STL simulation."
    )

    # Source
    source_group = ap.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source", type=str, help="Inline AWL source")
    source_group.add_argument("--source-file", type=str, help="Path to AWL source file")

    # Simulation options
    ap.add_argument("--cycles", type=int, default=1, help="Number of OB1 cycles (default: 1)")
    ap.add_argument("--set-inputs", type=str, help='JSON: {"I0.0": true, "IW2": 1500}')
    ap.add_argument("--set-db", type=str, help='JSON: {"DB1.DBW0": 100, "MD100": 7.5}')
    ap.add_argument("--cpu-type", type=str, default="S7-300", choices=["S7-300", "S7-400"])
    ap.add_argument("--mnemonics", type=str, default="EN", choices=["EN", "DE", "AUTO"])
    ap.add_argument("--cycle-delay-ms", type=int, default=0, help="Delay between cycles (ms)")

    # Trace options
    ap.add_argument("--trace-format", type=str, default="simatic",
                    choices=["simatic", "table", "json"],
                    help="Output format (default: simatic)")
    ap.add_argument("--trace-filter", type=str, action="append",
                    help='Filter: "block:FB1" or "network:27" (can repeat)')
    ap.add_argument("--output-trace", type=str, help="Write trace to file instead of stdout")
    ap.add_argument("--trace-depth", type=str, default="all-blocks",
                    choices=["current-block", "all-blocks"],
                    help="Trace into CALLed blocks or only current (default: all-blocks)")

    # Assertions
    ap.add_argument("--expect-trace", type=str,
                    help="JSON file or inline JSON with trace assertions")
    ap.add_argument("--tolerance", type=float, default=1e-6,
                    help="Tolerance for REAL comparisons (default: 1e-6)")

    ap.add_argument("--version", action="version", version=f"awlsim_tracer {__version__}")

    args = ap.parse_args()

    # Read source
    if args.source_file:
        try:
            with open(args.source_file, 'r') as f:
                source_text = f.read()
        except FileNotFoundError:
            print(json.dumps({"tool": TOOL, "version": __version__, "schema_version": SCHEMA_VERSION, "status": "error", "error": f"File not found: {args.source_file}", "errors": [{"code": "file-not-found", "message": f"File not found: {args.source_file}"}], "warnings": []}))
            sys.exit(1)
    else:
        source_text = args.source

    # Normalize line endings
    source_text = source_text.replace('\r\n', '\n').replace('\r', '\n')

    # Parse trace filters
    trace_filter = None
    if args.trace_filter:
        trace_filter = {}
        for f in args.trace_filter:
            key, _, val = f.partition(":")
            key = key.strip().lower()
            if key == "block":
                trace_filter.setdefault("block", set()).add(val.strip())
            elif key == "network":
                trace_filter.setdefault("network", set()).add(int(val.strip()))

    # Compile
    try:
        sim, cpu = compile_and_setup(source_text, args.mnemonics, args.cpu_type)
    except AwlSimError as e:
        print(json.dumps({"tool": TOOL, "version": __version__, "schema_version": SCHEMA_VERSION, "status": "compile_error", "error": str(e), "errors": [{"code": "compile-error", "message": str(e)}], "warnings": []}))
        sys.exit(1)

    # Set inputs/DB values
    if args.set_inputs:
        parse_set_values(args.set_inputs, cpu)
    if args.set_db:
        parse_set_values(args.set_db, cpu)

    # Create tracer and register callback
    tracer = InstructionTracer(cpu, trace_filter, args.trace_depth)
    cpu.setPostInsnCallback(tracer.callback)

    # Run cycles
    try:
        for cycle in range(args.cycles):
            if args.set_inputs:
                parse_set_values(args.set_inputs, cpu)
            sim.runCycle()
            if args.cycle_delay_ms > 0 and cycle < args.cycles - 1:
                time.sleep(args.cycle_delay_ms / 1000.0)
    except AwlSimError as e:
        print(json.dumps({"tool": TOOL, "version": __version__, "schema_version": SCHEMA_VERSION, "status": "runtime_error", "error": str(e), "errors": [{"code": "runtime-error", "message": str(e)}], "warnings": []}))
        sys.exit(1)

    # Format output
    if args.trace_format == "simatic":
        output = tracer.format_simatic()
    elif args.trace_format == "table":
        output = tracer.format_table()
    elif args.trace_format == "json":
        output = tracer.format_json()

    # Add summary for non-json formats
    if args.trace_format != "json":
        transitions = tracer.get_rlo_transitions()
        output += f"\n\nTotal instructions: {len(tracer.trace)}, Cycles: {args.cycles}"
        if transitions:
            output += f"\n\nRLO Transitions ({len(transitions)}):"
            for t in transitions:
                output += f"\n  Instr {t['index']:>4} (line {t['line']:>4}): RLO {t['from']}→{t['to']}  {t['instruction']}"

    # Write output
    # For JSON + assertions: defer printing until assertions are merged
    should_print_now = not (args.trace_format == "json" and args.expect_trace)

    if args.output_trace and should_print_now:
        with open(args.output_trace, 'w') as f:
            f.write(output)
        print(f"Trace written to {args.output_trace} ({len(tracer.trace)} instructions)", file=sys.stderr)
    elif should_print_now:
        print(output)

    # Check assertions (Task 3)
    if args.expect_trace:
        try:
            if os.path.isfile(args.expect_trace):
                with open(args.expect_trace, 'r') as f:
                    assertions_data = json.load(f)
            else:
                assertions_data = json.loads(args.expect_trace)

            assertions = assertions_data if isinstance(assertions_data, list) else assertions_data.get("trace_assertions", [])
            all_pass, results = tracer.check_assertions(assertions, args.tolerance)

            # Print assertion results
            assertion_output = {
                "tool": "trace_assertions",
                "schema_version": SCHEMA_VERSION,
                "assertion_result": "PASS" if all_pass else "FAIL",
                "total": len(results),
                "passed": sum(1 for r in results if r["pass"]),
                "failed": sum(1 for r in results if not r["pass"]),
                "details": results,
            }

            if args.trace_format == "json":
                # Merge into the JSON output
                full = json.loads(output)
                full["assertions"] = assertion_output
                output = json.dumps(full, indent=2)
                if args.output_trace:
                    with open(args.output_trace, 'w') as f:
                        f.write(output)
                else:
                    # Reprint with assertions
                    print(output)
            else:
                print(f"\n{'=' * 50}")
                print(f"Trace Assertions: {assertion_output['assertion_result']}")
                print(f"  Passed: {assertion_output['passed']}/{assertion_output['total']}")
                for r in results:
                    status = "✓" if r["pass"] else "✗"
                    note = f" ({r['note']})" if r.get("note") else ""
                    if r["pass"]:
                        print(f"  {status} Instr {r['at']}: {r['register']} = {r['actual']}{note}")
                    else:
                        print(f"  {status} Instr {r['at']}: {r['register']} expected={r['expected']}, actual={r['actual']}{note}")

            sys.exit(0 if all_pass else 2)

        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"\nAssertion error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
