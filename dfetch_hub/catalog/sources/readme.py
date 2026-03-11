"""Parse a source directory that contains only a README (no structured manifest)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from dfetch.log import get_logger

from dfetch_hub.catalog.sources import CHANGELOG_NAMES, BaseManifest

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_README_NAMES = ("README.md", "readme.md", "Readme.md", "README.rst", "README")

# Matches lines that should be skipped: blank, Markdown headings, or badge links.
_SKIP_RE = re.compile(r"^(#+\s+|\[!\[|\s*$)")
_DESCRIPTION_MAX = 120


def _is_content_line(line: str, in_code_block: bool) -> bool:
    """Return ``True`` if *line* is a prose content line worth using as a description."""
    return not in_code_block and not _SKIP_RE.match(line.lstrip()) and bool(line.strip())


def _extract_description(text: str) -> str:
    """Extract the first meaningful line from *text* as a short description.

    Skips blank lines, Markdown headings (``# …``), inline-badge lines
    (``[![…``), and fenced code-block content.  Returns the first remaining
    line, truncated to :data:`_DESCRIPTION_MAX` characters.

    Args:
        text: Raw README content.

    Returns:
        A short description string, or an empty string if nothing suitable
        is found.

    """
    in_code_block = False
    for line in text.splitlines():
        if line.startswith(("```", "~~~")):
            in_code_block = not in_code_block
            continue
        if _is_content_line(line, in_code_block):
            return line.strip()[:_DESCRIPTION_MAX]
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_readme_dir(entry_dir: Path) -> BaseManifest | None:
    """Build a :class:`~dfetch_hub.catalog.sources.BaseManifest` from a README.

    Scans *entry_dir* for the first README file it can find (``README.md``,
    ``readme.md``, ``README.rst``, etc.), reads its content, and constructs a
    minimal :class:`~dfetch_hub.catalog.sources.BaseManifest` using the folder
    name as both ``entry_name`` and ``package_name``.

    This parser is used with the ``subfolders`` strategy (``manifest = "readme"``)
    for repositories where packages have no structured manifest file — only a README.

    Args:
        entry_dir: Directory to scan.

    Returns:
        A :class:`~dfetch_hub.catalog.sources.BaseManifest` populated from the
        README, or ``None`` if no README file is found.

    """
    readme_content = None
    for name in _README_NAMES:
        readme_path = entry_dir / name
        if readme_path.is_file():
            try:
                readme_content = readme_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.debug("Could not read %s: %s — skipped", readme_path, exc)
                return None
            break
    if readme_content is None:
        logger.debug("No README found in %s — skipped", entry_dir)
        return None

    changelog_content = None
    for name in CHANGELOG_NAMES:
        changelog_path = entry_dir / name
        if changelog_path.is_file():
            try:
                changelog_content = changelog_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.debug("Could not read %s: %s", changelog_path, exc)
            break

    entry_name = entry_dir.name
    return BaseManifest(
        entry_name=entry_name,
        package_name=entry_name,
        description=_extract_description(readme_content),
        homepage=None,
        license=None,
        version=None,
        readme_content=readme_content,
        changelog_content=changelog_content,
        in_project_repo=True,
    )
