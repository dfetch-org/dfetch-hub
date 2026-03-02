"""Tests for dfetch_hub.catalog.sources: HTTP helpers and README fetching."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.error import URLError

from dfetch_hub.catalog.sources import (
    BaseManifest,
    _fetch_raw,
    _raw_url,
    fetch_readme,
    fetch_readme_for_homepage,
)

# ---------------------------------------------------------------------------
# BaseManifest
# ---------------------------------------------------------------------------


def test_base_manifest_urls_defaults_to_empty_dict() -> None:
    """urls field defaults to an empty dict when not supplied."""
    m = BaseManifest(
        entry_name="pkg",
        package_name="pkg",
        description="desc",
        homepage=None,
        license=None,
        version=None,
    )
    assert m.urls == {}


def test_base_manifest_urls_accepts_populated_dict() -> None:
    """urls field stores the supplied mapping unchanged."""
    m = BaseManifest(
        entry_name="pkg",
        package_name="pkg",
        description="desc",
        homepage="https://example.com",
        license=None,
        version=None,
        urls={"Homepage": "https://example.com", "Source": "https://github.com/x/y"},
    )
    assert m.urls["Homepage"] == "https://example.com"
    assert m.urls["Source"] == "https://github.com/x/y"


# ---------------------------------------------------------------------------
# _raw_url
# ---------------------------------------------------------------------------


def test_raw_url_produces_correct_format() -> None:
    """URL is assembled from owner, repo, branch, and filename."""
    url = _raw_url("owner", "repo", "main", "README.md")
    assert url == "https://raw.githubusercontent.com/owner/repo/main/README.md"


def test_raw_url_reflects_branch_and_filename() -> None:
    """Different branch and filename produce the expected URL."""
    url = _raw_url("org", "project", "master", "README.rst")
    assert "master" in url
    assert "README.rst" in url
    assert "org/project" in url


# ---------------------------------------------------------------------------
# _fetch_raw
# ---------------------------------------------------------------------------


def _make_response(content: bytes) -> MagicMock:
    """Build a mock HTTP response that acts as a context manager."""
    resp = MagicMock()
    resp.read.return_value = content
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_fetch_raw_returns_decoded_content_on_success() -> None:
    """Returns the response body as a string on a 200-OK."""
    with patch(
        "dfetch_hub.catalog.sources.urlopen",
        return_value=_make_response(b"hello world"),
    ):
        result = _fetch_raw("https://example.com/file")

    assert result == "hello world"


def test_fetch_raw_returns_none_on_url_error() -> None:
    """Returns None when urllib raises URLError (network failure, 404, etc.)."""
    with patch("dfetch_hub.catalog.sources.urlopen", side_effect=URLError("timeout")):
        result = _fetch_raw("https://example.com/file")

    assert result is None


def test_fetch_raw_returns_none_on_os_error() -> None:
    """Returns None when urllib raises OSError (socket-level failure)."""
    with patch(
        "dfetch_hub.catalog.sources.urlopen", side_effect=OSError("connection reset")
    ):
        result = _fetch_raw("https://example.com/file")

    assert result is None


# ---------------------------------------------------------------------------
# fetch_readme
# ---------------------------------------------------------------------------


def test_fetch_readme_returns_first_found_content() -> None:
    """Returns the first non-None result from the main branch, README.md."""

    def _side_effect(url: str) -> str | None:
        return "# README" if ("main" in url and "README.md" in url) else None

    with patch("dfetch_hub.catalog.sources._fetch_raw", side_effect=_side_effect):
        result = fetch_readme("owner", "repo")

    assert result == "# README"


def test_fetch_readme_falls_back_to_master_branch() -> None:
    """Falls back to master when main branch has no README."""

    def _side_effect(url: str) -> str | None:
        return "# Master README" if "master" in url else None

    with patch("dfetch_hub.catalog.sources._fetch_raw", side_effect=_side_effect):
        result = fetch_readme("owner", "repo")

    assert result == "# Master README"


def test_fetch_readme_returns_none_when_all_attempts_fail() -> None:
    """Returns None when every branch/filename combination returns nothing."""
    with patch("dfetch_hub.catalog.sources._fetch_raw", return_value=None):
        result = fetch_readme("owner", "repo")

    assert result is None


# ---------------------------------------------------------------------------
# fetch_readme_for_homepage
# ---------------------------------------------------------------------------


def test_fetch_readme_for_homepage_returns_none_for_none_input() -> None:
    """Returns None immediately for None input."""
    assert fetch_readme_for_homepage(None) is None


def test_fetch_readme_for_homepage_returns_none_for_non_vcs_url() -> None:
    """Returns None when the URL cannot be parsed as host/owner/repo."""
    assert fetch_readme_for_homepage("https://example.com") is None


def test_fetch_readme_for_homepage_returns_none_for_non_github_host() -> None:
    """Returns None for non-GitHub VCS URLs; fetch_readme is not called."""
    with patch("dfetch_hub.catalog.sources.fetch_readme") as mock_fn:
        result = fetch_readme_for_homepage("https://gitlab.com/owner/repo")

    mock_fn.assert_not_called()
    assert result is None


def test_fetch_readme_for_homepage_delegates_to_fetch_readme_for_github() -> None:
    """Calls fetch_readme(owner, repo) for GitHub URLs and returns its result."""
    with patch(
        "dfetch_hub.catalog.sources.fetch_readme", return_value="# content"
    ) as mock_fn:
        result = fetch_readme_for_homepage("https://github.com/myorg/myrepo")

    mock_fn.assert_called_once_with("myorg", "myrepo")
    assert result == "# content"
