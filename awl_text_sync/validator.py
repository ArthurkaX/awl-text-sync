from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

from .config import WorkspacePaths, resolve_project_symbols_path
from .encoding import contains_suspicious_mojibake, find_non_cp1252_characters, read_mixed_text
from .models import ParsedBlockFile, filename_component, slugify_symbol_name
from .parser import BLOCK_END_BY_TYPE, ParseError, parse_single_block_file
from .symbols import load_reverse_symbol_index, load_symbol_index
from .stl_validation import (
    BlockDeclarationIndex,
    CallStatement,
    build_block_declaration_index,
    collect_call_statements,
    collect_labels_and_jumps,
    parse_call_instance_reference,
    resolve_call_target,
    is_valid_pointer_literal,
    validate_call_parameter_types,
    validate_simple_statement_forms,
)

TYPE_ORDER = {"UDT": 0, "DB": 1, "FB": 2, "FC": 3, "OB": 4}
DB_REFERENCE_PATTERN = re.compile(r"DB\d+", re.IGNORECASE)
DB_SELECTOR_PATTERN = re.compile(r"DB[XBWD]\s*\d+(?:\.\d+)?", re.IGNORECASE)
DB_ACCESS_PATTERN = re.compile(
    r"\b(?P<left>DB\d+|[A-Za-z_][A-Za-z0-9_]*)\.(?P<right>DB[XBWD]\s*\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)
POINTER_LITERAL_PATTERN = re.compile(
    r"\bP#(?P<target>(?:DB\d+\.\s*DB[XBWD]\s*\d+(?:\.\d+)?|DB[XBWD]\s*\d+\.\d+|[A-Z]{1,3}\s*\d+\.\d+|\d+\.\d+|P\s+0\.0|0\.0|#[A-Za-z_][A-Za-z0-9_]*))(?:\s+(?P<data_type>BIT|BYTE|WORD|DWORD)\s+(?P<count>\d+))?\b",
    re.IGNORECASE,
)
BODY_LABEL_PATTERN = re.compile(r"^(?P<label>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<rest>.*)$")
JUMP_PATTERN = re.compile(
    r"^(?P<opcode>JU|JC|JCN|JBI|JNBI|JZ|JN|JP|JM|LOOP)\b(?:\s+(?P<target>[A-Za-z_][A-Za-z0-9_]*))?\s*;?\s*$",
    re.IGNORECASE,
)
CALL_START_PATTERN = re.compile(r"^(?:(?P<label>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*)?CALL\b", re.IGNORECASE)
CALL_HEADER_PATTERN = re.compile(
    r"^(?:(?P<label>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*)?CALL\s+(?P<target>(?:SFB|SFC|FB|FC|OB)\s+\d+|#?[A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\")(?P<tail>.*)$",
    re.IGNORECASE,
)
CALL_INSTANCE_PATTERN = re.compile(r"^\s*,\s*(?P<kind>DB|DI)\s+(?P<number>\d+)\b", re.IGNORECASE)
CALL_PARAM_PATTERN = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:=")
LOCAL_INSTANCE_PATTERN = re.compile(r"^#(?P<name>[A-Za-z_][A-Za-z0-9_]*)$")
DECL_SECTION_HEADERS = {"VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT"}
BLOCK_INSTANCE_DECL_PATTERN = re.compile(
    r'^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?:(?P<kind>FB|FC|OB|SFB|SFC)\s+(?P<number>\d+)|"(?P<quoted_name>[^"]+)")\s*;\s*$',
    re.IGNORECASE,
)
BLOCK_TYPE_PATTERN = re.compile(r"^(?P<kind>FB|FC|OB|SFB|SFC)\s+(?P<number>\d+)$", re.IGNORECASE)
QUOTED_BLOCK_PATTERN = re.compile(r'^"(?P<name>[^"]+)"$')
LOCAL_INSTANCE_PATTERN = re.compile(r"^#(?P<name>[A-Za-z_][A-Za-z0-9_]*)$")
INTERFACE_NAME_PATTERN = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:")
SECTION_HEADER_PATTERN = re.compile(r"^(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR|VAR_TEMP|END_VAR|BEGIN)$", re.IGNORECASE)
STATEMENT_END_PATTERN = re.compile(r";\s*$")
LABEL_ONLY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class BlockDeclarationIndex:
    interface_parameters: frozenset[str]
    local_block_instances: dict[str, tuple[str, int | None]]


class ValidationErrorReport(ParseError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        summary = [f"Validation failed with {len(errors)} error(s):"]
        summary.extend(f"- {error}" for error in errors)
        super().__init__("\n".join(summary))


def _format_invalid_characters(chars: list[str]) -> str:
    return ", ".join(f"{char!r} (U+{ord(char):04X})" for char in chars[:5])


def _validate_step7_roundtrip(path: Path) -> list[str]:
    text = read_mixed_text(path).text
    errors: list[str] = []
    invalid_chars = find_non_cp1252_characters(text)
    if invalid_chars:
        errors.append(
            f"{path.name}: contains characters not representable in cp1252 for STEP 7 export: {_format_invalid_characters(invalid_chars)}"
        )
    if contains_suspicious_mojibake(text):
        errors.append(
            f"{path.name}: contains suspicious mojibake text; check for a broken UTF-8/cp1252 conversion before STEP 7 import"
        )
    return errors


def _parse_filename(path: Path) -> tuple[str, int]:
    stem = path.stem
    match = re.fullmatch(r"([a-z]+)(\d+)(?:_(.+))?", stem)
    if not match:
        raise ParseError(f"Invalid block filename: {path.name}")
    return match.group(1).upper(), int(match.group(2))


def _is_canonical_filename(path: Path) -> bool:
    return bool(re.fullmatch(r"[a-z]+\d+_[A-Za-z0-9_]+", path.stem))


def _is_absolute_db_reference(token: str) -> bool:
    return bool(DB_REFERENCE_PATTERN.fullmatch(token))


def _is_absolute_db_selector(token: str) -> bool:
    return bool(DB_SELECTOR_PATTERN.fullmatch(token))


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


def _build_block_declaration_index(block_source: str) -> BlockDeclarationIndex:
    interface_parameters: set[str] = set()
    local_block_instances: dict[str, tuple[str, int | None]] = {}
    current_section: str | None = None

    for raw_line in _iter_block_header_lines(block_source):
        section_name = raw_line.upper()
        if section_name in {"VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR", "VAR_TEMP"}:
            current_section = section_name
            continue
        if section_name == "END_VAR":
            current_section = None
            continue
        if section_name.startswith("TITLE") or section_name.startswith("NAME") or section_name.startswith("VERSION"):
            continue

        if current_section in DECL_SECTION_HEADERS:
            interface_match = INTERFACE_NAME_PATTERN.match(raw_line)
            if interface_match:
                interface_parameters.add(interface_match.group("name"))
        if current_section in {"VAR", "VAR_TEMP"}:
            instance_match = BLOCK_INSTANCE_DECL_PATTERN.match(raw_line)
            if instance_match:
                quoted_name = instance_match.group("quoted_name")
                if quoted_name is not None:
                    local_block_instances[instance_match.group("name")] = ("QUOTED", None)
                else:
                    local_block_instances[instance_match.group("name")] = (
                        instance_match.group("kind").upper(),
                        int(instance_match.group("number")),
                    )

    return BlockDeclarationIndex(
        interface_parameters=frozenset(interface_parameters),
        local_block_instances=local_block_instances,
    )


def _normalize_call_target(target: str) -> tuple[str, str | None, int | None]:
    local_match = LOCAL_INSTANCE_PATTERN.fullmatch(target)
    if local_match:
        return "LOCAL_INSTANCE", local_match.group("name"), None

    quoted_match = QUOTED_BLOCK_PATTERN.fullmatch(target)
    if quoted_match:
        return "QUOTED", quoted_match.group("name"), None

    block_type_match = BLOCK_TYPE_PATTERN.fullmatch(target)
    if block_type_match:
        return block_type_match.group("kind").upper(), None, int(block_type_match.group("number"))

    return "UNKNOWN", target, None


def _collect_labels_and_jumps(body_lines: list[tuple[int, str]]) -> tuple[dict[str, int], list[tuple[int, str]]]:
    labels: dict[str, int] = {}
    jumps: list[tuple[int, str]] = []

    for line_number, line in body_lines:
        if ":=" in line:
            jump_match = JUMP_PATTERN.fullmatch(line)
            if jump_match:
                target = jump_match.group("target")
                if not target:
                    raise ParseError(f"Missing jump target on line {line_number}")
                jumps.append((line_number, target))
            continue

        match = BODY_LABEL_PATTERN.match(line)
        if match:
            label = match.group("label")
            if label in labels:
                raise ParseError(f"Duplicate label detected: {label} (line {line_number})")
            labels[label] = line_number
            line = match.group("rest").strip()
            if not line:
                continue

        jump_match = JUMP_PATTERN.fullmatch(line)
        if jump_match:
            target = jump_match.group("target")
            if not target:
                raise ParseError(f"Missing jump target on line {line_number}")
            jumps.append((line_number, target))

    return labels, jumps


def _collect_call_statements(body_lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    call_statements: list[tuple[int, str]] = []
    index = 0
    while index < len(body_lines):
        line_number, line = body_lines[index]
        if not CALL_START_PATTERN.match(line):
            index += 1
            continue

        statement_lines = [line]
        statement = line
        paren_depth = line.count("(") - line.count(")")
        while not STATEMENT_END_PATTERN.search(statement) or paren_depth > 0:
            index += 1
            if index >= len(body_lines):
                break
            next_line_number, next_line = body_lines[index]
            statement_lines.append(next_line)
            statement += " " + next_line
            paren_depth += next_line.count("(") - next_line.count(")")
            if STATEMENT_END_PATTERN.search(statement) and paren_depth <= 0:
                break

        call_statements.append((line_number, " ".join(statement_lines)))
        index += 1

    return call_statements


def _validate_db_access_consistency(path: Path, block_source: str) -> None:
    return


def _validate_pointer_literals(path: Path, block_source: str) -> None:
    for line_number, line in _iter_block_body_lines(block_source):
        pointer_matches = list(POINTER_LITERAL_PATTERN.finditer(line))
        matched_starts = {match.start() for match in pointer_matches}

        search_start = 0
        while True:
            pointer_index = line.find("P#", search_start)
            if pointer_index == -1:
                break
            if pointer_index not in matched_starts:
                raise ParseError(f"{path.name}: invalid pointer literal on line {line_number}: {line}")
            search_start = pointer_index + 2

        for match in pointer_matches:
            if is_valid_pointer_literal(match.group(0)):
                continue
            raise ParseError(
                f"{path.name}: unsupported or non-absolute pointer literal {match.group(0)!r} on line {line_number}"
            )


def _find_block_by_kind_and_number(
    block_index: dict[tuple[str, int], ParsedBlockFile],
    kind: str,
    number: int,
) -> ParsedBlockFile | None:
    return block_index.get((kind.upper(), number))


def _build_named_block_index(parsed: list[ParsedBlockFile]) -> dict[str, tuple[str, int]]:
    named_blocks: dict[str, tuple[str, int]] = {}
    conflicts: set[str] = set()
    for item in parsed:
        block = item.block
        for name in (block.symbol_name, block.internal_name):
            if not name or name in conflicts:
                continue
            key = (block.block_type, block.number)
            existing = named_blocks.get(name)
            if existing is None:
                named_blocks[name] = key
            elif existing != key:
                conflicts.add(name)
                named_blocks.pop(name, None)
    return named_blocks


def _validate_jump_targets(path: Path, block_source: str) -> None:
    body_lines = _iter_block_body_lines(block_source)
    labels, jumps = collect_labels_and_jumps(body_lines)
    for line_number, target in jumps:
        if target not in labels:
            raise ParseError(f"{path.name}: jump target {target!r} is not defined in this block (line {line_number})")


def _validate_call_statement(
    path: Path,
    line_number: int,
    statement: str,
    block_index: dict[tuple[str, int], ParsedBlockFile],
    declaration_index: BlockDeclarationIndex,
    named_block_index: dict[str, tuple[str, int]],
    block_interfaces: dict[tuple[str, int], dict[str, str]],
) -> None:
    match = CALL_HEADER_PATTERN.match(statement)
    if not match:
        raise ParseError(f"{path.name}: invalid CALL syntax on line {line_number}: {statement}")

    target_text = match.group("target")
    tail = match.group("tail") or ""
    resolved_target = resolve_call_target(target_text, declaration_index, named_block_index)
    if resolved_target is None:
        local_match = LOCAL_INSTANCE_PATTERN.fullmatch(target_text)
        if local_match:
            instance_name = local_match.group("name")
            if instance_name not in declaration_index.local_block_instances:
                raise ParseError(
                    f"{path.name}: local block instance {instance_name!r} is not declared (line {line_number})"
                )
        raise ParseError(f"{path.name}: invalid CALL target {target_text!r} on line {line_number}")

    target_kind = resolved_target.kind
    target_name = resolved_target.name
    target_number = resolved_target.number
    is_local_instance_call = resolved_target.source == "local_instance"
    is_external_quoted_call = resolved_target.source in {"quoted_external", "local_quoted_instance"}

    if is_external_quoted_call:
        return

    instance_match = CALL_INSTANCE_PATTERN.match(tail)
    if instance_match:
        instance_kind = instance_match.group("kind").upper()
        instance_number = int(instance_match.group("number"))
        tail = tail[instance_match.end() :]
    else:
        instance_kind = None
        instance_number = None

    if is_local_instance_call:
        assert target_name is not None
        instance_info = declaration_index.local_block_instances.get(target_name)
        if instance_info is None:
            raise ParseError(
                f"{path.name}: local block instance {target_name!r} is not declared (line {line_number})"
            )
    if target_kind not in {"FB", "FC", "OB", "SFB", "SFC"}:
        raise ParseError(f"{path.name}: invalid CALL target {target_text!r} on line {line_number}")

    if target_kind in {"FB", "FC", "OB"}:
        assert target_number is not None
        target_block = _find_block_by_kind_and_number(block_index, target_kind, target_number)
        if target_block is None:
            return

        if instance_kind is None and instance_number is None:
            quoted_instance = parse_call_instance_reference(tail)
            if quoted_instance is not None:
                if target_kind != "FB":
                    raise ParseError(f"{path.name}: only FB calls may specify an instance DB (line {line_number})")
                if quoted_instance.quoted_name is not None:
                    instance_resolved = named_block_index.get(quoted_instance.quoted_name)
                    if instance_resolved is None:
                        raise ParseError(
                            f"{path.name}: instance DB {quoted_instance.quoted_name!r} for FB {target_number} is not present in the workspace (line {line_number})"
                        )
                    instance_kind, instance_number = instance_resolved
                    if instance_kind != "DB":
                        raise ParseError(
                            f"{path.name}: FB call expects DB instance data (line {line_number})"
                        )
                else:
                    instance_kind = quoted_instance.kind
                    instance_number = quoted_instance.number

        if target_kind == "FB":
            if not is_local_instance_call and instance_kind != "DB":
                raise ParseError(
                    f"{path.name}: FB call requires an instance DB (line {line_number})"
                )
            if instance_kind not in {"DB", None}:
                raise ParseError(
                    f"{path.name}: FB call expects DB instance data (line {line_number})"
                )
            if instance_kind == "DB":
                assert instance_number is not None
                instance_block = _find_block_by_kind_and_number(block_index, "DB", instance_number)
                if instance_block is None:
                    raise ParseError(
                        f"{path.name}: instance DB {instance_number} for FB {target_number} is not present in the workspace (line {line_number})"
                    )
        elif target_kind == "FC":
            if instance_kind is not None:
                raise ParseError(f"{path.name}: only FB calls may specify an instance DB (line {line_number})")
        else:
            if instance_kind is not None:
                raise ParseError(f"{path.name}: only FB calls may specify an instance DB (line {line_number})")

        actual_parameters: list[str] = []
        for param_match in CALL_PARAM_PATTERN.finditer(statement):
            actual_parameters.append(param_match.group("name"))

        allowed_parameters = dict(block_interfaces.get((target_kind, target_number), {}))
        if target_kind == "FC":
            allowed_parameters.setdefault("RET_VAL", "INT")
        if allowed_parameters:
            unknown_parameters = [name for name in actual_parameters if name not in allowed_parameters]
            if unknown_parameters:
                unknown = ", ".join(unknown_parameters)
                raise ParseError(
                    f"{path.name}: unknown CALL parameter(s) for {target_kind} {target_number}: {unknown} (line {line_number})"
                )

    validate_call_parameter_types(
        path,
        CallStatement(line_number=line_number, statement=statement, line_numbers=(line_number,)),
        declaration_index,
        named_block_index,
        block_interfaces,
    )


def _validate_calls(
    path: Path,
    block_source: str,
    block_index: dict[tuple[str, int], ParsedBlockFile],
    declaration_index: BlockDeclarationIndex,
    named_block_index: dict[str, tuple[str, int]],
    block_interfaces: dict[tuple[str, int], dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    for call_statement in collect_call_statements(_iter_block_body_lines(block_source)):
        if not call_statement.statement.rstrip().endswith(";"):
            errors.append(f"{path.name}: missing ';' at end of CALL statement (line {call_statement.line_number})")
            continue
        try:
            _validate_call_statement(
                path,
                call_statement.line_number,
                call_statement.statement,
                block_index,
                declaration_index,
                named_block_index,
                block_interfaces,
            )
        except ParseError as exc:
            errors.append(str(exc))
    return errors


def load_block_files(paths: WorkspacePaths) -> tuple[list[ParsedBlockFile], list[str]]:
    if not paths.project_blocks_dir.exists():
        raise FileNotFoundError(f"Missing blocks directory: {paths.project_blocks_dir}")

    project_symbols = resolve_project_symbols_path(paths)
    symbol_index = load_symbol_index(project_symbols)
    reverse_symbol_index = load_reverse_symbol_index(project_symbols)
    parsed_by_key: dict[tuple[str, int], ParsedBlockFile] = {}
    errors: list[str] = []

    for path in sorted(paths.project_blocks_dir.glob("*.awl")):
        try:
            errors.extend(_validate_step7_roundtrip(path))
            expected_type, expected_number = _parse_filename(path)
            block = parse_single_block_file(path, symbol_index=symbol_index)

            if block.block_type != expected_type:
                raise ParseError(
                    f"{path.name}: filename type {expected_type} does not match header type {block.block_type}"
                )
            if block.number != expected_number:
                raise ParseError(
                    f"{path.name}: filename number {expected_number} does not match header number {block.number}"
                )
            if not block.source.rstrip("\r\n").endswith(BLOCK_END_BY_TYPE[block.block_type]):
                raise ParseError(f"{path.name}: closing keyword mismatch")
            _validate_db_access_consistency(path, block.source)
            _validate_pointer_literals(path, block.source)
            expected_symbol = block.symbol_name or reverse_symbol_index.get((block.block_type, block.number))
            if expected_symbol or block.internal_name:
                preferred_name = expected_symbol or block.internal_name
                assert preferred_name is not None
                expected_name = filename_component(preferred_name)
                expected_filename = f"{block.block_type.lower()}{block.number}_{expected_name}.awl"
                legacy_plain = f"{block.block_type.lower()}{block.number}.awl"
                legacy_underscored = f"{block.block_type.lower()}_{block.number}.awl"
                legacy_slug = f"{block.block_type.lower()}{block.number}_{slugify_symbol_name(preferred_name)}.awl"
                if path.name not in {expected_filename, legacy_plain, legacy_underscored, legacy_slug}:
                    raise ParseError(
                        f"{path.name}: expected filename {expected_filename} for block {block.block_type} {block.number}"
                    )

            key = (block.block_type, block.number)
            candidate = ParsedBlockFile(path=path, block=block)
            existing = parsed_by_key.get(key)
            if existing is None:
                parsed_by_key[key] = candidate
                continue

            existing_canonical = _is_canonical_filename(existing.path)
            candidate_canonical = _is_canonical_filename(candidate.path)
            if existing_canonical and not candidate_canonical:
                continue
            if candidate_canonical and not existing_canonical:
                parsed_by_key[key] = candidate
                continue
            raise ParseError(f"Duplicate block detected: {block.block_type} {block.number}")
        except ParseError as exc:
            errors.append(str(exc))

    return list(parsed_by_key.values()), errors


def validate_workspace(paths: WorkspacePaths) -> list[ParsedBlockFile]:
    project_symbols = resolve_project_symbols_path(paths)

    parsed, errors = load_block_files(paths)
    errors.extend(_validate_step7_roundtrip(project_symbols))
    block_index = {(item.block.block_type, item.block.number): item for item in parsed}
    declaration_indexes = {
        item.path: build_block_declaration_index(item.block.source)
        for item in parsed
        if item.block.block_type in {"FB", "FC", "OB"}
    }
    named_block_index = _build_named_block_index(parsed)
    block_interfaces = {
        (item.block.block_type, item.block.number): declaration_indexes[item.path].interface_types
        for item in parsed
        if item.path in declaration_indexes
    }

    for item in parsed:
        declaration_index = declaration_indexes.get(item.path)
        if declaration_index is None:
            continue
        try:
            validate_simple_statement_forms(item.path, _iter_block_body_lines(item.block.source), declaration_index)
        except ParseError as exc:
            errors.append(str(exc))
        try:
            _validate_jump_targets(item.path, item.block.source)
        except ParseError as exc:
            errors.append(str(exc))
        try:
            errors.extend(
                _validate_calls(
                    item.path,
                    item.block.source,
                    block_index,
                    declaration_index,
                    named_block_index,
                    block_interfaces,
                )
            )
        except ParseError as exc:
            errors.append(str(exc))

    if errors:
        raise ValidationErrorReport(errors)
    return sorted(parsed, key=lambda item: (TYPE_ORDER[item.block.block_type], item.block.number))
