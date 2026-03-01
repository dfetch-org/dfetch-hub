"""Tests for dfetch_hub.catalog.sources.vcpkg: vcpkg.json manifest parsing."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from dfetch_hub.catalog.sources.vcpkg import (
    VcpkgManifest,
    _extract_dependencies,
    _extract_description,
    _extract_version,
    parse_vcpkg_json,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_fetch_readme() -> object:
    """Prevent real network calls to fetch_readme_for_homepage in all tests."""
    with patch(
        "dfetch_hub.catalog.sources.vcpkg.fetch_readme_for_homepage", return_value=None
    ):
        yield


@pytest.fixture
def abseil_manifest() -> dict[str, object]:
    """Return a typical vcpkg.json for abseil."""
    return {
        "name": "abseil",
        "version-semver": "20240116.2",
        "description": "Abseil Common Libraries (C++) from Google",
        "homepage": "https://github.com/abseil/abseil-cpp",
        "license": "Apache-2.0",
        "dependencies": [
            "vcpkg-cmake",
            "vcpkg-cmake-config",
            {"name": "some-feature", "platform": "windows"},
        ],
    }


@pytest.fixture
def entry_dir_with_manifest(tmp_path: Path, abseil_manifest: dict[str, object]) -> Path:
    """Create an entry directory with a vcpkg.json file."""
    entry = tmp_path / "abseil"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(json.dumps(abseil_manifest), encoding="utf-8")
    return entry


# ---------------------------------------------------------------------------
# _extract_version
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data, expected",
    [
        ({"version-semver": "1.2.3"}, "1.2.3"),
        ({"version": "2024-01-15"}, "2024-01-15"),
        ({"version-date": "2024-01-15"}, "2024-01-15"),
        ({"version-relaxed": "1.2.3-alpha"}, "1.2.3-alpha"),
        ({"version-string": "custom-version"}, "custom-version"),
    ],
)
def test_extract_version_various_fields(
    data: dict[str, object], expected: str
) -> None:
    """_extract_version returns the first version field found."""
    assert _extract_version(data) == expected


def test_extract_version_precedence() -> None:
    """_extract_version prefers version-semver over other version fields."""
    data = {
        "version-semver": "1.2.3",
        "version": "2024-01-15",
        "version-date": "2024-02-01",
    }
    assert _extract_version(data) == "1.2.3"


def test_extract_version_missing_returns_none() -> None:
    """_extract_version returns None when no version field is present."""
    assert _extract_version({"name": "pkg"}) is None


def test_extract_version_empty_dict() -> None:
    """_extract_version handles an empty dict."""
    assert _extract_version({}) is None


# ---------------------------------------------------------------------------
# _extract_description
# ---------------------------------------------------------------------------


def test_extract_description_string() -> None:
    """_extract_description handles a plain string description."""
    data = {"description": "A simple package"}
    assert _extract_description(data) == "A simple package"


def test_extract_description_list() -> None:
    """_extract_description joins list elements with spaces."""
    data = {"description": ["First line.", "Second line.", "Third line."]}
    assert _extract_description(data) == "First line. Second line. Third line."


def test_extract_description_missing() -> None:
    """_extract_description returns empty string when description is missing."""
    assert _extract_description({"name": "pkg"}) == ""


def test_extract_description_empty_string() -> None:
    """_extract_description returns empty string for an empty description."""
    assert _extract_description({"description": ""}) == ""


def test_extract_description_empty_list() -> None:
    """_extract_description handles an empty list."""
    assert _extract_description({"description": []}) == ""


def test_extract_description_mixed_list() -> None:
    """_extract_description converts non-string list items to strings."""
    data = {"description": ["First", 123, "Third"]}
    assert _extract_description(data) == "First 123 Third"


# ---------------------------------------------------------------------------
# _extract_dependencies
# ---------------------------------------------------------------------------


def test_extract_dependencies_plain_strings() -> None:
    """_extract_dependencies handles a list of plain dependency names."""
    data = {"dependencies": ["zlib", "boost", "fmt"]}
    assert _extract_dependencies(data) == ["zlib", "boost", "fmt"]


def test_extract_dependencies_dict_entries() -> None:
    """_extract_dependencies extracts 'name' from dict entries."""
    data = {
        "dependencies": [
            "zlib",
            {"name": "boost", "features": ["system"]},
            {"name": "fmt", "platform": "windows"},
        ]
    }
    assert _extract_dependencies(data) == ["zlib", "boost", "fmt"]


def test_extract_dependencies_missing_name_in_dict() -> None:
    """_extract_dependencies skips dict entries without a 'name' key."""
    data = {"dependencies": ["zlib", {"features": ["test"]}, "fmt"]}
    assert _extract_dependencies(data) == ["zlib", "fmt"]


def test_extract_dependencies_missing_field() -> None:
    """_extract_dependencies returns empty list when dependencies is missing."""
    assert _extract_dependencies({"name": "pkg"}) == []


def test_extract_dependencies_not_a_list() -> None:
    """_extract_dependencies returns empty list when dependencies is not a list."""
    data = {"dependencies": "not-a-list"}
    assert _extract_dependencies(data) == []


def test_extract_dependencies_empty_list() -> None:
    """_extract_dependencies handles an empty dependencies list."""
    assert _extract_dependencies({"dependencies": []}) == []


def test_extract_dependencies_mixed_valid_invalid() -> None:
    """_extract_dependencies extracts valid entries and skips invalid ones."""
    data = {
        "dependencies": [
            "valid1",
            {"name": "valid2"},
            123,
            {"no-name-key": "value"},
            "valid3",
        ]
    }
    assert _extract_dependencies(data) == ["valid1", "valid2", "valid3"]


# ---------------------------------------------------------------------------
# parse_vcpkg_json — basic parsing
# ---------------------------------------------------------------------------


def test_parse_vcpkg_json_basic(entry_dir_with_manifest: Path) -> None:
    """parse_vcpkg_json extracts all standard fields from vcpkg.json."""
    manifest = parse_vcpkg_json(entry_dir_with_manifest)
    assert manifest is not None
    assert manifest.entry_name == "abseil"
    assert manifest.package_name == "abseil"
    assert manifest.description == "Abseil Common Libraries (C++) from Google"
    assert manifest.homepage == "https://github.com/abseil/abseil-cpp"
    assert manifest.license == "Apache-2.0"
    assert manifest.version == "20240116.2"


def test_parse_vcpkg_json_dependencies(entry_dir_with_manifest: Path) -> None:
    """parse_vcpkg_json extracts and flattens the dependencies list."""
    manifest = parse_vcpkg_json(entry_dir_with_manifest)
    assert manifest is not None
    assert "vcpkg-cmake" in manifest.dependencies
    assert "vcpkg-cmake-config" in manifest.dependencies
    assert "some-feature" in manifest.dependencies


def test_parse_vcpkg_json_entry_name_from_dir(tmp_path: Path) -> None:
    """parse_vcpkg_json uses the directory name as entry_name."""
    entry = tmp_path / "my-custom-name"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps({"name": "pkg", "description": "A package"}), encoding="utf-8"
    )

    manifest = parse_vcpkg_json(entry)
    assert manifest is not None
    assert manifest.entry_name == "my-custom-name"


def test_parse_vcpkg_json_package_name_from_json(entry_dir_with_manifest: Path) -> None:
    """parse_vcpkg_json uses the 'name' field from vcpkg.json as package_name."""
    manifest = parse_vcpkg_json(entry_dir_with_manifest)
    assert manifest is not None
    assert manifest.package_name == "abseil"


def test_parse_vcpkg_json_package_name_fallback_to_dir(tmp_path: Path) -> None:
    """parse_vcpkg_json falls back to directory name when 'name' is missing."""
    entry = tmp_path / "fallback-pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps({"description": "No name field"}), encoding="utf-8"
    )

    manifest = parse_vcpkg_json(entry)
    assert manifest is not None
    assert manifest.package_name == "fallback-pkg"


# ---------------------------------------------------------------------------
# parse_vcpkg_json — optional fields
# ---------------------------------------------------------------------------


def test_parse_vcpkg_json_missing_homepage(tmp_path: Path) -> None:
    """parse_vcpkg_json handles missing homepage gracefully."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps({"name": "pkg", "description": "No homepage"}), encoding="utf-8"
    )

    manifest = parse_vcpkg_json(entry)
    assert manifest is not None
    assert manifest.homepage is None


