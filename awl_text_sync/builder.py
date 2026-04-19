from __future__ import annotations

from .config import WorkspacePaths, resolve_project_symbols_path
from .symbols import write_symbols_file
from .validator import validate_workspace
from .writer import ensure_directory, write_cp1252_crlf


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
