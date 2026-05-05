from __future__ import annotations

from dataclasses import replace

from .config import (
    WorkspacePaths,
    resolve_exported_monolith_path,
    resolve_exported_symbols_path,
    resolve_project_symbols_path,
)
from .encoding import read_mixed_text
from .models import Block
from .parser import normalize_newlines, parse_monolith_blocks
from .symbols import load_reverse_symbol_index, load_symbol_index, write_symbols_file
from .validator import validate_workspace
from .writer import ensure_directory, write_cp1252_crlf


def _load_exported_blocks(paths: WorkspacePaths) -> list[Block]:
    monolith_source = resolve_exported_monolith_path(paths)
    exported_symbols = resolve_exported_symbols_path(paths)
    symbol_index = load_symbol_index(exported_symbols)
    reverse_symbol_index = load_reverse_symbol_index(exported_symbols)
    blocks = parse_monolith_blocks(read_mixed_text(monolith_source).text, symbol_index=symbol_index)

    next_numbers: dict[str, int] = {}
    for block in blocks:
        if block.number >= 0:
            next_numbers[block.block_type] = max(next_numbers.get(block.block_type, 0), block.number)
    for index, block in enumerate(blocks):
        if block.number >= 0:
            continue
        next_numbers[block.block_type] = next_numbers.get(block.block_type, 0) + 1
        blocks[index] = replace(block, number=next_numbers[block.block_type])

    return [
        replace(
            block,
            symbol_name=block.symbol_name or reverse_symbol_index.get((block.block_type, block.number)),
        )
        for block in blocks
    ]


def _compare_source(source: str) -> str:
    return normalize_newlines(source).rstrip("\n")


def build_split_import(paths: WorkspacePaths) -> int:
    parsed_blocks = validate_workspace(paths)
    project_symbols = resolve_project_symbols_path(paths)

    ensure_directory(paths.build_split_blocks_dir)
    ensure_directory(paths.build_split_symbols_dir)

    for parsed in parsed_blocks:
        write_cp1252_crlf(paths.build_split_blocks_dir / parsed.path.name, parsed.block.source)

    write_symbols_file(
        project_symbols,
        paths.build_split_symbols_dir / project_symbols.name,
        target_encoding="cp1252",
    )

    return len(parsed_blocks)


def build_patch(paths: WorkspacePaths) -> int:
    parsed_blocks = validate_workspace(paths)
    exported_blocks = _load_exported_blocks(paths)
    exported_by_key = {
        (block.block_type, block.number): block
        for block in exported_blocks
    }

    changed_blocks = []
    for parsed in parsed_blocks:
        key = (parsed.block.block_type, parsed.block.number)
        exported_block = exported_by_key.get(key)
        if exported_block is None or _compare_source(parsed.block.source) != _compare_source(exported_block.source):
            changed_blocks.append(parsed)

    ensure_directory(paths.build_patch_dir)
    if changed_blocks:
        patch_text = "\r\n".join(item.block.source.rstrip("\r\n") for item in changed_blocks) + "\r\n"
    else:
        patch_text = ""
    write_cp1252_crlf(paths.build_patch_blocks, patch_text)

    return len(changed_blocks)


def build_monolith(paths: WorkspacePaths) -> int:
    parsed_blocks = validate_workspace(paths)
    project_symbols = resolve_project_symbols_path(paths)

    ensure_directory(paths.build_monolith_dir)
    monolith_text = "\r\n".join(block.block.source.rstrip("\r\n") for block in parsed_blocks) + "\r\n"
    write_cp1252_crlf(paths.build_all_blocks, monolith_text)

    write_symbols_file(
        project_symbols,
        paths.build_monolith_dir / project_symbols.name,
        target_encoding="cp1252",
    )

    return len(parsed_blocks)
