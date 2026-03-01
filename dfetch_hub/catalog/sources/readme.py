"""Parse a source directory that contains only a README (no structured manifest)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from dfetch.log import get_logger

from dfetch_hub.catalog.sources import BaseManifest

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_README_NAMES = ("README.md", "readme.md", "Readme.md", "README.rst", "README")

_HEADING_RE = re.compile(r"^#+\s+")
_BADGE_RE = re.compile(r"^\[!\[")
_BLANK_RE = re.compile(r"^\s*$")
_DESCRIPTION_MAX = 120


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
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if _BLANK_RE.match(line) or _HEADING_RE.match(line) or _BADGE_RE.match(line):
            continue
        stripped = line.strip()
        if stripped:
            return stripped[:_DESCRIPTION_MAX]
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

    This parser is the building-block for the ``readme-only`` strategy, where
    packages have no structured manifest file — only a README.

    Args:
        entry_dir: Directory to scan.

    Returns:
        A :class:`~dfetch_hub.catalog.sources.BaseManifest` populated from the
        README, or ``None`` if no README file is found.

    """
    for name in _README_NAMES:
        readme_path = entry_dir / name
        if readme_path.exists():
            text = readme_path.read_text(errors="replace")
            entry_name = entry_dir.name
            return BaseManifest(
                entry_name=entry_name,
                package_name=entry_name,
                description=_extract_description(text),
                homepage=None,
                license=None,
                version=None,
                readme_content=text,
            )
    logger.debug("No README found in %s — skipped", entry_dir)
    return None
