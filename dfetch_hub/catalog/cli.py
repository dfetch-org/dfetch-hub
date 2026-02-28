"""CLI entry point: fetch sources and update the catalog from dfetch-hub.toml."""

import argparse
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from dfetch_hub.catalog.config import HubConfig, SourceConfig, load_config
from dfetch_hub.catalog.fetcher import fetch_source
from dfetch_hub.catalog.updater import update_catalog
from dfetch_hub.catalog.vcpkg import VcpkgManifest, parse_vcpkg_json

_DEFAULT_DATA_DIR = Path(__file__).parent.parent / "example_gui" / "data"


def _process_source(
    source: SourceConfig,
    data_dir: Path,
    limit: Optional[int],
) -> None:
    if source.strategy != "subfolders":
        print(f"[{source.name}] strategy '{source.strategy}' not yet supported — skipped")
        return

    if not source.manifest:
        print(f"[{source.name}] no 'manifest' configured — skipped")
        return

    print(f"[{source.name}] Fetching {source.url} (src: {source.path!r}) ...")
    with tempfile.TemporaryDirectory(prefix="dfetch-hub-") as tmp:
        tmp_path = Path(tmp)
        fetched_dir = fetch_source(source, tmp_path)

        port_dirs = sorted(
            d for d in fetched_dir.iterdir() if d.is_dir()
        )
        if limit is not None:
            port_dirs = port_dirs[:limit]

        print(f"[{source.name}] Parsing {len(port_dirs)} port(s) ...")
        manifests: List[VcpkgManifest] = []
        skipped = 0
        for port_dir in port_dirs:
            m = parse_vcpkg_json(port_dir)
            if m is None:
                skipped += 1
            else:
                manifests.append(m)

        if skipped:
            print(f"[{source.name}]   {skipped} port(s) had no/invalid {source.manifest}")

        added, updated = update_catalog(
            manifests,
            data_dir,
            source_name=source.name,
            label=source.label or source.name,
            ports_path=source.path or source.name,
        )
        print(
            f"[{source.name}] Done — {added} added, {updated} updated "
            f"({len(manifests) - added - updated} skipped/no-github-url)"
        )


def main(args: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Fetch sources configured in dfetch-hub.toml and update the catalog."
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
        print(f"Error: config file not found: {parsed.config}", file=sys.stderr)
        sys.exit(1)

    sources = config.sources
    if parsed.source:
        sources = [s for s in sources if s.name == parsed.source]
        if not sources:
            print(f"Error: no source named {parsed.source!r}", file=sys.stderr)
            sys.exit(1)

    for source in sources:
        _process_source(source, data_dir, parsed.limit)


if __name__ == "__main__":
    main()
