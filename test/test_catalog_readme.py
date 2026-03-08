"""Tests for dfetch_hub.catalog.sources.readme: README parsing and description extraction."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from dfetch_hub.catalog.sources.readme import _extract_description, parse_readme_dir

# ---------------------------------------------------------------------------
# _extract_description test data
# ---------------------------------------------------------------------------

_SIMPLE = "First meaningful line."
_WITH_HEADING = textwrap.dedent(
    """\
    # My Package

    First meaningful line.
    """
)
_WITH_BADGES = textwrap.dedent(
    """\
    # My Package

    [![Build](https://img.shields.io/badge/build-passing-green)](https://example.com)

    First meaningful line.
    """
)
_EMPTY = ""
_ONLY_HEADINGS = textwrap.dedent(
    """\
    # Title

    ## Subtitle
    """
)
_IN_CODE_BLOCK = textwrap.dedent(
    """\
    # Title

    ```python
    print("hello")
    ```

    After the code block.
    """
)
_LONG_LINE = "A" * 200
_MULTILINE = textwrap.dedent(
    """\
    # Title

    First paragraph first line.
    Second line of first paragraph.
    """
)


# ---------------------------------------------------------------------------
# _extract_description tests
# ---------------------------------------------------------------------------


class TestExtractDescription:
    """Unit tests for _extract_description."""

    def test_plain_text(self) -> None:
        """Returns the first line directly when there are no headings."""
        assert _extract_description(_SIMPLE) == "First meaningful line."

    def test_skips_heading(self) -> None:
        """Skips the heading and returns the first body line."""
        assert _extract_description(_WITH_HEADING) == "First meaningful line."

    def test_skips_badge_lines(self) -> None:
        """Skips badge lines ([![…) and returns the next body line."""
        assert _extract_description(_WITH_BADGES) == "First meaningful line."

    def test_empty_text(self) -> None:
        """Returns empty string for empty input."""
        assert _extract_description(_EMPTY) == ""

    def test_only_headings(self) -> None:
        """Returns empty string when there is no body text."""
        assert _extract_description(_ONLY_HEADINGS) == ""

    def test_skips_fenced_code_block(self) -> None:
        """Skips fenced code-block content and returns the next body line."""
        assert _extract_description(_IN_CODE_BLOCK) == "After the code block."

    def test_truncates_long_line(self) -> None:
        """Truncates to 120 characters."""
        result = _extract_description(_LONG_LINE)
        assert len(result) == 120
        assert result == "A" * 120

    def test_returns_first_line_only(self) -> None:
        """Returns only the first non-heading, non-blank line."""
        assert _extract_description(_MULTILINE) == "First paragraph first line."

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("  Indented line.", "Indented line."),
            ("\t\tTabbed line.", "Tabbed line."),
        ],
    )
    def test_strips_whitespace(self, text: str, expected: str) -> None:
        """Strips leading and trailing whitespace from the returned line."""
        assert _extract_description(text) == expected


# ---------------------------------------------------------------------------
# parse_readme_dir tests
# ---------------------------------------------------------------------------


class TestParseReadmeDir:
    """Unit tests for parse_readme_dir."""

    def test_parses_readme_md(self, tmp_path: Path) -> None:
        """Parses a README.md file and returns a BaseManifest."""
        pkg = tmp_path / "my-pkg"
        pkg.mkdir()
        (pkg / "README.md").write_text("# My Package\n\nA great package.", encoding="utf-8")

        result = parse_readme_dir(pkg)

        assert result is not None
        assert result.entry_name == "my-pkg"
        assert result.package_name == "my-pkg"
        assert result.description == "A great package."
        assert result.homepage is None
        assert result.license is None
        assert result.version is None
        assert result.readme_content is not None
        assert "A great package." in result.readme_content
        assert result.in_project_repo is True

    def test_parses_readme_rst(self, tmp_path: Path) -> None:
        """Falls back to README.rst when README.md is absent."""
        pkg = tmp_path / "rst-pkg"
        pkg.mkdir()
        (pkg / "README.rst").write_text("RST description here.", encoding="utf-8")

        result = parse_readme_dir(pkg)

        assert result is not None
        assert result.entry_name == "rst-pkg"
        assert result.description == "RST description here."

    def test_returns_none_when_no_readme(self, tmp_path: Path) -> None:
        """Returns None when the directory contains no README file."""
        pkg = tmp_path / "empty-pkg"
        pkg.mkdir()

        assert parse_readme_dir(pkg) is None

    def test_readme_content_stored(self, tmp_path: Path) -> None:
        """The full README text is stored in readme_content."""
        content = "# Title\n\nLine one.\nLine two.\n"
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "README.md").write_text(content, encoding="utf-8")

        result = parse_readme_dir(pkg)

        assert result is not None
        assert result.readme_content == content

    @pytest.mark.parametrize("filename", ["readme.md", "Readme.md", "README"])
    def test_case_variants(self, tmp_path: Path, filename: str) -> None:
        """Recognises common README filename variants."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / filename).write_text("Description.", encoding="utf-8")

        result = parse_readme_dir(pkg)

        assert result is not None
        assert result.description == "Description."

    def test_prefers_readme_md_over_rst(self, tmp_path: Path) -> None:
        """README.md takes priority when both README.md and README.rst exist."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "README.md").write_text("Markdown description.", encoding="utf-8")
        (pkg / "README.rst").write_text("RST description.", encoding="utf-8")

        result = parse_readme_dir(pkg)

        assert result is not None
        assert result.description == "Markdown description."

    def test_invalid_utf8_handled(self, tmp_path: Path) -> None:
        """Binary garbage in a README is decoded leniently without raising."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "README.md").write_bytes(b"Valid start.\n\xff\xfe Invalid bytes.")

        result = parse_readme_dir(pkg)

        assert result is not None
        assert result.entry_name == "pkg"

    def test_returns_none_on_read_oserror(self, tmp_path: Path) -> None:
        """Returns None when read_text raises OSError (e.g. permission denied)."""
        from pathlib import Path as _Path
        from unittest.mock import patch

        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "README.md").touch()

        with patch.object(_Path, "read_text", side_effect=OSError("permission denied")):
            result = parse_readme_dir(pkg)

        assert result is None
