"""Create a dfetch manifest and fetch remote sources into a local directory."""

from pathlib import Path

from dfetch.manifest.manifest import Manifest, ManifestDict
from dfetch.manifest.parse import parse as parse_manifest
from dfetch.manifest.project import ProjectEntryDict
from dfetch.project import create_sub_project
from dfetch.util.util import in_directory
from dfetch.vcs.git import GitRemote
from dfetch.log import get_logger

from dfetch_hub.catalog.config import SourceConfig

logger = get_logger(__name__)


def create_manifest(source: SourceConfig, dest_dir: Path) -> Path:
    """Write a ``dfetch.yaml`` for *source* into *dest_dir*.

    The manifest is configured to fetch only the sub-path specified by
    ``source.path`` (e.g. ``ports/``), so the fetched content lands at
    ``<dest_dir>/<source.name>/`` rather than the entire repository.

    When ``source.branch`` is empty the default branch is auto-detected from
    the remote via :meth:`~dfetch.vcs.git.GitRemote.get_default_branch`.

    Args:
        source:   Source configuration describing the remote to fetch.
        dest_dir: Directory where the manifest file will be written.

    Returns:
        Path to the written ``dfetch.yaml``.

    """
    if source.branch:
        branch = source.branch
    else:
        logger.debug("Auto-detecting default branch for %s", source.url)
        branch = GitRemote(source.url).get_default_branch()
        logger.debug("Detected branch '%s' for %s", branch, source.url)

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
    logger.debug("Wrote manifest to %s", manifest_path)
    return manifest_path


def fetch_source(source: SourceConfig, dest_dir: Path) -> Path:
    """Fetch *source* into *dest_dir* using the dfetch Python API.

    Creates a temporary ``dfetch.yaml`` in *dest_dir*, then runs
    :func:`dfetch.project.create_sub_project` + ``update`` for every project
    declared in that manifest (in practice exactly one).

    The fetched content ends up at ``<dest_dir>/<source.name>/``.

    Args:
        source:   Source configuration describing what to fetch.
        dest_dir: Directory that will receive the manifest and fetched files.

    Returns:
        Path to the directory containing the fetched sub-path.

    Raises:
        RuntimeError: If the expected output directory is absent after the
            fetch, which indicates a dfetch-level failure.

    """
    manifest_path = create_manifest(source, dest_dir)
    manifest = parse_manifest(str(manifest_path))

    with in_directory(dest_dir):
        for project in manifest.projects:
            create_sub_project(project).update(force=True)

    fetched = dest_dir / source.name
    if not fetched.is_dir():
        raise RuntimeError(
            f"Expected dfetch output directory "
            f"{fetched} not found after update"
        )
    logger.debug("Fetch complete: %s", fetched)
    return fetched
