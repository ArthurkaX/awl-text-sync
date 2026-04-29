#!/usr/bin/env python3
"""
test_harness_generator.py - Auto-generate OB1 test harnesses for FBs and FCs.

When a user wants to test an FB or FC that can't run standalone (it needs to be
CALLed from an OB), this script:
1. Pre-compiles the block to discover its interface (IN/OUT/INOUT/STAT)
2. Inspects the resulting instance DB layout for exact byte offsets
3. Generates a minimal OB1 that CALLs the block with user-specified inputs
4. Maps output parameters to readable memory (M area) for the runner to read

The output_map now includes both address and datatype for each parameter,
enabling the runner to decode REAL values correctly (instead of returning
raw integer bits).

Usage:
    python3 test_harness_generator.py \
        --block-source "AWL source for FB/FC" \
        --block-type FB \
        --block-number 1 \
        --instance-db 1 \
        --test-inputs '{"Start": true, "Speed": 1500}' \
        --read-outputs '["Running", "Fault"]'

Output: Complete AWL source (OB1 + original block + DB) ready for awlsim_runner.py
"""

import sys
import os
import json
import argparse

__version__ = "1.1.0"

AWLSIM_DIR = os.environ.get("AWLSIM_DIR", "/home/claude/awlsim")
if AWLSIM_DIR not in sys.path:
    sys.path.insert(0, AWLSIM_DIR)

from awlsim.core.main import AwlSim
from awlsim.awlcompiler import AwlParser
from awlsim.core.blockinterface import BlockInterfaceField
from awlsim.common import AwlSimError, S7CPUConfig


# Data type to AWL width mapping for readback
TYPE_INFO = {
    "BOOL":   {"width": 1,  "awl_load": "A", "awl_assign": "=", "q_bits": 1,  "s7_type": "BOOL"},
    "BYTE":   {"width": 8,  "awl_load": "L", "awl_assign": "T", "q_bits": 8,  "s7_type": "BYTE"},
    "INT":    {"width": 16, "awl_load": "L", "awl_assign": "T", "q_bits": 16, "s7_type": "INT"},
    "WORD":   {"width": 16, "awl_load": "L", "awl_assign": "T", "q_bits": 16, "s7_type": "WORD"},
    "DINT":   {"width": 32, "awl_load": "L", "awl_assign": "T", "q_bits": 32, "s7_type": "DINT"},
    "DWORD":  {"width": 32, "awl_load": "L", "awl_assign": "T", "q_bits": 32, "s7_type": "DWORD"},
    "REAL":   {"width": 32, "awl_load": "L", "awl_assign": "T", "q_bits": 32, "s7_type": "REAL"},
    "TIME":   {"width": 32, "awl_load": "L", "awl_assign": "T", "q_bits": 32, "s7_type": "TIME"},
    "S5TIME": {"width": 16, "awl_load": "L", "awl_assign": "T", "q_bits": 16, "s7_type": "S5TIME"},
}


def introspect_fb(block_source, block_number, instance_db_number, mnemonics="EN"):
    """
    Pre-compile an FB to discover its interface and DB layout.

    Returns:
        dict with 'inputs', 'outputs', 'inouts', 'statics', 'db_layout'
        Each field has: name, dataType, db_byte, db_bit, bitSize
    """
    # Build a minimal program to compile the FB and its instance DB
    dummy_source = block_source + f"""

DATA_BLOCK DB {instance_db_number}
FB {block_number}
BEGIN
END_DATA_BLOCK

ORGANIZATION_BLOCK OB 1
BEGIN
    CALL FB {block_number}, DB {instance_db_number};
END_ORGANIZATION_BLOCK
"""

    sim = AwlSim()
    cpu = sim.getCPU()
    conf = cpu.getConf()
    mnem_map = {"EN": S7CPUConfig.MNEMONICS_EN, "DE": S7CPUConfig.MNEMONICS_DE,
                "AUTO": S7CPUConfig.MNEMONICS_AUTO}
    conf.setConfiguredMnemonics(mnem_map.get(mnemonics.upper(), S7CPUConfig.MNEMONICS_AUTO))

    parser = AwlParser()
    parser.parseText(dummy_source)
    sim.load(parser.getParseTree())
    sim.build()
    sim.startup()
    cpu = sim.getCPU()

    fb = cpu.getFB(block_number)
    iface = fb.interface

    # Build DB field map: name -> {byte, bit, bitSize, type}
    db = cpu.getDB(instance_db_number)
    db_map = {}
    for field in db.struct.fields:
        if field.name:
            db_map[field.name] = {
                "byte": field.offset.byteOffset,
                "bit": field.offset.bitOffset,
                "bitSize": field.bitSize,
                "type": str(field.dataType) if field.dataType else "BYTE",
            }

    result = {"inputs": [], "outputs": [], "inouts": [], "statics": [], "db_size": db.struct.getSize()}

    area_map = [
        ("inputs", iface.fields_IN),
        ("outputs", iface.fields_OUT),
        ("inouts", iface.fields_INOUT),
        ("statics", iface.fields_STAT),
    ]

    for area_name, field_list in area_map:
        for f in field_list:
            entry = {
                "name": f.name,
                "dataType": str(f.dataType),
            }
            if f.name in db_map:
                entry.update(db_map[f.name])
            result[area_name].append(entry)

    sim.shutdown()
    return result


