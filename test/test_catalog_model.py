"""Tests for dfetch_hub.catalog.model: Tag, CatalogSource, and VCSLocation."""

from __future__ import annotations

from dfetch_hub.catalog.model import CatalogSource, Tag, VCSLocation


def test_vcs_location_catalog_id() -> None:
    """VCSLocation produces correct catalog ID."""
    loc = VCSLocation("github", "abseil", "abseil-cpp")
    assert loc.catalog_id == "github/abseil/abseil-cpp"


def test_vcs_location_catalog_id_with_subpath() -> None:
    """VCSLocation includes subpath in catalog ID."""
    loc = VCSLocation("github", "org", "repo", "mylib")
    assert loc.catalog_id == "github/org/repo/mylib"


def test_vcs_location_catalog_id_lowercases() -> None:
    """VCSLocation lowercases all components."""
    loc = VCSLocation("GITHUB", "Abseil", "Abseil-CPP")
    assert loc.catalog_id == "github/abseil/abseil-cpp"


def test_vcs_location_catalog_id_subpath_lowercases() -> None:
    """VCSLocation lowercases subpath."""
    loc = VCSLocation("github", "org", "repo", "MyLib")
    assert loc.catalog_id == "github/org/repo/mylib"


def test_tag_to_dict_roundtrip() -> None:
    """to_dict + from_dict preserves data."""
    original = Tag(name="v1.0.0", is_tag=True, commit_sha="abc123", date="2024-01-01")
    restored = Tag.from_dict(original.to_dict())
    assert restored.name == original.name
    assert restored.is_tag == original.is_tag


def test_tag_from_dict_with_defaults() -> None:
    """from_dict handles missing keys with defaults."""
    tag = Tag.from_dict({})
    assert tag.name == ""
    assert tag.is_tag is True


def test_catalog_source_to_dict_roundtrip() -> None:
    """to_dict + from_dict preserves data."""
    original = CatalogSource(
        source_name="vcpkg",
        label="vcpkg",
        index_path="ports/abseil",
        registry_version="1.0.0",
    )
    restored = CatalogSource.from_dict(original.to_dict())
    assert restored.source_name == original.source_name
    assert restored.label == original.label
    assert restored.index_path == original.index_path
    assert restored.registry_version == original.registry_version


def test_catalog_source_from_dict_with_defaults() -> None:
    """from_dict handles missing keys with defaults."""
    source = CatalogSource.from_dict({})
    assert source.source_name == ""
    assert source.label == ""
    assert source.index_path == ""
    assert source.registry_version is None
