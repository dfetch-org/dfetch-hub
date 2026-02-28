"""Parse vcpkg.json manifest files."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union


@dataclass
class VcpkgManifest:
    """Parsed contents of a vcpkg.json file."""

    port_name: str          # the folder name used as the port identifier
    package_name: str       # "name" field inside vcpkg.json
    description: str
    homepage: Optional[str]
    license: Optional[str]
    version: Optional[str]
    dependencies: List[str] = field(default_factory=list)


def _extract_version(data: dict) -> Optional[str]:
    for key in ("version-semver", "version", "version-date", "version-relaxed", "version-string"):
        if key in data:
            return str(data[key])
    return None


def _extract_description(data: dict) -> str:
    desc = data.get("description", "")
    if isinstance(desc, list):
        return " ".join(desc)
    return str(desc) if desc else ""


def _extract_dependencies(data: dict) -> List[str]:
    deps = []
    for dep in data.get("dependencies", []):
        if isinstance(dep, str):
            deps.append(dep)
        elif isinstance(dep, dict) and "name" in dep:
            deps.append(dep["name"])
    return deps


def parse_vcpkg_json(port_dir: Path) -> Optional[VcpkgManifest]:
    """Parse the vcpkg.json inside *port_dir*.

    Returns ``None`` if the file is absent or unparseable.
    """
    manifest_path = port_dir / "vcpkg.json"
    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None

    return VcpkgManifest(
        port_name=port_dir.name,
        package_name=data.get("name", port_dir.name),
        description=_extract_description(data),
        homepage=data.get("homepage") or None,
        license=data.get("license") or None,
        version=_extract_version(data),
        dependencies=_extract_dependencies(data),
    )
