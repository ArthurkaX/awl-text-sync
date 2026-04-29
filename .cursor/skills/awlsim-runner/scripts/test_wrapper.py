#!/usr/bin/env python3
"""
test_wrapper.py - Smoke and regression tests for the awlsim-runner wrapper.

Tests the wrapper's own features (not awlsim internals):
  - Address parsing for all patterns
  - store_value / fetch_value roundtrip for BOOL, INT, DINT, REAL
  - REAL encode/decode fidelity
  - Signed INT overflow behavior
  - Compile success and compile failure detection
  - FB harness generation with typed output_map
  - FC harness generation with typed output_map
  - Status word readback
  - DB access error handling
  - Assertion layer: pass case and fail case
  - Backward compatibility (plain string reads)

Run:
    PYTHONPATH=/home/claude/awlsim python3 scripts/test_wrapper.py

Exit code: 0 if all tests pass, 1 if any fail.
"""

import sys
import os
import json
import struct
import math
import argparse
import subprocess
import tempfile
from pathlib import Path

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
AWLSIM_DIR = os.environ.get("AWLSIM_DIR", "/home/claude/awlsim")
if AWLSIM_DIR not in sys.path:
    sys.path.insert(0, AWLSIM_DIR)
DEFAULT_AWLSIM_DIR = Path(SCRIPT_DIR).parents[2] / "awl-sim-repo"
if (DEFAULT_AWLSIM_DIR / "awlsim").exists() and str(DEFAULT_AWLSIM_DIR) not in sys.path:
    sys.path.insert(0, str(DEFAULT_AWLSIM_DIR))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from awlsim_runner import (
    parse_address, encode_real, decode_real, store_value, fetch_value,
    run_simulation, normalize_read_spec, S7_TYPES, __version__,
)
import awlsim_runner
from test_harness_generator import (
    generate_fb_harness, generate_fc_harness, format_awl_value,
)

RUNNER_PATH = Path(SCRIPT_DIR) / "awlsim_runner.py"


def run_cli(args, source_text=None):
    env = os.environ.copy()
    if "AWLSIM_DIR" not in env:
        candidate = Path(SCRIPT_DIR).parents[2] / "awl-sim-repo"
        if (candidate / "awlsim").exists():
            env["AWLSIM_DIR"] = str(candidate)
    return subprocess.run(
        [sys.executable, str(RUNNER_PATH)] + args,
        input=source_text,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )

# ============================================================
# Test Infrastructure
# ============================================================

_pass_count = 0
_fail_count = 0
_test_names = []


def test(name):
    """Decorator to register and run a test function."""
    def decorator(fn):
        _test_names.append((name, fn))
        return fn
    return decorator


def ok(condition, msg=""):
    global _pass_count, _fail_count
    if condition:
        _pass_count += 1
    else:
        _fail_count += 1
        # Walk the stack to find the test name
        import traceback
        tb = traceback.extract_stack()
        caller = tb[-2]
        print(f"    FAIL: {msg} (line {caller.lineno})")


def approx(a, b, tol=1e-5):
    """Check if two floats are approximately equal."""
    if math.isnan(a) and math.isnan(b):
        return True
    return abs(a - b) <= tol


# ============================================================
# Tests
# ============================================================

