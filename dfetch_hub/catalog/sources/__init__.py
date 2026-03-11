"""Format-specific source parsers (vcpkg, conan, clib)."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from dfetch.log import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# VCS URL helpers
# ---------------------------------------------------------------------------

# Path segments that signal the end of the ``owner/repo`` portion of a VCS URL.
# For example ``/tree/``, ``/blob/``, ``/src/``, or GitLab's ``/-/`` separator.
_TRAILING_MARKERS: frozenset[str] = frozenset({"tree", "blob", "src", "-"})


def parse_vcs_slug(url: str) -> tuple[str, str, str] | None:
    """Return ``(host, owner, repo)`` extracted from a VCS URL, normalised to lowercase.

    Works with any ``https://host/owner/repo`` URL — GitHub, GitLab, Gitea,
    Bitbucket, and company-hosted instances.  For GitLab (and similar hosts)
    the *owner* component may contain slashes representing nested groups, e.g.
    ``"group/subgroup"`` for ``https://gitlab.com/group/subgroup/repo``.
    Trailing path components that indicate sub-tree navigation (``/tree/``,
    ``/blob/``, ``/src/``, ``/-/``) are stripped so that component URLs like
    ``https://github.com/owner/repo/tree/main/src`` are correctly parsed.
    Lowercasing ensures the catalog ID, the detail-file path, and the JSON
    fields are all consistent.

    Args:
        url: A VCS repository URL.

    Returns:
        A ``(host, owner, repo)`` triple, or ``None`` if *url* does not match
        the expected ``https://host/…/repo`` pattern.

    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return None
    netloc = parsed.netloc.lower()
    if not netloc:
        return None

    segments = [s for s in parsed.path.split("/") if s]
    if len(segments) < 2:
        return None

    # Truncate at the first trailing marker (e.g. /tree/, /blob/, /-/).
    # Only look from index 2 onwards so owner and repo are always present.
    repo_end = len(segments)
    for i in range(2, len(segments)):
        if segments[i] in _TRAILING_MARKERS:
            repo_end = i
            break

    path_segments = segments[:repo_end]
    repo = path_segments[-1].removesuffix(".git")
    owner = "/".join(path_segments[:-1])
    return netloc, owner.lower(), repo.lower()


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
    scheme = urlparse(url).scheme
    if scheme not in ("http", "https"):
        logger.debug("GET %s skipped: unsupported scheme %r", url, scheme)
        return None
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
    return _probe_repo_files(owner, repo, _README_NAMES)


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


CHANGELOG_NAMES: tuple[str, ...] = (
    "CHANGELOG.md",
    "changelog.md",
    "Changelog.md",
    "CHANGELOG",
    "CHANGELOG.txt",
    "CHANGES.md",
    "changes.md",
    "Changes.md",
    "CHANGES",
    "CHANGES.txt",
    "HISTORY.md",
    "history.md",
    "History.md",
    "HISTORY",
    "RELEASE_NOTES.md",
    "RELEASE_NOTES",
)


def _probe_repo_files(owner: str, repo: str, names: tuple[str, ...]) -> str | None:
    """Probe a GitHub repository for the first file matching one of *names*.

    Tries ``main`` then ``master`` branch for each candidate filename in *names*.

    Args:
        owner: GitHub organisation or username.
        repo:  Repository name.
        names: Candidate filenames to probe, tried in order.

    Returns:
        The raw file content on success, or ``None`` if nothing is found.

    """
    for branch in RAW_BRANCHES:
        for name in names:
            content = fetch_raw(raw_url(owner, repo, branch, name))
            if content is not None:
                logger.debug("Fetched %s for %s/%s from %s", name, owner, repo, branch)
                return content
    return None


