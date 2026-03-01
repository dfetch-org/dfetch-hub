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
    with open(src, encoding="utf-8") as fh:
        data = json.load(fh)
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"), ensure_ascii=False)


def _cmd_publish(parsed: argparse.Namespace) -> None:
    """Build a deployable static site for GitHub Pages / GitLab Pages."""
    output = Path(parsed.output)
    _config, data_dir = load_config_with_data_dir(
        parsed.config, parsed.data_dir, _DEFAULT_DATA_DIR
    )

    if not data_dir.is_dir():
        logger.error(
            "Catalog data directory '%s' does not exist or is not a directory", data_dir
        )
        sys.exit(1)
    if not any(data_dir.rglob("*.json")):
        logger.error("Catalog data directory '%s' contains no JSON files", data_dir)
        sys.exit(1)
    out_res = output.resolve()
    src_res = data_dir.resolve()
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

    if output.exists():
        logger.print_info_line("publish", f"Removing existing '{output}' ...")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    # Copy site assets; rewrite the two fetch() paths in index.html so that
    # data/ is relative to the output root instead of ../data/ (the dev layout).
    logger.print_info_line("publish", "Copying site assets ...")
    for src in _SITE_DIR.rglob("*"):
        if not src.is_file():
            continue
        relative = src.relative_to(_SITE_DIR)
        dst = output / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.name == "index.html":
            text = src.read_text(encoding="utf-8")
            text = re.sub(r"(['\"`])\.\.\/data\/", r"\1data/", text)
            dst.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(src, dst)

    # Copy and minify all JSON from the data directory.
    json_files = sorted(data_dir.rglob("*.json"))
    logger.print_info_line("publish", f"Minifying {len(json_files)} JSON file(s) ...")
    for src in json_files:
        dst = output / "data" / src.relative_to(data_dir)
        _minify_json(src, dst)

    logger.print_info_line(
        "publish",
        f"Done — static site written to '{output}' ({len(json_files)} JSON file(s) minified)",
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
