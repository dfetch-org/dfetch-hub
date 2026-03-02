"""Tests for dfetch_hub.catalog.sources.vcpkg: vcpkg.json parsing."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from dfetch_hub.catalog.sources.vcpkg import (
    VcpkgManifest,
    _extract_dependencies,
    _extract_description,
    _extract_version,
    parse_vcpkg_json,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_VCPKG_JSON: dict[str, object] = {
    "name": "abseil",
    "version-semver": "20240116.2",
    "description": "Abseil C++ libraries",
    "homepage": "https://github.com/abseil/abseil-cpp",
    "license": "Apache-2.0",
    "dependencies": ["boost-core", {"name": "boost-filesystem", "features": []}],
}


@pytest.fixture(autouse=True)
def _mock_readme() -> object:
    """Prevent real network calls in all vcpkg tests."""
    with patch(
        "dfetch_hub.catalog.sources.vcpkg.fetch_readme_for_homepage", return_value=None
    ):
        yield


# ---------------------------------------------------------------------------
# _extract_version
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["version-semver", "version", "version-date", "version-relaxed", "version-string"],
)
def test_extract_version_picks_each_key(key: str) -> None:
    """Every supported version key is recognised."""
    assert _extract_version({key: "1.0"}) == "1.0"


def test_extract_version_prefers_semver_over_plain_version() -> None:
    """version-semver wins when both version-semver and version are present."""
    assert _extract_version({"version-semver": "2.0", "version": "1.0"}) == "2.0"


def test_extract_version_returns_none_when_absent() -> None:
    """Returns None when no version field is present."""
    assert _extract_version({"name": "pkg"}) is None


# ---------------------------------------------------------------------------
# _extract_description
# ---------------------------------------------------------------------------


def test_extract_description_plain_string() -> None:
    """Plain string description is returned as-is."""
    assert _extract_description({"description": "A library"}) == "A library"


def test_extract_description_list_joined() -> None:
    """List description elements are joined with a space."""
    assert (
        _extract_description({"description": ["Summary.", "Detail."]})
        == "Summary. Detail."
    )


def test_extract_description_missing_returns_empty() -> None:
    """Missing description returns empty string."""
    assert _extract_description({}) == ""


# ---------------------------------------------------------------------------
# _extract_dependencies
# ---------------------------------------------------------------------------


def test_extract_dependencies_string_items() -> None:
    """Plain string dependencies are returned directly."""
    assert _extract_dependencies({"dependencies": ["a", "b"]}) == ["a", "b"]


def test_extract_dependencies_dict_items() -> None:
    """Dict dependency entries are reduced to their name."""
    assert _extract_dependencies({"dependencies": [{"name": "boost"}]}) == ["boost"]


def test_extract_dependencies_mixed() -> None:
    """Mixed string/dict entries are flattened; dicts without 'name' are skipped."""
    result = _extract_dependencies(
        {"dependencies": ["a", {"name": "b"}, {"other": "x"}]}
    )
    assert result == ["a", "b"]


def test_extract_dependencies_missing_returns_empty() -> None:
    """Missing dependencies key returns an empty list."""
    assert _extract_dependencies({}) == []


def test_extract_dependencies_non_list_returns_empty() -> None:
    """A non-list dependencies value returns an empty list."""
    assert _extract_dependencies({"dependencies": "not-a-list"}) == []


# ---------------------------------------------------------------------------
# parse_vcpkg_json
# ---------------------------------------------------------------------------


def test_parse_vcpkg_json_basic_fields(tmp_path: Path) -> None:
    """Basic fields are parsed from a minimal vcpkg.json."""
    pkg = tmp_path / "abseil"
    pkg.mkdir()
    (pkg / "vcpkg.json").write_text(json.dumps(_VCPKG_JSON), encoding="utf-8")

    result = parse_vcpkg_json(pkg)

    assert result is not None
    assert result.package_name == "abseil"
    assert result.version == "20240116.2"
    assert result.description == "Abseil C++ libraries"
    assert result.homepage == "https://github.com/abseil/abseil-cpp"
    assert result.license == "Apache-2.0"
    assert result.entry_name == "abseil"


def test_parse_vcpkg_json_dependencies(tmp_path: Path) -> None:
    """Dependencies are extracted from the dependencies array."""
    pkg = tmp_path / "abseil"
    pkg.mkdir()
    (pkg / "vcpkg.json").write_text(json.dumps(_VCPKG_JSON), encoding="utf-8")

    result = parse_vcpkg_json(pkg)

    assert result is not None
    assert "boost-core" in result.dependencies
    assert "boost-filesystem" in result.dependencies


def test_parse_vcpkg_json_returns_none_when_file_absent(tmp_path: Path) -> None:
    """Returns None when vcpkg.json does not exist in the directory."""
    assert parse_vcpkg_json(tmp_path) is None


def test_parse_vcpkg_json_returns_none_on_bad_json(tmp_path: Path) -> None:
    """Returns None when vcpkg.json contains invalid JSON."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "vcpkg.json").write_text("not json", encoding="utf-8")

    assert parse_vcpkg_json(pkg) is None