def fetch_changelog(owner: str, repo: str) -> str | None:
    """Fetch the CHANGELOG from a GitHub repository.

    Tries ``main`` then ``master`` branch, and several common CHANGELOG filenames.

    Args:
        owner: GitHub organisation or username.
        repo:  Repository name.

    Returns:
        The raw CHANGELOG text on success, or ``None`` if nothing is found.

    """
    return _probe_repo_files(owner, repo, CHANGELOG_NAMES)


def fetch_changelog_for_homepage(homepage: str | None) -> str | None:
    """Fetch the CHANGELOG for a package given its homepage URL.

    Extracts the VCS host/owner/repo from *homepage* and delegates to
    :func:`fetch_changelog` when the host is ``github.com``.  Returns ``None``
    for ``None`` input, non-VCS URLs, or non-GitHub hosts.

    Args:
        homepage: Upstream project URL (may be ``None`` or a non-GitHub URL).

    Returns:
        The raw CHANGELOG text on success, or ``None``.

    """
    if not homepage:
        return None
    parsed = parse_vcs_slug(homepage)
    if parsed is None or parsed[0] != "github.com":
        return None
    _, owner, repo = parsed
    return fetch_changelog(owner, repo)


# ---------------------------------------------------------------------------
# Base data model
# ---------------------------------------------------------------------------


@dataclass
class BaseManifest:  # pylint: disable=too-many-instance-attributes
    """Shared base fields for all catalog manifest dataclasses.

    Attributes:
        entry_name:          Unique identifier within the source registry.
        package_name:        Human-readable package name (may differ from entry_name).
        description:         Short description of the package.
        homepage:            Upstream project URL, or ``None`` if unknown.
        license:             SPDX license expression, or ``None`` if unspecified.
        version:             Latest version string, or ``None`` if unavailable.
        readme_content:      Raw README text fetched from the upstream repo, or ``None``.
        changelog_content:   Raw CHANGELOG text fetched from the upstream repo, or ``None``.
        urls:                Named URLs for the package (e.g. ``{"Homepage": "...",
                             "Source": "..."``).  Modelled on ``[project.urls]`` in
                             ``pyproject.toml``.  Parsers populate this with every URL
                             they can discover; the catalog detail JSON exposes the full
                             dict so the frontend can render all links.
        subpath:             Subdirectory path within the source repository for this
                             component (e.g. ``"mylib"`` for a monorepo package at
                             ``repo/mylib``).  ``None`` when the manifest represents
                             the repository root.  Used to disambiguate catalog IDs and
                             detail-file paths for monorepos that contain multiple
                             components sharing the same repository URL.
        in_project_repo:     ``True`` when this manifest file resides within the same
                             repository as the project it describes (e.g. a README that
                             is part of the monorepo component it documents).  ``False``
                             (default) when the manifest is a registry entry that points
                             to an external project living in a separate repository (e.g.
                             a ``vcpkg.json`` or ``conanfile.py`` in a central registry).
                             Only manifests with ``in_project_repo=True`` should have
                             their ``subpath`` derived from the containing directory name.
    """

    entry_name: str
    package_name: str
    description: str
    homepage: str | None
    license: str | None
    version: str | None
    readme_content: str | None = None
    changelog_content: str | None = None
    urls: dict[str, str] = field(default_factory=dict)
    subpath: str | None = None
    in_project_repo: bool = False

    @property
    def sanitized_subpath(self) -> str | None:
        """Return the sanitized subpath to prevent path traversal.

        Returns:
            The sanitized subpath, or None if invalid.
        """
        return self.sanitize_subpath(self.subpath)

    @staticmethod
    def sanitize_subpath(subpath: str | None) -> str | None:
        """Validate and sanitize a subpath to prevent path traversal.

        Args:
            subpath: The subpath to validate.

        Returns:
            The sanitized subpath, or None if invalid.
        """
        if not subpath:
            return None

        subpath = subpath.replace("\\", "/").strip("/")

        if not subpath or subpath.startswith("."):
            return None

        if any(part == ".." for part in subpath.split("/")):
            return None

        return subpath
