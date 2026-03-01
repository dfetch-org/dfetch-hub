"""Format-specific source parsers (vcpkg, conan, clib)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen

from dfetch.log import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# GitHub URL helpers
# ---------------------------------------------------------------------------

_GITHUB_RE = re.compile(
    r"https?://github\.com/([^/]+)/([^/\s#?]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def parse_github_slug(url: str) -> tuple[str, str] | None:
    """Return ``(owner, repo)`` extracted from a GitHub URL, normalised to lowercase.

    GitHub URLs are case-insensitive; lowercasing ensures the catalog ID, the
    detail-file path, and the ``org``/``repo`` fields in the detail JSON are all
    consistent with each other.
    """
    m = _GITHUB_RE.match(url.strip())
    return (m.group(1).lower(), m.group(2).lower()) if m else None


# ---------------------------------------------------------------------------
# README fetching
# ---------------------------------------------------------------------------

_HEADERS = {"User-Agent": "dfetch-hub/0.0.1"}
_README_NAMES = ("README.md", "readme.md", "Readme.md", "README.rst", "README")
_RAW_BRANCHES = ("main", "master")


def _raw_url(owner: str, repo: str, branch: str, filename: str) -> str:
    """Build a raw.githubusercontent.com URL for a specific file."""
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"


def _fetch_raw(url: str) -> str | None:
    """GET *url* and return the response body as a string, or ``None`` on failure."""
    try:
        req = Request(url, headers=_HEADERS)
        with urlopen(req, timeout=10) as resp:  # nosec B310
            return str(resp.read().decode(errors="replace"))
    except (URLError, OSError) as exc:
        logger.debug("GET %s failed: %s", url, exc)
        return None


def fetch_readme(owner: str, repo: str) -> str | None:
    """Fetch the README from a GitHub repository.

    Tries ``main`` then ``master`` branch, and several common README filenames.

    Args:
        owner: GitHub organisation or username.
        repo:  Repository name.

    Returns:
        The raw README text on success, or ``None`` if nothing is found.

    """
    for branch in _RAW_BRANCHES:
        for name in _README_NAMES:
            content = _fetch_raw(_raw_url(owner, repo, branch, name))
            if content is not None:
                logger.debug("Fetched %s for %s/%s from %s", name, owner, repo, branch)
                return content
    return None


def fetch_readme_for_homepage(homepage: str | None) -> str | None:
    """Fetch the README for a package given its homepage URL.

    Extracts the GitHub owner/repo from *homepage* and delegates to
    :func:`fetch_readme`.  Returns ``None`` if *homepage* is ``None`` or is not
    a recognised GitHub URL.

    Args:
        homepage: Upstream project URL (may be ``None`` or a non-GitHub URL).

    Returns:
        The raw README text on success, or ``None``.

    """
    if not homepage:
        return None
    parsed = parse_github_slug(homepage)
    return fetch_readme(*parsed) if parsed else None


# ---------------------------------------------------------------------------
# Base data model
# ---------------------------------------------------------------------------


@dataclass
class BaseManifest:
    """Shared base fields for all catalog manifest dataclasses.

    Attributes:
        port_name:      Unique identifier within the source registry.
        package_name:   Human-readable package name (may differ from port_name).
        description:    Short description of the package.
        homepage:       Upstream project URL, or ``None`` if unknown.
        license:        SPDX license expression, or ``None`` if unspecified.
        version:        Latest version string, or ``None`` if unavailable.
        readme_content: Raw README text fetched from the upstream repo, or ``None``.
    """

    port_name: str
    package_name: str
    description: str
    homepage: str | None
    license: str | None
    version: str | None
    readme_content: str | None = None
