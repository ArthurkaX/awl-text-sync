from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

try:
    from . import APP_NAME
    from .agent_docs import write_agent_docs
    from .call_graph import build_call_graph, default_call_graph_report_path, write_call_graph_report
    from .builder import build_monolith, build_patch, build_split_import
    from .config import resolve_workspace
    from .splitter import split_exported_workspace
    from .ui import launch_ui
    from .validator import validate_workspace
    from .parser import ParseError
except ImportError:  # pragma: no cover - script/PyInstaller fallback
    from awl_text_sync import APP_NAME
    from awl_text_sync.agent_docs import write_agent_docs
    from awl_text_sync.call_graph import build_call_graph, default_call_graph_report_path, write_call_graph_report
    from awl_text_sync.builder import build_monolith, build_patch, build_split_import
    from awl_text_sync.config import resolve_workspace
    from awl_text_sync.splitter import split_exported_workspace
    from awl_text_sync.ui import launch_ui
    from awl_text_sync.parser import ParseError
    from awl_text_sync.validator import validate_workspace


def build_parser() -> argparse.ArgumentParser:
    try:
        from . import __version__
    except ImportError:  # pragma: no cover - script/PyInstaller fallback
        from awl_text_sync import __version__

    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=(
            "STEP 7 AWL workspace text sync tool.\n"
            "Split, validate, and build AWL block files for STEP 7 import/export.\n"
            "Run without arguments to launch the desktop GUI."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("."),
        help="Workspace root containing Exported/, Project/, and Build/ (default: .)",
    )

    workspace_parent = argparse.ArgumentParser(add_help=False)
    workspace_parent.add_argument(
        "--workspace",
        type=Path,
        default=argparse.SUPPRESS,
        help="Workspace root containing Exported/, Project/, and Build/ (default: .)",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
    )

    subparsers.add_parser(
        "split",
        parents=[workspace_parent],
        help="Split Exported/*.AWL into Project/Blocks/",
        description=(
            "Read the single exported .AWL file from Exported/ and split it into\n"
            "individual block files under Project/Blocks/.\n"
            "Each block gets a file named like fb68.awl.\n"
            "Also copies the .sdf symbols file to Project/Symbols/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    validate_parser = subparsers.add_parser(
        "validate",
        parents=[workspace_parent],
        help="Validate Project/Blocks/ and Project/Symbols/",
        description=(
            "Parse all .awl block files in Project/Blocks/ and the .sdf symbols file\n"
            "in Project/Symbols/. Reports syntax errors and consistency issues."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    validate_parser.add_argument(
        "--call-graph",
        action="store_true",
        help="Write an interactive call graph HTML report under Build/Reports/",
    )
    validate_parser.add_argument(
        "--open-call-graph",
        action="store_true",
        help="Open the call graph report in the default browser",
    )

    subparsers.add_parser(
        "build-split",
        parents=[workspace_parent],
        help="Build split import output under Build/SplitImport/",
        description=(
            "Build a set of individual .awl files and a .sdf file under\n"
            "Build/SplitImport/, ready for import into STEP 7."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers.add_parser(
        "build-monolith",
        parents=[workspace_parent],
        help="Build ALL_BLOCKS.AWL under Build/Monolith/",
        description=(
            "Combine all Project/Blocks/*.awl files into a single\n"
            "ALL_BLOCKS.AWL file under Build/Monolith/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers.add_parser(
        "build-patch",
        parents=[workspace_parent],
        help="Build changed blocks only under Build/Patch/",
        description=(
            "Compare Project/Blocks/ against the original Exported/*.AWL source\n"
            "and write only changed or new blocks to Build/Patch/PATCH_BLOCKS.AWL."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    agent_docs_parser = subparsers.add_parser(
        "init-agent-docs",
        parents=[workspace_parent],
        help="Create agent/AI bootstrap docs in the workspace",
        description=(
            "Create AGENTS.md and documentation files in the workspace root.\n"
            "These files help AI coding agents understand the project structure."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    agent_docs_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing agent docs instead of skipping them",
    )

    subparsers.add_parser(
        "ui",
        parents=[workspace_parent],
        help="Launch the desktop GUI",
        description="Launch the awl-text-sync desktop GUI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    paths = resolve_workspace(args.workspace)

    if args.command is None:
        launch_ui(args.workspace)
        return 0

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
        return 0

    if args.command == "build-split":
        count = build_split_import(paths)
        print(f"Built split import set with {count} blocks in {paths.build_split_dir}")
        return 0

    if args.command == "build-monolith":
        count = build_monolith(paths)
        print(f"Built monolith with {count} blocks at {paths.build_all_blocks}")
        return 0

    if args.command == "build-patch":
        count = build_patch(paths)
        print(f"Built patch with {count} changed block(s) at {paths.build_patch_blocks}")
        return 0

    if args.command == "init-agent-docs":
        result = write_agent_docs(paths, force=getattr(args, "force", False))
        for path in result.created:
            print(f"Created {path}")
        for path in result.overwritten:
            print(f"Overwrote {path}")
        for path in result.skipped:
            print(f"Skipped existing {path}")
        return 0

    if args.command == "ui":
        launch_ui(args.workspace)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
