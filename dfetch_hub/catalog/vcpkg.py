"""Parse vcpkg.json port manifest files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from dfetch.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


@dataclass
class VcpkgManifest:
    """Parsed contents of a single ``vcpkg.json`` file.

    Attributes:
        port_name:    Name of the port directory (used as the vcpkg identifier).
        package_name: Value of the ``name`` field inside ``vcpkg.json``.
        description:  Human-readable description of the package.
        homepage:     Upstream project URL, usually a GitHub link.
        license:      SPDX license expression, or ``None`` if unspecified.
        version:      Resolved version string (from whichever version field is
                      present in the manifest), or ``None`` if absent.
        dependencies: Names of direct vcpkg dependencies.

    """

    port_name: str
    package_name: str
    description: str
    homepage: str | None
    license: str | None
    version: str | None
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


def _extract_dependencies(data: dict[str, object]) -> list[str]:
    """Return a flat list of dependency names from *data*.

    Each element in the ``dependencies`` array may be either a plain name
    string or a dict with at least a ``"name"`` key.
    """
    deps: list[str] = []
    for dep in data.get("dependencies", []):  # type: ignore[union-attr]
        if isinstance(dep, str):
            deps.append(dep)
        elif isinstance(dep, dict) and "name" in dep:
            deps.append(dep["name"])
    return deps


def parse_vcpkg_json(port_dir: Path) -> VcpkgManifest | None:
    """Parse the ``vcpkg.json`` inside *port_dir*.

    Args:
        port_dir: Path to a single port directory (e.g. ``ports/abseil``).

    Returns:
        A :class:`VcpkgManifest` on success, or ``None`` if the file is
        absent, unreadable, or contains invalid JSON.

    """
    manifest_path = port_dir / "vcpkg.json"
    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, encoding="utf-8") as fh:
            data: dict[str, object] = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not parse %s: %s", manifest_path, exc)
        return None

    return VcpkgManifest(
        port_name=port_dir.name,
        package_name=data.get("name", port_dir.name),  # type: ignore[arg-type]
        description=_extract_description(data),
        homepage=data.get("homepage") or None,  # type: ignore[arg-type]
        license=data.get("license") or None,  # type: ignore[arg-type]
        version=_extract_version(data),
        dependencies=_extract_dependencies(data),
    )
