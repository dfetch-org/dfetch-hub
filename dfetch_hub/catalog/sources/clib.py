"""Parse the clib Packages.md wiki index and per-package package.json files."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dfetch.log import get_logger

from dfetch_hub.catalog.sources import (
    _RAW_BRANCHES,
    BaseManifest,
    _fetch_raw,
    _raw_url,
    fetch_readme,
    parse_github_slug,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

# Matches a Markdown bullet with a link: " - [text](url) - tagline"
# The clib wiki uses " - " as the bullet character.
_BULLET_RE = re.compile(r"^\s*-\s+\[([^\]]+)\]\((https?://[^\)]+)\)\s*(?:-\s*(.+))?$")

# Category heading: "## Some Category"
_HEADING_RE = re.compile(r"^#{1,4}\s+(.+)$")


@dataclass
class CLibPackage(BaseManifest):
    """Parsed representation of a single clib package entry.

    Attributes:
        keywords: Category from Packages.md plus keywords from package.json.
    """

    keywords: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# package.json fetching
# ---------------------------------------------------------------------------


def _fetch_package_json(owner: str, repo: str) -> dict[str, object] | None:
    """Try to download ``package.json`` from the GitHub repo.

    Tries ``main`` then ``master`` branch.  Returns ``None`` on failure.
    """
    for branch in _RAW_BRANCHES:
        raw = _fetch_raw(_raw_url(owner, repo, branch, "package.json"))
        if raw is None:
            continue
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.debug("Bad JSON in package.json for %s/%s: %s", owner, repo, exc)
            continue
        if not isinstance(loaded, dict):
            logger.debug("Ignoring non-object package.json for %s/%s", owner, repo)
            continue
        data: dict[str, object] = loaded
        logger.debug("Fetched package.json for %s/%s from %s", owner, repo, branch)
        return data
    return None


# ---------------------------------------------------------------------------
# Packages.md parsing
# ---------------------------------------------------------------------------


def _build_package(owner: str, repo: str, tagline: str, category: str) -> CLibPackage:
    """Build a :class:`CLibPackage` from a bullet entry and its ``package.json``."""
    github_url = f"https://github.com/{owner}/{repo}"
    pkg_json = _fetch_package_json(owner, repo)

    if pkg_json is not None:
        package_name = str(pkg_json.get("name") or repo)
        description = tagline or str(pkg_json.get("description") or "")
        license_val = str(pkg_json.get("license") or "") or None
        version_val = str(pkg_json.get("version") or "") or None
        raw_keywords = pkg_json.get("keywords")
        if isinstance(raw_keywords, list):
            json_kws: list[str] = [str(k) for k in raw_keywords]
        elif isinstance(raw_keywords, str):
            json_kws = [raw_keywords]
        else:
            json_kws = []
        # Prefer an explicit homepage from package.json (e.g. project website);
        # fall back to the GitHub repo URL so the field is always populated.
        canonical_url: str | None = str(pkg_json.get("homepage") or "") or github_url
    else:
        package_name = repo
        description = tagline
        license_val = None
        version_val = None
        json_kws = []
        canonical_url = github_url

    keywords: list[str] = ([category] if category else []) + [
        k for k in json_kws if k != category
    ]
    return CLibPackage(
        port_name=f"{owner}/{repo}",
        package_name=package_name,
        description=description,
        homepage=canonical_url,
        license=license_val,
        version=version_val,
        keywords=keywords,
        readme_content=fetch_readme(owner, repo),
    )


def parse_packages_md(
    packages_md: "Path", limit: int | None = None
) -> list[CLibPackage]:
    """Parse ``Packages.md`` from the clib wiki into a list of :class:`CLibPackage`.

    For each bullet-point entry the function:

    1. Extracts the GitHub URL and tagline.
    2. Records the nearest ``## Heading`` as a *category* keyword.
    3. Fetches the repo's ``package.json`` (via HTTPS) for richer metadata.

    Args:
        packages_md: Path to the ``Packages.md`` file.
        limit:       Maximum number of packages to return.  ``None`` = unlimited.

    Returns:
        A list of :class:`CLibPackage` instances, one per discovered repo.
    """
    packages: list[CLibPackage] = []
    current_category: str = ""

    for line in packages_md.read_text(encoding="utf-8").splitlines():
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            current_category = heading_match.group(1).strip()
            continue

        bullet_match = _BULLET_RE.match(line)
        if not bullet_match:
            continue

        _link_text, url, tagline = bullet_match.groups()
        parsed = parse_github_slug(url)
        if not parsed:
            logger.debug("Skipping non-GitHub URL in Packages.md: %s", url)
            continue

        if limit is not None and len(packages) >= limit:
            break

        owner, repo = parsed
        packages.append(
            _build_package(owner, repo, (tagline or "").strip(), current_category)
        )

    return packages
