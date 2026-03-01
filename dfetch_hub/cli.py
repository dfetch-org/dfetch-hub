"""dfetch-hub command-line interface."""

from __future__ import annotations

import argparse
from importlib.metadata import version as _pkg_version

from dfetch.log import configure_root_logger, setup_root

from dfetch_hub.commands import publish, serve, update


def main(args: list[str] | None = None) -> None:
    """Run the dfetch-hub CLI."""
    configure_root_logger()
    logger = setup_root("dfetch-hub")

    try:
        pkg_version = _pkg_version("dfetch_hub")
    except Exception:  # pylint: disable=broad-exception-caught
        pkg_version = "unknown"

    logger.info("[bold blue]Dfetch:[white]hub[/white] (%s)[/bold blue]", pkg_version)

    parser = argparse.ArgumentParser(
        prog="dfetch-hub",
        description="dfetch-hub: catalog builder and viewer for dfetch package registries.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = True

    update.register(subparsers)
    serve.register(subparsers)
    publish.register(subparsers)

    parsed = parser.parse_args(args)
    parsed.func(parsed)


if __name__ == "__main__":
    main()
