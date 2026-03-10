"""Validate JavaScript embedded in HTML files using py-mini-racer (V8).

Extracts every inline ``<script>`` block from each HTML file supplied on the
command line (skipping ``<script src="...">`` external scripts) and passes it
through V8's ``Function`` constructor, which compiles the code without
executing it.  Any ``SyntaxError`` thrown by V8 is reported and causes the
script to exit with code 1.

This approach supports the full modern ECMAScript feature set (ES2020+,
including optional chaining ``?.``, nullish coalescing ``??``, async/await,
etc.) because it uses the real V8 engine bundled with py-mini-racer.
"""

from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_mini_racer import MiniRacer  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# V8 syntax-check bootstrap
# ---------------------------------------------------------------------------

# Runs once per process.  The helper function is injected into the V8 context
# before any user code is checked.
_V8_BOOTSTRAP = """
function _checkSyntax(code) {
    try {
        new Function(code);
        return null;
    } catch (e) {
        return (e instanceof SyntaxError) ? e.message : null;
    }
}
"""

# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------


class _ScriptExtractor(HTMLParser):
    """Collect the text content of inline ``<script>`` elements."""

    def __init__(self) -> None:
        """Initialise parser state."""
        super().__init__()
        self._in_script: bool = False
        self._start_line: int = 0
        self._buf: list[str] = []
        self.blocks: list[tuple[int, str]] = []  # (start_line, js_text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Enter an inline ``<script>`` element; skip external ones."""
        if tag == "script":
            attr_dict = dict(attrs)
            if "src" not in attr_dict:
                self._in_script = True
                self._start_line = self.getpos()[0]
                self._buf = []

    def handle_endtag(self, tag: str) -> None:
        """Save accumulated text when a ``<script>`` element closes."""
        if tag == "script" and self._in_script:
            self.blocks.append((self._start_line, "".join(self._buf)))
            self._in_script = False

    def handle_data(self, data: str) -> None:
        """Accumulate character data while inside a ``<script>`` element."""
        if self._in_script:
            self._buf.append(data)


# ---------------------------------------------------------------------------
# JavaScript validation
# ---------------------------------------------------------------------------


def _make_ctx() -> MiniRacer:
    """Create and return a warm py-mini-racer context with the helper loaded.

    Returns:
        A ``py_mini_racer.MiniRacer`` instance ready to call ``_checkSyntax``.
    """
    from py_mini_racer import MiniRacer  # type: ignore[import-untyped]

    ctx = MiniRacer()
    ctx.eval(_V8_BOOTSTRAP)
    return ctx


def _validate_block(ctx: object, js_text: str, start_line: int, block_num: int) -> list[str]:
    """Use V8 to syntax-check one JavaScript block.

    Args:
        ctx: A warm ``MiniRacer`` context (already has ``_checkSyntax`` loaded).
        js_text: Raw JavaScript extracted from an inline ``<script>`` element.
        start_line: Line number of the ``<script>`` opening tag in the HTML.
        block_num: 1-based index of this block within the file.

    Returns:
        A (possibly empty) list of formatted error strings.
    """
    result = ctx.call("_checkSyntax", js_text)  # type: ignore[union-attr]
    if result is None:
        return []
    # V8 SyntaxError messages don't include line numbers relative to the
    # extracted block, so we report the HTML source line of the <script> tag.
    return [f"  <script> block {block_num} (HTML line ~{start_line}): SyntaxError: {result}"]


def _check_file(path: Path) -> list[str]:
    """Return JS syntax-error messages for all inline ``<script>`` blocks.

    Args:
        path: Path to an HTML file.

    Returns:
        A (possibly empty) list of formatted diagnostic messages.
    """
    extractor = _ScriptExtractor()
    extractor.feed(path.read_text(encoding="utf-8"))
    if not extractor.blocks:
        return []

    ctx = _make_ctx()
    messages: list[str] = []
    for idx, (start_line, js_text) in enumerate(extractor.blocks, 1):
        messages.extend(_validate_block(ctx, js_text, start_line, idx))
    return messages


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Validate embedded JavaScript in all HTML files given as arguments.

    Returns:
        0 if all JavaScript is syntactically valid, 1 if any errors were found.
    """
    failed = False
    for arg in sys.argv[1:]:
        path = Path(arg)
        messages = _check_file(path)
        if messages:
            print(f"{arg}: JavaScript syntax errors detected")
            for msg in messages:
                print(msg)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
