"""dfetch-hub command-line interface."""

from __future__ import annotations

import argparse
from importlib.metadata import version as _pkg_version

from dfetch.log import configure_root_logger, get_logger, setup_root

from dfetch_hub.commands import publish, serve, update

logger = get_logger(__name__)


def main(args: list[str] | None = None) -> None:
    """Run the dfetch-hub CLI.

    Args:
        args: Command-line arguments to parse.  ``None`` reads from
              ``sys.argv`` (the default argparse behaviour).

    Returns:
        None

    """
    configure_root_logger()
    root_logger = setup_root("dfetch-hub")

    try:
        pkg_version = _pkg_version("dfetch_hub")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.debug("Could not determine package version: %s", exc)
        pkg_version = "unknown"

    root_logger.info("[bold blue]Dfetch:[white]hub[/white] (%s)[/bold blue]", pkg_version)

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