@test("parse_address: all address patterns")
def test_parse_address():
    from awlsim.core.operatortypes import AwlOperatorTypes as OT

    cases = [
        # (addr_string, expected_mem_type, expected_byte, expected_bit, expected_width, expected_db)
        ("I0.0",        OT.MEM_E,  0, 0, 1,  None),
        ("I0.7",        OT.MEM_E,  0, 7, 1,  None),
        ("E1.3",        OT.MEM_E,  1, 3, 1,  None),
        ("IB0",         OT.MEM_E,  0, 0, 8,  None),
        ("EB4",         OT.MEM_E,  4, 0, 8,  None),
        ("IW0",         OT.MEM_E,  0, 0, 16, None),
        ("EW2",         OT.MEM_E,  2, 0, 16, None),
        ("ID0",         OT.MEM_E,  0, 0, 32, None),
        ("Q0.0",        OT.MEM_A,  0, 0, 1,  None),
        ("A1.5",        OT.MEM_A,  1, 5, 1,  None),
        ("QB0",         OT.MEM_A,  0, 0, 8,  None),
        ("QW0",         OT.MEM_A,  0, 0, 16, None),
        ("QD0",         OT.MEM_A,  0, 0, 32, None),
        ("M0.0",        OT.MEM_M,  0, 0, 1,  None),
        ("M10.3",       OT.MEM_M, 10, 3, 1,  None),
        ("MB0",         OT.MEM_M,  0, 0, 8,  None),
        ("MW10",        OT.MEM_M, 10, 0, 16, None),
        ("MD100",       OT.MEM_M, 100,0, 32, None),
        ("DB1.DBX0.0",  OT.MEM_DB, 0, 0, 1,  1),
        ("DB5.DBB10",   OT.MEM_DB, 10,0, 8,  5),
        ("DB1.DBW0",    OT.MEM_DB, 0, 0, 16, 1),
        ("DB1.DBD0",    OT.MEM_DB, 0, 0, 32, 1),
        ("T0",          OT.MEM_T,  0, 0, 16, None),
        ("C0",          OT.MEM_Z,  0, 0, 16, None),
        ("Z5",          OT.MEM_Z,  5, 0, 16, None),
    ]

    for addr_str, exp_mem, exp_byte, exp_bit, exp_width, exp_db in cases:
        mem_type, byte_off, bit_off, width, db_num = parse_address(addr_str)
        ok(mem_type == exp_mem, f"{addr_str}: mem_type mismatch")
        ok(byte_off == exp_byte, f"{addr_str}: byte_off expected {exp_byte}, got {byte_off}")
        ok(bit_off == exp_bit, f"{addr_str}: bit_off expected {exp_bit}, got {bit_off}")
        ok(width == exp_width, f"{addr_str}: width expected {exp_width}, got {width}")
        ok(db_num == exp_db, f"{addr_str}: db_num expected {exp_db}, got {db_num}")

    # Invalid address should raise
    try:
        parse_address("FOOBAR")
        ok(False, "Should have raised ValueError for invalid address")
    except ValueError:
        ok(True)


@test("encode_real / decode_real roundtrip")
def test_real_encoding():
    test_values = [0.0, 1.0, -1.0, 12.5, -3.14, 100000.0, 1e-10, 1e30]
    for val in test_values:
        encoded = encode_real(val)
        decoded = decode_real(encoded)
        # 32-bit float has limited precision, so compare with tolerance
        ok(approx(decoded, val, tol=abs(val) * 1e-6 + 1e-38),
           f"REAL roundtrip failed for {val}: got {decoded}")

    # Special: NaN
    nan_encoded = encode_real(float('nan'))
    nan_decoded = decode_real(nan_encoded)
    ok(math.isnan(nan_decoded), "NaN roundtrip failed")

    # Special: Infinity
    inf_encoded = encode_real(float('inf'))
    inf_decoded = decode_real(inf_encoded)
    ok(math.isinf(inf_decoded) and inf_decoded > 0, "Inf roundtrip failed")

    # Known bit pattern: 12.5 = 0x41480000
    ok(encode_real(12.5) == 0x41480000, f"12.5 should encode to 0x41480000, got {hex(encode_real(12.5))}")
    ok(decode_real(0x41480000) == 12.5, f"0x41480000 should decode to 12.5, got {decode_real(0x41480000)}")


@test("normalize_read_spec: plain and typed formats")
def test_normalize_read_spec():
    # Plain string
    spec = normalize_read_spec("MW10")
    ok(spec["addr"] == "MW10", f"addr mismatch: {spec}")
    ok(spec["type"] == "INT", f"type mismatch for MW10: {spec}")

    spec = normalize_read_spec("MD100")
    ok(spec["type"] == "DINT", f"plain MD should default to DINT: {spec}")

    spec = normalize_read_spec("Q0.0")
    ok(spec["type"] == "BOOL", f"Q0.0 should be BOOL: {spec}")

    # Typed dict
    spec = normalize_read_spec({"addr": "MD100", "type": "REAL"})
    ok(spec["addr"] == "MD100" and spec["type"] == "REAL", f"typed spec mismatch: {spec}")

    # Typed dict with lowercase
    spec = normalize_read_spec({"addr": "MD0", "type": "real"})
    ok(spec["type"] == "REAL", f"should uppercase type: {spec}")


