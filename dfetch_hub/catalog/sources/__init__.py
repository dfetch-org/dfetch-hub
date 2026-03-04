"""Format-specific source parsers (vcpkg, conan, clib)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.error import URLError
from urllib.request import Request, urlopen

from dfetch.log import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# VCS URL helpers
# ---------------------------------------------------------------------------

# Matches any https://host/[groups.../]repo[.git] URL regardless of hosting provider.
# The owner group captures everything between the host and the final path segment,
# so GitLab nested groups (group/subgroup/…) are preserved intact.
_VCS_URL_RE = re.compile(
    r"https?://([^/]+)/(.+)/([^/\s#?]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def parse_vcs_slug(url: str) -> tuple[str, str, str] | None:
    """Return ``(host, owner, repo)`` extracted from a VCS URL, normalised to lowercase.

    Works with any ``https://host/owner/repo`` URL — GitHub, GitLab, Gitea,
    Bitbucket, and company-hosted instances.  For GitLab (and similar hosts)
    the *owner* component may contain slashes representing nested groups, e.g.
    ``"group/subgroup"`` for ``https://gitlab.com/group/subgroup/repo``.
    Lowercasing ensures the catalog ID, the detail-file path, and the JSON
    fields are all consistent.

    Args:
        url: A VCS repository URL.

    Returns:
        A ``(host, owner, repo)`` triple, or ``None`` if *url* does not match
        the expected ``https://host/…/repo`` pattern.

    """
    m = _VCS_URL_RE.match(url.strip())
    return (m.group(1).lower(), m.group(2).lower(), m.group(3).lower()) if m else None


# ---------------------------------------------------------------------------
# README fetching
# ---------------------------------------------------------------------------

_HEADERS = {"User-Agent": "dfetch-hub/0.0.1"}
_README_NAMES = ("README.md", "readme.md", "Readme.md", "README.rst", "README")
RAW_BRANCHES = ("main", "master")


def raw_url(owner: str, repo: str, branch: str, filename: str) -> str:
    """Build a raw.githubusercontent.com URL for a specific file.

    Args:
        owner: Repository owner or organization.
        repo: Repository name.
        branch: Branch name to fetch from.
        filename: Filename within the repository root.

    Returns:
        Raw GitHub content
    """
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"


def fetch_raw(url: str) -> str | None:
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
    for branch in RAW_BRANCHES:
        for name in _README_NAMES:
            content = fetch_raw(raw_url(owner, repo, branch, name))
            if content is not None:
                logger.debug("Fetched %s for %s/%s from %s", name, owner, repo, branch)
                return content
    return None


def fetch_readme_for_homepage(homepage: str | None) -> str | None:
    """Fetch the README for a package given its homepage URL.

    Extracts the VCS host/owner/repo from *homepage* and delegates to
    :func:`fetch_readme` when the host is ``github.com``.  Returns ``None``
    for ``None`` input, non-VCS URLs, or non-GitHub hosts (README fetching
    via raw content URLs is currently only implemented for GitHub).

    Args:
        homepage: Upstream project URL (may be ``None`` or a non-GitHub URL).

    Returns:
        The raw README text on success, or ``None``.

    """
    if not homepage:
        return None
    parsed = parse_vcs_slug(homepage)
    if parsed is None or parsed[0] != "github.com":
        return None
    _, owner, repo = parsed
    return fetch_readme(owner, repo)


# ---------------------------------------------------------------------------
# Base data model
# ---------------------------------------------------------------------------


@dataclass
class BaseManifest:
    """Shared base fields for all catalog manifest dataclasses.

    Attributes:
        entry_name:     Unique identifier within the source registry.
        package_name:   Human-readable package name (may differ from entry_name).
        description:    Short description of the package.
        homepage:       Upstream project URL, or ``None`` if unknown.
        license:        SPDX license expression, or ``None`` if unspecified.
        version:        Latest version string, or ``None`` if unavailable.
        readme_content: Raw README text fetched from the upstream repo, or ``None``.
        urls:           Named URLs for the package (e.g. ``{"Homepage": "...",
                        "Source": "..."``).  Modelled on ``[project.urls]`` in
                        ``pyproject.toml``.  Parsers populate this with every URL
                        they can discover; the catalog detail JSON exposes the full
                        dict so the frontend can render all links.
    """

    entry_name: str
    package_name: str
    description: str
    homepage: str | None
    license: str | None
    version: str | None
    readme_content: str | None = None
    urls: dict[str, str] = field(default_factory=dict)
