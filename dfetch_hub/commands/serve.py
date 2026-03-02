"""dfetch-hub ``serve`` subcommand."""

from __future__ import annotations

import argparse
import http.server
import importlib.resources
import threading
import webbrowser
from pathlib import Path

from dfetch.log import get_logger

logger = get_logger(__name__)


def _port_type(value: str) -> int:
    """Parse *value* as a TCP port number (1-65535)."""
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("--port must be between 1 and 65535")
    return port


def _cmd_serve(parsed: argparse.Namespace) -> None:
    """Serve the site from the package directory and open the browser."""
    port: int = parsed.port
    serve_dir = Path(str(importlib.resources.files("dfetch_hub")))

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(serve_dir), **kwargs)  # type: ignore[arg-type]

        def log_message(
            self,
            format: str,  # pylint: disable=redefined-builtin  # noqa: A002
            *args: object,
        ) -> None:
            pass  # suppress per-request noise

    url = f"http://localhost:{port}/site/index.html"
    logger.info("Serving %s on %s  (Ctrl-C to stop)", serve_dir, url)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)

    threading.Timer(0.3, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopped.")
    finally:
        server.server_close()


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the ``serve`` subcommand onto *subparsers*."""
    serve_p = subparsers.add_parser(
        "serve",
        help="Start a local HTTP server and open the catalog UI in the browser.",
    )
    serve_p.add_argument(
        "--port",
        type=_port_type,
        default=8000,
        help="TCP port to listen on (1-65535, default: %(default)s)",
    )
    serve_p.set_defaults(func=_cmd_serve)
