"""dfetch-hub ``update`` subcommand."""

from __future__ import annotations

import argparse
import importlib.resources
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from dfetch.log import get_logger

from dfetch_hub.catalog.cloner import clone_source
from dfetch_hub.catalog.sources import RAW_BRANCHES, fetch_raw, parse_vcs_slug, raw_url
from dfetch_hub.catalog.sources.clib import CLibPackage, parse_packages_md
from dfetch_hub.catalog.sources.conan import parse_conan_recipe
from dfetch_hub.catalog.sources.readme import parse_readme_dir
from dfetch_hub.catalog.sources.vcpkg import parse_vcpkg_json
from dfetch_hub.catalog.sources.west import parse_west_yaml
from dfetch_hub.catalog.writer import CatalogWriter
from dfetch_hub.commands import load_config_with_data_dir

if TYPE_CHECKING:
    from collections.abc import Callable

    from dfetch_hub.catalog.sources import BaseManifest
    from dfetch_hub.config import SourceConfig

logger = get_logger(__name__)

_DEFAULT_DATA_DIR: Path = Path(str(importlib.resources.files("dfetch_hub") / "data"))

_MANIFEST_PARSERS = {
    "vcpkg.json": parse_vcpkg_json,
    "conandata.yml": parse_conan_recipe,
    "readme": parse_readme_dir,
}


def _filter_sentinel(source: SourceConfig, entry_dirs: list[Path]) -> list[Path]:
    """Remove entries from *entry_dirs* that contain ``source.ignore_if_present``.

    When ``source.ignore_if_present`` is an empty string the original list is
    returned unchanged.  Otherwise every directory that contains a file (or
    sub-directory) with that name is removed, and the number of removals is
    logged at info level.

    Args:
        source:     Source configuration (provides ``ignore_if_present`` and ``name``).
        entry_dirs: Candidate entry directories to filter.

    Returns:
        Filtered list with sentinel-containing directories removed.

    """
    if not source.ignore_if_present:
        return entry_dirs
    before = len(entry_dirs)
    filtered = [d for d in entry_dirs if not (d / source.ignore_if_present).exists()]
    ignored = before - len(filtered)
    if ignored:
        logger.print_info_line(
            source.name,
            f"Ignored {ignored} folder(s) containing '{source.ignore_if_present}'",
        )
    return filtered


def _subfolder_homepage(source: SourceConfig) -> str | None:
    """Return the repository URL as a homepage for a subfolder package.

    VCS hosting providers (GitHub, GitLab, Gitea, Bitbucket, company-hosted
    instances) each use different URL schemes for linking to subdirectories, so
    we do not attempt to construct a provider-specific tree URL.  The repository
    root URL is always a valid and useful landing page.

    Args:
        source: Source configuration supplying the remote URL.

    Returns:
        ``source.url`` if non-empty, ``None`` otherwise.

    """
    return source.url or None


def _parse_entry_dirs(
    entry_dirs: list[Path],
    parse_fn: Callable[[Path], BaseManifest | None],
    fallback_homepage: str | None,
) -> tuple[list[BaseManifest], int]:
    """Parse *entry_dirs* and return ``(manifests, skipped_count)``.

    For each directory the appropriate parser is called.  Packages whose
    homepage is ``None`` get the *fallback_homepage* (i.e. the repository root
    URL) if one is available.

    Args:
        entry_dirs:       Sorted list of package directories to process.
        parse_fn:         Parser function for the manifest type.
        fallback_homepage: Repository root URL used when a manifest has no homepage.

    Returns:
        A ``(manifests, skipped)`` tuple.
    """
    manifests: list[BaseManifest] = []
    skipped = 0
    for entry_dir in entry_dirs:
        m = parse_fn(entry_dir)
        if m is None:
            skipped += 1
        else:
            if m.homepage is None and fallback_homepage is not None:
                m.homepage = fallback_homepage
            if m.in_project_repo and not m.subpath:
                m.subpath = entry_dir.name
            manifests.append(m)
    return manifests, skipped


