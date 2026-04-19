from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


UTF8_BOM = b"\xef\xbb\xbf"
SUSPICIOUS_MOJIBAKE_SEQUENCES = (
    "Ã",
    "Â",
    "┬",
    "├",
    "�",
)


@dataclass(frozen=True)
class DecodedText:
    text: str
    encoding: str


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_mixed_text(path: Path) -> DecodedText:
    raw = path.read_bytes()
    if raw.startswith(UTF8_BOM):
        return DecodedText(raw.decode("utf-8-sig"), "utf-8-sig")

    try:
        return DecodedText(raw.decode("utf-8"), "utf-8")
    except UnicodeDecodeError:
        pass

    for encoding in ("cp1252", "cp437", "latin-1"):
        try:
            return DecodedText(raw.decode(encoding), encoding)
        except UnicodeDecodeError:
            continue

    return DecodedText(raw.decode("latin-1"), "latin-1")


def write_utf8_text(path: Path, text: str) -> None:
    normalized = normalize_newlines(text)
    path.write_text(normalized.replace("\n", "\r\n"), encoding="utf-8", newline="")


def write_cp1252_text(path: Path, text: str) -> None:
    normalized = normalize_newlines(text)
    path.write_bytes(normalized.replace("\n", "\r\n").encode("cp1252"))


def find_non_cp1252_characters(text: str) -> list[str]:
    invalid: list[str] = []
    seen: set[str] = set()
    for char in text:
        if char in {"\r", "\n", "\t"}:
            continue
        try:
            char.encode("cp1252")
        except UnicodeEncodeError:
            if char not in seen:
                invalid.append(char)
                seen.add(char)
    return invalid


def contains_suspicious_mojibake(text: str) -> bool:
    return any(token in text for token in SUSPICIOUS_MOJIBAKE_SEQUENCES)
