"""Tests for dfetch_hub.catalog.entry: CatalogEntry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from dfetch_hub.catalog.entry import CatalogEntry
from dfetch_hub.catalog.model import Tag


def _manifest(
    entry_name: str = "abseil",
    package_name: str = "abseil-cpp",
    description: str = "Abseil C++ libraries from Google",
    homepage: str | None = "https://github.com/abseil/abseil-cpp",
    license_: str | None = "Apache-2.0",
    version: str | None = "20240116.2",
    subpath: str | None = None,
):
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


def test_catalog_entry_from_manifest() -> None:
    """from_manifest creates a proper entry."""
    entry = CatalogEntry.from_manifest(
        _manifest(),
        "github",
        "abseil",
        "abseil-cpp",
        "vcpkg",
    )
    assert entry.id == "github/abseil/abseil-cpp"
    assert entry.name == "abseil-cpp"
    assert entry.description == "Abseil C++ libraries from Google"
    assert entry.license == "Apache-2.0"
    assert entry.source_type == "github"
    assert "vcpkg" in entry.source_labels
    assert any(t.name == "20240116.2" for t in entry.tags)


def test_catalog_entry_from_dict_roundtrip() -> None:
    """from_dict + to_dict preserves data."""
    original = CatalogEntry.from_manifest(
        _manifest(version="1.0.0"),
        "github",
        "org",
        "repo",
        "label",
    )
    restored = CatalogEntry.from_dict(original.to_dict())
    assert restored.id == original.id
    assert restored.name == original.name


def test_catalog_entry_merge_backfills_missing() -> None:
    """merge_from_manifest backfills missing description and license."""
    entry = CatalogEntry(cat_id="test", name="test", description=None, license_str=None)
    entry.merge_from_manifest(_manifest(), is_update=True, label="new")
    assert entry.description == "Abseil C++ libraries from Google"
    assert entry.license == "Apache-2.0"


def test_catalog_entry_merge_preserves_existing() -> None:
    """merge_from_manifest does not overwrite existing description/license."""
    entry = CatalogEntry(cat_id="test", name="test", description="old", license_str="MIT")
    entry.merge_from_manifest(_manifest(), is_update=True, label="new")
    assert entry.description == "old"
    assert entry.license == "MIT"


def test_catalog_entry_merge_adds_labels() -> None:
    """merge_from_manifest adds new labels without duplicating."""
    entry = CatalogEntry(cat_id="test", name="test", source_labels=["conan"])
    entry.merge_from_manifest(_manifest(), is_update=True, label="vcpkg")
    assert "conan" in entry.source_labels
    assert "vcpkg" in entry.source_labels
    assert entry.source_labels.count("vcpkg") == 1


def test_catalog_entry_update_tags_no_duplicate() -> None:
    """update_tags doesn't add duplicate tags (with or without 'v' prefix)."""
    entry = CatalogEntry(cat_id="test", name="test", tags=[Tag(name="v1.0.0", is_tag=True)])
    entry.update_tags("1.0.0")
    assert sum(1 for t in entry.tags if t.name.lstrip("v") == "1.0.0") == 1


def test_catalog_entry_update_tags_no_duplicate_version() -> None:
    """update_tags doesn't add same version twice."""
    entry = CatalogEntry(cat_id="test", name="test", tags=[Tag(name="20240116.2", is_tag=True)])
    entry.update_tags("20240116.2")
    assert sum(1 for t in entry.tags if t.name == "20240116.2") == 1


def test_catalog_id_format() -> None:
    """Catalog ID format is vcs_host/org/repo."""
    assert CatalogEntry.catalog_id("github", "abseil", "abseil-cpp") == "github/abseil/abseil-cpp"


def test_catalog_id_lowercases_inputs() -> None:
    """All components are lowercased."""
    assert CatalogEntry.catalog_id("GITHUB", "Abseil", "Abseil-CPP") == "github/abseil/abseil-cpp"


def test_catalog_id_with_subpath() -> None:
    """Monorepo component includes the subpath segment."""
    assert CatalogEntry.catalog_id("github", "org", "repo", "mylib") == "github/org/repo/mylib"


def test_vcs_host_label_github() -> None:
    """Maps github.com to github."""
    assert CatalogEntry.vcs_host_label("github.com") == "github"


def test_vcs_host_label_gitlab() -> None:
    """Maps gitlab.com to gitlab."""
    assert CatalogEntry.vcs_host_label("gitlab.com") == "gitlab"


def test_vcs_host_label_unknown() -> None:
    """Unknown hosts are returned as-is."""
    assert CatalogEntry.vcs_host_label("gitea.example.com") == "gitea.example.com"
