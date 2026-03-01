"""dfetch-hub ``update`` subcommand."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from dfetch.log import get_logger

from dfetch_hub.catalog.cloner import clone_source
from dfetch_hub.catalog.sources import BaseManifest
from dfetch_hub.catalog.sources.clib import CLibPackage, parse_packages_md
from dfetch_hub.catalog.sources.conan import parse_conan_recipe
from dfetch_hub.catalog.sources.vcpkg import parse_vcpkg_json
from dfetch_hub.catalog.writer import write_catalog
from dfetch_hub.commands import load_config_with_data_dir
from dfetch_hub.config import SourceConfig

logger = get_logger(__name__)

_PACKAGE_DIR = Path(__file__).parent.parent
_DEFAULT_DATA_DIR = _PACKAGE_DIR / "data"

_SUBFOLDER_PARSERS = {
    "vcpkg.json": parse_vcpkg_json,
    "conandata.yml": parse_conan_recipe,
}


def _process_subfolders_source(
    source: SourceConfig,
    data_dir: Path,
    limit: int | None,
) -> None:
    """Handle strategy='subfolders' (vcpkg, conan-center, …).

    Dispatches to the appropriate per-directory parser based on
    ``source.manifest`` (e.g. ``vcpkg.json`` → vcpkg, ``conandata.yml`` → conan).
    """
    parse_fn = _SUBFOLDER_PARSERS.get(source.manifest)
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

    logger.print_info_line(
        source.name, f"Fetching {source.url} (src: {source.path}) ..."
    )
    with tempfile.TemporaryDirectory(prefix="dfetch-hub-") as tmp:
        tmp_path = Path(tmp)
        fetched_dir = clone_source(source, tmp_path)

        port_dirs = sorted(d for d in fetched_dir.iterdir() if d.is_dir())
        if limit is not None:
            port_dirs = port_dirs[:limit]

        logger.print_info_line(source.name, f"Parsing {len(port_dirs)} port(s) ...")
        manifests: list[BaseManifest] = []
        skipped = 0
        for port_dir in port_dirs:
            m = parse_fn(port_dir)
            if m is None:
                skipped += 1
            else:
                manifests.append(m)

        if skipped:
            logger.print_warning_line(
                source.name,
                f"Skipped {skipped} port(s) with no manifest",
            )

        _added, _updated = write_catalog(
            manifests,
            data_dir,
            source_name=source.name,
            label=source.label or source.name,
            ports_path=source.path or source.name,
        )
        logger.print_info_line(
            source.name,
            f"Done — {_added} added, {_updated} updated ({len(manifests) - _added - _updated} skipped/no-github-url)",
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

        logger.print_info_line(
            source.name, f"Fetched metadata for {len(packages)} package(s)"
        )
        _added, _updated = write_catalog(
            packages,  # type: ignore[arg-type]
            data_dir,
            source_name=source.name,
            label=source.label or source.name,
            ports_path=source.path or source.name,
        )
        logger.print_info_line(
            source.name,
            f"Done — {_added} added, {_updated} updated ({len(packages) - _added - _updated} skipped/no-github-url)",
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
    else:
        logger.warning(
            "%s: strategy '%s' not yet supported — skipped",
            source.name,
            source.strategy,
        )


def _cmd_update(parsed: argparse.Namespace) -> None:
    """Run the catalog update pipeline."""
    config, data_dir = load_config_with_data_dir(
        parsed.config, parsed.data_dir, _DEFAULT_DATA_DIR
    )

    sources = config.sources
    if parsed.source:
        sources = [s for s in sources if s.name == parsed.source]
        if not sources:
            logger.warning("No source found with name '%s'", parsed.source)
            sys.exit(1)

    for source in sources:
        _process_source(source, data_dir, parsed.limit)


def _non_negative_int(value: str) -> int:
    """Parse *value* as a non-negative integer for ``--limit``."""
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("--limit must be >= 0")
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
        help="Process only the first N ports per source (useful for testing)",
    )
    update_p.add_argument(
        "--source",
        default=None,
        metavar="NAME",
        help="Only process the source with this name",
    )
    update_p.set_defaults(func=_cmd_update)
