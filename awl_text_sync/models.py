from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


def slugify_symbol_name(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"^(udt|db|fb|fc|ob)[ _-]*", "", lowered)
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered).strip("_")
    return lowered


def filename_component(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned


@dataclass(frozen=True)
class Block:
    block_type: str
    number: int
    source: str
    symbol_name: str | None = None
    internal_name: str | None = None

    @property
    def filename(self) -> str:
        base = f"{self.block_type.lower()}{self.number}"
        preferred_name = self.symbol_name or self.internal_name
        if not preferred_name:
            return f"{base}.awl"
        suffix = filename_component(preferred_name)
        if not suffix:
            return f"{base}.awl"
        return f"{base}_{suffix}.awl"


@dataclass(frozen=True)
class ParsedBlockFile:
    path: Path
    block: Block