def introspect_fc(block_source, block_number, mnemonics="EN"):
    """
    Pre-compile an FC to discover its interface.
    FCs don't have instance DBs, so we only get parameter names and types.

    We compile the FC source with a no-op OB1 (no CALL) to avoid the
    parameter-mismatch error that awlsim raises for bare CALL FC without args.
    The FC block is still parsed and built, so we can inspect its interface.
    """
    dummy_source = block_source + f"""

ORGANIZATION_BLOCK OB 1
BEGIN
    SET;
END_ORGANIZATION_BLOCK
"""

    sim = AwlSim()
    cpu = sim.getCPU()
    conf = cpu.getConf()
    mnem_map = {"EN": S7CPUConfig.MNEMONICS_EN, "DE": S7CPUConfig.MNEMONICS_DE,
                "AUTO": S7CPUConfig.MNEMONICS_AUTO}
    conf.setConfiguredMnemonics(mnem_map.get(mnemonics.upper(), S7CPUConfig.MNEMONICS_AUTO))

    parser = AwlParser()
    parser.parseText(dummy_source)
    sim.load(parser.getParseTree())
    sim.build()
    sim.startup()
    cpu = sim.getCPU()

    fc = cpu.getFC(block_number)
    iface = fc.interface

    result = {"inputs": [], "outputs": [], "inouts": []}
    area_map = [
        ("inputs", iface.fields_IN),
        ("outputs", iface.fields_OUT),
        ("inouts", iface.fields_INOUT),
    ]

    for area_name, field_list in area_map:
        for f in field_list:
            result[area_name].append({
                "name": f.name,
                "dataType": str(f.dataType),
            })

    sim.shutdown()
    return result


def format_awl_value(value, data_type):
    """Format a Python value as an AWL literal for the given data type."""
    dt = data_type.upper()
    if dt == "BOOL":
        return "TRUE" if value else "FALSE"
    elif dt == "INT":
        return str(int(value))
    elif dt == "WORD":
        return f"W#16#{int(value):04X}"
    elif dt == "DINT":
        return f"L#{int(value)}"
    elif dt == "DWORD":
        return f"DW#16#{int(value):08X}"
    elif dt == "REAL":
        # AWL real literal
        return f"{float(value):.6e}"
    elif dt in ("TIME", "S5TIME"):
        return str(value)  # Expect user to provide AWL-formatted time string
    else:
        return str(value)