@test("CLI contract: help without AWLSIM_DIR")
def test_cli_help_without_awlsim_dir():
    env = os.environ.copy()
    env.pop("AWLSIM_DIR", None)
    proc = subprocess.run(
        [sys.executable, str(RUNNER_PATH), "--help"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=10,
    )
    ok(proc.returncode == 0, f"--help failed: {proc.stderr}")
    ok("--read-typed" in proc.stdout and "--set-inputs-typed" in proc.stdout, "help missing typed flags")


@test("CLI contract: schema v2 comma reads and typed writes")
def test_cli_schema_v2_comma_reads_typed_writes():
    source = "ORGANIZATION_BLOCK OB 1\nBEGIN\nEND_ORGANIZATION_BLOCK\n"
    proc = run_cli([
        "--source", source,
        "--cycles", "1",
        "--set-inputs-typed", '[{"addr":"MD200","type":"REAL","value":12.5}]',
        "--read", "MD200:REAL,Q4.0:BOOL",
        "--bypass-precheck",
        "--format", "json",
    ])
    ok(proc.returncode == 0, f"CLI returned {proc.returncode}: {proc.stderr} {proc.stdout}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        ok(False, f"CLI did not emit JSON only: {e}; stdout={proc.stdout!r}")
        return
    ok(payload.get("schema_version") == "2.0", f"schema mismatch: {payload}")
    ok(payload.get("status") == "ok", f"public status mismatch: {payload.get('status')}")
    reads = payload.get("results", [{}])[0].get("reads", {})
    ok(approx(reads.get("MD200"), 12.5), f"typed REAL read mismatch: {reads}")
    ok(reads.get("Q4.0") is False, f"BOOL read mismatch: {reads}")


@test("CLI contract: precheck failure is schema-valid")
def test_cli_precheck_failure_schema_valid():
    source = "ORGANIZATION_BLOCK OB 1\nBEGIN\n      NOP 0\nEND_ORGANIZATION_BLOCK\n"
    proc = run_cli(["--source", source, "--cycles", "1", "--format", "json"])
    ok(proc.returncode == 1, f"precheck failure should exit 1, got {proc.returncode}")
    payload = json.loads(proc.stdout)
    ok(payload.get("schema_version") == "2.0", f"schema mismatch: {payload}")
    ok(payload.get("status") == "fail", f"status mismatch: {payload}")
    ok(payload.get("precheck", {}).get("fail_count", 0) > 0, f"precheck not flattened: {payload}")


@test("virtual time: S5 on-delay advances without sleep")
def test_virtual_time_s5_on_delay_no_sleep():
    source = """ORGANIZATION_BLOCK OB 1
BEGIN
      A     I 0.0;
      L     S5T#100MS;
      SD    T 1;
      A     T 1;
      =     Q 0.0;
END_ORGANIZATION_BLOCK
"""
    original_sleep = awlsim_runner.time.sleep

    def fail_sleep(_seconds):
        raise AssertionError("time.sleep must not be used for virtual time")

    awlsim_runner.time.sleep = fail_sleep
    try:
        result = run_simulation(
            sources=[source],
            cycles=4,
            set_inputs={"I0.0": True},
            read_addrs=[{"addr": "Q0.0", "type": "BOOL"}],
            virtual_time_ms_per_cycle=50,
        )
    finally:
        awlsim_runner.time.sleep = original_sleep

    ok(result["status"] == "success", f"virtual timer compile/run failed: {result}")
    reads = [cycle["memory_state"]["Q0.0"] for cycle in result["results"]]
    ok(reads[:2] == [False, False], f"timer should remain false before elapsed time: {reads}")
    ok(reads[-1] is True, f"timer should become true after enough virtual elapsed time: {reads}")
    ok(result.get("virtual_time", {}).get("mode") == "cpu_timestamp_injection", "virtual time mode missing")


@test("compile success: trivial OB1")
def test_compile_success():
    result = run_simulation(
        sources=["ORGANIZATION_BLOCK OB 1\nBEGIN\n    SET;\n    = Q 0.0;\nEND_ORGANIZATION_BLOCK"],
        cycles=1,
        read_addrs=["Q0.0"],
    )
    ok(result["status"] == "success", f"Expected success, got {result['status']}")
    ok(result["cycles_executed"] == 1, f"Expected 1 cycle, got {result['cycles_executed']}")
    ok(result["results"][0]["memory_state"]["Q0.0"] == True, "Q0.0 should be True")


@test("compile failure: invalid instruction")
def test_compile_failure():
    result = run_simulation(
        sources=["ORGANIZATION_BLOCK OB 1\nBEGIN\n    FOOBAR;\nEND_ORGANIZATION_BLOCK"],
        cycles=1,
    )
    ok(result["status"] == "compile_error", f"Expected compile_error, got {result['status']}")
    ok(result["error"] is not None and len(result["error"]) > 0, "Should have error message")


@test("BOOL store/fetch roundtrip via simulation")
def test_bool_roundtrip():
    # Set M0.0 = true, read it back
    result = run_simulation(
        sources=["ORGANIZATION_BLOCK OB 1\nBEGIN\nEND_ORGANIZATION_BLOCK"],
        cycles=1,
        set_inputs={"M0.0": True},
        read_addrs=["M0.0"],
    )
    ok(result["status"] == "success", f"BOOL test: {result['status']}")
    ok(result["results"][0]["memory_state"]["M0.0"] == True, "M0.0 should be True")


@test("INT store/fetch and signed overflow at 32767+1")
def test_int_overflow():
    source = """ORGANIZATION_BLOCK OB 1
BEGIN
    L MW 0;
    L 1;
    +I;
    T MW 0;
END_ORGANIZATION_BLOCK"""
    result = run_simulation(
        sources=[source],
        cycles=2,
        set_db={"MW0": 32766},
        read_addrs=["MW0"],
        read_stw=True,
    )
    ok(result["status"] == "success", f"INT overflow test: {result['status']}")
    # Cycle 1: 32766 + 1 = 32767 (no overflow)
    ok(result["results"][0]["memory_state"]["MW0"] == 32767, "Cycle 1 should be 32767")
    ok(result["results"][0]["status_word"]["OV"] == 0, "Cycle 1 OV should be 0")
    # Cycle 2: 32767 + 1 = -32768 (overflow!)
    ok(result["results"][1]["memory_state"]["MW0"] == -32768, "Cycle 2 should be -32768 (overflow)")
    ok(result["results"][1]["status_word"]["OV"] == 1, "Cycle 2 OV should be 1")


@test("DINT arithmetic")
def test_dint_arithmetic():
    source = """ORGANIZATION_BLOCK OB 1
BEGIN
    L MD 0;
    L L#100000;
    +D;
    T MD 0;
END_ORGANIZATION_BLOCK"""
    result = run_simulation(
        sources=[source],
        cycles=1,
        set_db={"MD0": 200000},
        read_addrs=["MD0"],
    )
    ok(result["status"] == "success", f"DINT test: {result['status']}")
    ok(result["results"][0]["memory_state"]["MD0"] == 300000, f"Expected 300000, got {result['results'][0]['memory_state']['MD0']}")


@test("REAL read/write roundtrip via simulation")
def test_real_roundtrip_sim():
    source = """ORGANIZATION_BLOCK OB 1
BEGIN
    L MD 0;
    L MD 4;
    +R;
    T MD 8;
END_ORGANIZATION_BLOCK"""
    result = run_simulation(
        sources=[source],
        cycles=1,
        set_db={"MD0": 10.5, "MD4": 2.0},
        read_addrs=[
            {"addr": "MD0", "type": "REAL"},
            {"addr": "MD4", "type": "REAL"},
            {"addr": "MD8", "type": "REAL"},
        ],
    )
    ok(result["status"] == "success", f"REAL roundtrip: {result['status']}")
    md0 = result["results"][0]["memory_state"]["MD0"]
    md4 = result["results"][0]["memory_state"]["MD4"]
    md8 = result["results"][0]["memory_state"]["MD8"]
    ok(approx(md0, 10.5), f"MD0 should be ~10.5, got {md0}")
    ok(approx(md4, 2.0), f"MD4 should be ~2.0, got {md4}")
    ok(approx(md8, 12.5), f"MD8 should be ~12.5, got {md8}")


@test("REAL without typed spec returns raw integer (backward compat)")
def test_real_untyped_returns_int():
    source = """ORGANIZATION_BLOCK OB 1
BEGIN
    L 1.250000e+001;
    T MD 0;
END_ORGANIZATION_BLOCK"""
    result = run_simulation(
        sources=[source],
        cycles=1,
        read_addrs=["MD0"],  # plain string = DINT interpretation
    )
    ok(result["status"] == "success", f"untyped REAL test: {result['status']}")
    raw = result["results"][0]["memory_state"]["MD0"]
    # 12.5 as IEEE 754 = 0x41480000 = 1095237632 as signed DINT
    ok(raw == 1095237632, f"Untyped MD0 should be raw int 1095237632, got {raw}")


@test("FB harness generation with typed output_map")
def test_fb_harness():
    fb_source = """FUNCTION_BLOCK FB 1
VAR_INPUT
    Setpoint : REAL;
    Enable : BOOL;
END_VAR
VAR_OUTPUT
    Output : REAL;
    Active : BOOL;
END_VAR
BEGIN
    L #Setpoint;
    L 2.000000e+000;
    *R;
    T #Output;
    A #Enable;
    = #Active;
END_FUNCTION_BLOCK"""

    result = generate_fb_harness(
        fb_source, block_number=1, instance_db_number=1,
        test_inputs={"Setpoint": 5.0, "Enable": True},
        read_outputs=["Output", "Active"],
    )

    ok("source" in result, "Harness should have source")
    ok("output_map" in result, "Harness should have output_map")

    # output_map should have typed entries
    om = result["output_map"]
    ok("Output" in om, "output_map missing 'Output'")
    ok(om["Output"]["type"] == "REAL", f"Output type should be REAL, got {om['Output']['type']}")
    ok("addr" in om["Output"], "Output entry missing addr")

    ok("Active" in om, "output_map missing 'Active'")
    ok(om["Active"]["type"] == "BOOL", f"Active type should be BOOL, got {om['Active']['type']}")

    # read_addresses should be typed specs
    ra = result["read_addresses"]
    ok(len(ra) == 2, f"Expected 2 read_addresses, got {len(ra)}")
    ok(all("addr" in r and "type" in r for r in ra), "read_addresses should be typed dicts")

    # Now run the generated source through the runner
    sim_result = run_simulation(
        sources=[result["source"]],
        cycles=1,
        read_addrs=result["read_addresses"],
    )
    ok(sim_result["status"] == "success", f"FB harness sim: {sim_result['status']}")
    # 5.0 * 2.0 = 10.0
    output_addr = om["Output"]["addr"]
    active_addr = om["Active"]["addr"]
    ok(approx(sim_result["results"][0]["memory_state"][output_addr], 10.0),
       f"Output should be 10.0, got {sim_result['results'][0]['memory_state'].get(output_addr)}")
    ok(sim_result["results"][0]["memory_state"][active_addr] == True,
       f"Active should be True")


@test("FC harness generation with typed output_map")
def test_fc_harness():
    fc_source = """FUNCTION FC 1 : VOID
VAR_INPUT
    A : INT;
    B : INT;
END_VAR
VAR_OUTPUT
    Sum : INT;
    IsPositive : BOOL;
END_VAR
BEGIN
    L #A;
    L #B;
    +I;
    T #Sum;
    L #Sum;
    L 0;
    >I;
    = #IsPositive;
END_FUNCTION"""

    result = generate_fc_harness(
        fc_source, block_number=1,
        test_inputs={"A": 10, "B": 20},
        read_outputs=["Sum", "IsPositive"],
    )

    om = result["output_map"]
    ok("Sum" in om and om["Sum"]["type"] == "INT", f"Sum type: {om.get('Sum')}")
    ok("IsPositive" in om and om["IsPositive"]["type"] == "BOOL", f"IsPositive type: {om.get('IsPositive')}")

    # Run it
    sim_result = run_simulation(
        sources=[result["source"]],
        cycles=1,
        read_addrs=result["read_addresses"],
    )
    ok(sim_result["status"] == "success", f"FC harness sim: {sim_result['status']}")
    sum_addr = om["Sum"]["addr"]
    pos_addr = om["IsPositive"]["addr"]
    ok(sim_result["results"][0]["memory_state"][sum_addr] == 30,
       f"Sum should be 30, got {sim_result['results'][0]['memory_state'].get(sum_addr)}")
    ok(sim_result["results"][0]["memory_state"][pos_addr] == True,
       f"IsPositive should be True")


@test("status word readback (OV flag)")
def test_status_word():
    source = """ORGANIZATION_BLOCK OB 1
BEGIN
    L 32767;
    T MW 0;
    L MW 0;
    L 1;
    +I;
    T MW 0;
END_ORGANIZATION_BLOCK"""
    result = run_simulation(
        sources=[source],
        cycles=1,
        read_addrs=["MW0"],
        read_stw=True,
    )
    ok(result["status"] == "success", f"Status word test: {result['status']}")
    stw = result["results"][0]["status_word"]
    ok(stw["OV"] == 1, f"OV should be 1 after overflow, got {stw['OV']}")
    ok(result["results"][0]["memory_state"]["MW0"] == -32768,
       f"MW0 should be -32768, got {result['results'][0]['memory_state']['MW0']}")


@test("DB access error handling")
def test_db_access_error():
    # Try to read from a DB that doesn't exist
    source = """ORGANIZATION_BLOCK OB 1
BEGIN
    SET;
    = Q 0.0;
END_ORGANIZATION_BLOCK"""
    result = run_simulation(
        sources=[source],
        cycles=1,
        read_addrs=["DB99.DBW0"],  # DB99 not declared
    )
    # The simulation should succeed (OB1 runs fine), but reading DB99 should error
    ok(result["status"] == "success", f"DB access test status: {result['status']}")
    db_val = result["results"][0]["memory_state"]["DB99.DBW0"]
    ok(isinstance(db_val, str) and "ERROR" in db_val,
       f"DB99.DBW0 should be an error string, got {db_val}")


@test("assertion layer: all pass")
def test_assertions_pass():
    source = """ORGANIZATION_BLOCK OB 1
BEGIN
    A I 0.0;
    A I 0.1;
    = Q 0.0;
END_ORGANIZATION_BLOCK"""
    result = run_simulation(
        sources=[source],
        cycles=2,
        set_before_cycle=[
            {"I0.0": True, "I0.1": True},
            {"I0.0": True, "I0.1": False},
        ],
        read_addrs=["Q0.0"],
        expect={"cycles": [
            {"read": {"Q0.0": True}},
            {"read": {"Q0.0": False}},
        ]},
    )
    ok(result["status"] == "success", f"Assertion pass test: {result['status']}")
    ok(result.get("test_result") == "pass", f"test_result should be 'pass', got {result.get('test_result')}")
    ok(len(result.get("assertions", [])) == 2, f"Should have 2 assertions")
    ok(all(a["pass"] for a in result["assertions"]), "All assertions should pass")


@test("assertion layer: failure detected")
def test_assertions_fail():
    source = """ORGANIZATION_BLOCK OB 1
BEGIN
    CLR;
    = Q 0.0;
END_ORGANIZATION_BLOCK"""
    result = run_simulation(
        sources=[source],
        cycles=1,
        read_addrs=["Q0.0"],
        expect={"cycles": [
            {"read": {"Q0.0": True}},  # Wrong! Q0.0 will be False
        ]},
    )
    ok(result["status"] == "success", f"Assertion fail test: {result['status']}")
    ok(result.get("test_result") == "fail", f"test_result should be 'fail', got {result.get('test_result')}")
    ok(len(result.get("assertions", [])) == 1, "Should have 1 assertion")
    ok(result["assertions"][0]["pass"] == False, "Assertion should fail")
    ok(result["assertions"][0]["expected"] == True, "Expected was True")
    ok(result["assertions"][0]["actual"] == False, "Actual was False")


@test("assertion layer: REAL with tolerance")
def test_assertions_real_tolerance():
    source = """ORGANIZATION_BLOCK OB 1
BEGIN
    L 1.000000e+000;
    L 3.000000e+000;
    /R;
    T MD 0;
END_ORGANIZATION_BLOCK"""
    # 1.0 / 3.0 = 0.333333... which can't be represented exactly
    result = run_simulation(
        sources=[source],
        cycles=1,
        read_addrs=[{"addr": "MD0", "type": "REAL"}],
        expect={"cycles": [
            {"read": {"MD0": 0.333333}},
        ]},
        tolerance=0.001,
    )
    ok(result["status"] == "success", f"REAL tolerance test: {result['status']}")
    ok(result.get("test_result") == "pass", f"Should pass with tolerance 0.001, got {result.get('test_result')}")
    ok("delta" in result["assertions"][0], "REAL assertion should include delta")


@test("db_layouts extraction from FB instance DB")
def test_db_layouts():
    source = """FUNCTION_BLOCK FB 5
VAR_INPUT
    Cmd : INT;
    Speed : REAL;
END_VAR
VAR_OUTPUT
    Status : INT;
END_VAR
BEGIN
    NOP 0;
END_FUNCTION_BLOCK

DATA_BLOCK DB 5
FB 5
BEGIN
END_DATA_BLOCK

ORGANIZATION_BLOCK OB 1
BEGIN
    CALL FB 5, DB 5;
END_ORGANIZATION_BLOCK"""
    result = run_simulation(sources=[source], cycles=1)
    ok(result["status"] == "success", f"db_layouts test: {result['status']}")
    layouts = result.get("db_layouts", {})
    ok("DB5" in layouts, f"DB5 should be in db_layouts, got keys: {list(layouts.keys())}")
    if "DB5" in layouts:
        fields = layouts["DB5"]
        names = [f["name"] for f in fields]
        ok("Cmd" in names, f"Cmd should be in DB5 fields, got {names}")
        ok("Speed" in names, f"Speed should be in DB5 fields, got {names}")
        ok("Status" in names, f"Status should be in DB5 fields, got {names}")
        # Check that Speed is typed as REAL
        speed_field = [f for f in fields if f["name"] == "Speed"][0]
        ok(speed_field["type"] == "REAL", f"Speed type should be REAL, got {speed_field['type']}")
        ok(speed_field["bits"] == 32, f"Speed bits should be 32, got {speed_field['bits']}")


@test("counter direct readback via C0")
def test_counter_readback():
    source = """ORGANIZATION_BLOCK OB 1
BEGIN
    L C#3;
    S C 0;
    A I 0.0;
    CU C 0;
END_ORGANIZATION_BLOCK"""
    result = run_simulation(
        sources=[source],
        cycles=2,
        set_before_cycle=[{"I0.0": True}, {"I0.0": False}],
        read_addrs=["C0"],
    )
    ok(result["status"] == "success", f"Counter readback: {result['status']}")
    c0_val = result["results"][0]["memory_state"]["C0"]
    ok(isinstance(c0_val, int), f"C0 should be int, got {type(c0_val)}: {c0_val}")
    # Counter should have a value (not an error string)
    ok(not isinstance(c0_val, str), f"C0 should not be an error: {c0_val}")


@test("timer direct readback via T0")
def test_timer_readback():
    source = """ORGANIZATION_BLOCK OB 1
BEGIN
    A I 0.0;
    L S5T#2S;
    SD T 0;
END_ORGANIZATION_BLOCK"""
    result = run_simulation(
        sources=[source],
        cycles=1,
        set_inputs={"I0.0": True},
        read_addrs=["T0"],
    )
    ok(result["status"] == "success", f"Timer readback: {result['status']}")
    t0_val = result["results"][0]["memory_state"]["T0"]
    ok(isinstance(t0_val, int), f"T0 should be int, got {type(t0_val)}: {t0_val}")
    ok(not isinstance(t0_val, str), f"T0 should not be an error: {t0_val}")


@test("FB harness with INOUT parameter")
def test_inout_harness():
    fb_source = """FUNCTION_BLOCK FB 2
VAR_INPUT
    Enable : BOOL;
END_VAR
VAR_OUTPUT
    Done : BOOL;
END_VAR
VAR_IN_OUT
    Counter : INT;
END_VAR
BEGIN
    A #Enable;
    JCN skip;
    L #Counter;
    L 1;
    +I;
    T #Counter;
    SET;
    = #Done;
    JU end;
skip: CLR;
    = #Done;
end: NOP 0;
END_FUNCTION_BLOCK"""

    result = generate_fb_harness(
        fb_source, block_number=2, instance_db_number=2,
        test_inputs={"Enable": True, "Counter": 10},
        read_outputs=["Done", "Counter"],
    )

    om = result["output_map"]
    ok("Counter" in om, f"output_map should contain Counter, got {list(om.keys())}")
    ok(om["Counter"]["type"] == "INT", f"Counter type should be INT, got {om['Counter']['type']}")
    ok("Done" in om, f"output_map should contain Done")

    # inout_init should provide the initial Counter value
    inout_init = result.get("inout_init", {})
    ok(len(inout_init) > 0, f"inout_init should have Counter init, got {inout_init}")
    counter_addr = om["Counter"]["addr"]
    ok(counter_addr in inout_init, f"inout_init should have {counter_addr}")
    ok(inout_init[counter_addr] == 10, f"Counter init should be 10, got {inout_init.get(counter_addr)}")

    # Run end-to-end: Counter should increment 10 -> 11 -> 12
    sim_result = run_simulation(
        sources=[result["source"]],
        cycles=2,
        set_db=inout_init,
        read_addrs=result["read_addresses"],
        expect={"cycles": [
            {"read": {om["Done"]["addr"]: True, counter_addr: 11}},
            {"read": {om["Done"]["addr"]: True, counter_addr: 12}},
        ]},
    )
    ok(sim_result["status"] == "success", f"INOUT sim: {sim_result['status']}")
    ok(sim_result.get("test_result") == "pass",
       f"INOUT assertions should pass, got {sim_result.get('test_result')}")


@test("--format table output")
def test_format_table():
    from awlsim_runner import format_table
    result = run_simulation(
        sources=["ORGANIZATION_BLOCK OB 1\nBEGIN\n    A I 0.0; = Q 0.0;\nEND_ORGANIZATION_BLOCK"],
        cycles=2,
        set_before_cycle=[{"I0.0": True}, {"I0.0": False}],
        read_addrs=["Q0.0"],
        expect={"cycles": [
            {"read": {"Q0.0": True}},
            {"read": {"Q0.0": False}},
        ]},
    )
    ok(result["status"] == "success", f"table test sim: {result['status']}")
    table = format_table(result)
    ok("Cycle" in table, "Table should have Cycle header")
    ok("Q0.0" in table, "Table should have Q0.0 column")
    ok("PASS" in table, "Table should show PASS")
    ok("FAIL" not in table, "Table should not show FAIL")


@test("test scenario runner")
def test_scenario_runner():
    import tempfile, os
    from awlsim_runner import run_test_scenario

    scenario = {
        "name": "wrapper test scenario",
        "tests": [
            {
                "name": "pass_case",
                "cycles": 1,
                "set_before_cycle": [{"I0.0": True, "I0.1": True}],
                "read": ["Q0.0"],
                "expect": {"cycles": [{"read": {"Q0.0": True}}]}
            },
            {
                "name": "fail_case",
                "cycles": 1,
                "set_before_cycle": [{"I0.0": False}],
                "read": ["Q0.0"],
                "expect": {"cycles": [{"read": {"Q0.0": True}}]}
            },
        ],
    }

    # Write scenario to temp file
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(scenario, f)

        source = "ORGANIZATION_BLOCK OB 1\nBEGIN\n    A I 0.0; A I 0.1; = Q 0.0;\nEND_ORGANIZATION_BLOCK"
        summary = run_test_scenario(path, [source])

        ok(summary["total"] == 2, f"Should have 2 tests, got {summary['total']}")
        ok(summary["passed"] == 1, f"Should have 1 passed, got {summary['passed']}")
        ok(summary["failed"] == 1, f"Should have 1 failed, got {summary['failed']}")
        ok(summary["overall"] == "FAIL", f"Overall should be FAIL, got {summary['overall']}")
        ok(summary["tests"][0]["test_result"] == "pass", "First test should pass")
        ok(summary["tests"][1]["test_result"] == "fail", "Second test should fail")
    finally:
        os.unlink(path)


@test("version string exists")
def test_version():
    ok(__version__ == "1.2.0", f"Version should be 1.2.0, got {__version__}")


# ============================================================
# Runner
# ============================================================

SMOKE_TESTS = {
    "compile success: trivial OB1",
    "BOOL store/fetch roundtrip via simulation",
    "REAL read/write roundtrip via simulation",
}


def run_all(smoke=False):
    global _pass_count, _fail_count

    print(f"awlsim-runner wrapper test suite v{__version__}")
    tests = [(name, fn) for name, fn in _test_names if (not smoke or name in SMOKE_TESTS)]
    print(f"Running {len(tests)} tests{' (smoke)' if smoke else ''}...\n")

    for name, fn in tests:
        before_fail = _fail_count
        try:
            fn()
            status = "PASS" if _fail_count == before_fail else "FAIL"
        except Exception as e:
            _fail_count += 1
            status = "ERROR"
            print(f"    ERROR: {type(e).__name__}: {e}")

        icon = "[OK]" if status == "PASS" else "[FAIL]"
        print(f"  {icon} {name} [{status}]")

    print(f"\n{'='*50}")
    total = _pass_count + _fail_count
    print(f"Results: {_pass_count}/{total} checks passed, {_fail_count} failed")

    if _fail_count == 0:
        print("All tests PASSED")
        return 0
    else:
        print(f"{_fail_count} check(s) FAILED")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true",
                        help="Run only compile, BOOL roundtrip, and REAL roundtrip checks")
    args = parser.parse_args()
    sys.exit(run_all(smoke=args.smoke))