def test_parse_vcpkg_json_missing_license(tmp_path: Path) -> None:
    """parse_vcpkg_json handles missing license gracefully."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps({"name": "pkg", "description": "No license"}), encoding="utf-8"
    )

    manifest = parse_vcpkg_json(entry)
    assert manifest is not None
    assert manifest.license is None


def test_parse_vcpkg_json_missing_version(tmp_path: Path) -> None:
    """parse_vcpkg_json handles missing version gracefully."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps({"name": "pkg", "description": "No version"}), encoding="utf-8"
    )

    manifest = parse_vcpkg_json(entry)
    assert manifest is not None
    assert manifest.version is None


def test_parse_vcpkg_json_missing_dependencies(tmp_path: Path) -> None:
    """parse_vcpkg_json handles missing dependencies gracefully."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps({"name": "pkg", "description": "No deps"}), encoding="utf-8"
    )

    manifest = parse_vcpkg_json(entry)
    assert manifest is not None
    assert manifest.dependencies == []


# ---------------------------------------------------------------------------
# parse_vcpkg_json — error cases
# ---------------------------------------------------------------------------


def test_parse_vcpkg_json_missing_file(tmp_path: Path) -> None:
    """parse_vcpkg_json returns None when vcpkg.json does not exist."""
    entry = tmp_path / "pkg"
    entry.mkdir()

    assert parse_vcpkg_json(entry) is None


def test_parse_vcpkg_json_invalid_json(tmp_path: Path) -> None:
    """parse_vcpkg_json returns None for malformed JSON."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text("not valid json {", encoding="utf-8")

    assert parse_vcpkg_json(entry) is None


def test_parse_vcpkg_json_not_an_object(tmp_path: Path) -> None:
    """parse_vcpkg_json returns None when vcpkg.json is not a JSON object."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(json.dumps(["array", "not", "object"]), encoding="utf-8")

    assert parse_vcpkg_json(entry) is None


def test_parse_vcpkg_json_read_error(tmp_path: Path) -> None:
    """parse_vcpkg_json returns None when the file cannot be read."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    manifest_path = entry / "vcpkg.json"
    manifest_path.write_text(json.dumps({"name": "pkg"}), encoding="utf-8")
    manifest_path.chmod(0o000)

    try:
        assert parse_vcpkg_json(entry) is None
    finally:
        manifest_path.chmod(0o644)


# ---------------------------------------------------------------------------
# parse_vcpkg_json — description variants
# ---------------------------------------------------------------------------


def test_parse_vcpkg_json_description_string(tmp_path: Path) -> None:
    """parse_vcpkg_json handles a plain string description."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps({"name": "pkg", "description": "A simple package"}),
        encoding="utf-8",
    )

    manifest = parse_vcpkg_json(entry)
    assert manifest is not None
    assert manifest.description == "A simple package"


def test_parse_vcpkg_json_description_list(tmp_path: Path) -> None:
    """parse_vcpkg_json joins list descriptions with spaces."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps(
            {"name": "pkg", "description": ["Line one.", "Line two.", "Line three."]}
        ),
        encoding="utf-8",
    )

    manifest = parse_vcpkg_json(entry)
    assert manifest is not None
    assert manifest.description == "Line one. Line two. Line three."