def generate_fb_harness(block_source, block_number, instance_db_number,
                        test_inputs, read_outputs, mnemonics="EN"):
    """
    Generate a complete AWL test harness for an FB.

    Returns:
        dict with:
            - 'source': complete AWL source ready for awlsim_runner.py
            - 'output_map': mapping of output param names to {addr, type} for typed readback
            - 'read_addresses': list of typed read specs for --read argument
            - 'interface': the introspected interface info
    """
    # Introspect to get the interface
    interface_info = introspect_fb(block_source, block_number, instance_db_number, mnemonics)

    # Build CALL parameter assignments
    call_params = []
    for inp in interface_info["inputs"]:
        name = inp["name"]
        if name in test_inputs:
            dt = inp["dataType"].upper()
            call_params.append(f"        {name} := {format_awl_value(test_inputs[name], dt)}")

    # INOUT params require memory addresses (not literals) in the CALL.
    # We allocate M-area addresses for INOUTs and pass the M-area address
    # in the CALL. Initial values are returned in 'inout_init' dict for
    # the runner's --set-db to apply once before cycle 1.
    inout_addr_map = {}    # inout_name -> {"m_addr": str, "type": str}
    m_inout_offset = 50    # Start INOUT M-area at MB50 (below MB100 used for readback)

    for inout in interface_info["inouts"]:
        name = inout["name"]
        dt = inout["dataType"].upper()
        type_info = TYPE_INFO.get(dt, TYPE_INFO["INT"])

        if dt == "BOOL":
            m_addr = f"M {m_inout_offset}.0"
            m_read_addr = f"M{m_inout_offset}.0"
            call_params.append(f"        {name} := {m_addr}")
            inout_addr_map[name] = {"m_addr": m_read_addr, "type": "BOOL"}
            m_inout_offset += 1
        elif type_info["q_bits"] <= 16:
            m_addr = f"MW {m_inout_offset}"
            m_read_addr = f"MW{m_inout_offset}"
            call_params.append(f"        {name} := {m_addr}")
            inout_addr_map[name] = {"m_addr": m_read_addr, "type": dt}
            m_inout_offset += 2
        else:
            m_addr = f"MD {m_inout_offset}"
            m_read_addr = f"MD{m_inout_offset}"
            call_params.append(f"        {name} := {m_addr}")
            inout_addr_map[name] = {"m_addr": m_read_addr, "type": dt}
            m_inout_offset += 4

    # Build output readback: copy from DB to M-area for easy reading
    readback_code = []
    output_map = {}  # param_name -> {"addr": str, "type": str}
    m_byte_offset = 100  # Start at MB100 to avoid collisions

    if read_outputs is None:
        # Auto-include all outputs AND all inouts for readback
        read_outputs = [o["name"] for o in interface_info["outputs"]]
        read_outputs += [io["name"] for io in interface_info["inouts"]]

    # Readback for VAR_OUTPUT fields
    for out in interface_info["outputs"]:
        name = out["name"]
        if name not in read_outputs:
            continue

        dt = out["dataType"].upper()
        db_byte = out.get("byte", 0)
        db_bit = out.get("bit", 0)
        type_info = TYPE_INFO.get(dt, TYPE_INFO["INT"])

        if dt == "BOOL":
            readback_code.append(f"    A   DB{instance_db_number}.DBX {db_byte}.{db_bit};")
            readback_code.append(f"    =   M {m_byte_offset}.0;")
            output_map[name] = {"addr": f"M{m_byte_offset}.0", "type": "BOOL"}
            m_byte_offset += 1
        elif type_info["q_bits"] <= 16:
            readback_code.append(f"    L   DB{instance_db_number}.DBW {db_byte};")
            readback_code.append(f"    T   MW {m_byte_offset};")
            output_map[name] = {"addr": f"MW{m_byte_offset}", "type": dt}
            m_byte_offset += 2
        else:
            readback_code.append(f"    L   DB{instance_db_number}.DBD {db_byte};")
            readback_code.append(f"    T   MD {m_byte_offset};")
            output_map[name] = {"addr": f"MD{m_byte_offset}", "type": dt}
            m_byte_offset += 4

    # Readback for VAR_IN_OUT fields — these already live in M-area from the
    # INOUT address allocation above, so no DB-to-M copy is needed. Just add
    # them to the output_map.
    for inout in interface_info["inouts"]:
        name = inout["name"]
        if name not in read_outputs:
            continue
        if name in inout_addr_map:
            output_map[name] = {"addr": inout_addr_map[name]["m_addr"],
                                "type": inout_addr_map[name]["type"]}

    # Assemble the OB1
    call_param_str = ",\n".join(call_params)
    if call_param_str:
        call_param_str = " (\n" + call_param_str + "\n    )"

    readback_str = "\n".join(readback_code)

    ob1 = f"""
ORGANIZATION_BLOCK OB 1
BEGIN
    CALL FB {block_number}, DB {instance_db_number}{call_param_str};

    // === Auto-generated output readback ===
{readback_str}
END_ORGANIZATION_BLOCK
"""

    # Build complete source
    db_decl = f"""
DATA_BLOCK DB {instance_db_number}
FB {block_number}
BEGIN
END_DATA_BLOCK
"""

    complete_source = block_source + "\n" + db_decl + "\n" + ob1

    # Build typed read_addresses list for the runner's --read argument
    read_addresses = [spec for spec in output_map.values()]

    # Build set_db dict for INOUT initial values (applied once before first cycle)
    inout_init = {}
    for name, info in inout_addr_map.items():
        if name in test_inputs:
            inout_init[info["m_addr"]] = test_inputs[name]

    return {
        "source": complete_source,
        "output_map": output_map,
        "interface": interface_info,
        "read_addresses": read_addresses,
        "inout_init": inout_init,
    }


