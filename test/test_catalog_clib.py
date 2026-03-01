"""Tests for dfetch_hub.catalog.clib: Packages.md parsing and limit handling."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from dfetch_hub.catalog.sources.clib import (
    CLibPackage,
    _build_package,
    parse_packages_md,
)

# ---------------------------------------------------------------------------
# Fixtures / shared data
# ---------------------------------------------------------------------------

_PACKAGES_MD = textwrap.dedent(
    """\
    List of available packages.

    ## String manipulation
     - [clibs/buffer](https://github.com/clibs/buffer) - tiny c-string library
     - [jwerle/strsplit.h](https://github.com/jwerle/strsplit.h) - Split a string by a delimiter

    ## Math
     - [micha/jsawk](https://github.com/micha/jsawk) - like awk, for JSON
     - [user/notgithub](https://gitlab.com/user/notgithub) - should be skipped

    ## Networking
     - [nicowillis/http-parser](https://github.com/nicowillis/http-parser) - HTTP request/response parser
    """
)

_PACKAGE_JSON_BUFFER = {
    "name": "buffer",
    "version": "0.4.0",
    "repo": "clibs/buffer",
    "description": "Higher level C-string utilities",
    "keywords": ["buf", "buffer", "string"],
    "license": "MIT",
}

_PACKAGE_JSON_STRSPLIT = {
    "name": "strsplit",
    "version": "1.0.0",
    "repo": "jwerle/strsplit.h",
    "description": "String splitting for C",
    "keywords": ["string", "split"],
    "license": "MIT",
}

_SAMPLE_README = "# buffer\n\nA tiny C string library.\n"


@pytest.fixture
def packages_md_file(tmp_path: Path) -> Path:
    p = tmp_path / "Packages.md"
    p.write_text(_PACKAGES_MD, encoding="utf-8")
    return p


def _mock_pkg_json(owner: str, repo: str) -> dict | None:
    data = {
        ("clibs", "buffer"): _PACKAGE_JSON_BUFFER,
        ("jwerle", "strsplit.h"): _PACKAGE_JSON_STRSPLIT,
    }
    return data.get((owner, repo))


# ---------------------------------------------------------------------------
# _build_package — canonical URL
# ---------------------------------------------------------------------------


def test_build_package_uses_github_url_when_no_homepage_in_json() -> None:
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            return_value=_PACKAGE_JSON_BUFFER,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package(
            "clibs", "buffer", "tiny c-string library", "String manipulation"
        )

    assert pkg.homepage == "https://github.com/clibs/buffer"


def test_build_package_uses_json_homepage_as_canonical_url() -> None:
    pkg_json = {**_PACKAGE_JSON_BUFFER, "homepage": "https://example.com/buffer"}
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=pkg_json
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("clibs", "buffer", "desc", "Strings")

    assert pkg.homepage == "https://example.com/buffer"


def test_build_package_falls_back_to_github_url_when_no_package_json() -> None:
    with (
        patch("dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=None),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("owner", "repo", "a tagline", "Cat")

    assert pkg.homepage == "https://github.com/owner/repo"


# ---------------------------------------------------------------------------
# _build_package — readme_content
# ---------------------------------------------------------------------------


def test_build_package_stores_fetched_readme() -> None:
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            return_value=_PACKAGE_JSON_BUFFER,
        ),
        patch(
            "dfetch_hub.catalog.sources.clib.fetch_readme", return_value=_SAMPLE_README
        ),
    ):
        pkg = _build_package("clibs", "buffer", "desc", "Strings")

    assert pkg.readme_content == _SAMPLE_README


def test_build_package_readme_none_when_not_found() -> None:
    with (
        patch("dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=None),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("owner", "repo", "desc", "Cat")

    assert pkg.readme_content is None


# ---------------------------------------------------------------------------
# _build_package — other fields
# ---------------------------------------------------------------------------


def test_build_package_basic_fields() -> None:
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            return_value=_PACKAGE_JSON_BUFFER,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package(
            "clibs", "buffer", "tiny c-string library", "String manipulation"
        )

    assert pkg.port_name == "clibs/buffer"
    assert pkg.package_name == "buffer"
    assert pkg.version == "0.4.0"
    assert pkg.license == "MIT"
    assert "String manipulation" in pkg.keywords
    assert "buffer" in pkg.keywords


def test_build_package_tagline_preferred_over_json_description() -> None:
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            return_value=_PACKAGE_JSON_BUFFER,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("clibs", "buffer", "my custom tagline", "")

    assert pkg.description == "my custom tagline"


def test_build_package_falls_back_to_json_description_when_no_tagline() -> None:
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            return_value=_PACKAGE_JSON_BUFFER,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("clibs", "buffer", "", "String manipulation")

    assert pkg.description == "Higher level C-string utilities"


def test_build_package_no_package_json() -> None:
    with (
        patch("dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=None),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("owner", "repo", "a tagline", "Category")

    assert pkg.package_name == "repo"
    assert pkg.license is None
    assert pkg.version is None
    assert pkg.keywords == ["Category"]


def test_build_package_category_not_duplicated_in_keywords() -> None:
    pkg_json = {**_PACKAGE_JSON_BUFFER, "keywords": ["String manipulation", "buffer"]}
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=pkg_json
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("clibs", "buffer", "desc", "String manipulation")

    assert pkg.keywords.count("String manipulation") == 1


# ---------------------------------------------------------------------------
# parse_packages_md — content
# ---------------------------------------------------------------------------


def test_parse_packages_md_skips_non_github_urls(packages_md_file: Path) -> None:
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file)

    urls = [p.homepage for p in pkgs]
    assert all(
        "github.com" in (u or "") for u in urls
    ), f"Non-GitHub URL slipped in: {urls}"


def test_parse_packages_md_category_becomes_keyword(packages_md_file: Path) -> None:
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file)

    buffer_pkg = next(p for p in pkgs if p.port_name == "clibs/buffer")
    assert "String manipulation" in buffer_pkg.keywords

    jsawk_pkg = next(p for p in pkgs if p.port_name == "micha/jsawk")
    assert "Math" in jsawk_pkg.keywords


def test_parse_packages_md_correct_package_count(packages_md_file: Path) -> None:
    """4 GitHub entries in _PACKAGES_MD (1 non-GitHub skipped)."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file)

    assert len(pkgs) == 4


# ---------------------------------------------------------------------------
# parse_packages_md — limit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_parse_packages_md_limit(packages_md_file: Path, limit: int) -> None:
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file, limit=limit)

    assert len(pkgs) == limit


def test_parse_packages_md_limit_none_returns_all(packages_md_file: Path) -> None:
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file, limit=None)

    assert len(pkgs) == 4


def test_parse_packages_md_limit_larger_than_total(packages_md_file: Path) -> None:
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file, limit=100)

    assert len(pkgs) == 4