def _process_subfolders_source(
    source: SourceConfig,
    data_dir: Path,
    limit: int | None,
) -> None:
    """Handle strategy='subfolders' (vcpkg, conan-center, …).

    Dispatches to the appropriate per-directory parser based on
    ``source.manifest`` (e.g. ``vcpkg.json`` → vcpkg, ``conandata.yml`` → conan).
    """
    parse_fn = _MANIFEST_PARSERS.get(source.manifest)
    if parse_fn is None:
        if not source.manifest:
            logger.warning("%s: no 'manifest' configured — skipped", source.name)
        else:
            logger.warning(
                "%s: manifest type '%s' not supported — skipped",
                source.name,
                source.manifest,
            )
        return

    logger.print_info_line(source.name, f"Fetching {source.url} (src: {source.path}) ...")
    with tempfile.TemporaryDirectory(prefix="dfetch-hub-") as tmp:
        fetched_dir = clone_source(source, Path(tmp))

        entry_dirs = sorted(d for d in fetched_dir.iterdir() if d.is_dir())
        entry_dirs = _filter_sentinel(source, entry_dirs)
        if limit is not None:
            entry_dirs = entry_dirs[:limit]

        logger.print_info_line(source.name, f"Parsing {len(entry_dirs)} package(s) ...")
        manifests, skipped = _parse_entry_dirs(entry_dirs, parse_fn, _subfolder_homepage(source))

        if skipped:
            logger.print_warning_line(
                source.name,
                f"Skipped {skipped} package(s) with no manifest",
            )

        writer = CatalogWriter(
            data_dir,
            source.name,
            source.label or source.name,
            source.path or source.name,
        )
        _added, _updated = writer.write(manifests)
        logger.print_info_line(
            source.name,
            f"Done — {_added} added, {_updated} updated ({len(manifests) - _added - _updated} skipped/no-vcs-url)",
        )


def _process_git_wiki_source(
    source: SourceConfig,
    data_dir: Path,
    limit: int | None,
) -> None:
    """Handle strategy='git-wiki': clone a git wiki repo and parse a markdown index.

    The wiki is fetched via dfetch (shallow clone), then the file named by
    ``source.manifest`` (e.g. ``Packages.md``) is parsed to discover packages.
    For each package the upstream ``package.json`` is fetched from GitHub to
    collect richer metadata.
    """
    if not source.manifest:
        logger.print_warning_line(source.name, "no 'manifest' configured — skipped")
        return

    logger.print_info_line(source.name, f"Fetching wiki {source.url} ...")
    with tempfile.TemporaryDirectory(prefix="dfetch-hub-") as tmp:
        tmp_path = Path(tmp)
        fetched_dir = clone_source(source, tmp_path)

        index_file = fetched_dir / source.manifest
        if not index_file.exists():
            logger.print_warning_line(
                source.name,
                f"'{source.manifest}' not found in fetched wiki — skipped",
            )
            return

        logger.print_info_line(source.name, f"Parsing {source.manifest} ...")
        packages: list[CLibPackage] = parse_packages_md(index_file, limit=limit)

        logger.print_info_line(source.name, f"Fetched metadata for {len(packages)} package(s)")
        writer = CatalogWriter(
            data_dir,
            source.name,
            source.label or source.name,
            source.path or source.name,
        )
        _added, _updated = writer.write(packages)  # type: ignore[arg-type]
        logger.print_info_line(
            source.name,
            f"Done — {_added} added, {_updated} updated ({len(packages) - _added - _updated} skipped/no-vcs-url)",
        )


def _download_west_yaml(source: SourceConfig, manifest_filename: str, tmp_dir: Path) -> Path | None:
    """Fetch a west YAML manifest file from a GitHub repository via HTTP.

    Constructs a raw GitHub content URL from *source.url*, then tries the
    configured branch (or ``main`` / ``master`` as fallbacks) until the file
    is retrieved.  On success the content is written to *tmp_dir* and its
    path is returned.

    Args:
        source:            Source configuration (provides ``url`` and ``branch``).
        manifest_filename: Filename to fetch (e.g. ``"west.yml"``).
        tmp_dir:           Temporary directory to write the downloaded file into.

    Returns:
        Path to the downloaded file on success, or ``None`` if the file could
        not be retrieved or *source.url* is not a GitHub URL.
    """
    slug = parse_vcs_slug(source.url)
    if slug is None or slug[0] != "github.com":
        logger.warning(
            "%s: west-manifest strategy supports GitHub URLs only (got %s)",
            source.name,
            source.url,
        )
        return None
    _, owner, repo = slug
    branches = [source.branch] if source.branch else list(RAW_BRANCHES)
    for branch in branches:
        content = fetch_raw(raw_url(owner, repo, branch, manifest_filename))
        if content is not None:
            dest = tmp_dir / manifest_filename
            dest.write_text(content, encoding="utf-8")
            logger.debug("Downloaded %s from %s/%s@%s", manifest_filename, owner, repo, branch)
            return dest
    return None


