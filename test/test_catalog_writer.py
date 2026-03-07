"""Tests for dfetch_hub.catalog.writer: Catalog and CatalogWriter."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from dfetch_hub.catalog.sources import BaseManifest

from dfetch_hub.catalog.entry import CatalogEntry
from dfetch_hub.catalog.writer import Catalog, CatalogWriter


@pytest.fixture(autouse=True)
def mock_fetch_tags():
    """Mock fetch_upstream_tags to prevent network access in all tests."""
    with patch("dfetch_hub.catalog.detail.CatalogDetail.fetch_upstream_tags", return_value=[]):
        yield


def _manifest(
    entry_name: str = "abseil",
    package_name: str = "abseil-cpp",
    description: str = "Abseil C++ libraries from Google",
    homepage: str | None = "https://github.com/abseil/abseil-cpp",
    license_: str | None = "Apache-2.0",
    version: str | None = "20240116.2",
    subpath: str | None = None,
) -> "BaseManifest":
    from dfetch_hub.catalog.sources import BaseManifest

    return BaseManifest(
        entry_name=entry_name,
        package_name=package_name,
        description=description,
        homepage=homepage,
        license=license_,
        version=version,
        subpath=subpath,
    )


def _monorepo_manifest(name: str) -> "BaseManifest":
    """Build a manifest for a sub-component of a monorepo."""
    return _manifest(
        entry_name=name,
        package_name=name,
        homepage="https://github.com/myorg/mymonorepo",
        subpath=name,
    )


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_catalog_load_returns_empty_when_missing(tmp_path: Path) -> None:
    """load returns empty catalog when file doesn't exist."""
    catalog = Catalog.load(tmp_path / "catalog.json")
    assert catalog.entries == {}


def test_catalog_dump_and_load_roundtrip(tmp_path: Path) -> None:
    """dump + load preserves data."""
    original = Catalog()
    original.entries["test"] = CatalogEntry(cat_id="test", name="test")
    path = tmp_path / "catalog.json"
    original.dump(path)
    restored = Catalog.load(path)
    assert "test" in restored.entries


def test_catalog_get_or_create_creates_new() -> None:
    """get_or_create_entry creates new entry."""
    catalog = Catalog()
    _, is_new = catalog.get_or_create_entry(
        _manifest(),
        "github",
        "org",
        "repo",
        "label",
    )
    assert is_new
    assert "github/org/repo" in catalog.entries


def test_catalog_get_or_create_returns_existing() -> None:
    """get_or_create_entry returns existing entry."""
    catalog = Catalog()
    catalog.entries["github/org/repo"] = CatalogEntry(cat_id="github/org/repo", name="test")
    _, is_new = catalog.get_or_create_entry(
        _manifest(),
        "github",
        "org",
        "repo",
        "label",
    )
    assert not is_new


# ---------------------------------------------------------------------------
# CatalogWriter
# ---------------------------------------------------------------------------


def test_catalog_writer_write_creates_files(tmp_path: Path) -> None:
    """write creates catalog.json and detail JSON."""
    writer = CatalogWriter(tmp_path, "vcpkg", "vcpkg", "ports")
    writer.write([_manifest()])
    assert (tmp_path / "catalog.json").exists()
    assert (tmp_path / "github" / "abseil" / "abseil-cpp.json").exists()


def test_catalog_writer_write_returns_counts(tmp_path: Path) -> None:
    """write returns added/updated counts."""
    writer = CatalogWriter(tmp_path, "vcpkg", "vcpkg", "ports")
    added, updated = writer.write([_manifest()])
    assert added == 1
    assert updated == 0


def test_catalog_writer_write_skips_without_homepage(tmp_path: Path) -> None:
    """Manifests with no homepage are skipped."""
    writer = CatalogWriter(tmp_path, "vcpkg", "vcpkg", "ports")
    added, updated = writer.write([_manifest(homepage=None)])
    assert added == 0
    assert updated == 0
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert len(catalog) == 0


def test_catalog_writer_write_skips_unrecognized_url(tmp_path: Path) -> None:
    """Manifests with unparsable URLs are skipped."""
    writer = CatalogWriter(tmp_path, "vcpkg", "vcpkg", "ports")
    added, updated = writer.write([_manifest(homepage="https://example.com/not-a-repo")])
    assert added == 0
    assert updated == 0


def test_write_catalog_writes_catalog_json(tmp_path: Path) -> None:
    """A catalog.json file is created in data_dir."""
    writer = CatalogWriter(tmp_path, "vcpkg", "vcpkg", "ports")
    writer.write([_manifest()])
    assert (tmp_path / "catalog.json").exists()


def test_write_catalog_entry_in_catalog_json(tmp_path: Path) -> None:
    """GitHub entries appear under github/org/repo keys in catalog.json."""
    writer = CatalogWriter(tmp_path, "vcpkg", "vcpkg", "ports")
    writer.write([_manifest()])
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert "github/abseil/abseil-cpp" in catalog


def test_write_catalog_writes_detail_json(tmp_path: Path) -> None:
    """Detail JSON is written to data/github/org/repo.json for GitHub packages."""
    writer = CatalogWriter(tmp_path, "vcpkg", "vcpkg", "ports")
    writer.write([_manifest()])
    detail_path = tmp_path / "github" / "abseil" / "abseil-cpp.json"
    assert detail_path.exists()
    detail = json.loads(detail_path.read_text(encoding="utf-8"))
    assert detail["org"] == "abseil"
    assert detail["repo"] == "abseil-cpp"