# ---------------------------------------------------------------------------
# VcpkgManifest dataclass
# ---------------------------------------------------------------------------


def test_vcpkg_manifest_defaults() -> None:
    """VcpkgManifest has an empty dependencies list by default."""
    manifest = VcpkgManifest(
        entry_name="pkg",
        package_name="pkg",
        description="A package",
        homepage=None,
        license=None,
        version=None,
    )
    assert manifest.dependencies == []


def test_vcpkg_manifest_with_dependencies() -> None:
    """VcpkgManifest stores a custom dependencies list."""
    manifest = VcpkgManifest(
        entry_name="pkg",
        package_name="pkg",
        description="A package",
        homepage=None,
        license=None,
        version=None,
        dependencies=["zlib", "boost"],
    )
    assert manifest.dependencies == ["zlib", "boost"]


# ---------------------------------------------------------------------------
# parse_vcpkg_json — readme fetching
# ---------------------------------------------------------------------------


def test_parse_vcpkg_json_fetches_readme_when_homepage_present(tmp_path: Path) -> None:
    """parse_vcpkg_json calls fetch_readme_for_homepage when homepage is present."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps(
            {
                "name": "pkg",
                "description": "A package",
                "homepage": "https://github.com/org/repo",
            }
        ),
        encoding="utf-8",
    )

    with patch(
        "dfetch_hub.catalog.sources.vcpkg.fetch_readme_for_homepage",
        return_value="# README content",
    ) as mock_fetch:
        manifest = parse_vcpkg_json(entry)
        assert manifest is not None
        mock_fetch.assert_called_once_with("https://github.com/org/repo")
        assert manifest.readme_content == "# README content"


def test_parse_vcpkg_json_no_readme_when_homepage_missing(tmp_path: Path) -> None:
    """parse_vcpkg_json does not fetch README when homepage is missing."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps({"name": "pkg", "description": "No homepage"}), encoding="utf-8"
    )

    with patch(
        "dfetch_hub.catalog.sources.vcpkg.fetch_readme_for_homepage"
    ) as mock_fetch:
        manifest = parse_vcpkg_json(entry)
        assert manifest is not None
        mock_fetch.assert_called_once_with(None)


# ---------------------------------------------------------------------------
# parse_vcpkg_json — edge cases
# ---------------------------------------------------------------------------


def test_parse_vcpkg_json_empty_description_field(tmp_path: Path) -> None:
    """parse_vcpkg_json handles an empty description."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps({"name": "pkg", "description": ""}), encoding="utf-8"
    )

    manifest = parse_vcpkg_json(entry)
    assert manifest is not None
    assert manifest.description == ""


def test_parse_vcpkg_json_non_string_homepage(tmp_path: Path) -> None:
    """parse_vcpkg_json handles non-string homepage gracefully."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps({"name": "pkg", "description": "desc", "homepage": 123}),
        encoding="utf-8",
    )

    manifest = parse_vcpkg_json(entry)
    assert manifest is not None
    assert manifest.homepage is None


def test_parse_vcpkg_json_non_string_license(tmp_path: Path) -> None:
    """parse_vcpkg_json handles non-string license gracefully."""
    entry = tmp_path / "pkg"
    entry.mkdir()
    (entry / "vcpkg.json").write_text(
        json.dumps({"name": "pkg", "description": "desc", "license": ["MIT", "Apache"]}),
        encoding="utf-8",
    )

    manifest = parse_vcpkg_json(entry)
    assert manifest is not None
    assert manifest.license is None