from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from awl_text_sync.plccheck_extra import _npx_executable

REPO_ROOT = Path(__file__).resolve().parents[1]
PLCCHECK_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "plccheck_demo_minimal"


@pytest.mark.integration
def test_plccheck_minimal_fixture_exits_zero() -> None:
    """Live `plccheck check` on synthetic fixture; skip unless RUN_PLCCHECK_INTEGRATION=1."""
    if os.environ.get("RUN_PLCCHECK_INTEGRATION") != "1":
        pytest.skip("Set RUN_PLCCHECK_INTEGRATION=1 to run live plccheck (requires Node/npm).")
    assert (PLCCHECK_FIXTURE / ".plc.json").is_file()
    npx = _npx_executable()
    if not npx:
        pytest.skip("npx not on PATH")
    result = subprocess.run(
        [npx, "--yes", "plccheck", "check", str(PLCCHECK_FIXTURE)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


@pytest.mark.integration
def test_combined_validate_and_plccheck_exits_zero() -> None:
    """Native validate + optional plccheck root (Windows npx.cmd resolved in plccheck_extra)."""
    if os.environ.get("RUN_PLCCHECK_INTEGRATION") != "1":
        pytest.skip("Set RUN_PLCCHECK_INTEGRATION=1 for end-to-end CLI check.")
    classic = REPO_ROOT / "tests" / "fixtures" / "classic_demo_workspace"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "awl_text_sync.main",
            "--workspace",
            str(classic),
            "validate",
            "--plccheck-root",
            str(PLCCHECK_FIXTURE),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
