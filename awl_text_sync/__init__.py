"""Core package for STEP 7 text sync workflows."""

from .builder import build_monolith, build_split_import
from .splitter import split_exported_workspace
from .validator import validate_workspace

APP_NAME = "awl-text-sync"
LEGACY_APP_NAME = "s7p-sync"
PACKAGE_NAME = "awl_text_sync"

__all__ = [
    "APP_NAME",
    "build_monolith",
    "build_split_import",
    "LEGACY_APP_NAME",
    "PACKAGE_NAME",
    "split_exported_workspace",
    "validate_workspace",
]
