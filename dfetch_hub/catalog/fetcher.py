"""Create a dfetch manifest and fetch sources into a temporary directory."""

import os
import subprocess
import sys
from pathlib import Path

from dfetch.manifest.manifest import Manifest, ManifestDict
from dfetch.manifest.project import ProjectEntryDict

from dfetch_hub.catalog.config import SourceConfig


def create_manifest(source: SourceConfig, dest_dir: Path) -> Path:
    """Write a dfetch.yaml for *source* into *dest_dir* and return its path.

    The manifest fetches only the configured sub-path of the remote repo
    (e.g. ``ports/`` for vcpkg), placing the result at ``<name>/`` inside
    *dest_dir*.
    """
    project = ProjectEntryDict(
        name=source.name,
        url=source.url,
        src=source.path,
        branch=source.branch or "",
        revision="",
        repo_path="",
        vcs="git",
    )
    manifest_dict = ManifestDict(
        version=Manifest.CURRENT_VERSION,
        remotes=[],
        projects=[project],
    )
    manifest_path = dest_dir / "dfetch.yaml"
    Manifest(manifest_dict).dump(str(manifest_path))
    return manifest_path


def fetch_source(source: SourceConfig, dest_dir: Path) -> Path:
    """Fetch *source* into *dest_dir* using dfetch and return the fetched folder.

    The fetched content ends up at ``<dest_dir>/<source.name>/``.
    """
    create_manifest(source, dest_dir)

    dfetch_bin = _dfetch_executable()
    result = subprocess.run(
        [dfetch_bin, "update"],
        cwd=str(dest_dir),
        capture_output=False,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"dfetch update failed in {dest_dir} (exit {result.returncode})"
        )

    fetched = dest_dir / source.name
    if not fetched.is_dir():
        raise RuntimeError(
            f"Expected dfetch output directory {fetched} not found after update"
        )
    return fetched


def _dfetch_executable() -> str:
    """Return the path to the dfetch executable, preferring the active venv."""
    # Check alongside the running Python interpreter (works inside a venv)
    candidate = Path(sys.executable).parent / "dfetch"
    if candidate.exists():
        return str(candidate)
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        candidate = Path(venv) / "bin" / "dfetch"
        if candidate.exists():
            return str(candidate)
    return "dfetch"
