from __future__ import annotations

import re
from pathlib import Path

from .encoding import read_mixed_text
from .models import Block

BLOCK_START_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("UDT", re.compile(r"^TYPE UDT (\d+)$")),
    ("DB", re.compile(r"^DATA_BLOCK DB (\d+)$")),
    ("FB", re.compile(r"^FUNCTION_BLOCK FB (\d+)$")),
    ("FC", re.compile(r"^FUNCTION FC (\d+)\s*:\s*.+$")),
    ("OB", re.compile(r"^ORGANIZATION_BLOCK OB (\d+)$")),
)

BLOCK_END_BY_TYPE = {
    "UDT": "END_TYPE",
    "DB": "END_DATA_BLOCK",
    "FB": "END_FUNCTION_BLOCK",
    "FC": "END_FUNCTION",
    "OB": "END_ORGANIZATION_BLOCK",
}

SYMBOLIC_BLOCK_START_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("UDT", re.compile(r'^TYPE "(.+)"$')),
    ("DB", re.compile(r'^DATA_BLOCK "(.+)"$')),
    ("FB", re.compile(r'^FUNCTION_BLOCK "(.+)"$')),
    ("FC", re.compile(r'^FUNCTION "(.+)"\s*:\s*.+$')),
    ("OB", re.compile(r'^ORGANIZATION_BLOCK "(.+)"$')),
)


class ParseError(ValueError):
    """Raised when AWL content cannot be parsed into blocks."""


INTERNAL_NAME_PATTERN = re.compile(r'^NAME\s*:\s*(.+?)\s*$')


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _extract_internal_name(lines: list[str]) -> str | None:
    for line in lines:
        match = INTERNAL_NAME_PATTERN.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1].strip()
        return value or None
    return None


def detect_block_header(
    line: str,
    symbol_index: dict[tuple[str, str], int] | None = None,
) -> Block | None:
    stripped = line.strip()
    for block_type, pattern in BLOCK_START_PATTERNS:
        match = pattern.match(stripped)
        if match:
            return Block(block_type=block_type, number=int(match.group(1)), source="")

    if symbol_index:
        for block_type, pattern in SYMBOLIC_BLOCK_START_PATTERNS:
            match = pattern.match(stripped)
            if not match:
                continue
            symbol_name = match.group(1)
            number = symbol_index.get((block_type, symbol_name))
            if number is None:
                return Block(
                    block_type=block_type,
                    number=-1,
                    source="",
                    symbol_name=symbol_name,
                )
            return Block(
                block_type=block_type,
                number=number,
                source="",
                symbol_name=symbol_name,
            )
    return None


def parse_monolith_blocks(
    text: str,
    symbol_index: dict[tuple[str, str], int] | None = None,
) -> list[Block]:
    normalized = normalize_newlines(text)
    lines = normalized.split("\n")
    blocks: list[Block] = []
    current_block: Block | None = None
    current_lines: list[str] = []

    for line in lines:
        detected = detect_block_header(line, symbol_index=symbol_index)
        if current_block is None:
            if detected is None:
                if line.strip():
                    raise ParseError(f"Unexpected content outside block: {line!r}")
                continue
            current_block = detected
            current_lines = [line]
            continue

        current_lines.append(line)
        if line == BLOCK_END_BY_TYPE[current_block.block_type]:
            source = "\r\n".join(current_lines).rstrip("\r\n") + "\r\n"
            blocks.append(
                Block(
                    block_type=current_block.block_type,
                    number=current_block.number,
                    source=source,
                    symbol_name=current_block.symbol_name,
                    internal_name=_extract_internal_name(current_lines),
                )
            )
            current_block = None
            current_lines = []

    if current_block is not None:
        raise ParseError(
            f"Block {current_block.block_type} {current_block.number} is missing its closing line"
        )

    return blocks


def parse_single_block_file(
    path: Path,
    symbol_index: dict[tuple[str, str], int] | None = None,
) -> Block:
    text = read_mixed_text(path).text
    blocks = parse_monolith_blocks(text, symbol_index=symbol_index)
    if len(blocks) != 1:
        raise ParseError(f"{path} must contain exactly one block, found {len(blocks)}")
    block = blocks[0]
    if block.number < 0:
        match = re.fullmatch(r"([a-z]+)(\d+)(?:_.+)?", path.stem, re.IGNORECASE)
        if match:
            block = Block(
                block_type=block.block_type,
                number=int(match.group(2)),
                source=block.source,
                symbol_name=block.symbol_name,
                internal_name=block.internal_name,
            )
    return block
