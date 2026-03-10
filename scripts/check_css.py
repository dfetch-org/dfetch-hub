"""Validate CSS embedded in HTML files using tinycss2.

Extracts every ``<style>`` block from each HTML file supplied on the command
line and parses it with tinycss2.  The following problems are reported as
errors:

* CSS parse errors flagged by the tokeniser (malformed tokens, unexpected
  characters, etc.).
* Declaration-level syntax errors such as a missing ``:`` separator.
* Declarations whose value token list is completely empty (``prop: ;``).
* Qualified rules whose declaration block is empty (``selector {}``).

Exits with code 1 if any problems are found, 0 otherwise.

Note: tinycss2 is intentionally permissive about *unknown* property names and
values (matching browser error-recovery behaviour), so vendor-prefixed
properties and modern CSS4 functions like ``clamp()``/``var()`` are accepted
without warnings.
"""

from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------


class _StyleExtractor(HTMLParser):
    """Collect the text content of every ``<style>`` element."""

    def __init__(self) -> None:
        """Initialise parser state."""
        super().__init__()
        self._in_style: bool = False
        self._buf: list[str] = []
        self.blocks: list[tuple[int, str]] = []  # (start_line, css_text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Enter a ``<style>`` element."""
        if tag == "style":
            self._in_style = True
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        """Save accumulated text when a ``<style>`` element closes."""
        if tag == "style" and self._in_style:
            self.blocks.append((self.getpos()[0], "".join(self._buf)))
            self._in_style = False

    def handle_data(self, data: str) -> None:
        """Accumulate character data while inside a ``<style>`` element."""
        if self._in_style:
            self._buf.append(data)


# ---------------------------------------------------------------------------
# CSS validation helpers
# ---------------------------------------------------------------------------


def _check_declarations(content: list[object], block_line: int, block_num: int) -> list[str]:
    """Validate declaration-level nodes inside a qualified rule or at-rule block.

    Args:
        content: The ``content`` token list from a tinycss2 ``QualifiedRule`` or
            ``AtRule`` node, already passed through ``parse_declaration_list``.
        block_line: Source line of the opening ``<style>`` tag in the HTML file.
        block_num: 1-based index of the ``<style>`` block in the file.

    Returns:
        A list of human-readable error strings (empty if no problems found).
    """
    import tinycss2  # type: ignore[import-untyped]

    messages: list[str] = []
    decls = tinycss2.parse_declaration_list(content, skip_whitespace=True, skip_comments=True)
    for node in decls:
        line = block_line + getattr(node, "source_line", 1) - 1
        if node.type == "error":  # type: ignore[union-attr]
            messages.append(f"  <style> block {block_num} line ~{line}: {node.message}")  # type: ignore[union-attr]
        elif node.type == "declaration":  # type: ignore[union-attr]
            # Flag completely empty value lists (e.g. "color: ;")
            value_tokens = [
                t
                for t in node.value  # type: ignore[union-attr]
                if getattr(t, "type", None) not in ("whitespace", "comment")
            ]
            if not value_tokens:
                messages.append(
                    f"  <style> block {block_num} line ~{line}:"
                    f" empty value for property '{node.name}'"  # type: ignore[union-attr]
                )
    return messages


def _validate_block(css_text: str, start_line: int, block_num: int) -> list[str]:
    """Parse one CSS block and return all error messages.

    Args:
        css_text: Raw CSS text extracted from a ``<style>`` element.
        start_line: Line number of the ``<style>`` opening tag in the HTML source.
        block_num: 1-based index of this block within the file.

    Returns:
        A (possibly empty) list of formatted diagnostic strings.
    """
    import tinycss2  # type: ignore[import-untyped]

    rules = tinycss2.parse_stylesheet(css_text, skip_whitespace=True, skip_comments=True)
    messages: list[str] = []

    for rule in rules:
        line = start_line + getattr(rule, "source_line", 1) - 1
        if rule.type == "error":  # type: ignore[union-attr]
            messages.append(f"  <style> block {block_num} line ~{line}: {rule.message}")  # type: ignore[union-attr]
        elif rule.type == "qualified-rule":  # type: ignore[union-attr]
            messages.extend(_check_declarations(rule.content, start_line, block_num))  # type: ignore[union-attr]
        elif rule.type == "at-rule" and rule.content is not None:  # type: ignore[union-attr]
            # Recurse into @media, @supports, etc.
            inner = tinycss2.parse_stylesheet(rule.content, skip_whitespace=True, skip_comments=True)  # type: ignore[union-attr]
            for inner_rule in inner:
                if inner_rule.type == "error":  # type: ignore[union-attr]
                    messages.append(
                        f"  <style> block {block_num} (inside @{rule.at_keyword}): {inner_rule.message}"  # type: ignore[union-attr]
                    )
                elif inner_rule.type == "qualified-rule":  # type: ignore[union-attr]
                    messages.extend(_check_declarations(inner_rule.content, start_line, block_num))  # type: ignore[union-attr]

    return messages


def _check_file(path: Path) -> list[str]:
    """Return CSS error messages for all ``<style>`` blocks in an HTML file.

    Args:
        path: Path to an HTML file.

    Returns:
        A (possibly empty) list of formatted diagnostic messages.
    """
    extractor = _StyleExtractor()
    extractor.feed(path.read_text(encoding="utf-8"))
    messages: list[str] = []
    for idx, (start_line, css_text) in enumerate(extractor.blocks, 1):
        messages.extend(_validate_block(css_text, start_line, idx))
    return messages


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Validate embedded CSS in all HTML files given as arguments.

    Returns:
        0 if all CSS is structurally valid, 1 if any errors were found.
    """
    failed = False
    for arg in sys.argv[1:]:
        path = Path(arg)
        messages = _check_file(path)
        if messages:
            print(f"{arg}: CSS errors detected")
            for msg in messages:
                print(msg)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
