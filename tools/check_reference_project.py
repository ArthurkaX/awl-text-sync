from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _copy_reference_project(source: Path, destination: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        ignored = {".git", "Build", "__pycache__"}
        return {name for name in names if name in ignored}

    shutil.copytree(source, destination, ignore=ignore)


def _run_awl_text_sync(workspace: Path, *args: str) -> None:
    command = [
        sys.executable,
        "-m",
        "awl_text_sync.main",
        "--workspace",
        str(workspace),
        *args,
    ]
    subprocess.run(command, check=True)


def check_reference_project(source: Path, *, keep_copy: bool = False) -> Path | None:
    if not source.exists():
        raise FileNotFoundError(f"Reference project does not exist: {source}")
    if not (source / "Project" / "Blocks").is_dir():
        raise FileNotFoundError(f"Reference project has no Project/Blocks folder: {source}")

    temp_root = Path(tempfile.mkdtemp(prefix="awl-text-sync-ref-"))
    workspace = temp_root / source.name
    try:
        _copy_reference_project(source, workspace)
        _run_awl_text_sync(workspace, "validate")
        _run_awl_text_sync(workspace, "validate", "--call-graph")
        _run_awl_text_sync(workspace, "build-monolith")
        _run_awl_text_sync(workspace, "build-split")
    except Exception:
        if keep_copy:
            print(f"Kept failed workspace copy at {workspace}", file=sys.stderr)
        else:
            shutil.rmtree(temp_root, ignore_errors=True)
        raise

    if keep_copy:
        return workspace

    shutil.rmtree(temp_root, ignore_errors=True)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run awl-text-sync regression checks against an external reference project."
    )
    parser.add_argument("reference_project", type=Path)
    parser.add_argument(
        "--keep-copy",
        action="store_true",
        help="Keep the temporary workspace copy after the checks finish.",
    )
    args = parser.parse_args()

    kept_path = check_reference_project(args.reference_project.resolve(), keep_copy=args.keep_copy)
    if kept_path is not None:
        print(f"Reference project checks passed; kept workspace copy at {kept_path}")
    else:
        print("Reference project checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
