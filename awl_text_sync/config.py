from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    exported_dir: Path
    project_dir: Path
    project_blocks_dir: Path
    project_symbols_dir: Path
    build_dir: Path
    build_monolith_dir: Path
    build_split_dir: Path
    exported_all_blocks: Path
    exported_all_blocks_symbols: Path
    exported_symbols: Path
    build_all_blocks: Path
    build_split_blocks_dir: Path
    build_split_symbols_dir: Path


def _find_single_file(directory: Path, suffix: str, label: str) -> Path:
    candidates = sorted(
        path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == suffix.lower()
    )
    if not candidates:
        raise FileNotFoundError(f"Missing {label}: expected exactly one *{suffix} file in {directory}")
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise FileExistsError(f"Multiple {label} files found in {directory}: {names}")
    return candidates[0]


def resolve_exported_monolith_path(paths: WorkspacePaths) -> Path:
    if not paths.exported_dir.exists():
        raise FileNotFoundError(f"Missing exported directory: {paths.exported_dir}")
    return _find_single_file(paths.exported_dir, ".awl", "monolith export")


def resolve_exported_symbols_path(paths: WorkspacePaths) -> Path:
    if not paths.exported_dir.exists():
        raise FileNotFoundError(f"Missing exported directory: {paths.exported_dir}")
    return _find_single_file(paths.exported_dir, ".sdf", "symbols export")


def resolve_project_symbols_path(paths: WorkspacePaths) -> Path:
    if not paths.project_symbols_dir.exists():
        raise FileNotFoundError(f"Missing symbols directory: {paths.project_symbols_dir}")
    return _find_single_file(paths.project_symbols_dir, ".sdf", "project symbols")


def resolve_workspace(root: str | Path | None = None) -> WorkspacePaths:
    workspace_root = Path(root or ".").resolve()
    exported_dir = workspace_root / "Exported"
    project_dir = workspace_root / "Project"
    project_blocks_dir = project_dir / "Blocks"
    project_symbols_dir = project_dir / "Symbols"
    build_dir = workspace_root / "Build"
    build_monolith_dir = build_dir / "Monolith"
    build_split_dir = build_dir / "SplitImport"

    return WorkspacePaths(
        root=workspace_root,
        exported_dir=exported_dir,
        project_dir=project_dir,
        project_blocks_dir=project_blocks_dir,
        project_symbols_dir=project_symbols_dir,
        build_dir=build_dir,
        build_monolith_dir=build_monolith_dir,
        build_split_dir=build_split_dir,
        exported_all_blocks=exported_dir / "ALL_BLOCKS.AWL",
        exported_all_blocks_symbols=exported_dir / "ALL_BLOCKS_SYMBOLS.AWL",
        exported_symbols=exported_dir / "Symbols.sdf",
        build_all_blocks=build_monolith_dir / "ALL_BLOCKS.AWL",
        build_split_blocks_dir=build_split_dir / "Blocks",
        build_split_symbols_dir=build_split_dir / "Symbols",
    )
