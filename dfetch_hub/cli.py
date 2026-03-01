"""dfetch-hub command-line interface."""

from __future__ import annotations

import argparse
import http.server
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path

from dfetch.log import configure_root_logger, setup_root

from dfetch_hub.catalog.sources.clib import CLibPackage, parse_packages_md
from dfetch_hub.catalog.sources.conan import parse_conan_recipe
from dfetch_hub.catalog.sources.vcpkg import parse_vcpkg_json
from dfetch_hub.catalog.store.fetcher import fetch_source
from dfetch_hub.catalog.store.updater import ComponentManifest, update_catalog
from dfetch_hub.config import HubConfig, SourceConfig, load_config

_PACKAGE_DIR = Path(__file__).parent
_DEFAULT_DATA_DIR = _PACKAGE_DIR / "data"
_SITE_DIR = _PACKAGE_DIR / "site"

configure_root_logger()
logger = setup_root("dfetch-hub")


# ---------------------------------------------------------------------------
# update subcommand helpers
# ---------------------------------------------------------------------------

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
            logger.print_warning_line(source.name, "no 'manifest' configured — skipped")
        else:
            logger.print_warning_line(
                source.name,
                f"manifest type '{source.manifest}' not supported — skipped",
            )
        return

    logger.print_info_line(
        source.name, f"Fetching {source.url} (src: {source.path!r}) ..."
    )
    with tempfile.TemporaryDirectory(prefix="dfetch-hub-") as tmp:
        tmp_path = Path(tmp)
        fetched_dir = fetch_source(source, tmp_path)

        port_dirs = sorted(d for d in fetched_dir.iterdir() if d.is_dir())
        if limit is not None:
            port_dirs = port_dirs[:limit]

        logger.print_info_line(source.name, f"Parsing {len(port_dirs)} port(s) ...")
        manifests: list[ComponentManifest] = []
        skipped = 0
        for port_dir in port_dirs:
            m = parse_fn(port_dir)
            if m is None:
                skipped += 1
            else:
                manifests.append(m)

        if skipped:
            logger.print_warning_line(
                source.name, f"Skipped {skipped} port(s) with no manifest"
            )

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
            f"({len(manifests) - _added - _updated} skipped/no-github-url)",
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
        fetched_dir = fetch_source(source, tmp_path)

        index_file = fetched_dir / source.manifest
        if not index_file.exists():
            logger.print_warning_line(
                source.name, f"'{source.manifest}' not found in fetched wiki — skipped"
            )
            return

        logger.print_info_line(source.name, f"Parsing {source.manifest} ...")
        packages: list[CLibPackage] = parse_packages_md(index_file, limit=limit)

        logger.print_info_line(
            source.name, f"Fetched metadata for {len(packages)} package(s)"
        )
        _added, _updated = update_catalog(
            packages,  # type: ignore[arg-type]
            data_dir,
            source_name=source.name,
            label=source.label or source.name,
            ports_path=source.label or source.name,
        )
        logger.print_info_line(
            source.name,
            f"Done — {_added} added, {_updated} updated "
            f"({len(packages) - _added - _updated} skipped/no-github-url)",
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
        logger.print_warning_line(
            source.name, f"strategy '{source.strategy}' not yet supported — skipped"
        )


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def _cmd_update(parsed: argparse.Namespace) -> None:
    """Run the catalog update pipeline."""
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


def _cmd_serve(parsed: argparse.Namespace) -> None:
    """Serve the site from the package directory and open the browser."""
    port: int = parsed.port
    serve_dir = _PACKAGE_DIR

    # SimpleHTTPRequestHandler serves files relative to the process cwd,
    # so we subclass it to always serve from the package directory.
    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(serve_dir), **kwargs)  # type: ignore[arg-type]

        def log_message(
            self,
            format: str,  # pylint: disable=redefined-builtin
            *args: object,
        ) -> None:
            pass  # suppress per-request noise

    url = f"http://localhost:{port}/site/index.html"
    print(f"Serving {serve_dir} on {url}  (Ctrl-C to stop)")

    server = http.server.HTTPServer(("", port), _Handler)

    # Open the browser slightly after the server starts
    threading.Timer(0.3, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


# ---------------------------------------------------------------------------
# Top-level parser
# ---------------------------------------------------------------------------


def main(args: list[str] | None = None) -> None:
    """Main entry point for the dfetch-hub CLI."""
    logger.info("[bold blue]Dfetch:[white]hub[/white] (0.0.1)[/bold blue]")

    parser = argparse.ArgumentParser(
        prog="dfetch-hub",
        description="dfetch-hub: catalog builder and viewer for dfetch package registries.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = True

    # ── update ────────────────────────────────────────────────────────────
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
        default=str(_DEFAULT_DATA_DIR),
        help="Catalog data directory (default: %(default)s)",
    )
    update_p.add_argument(
        "--limit",
        type=int,
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

    # ── serve ─────────────────────────────────────────────────────────────
    serve_p = subparsers.add_parser(
        "serve",
        help="Start a local HTTP server and open the catalog UI in the browser.",
    )
    serve_p.add_argument(
        "--port",
        type=int,
        default=8000,
        help="TCP port to listen on (default: %(default)s)",
    )
    serve_p.set_defaults(func=_cmd_serve)

    parsed = parser.parse_args(args)
    parsed.func(parsed)


if __name__ == "__main__":
    main()
