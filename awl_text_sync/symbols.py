from __future__ import annotations

import re
from pathlib import Path

from .encoding import read_mixed_text
from .writer import ensure_directory

EDITABLE_BLOCK_TYPES = {"UDT", "DB", "FB", "FC", "OB"}


def write_symbols_file(source: Path, destination: Path, target_encoding: str) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Symbols file not found: {source}")
    ensure_directory(destination.parent)
    text = read_mixed_text(source).text
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    destination.write_text(normalized, encoding=target_encoding, newline="")


def _parse_sdf_line(line: str) -> tuple[str, str, str, str] | None:
    match = re.fullmatch(r'"([^\"]*)","([^\"]*)","([^\"]*)","([^\"]*)"', line.rstrip("\r\n"))
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3), match.group(4)


def _split_type_and_number(raw: str) -> tuple[str, int] | None:
    match = re.fullmatch(r"\s*([A-Z]+)\s+(\d+(?:\.\d+)?)\s*", raw)
    if not match:
        return None
    block_type = match.group(1)
    if block_type not in EDITABLE_BLOCK_TYPES:
        return None
    number_text = match.group(2)
    if "." in number_text:
        return None
    return block_type, int(number_text)


def load_symbol_index(symbols_path: Path) -> dict[tuple[str, str], int]:
    if not symbols_path.exists():
        raise FileNotFoundError(f"Symbols file not found: {symbols_path}")

    index: dict[tuple[str, str], int] = {}
    for raw_line in read_mixed_text(symbols_path).text.splitlines():
            parsed = _parse_sdf_line(raw_line)
            if parsed is None:
                continue
            symbol, addr, _data, _comment = parsed
            symbol_name = symbol.rstrip()
            type_and_number = _split_type_and_number(addr)
            if type_and_number is None:
                continue
            block_type, number = type_and_number
            index[(block_type, symbol_name)] = number
    return index


def load_reverse_symbol_index(symbols_path: Path) -> dict[tuple[str, int], str]:
    if not symbols_path.exists():
        raise FileNotFoundError(f"Symbols file not found: {symbols_path}")

    index: dict[tuple[str, int], str] = {}
    for raw_line in read_mixed_text(symbols_path).text.splitlines():
            parsed = _parse_sdf_line(raw_line)
            if parsed is None:
                continue
            symbol, addr, _data, _comment = parsed
            symbol_name = symbol.rstrip()
            type_and_number = _split_type_and_number(addr)
            if type_and_number is None:
                continue
            block_type, number = type_and_number
            index[(block_type, number)] = symbol_name
    return index
