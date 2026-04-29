from __future__ import annotations

import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path

try:
    from . import APP_NAME
    from .call_graph import build_call_graph, default_call_graph_report_path, write_call_graph_report
    from .builder import build_monolith, build_split_import
    from .config import resolve_workspace
    from .plccheck_extra import PlccheckError, run_plccheck_check
    from .splitter import split_exported_workspace
    from .ui import launch_ui
    from .validator import validate_workspace
    from .parser import ParseError
except ImportError:  # pragma: no cover - script/PyInstaller fallback
    from awl_text_sync import APP_NAME
    from awl_text_sync.call_graph import build_call_graph, default_call_graph_report_path, write_call_graph_report
    from awl_text_sync.builder import build_monolith, build_split_import
    from awl_text_sync.config import resolve_workspace
    from awl_text_sync.splitter import split_exported_workspace
    from awl_text_sync.plccheck_extra import PlccheckError, run_plccheck_check
    from awl_text_sync.ui import launch_ui
    from awl_text_sync.parser import ParseError
    from awl_text_sync.validator import validate_workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_NAME)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("."),
        help="Workspace root containing Exported/, Project/, and Build/",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("split", help="Split the single Exported/*.AWL file into Project/Blocks/ using names like fb68.awl")
    validate_parser = subparsers.add_parser("validate", help="Validate Project/Blocks/ and Project/Symbols/")
    validate_parser.add_argument(
        "--call-graph",
        action="store_true",
        help="Write an interactive call graph report under Build/Reports/call_graph.html",
    )
    validate_parser.add_argument(
        "--open-call-graph",
        action="store_true",
        help="Open the call graph report in the default browser after writing it",
    )
    validate_parser.add_argument(
        "--plccheck-root",
        type=Path,
        default=None,
        help="After native validate, run `plccheck check` on this folder (must contain .plc.json); "
        "optional; requires Node/npm if plccheck is not on PATH",
    )
    subparsers.add_parser("build-split", help="Build split import output under Build/SplitImport/")
    subparsers.add_parser("build-monolith", help="Build ALL_BLOCKS.AWL under Build/Monolith/")
    subparsers.add_parser("ui", help="Launch the desktop UI")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    paths = resolve_workspace(args.workspace)

    if args.command == "split":
        count = split_exported_workspace(paths)
        print(f"Split {count} blocks into {paths.project_blocks_dir}")
        return 0

    if args.command == "validate":
        try:
            parsed = validate_workspace(paths)
        except ParseError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Validated {len(parsed)} blocks in {paths.project_blocks_dir}")
        if getattr(args, "call_graph", False):
            graph = build_call_graph(parsed)
            report_path = default_call_graph_report_path(paths)
            try:
                write_call_graph_report(graph, paths.root, report_path)
            except OSError as exc:
                print(f"Call graph report not written: {exc}")
            else:
                print(f"Wrote call graph report to {report_path}")
                if getattr(args, "open_call_graph", False):
                    webbrowser.open(report_path.resolve().as_uri())
        if args.plccheck_root is not None:
            try:
                proc = run_plccheck_check(args.plccheck_root)
            except PlccheckError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            except OSError as exc:
                print(f"plccheck failed to start: {exc}", file=sys.stderr)
                return 1
            except subprocess.TimeoutExpired:
                print("plccheck check timed out", file=sys.stderr)
                return 1
            if proc.stdout:
                print(proc.stdout, end="")
            if proc.stderr:
                print(proc.stderr, end="", file=sys.stderr)
            if proc.returncode != 0:
                return proc.returncode
        return 0

    if args.command == "build-split":
        count = build_split_import(paths)
        print(f"Built split import set with {count} blocks in {paths.build_split_dir}")
        return 0

    if args.command == "build-monolith":
        count = build_monolith(paths)
        print(f"Built monolith with {count} blocks at {paths.build_all_blocks}")
        return 0

    if args.command == "ui":
        launch_ui(args.workspace)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
