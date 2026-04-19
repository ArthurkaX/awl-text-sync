from __future__ import annotations

from dataclasses import replace
import ctypes
import re
import stat
import time
from pathlib import Path
from uuid import uuid4

from .config import WorkspacePaths, resolve_exported_monolith_path, resolve_exported_symbols_path
from .encoding import read_mixed_text
from .parser import parse_monolith_blocks
from .symbols import load_reverse_symbol_index, load_symbol_index, write_symbols_file
from .writer import ensure_directory, ensure_workspace_gitignore, ensure_workspace_rules, write_utf8_crlf


def _select_monolith_source(paths: WorkspacePaths) -> Path:
    return resolve_exported_monolith_path(paths)


def _read_monolith_text(path: Path) -> str:
    return read_mixed_text(path).text


def _block_identity_from_filename(path: Path) -> tuple[str, int] | None:
    match = re.fullmatch(r"([a-z]+)(\d+)(?:_.+)?", path.stem, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).upper(), int(match.group(2))


def _remove_file(path: Path) -> None:
    file_path = str(path)
    for attempt in range(20):
        try:
            path.chmod(stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
        try:
            attributes = ctypes.windll.kernel32.GetFileAttributesW(file_path)
            if attributes != -1 and attributes & 0x1:
                ctypes.windll.kernel32.SetFileAttributesW(file_path, 0)
        except Exception:
            pass
        try:
            path.unlink()
            return
        except PermissionError:
            time.sleep(0.05 * (attempt + 1))
    try:
        quarantine_path = path.with_name(f"{path.stem}.delete_{uuid4().hex}{path.suffix}")
        path.rename(quarantine_path)
        quarantine_path.unlink()
    except OSError:
        return


def split_exported_workspace(paths: WorkspacePaths) -> int:
    monolith_source = _select_monolith_source(paths)
    exported_symbols = resolve_exported_symbols_path(paths)

    ensure_workspace_gitignore(paths.root)
    ensure_workspace_rules(paths.root)
    ensure_directory(paths.project_blocks_dir)
    ensure_directory(paths.project_symbols_dir)

    symbol_index = load_symbol_index(exported_symbols)
    reverse_symbol_index = load_reverse_symbol_index(exported_symbols)
    monolith_text = _read_monolith_text(monolith_source)
    blocks = parse_monolith_blocks(monolith_text, symbol_index=symbol_index)

    next_numbers: dict[str, int] = {}
    for block in blocks:
        if block.number >= 0:
            next_numbers[block.block_type] = max(next_numbers.get(block.block_type, 0), block.number)
    for index, block in enumerate(blocks):
        if block.number >= 0:
            continue
        next_numbers[block.block_type] = next_numbers.get(block.block_type, 0) + 1
        blocks[index] = replace(block, number=next_numbers[block.block_type])

    normalized_blocks = [
        replace(
            block,
            symbol_name=block.symbol_name or reverse_symbol_index.get((block.block_type, block.number)),
        )
        for block in blocks
    ]

    target_filenames = {
        (block.block_type, block.number): block.filename
        for block in normalized_blocks
    }

    for existing_path in paths.project_blocks_dir.glob("*.awl"):
        identity = _block_identity_from_filename(existing_path)
        if identity is None or identity not in target_filenames:
            continue
        if existing_path.name != target_filenames[identity]:
            _remove_file(existing_path)

    for block in normalized_blocks:
        write_utf8_crlf(paths.project_blocks_dir / block.filename, block.source)

    write_symbols_file(
        exported_symbols,
        paths.project_symbols_dir / exported_symbols.name,
        target_encoding="utf-8",
    )

    return len(normalized_blocks)