def test_parse_vcpkg_json_returns_none_for_non_object_json(tmp_path: Path) -> None:
    """Returns None when vcpkg.json is valid JSON but not an object."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "vcpkg.json").write_text("[1, 2, 3]", encoding="utf-8")

    assert parse_vcpkg_json(pkg) is None


def test_parse_vcpkg_json_uses_dir_name_when_no_name_field(tmp_path: Path) -> None:
    """Falls back to the directory name when vcpkg.json has no 'name' field."""
    pkg = tmp_path / "mylib"
    pkg.mkdir()
    (pkg / "vcpkg.json").write_text(
        json.dumps({"description": "A library"}), encoding="utf-8"
    )

    result = parse_vcpkg_json(pkg)

    assert result is not None
    assert result.package_name == "mylib"


def test_parse_vcpkg_json_readme_stored(tmp_path: Path) -> None:
    """readme_content is set from the upstream README when found."""
    pkg = tmp_path / "abseil"
    pkg.mkdir()
    (pkg / "vcpkg.json").write_text(json.dumps(_VCPKG_JSON), encoding="utf-8")

    with patch(
        "dfetch_hub.catalog.sources.vcpkg.fetch_readme_for_homepage",
        return_value="# README",
    ):
        result = parse_vcpkg_json(pkg)

    assert result is not None
    assert result.readme_content == "# README"


def test_parse_vcpkg_json_version_date_key(tmp_path: Path) -> None:
    """version-date is used when version-semver is absent."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "vcpkg.json").write_text(
        json.dumps({"name": "pkg", "version-date": "2024-01-16"}), encoding="utf-8"
    )

    result = parse_vcpkg_json(pkg)

    assert result is not None
    assert result.version == "2024-01-16"


def test_parse_vcpkg_json_no_version(tmp_path: Path) -> None:
    """version is None when no version field is present."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "vcpkg.json").write_text(json.dumps({"name": "pkg"}), encoding="utf-8")

    result = parse_vcpkg_json(pkg)

    assert result is not None
    assert result.version is None


def test_parse_vcpkg_json_description_list(tmp_path: Path) -> None:
    """List-valued description is joined into a single string."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "vcpkg.json").write_text(
        json.dumps({"name": "pkg", "description": ["Summary.", "Details."]}),
        encoding="utf-8",
    )

    result = parse_vcpkg_json(pkg)

    assert result is not None
    assert result.description == "Summary. Details."


def test_parse_vcpkg_json_is_vcpkg_manifest_instance(tmp_path: Path) -> None:
    """parse_vcpkg_json returns a VcpkgManifest, not just BaseManifest."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "vcpkg.json").write_text(json.dumps({"name": "pkg"}), encoding="utf-8")

    result = parse_vcpkg_json(pkg)

    assert isinstance(result, VcpkgManifest)


def test_parse_vcpkg_json_urls_contains_homepage(tmp_path: Path) -> None:
    """urls dict contains 'Homepage' when vcpkg.json has a homepage field."""
    pkg = tmp_path / "abseil"
    pkg.mkdir()
    (pkg / "vcpkg.json").write_text(json.dumps(_VCPKG_JSON), encoding="utf-8")

    result = parse_vcpkg_json(pkg)

    assert result is not None
    assert result.urls.get("Homepage") == "https://github.com/abseil/abseil-cpp"


def test_parse_vcpkg_json_urls_empty_without_homepage(tmp_path: Path) -> None:
    """urls dict is empty when vcpkg.json has no homepage field."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "vcpkg.json").write_text(json.dumps({"name": "pkg"}), encoding="utf-8")

    result = parse_vcpkg_json(pkg)

    assert result is not None
    assert result.urls == {}
