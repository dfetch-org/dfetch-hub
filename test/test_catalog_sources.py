"""Tests for dfetch_hub.catalog.sources: VCS URL parsing and README fetching."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from dfetch_hub.catalog.sources import (
    BaseManifest,
    _fetch_raw,
    _raw_url,
    fetch_readme,
    fetch_readme_for_homepage,
    parse_vcs_slug,
)

# ---------------------------------------------------------------------------
# parse_vcs_slug — valid URLs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://github.com/abseil/abseil-cpp",
            ("github.com", "abseil", "abseil-cpp"),
        ),
        (
            "https://github.com/abseil/abseil-cpp.git",
            ("github.com", "abseil", "abseil-cpp"),
        ),
        (
            "https://github.com/abseil/abseil-cpp/",
            ("github.com", "abseil", "abseil-cpp"),
        ),
        ("http://github.com/foo/bar", ("github.com", "foo", "bar")),
        ("https://gitlab.com/org/repo", ("gitlab.com", "org", "repo")),
        ("https://bitbucket.org/org/repo", ("bitbucket.org", "org", "repo")),
        (
            "https://gitea.example.com/org/repo",
            ("gitea.example.com", "org", "repo"),
        ),
        (
            "https://git.company.internal/team/project",
            ("git.company.internal", "team", "project"),
        ),
    ],
)
def test_parse_vcs_slug_valid_urls(url: str, expected: tuple[str, str, str]) -> None:
    """parse_vcs_slug extracts (host, owner, repo) from any VCS URL."""
    assert parse_vcs_slug(url) == expected


def test_parse_vcs_slug_lowercases_all_parts() -> None:
    """parse_vcs_slug lowercases host, owner, and repo."""
    assert parse_vcs_slug("https://GitHub.COM/ABSEIL/Abseil-CPP") == (
        "github.com",
        "abseil",
        "abseil-cpp",
    )


def test_parse_vcs_slug_strips_whitespace() -> None:
    """parse_vcs_slug handles URLs with leading/trailing whitespace."""
    assert parse_vcs_slug("  https://github.com/owner/repo  ") == (
        "github.com",
        "owner",
        "repo",
    )


# ---------------------------------------------------------------------------
# parse_vcs_slug — invalid URLs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "",
        "https://github.com/only-org",
        "https://github.com/",
        "ftp://github.com/org/repo",
        "https://github.com",
    ],
)
def test_parse_vcs_slug_invalid_returns_none(url: str) -> None:
    """parse_vcs_slug returns None for URLs that don't match host/owner/repo."""
    assert parse_vcs_slug(url) is None


# ---------------------------------------------------------------------------
# _raw_url
# ---------------------------------------------------------------------------


def test_raw_url_format() -> None:
    """_raw_url builds a raw.githubusercontent.com URL."""
    url = _raw_url("owner", "repo", "main", "README.md")
    assert url == "https://raw.githubusercontent.com/owner/repo/main/README.md"


def test_raw_url_different_branch() -> None:
    """_raw_url handles different branch names."""
    url = _raw_url("owner", "repo", "develop", "docs/guide.md")
    assert url == "https://raw.githubusercontent.com/owner/repo/develop/docs/guide.md"


# ---------------------------------------------------------------------------
# _fetch_raw — success
# ---------------------------------------------------------------------------


def test_fetch_raw_success() -> None:
    """_fetch_raw returns the response body on success."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"README content"
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = lambda *args: None

    with patch("dfetch_hub.catalog.sources.urlopen", return_value=mock_response):
        result = _fetch_raw("https://example.com/file.txt")
        assert result == "README content"


def test_fetch_raw_sets_user_agent() -> None:
    """_fetch_raw sends a custom User-Agent header."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"content"
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = lambda *args: None

    with patch("dfetch_hub.catalog.sources.urlopen", return_value=mock_response) as mock_urlopen:
        with patch("dfetch_hub.catalog.sources.Request") as mock_request:
            _fetch_raw("https://example.com/file.txt")
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[1]["headers"]["User-Agent"] == "dfetch-hub/0.0.1"


def test_fetch_raw_decodes_utf8() -> None:
    """_fetch_raw decodes the response as UTF-8."""
    mock_response = MagicMock()
    mock_response.read.return_value = "Héllo wörld".encode("utf-8")
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = lambda *args: None

    with patch("dfetch_hub.catalog.sources.urlopen", return_value=mock_response):
        result = _fetch_raw("https://example.com/file.txt")
        assert result == "Héllo wörld"


