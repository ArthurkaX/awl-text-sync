from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from awl_text_sync.plccheck_extra import PlccheckError, plc_root_has_config, run_plccheck_check


class TestPlccheckExtra(unittest.TestCase):
    def test_plc_root_has_config_false_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(plc_root_has_config(Path(td)))

    def test_plc_root_has_config_true_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".plc.json").write_text("{}", encoding="utf-8")
            self.assertTrue(plc_root_has_config(root))

    def test_run_plccheck_check_raises_without_plc_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(PlccheckError) as ctx:
                run_plccheck_check(root)
            self.assertIn(".plc.json", str(ctx.exception))

    def test_run_plccheck_check_invokes_plccheck_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".plc.json").write_text("{}", encoding="utf-8")
            fake = subprocess.CompletedProcess(
                args=["plccheck", "check", str(root.resolve())],
                returncode=0,
                stdout="ok\n",
                stderr="",
            )
            with patch("awl_text_sync.plccheck_extra.shutil.which", return_value="plccheck"):
                with patch("awl_text_sync.plccheck_extra.subprocess.run", return_value=fake) as run_mock:
                    proc = run_plccheck_check(root)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("ok", proc.stdout)
            run_mock.assert_called_once()
            args, kwargs = run_mock.call_args
            self.assertEqual(args[0], ["plccheck", "check", str(root.resolve())])
            self.assertTrue(kwargs.get("capture_output"))

    def test_run_plccheck_check_falls_back_to_npx(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".plc.json").write_text("{}", encoding="utf-8")
            fake = subprocess.CompletedProcess(
                args=["npx", "--yes", "plccheck", "check", str(root.resolve())],
                returncode=0,
                stdout="",
                stderr="",
            )
            with patch("awl_text_sync.plccheck_extra.shutil.which", return_value=None):
                with patch("awl_text_sync.plccheck_extra.subprocess.run", return_value=fake) as run_mock:
                    run_plccheck_check(root)
            run_mock.assert_called_once()
            self.assertEqual(
                run_mock.call_args[0][0],
                ["npx", "--yes", "plccheck", "check", str(root.resolve())],
            )


if __name__ == "__main__":
    unittest.main()
