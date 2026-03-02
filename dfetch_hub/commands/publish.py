"""dfetch-hub ``publish`` subcommand — build a deployable static site."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from dfetch.log import get_logger

from dfetch_hub.commands import load_config_with_data_dir

if TYPE_CHECKING:
    import argparse

logger = get_logger(__name__)

_PACKAGE_DIR = Path(__file__).parent.parent
_DEFAULT_DATA_DIR = _PACKAGE_DIR / "data"
_SITE_DIR = _PACKAGE_DIR / "site"
_DEFAULT_OUTPUT = Path("public")


def _minify_json(src: Path, dst: Path) -> None:
    """Read *src*, minify JSON, write to *dst*."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Path.open(src, encoding="utf-8") as fh:
        data = json.load(fh)
    with Path.open(dst, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"), ensure_ascii=False)


def _validate_output_dir(data_dir: Path, output: Path) -> None:
    """Validate that *data_dir* is populated and does not overlap *output*.

    Logs an error and calls ``sys.exit(1)`` if any check fails.

    Args:
        data_dir: Catalog data directory that must contain JSON files.
        output:   Intended output directory that must not overlap *data_dir*.
    """
    if not data_dir.is_dir():
        logger.error(
            "Catalog data directory '%s' does not exist or is not a directory", data_dir
        )
        sys.exit(1)
    if not any(data_dir.rglob("*.json")):
        logger.error("Catalog data directory '%s' contains no JSON files", data_dir)
        sys.exit(1)
    out_res, src_res = output.resolve(), data_dir.resolve()
    if (
        out_res == src_res
        or out_res.is_relative_to(src_res)
        or src_res.is_relative_to(out_res)
    ):
        logger.error(
            "Output '%s' and data directory '%s' overlap — aborting to prevent data loss",
            output,
            data_dir,
        )
        sys.exit(1)


def _copy_assets(site_dir: Path, output: Path) -> None:
    """Copy site assets from *site_dir* to *output*, rewriting data paths in ``index.html``.

    The ``../data/`` prefix in ``index.html`` fetch calls is rewritten to ``data/``
    so that paths are relative to the output root rather than the dev layout.

    Args:
        site_dir: Source directory containing site assets.
        output:   Destination directory for the published site.
    """
    for src in site_dir.rglob("*"):
        if not src.is_file():
            continue
        dst = output / src.relative_to(site_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.name == "index.html":
            text = src.read_text(encoding="utf-8")
            dst.write_text(
                re.sub(r"(['\"`])\.\.\/data\/", r"\1data/", text), encoding="utf-8"
            )
        else:
            shutil.copy2(src, dst)


def _minify_catalog(data_dir: Path, output: Path) -> int:
    """Copy and minify all JSON files from *data_dir* into ``output/data/``.

    Args:
        data_dir: Source catalog data directory.
        output:   Destination output directory.

    Returns:
        The number of JSON files processed.
    """
    json_files = sorted(data_dir.rglob("*.json"))
    logger.print_info_line("publish", f"Minifying {len(json_files)} JSON file(s) ...")
    for src in json_files:
        _minify_json(src, output / "data" / src.relative_to(data_dir))
    return len(json_files)


def _cmd_publish(parsed: argparse.Namespace) -> None:
    """Build a deployable static site for GitHub Pages / GitLab Pages."""
    output = Path(parsed.output)
    _config, data_dir = load_config_with_data_dir(
        parsed.config, parsed.data_dir, _DEFAULT_DATA_DIR
    )
    _validate_output_dir(data_dir, output)

    if output.exists():
        logger.print_info_line("publish", f"Removing existing '{output}' ...")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    logger.print_info_line("publish", "Copying site assets ...")
    _copy_assets(_SITE_DIR, output)

    count = _minify_catalog(data_dir, output)
    logger.print_info_line(
        "publish",
        f"Done — static site written to '{output}' ({count} JSON file(s) minified)",
    )


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the ``publish`` subcommand onto *subparsers*."""
    publish_p = subparsers.add_parser(
        "publish",
        help="Build a deployable static site for GitHub Pages / GitLab Pages.",
    )
    publish_p.add_argument(
        "--config",
        default="dfetch-hub.toml",
        help="Path to dfetch-hub.toml (default: %(default)s)",
    )
    publish_p.add_argument(
        "--output",
        "-o",
        default=str(_DEFAULT_OUTPUT),
        metavar="DIR",
        help="Output directory (default: %(default)s)",
    )
    publish_p.add_argument(
        "--data-dir",
        default=None,
        help=f"Catalog data directory (default: catalog_path from config, else {_DEFAULT_DATA_DIR})",
    )
    publish_p.set_defaults(func=_cmd_publish)
