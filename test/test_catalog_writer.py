"""Tests for dfetch_hub.catalog.writer: catalog JSON writing pipeline.

Covers:
- _parse_github_slug: URL parsing and lowercase normalisation.
- _catalog_id: ID string format.
- _merge_catalog_entry: create / update catalog.json entries.
- _generate_readme: fallback README content.
- _merge_detail: create / update per-project detail JSONs.
- write_catalog: full pipeline against a tmp_path data directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from dfetch_hub.catalog.sources import BaseManifest, _parse_github_slug
from dfetch_hub.catalog.sources.clib import CLibPackage
from dfetch_hub.catalog.writer import (
    _catalog_id,
    _generate_readme,
    _merge_catalog_entry,
    _merge_detail,
    write_catalog,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manifest(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    port_name: str = "abseil",
    package_name: str = "abseil-cpp",
    description: str = "Abseil C++ libraries from Google",
    homepage: str | None = "https://github.com/abseil/abseil-cpp",
    license_: str | None = "Apache-2.0",
    version: str | None = "20240116.2",
) -> BaseManifest:
    """Build a minimal BaseManifest with sensible defaults for testing."""
    return BaseManifest(
        port_name=port_name,
        package_name=package_name,
        description=description,
        homepage=homepage,
        license=license_,
        version=version,
    )


def _existing_catalog_entry(label: str = "vcpkg") -> dict[str, Any]:
    """Return a minimal pre-existing catalog.json entry for abseil-cpp."""
    return {
        "id": "github/abseil/abseil-cpp",
        "name": "abseil-cpp",
        "description": "old description",
        "url": "https://github.com/abseil/abseil-cpp",
        "source_type": "github",
        "default_branch": "main",
        "license": None,
        "topics": [],
        "stars": 0,
        "last_updated": "2024-01-01T00:00:00+00:00",
        "source_labels": [label],
        "tags": [],
    }


def _existing_detail() -> dict[str, Any]:
    """Return a minimal pre-existing per-project detail JSON for abseil-cpp."""
    return {
        "canonical_url": "https://github.com/abseil/abseil-cpp",
        "org": "abseil",
        "repo": "abseil-cpp",
        "subfolder_path": None,
        "catalog_sources": [
            {
                "source_name": "vcpkg",
                "label": "vcpkg",
                "index_path": "ports/abseil",
                "registry_version": "1.0",
            }
        ],
        "manifests": [],
        "readme": "placeholder readme",
        "tags": [],
        "branches": [
            {"name": "main", "is_tag": False, "commit_sha": None, "date": None}
        ],
        "license_text": None,
        "fetched_at": "2024-01-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# _parse_github_slug
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/abseil/abseil-cpp", ("abseil", "abseil-cpp")),
        ("https://github.com/abseil/abseil-cpp.git", ("abseil", "abseil-cpp")),
        ("https://github.com/abseil/abseil-cpp/", ("abseil", "abseil-cpp")),
        ("http://github.com/foo/bar", ("foo", "bar")),
    ],
)
def test_parse_github_slug_valid(url: str, expected: tuple[str, str]) -> None:
    assert _parse_github_slug(url) == expected


def test_parse_github_slug_lowercases_org_and_repo() -> None:
    assert _parse_github_slug("https://github.com/ABSEIL/Abseil-CPP") == (
        "abseil",
        "abseil-cpp",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/org/repo",
        "https://bitbucket.org/org/repo",
        "not-a-url",
        "",
        "https://github.com/only-org",
    ],
)
def test_parse_github_slug_non_github_returns_none(url: str) -> None:
    assert _parse_github_slug(url) is None


# ---------------------------------------------------------------------------
# _catalog_id
# ---------------------------------------------------------------------------


def test_catalog_id_format() -> None:
    assert _catalog_id("abseil", "abseil-cpp") == "github/abseil/abseil-cpp"


def test_catalog_id_lowercases_inputs() -> None:
    assert _catalog_id("Abseil", "Abseil-CPP") == "github/abseil/abseil-cpp"


# ---------------------------------------------------------------------------
# _merge_catalog_entry
# ---------------------------------------------------------------------------


def test_merge_catalog_entry_new_has_correct_id() -> None:
    entry = _merge_catalog_entry(None, _manifest(), "abseil", "abseil-cpp", "vcpkg")
    assert entry["id"] == "github/abseil/abseil-cpp"


def test_merge_catalog_entry_new_populates_name() -> None:
    entry = _merge_catalog_entry(None, _manifest(), "abseil", "abseil-cpp", "vcpkg")
    assert entry["name"] == "abseil-cpp"


def test_merge_catalog_entry_new_populates_description() -> None:
    entry = _merge_catalog_entry(None, _manifest(), "abseil", "abseil-cpp", "vcpkg")
    assert entry["description"] == "Abseil C++ libraries from Google"


def test_merge_catalog_entry_new_populates_license() -> None:
    entry = _merge_catalog_entry(None, _manifest(), "abseil", "abseil-cpp", "vcpkg")
    assert entry["license"] == "Apache-2.0"


def test_merge_catalog_entry_adds_source_label() -> None:
    entry = _merge_catalog_entry(None, _manifest(), "abseil", "abseil-cpp", "vcpkg")
    assert "vcpkg" in entry["source_labels"]


def test_merge_catalog_entry_adds_version_tag() -> None:
    entry = _merge_catalog_entry(
        None, _manifest(version="20240116.2"), "abseil", "abseil-cpp", "vcpkg"
    )
    tag_names = {t["name"] for t in entry["tags"]}
    assert "20240116.2" in tag_names


def test_merge_catalog_entry_no_duplicate_version_tag() -> None:
    existing = _existing_catalog_entry()
    existing["tags"] = [
        {"name": "20240116.2", "is_tag": True, "commit_sha": None, "date": None}
    ]
    entry = _merge_catalog_entry(
        existing, _manifest(version="20240116.2"), "abseil", "abseil-cpp", "vcpkg"
    )
    assert sum(1 for t in entry["tags"] if t["name"] == "20240116.2") == 1


def test_merge_catalog_entry_merges_source_labels() -> None:
    existing = _existing_catalog_entry(label="conan")
    entry = _merge_catalog_entry(existing, _manifest(), "abseil", "abseil-cpp", "vcpkg")
    assert "conan" in entry["source_labels"]
    assert "vcpkg" in entry["source_labels"]


def test_merge_catalog_entry_no_duplicate_label() -> None:
    existing = _existing_catalog_entry(label="vcpkg")
    entry = _merge_catalog_entry(existing, _manifest(), "abseil", "abseil-cpp", "vcpkg")
    assert entry["source_labels"].count("vcpkg") == 1


def test_merge_catalog_entry_url_falls_back_to_github_url() -> None:
    entry = _merge_catalog_entry(
        None, _manifest(homepage=None), "abseil", "abseil-cpp", "vcpkg"
    )
    assert entry["url"] == "https://github.com/abseil/abseil-cpp"


def test_merge_catalog_entry_no_version_no_tag_added() -> None:
    entry = _merge_catalog_entry(
        None, _manifest(version=None), "abseil", "abseil-cpp", "vcpkg"
    )
    assert not entry["tags"]


def test_merge_catalog_entry_backfills_missing_description() -> None:
    """Existing entry with no description is backfilled from the manifest."""
    existing = _existing_catalog_entry()
    existing["description"] = None
    entry = _merge_catalog_entry(existing, _manifest(), "abseil", "abseil-cpp", "vcpkg")
    assert entry["description"] == "Abseil C++ libraries from Google"


def test_merge_catalog_entry_does_not_overwrite_existing_description() -> None:
    """An already-populated description must not be replaced by the manifest."""
    existing = _existing_catalog_entry()  # description = "old description"
    entry = _merge_catalog_entry(existing, _manifest(), "abseil", "abseil-cpp", "vcpkg")
    assert entry["description"] == "old description"


def test_merge_catalog_entry_backfills_missing_license() -> None:
    """Existing entry with no license is backfilled from the manifest."""
    existing = _existing_catalog_entry()  # license = None by default
    entry = _merge_catalog_entry(existing, _manifest(), "abseil", "abseil-cpp", "vcpkg")
    assert entry["license"] == "Apache-2.0"


def test_merge_catalog_entry_does_not_overwrite_existing_license() -> None:
    """An already-populated license must not be replaced by the manifest."""
    existing = _existing_catalog_entry()
    existing["license"] = "MIT"
    entry = _merge_catalog_entry(existing, _manifest(), "abseil", "abseil-cpp", "vcpkg")
    assert entry["license"] == "MIT"


def test_merge_catalog_entry_v_prefix_tag_not_duplicated() -> None:
    """Version '1.2.3' is not added if 'v1.2.3' already exists in the tag list."""
    existing = _existing_catalog_entry()
    existing["tags"] = [
        {"name": "v1.2.3", "is_tag": True, "commit_sha": None, "date": None}
    ]
    entry = _merge_catalog_entry(
        existing, _manifest(version="1.2.3"), "abseil", "abseil-cpp", "vcpkg"
    )
    assert sum(1 for t in entry["tags"] if t["name"].lstrip("v") == "1.2.3") == 1


# ---------------------------------------------------------------------------
# _generate_readme
# ---------------------------------------------------------------------------


def test_generate_readme_contains_package_name() -> None:
    assert "abseil-cpp" in _generate_readme(_manifest(), "abseil", "abseil-cpp")


def test_generate_readme_contains_description() -> None:
    assert "Abseil C++ libraries" in _generate_readme(
        _manifest(), "abseil", "abseil-cpp"
    )


def test_generate_readme_contains_version_tag() -> None:
    assert "20240116.2" in _generate_readme(
        _manifest(version="20240116.2"), "abseil", "abseil-cpp"
    )


def test_generate_readme_omits_tag_when_no_version() -> None:
    readme = _generate_readme(_manifest(version=None), "abseil", "abseil-cpp")
    assert "tag:" not in readme


def test_generate_readme_contains_dfetch_yaml_snippet() -> None:
    readme = _generate_readme(_manifest(), "abseil", "abseil-cpp")
    assert "dfetch.yaml" in readme


# ---------------------------------------------------------------------------
# _merge_detail
# ---------------------------------------------------------------------------


def test_merge_detail_new_sets_org_and_repo() -> None:
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        detail = _merge_detail(
            None, _manifest(), "abseil", "abseil-cpp", "vcpkg", "vcpkg", "ports"
        )
    assert detail["org"] == "abseil"
    assert detail["repo"] == "abseil-cpp"


def test_merge_detail_new_adds_catalog_source() -> None:
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        detail = _merge_detail(
            None, _manifest(), "abseil", "abseil-cpp", "vcpkg", "vcpkg", "ports"
        )
    sources = detail["catalog_sources"]
    assert len(sources) == 1
    assert sources[0]["source_name"] == "vcpkg"
    assert sources[0]["label"] == "vcpkg"


def test_merge_detail_readme_content_overwrites_generated() -> None:
    """readme_content on the manifest (e.g. CLibPackage) replaces the generated placeholder."""
    m = CLibPackage(
        port_name="clibs/buffer",
        package_name="buffer",
        description="Tiny C buffer library",
        homepage="https://github.com/clibs/buffer",
        license="MIT",
        version="0.4.0",
        readme_content="# Real README from upstream",
    )
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        detail = _merge_detail(None, m, "clibs", "buffer", "clib", "clib", "clib")
    assert detail["readme"] == "# Real README from upstream"


def test_merge_detail_readme_content_overwrites_existing_readme() -> None:
    """readme_content always overwrites, even when updating an existing detail."""
    m = CLibPackage(
        port_name="clibs/buffer",
        package_name="buffer",
        description="desc",
        homepage="https://github.com/clibs/buffer",
        license="MIT",
        version="0.4.0",
        readme_content="# Fresh README",
    )
    existing = _existing_detail()
    existing["org"] = "clibs"
    existing["repo"] = "buffer"
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        detail = _merge_detail(existing, m, "clibs", "buffer", "clib", "clib", "clib")
    assert detail["readme"] == "# Fresh README"


def test_merge_detail_updates_existing_catalog_source() -> None:
    """Updating an existing source entry replaces registry_version in-place."""
    existing = _existing_detail()
    m = _manifest(version="2.0")
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        detail = _merge_detail(
            existing, m, "abseil", "abseil-cpp", "vcpkg", "vcpkg", "ports"
        )
    assert detail["catalog_sources"][0]["registry_version"] == "2.0"
    assert len(detail["catalog_sources"]) == 1


def test_merge_detail_appends_new_catalog_source() -> None:
    """A second source is appended, not overwriting the first."""
    existing = _existing_detail()
    m = _manifest()
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        detail = _merge_detail(
            existing, m, "abseil", "abseil-cpp", "conan", "conan", "recipes"
        )
    source_names = [s["source_name"] for s in detail["catalog_sources"]]
    assert "vcpkg" in source_names
    assert "conan" in source_names


def test_merge_detail_version_tag_added_when_absent() -> None:
    """The manifest version is added to the tags list if not already present."""
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        detail = _merge_detail(
            None,
            _manifest(version="1.2.3"),
            "abseil",
            "abseil-cpp",
            "vcpkg",
            "vcpkg",
            "ports",
        )
    tag_names = {t["name"] for t in detail["tags"]}
    assert "1.2.3" in tag_names


def test_merge_detail_version_tag_not_duplicated() -> None:
    """The manifest version is not added again if already present (modulo leading v)."""
    existing = _existing_detail()
    existing["tags"] = [
        {"name": "v1.2.3", "is_tag": True, "commit_sha": None, "date": None}
    ]
    m = _manifest(version="1.2.3")
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        detail = _merge_detail(
            existing, m, "abseil", "abseil-cpp", "vcpkg", "vcpkg", "ports"
        )
    assert sum(1 for t in detail["tags"] if t["name"].lstrip("v") == "1.2.3") == 1


def test_merge_detail_stale_source_name_replaced_not_duplicated() -> None:
    """A source entry with the same index_path but an old source_name is replaced.

    This covers the case where a source is renamed in dfetch-hub.toml (e.g.
    "vcpkg-source" → "vcpkg"): the old entry must be purged so only one entry
    survives, avoiding duplicate catalog_sources entries.
    """
    existing = _existing_detail()
    # Simulate the stale entry left by a previous manual rename
    # Simulate a stale entry: same index_path ("ports/abseil") but old source_name
    existing["catalog_sources"][0]["source_name"] = "vcpkg-source"

    m = _manifest(version="1.0")
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        detail = _merge_detail(
            existing, m, "abseil", "abseil-cpp", "vcpkg", "vcpkg", "ports"
        )

    source_names = [s["source_name"] for s in detail["catalog_sources"]]
    assert source_names == ["vcpkg"], f"expected only 'vcpkg', got {source_names}"


# ---------------------------------------------------------------------------
# write_catalog
# ---------------------------------------------------------------------------


def test_write_catalog_writes_catalog_json(tmp_path: Path) -> None:
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            ports_path="ports",
        )
    assert (tmp_path / "catalog.json").exists()


def test_write_catalog_entry_in_catalog_json(tmp_path: Path) -> None:
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            ports_path="ports",
        )
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert "github/abseil/abseil-cpp" in catalog


def test_write_catalog_writes_detail_json(tmp_path: Path) -> None:
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            ports_path="ports",
        )
    detail_path = tmp_path / "github" / "abseil" / "abseil-cpp.json"
    assert detail_path.exists()
    detail = json.loads(detail_path.read_text(encoding="utf-8"))
    assert detail["org"] == "abseil"
    assert detail["repo"] == "abseil-cpp"


def test_write_catalog_returns_added_count(tmp_path: Path) -> None:
    boost = _manifest(
        port_name="boost",
        package_name="boost",
        homepage="https://github.com/boostorg/boost",
        description="Boost C++ libraries",
    )
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        added, updated = write_catalog(
            [_manifest(), boost],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            ports_path="ports",
        )
    assert added == 2
    assert updated == 0


def test_write_catalog_returns_updated_count(tmp_path: Path) -> None:
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            ports_path="ports",
        )
        added, updated = write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            ports_path="ports",
        )
    assert added == 0
    assert updated == 1


def test_write_catalog_skips_manifest_without_homepage(tmp_path: Path) -> None:
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        added, updated = write_catalog(
            [_manifest(homepage=None)],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            ports_path="ports",
        )
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert len(catalog) == 0
    assert added == 0
    assert updated == 0


def test_write_catalog_skips_non_github_homepage(tmp_path: Path) -> None:
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        added, updated = write_catalog(
            [_manifest(homepage="https://gitlab.com/org/repo")],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            ports_path="ports",
        )
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert len(catalog) == 0
    assert added == 0
    assert updated == 0


def test_write_catalog_merges_across_two_sources(tmp_path: Path) -> None:
    """Same package from two separate sources should be merged into one entry."""
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            ports_path="ports",
        )
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="conan",
            label="conan",
            ports_path="recipes",
        )
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    entry = catalog["github/abseil/abseil-cpp"]
    assert "vcpkg" in entry["source_labels"]
    assert "conan" in entry["source_labels"]


def test_write_catalog_detail_json_has_both_sources(tmp_path: Path) -> None:
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            ports_path="ports",
        )
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="conan",
            label="conan",
            ports_path="recipes",
        )
    detail = json.loads(
        (tmp_path / "github" / "abseil" / "abseil-cpp.json").read_text(encoding="utf-8")
    )
    source_names = [s["source_name"] for s in detail["catalog_sources"]]
    assert "vcpkg" in source_names
    assert "conan" in source_names
