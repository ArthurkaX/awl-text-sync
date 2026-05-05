"""Core package for STEP 7 text sync workflows."""

from .builder import build_monolith, build_patch, build_split_import
from .splitter import split_exported_workspace
from .validator import validate_workspace

APP_NAME = "awl-text-sync"
LEGACY_APP_NAME = "s7p-sync"
PACKAGE_NAME = "awl_text_sync"

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version(PACKAGE_NAME)
except Exception:
    __version__ = "1.1.0"

__all__ = [
    "APP_NAME",
    "__version__",
    "build_monolith",
    "build_patch",
    "build_split_import",
    "LEGACY_APP_NAME",
    "PACKAGE_NAME",
    "split_exported_workspace",
    "validate_workspace",
]
