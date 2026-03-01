"""Parse the clib Packages.md wiki index and per-package package.json files."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.error import URLError
from urllib.request import Request, urlopen

from dfetch.log import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_GITHUB_RE = re.compile(
    r"https?://github\.com/([^/\s\)]+)/([^/\s\)]+?)(?:\.git)?$",
    re.IGNORECASE,
)

# Matches a Markdown bullet with a link: " - [text](url) - tagline"
# The clib wiki uses " - " as the bullet character.
_BULLET_RE = re.compile(
    r"^\s*-\s+\[([^\]]+)\]\((https?://[^\)]+)\)\s*(?:-\s*(.+))?$"
)

# Category heading: "## Some Category"
_HEADING_RE = re.compile(r"^#{1,4}\s+(.+)$")

# Raw content URLs to try when fetching package.json (main before master)
_RAW_BRANCHES = ("main", "master")


@dataclass
class CLibPackage:
    """Parsed representation of a single clib package entry.

    Attributes:
        port_name:      ``owner/repo`` slug used as the index identifier.
        package_name:   ``name`` field from ``package.json``, or the repo name.
        description:    Tagline from Packages.md, possibly augmented from package.json.
        homepage:       Canonical project URL: ``homepage`` from ``package.json`` when
                        present, otherwise the GitHub repo URL.
        license:        License from ``package.json``, or ``None``.
        version:        Version from ``package.json``, or ``None``.
        keywords:       Category from Packages.md plus keywords from package.json.
        readme_content: Raw README.md text fetched from the upstream repo, or ``None``.
    """

    port_name: str
    package_name: str
    description: str
    homepage: str | None
    license: str | None
    version: str | None
    keywords: list[str] = field(default_factory=list)
    readme_content: str | None = None


# ---------------------------------------------------------------------------
# package.json fetching
# ---------------------------------------------------------------------------


_HEADERS = {"User-Agent": "dfetch-hub/0.0.1"}

_README_NAMES = ("README.md", "readme.md", "Readme.md", "README.rst", "README")


def _raw_url(owner: str, repo: str, branch: str, filename: str) -> str:
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"


def _fetch_raw(url: str) -> str | None:
    """GET *url* and return the response body as a string, or ``None`` on failure."""
    try:
        req = Request(url, headers=_HEADERS)
        with urlopen(req, timeout=10) as resp:
            return str(resp.read().decode(errors="replace"))
    except (URLError, OSError) as exc:
        logger.debug("GET %s failed: %s", url, exc)
        return None


def _fetch_package_json(owner: str, repo: str) -> dict[str, object] | None:
    """Try to download ``package.json`` from the GitHub repo.

    Tries ``main`` then ``master`` branch.  Returns ``None`` on failure.
    """
    for branch in _RAW_BRANCHES:
        raw = _fetch_raw(_raw_url(owner, repo, branch, "package.json"))
        if raw is None:
            continue
        try:
            data: dict[str, object] = json.loads(raw)
            logger.debug("Fetched package.json for %s/%s from %s", owner, repo, branch)
            return data
        except json.JSONDecodeError as exc:
            logger.debug("Bad JSON in package.json for %s/%s: %s", owner, repo, exc)
    return None


def _fetch_readme(owner: str, repo: str) -> str | None:
    """Fetch the README from the upstream GitHub repo.

    Tries ``main`` then ``master`` branch, and several common README filenames.
    Returns the raw text on success, or ``None`` if nothing is found.
    """
    for branch in _RAW_BRANCHES:
        for name in _README_NAMES:
            content = _fetch_raw(_raw_url(owner, repo, branch, name))
            if content is not None:
                logger.debug("Fetched %s for %s/%s from %s", name, owner, repo, branch)
                return content
    return None


# ---------------------------------------------------------------------------
# Packages.md parsing
# ---------------------------------------------------------------------------


def _parse_github_slug(url: str) -> tuple[str, str] | None:
    """Return (owner, repo) from a GitHub URL, normalised to lowercase.

    GitHub URLs are case-insensitive; lowercasing keeps ``port_name`` and the
    constructed ``homepage`` consistent with the catalog IDs written by the updater.
    """
    m = _GITHUB_RE.match(url.strip().rstrip("/"))
    return (m.group(1).lower(), m.group(2).lower()) if m else None


def _build_package(
    owner: str, repo: str, tagline: str, category: str
) -> CLibPackage:
    """Build a :class:`CLibPackage` from a bullet entry and its ``package.json``."""
    github_url = f"https://github.com/{owner}/{repo}"
    pkg_json = _fetch_package_json(owner, repo)

    if pkg_json is not None:
        package_name = str(pkg_json.get("name") or repo)
        description = tagline or str(pkg_json.get("description") or "")
        license_val = str(pkg_json.get("license") or "") or None
        version_val = str(pkg_json.get("version") or "") or None
        json_kws: list[str] = [str(k) for k in (pkg_json.get("keywords") or [])]  # type: ignore[attr-defined]
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
        readme_content=_fetch_readme(owner, repo),
    )


def parse_packages_md(
    packages_md: Path, limit: int | None = None
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
        parsed = _parse_github_slug(url)
        if not parsed:
            logger.debug("Skipping non-GitHub URL in Packages.md: %s", url)
            continue

        owner, repo = parsed
        packages.append(_build_package(owner, repo, (tagline or "").strip(), current_category))

        if limit is not None and len(packages) >= limit:
            break

    return packages
