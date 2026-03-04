"""Clone a remote source registry into a local directory via the dfetch API."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dfetch.log import get_logger
from dfetch.manifest.manifest import Manifest, ManifestDict
from dfetch.manifest.parse import parse as parse_manifest
from dfetch.manifest.project import ProjectEntryDict
from dfetch.project import create_sub_project
from dfetch.util.util import in_directory

if TYPE_CHECKING:
    from dfetch_hub.config import SourceConfig

logger = get_logger(__name__)


def _validate_source_name(name: str) -> None:
    """Reject source names that could escape *dest_dir* via path traversal.

    A valid source name must be a single path component — no separators,
    no absolute paths, no ``..`` or ``.`` traversal segments.

    Args:
        name: The source name to validate.

    Raises:
        ValueError: If *name* contains path separators, traversal segments,
            or is otherwise unsafe to use as a directory name inside a
            controlled destination directory.

    """
    parts = Path(name).parts
    if Path(name).is_absolute() or len(parts) != 1 or parts[0] in (".", ".."):
        raise ValueError(
            f"Source name {name!r} is not a safe single path component "
            "(must contain no separators, no leading slash, and no traversal segments)"
        )


def create_manifest(source: SourceConfig, dest_dir: Path) -> Path:
    """Write a ``dfetch.yaml`` for *source* into *dest_dir*.

    The manifest is configured to fetch only the sub-path specified by
    ``source.path`` (e.g. ``ports/``), so the fetched content lands at
    ``<dest_dir>/<source.name>/`` rather than the entire repository.

    Args:
        source:   Source configuration describing the remote to fetch.
        dest_dir: Directory where the manifest file will be written.

    Returns:
        Path to the written ``dfetch.yaml``.

    """
    _validate_source_name(source.name)
    project = ProjectEntryDict(  # pyright: ignore[reportCallIssue]
        name=source.name,
        url=source.url,
        src=source.path,
        branch=source.branch or "",
        revision="",
        vcs="git",
    )
    manifest_dict = ManifestDict(
        version=Manifest.CURRENT_VERSION,
        remotes=[],
        projects=[project],
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dest_dir / "dfetch.yaml"
    Manifest(manifest_dict).dump(str(manifest_path))
    logger.debug("Wrote manifest to %s", manifest_path)
    return manifest_path


def clone_source(source: SourceConfig, dest_dir: Path) -> Path:
    """Clone *source* into *dest_dir* using the dfetch Python API.

    Creates a temporary ``dfetch.yaml`` in *dest_dir*, then runs
    :func:`dfetch.project.create_sub_project` + ``update`` for every project
    declared in that manifest (in practice exactly one).

    The cloned content ends up at ``<dest_dir>/<source.name>/``.

    Args:
        source:   Source configuration describing what to clone.
        dest_dir: Directory that will receive the manifest and cloned files.

    Returns:
        Path to the directory containing the cloned sub-path.

    Raises:
        RuntimeError: If the expected output directory is absent after the
            clone, which indicates a dfetch-level failure.

    """
    manifest_path = create_manifest(source, dest_dir)
    manifest = parse_manifest(str(manifest_path))

    with in_directory(dest_dir):
        for project in manifest.projects:
            create_sub_project(project).update(force=True)

    cloned = dest_dir / source.name
    if not cloned.resolve().is_relative_to(dest_dir.resolve()):
        raise RuntimeError(f"Source name {source.name!r} resolves outside dest_dir {dest_dir}")
    if not cloned.is_dir():
        raise RuntimeError(f"Expected dfetch output directory {cloned} not found after update")
    logger.debug("Clone complete: %s", cloned)
    return cloned
