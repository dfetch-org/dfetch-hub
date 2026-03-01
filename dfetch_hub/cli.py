"""dfetch-hub command-line interface."""

from __future__ import annotations

import argparse

from dfetch.log import configure_root_logger, setup_root

from dfetch_hub.commands import serve, update

configure_root_logger()
logger = setup_root("dfetch-hub")


def main(args: list[str] | None = None) -> None:
    """Main entry point for the dfetch-hub CLI."""
    logger.info("[bold blue]Dfetch:[white]hub[/white] (0.0.1)[/bold blue]")

    parser = argparse.ArgumentParser(
        prog="dfetch-hub",
        description="dfetch-hub: catalog builder and viewer for dfetch package registries.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = True

    update.register(subparsers)
    serve.register(subparsers)

    parsed = parser.parse_args(args)
    parsed.func(parsed)


if __name__ == "__main__":
    main()
