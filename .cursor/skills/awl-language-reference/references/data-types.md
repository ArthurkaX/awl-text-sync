# Data Types — STEP 7 STL/AWL

---

## Elementary Data Types

| Type | Size | Range | Default | Example |
|------|------|-------|---------|---------|
| `BOOL` | 1 bit | TRUE / FALSE | FALSE | `A #Flag` |
| `BYTE` | 8 bit | 0 – 255 | 0 | `L B#16#FF` |
| `WORD` | 16 bit | 0 – 65535 | 0 | `L W#16#0001` |
| `DWORD` | 32 bit | 0 – 4294967295 | 0 | `L DW#16#FFFFFFFF` |
| `INT` | 16 bit | −32768 – +32767 | 0 | `L 100` |
| `DINT` | 32 bit | −2,147,483,648 – +2,147,483,647 | 0 | `L L#100000` |
| `REAL` | 32 bit IEEE 754 | ±1.175494E-38 – ±3.402823E+38 (normalized); denormalized down to ±1.401298E-45 | 0.0 | `L 5.000000e+000` |
| `TIME` | 32 bit | T#-24D_20H_31M_23S_648MS – T#+24D... | T#0MS | `L T#10S` |
| `DATE` | 16 bit | D#1990-1-1 – D#2168-12-31 | D#1990-1-1 | |
| `TIME_OF_DAY` | 32 bit | TOD#0:0:0 – TOD#23:59:59.999 | TOD#0:0:0 | |
| `S5TIME` | 16 bit | S5T#0MS – S5T#9990S | S5T#0MS | `L S5T#10S` |
| `CHAR` | 8 bit | ASCII character | ' ' | `L 'A'` |

### REAL Constant Format
Project convention: **always use scientific notation with 6 decimal places**:
```
5.000000e+000   = 5.0
1.000000e+002   = 100.0
8.500000e+001   = 85.0
-2.500000e+001  = -25.0
5.000000e-002   = 0.05
```

---

## Complex Data Types

### STRING
```awl
VariableName : STRING[20];     // Max 20 characters
```
- Stored as length byte + characters
- Not directly accessible in STL (use SFC/SFB string functions)

### DATE_AND_TIME (DT)
```awl
VariableName : DATE_AND_TIME;  // 8 bytes BCD encoded
```

### ARRAY
```awl
// Declaration in VAR section:
ArrayName : ARRAY [1..10] OF REAL;      // Single dimension
Matrix    : ARRAY [1..4, 1..4] OF INT;  // Two dimensions
PulseBits : ARRAY [1..32] OF BOOL;      // Boolean array (project standard)

// Access in STL:
L     #ArrayName[1];                    // Load first element
T     #ArrayName[5];                    // Transfer to fifth element
FP    #PulseBits[3];                    // Edge detect on element 3
```

**Index rules:**
- Indices are 1-based by project convention (can start at any INT)
- Index must be a constant in standard STL — use indirect addressing for variable index

### STRUCT
```awl
// Declaration:
StructName : STRUCT
  Member1 : REAL;
  Member2 : BOOL;
  Nested  : STRUCT
    SubMember : INT;
  END_STRUCT;
END_STRUCT;

// Access in STL:
L     #StructName.Member1;
A     #StructName.Member2;
L     #StructName.Nested.SubMember;
```

**Project STRUCT conventions:**
```awl
VAR
  SCADA : STRUCT         // HMI interface layer
    AutoMode_PB : BOOL;
    Setpoint1   : REAL;
  END_STRUCT;
  Control : STRUCT       // Internal logic state
    AutoMode    : BOOL;
    ManualMode  : BOOL;
  END_STRUCT;
  Interlocks : STRUCT    // Safety conditions
    LevelHigh   : BOOL;
  END_STRUCT;
  Faults : STRUCT        // Alarm tracking
    GeneralFault : BOOL;
  END_STRUCT;
END_VAR
```

---

## User-Defined Types (UDT)

```awl
// Definition (separate TYPE block):
TYPE "MyUDT"
VERSION : 0.1
STRUCT
  Value1 : REAL;
  Status : STRUCT
    Running : BOOL;
    Fault   : BOOL;
  END_STRUCT;
END_STRUCT
END_TYPE

// Usage in FB VAR:
VAR
  DeviceA : "MyUDT";               // Single instance
  DeviceB : "MyUDT";               // Second instance
  Devices : ARRAY [1..5] OF "MyUDT"; // Array of UDT
END_VAR

// Access:
L     #DeviceA.Value1;
A     #DeviceA.Status.Running;
L     #Devices[1].Value1;
```

**Project UDTs in use:**
- `"MCC_DOL_Control"` — Direct-on-line motor control interface
- `"T20_CrystSptRamp"` — Crystalliser setpoint ramp FB
- `"TON"` — IEC on-delay timer (multi-instance)
- `"MCC_VSD_Control"` — Variable speed drive control

---

## VAR Section Types

| Section | Scope | Persistence | Block |
|---------|-------|-------------|-------|
| `VAR_INPUT` | Caller-supplied params | Per call | FB, FC |
| `VAR_OUTPUT` | Returned to caller | Per call | FB, FC |
| `VAR_IN_OUT` | Bidirectional | Per call | FB, FC |
| `VAR` | Static local | Persistent in Instance DB | FB only |
| `VAR_TEMP` | Temporary local | Lost after block ends | All |

**Critical distinction:**
- `VAR` data survives between scan cycles (stored in Instance DB)
- `VAR_TEMP` data is undefined at the start of every block call — **must initialise before use**

---

## Data Block Declarations

### Global DB
```awl
DATA_BLOCK "DB_Name"
STRUCT
  Field1 : REAL;
  Field2 : INT;
  SubStruct : STRUCT
    Bit1 : BOOL;
  END_STRUCT;
END_STRUCT
BEGIN
  Field1 := 0.000000e+000;
  Field2 := 0;
END_DATA_BLOCK
```

### Instance DB (references FB)
```awl
DATA_BLOCK "DB_InstanceName"
"FB_Name"              // References FB — inherits VAR structure
BEGIN
  // Optional initial value overrides
  SCADA.Setpoint1 := 5.000000e+001;
END_DATA_BLOCK
```

---

## Type Compatibility Notes

| Operation | Type Required | Common Issue |
|-----------|--------------|--------------|
| `+R`, `-R`, `*R`, `/R` | REAL | INT must be converted first: `ITD` then `DTR` |
| `RND` / `RND+` / `RND-` / `TRUNC` | Input must be REAL in ACCU1; result is DINT. Check OV after conversion in case value is out of DINT range |
| `SD`, `SE`, `SF`, `SS`, `SP` | S5TIME | Must load with `L S5T#...` before timer |
| `CU`, `CD` | Counter | Must load `C#n` preset before `S C n` |
| Comparison `>R` | Both REAL | Load both operands before compare |
| Array index | INT constant | Variable index needs indirect addressing |
