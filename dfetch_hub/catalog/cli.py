"""CLI entry point: fetch sources and update the catalog from dfetch-hub.toml."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from dfetch.log import configure_root_logger, setup_root

from dfetch_hub.catalog.config import HubConfig, SourceConfig, load_config
from dfetch_hub.catalog.fetcher import fetch_source
from dfetch_hub.catalog.updater import update_catalog
from dfetch_hub.catalog.vcpkg import VcpkgManifest, parse_vcpkg_json

_DEFAULT_DATA_DIR = Path(__file__).parent.parent / "example_gui" / "data"


configure_root_logger()
logger = setup_root("dfetch-hub")

def _process_source(
    source: SourceConfig,
    data_dir: Path,
    limit: int | None,
) -> None:
    if source.strategy != "subfolders":
        logger.print_warning_line(source.name, f"strategy '{source.strategy}' not yet supported — skipped")
        return

    if not source.manifest:
        logger.print_warning_line(source.name, "no 'manifest' configured — skipped")
        return

    logger.print_info_line(source.name, f"Fetching {source.url} (src: {source.path!r}) ...")
    with tempfile.TemporaryDirectory(prefix="dfetch-hub-") as tmp:
        tmp_path = Path(tmp)
        fetched_dir = fetch_source(source, tmp_path)

        port_dirs = sorted(d for d in fetched_dir.iterdir() if d.is_dir())
        if limit is not None:
            port_dirs = port_dirs[:limit]

        logger.print_info_line(source.name, f"Parsing {len(port_dirs)} port(s) ...")
        manifests: list[VcpkgManifest] = []
        skipped = 0
        for port_dir in port_dirs:
            m = parse_vcpkg_json(port_dir)
            if m is None:
                skipped += 1
            else:
                manifests.append(m)

        if skipped:
            logger.print_warning_line(source.name, f"Skipped {skipped} port(s) with no manifest")

        _added, _updated = update_catalog(
            manifests,
            data_dir,
            source_name=source.name,
            label=source.label or source.name,
            ports_path=source.path or source.name,
        )
        logger.print_info_line(
            source.name,
            f"Done — {_added} added, {_updated} updated "
            f"({len(manifests) - _added - _updated} skipped/no-github-url)"
        )


def main(args: list[str] | None = None) -> None:
    """Main entry point for the dfetch-hub CLI."""
    parser = argparse.ArgumentParser(
        description="Fetch sources configured in dfetch-hub.toml and update the catalog.",
    )
    parser.add_argument(
        "--config",
        default="dfetch-hub.toml",
        help="Path to dfetch-hub.toml (default: %(default)s)",
    )
    parser.add_argument(
        "--data-dir",
        default=str(_DEFAULT_DATA_DIR),
        help="Path to the catalog data directory (default: %(default)s)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process only the first N ports (useful for testing)",
    )
    parser.add_argument(
        "--source",
        default=None,
        metavar="NAME",
        help="Only process the source with this name",
    )

    parsed = parser.parse_args(args)
    data_dir = Path(parsed.data_dir)

    try:
        config: HubConfig = load_config(parsed.config)
    except FileNotFoundError:
        logger.error(f"Config file '{parsed.config}' not found")
        sys.exit(1)

    sources = config.sources
    if parsed.source:
        sources = [s for s in sources if s.name == parsed.source]
        if not sources:
            logger.warning(f"No source found with name '{parsed.source}'")
            sys.exit(1)

    for source in sources:
        _process_source(source, data_dir, parsed.limit)


if __name__ == "__main__":
    main()
