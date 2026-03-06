"""Tests for dfetch_hub.catalog.clib: Packages.md parsing and limit handling."""

from __future__ import annotations

import json
import textwrap
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from dfetch_hub.catalog.sources.clib import (
    _build_package,
    _fetch_package_json,
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
     - [user/notgithub](https://gitlab.com/user/notgithub) - non-GitHub entry

    ## Networking
     - [nicowillis/http-parser](https://github.com/nicowillis/http-parser) - HTTP request/response parser
    """
)

_PACKAGE_JSON_BUFFER: dict[str, object] = {
    "name": "buffer",
    "version": "0.4.0",
    "repo": "clibs/buffer",
    "description": "Higher level C-string utilities",
    "keywords": ["buf", "buffer", "string"],
    "license": "MIT",
}

_PACKAGE_JSON_STRSPLIT: dict[str, object] = {
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
    """Write _PACKAGES_MD to a temporary file and return its path."""
    p = tmp_path / "Packages.md"
    p.write_text(_PACKAGES_MD, encoding="utf-8")
    return p


def _mock_pkg_json(owner: str, repo: str) -> dict[str, object] | None:
    """Return canned package.json data keyed by (owner, repo)."""
    data: dict[tuple[str, str], dict[str, object]] = {
        ("clibs", "buffer"): _PACKAGE_JSON_BUFFER,
        ("jwerle", "strsplit.h"): _PACKAGE_JSON_STRSPLIT,
    }
    return data.get((owner, repo))


# ---------------------------------------------------------------------------
# _build_package — canonical URL
# ---------------------------------------------------------------------------


def test_build_package_uses_vcs_url_when_no_homepage_in_json() -> None:
    """Falls back to the VCS repo URL when package.json has no homepage."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            return_value=_PACKAGE_JSON_BUFFER,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package(
            "github.com",
            "clibs",
            "buffer",
            "tiny c-string library",
            "String manipulation",
        )

    assert pkg.homepage == "https://github.com/clibs/buffer"


def test_build_package_uses_json_homepage_as_canonical_url() -> None:
    """Prefers the explicit homepage from package.json over the VCS URL."""
    pkg_json = {**_PACKAGE_JSON_BUFFER, "homepage": "https://example.com/buffer"}
    with (
        patch("dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=pkg_json),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("github.com", "clibs", "buffer", "desc", "Strings")

    assert pkg.homepage == "https://example.com/buffer"


def test_build_package_falls_back_to_vcs_url_when_no_package_json() -> None:
    """Uses the VCS URL as homepage when no package.json is found."""
    with (
        patch("dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=None),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("github.com", "owner", "repo", "a tagline", "Cat")

    assert pkg.homepage == "https://github.com/owner/repo"


def test_build_package_non_github_uses_vcs_url() -> None:
    """Non-GitHub entries use their own VCS URL as homepage."""
    with (
        patch("dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=None) as mock_pkg_json,
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None) as mock_readme,
    ):
        pkg = _build_package("gitlab.com", "myorg", "myrepo", "a gitlab lib", "Tools")
    mock_pkg_json.assert_not_called()
    mock_readme.assert_not_called()

    assert pkg.homepage == "https://gitlab.com/myorg/myrepo"


# ---------------------------------------------------------------------------
# _build_package — readme_content
# ---------------------------------------------------------------------------


def test_build_package_stores_fetched_readme() -> None:
    """readme_content is populated from the fetched README for GitHub packages."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            return_value=_PACKAGE_JSON_BUFFER,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=_SAMPLE_README),
    ):
        pkg = _build_package("github.com", "clibs", "buffer", "desc", "Strings")

    assert pkg.readme_content == _SAMPLE_README


def test_build_package_readme_none_when_not_found() -> None:
    """readme_content is None when the upstream README cannot be fetched."""
    with (
        patch("dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=None),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("github.com", "owner", "repo", "desc", "Cat")

    assert pkg.readme_content is None


def test_build_package_non_github_readme_is_none() -> None:
    """Non-GitHub packages always have readme_content=None (raw URL not available)."""
    with (
        patch("dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=None) as mock_pkg_json,
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None) as mock_readme,
    ):
        pkg = _build_package("gitlab.com", "org", "repo", "desc", "Cat")
    mock_pkg_json.assert_not_called()
    mock_readme.assert_not_called()

    assert pkg.readme_content is None


# ---------------------------------------------------------------------------
# _build_package — other fields
# ---------------------------------------------------------------------------


def test_build_package_basic_fields() -> None:
    """entry_name, package_name, version, license and keywords are set correctly."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            return_value=_PACKAGE_JSON_BUFFER,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package(
            "github.com",
            "clibs",
            "buffer",
            "tiny c-string library",
            "String manipulation",
        )

    assert pkg.entry_name == "github.com/clibs/buffer"
    assert pkg.package_name == "buffer"
    assert pkg.version == "0.4.0"
    assert pkg.license == "MIT"
    assert "String manipulation" in pkg.keywords
    assert "buffer" in pkg.keywords


def test_json_description_preferred_over_build_package_tagline() -> None:
    """The package.json description takes priority over the wiki tagline."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            return_value=_PACKAGE_JSON_BUFFER,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("github.com", "clibs", "buffer", "my custom tagline", "")

    assert pkg.description == "Higher level C-string utilities"


def test_build_package_falls_back_to_json_description_when_no_tagline() -> None:
    """Falls back to package.json description when the tagline is empty."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            return_value=_PACKAGE_JSON_BUFFER,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("github.com", "clibs", "buffer", "", "String manipulation")

    assert pkg.description == "Higher level C-string utilities"


def test_build_package_no_package_json() -> None:
    """Missing package.json produces a minimal entry from the tagline only."""
    with (
        patch("dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=None),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("github.com", "owner", "repo", "a tagline", "Category")

    assert pkg.package_name == "repo"
    assert pkg.license is None
    assert pkg.version is None
    assert pkg.keywords == ["Category"]


def test_build_package_category_not_duplicated_in_keywords() -> None:
    """Category keyword that already appears in package.json keywords is not duplicated."""
    pkg_json = {**_PACKAGE_JSON_BUFFER, "keywords": ["String manipulation", "buffer"]}
    with (
        patch("dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=pkg_json),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("github.com", "clibs", "buffer", "desc", "String manipulation")

    assert pkg.keywords.count("String manipulation") == 1


# ---------------------------------------------------------------------------
# parse_packages_md — content
# ---------------------------------------------------------------------------


def test_parse_packages_md_includes_non_github_vcs_urls(packages_md_file: Path) -> None:
    """Non-GitHub VCS URLs (e.g. gitlab.com) are included with basic metadata."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file)

    urls = [p.homepage for p in pkgs]
    assert any("gitlab.com" in (u or "") for u in urls), "Expected GitLab entry to be included"


def test_parse_packages_md_non_github_entry_has_no_readme(
    packages_md_file: Path,
) -> None:
    """Non-GitHub entries have readme_content=None since raw URLs are unavailable."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file)

    gitlab_pkg = next(p for p in pkgs if "gitlab.com" in (p.homepage or ""))
    assert gitlab_pkg.readme_content is None


def test_parse_packages_md_category_becomes_keyword(packages_md_file: Path) -> None:
    """Each package carries the nearest section heading as a keyword."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file)

    buffer_pkg = next(p for p in pkgs if p.entry_name == "github.com/clibs/buffer")
    assert "String manipulation" in buffer_pkg.keywords

    jsawk_pkg = next(p for p in pkgs if p.entry_name == "github.com/micha/jsawk")
    assert "Math" in jsawk_pkg.keywords


def test_parse_packages_md_correct_package_count(packages_md_file: Path) -> None:
    """All 5 entries in _PACKAGES_MD are returned (4 GitHub + 1 GitLab)."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file)

    assert len(pkgs) == 5


# ---------------------------------------------------------------------------
# parse_packages_md — limit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_parse_packages_md_limit(packages_md_file: Path, limit: int) -> None:
    """limit=N returns exactly N packages."""
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
    """limit=None returns all 5 packages."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file, limit=None)

    assert len(pkgs) == 5


def test_parse_packages_md_limit_larger_than_total(packages_md_file: Path) -> None:
    """A limit larger than the total count returns all 5 packages."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file, limit=100)

    assert len(pkgs) == 5


def test_parse_packages_md_limit_zero_returns_empty(packages_md_file: Path) -> None:
    """limit=0 must return an empty list, not one package (off-by-one guard)."""
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            side_effect=_mock_pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(packages_md_file, limit=0)

    assert pkgs == []


# ---------------------------------------------------------------------------
# _fetch_package_json
# ---------------------------------------------------------------------------


def test_fetch_package_json_returns_dict_on_valid_response() -> None:
    """Returns the parsed dict when the raw response is valid JSON."""
    data = {"name": "buffer", "version": "0.4.0"}
    with patch("dfetch_hub.catalog.sources.clib.fetch_raw", return_value=json.dumps(data)):
        result = _fetch_package_json("clibs", "buffer")

    assert result == data


def test_fetch_package_json_returns_none_when_fetch_fails() -> None:
    """Returns None when every HTTP fetch attempt fails."""
    with patch("dfetch_hub.catalog.sources.clib.fetch_raw", return_value=None):
        result = _fetch_package_json("owner", "repo")

    assert result is None


def test_fetch_package_json_returns_none_on_bad_json() -> None:
    """Returns None when the response body is not valid JSON."""
    with patch("dfetch_hub.catalog.sources.clib.fetch_raw", return_value="not json"):
        result = _fetch_package_json("owner", "repo")

    assert result is None


def test_fetch_package_json_returns_none_for_non_object_json() -> None:
    """Returns None when the JSON root is not an object (e.g. a list)."""
    with patch(
        "dfetch_hub.catalog.sources.clib.fetch_raw",
        return_value=json.dumps([1, 2, 3]),
    ):
        result = _fetch_package_json("owner", "repo")

    assert result is None


def test_fetch_package_json_falls_back_to_master_branch() -> None:
    """Returns data from the master branch when main has nothing."""
    data = {"name": "pkg"}

    def _side_effect(url: str) -> str | None:
        return json.dumps(data) if "master" in url else None

    with patch("dfetch_hub.catalog.sources.clib.fetch_raw", side_effect=_side_effect):
        result = _fetch_package_json("owner", "repo")

    assert result == data


# ---------------------------------------------------------------------------
# _build_package — keywords edge cases
# ---------------------------------------------------------------------------


def test_build_package_string_keywords_in_package_json() -> None:
    """A string-valued keywords field is treated as a single-element list."""
    pkg_json = {**_PACKAGE_JSON_BUFFER, "keywords": "single-keyword"}
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            return_value=pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("github.com", "clibs", "buffer", "desc", "Cat")

    assert "single-keyword" in pkg.keywords


def test_build_package_non_list_non_string_keywords_ignored() -> None:
    """A non-list, non-string keywords value produces no JSON keywords."""
    pkg_json = {**_PACKAGE_JSON_BUFFER, "keywords": 42}
    with (
        patch(
            "dfetch_hub.catalog.sources.clib._fetch_package_json",
            return_value=pkg_json,
        ),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkg = _build_package("github.com", "clibs", "buffer", "desc", "Cat")

    assert pkg.keywords == ["Cat"]


# ---------------------------------------------------------------------------
# parse_packages_md — skips URLs without recognized VCS host
# ---------------------------------------------------------------------------

_PACKAGES_MD_WITH_INVALID_URL = textwrap.dedent(
    """\
    ## Tools
     - [good/repo](https://github.com/good/repo) - a valid entry
     - [bad entry](ftp://invalid.host/no/repo) - invalid URL scheme
    """
)


def test_parse_packages_md_skips_unrecognized_vcs_url(tmp_path: Path) -> None:
    """Bullets with URLs that don't match any VCS pattern are silently skipped."""
    p = tmp_path / "Packages.md"
    p.write_text(_PACKAGES_MD_WITH_INVALID_URL, encoding="utf-8")

    with (
        patch("dfetch_hub.catalog.sources.clib._fetch_package_json", return_value=None),
        patch("dfetch_hub.catalog.sources.clib.fetch_readme", return_value=None),
    ):
        pkgs = parse_packages_md(p)

    assert len(pkgs) == 1
    assert pkgs[0].entry_name == "github.com/good/repo"