def generate_fc_harness(block_source, block_number, test_inputs, read_outputs, mnemonics="EN"):
    """
    Generate a complete AWL test harness for an FC.

    FCs are stateless, so we pass inputs directly and capture outputs to M-area.
    """
    interface_info = introspect_fc(block_source, block_number, mnemonics)

    call_params = []
    for inp in interface_info["inputs"]:
        name = inp["name"]
        if name in test_inputs:
            dt = inp["dataType"].upper()
            call_params.append(f"        {name} := {format_awl_value(test_inputs[name], dt)}")

    # For FC outputs, we need temp variables or M-area addresses
    output_map = {}
    m_byte_offset = 100
    output_params = []

    if read_outputs is None:
        read_outputs = [o["name"] for o in interface_info["outputs"]]

    for out in interface_info["outputs"]:
        name = out["name"]
        if name not in read_outputs:
            continue
        dt = out["dataType"].upper()
        type_info = TYPE_INFO.get(dt, TYPE_INFO["INT"])

        if dt == "BOOL":
            output_params.append(f"        {name} := M {m_byte_offset}.0")
            output_map[name] = {"addr": f"M{m_byte_offset}.0", "type": "BOOL"}
            m_byte_offset += 1
        elif type_info["q_bits"] <= 16:
            output_params.append(f"        {name} := MW {m_byte_offset}")
            output_map[name] = {"addr": f"MW{m_byte_offset}", "type": dt}
            m_byte_offset += 2
        else:
            output_params.append(f"        {name} := MD {m_byte_offset}")
            output_map[name] = {"addr": f"MD{m_byte_offset}", "type": dt}
            m_byte_offset += 4

    all_params = call_params + output_params
    call_param_str = ",\n".join(all_params)
    if call_param_str:
        call_param_str = " (\n" + call_param_str + "\n    )"

    ob1 = f"""
ORGANIZATION_BLOCK OB 1
BEGIN
    CALL FC {block_number}{call_param_str};
END_ORGANIZATION_BLOCK
"""

    complete_source = block_source + "\n" + ob1

    # Build typed read_addresses list
    read_addresses = [spec for spec in output_map.values()]

    return {
        "source": complete_source,
        "output_map": output_map,
        "interface": interface_info,
        "read_addresses": read_addresses,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate OB1 test harness for FB/FC")

    parser.add_argument("--version", action="version", version=f"test_harness_generator {__version__}")
    parser.add_argument("--block-source", type=str, help="Inline AWL source for the FB/FC")
    parser.add_argument("--block-source-file", type=str, help="Path to .awl file for the block")
    parser.add_argument("--block-type", type=str, required=True, choices=["FB", "FC"])
    parser.add_argument("--block-number", type=int, required=True)
    parser.add_argument("--instance-db", type=int, default=None, help="Instance DB number (FB only)")
    parser.add_argument("--test-inputs", type=str, default="{}", help='JSON: {"Start": true}')
    parser.add_argument("--read-outputs", type=str, default=None, help='JSON array: ["Running"]')
    parser.add_argument("--mnemonics", type=str, default="EN", choices=["EN", "DE", "AUTO"])
    parser.add_argument("--output-source", action="store_true", help="Print just the AWL source")

    args = parser.parse_args()

    # Get block source
    if args.block_source:
        block_source = args.block_source
    elif args.block_source_file:
        with open(args.block_source_file, "r") as f:
            block_source = f.read()
    else:
        print("Error: provide --block-source or --block-source-file", file=sys.stderr)
        sys.exit(1)

    test_inputs = json.loads(args.test_inputs)
    read_outputs = json.loads(args.read_outputs) if args.read_outputs else None

    try:
        if args.block_type == "FB":
            db_num = args.instance_db or (args.block_number + 100)
            result = generate_fb_harness(
                block_source, args.block_number, db_num,
                test_inputs, read_outputs, args.mnemonics
            )
        else:
            result = generate_fc_harness(
                block_source, args.block_number,
                test_inputs, read_outputs, args.mnemonics
            )

        if args.output_source:
            print(result["source"])
        else:
            print(json.dumps(result, indent=2))

    except AwlSimError as e:
        print(json.dumps({"error": str(e).strip()}, indent=2))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {str(e)}"}), indent=2)
        sys.exit(1)


if __name__ == "__main__":
    main()