def _process_west_manifest_source(
    source: SourceConfig,
    data_dir: Path,
    limit: int | None,
) -> None:
    """Handle strategy='west-manifest': fetch a west.yml and index its projects.

    Downloads the west manifest file named by ``source.manifest`` (default:
    ``west.yml``) directly from the GitHub repository at ``source.url``, then
    parses every ``manifest.projects`` entry into catalog entries.  Each
    project becomes a separate catalog component pointing to its upstream repo.
    """
    manifest_filename = source.manifest or "west.yml"
    logger.print_info_line(source.name, f"Fetching {source.url}/{manifest_filename} ...")

    with tempfile.TemporaryDirectory(prefix="dfetch-hub-") as tmp:
        west_yaml_path = _download_west_yaml(source, manifest_filename, Path(tmp))
        if west_yaml_path is None:
            logger.print_warning_line(
                source.name,
                f"Could not fetch '{manifest_filename}' from {source.url} — skipped",
            )
            return

        logger.print_info_line(source.name, f"Parsing {manifest_filename} ...")
        projects = parse_west_yaml(west_yaml_path, limit=limit)

        logger.print_info_line(source.name, f"Fetched metadata for {len(projects)} project(s)")
        writer = CatalogWriter(
            data_dir,
            source.name,
            source.label or source.name,
            source.path or source.name,
        )
        _added, _updated = writer.write(projects)  # type: ignore[arg-type]
        logger.print_info_line(
            source.name,
            f"Done — {_added} added, {_updated} updated ({len(projects) - _added - _updated} skipped/no-vcs-url)",
        )


def _process_source(
    source: SourceConfig,
    data_dir: Path,
    limit: int | None,
) -> None:
    if source.strategy == "subfolders":
        _process_subfolders_source(source, data_dir, limit)
    elif source.strategy == "git-wiki":
        _process_git_wiki_source(source, data_dir, limit)
    elif source.strategy == "west-manifest":
        _process_west_manifest_source(source, data_dir, limit)
    else:
        logger.warning(
            "%s: strategy '%s' not yet supported — skipped",
            source.name,
            source.strategy,
        )


def _cmd_update(parsed: argparse.Namespace) -> None:
    """Run the catalog update pipeline."""
    config, data_dir = load_config_with_data_dir(parsed.config, parsed.data_dir, _DEFAULT_DATA_DIR)

    sources = config.sources
    if parsed.source:
        sources = [s for s in sources if s.name == parsed.source]
        if not sources:
            logger.warning("No source found with name '%s'", parsed.source)
            sys.exit(1)

    for source in sources:
        _process_source(source, data_dir, parsed.limit)


_LIMIT_ERROR_MSG = "--limit must be >= 0"


def _non_negative_int(value: str) -> int:
    """Parse *value* as a non-negative integer for ``--limit``."""
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError(_LIMIT_ERROR_MSG)
    return parsed


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the ``update`` subcommand onto *subparsers*."""
    update_p = subparsers.add_parser(
        "update",
        help="Fetch sources from dfetch-hub.toml and update the catalog.",
    )
    update_p.add_argument(
        "--config",
        default="dfetch-hub.toml",
        help="Path to dfetch-hub.toml (default: %(default)s)",
    )
    update_p.add_argument(
        "--data-dir",
        default=None,
        help=f"Catalog data directory (default: catalog_path from config, else {_DEFAULT_DATA_DIR})",
    )
    update_p.add_argument(
        "--limit",
        type=_non_negative_int,
        default=None,
        metavar="N",
        help="Process only the first N entries per source (useful for testing)",
    )
    update_p.add_argument(
        "--source",
        default=None,
        metavar="NAME",
        help="Only process the source with this name",
    )
    update_p.set_defaults(func=_cmd_update)
