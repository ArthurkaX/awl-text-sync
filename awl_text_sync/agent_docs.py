from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .config import WorkspacePaths


AGENT_DOC_FILES = (
    "AGENTS.md",
    "docs/working_rules.md",
    "docs/awl_reference.md",
)


@dataclass(frozen=True)
class AgentDocsResult:
    created: tuple[Path, ...]
    overwritten: tuple[Path, ...]
    skipped: tuple[Path, ...]


def _template_text(relative_path: str) -> str:
    template = resources.files(__package__) / "templates" / "agent_docs" / relative_path
    return template.read_text(encoding="utf-8")


def write_agent_docs(paths: WorkspacePaths, *, force: bool = False) -> AgentDocsResult:
    created: list[Path] = []
    overwritten: list[Path] = []
    skipped: list[Path] = []

    for relative_path in AGENT_DOC_FILES:
        target = paths.root / relative_path
        if target.exists() and not force:
            skipped.append(target)
            continue

        text = _template_text(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        target.write_text(text, encoding="utf-8", newline="\n")

        if existed:
            overwritten.append(target)
        else:
            created.append(target)

    return AgentDocsResult(
        created=tuple(created),
        overwritten=tuple(overwritten),
        skipped=tuple(skipped),
    )
