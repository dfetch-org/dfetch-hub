"""dfetch-hub ``serve`` subcommand."""

from __future__ import annotations

import argparse
import http.server
import threading
import webbrowser
from pathlib import Path

_PACKAGE_DIR = Path(__file__).parent.parent


def _cmd_serve(parsed: argparse.Namespace) -> None:
    """Serve the site from the package directory and open the browser."""
    port: int = parsed.port
    serve_dir = _PACKAGE_DIR

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

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)

    threading.Timer(0.3, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
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
        type=int,
        default=8000,
        help="TCP port to listen on (default: %(default)s)",
    )
    serve_p.set_defaults(func=_cmd_serve)