def test_write_catalog_returns_added_count(tmp_path: Path) -> None:
    """Two distinct packages each increment the added counter."""
    boost = _manifest(
        entry_name="boost",
        package_name="boost",
        homepage="https://github.com/boostorg/boost",
        description="Boost C++ libraries",
    )
    writer = CatalogWriter(tmp_path, "vcpkg", "vcpkg", "ports")
    added, updated = writer.write([_manifest(), boost])
    assert added == 2
    assert updated == 0


def test_write_catalog_returns_updated_count(tmp_path: Path) -> None:
    """Processing the same package twice increments the updated counter."""
    writer = CatalogWriter(tmp_path, "vcpkg", "vcpkg", "ports")
    writer.write([_manifest()])
    added, updated = writer.write([_manifest()])
    assert added == 0
    assert updated == 1


def test_write_catalog_accepts_gitlab_homepage(tmp_path: Path) -> None:
    """GitLab-hosted packages are written under the gitlab/ directory."""
    gitlab_manifest = _manifest(
        entry_name="mylib",
        package_name="mylib",
        homepage="https://gitlab.com/myorg/mylib",
        description="A library on GitLab",
    )
    writer = CatalogWriter(tmp_path, "some-source", "some-source", "packages")
    added, updated = writer.write([gitlab_manifest])
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert "gitlab/myorg/mylib" in catalog
    assert added == 1
    assert updated == 0


def test_write_catalog_merges_across_two_sources(tmp_path: Path) -> None:
    """Same package from two separate sources should be merged into one entry."""
    writer = CatalogWriter(tmp_path, "vcpkg", "vcpkg", "ports")
    writer.write([_manifest()])
    writer = CatalogWriter(tmp_path, "conan", "conan", "recipes")
    writer.write([_manifest()])
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    entry = catalog["github/abseil/abseil-cpp"]
    assert "vcpkg" in entry["source_labels"]
    assert "conan" in entry["source_labels"]


def test_write_catalog_detail_json_has_both_sources(tmp_path: Path) -> None:
    """Detail JSON lists both sources after two write_catalog calls."""
    writer = CatalogWriter(tmp_path, "vcpkg", "vcpkg", "ports")
    writer.write([_manifest()])
    writer = CatalogWriter(tmp_path, "conan", "conan", "recipes")
    writer.write([_manifest()])
    detail = json.loads((tmp_path / "github" / "abseil" / "abseil-cpp.json").read_text(encoding="utf-8"))
    source_names = [s["source_name"] for s in detail["catalog_sources"]]
    assert "vcpkg" in source_names
    assert "conan" in source_names


def test_write_catalog_monorepo_components_get_distinct_ids(tmp_path: Path) -> None:
    """Two components from the same repo with different subpaths get distinct catalog IDs."""
    foo = _monorepo_manifest("foo")
    bar = _monorepo_manifest("bar")
    writer = CatalogWriter(tmp_path, "readme", "readme", "packages")
    added, updated = writer.write([foo, bar])
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert "github/myorg/mymonorepo/foo" in catalog
    assert "github/myorg/mymonorepo/bar" in catalog
    assert added == 2
    assert updated == 0


def test_write_catalog_monorepo_components_get_distinct_detail_paths(tmp_path: Path) -> None:
    """Each monorepo component is written to its own detail JSON file."""
    foo = _monorepo_manifest("foo")
    bar = _monorepo_manifest("bar")
    writer = CatalogWriter(tmp_path, "readme", "readme", "packages")
    writer.write([foo, bar])
    foo_path = tmp_path / "github" / "myorg" / "mymonorepo" / "foo.json"
    bar_path = tmp_path / "github" / "myorg" / "mymonorepo" / "bar.json"
    assert foo_path.exists()
    assert bar_path.exists()


def test_write_catalog_monorepo_detail_contains_subfolder_path(tmp_path: Path) -> None:
    """The detail JSON for a monorepo component stores its subfolder_path."""
    foo = _monorepo_manifest("foo")
    writer = CatalogWriter(tmp_path, "readme", "readme", "packages")
    writer.write([foo])
    detail = json.loads((tmp_path / "github" / "myorg" / "mymonorepo" / "foo.json").read_text(encoding="utf-8"))
    assert detail["subfolder_path"] == "foo"


def test_write_catalog_non_monorepo_detail_path_unchanged(tmp_path: Path) -> None:
    """Packages without a subpath continue to use the flat <repo>.json path."""
    writer = CatalogWriter(tmp_path, "vcpkg", "vcpkg", "ports")
    writer.write([_manifest()])
    assert (tmp_path / "github" / "abseil" / "abseil-cpp.json").exists()


def test_write_catalog_monorepo_catalog_id_in_entry(tmp_path: Path) -> None:
    """The id field inside the catalog entry includes the subpath."""
    foo = _monorepo_manifest("foo")
    writer = CatalogWriter(tmp_path, "readme", "readme", "packages")
    writer.write([foo])
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["github/myorg/mymonorepo/foo"]["id"] == "github/myorg/mymonorepo/foo"


def test_write_catalog_nested_subpath(tmp_path: Path) -> None:
    """Nested subpath like 'libs/foo' is preserved in catalog ID and detail file."""
    m = _manifest(
        entry_name="libs/foo",
        package_name="foo",
        homepage="https://github.com/myorg/mymonorepo",
        subpath="libs/foo",
    )
    writer = CatalogWriter(tmp_path, "readme", "readme", "packages")
    writer.write([m])

    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert "github/myorg/mymonorepo/libs/foo" in catalog
    assert catalog["github/myorg/mymonorepo/libs/foo"]["id"] == "github/myorg/mymonorepo/libs/foo"

    detail_path = tmp_path / "github" / "myorg" / "mymonorepo" / "libs" / "foo.json"
    assert detail_path.exists()
    detail = json.loads(detail_path.read_text(encoding="utf-8"))
    assert detail["subfolder_path"] == "libs/foo"
