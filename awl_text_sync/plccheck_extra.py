"""Optional `plccheck check` integration (Dynamic Siemens / npm CLI)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class PlccheckError(Exception):
    """Configuration or environment error before invoking plccheck."""


def plc_root_has_config(plc_root: Path) -> bool:
    return (plc_root.resolve() / ".plc.json").is_file()


def _npx_executable() -> str | None:
    if sys.platform == "win32":
        return shutil.which("npx.cmd") or shutil.which("npx")
    return shutil.which("npx")


def run_plccheck_check(plc_root: Path, *, timeout_sec: float = 300.0) -> subprocess.CompletedProcess[str]:
    """
    Run `plccheck check <plc_root>` using `plccheck` on PATH or `npx --yes plccheck`.

    stdout/stderr are captured for callers to print.
    """
    root = plc_root.resolve()
    if not plc_root_has_config(root):
        raise PlccheckError(f"No .plc.json under {root}")
    plccheck_exe = shutil.which("plccheck")
    if plccheck_exe:
        cmd = [plccheck_exe, "check", str(root)]
    else:
        npx = _npx_executable()
        if not npx:
            raise PlccheckError(
                "Neither 'plccheck' nor 'npx' was found on PATH. "
                "Install Node.js or add plccheck to PATH."
            )
        cmd = [npx, "--yes", "plccheck", "check", str(root)]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