def test_fetch_raw_replaces_invalid_utf8() -> None:
    """_fetch_raw replaces invalid UTF-8 sequences instead of raising."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"Valid start\xff\xfeInvalid bytes"
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = lambda *args: None

    with patch("dfetch_hub.catalog.sources.urlopen", return_value=mock_response):
        result = _fetch_raw("https://example.com/file.txt")
        assert "Valid start" in result


# ---------------------------------------------------------------------------
# _fetch_raw — failure
# ---------------------------------------------------------------------------


def test_fetch_raw_url_error_returns_none() -> None:
    """_fetch_raw returns None on URLError."""
    with patch(
        "dfetch_hub.catalog.sources.urlopen", side_effect=URLError("Network error")
    ):
        assert _fetch_raw("https://example.com/file.txt") is None


def test_fetch_raw_os_error_returns_none() -> None:
    """_fetch_raw returns None on OSError."""
    with patch("dfetch_hub.catalog.sources.urlopen", side_effect=OSError("Disk error")):
        assert _fetch_raw("https://example.com/file.txt") is None


def test_fetch_raw_timeout_error_returns_none() -> None:
    """_fetch_raw returns None on timeout."""
    with patch(
        "dfetch_hub.catalog.sources.urlopen", side_effect=TimeoutError("Timed out")
    ):
        assert _fetch_raw("https://example.com/file.txt") is None


# ---------------------------------------------------------------------------
# fetch_readme — success
# ---------------------------------------------------------------------------


def test_fetch_readme_tries_main_first() -> None:
    """fetch_readme tries the 'main' branch before 'master'."""
    call_count = 0

    def mock_fetch(url: str) -> str | None:
        nonlocal call_count
        call_count += 1
        if "main" in url and "README.md" in url:
            return "README from main"
        return None

    with patch("dfetch_hub.catalog.sources._fetch_raw", side_effect=mock_fetch):
        result = fetch_readme("owner", "repo")
        assert result == "README from main"


def test_fetch_readme_falls_back_to_master() -> None:
    """fetch_readme tries 'master' when 'main' fails."""

    def mock_fetch(url: str) -> str | None:
        if "master" in url and "README.md" in url:
            return "README from master"
        return None

    with patch("dfetch_hub.catalog.sources._fetch_raw", side_effect=mock_fetch):
        result = fetch_readme("owner", "repo")
        assert result == "README from master"


def test_fetch_readme_tries_multiple_filenames() -> None:
    """fetch_readme tries README.md, readme.md, Readme.md, etc."""

    def mock_fetch(url: str) -> str | None:
        if "Readme.md" in url:
            return "Content from Readme.md"
        return None

    with patch("dfetch_hub.catalog.sources._fetch_raw", side_effect=mock_fetch):
        result = fetch_readme("owner", "repo")
        assert result == "Content from Readme.md"


def test_fetch_readme_returns_first_match() -> None:
    """fetch_readme returns the first successful fetch."""

    def mock_fetch(url: str) -> str | None:
        if "README.md" in url:
            return "First match"
        if "readme.md" in url:
            return "Second match"
        return None

    with patch("dfetch_hub.catalog.sources._fetch_raw", side_effect=mock_fetch):
        result = fetch_readme("owner", "repo")
        assert result == "First match"


# ---------------------------------------------------------------------------
# fetch_readme — failure
# ---------------------------------------------------------------------------


def test_fetch_readme_returns_none_when_all_fail() -> None:
    """fetch_readme returns None when no README is found."""
    with patch("dfetch_hub.catalog.sources._fetch_raw", return_value=None):
        assert fetch_readme("owner", "repo") is None


# ---------------------------------------------------------------------------
# fetch_readme_for_homepage — GitHub
# ---------------------------------------------------------------------------


def test_fetch_readme_for_homepage_github() -> None:
    """fetch_readme_for_homepage delegates to fetch_readme for GitHub URLs."""
    with patch(
        "dfetch_hub.catalog.sources.fetch_readme", return_value="README content"
    ) as mock_fetch:
        result = fetch_readme_for_homepage("https://github.com/owner/repo")
        assert result == "README content"
        mock_fetch.assert_called_once_with("owner", "repo")


def test_fetch_readme_for_homepage_github_with_git_suffix() -> None:
    """fetch_readme_for_homepage handles GitHub URLs with .git suffix."""
    with patch(
        "dfetch_hub.catalog.sources.fetch_readme", return_value="README"
    ) as mock_fetch:
        result = fetch_readme_for_homepage("https://github.com/owner/repo.git")
        assert result == "README"
        mock_fetch.assert_called_once_with("owner", "repo")


# ---------------------------------------------------------------------------
# fetch_readme_for_homepage — non-GitHub
# ---------------------------------------------------------------------------


def test_fetch_readme_for_homepage_gitlab_returns_none() -> None:
    """fetch_readme_for_homepage returns None for GitLab URLs (not supported)."""
    assert fetch_readme_for_homepage("https://gitlab.com/org/repo") is None


def test_fetch_readme_for_homepage_bitbucket_returns_none() -> None:
    """fetch_readme_for_homepage returns None for Bitbucket URLs (not supported)."""
    assert fetch_readme_for_homepage("https://bitbucket.org/org/repo") is None


def test_fetch_readme_for_homepage_custom_host_returns_none() -> None:
    """fetch_readme_for_homepage returns None for custom VCS hosts."""
    assert fetch_readme_for_homepage("https://git.company.com/org/repo") is None


# ---------------------------------------------------------------------------
# fetch_readme_for_homepage — invalid input
# ---------------------------------------------------------------------------


def test_fetch_readme_for_homepage_none_returns_none() -> None:
    """fetch_readme_for_homepage returns None for None input."""
    assert fetch_readme_for_homepage(None) is None


def test_fetch_readme_for_homepage_empty_string_returns_none() -> None:
    """fetch_readme_for_homepage returns None for empty string."""
    assert fetch_readme_for_homepage("") is None


def test_fetch_readme_for_homepage_invalid_url_returns_none() -> None:
    """fetch_readme_for_homepage returns None for non-VCS URLs."""
    assert fetch_readme_for_homepage("https://example.com/not-a-repo") is None


# ---------------------------------------------------------------------------
# BaseManifest dataclass
# ---------------------------------------------------------------------------


def test_base_manifest_required_fields() -> None:
    """BaseManifest can be created with all required fields."""
    manifest = BaseManifest(
        entry_name="my-pkg",
        package_name="My Package",
        description="A sample package",
        homepage="https://github.com/org/repo",
        license="MIT",
        version="1.0.0",
    )
    assert manifest.entry_name == "my-pkg"
    assert manifest.package_name == "My Package"
    assert manifest.description == "A sample package"
    assert manifest.homepage == "https://github.com/org/repo"
    assert manifest.license == "MIT"
    assert manifest.version == "1.0.0"
    assert manifest.readme_content is None


def test_base_manifest_with_readme_content() -> None:
    """BaseManifest stores optional readme_content."""
    manifest = BaseManifest(
        entry_name="pkg",
        package_name="pkg",
        description="desc",
        homepage=None,
        license=None,
        version=None,
        readme_content="# README\n\nContent here.",
    )
    assert manifest.readme_content == "# README\n\nContent here."


def test_base_manifest_none_values() -> None:
    """BaseManifest allows None for optional fields."""
    manifest = BaseManifest(
        entry_name="pkg",
        package_name="pkg",
        description="desc",
        homepage=None,
        license=None,
        version=None,
    )
    assert manifest.homepage is None
    assert manifest.license is None
    assert manifest.version is None
    assert manifest.readme_content is None


# ---------------------------------------------------------------------------
# fetch_readme — edge cases
# ---------------------------------------------------------------------------


def test_fetch_readme_tries_all_combinations() -> None:
    """fetch_readme tries all (branch, filename) combinations before giving up."""
    call_count = 0

    def mock_fetch(url: str) -> str | None:
        nonlocal call_count
        call_count += 1
        # Only the last combination succeeds
        if "master" in url and "README" in url and "README.md" not in url:
            return "Plain README from master"
        return None

    with patch("dfetch_hub.catalog.sources._fetch_raw", side_effect=mock_fetch):
        result = fetch_readme("owner", "repo")
        assert result == "Plain README from master"
        # Should have tried: main + 5 filenames, then master + 4 filenames before match = 9 total
        assert call_count == 9


def test_fetch_readme_for_homepage_preserves_case_in_org_repo() -> None:
    """fetch_readme_for_homepage passes lowercased org/repo to fetch_readme."""
    with patch("dfetch_hub.catalog.sources.fetch_readme", return_value="README") as mock_fetch:
        fetch_readme_for_homepage("https://github.com/OwNeR/RePoSiToRy")
        # parse_vcs_slug lowercases, so fetch_readme receives lowercased values
        mock_fetch.assert_called_once_with("owner", "repository")