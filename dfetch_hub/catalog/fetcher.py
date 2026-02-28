"""Create a dfetch manifest and fetch sources into a temporary directory."""

from pathlib import Path

from dfetch.manifest.manifest import Manifest, ManifestDict
from dfetch.manifest.parse import parse as parse_manifest
from dfetch.manifest.project import ProjectEntryDict
from dfetch.project import create_sub_project
from dfetch.util.util import in_directory
from dfetch.vcs.git import GitRemote

from dfetch_hub.catalog.config import SourceConfig


def create_manifest(source: SourceConfig, dest_dir: Path) -> Path:
    """Write a dfetch.yaml for *source* into *dest_dir* and return its path.

    The manifest fetches only the configured sub-path of the remote repo
    (e.g. ``ports/`` for vcpkg), placing the result at ``<name>/`` inside
    *dest_dir*.
    """
    branch = source.branch or GitRemote(source.url).get_default_branch()
    project = ProjectEntryDict(
        name=source.name,
        url=source.url,
        src=source.path,
        branch=branch,
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
    """Fetch *source* into *dest_dir* using the dfetch Python API.

    The fetched content ends up at ``<dest_dir>/<source.name>/``.
    """
    manifest_path = create_manifest(source, dest_dir)
    manifest = parse_manifest(str(manifest_path))

    with in_directory(dest_dir):
        for project in manifest.projects:
            create_sub_project(project).update(force=True)

    fetched = dest_dir / source.name
    if not fetched.is_dir():
        raise RuntimeError(
            f"Expected dfetch output directory {fetched} not found after update"
        )
    return fetched
