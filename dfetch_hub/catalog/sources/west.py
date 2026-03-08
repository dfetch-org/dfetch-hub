"""Parse west manifest files (west.yml) to discover Zephyr project dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import yaml
from dfetch.log import get_logger

from dfetch_hub.catalog.sources import BaseManifest, fetch_readme_for_homepage

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class WestProject(BaseManifest):
    """Parsed representation of a single west manifest project entry.

    Attributes:
        groups: West group memberships for this project (e.g. ``["hal"]``,
                ``["optional"]``).  Projects with ``groups: [babblesim]``
                are off by default in Zephyr but are still catalogued.
    """

    groups: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_remote_map(remotes_raw: object) -> dict[str, str]:
    """Return a ``{name: url_base}`` mapping built from the *remotes* list.

    Args:
        remotes_raw: The ``manifest.remotes`` value from west YAML (expected
                     to be a list of dicts, each with ``name`` and ``url-base``).

    Returns:
        A dict mapping remote name to base URL (trailing slash stripped).
        Returns an empty dict when *remotes_raw* is not a list.
    """
    if not isinstance(remotes_raw, list):
        return {}
    result: dict[str, str] = {}
    for item in remotes_raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        url_base = item.get("url-base")
        if isinstance(name, str) and isinstance(url_base, str):
            result[name] = url_base.rstrip("/")
    return result


def _project_url(
    entry: dict[str, object],
    remote_bases: dict[str, str],
    default_remote: str,
) -> str | None:
    """Derive the upstream repository URL for a west project entry.

    Precedence (west specification):

    1. Explicit ``url:`` field.
    2. ``{remote.url-base}/{repo-path}`` where ``repo-path`` defaults to ``name``.

    Args:
        entry:          Parsed west project dict.
        remote_bases:   ``{remote_name: url_base}`` from the manifest remotes.
        default_remote: Name of the manifest default remote.

    Returns:
        The upstream URL string, or ``None`` when it cannot be determined.
    """
    explicit = entry.get("url")
    if isinstance(explicit, str) and explicit:
        return explicit

    remote = entry.get("remote") or default_remote
    if not isinstance(remote, str):
        remote = default_remote

    url_base = remote_bases.get(remote, "")
    if not url_base:
        name = entry.get("name", "<unknown>")
        logger.debug("No url-base for remote %r, skipping project %s", remote, name)
        return None

    repo_path = entry.get("repo-path") or entry.get("name") or ""
    if not isinstance(repo_path, str) or not repo_path:
        return None

    return f"{url_base}/{repo_path}"


def _extract_groups(entry: dict[str, object]) -> list[str]:
    """Return the list of west group names for *entry*.

    Args:
        entry: Parsed west project dict.

    Returns:
        A list of group name strings, or an empty list.
    """
    raw = entry.get("groups")
    if not isinstance(raw, list):
        return []
    return [str(g) for g in raw if g]


def _build_west_project(
    entry: dict[str, object],
    remote_bases: dict[str, str],
    default_remote: str,
) -> WestProject | None:
    """Build a :class:`WestProject` from a single west manifest project dict.

    Args:
        entry:          Raw project dict from ``manifest.projects``.
        remote_bases:   Mapping of remote name to base URL.
        default_remote: Name of the manifest-level default remote.

    Returns:
        A populated :class:`WestProject`, or ``None`` if the entry is missing
        a required ``name`` or has no resolvable upstream URL.
    """
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        logger.debug("Skipping west project entry with no name: %r", entry)
        return None

    homepage = _project_url(entry, remote_bases, default_remote)
    if not homepage:
        logger.debug("Could not determine URL for west project %r — skipped", name)
        return None

    revision = entry.get("revision")
    version = str(revision) if revision else None

    description_raw = entry.get("description", "")
    description = str(description_raw) if description_raw else ""

    urls: dict[str, str] = {"Repository": homepage}

    return WestProject(
        entry_name=name.lower(),
        package_name=name,
        description=description,
        homepage=homepage,
        license=None,
        version=version,
        groups=_extract_groups(entry),
        readme_content=fetch_readme_for_homepage(homepage),
        urls=urls,
        in_project_repo=False,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_west_yaml(west_yaml: "Path", limit: int | None = None) -> list[WestProject]:
    """Parse a ``west.yml`` manifest file into a list of :class:`WestProject`.

    Reads the YAML file at *west_yaml*, extracts remote definitions and the
    project list, and resolves each project's upstream URL.  Projects whose
    URL cannot be determined (missing remote, no ``url-base``) are silently
    skipped with a ``debug`` log message.

    Args:
        west_yaml: Path to the ``west.yml`` (or equivalent) manifest file.
        limit:     Maximum number of projects to return.  ``None`` = unlimited.

    Returns:
        A list of :class:`WestProject` instances, one per discovered project.
        Returns an empty list on parse errors.
    """
    try:
        raw_content = west_yaml.read_text(encoding="utf-8")
        data: object = yaml.safe_load(raw_content)
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Could not parse %s: %s", west_yaml, exc)
        return []

    if not isinstance(data, dict):
        logger.warning("Ignoring non-mapping west YAML in %s", west_yaml)
        return []

    manifest = data.get("manifest")
    if not isinstance(manifest, dict):
        logger.warning("No 'manifest' key found in %s", west_yaml)
        return []

    remote_bases = _build_remote_map(manifest.get("remotes", []))

    defaults = manifest.get("defaults")
    default_remote: str = ""
    if isinstance(defaults, dict):
        dr = defaults.get("remote", "")
        default_remote = str(dr) if dr else ""

    projects_raw = manifest.get("projects", [])
    if not isinstance(projects_raw, list):
        logger.warning("'manifest.projects' is not a list in %s", west_yaml)
        return []

    projects: list[WestProject] = []
    for entry in projects_raw:
        if limit is not None and len(projects) >= limit:
            break
        if not isinstance(entry, dict):
            continue
        project = _build_west_project(entry, remote_bases, default_remote)
        if project is not None:
            projects.append(project)

    logger.debug("Parsed %d project(s) from %s", len(projects), west_yaml)
    return projects
