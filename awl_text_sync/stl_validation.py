from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

from .parser import ParseError

DECL_SECTION_HEADERS = {"VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT"}
STRUCTURAL_BODY_LINES = {"NETWORK", "TITLE", "TITLE =", "BEGIN"}
BLOCK_END_LINES = {"END_FUNCTION", "END_FUNCTION_BLOCK", "END_ORGANIZATION_BLOCK"}
SCALAR_TYPES = {
    "BOOL",
    "BYTE",
    "CHAR",
    "WORD",
    "DWORD",
    "SINT",
    "USINT",
    "INT",
    "UINT",
    "DINT",
    "UDINT",
    "REAL",
    "LREAL",
    "TIME",
    "DATE",
    "TOD",
    "DT",
    "STRING",
    "WSTRING",
    "ANY",
    "POINTER",
    "BLOCK_DB",
}
STRUCTURAL_DECLARATION_KEYWORDS = {"STRUCT", "END_STRUCT", "ARRAY", "END_ARRAY"}

SECTION_HEADER_PATTERN = re.compile(r"^(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR|VAR_TEMP|END_VAR|BEGIN)$", re.IGNORECASE)
DECLARATION_PATTERN = re.compile(
    r"^(?P<names>[A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*)\s*:\s*(?P<type>.+?)\s*;\s*$",
    re.IGNORECASE,
)
STRUCT_DECLARATION_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<type>STRUCT|ARRAY\b.*)$",
    re.IGNORECASE,
)
ARRAY_DECLARATION_START_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*ARRAY\b.*\bOF\s*$",
    re.IGNORECASE,
)
BLOCK_INSTANCE_DECL_PATTERN = re.compile(
    r'^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?:(?P<kind>FB|FC|OB|SFB|SFC)\s+(?P<number>\d+)|"(?P<quoted_name>[^"]+)")\s*;\s*$',
    re.IGNORECASE,
)
CALL_START_PATTERN = re.compile(r"^(?:(?P<label>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*)?CALL\b", re.IGNORECASE)
CALL_HEADER_PATTERN = re.compile(
    r"^(?:(?P<label>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*)?CALL\s+(?P<target>(?:SFB|SFC|FB|FC|OB)\s+\d+|#?[A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\")(?P<tail>.*)$",
    re.IGNORECASE,
)
CALL_INSTANCE_PATTERN = re.compile(r"^\s*,\s*(?P<kind>DB|DI)\s+(?P<number>\d+)\b", re.IGNORECASE)
CALL_INSTANCE_QUOTED_PATTERN = re.compile(r'^\s*,\s*"(?P<name>[^"]+)"\s*', re.IGNORECASE)
BLOCK_TYPE_PATTERN = re.compile(r"^(?P<kind>FB|FC|OB|SFB|SFC)\s+(?P<number>\d+)$", re.IGNORECASE)
QUOTED_BLOCK_PATTERN = re.compile(r'^"(?P<name>[^"]+)"$')
LOCAL_INSTANCE_PATTERN = re.compile(r"^#(?P<name>[A-Za-z_][A-Za-z0-9_]*)$")
CALL_POINTER_LITERAL_PATTERN = re.compile(
    r'^P#(?P<target>(?:'
    r'DB\d+\.\s*DB[XBWD]\s*\d+(?:\.\d+)?'
    r'|DB[XBWD]\s*\d+\.\d+'
    r'|[A-Z]{1,3}\s*\d+\.\d+'
    r'|\d+\.\d+'
    r'|P\s+0\.0'
    r'|0\.0'
    r'|##[A-Za-z_][A-Za-z0-9_]*'
    r'|#[A-Za-z_][A-Za-z0-9_]*'
    r'))(?:\s+(?P<data_type>BIT|BYTE|WORD|DWORD)\s+(?P<count>\d+))?$',
    re.IGNORECASE,
)
CALL_PARAM_PATTERN = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:=")
SIMPLE_REFERENCE_PATTERN = re.compile(r"^#?(?P<name>[A-Za-z_][A-Za-z0-9_]*)$")
DIRECT_BIT_OPERAND_PATTERN = re.compile(
    r"^(?:(?:DBX|DIX|M|E|A|Q|L)\s*(?:\[\s*AR\d+\s*,\s*P#\d+\.\d+\s*\]|\d+\.\d+|\"[^\"]+\"(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?)?)|DBX\s+\d+\.\d+|DIX\s+\d+\.\d+|M\s+\d+\.\d+|E\s+\d+\.\d+|A\s+\d+\.\d+|Q\s+\d+\.\d+|L\s+\d+\.\d+)$",
    re.IGNORECASE,
)
DIRECT_ADDRESS_PATTERN = re.compile(
    r"^(?:DB\d+\.\s*(?:DB[XBWD]\s*\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*)|(?:DB[XBWD]|[IQMP])\s*\d+(?:\.\d+)?|L\s*\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)
DB_SYMBOLIC_REFERENCE_PATTERN = re.compile(
    r"^DB\d+\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$",
    re.IGNORECASE,
)
SIMPLE_OPCODE_BIT_OPERAND_REQUIRED = {
    "A",
    "AN",
    "ON",
    "X",
    "XN",
    "S",
    "R",
    "FP",
    "FN",
    "=",
}
SIMPLE_OPCODE_BIT_OPERAND_OPTIONAL = {"O"}
SIMPLE_OPCODE_DISALLOW_BIT_OPERAND = {"L", "T"}
SIMPLE_OPCODE_NO_OPERAND = {"SET", "CLR", "NOT", "CDB", "BE", "BEC"}
SIMPLE_OPCODE_NUMERIC_OPERAND = {"NOP"}
INTEGER_TYPES = {
    "BYTE",
    "CHAR",
    "WORD",
    "DWORD",
    "SINT",
    "USINT",
    "INT",
    "UINT",
    "DINT",
    "UDINT",
    "REAL",
    "LREAL",
    "TIME",
    "DATE",
    "TOD",
    "DT",
}
BIT_OPERAND_CATEGORIES = {"bit"}
NON_BIT_OPERAND_CATEGORIES = {"numeric", "pointer"}


@dataclass(frozen=True)
class BlockDeclarationIndex:
    interface_parameters: frozenset[str]
    interface_types: dict[str, str]
    local_block_instances: dict[str, tuple[str, int | None]]
    local_variable_types: dict[str, str]


@dataclass(frozen=True)
class CallStatement:
    line_number: int
    statement: str
    line_numbers: tuple[int, ...]


@dataclass(frozen=True)
class CallInstanceReference:
    quoted_name: str | None
    kind: str | None
    number: int | None
    span_end: int


@dataclass(frozen=True)
class ResolvedCallTarget:
    kind: str
    name: str | None
    number: int | None
    source: str


@dataclass(frozen=True)
class SimpleStatement:
    line_number: int
    label: str | None
    opcode: str
    operand_text: str
    raw_text: str
    has_statement_terminator: bool


def is_valid_pointer_literal(expression: str) -> bool:
    return bool(CALL_POINTER_LITERAL_PATTERN.fullmatch(expression.strip()))


def is_obvious_direct_address(expression: str) -> bool:
    return bool(DIRECT_ADDRESS_PATTERN.fullmatch(expression.strip()))


def is_db_symbolic_reference(expression: str) -> bool:
    return bool(DB_SYMBOLIC_REFERENCE_PATTERN.fullmatch(expression.strip()))


def _iter_block_header_lines(source: str) -> list[str]:
    header_lines: list[str] = []
    for raw_line in source.splitlines():
        code_part = raw_line.split("//", 1)[0].strip()
        if not code_part:
            continue
        if code_part == "BEGIN":
            break
        header_lines.append(code_part)
    return header_lines


def _iter_block_header_lines_with_numbers(source: str) -> list[tuple[int, str]]:
    header_lines: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(source.splitlines(), 1):
        code_part = raw_line.split("//", 1)[0].strip()
        if not code_part:
            continue
        if code_part == "BEGIN":
            break
        header_lines.append((line_number, code_part))
    return header_lines


def _iter_block_body_lines(source: str) -> list[tuple[int, str]]:
    in_body = False
    body_lines: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(source.splitlines(), 1):
        if not in_body:
            if raw_line.strip() == "BEGIN":
                in_body = True
            continue
        code_part = raw_line.split("//", 1)[0].strip()
        if code_part:
            body_lines.append((line_number, code_part))
    return body_lines


def _normalize_declared_type(type_text: str) -> str | None:
    cleaned = type_text.strip().upper()
    if not cleaned:
        return None
    if cleaned.startswith('"') and cleaned.endswith('"'):
        return None
    if re.fullmatch(r"(?:FB|FC|OB|SFB|SFC)\s+\d+", cleaned):
        return None
    match = re.fullmatch(r"(?P<base>[A-Z_][A-Z0-9_]*)(?:\s*\[\s*\d+\s*\])?", cleaned)
    if not match:
        if cleaned in {"STRUCT", "ARRAY"}:
            return cleaned
        return None
    base = match.group("base")
    if base in SCALAR_TYPES:
        return base
    return None


def _append_declared_name(
    name: str,
    type_text: str,
    interface_parameters: set[str],
    interface_types: dict[str, str],
    local_block_instances: dict[str, tuple[str, int | None]],
    local_variable_types: dict[str, str],
    current_section: str,
    line_number: int,
) -> None:
    if name in interface_types or name in local_variable_types or name in local_block_instances:
        raise ParseError(f"Duplicate declaration detected: {name} (line {line_number})")

    instance_match = BLOCK_INSTANCE_DECL_PATTERN.fullmatch(f"{name} : {type_text};")
    if current_section in {"VAR", "VAR_TEMP"} and instance_match:
        quoted_name = instance_match.group("quoted_name")
        if quoted_name is not None:
            local_block_instances[name] = ("QUOTED", None)
        else:
            local_block_instances[name] = (
                instance_match.group("kind").upper(),
                int(instance_match.group("number")),
            )
        return

    if current_section in DECL_SECTION_HEADERS:
        interface_parameters.add(name)
        interface_types[name] = type_text
    elif current_section in {"VAR", "VAR_TEMP"}:
        local_variable_types[name] = type_text


def build_block_declaration_index(block_source: str) -> BlockDeclarationIndex:
    interface_parameters: set[str] = set()
    interface_types: dict[str, str] = {}
    local_block_instances: dict[str, tuple[str, int | None]] = {}
    local_variable_types: dict[str, str] = {}
    current_section: str | None = None
    struct_depth = 0
    pending_array_name: str | None = None

    for line_number, raw_line in _iter_block_header_lines_with_numbers(block_source):
        section_name = raw_line.rstrip(";").strip().upper()
        if section_name in {"VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR", "VAR_TEMP"}:
            current_section = section_name
            continue
        if section_name == "END_VAR":
            current_section = None
            struct_depth = 0
            pending_array_name = None
            continue
        if section_name.startswith("TITLE") or section_name.startswith("NAME") or section_name.startswith("VERSION"):
            continue
        if current_section is None:
            continue
        if section_name == "END_STRUCT":
            if struct_depth > 0:
                struct_depth -= 1
            continue
        if pending_array_name is not None:
            if raw_line.rstrip().endswith(";"):
                pending_array_name = None
            continue

        struct_decl_match = STRUCT_DECLARATION_PATTERN.fullmatch(raw_line)
        if struct_decl_match and current_section in {"VAR", "VAR_TEMP", *DECL_SECTION_HEADERS}:
            name = struct_decl_match.group("name")
            type_text = struct_decl_match.group("type").strip()
            if struct_depth == 0:
                _append_declared_name(
                    name,
                    type_text,
                    interface_parameters,
                    interface_types,
                    local_block_instances,
                    local_variable_types,
                    current_section,
                    line_number,
                )
                if type_text.upper().startswith("ARRAY"):
                    pending_array_name = name
                else:
                    struct_depth += 1
            elif type_text.upper().startswith("STRUCT"):
                struct_depth += 1
            continue
        if struct_depth > 0:
            continue

        array_start_match = ARRAY_DECLARATION_START_PATTERN.fullmatch(raw_line)
        if array_start_match and current_section in {"VAR", "VAR_TEMP", *DECL_SECTION_HEADERS}:
            name = array_start_match.group("name")
            _append_declared_name(
                name,
                "ARRAY",
                interface_parameters,
                interface_types,
                local_block_instances,
                local_variable_types,
                current_section,
                line_number,
            )
            pending_array_name = name
            continue

        decl_match = DECLARATION_PATTERN.fullmatch(raw_line)
        if not decl_match:
            continue

        names = [part.strip() for part in decl_match.group("names").split(",")]
        type_text = decl_match.group("type").strip()
        for name in names:
            _append_declared_name(
                name,
                type_text,
                interface_parameters,
                interface_types,
                local_block_instances,
                local_variable_types,
                current_section,
                line_number,
            )

    return BlockDeclarationIndex(
        interface_parameters=frozenset(interface_parameters),
        interface_types=interface_types,
        local_block_instances=local_block_instances,
        local_variable_types=local_variable_types,
    )


def collect_call_statements(body_lines: list[tuple[int, str]]) -> list[CallStatement]:
    call_statements: list[CallStatement] = []
    index = 0
    while index < len(body_lines):
        line_number, line = body_lines[index]
        if not CALL_START_PATTERN.match(line):
            index += 1
            continue

        statement_lines = [line]
        line_numbers = [line_number]
        statement = line
        paren_depth = line.count("(") - line.count(")")
        while not statement.rstrip().endswith(";") or paren_depth > 0:
            index += 1
            if index >= len(body_lines):
                break
            next_line_number, next_line = body_lines[index]
            statement_lines.append(next_line)
            line_numbers.append(next_line_number)
            statement += " " + next_line
            paren_depth += next_line.count("(") - next_line.count(")")
            if statement.rstrip().endswith(";") and paren_depth <= 0:
                break

        call_statements.append(CallStatement(line_number, " ".join(statement_lines), tuple(line_numbers)))
        index += 1

    return call_statements


def collect_simple_statements(body_lines: list[tuple[int, str]]) -> list[SimpleStatement]:
    statements: list[SimpleStatement] = []
    for line_number, line in body_lines:
        if ":=" in line or CALL_START_PATTERN.match(line):
            continue

        working = line.strip()
        if not working or working.startswith("//"):
            continue
        if working.startswith("NETWORK") or working.startswith("TITLE") or working == "BEGIN":
            continue
        if working.upper() in BLOCK_END_LINES:
            continue

        label = None
        match = re.match(r"^(?P<label>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<rest>.*)$", working)
        if match:
            label = match.group("label")
            working = match.group("rest").strip()
        if not working:
            continue

        has_statement_terminator = working.endswith(";")
        if working.endswith(";"):
            working = working[:-1].rstrip()

        if not working:
            continue

        parts = working.split(None, 1)
        opcode = parts[0].upper()
        operand_text = parts[1].strip() if len(parts) > 1 else ""
        statements.append(SimpleStatement(line_number, label, opcode, operand_text, line, has_statement_terminator))

    return statements


def collect_labels_and_jumps(body_lines: list[tuple[int, str]]) -> tuple[dict[str, int], list[tuple[int, str]]]:
    labels: dict[str, int] = {}
    jumps: list[tuple[int, str]] = []

    for line_number, line in body_lines:
        if ":=" in line:
            continue

        match = re.match(r"^(?P<label>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<rest>.*)$", line)
        if match:
            label = match.group("label")
            if label in labels:
                raise ParseError(f"Duplicate label detected: {label} (line {line_number})")
            labels[label] = line_number
            line = match.group("rest").strip()
            if not line:
                continue

        jump_match = re.match(
            r"^(?P<opcode>JU|JC|JCN|JBI|JNBI|JZ|JN|JP|JM|LOOP)\b(?:\s+(?P<target>[A-Za-z_][A-Za-z0-9_]*))?\s*;?\s*$",
            line,
            re.IGNORECASE,
        )
        if jump_match:
            target = jump_match.group("target")
            if not target:
                raise ParseError(f"Missing jump target on line {line_number}")
            jumps.append((line_number, target))

    return labels, jumps


def _strip_trailing_punctuation(value: str) -> str:
    cleaned = value.strip()
    while cleaned and cleaned[-1] in ",;)":
        if cleaned[-1] == ")" and cleaned.count("(") >= cleaned.count(")"):
            break
        cleaned = cleaned[:-1].rstrip()
    return cleaned


def extract_call_arguments(statement: str) -> list[tuple[str, str]]:
    matches = list(CALL_PARAM_PATTERN.finditer(statement))
    arguments: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        value_start = match.end()
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(statement)
        value = _strip_trailing_punctuation(statement[value_start:value_end])
        arguments.append((match.group("name"), value))
    return arguments


def _normalize_simple_type(type_text: str | None) -> str | None:
    if not type_text:
        return None
    return _normalize_declared_type(type_text)


def infer_type_category(type_text: str | None) -> str | None:
    normalized = _normalize_simple_type(type_text)
    if normalized is None:
        return None
    if normalized == "BOOL":
        return "bit"
    if normalized in {"ANY", "POINTER", "BLOCK_DB"}:
        return "pointer"
    return "numeric"


def infer_operand_category(expression: str, declaration_index: BlockDeclarationIndex | None = None) -> str | None:
    token = expression.strip()
    if not token:
        return None

    if token.startswith("P#"):
        return "pointer"
    if re.fullmatch(r"[-+]?\d+", token):
        return "numeric"
    if re.fullmatch(r"(?:W|DW|B|L)?#16#[0-9A-F]+", token, re.IGNORECASE):
        return "numeric"
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", token):
        return "numeric"
    if DIRECT_BIT_OPERAND_PATTERN.fullmatch(token):
        return "bit"

    if declaration_index is None:
        return None

    match = SIMPLE_REFERENCE_PATTERN.fullmatch(token)
    if not match:
        return None

    name = match.group("name")
    declared_type = declaration_index.local_variable_types.get(name) or declaration_index.interface_types.get(name)
    normalized_type = _normalize_simple_type(declared_type)
    if normalized_type is None:
        return None
    if normalized_type == "BOOL":
        return "bit"
    if normalized_type in INTEGER_TYPES:
        return "numeric"
    if normalized_type in {"ANY", "POINTER"}:
        return "pointer"
    return "direct_address"


def infer_simple_reference_type(
    expression: str,
    declaration_index: BlockDeclarationIndex,
) -> str | None:
    token = expression.strip()
    match = SIMPLE_REFERENCE_PATTERN.fullmatch(token)
    if not match:
        return None

    name = match.group("name")
    if token.startswith("#"):
        declared_type = declaration_index.local_variable_types.get(name) or declaration_index.interface_types.get(name)
        normalized_type = _normalize_simple_type(declared_type)
        if normalized_type is not None:
            return normalized_type
        if declared_type is not None:
            return "direct_address"
        return None

    return _normalize_simple_type(
        declaration_index.local_variable_types.get(name) or declaration_index.interface_types.get(name)
    )


def infer_call_actual_category(
    expression: str,
    declaration_index: BlockDeclarationIndex,
    named_block_index: dict[str, tuple[str, int]] | None = None,
) -> str | None:
    token = expression.strip()
    if not token:
        return None
    if token.upper() in {"TRUE", "FALSE"}:
        return "bit"

    inferred_type = infer_simple_reference_type(token, declaration_index)
    inferred_category = infer_type_category(inferred_type)
    if inferred_category is not None:
        return inferred_category

    if token.startswith('"') and token.endswith('"') and named_block_index is not None:
        resolved = named_block_index.get(token[1:-1])
        if resolved is not None and resolved[0] == "DB":
            return "pointer"

    if token.startswith("P#"):
        return "pointer" if is_valid_pointer_literal(token) else "malformed_pointer"

    if is_obvious_direct_address(token):
        return "direct_address"

    if is_db_symbolic_reference(token):
        return "direct_address"

    if re.fullmatch(r"DB\s*\d+", token, re.IGNORECASE):
        return "direct_address"

    if token.startswith("#") and "." in token:
        base_name = token[1:].split(".", 1)[0]
        declared_type = declaration_index.local_variable_types.get(base_name) or declaration_index.interface_types.get(base_name)
        if declared_type is not None:
            return "direct_address"

    operand_category = infer_operand_category(token, declaration_index)
    if operand_category is not None:
        return operand_category

    return None


def resolve_call_target(
    target_text: str,
    declaration_index: BlockDeclarationIndex,
    named_block_index: dict[str, tuple[str, int]] | None = None,
) -> ResolvedCallTarget | None:
    if re.fullmatch(r"(?:SFB|SFC|FB|FC|OB)\s+\d+", target_text, re.IGNORECASE):
        kind, number_text = target_text.split()
        return ResolvedCallTarget(kind=kind.upper(), name=None, number=int(number_text), source="direct")

    local_match = LOCAL_INSTANCE_PATTERN.fullmatch(target_text)
    if local_match:
        instance_name = local_match.group("name")
        instance_info = declaration_index.local_block_instances.get(instance_name)
        if instance_info is None:
            return None
        if instance_info[0] == "QUOTED":
            return ResolvedCallTarget(
                kind="QUOTED",
                name=instance_name,
                number=None,
                source="local_quoted_instance",
            )
        return ResolvedCallTarget(
            kind=instance_info[0],
            name=instance_name,
            number=instance_info[1],
            source="local_instance",
        )

    quoted_match = QUOTED_BLOCK_PATTERN.fullmatch(target_text)
    if quoted_match:
        if named_block_index is None:
            return ResolvedCallTarget(
                kind="QUOTED",
                name=quoted_match.group("name"),
                number=None,
                source="quoted_external",
            )
        resolved = named_block_index.get(quoted_match.group("name"))
        if resolved is None:
            return ResolvedCallTarget(
                kind="QUOTED",
                name=quoted_match.group("name"),
                number=None,
                source="quoted_external",
            )
        return ResolvedCallTarget(
            kind=resolved[0],
            name=quoted_match.group("name"),
            number=resolved[1],
            source="quoted",
        )

    return None


def is_type_compatible(formal_type: str | None, actual_type: str | None) -> bool:
    if formal_type is None or actual_type is None:
        return True
    if formal_type in {"ANY", "POINTER"} or actual_type in {"ANY", "POINTER"}:
        return True
    return formal_type == actual_type


def validate_simple_statement_forms(
    path: Path,
    body_lines: list[tuple[int, str]],
    declaration_index: BlockDeclarationIndex | None = None,
) -> None:
    for statement in collect_simple_statements(body_lines):
        if not statement.has_statement_terminator:
            raise ParseError(
                f"{path.name}: missing ';' at end of statement (line {statement.line_number})"
            )
        opcode = statement.opcode
        operand_text = statement.operand_text

        if opcode in SIMPLE_OPCODE_BIT_OPERAND_REQUIRED:
            if not operand_text:
                raise ParseError(f"{path.name}: opcode {opcode} requires an operand (line {statement.line_number})")
            operand_category = infer_operand_category(operand_text, declaration_index)
            if operand_category in NON_BIT_OPERAND_CATEGORIES:
                raise ParseError(
                    f"{path.name}: opcode {opcode} requires a bit-compatible operand (line {statement.line_number})"
                )
            continue

        if opcode in SIMPLE_OPCODE_BIT_OPERAND_OPTIONAL:
            if not operand_text:
                continue
            operand_category = infer_operand_category(operand_text, declaration_index)
            if operand_category in NON_BIT_OPERAND_CATEGORIES:
                raise ParseError(
                    f"{path.name}: opcode {opcode} requires a bit-compatible operand (line {statement.line_number})"
                )
            continue

        if opcode in SIMPLE_OPCODE_DISALLOW_BIT_OPERAND:
            operand_category = infer_operand_category(operand_text, declaration_index)
            if operand_category in BIT_OPERAND_CATEGORIES:
                raise ParseError(
                    f"{path.name}: opcode {opcode} does not accept a bit operand (line {statement.line_number})"
                )
            continue

        if opcode in {"L", "T"}:
            continue

        if opcode in SIMPLE_OPCODE_NO_OPERAND:
            if operand_text:
                raise ParseError(f"{path.name}: opcode {opcode} does not take an operand (line {statement.line_number})")
            continue

        if opcode in SIMPLE_OPCODE_NUMERIC_OPERAND:
            if not re.fullmatch(r"\d+", operand_text):
                raise ParseError(
                    f"{path.name}: opcode {opcode} requires a numeric operand (line {statement.line_number})"
                )


def validate_call_parameter_types(
    path,
    call_statement: CallStatement,
    declaration_index: BlockDeclarationIndex,
    named_block_index: dict[str, tuple[str, int]],
    block_interfaces: dict[tuple[str, int], dict[str, str]],
) -> None:
    match = CALL_HEADER_PATTERN.match(call_statement.statement)
    if not match:
        return

    target_text = match.group("target")
    tail = match.group("tail") or ""

    target_kind: str | None = None
    target_number: int | None = None
    if re.fullmatch(r"(?:SFB|SFC|FB|FC|OB)\s+\d+", target_text, re.IGNORECASE):
        kind, number_text = target_text.split()
        target_kind = kind.upper()
        target_number = int(number_text)
    elif target_text.startswith("#") or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", target_text):
        instance_name = target_text[1:] if target_text.startswith("#") else target_text
        instance_info = declaration_index.local_block_instances.get(instance_name)
        if instance_info is None:
            return
        if instance_info[0] == "QUOTED":
            return
        target_kind = instance_info[0]
        target_number = instance_info[1]
    else:
        return

    if target_kind is None or target_number is None:
        return

    if target_kind not in {"FB", "FC", "OB"}:
        return

    instance_match = CALL_INSTANCE_PATTERN.match(tail) or CALL_INSTANCE_QUOTED_PATTERN.match(tail)
    if instance_match:
        tail = tail[instance_match.end() :]

    allowed_parameters = block_interfaces.get((target_kind, target_number), {})
    if not allowed_parameters:
        return

    for formal_name, actual_value in extract_call_arguments(call_statement.statement):
        formal_type = _normalize_simple_type(allowed_parameters.get(formal_name))
        formal_category = infer_type_category(allowed_parameters.get(formal_name))
        actual_type = infer_simple_reference_type(actual_value, declaration_index)
        actual_category = infer_call_actual_category(actual_value, declaration_index, named_block_index)
        if actual_category == "malformed_pointer":
            raise ParseError(
                f"{path.name}: CALL parameter {formal_name!r} has invalid pointer literal {actual_value!r} "
                f"(line {call_statement.line_number})"
            )
        if actual_type == "direct_address" or actual_category == "direct_address":
            continue
        if formal_category == "pointer":
            if actual_category not in {"pointer", "direct_address"}:
                formal_display = formal_type or formal_category
                actual_display = actual_type or actual_category
                raise ParseError(
                    f"{path.name}: CALL parameter {formal_name!r} expects {formal_display} but got {actual_display} "
                    f"(line {call_statement.line_number})"
                )
            continue

        if formal_type is not None and actual_type is not None:
            if formal_type != actual_type:
                raise ParseError(
                    f"{path.name}: CALL parameter {formal_name!r} expects {formal_type} but got {actual_type} "
                    f"(line {call_statement.line_number})"
                )
            continue

        if actual_category is not None and formal_category is not None and actual_category != formal_category:
            formal_display = formal_type or formal_category
            actual_display = actual_type or actual_category
            raise ParseError(
                f"{path.name}: CALL parameter {formal_name!r} expects {formal_display} but got {actual_display} "
                f"(line {call_statement.line_number})"
            )


def parse_call_instance_reference(tail: str) -> CallInstanceReference | None:
    quoted_match = CALL_INSTANCE_QUOTED_PATTERN.match(tail)
    if quoted_match:
        return CallInstanceReference(
            quoted_name=quoted_match.group("name"),
            kind=None,
            number=None,
            span_end=quoted_match.end(),
        )

    instance_match = CALL_INSTANCE_PATTERN.match(tail)
    if instance_match:
        return CallInstanceReference(
            quoted_name=None,
            kind=instance_match.group("kind").upper(),
            number=int(instance_match.group("number")),
            span_end=instance_match.end(),
        )

    return None
