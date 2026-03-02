"""Parse vcpkg.json port manifest files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from dfetch.log import get_logger

from dfetch_hub.catalog.sources import BaseManifest, fetch_readme_for_homepage

logger = get_logger(__name__)


@dataclass
class VcpkgManifest(BaseManifest):
    """Parsed contents of a single ``vcpkg.json`` file.

    Attributes:
        dependencies: Names of direct vcpkg dependencies.
    """

    dependencies: list[str] = field(default_factory=list)


def _extract_version(data: dict[str, object]) -> str | None:
    """Return the first version string found in *data*, or ``None``.

    vcpkg supports several mutually exclusive version fields; we try them in
    order of specificity.
    """
    for key in (
        "version-semver",
        "version",
        "version-date",
        "version-relaxed",
        "version-string",
    ):
        if key in data:
            return str(data[key])
    return None


def _extract_description(data: dict[str, object]) -> str:
    """Return the package description from *data* as a single string.

    The ``description`` field may be either a plain string or a list of strings
    (where the first element is the summary and subsequent ones are details).
    """
    desc = data.get("description", "")
    if isinstance(desc, list):
        return " ".join(str(d) for d in desc)
    return str(desc) if desc else ""


def _extract_str_field(data: dict[str, object], key: str) -> str | None:
    """Return the string value for *key* in *data*, or ``None`` if absent or non-string."""
    val = data.get(key)
    return str(val) if isinstance(val, str) else None


def _extract_dependencies(data: dict[str, object]) -> list[str]:
    """Return a flat list of dependency names from *data*.

    Each element in the ``dependencies`` array may be either a plain name
    string or a dict with at least a ``"name"`` key.
    """
    deps: list[str] = []
    raw_deps = data.get("dependencies", [])
    if not isinstance(raw_deps, list):
        return deps
    for dep in raw_deps:
        if isinstance(dep, str):
            deps.append(dep)
        elif isinstance(dep, dict):
            name = dep.get("name")
            if isinstance(name, str):
                deps.append(name)
    return deps


def parse_vcpkg_json(entry_dir: Path) -> VcpkgManifest | None:
    """Parse the ``vcpkg.json`` inside *entry_dir*.

    Args:
        entry_dir: Path to a single port directory (e.g. ``ports/abseil``).

    Returns:
        A :class:`VcpkgManifest` on success, or ``None`` if the file is
        absent, unreadable, or contains invalid JSON.

    """
    manifest_path = entry_dir / "vcpkg.json"
    if not manifest_path.exists():
        return None

    try:
        with Path.open(manifest_path, encoding="utf-8") as fh:
            loaded = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not parse %s: %s", manifest_path, exc)
        return None

    if not isinstance(loaded, dict):
        logger.warning("Ignoring non-object vcpkg.json in %s", entry_dir)
        return None

    data: dict[str, object] = loaded
    homepage = _extract_str_field(data, "homepage")
    license_val = _extract_str_field(data, "license")
    package_name = _extract_str_field(data, "name") or entry_dir.name

    urls: dict[str, str] = {}
    if homepage:
        urls["Homepage"] = homepage

    return VcpkgManifest(
        entry_name=entry_dir.name,
        package_name=package_name,
        description=_extract_description(data),
        homepage=homepage,
        license=license_val,
        version=_extract_version(data),
        dependencies=_extract_dependencies(data),
        readme_content=fetch_readme_for_homepage(homepage),
        urls=urls,
    )
