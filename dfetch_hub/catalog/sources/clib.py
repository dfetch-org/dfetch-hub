"""Parse the clib Packages.md wiki index and per-package package.json files."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dfetch.log import get_logger

from dfetch_hub.catalog.sources import (
    RAW_BRANCHES,
    BaseManifest,
    fetch_raw,
    fetch_readme,
    parse_vcs_slug,
    raw_url,
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
    for branch in RAW_BRANCHES:
        raw = fetch_raw(raw_url(owner, repo, branch, "package.json"))
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


def _build_urls(vcs_url: str, canonical_url: str | None) -> dict[str, str]:
    """Return the named-URL mapping for a clib entry.

    Always includes ``"Repository"``; adds ``"Homepage"`` when *canonical_url*
    differs from *vcs_url* (i.e. when ``package.json`` advertises a separate
    project website).
    """
    urls: dict[str, str] = {"Repository": vcs_url}
    if canonical_url and canonical_url != vcs_url:
        urls["Homepage"] = canonical_url
    return urls


def _str_or_none(value: object) -> str | None:
    """Return ``str(value)`` when *value* is truthy, else ``None``."""
    return str(value) if value else None


def _pkg_json_keywords(raw: object) -> list[str]:
    """Extract a flat keyword list from the ``keywords`` field of ``package.json``."""
    if isinstance(raw, list):
        return [str(k) for k in raw]
    if isinstance(raw, str):
        return [raw]
    return []


def _enrich_from_pkg_json(
    pkg_json: dict[str, object], vcs_url: str, tagline: str, repo: str
) -> tuple[str, str, str | None, str | None, list[str], str]:
    """Extract package metadata from ``package.json``.

    Args:
        pkg_json: Parsed ``package.json`` dict.
        vcs_url:  VCS repository URL used as the fallback homepage.
        tagline:  Description extracted from the wiki bullet (used when ``package.json`` has none).
        repo:     Repository name used as the fallback package name.

    Returns:
        ``(package_name, description, license, version, keywords, canonical_url)``
    """
    package_name = str(pkg_json.get("name") or repo)
    description = tagline or str(pkg_json.get("description") or "")
    license_val = _str_or_none(pkg_json.get("license"))
    version_val = _str_or_none(pkg_json.get("version"))
    json_kws = _pkg_json_keywords(pkg_json.get("keywords"))
    canonical_url = _str_or_none(pkg_json.get("homepage")) or vcs_url
    return package_name, description, license_val, version_val, json_kws, canonical_url


def _build_package(  # pylint: disable=too-many-locals
    host: str, owner: str, repo: str, tagline: str, category: str
) -> CLibPackage:
    """Build a :class:`CLibPackage` from a bullet entry and optional ``package.json``.

    For ``github.com`` entries the function fetches ``package.json`` and the
    README via raw content URLs (GitHub-specific).  For other VCS hosts the
    entry is created with only the information available from the wiki index
    (tagline, VCS URL) and no upstream enrichment.

    Args:
        host:     Lowercased VCS hostname (e.g. ``"github.com"``).
        owner:    Repository owner / organisation.
        repo:     Repository name.
        tagline:  Short description extracted from the wiki bullet.
        category: Nearest section heading (used as a keyword).

    Returns:
        A populated :class:`CLibPackage`.

    """
    vcs_url = f"https://{host}/{owner}/{repo}"
    is_github = host == "github.com"
    pkg_json = _fetch_package_json(owner, repo) if is_github else None

    if pkg_json is not None:
        package_name, description, license_val, version_val, json_kws, canonical_url = (
            _enrich_from_pkg_json(pkg_json, vcs_url, tagline, repo)
        )
    else:
        package_name, description, license_val, version_val, json_kws = (
            repo,
            tagline,
            None,
            None,
            [],
        )
        canonical_url = vcs_url

    keywords: list[str] = ([category] if category else []) + [
        k for k in json_kws if k != category
    ]
    return CLibPackage(
        entry_name=f"{host}/{owner}/{repo}",
        package_name=package_name,
        description=description,
        homepage=canonical_url,
        license=license_val,
        version=version_val,
        keywords=keywords,
        readme_content=fetch_readme(owner, repo) if is_github else None,
        urls=_build_urls(vcs_url, canonical_url),
    )


def _process_wiki_line(
    line: str, current_category: str
) -> tuple[str, CLibPackage | None]:
    """Process one Packages.md line; return updated category and optional package.

    Args:
        line:             A single line from ``Packages.md``.
        current_category: The most-recently seen section heading.

    Returns:
        A ``(category, package)`` pair where *category* may be updated and
        *package* is ``None`` for non-bullet or unrecognised lines.
    """
    heading_match = _HEADING_RE.match(line)
    if heading_match:
        return heading_match.group(1).strip(), None

    bullet_match = _BULLET_RE.match(line)
    if not bullet_match:
        return current_category, None

    _link_text, url, tagline = bullet_match.groups()
    parsed = parse_vcs_slug(url)
    if not parsed:
        logger.debug("Skipping URL without recognized VCS host in Packages.md: %s", url)
        return current_category, None

    host, owner, repo = parsed
    return current_category, _build_package(
        host, owner, repo, (tagline or "").strip(), current_category
    )


def parse_packages_md(
    packages_md: "Path", limit: int | None = None
) -> list[CLibPackage]:
    """Parse ``Packages.md`` from the clib wiki into a list of :class:`CLibPackage`.

    For each bullet-point entry the function:

    1. Extracts the VCS URL and tagline.
    2. Records the nearest ``## Heading`` as a *category* keyword.
    3. Fetches the repo's ``package.json`` via HTTPS for richer metadata
       (GitHub-hosted repos only; other VCS hosts get basic metadata only).

    Args:
        packages_md: Path to the ``Packages.md`` file.
        limit:       Maximum number of packages to return.  ``None`` = unlimited.

    Returns:
        A list of :class:`CLibPackage` instances, one per discovered repo.
    """
    packages: list[CLibPackage] = []
    current_category: str = ""

    for line in packages_md.read_text(encoding="utf-8").splitlines():
        if limit is not None and len(packages) >= limit:
            break
        current_category, pkg = _process_wiki_line(line, current_category)
        if pkg is not None:
            packages.append(pkg)

    return packages
