from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from awl_text_sync.agent_docs import write_agent_docs
from awl_text_sync.config import resolve_workspace
from awl_text_sync.main import build_parser
from awl_text_sync.ui import _run_agent_docs


class AgentDocsTests(unittest.TestCase):
    def test_write_agent_docs_creates_bootstrap_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_workspace(Path(tmp))

            result = write_agent_docs(paths)

            self.assertEqual(result.skipped, ())
            self.assertEqual(result.overwritten, ())
            self.assertEqual(
                {path.relative_to(paths.root).as_posix() for path in result.created},
                {
                    "AGENTS.md",
                    "docs/working_rules.md",
                    "docs/awl_reference.md",
                },
            )
            self.assertIn("STEP 7 AWL text workspace", (paths.root / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertIn("CALL Safety", (paths.root / "docs" / "working_rules.md").read_text(encoding="utf-8"))
            self.assertIn("Peripheral I/O", (paths.root / "docs" / "awl_reference.md").read_text(encoding="utf-8"))

    def test_write_agent_docs_skips_existing_files_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_workspace(Path(tmp))
            target = paths.root / "AGENTS.md"
            target.write_text("custom\n", encoding="utf-8")

            result = write_agent_docs(paths)

            self.assertEqual(target.read_text(encoding="utf-8"), "custom\n")
            self.assertIn(target, result.skipped)
            self.assertEqual(
                {path.relative_to(paths.root).as_posix() for path in result.created},
                {
                    "docs/working_rules.md",
                    "docs/awl_reference.md",
                },
            )

    def test_write_agent_docs_force_overwrites_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_workspace(Path(tmp))
            target = paths.root / "AGENTS.md"
            target.write_text("custom\n", encoding="utf-8")

            result = write_agent_docs(paths, force=True)

            self.assertNotEqual(target.read_text(encoding="utf-8"), "custom\n")
            self.assertIn(target, result.overwritten)
            self.assertEqual(result.skipped, ())

    def test_cli_accepts_workspace_after_subcommand(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["init-agent-docs", "--workspace", "workspace-root", "--force"])

        self.assertEqual(args.command, "init-agent-docs")
        self.assertEqual(args.workspace, Path("workspace-root"))
        self.assertTrue(args.force)

    def test_ui_agent_docs_action_reports_created_and_skipped_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_workspace(Path(tmp))

            self.assertEqual(_run_agent_docs(paths), "Agent docs: created 3, skipped 0, overwritten 0")
            self.assertEqual(_run_agent_docs(paths), "Agent docs: created 0, skipped 3, overwritten 0")


if __name__ == "__main__":
    unittest.main()
