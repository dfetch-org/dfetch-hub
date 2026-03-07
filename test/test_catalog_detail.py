"""Tests for dfetch_hub.catalog.detail: CatalogDetail."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from dfetch_hub.catalog.detail import CatalogDetail
from dfetch_hub.catalog.model import CatalogSource

if TYPE_CHECKING:
    pass


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


def test_catalog_detail_from_manifest() -> None:
    """from_manifest creates a proper detail."""
    detail = CatalogDetail.from_manifest(
        _manifest(),
        "abseil",
        "abseil-cpp",
        "vcpkg",
        "vcpkg",
        "ports",
    )
    assert detail.org == "abseil"
    assert detail.repo == "abseil-cpp"
    assert len(detail.catalog_sources) == 1
    assert detail.catalog_sources[0].source_name == "vcpkg"


def test_catalog_detail_from_dict_roundtrip() -> None:
    """from_dict + to_dict preserves data."""
    original = CatalogDetail.from_manifest(
        _manifest(),
        "org",
        "repo",
        "source",
        "label",
        "path",
    )
    restored = CatalogDetail.from_dict(original.to_dict())
    assert restored.org == original.org
    assert restored.repo == original.repo


def test_catalog_detail_add_source_updates_existing() -> None:
    """add_source updates existing source."""
    from dfetch_hub.catalog.model import VCSLocation

    detail = CatalogDetail(
        location=VCSLocation(host="", org="org", repo="repo"),
        catalog_sources=[CatalogSource(source_name="src1", label="label1", index_path="path1")],
    )
    detail.add_source(_manifest(version="2.0"), "src1", "label1", "newpath")
    assert len(detail.catalog_sources) == 1
    assert detail.catalog_sources[0].registry_version == "2.0"


def test_catalog_detail_add_source_appends_new() -> None:
    """add_source appends new source."""
    from dfetch_hub.catalog.model import VCSLocation

    detail = CatalogDetail(
        location=VCSLocation(host="", org="org", repo="repo"),
        catalog_sources=[CatalogSource(source_name="src1", label="label1", index_path="path1")],
    )
    detail.add_source(_manifest(), "src2", "label2", "path2")
    assert len(detail.catalog_sources) == 2


def test_catalog_detail_readme_content_from_manifest() -> None:
    """readme_content on manifest replaces generated readme."""
    from dfetch_hub.catalog.sources.clib import CLibPackage

    m = CLibPackage(
        entry_name="clibs/buffer",
        package_name="buffer",
        description="Tiny C buffer library",
        homepage="https://github.com/clibs/buffer",
        license="MIT",
        version="0.4.0",
        readme_content="# Real README from upstream",
    )
    detail = CatalogDetail.from_manifest(m, "clibs", "buffer", "clib", "clib", "clib")
    assert detail.readme == "# Real README from upstream"


def test_catalog_detail_urls_from_manifest() -> None:
    """urls from manifest are written to detail."""
    from dfetch_hub.catalog.sources import BaseManifest

    m = BaseManifest(
        entry_name="abseil",
        package_name="abseil-cpp",
        description="desc",
        homepage="https://github.com/abseil/abseil-cpp",
        license=None,
        version=None,
        urls={"Homepage": "https://github.com/abseil/abseil-cpp", "Source": "https://github.com/x/y"},
    )
    detail = CatalogDetail.from_manifest(m, "abseil", "abseil-cpp", "vcpkg", "vcpkg", "ports")
    detail.update_from_manifest(m, "abseil-cpp", "vcpkg", "vcpkg", "ports")
    assert detail.urls["Homepage"] == "https://github.com/abseil/abseil-cpp"
    assert detail.urls["Source"] == "https://github.com/x/y"


_FULL_SHA = "a" * 40


def test_fetch_upstream_tags_returns_tag_entries() -> None:
    """Tags are extracted from refs/tags/* entries returned by ls-remote."""
    ls_remote = {
        "refs/tags/v1.0.0": _FULL_SHA,
        "refs/tags/v2.0.0": "b" * 40,
        "refs/heads/main": "c" * 40,
    }
    with patch("dfetch_hub.catalog.detail.GitRemote._ls_remote", return_value=ls_remote):
        tags = CatalogDetail.fetch_upstream_tags("https://github.com/owner/repo")

    tag_names = {t.name for t in tags}
    assert tag_names == {"v1.0.0", "v2.0.0"}


def test_fetch_upstream_tags_excludes_branch_refs() -> None:
    """Entries under refs/heads/ are not returned as tags."""
    ls_remote = {
        "refs/heads/main": _FULL_SHA,
        "refs/heads/dev": "b" * 40,
    }
    with patch("dfetch_hub.catalog.detail.GitRemote._ls_remote", return_value=ls_remote):
        tags = CatalogDetail.fetch_upstream_tags("https://github.com/owner/repo")

    assert tags == []


def test_fetch_upstream_tags_commit_sha_is_full_length() -> None:
    """commit_sha is the full 40-character SHA."""
    ls_remote = {"refs/tags/v1.0.0": _FULL_SHA}
    with patch("dfetch_hub.catalog.detail.GitRemote._ls_remote", return_value=ls_remote):
        tags = CatalogDetail.fetch_upstream_tags("https://github.com/owner/repo")

    assert len(tags) == 1
    assert tags[0].commit_sha == _FULL_SHA


def test_fetch_upstream_tags_is_tag_true() -> None:
    """Every entry has is_tag set to True."""
    ls_remote = {"refs/tags/v1.0.0": _FULL_SHA}
    with patch("dfetch_hub.catalog.detail.GitRemote._ls_remote", return_value=ls_remote):
        tags = CatalogDetail.fetch_upstream_tags("https://github.com/owner/repo")

    assert tags[0].is_tag is True


def test_fetch_upstream_tags_name_strips_refs_prefix() -> None:
    """The 'refs/tags/' prefix is stripped from the tag name."""
    ls_remote = {"refs/tags/release-2024": _FULL_SHA}
    with patch("dfetch_hub.catalog.detail.GitRemote._ls_remote", return_value=ls_remote):
        tags = CatalogDetail.fetch_upstream_tags("https://github.com/owner/repo")

    assert tags[0].name == "release-2024"


def test_fetch_upstream_tags_returns_empty_on_error() -> None:
    """Returns an empty list when ls-remote raises an exception."""
    with patch(
        "dfetch_hub.catalog.detail.GitRemote._ls_remote",
        side_effect=RuntimeError("network error"),
    ):
        tags = CatalogDetail.fetch_upstream_tags("https://github.com/owner/repo")

    assert tags == []


def test_generate_readme_contains_package_name() -> None:
    """Package name appears in the generated README heading."""
    m = _manifest()
    readme = CatalogDetail.generate_readme(m, "abseil-cpp", "https://github.com/abseil/abseil-cpp")
    assert "abseil-cpp" in readme


def test_generate_readme_contains_description() -> None:
    """Package description appears in the generated README."""
    m = _manifest()
    readme = CatalogDetail.generate_readme(m, "abseil-cpp", "https://github.com/abseil/abseil-cpp")
    assert "Abseil C++ libraries" in readme


def test_generate_readme_contains_version_tag() -> None:
    """Version tag appears in the dfetch.yaml snippet."""
    m = _manifest(version="20240116.2")
    readme = CatalogDetail.generate_readme(m, "abseil-cpp", "https://github.com/abseil/abseil-cpp")
    assert "20240116.2" in readme


def test_generate_readme_omits_tag_when_no_version() -> None:
    """No 'tag:' line is emitted when version is None."""
    m = _manifest(version=None)
    readme = CatalogDetail.generate_readme(m, "abseil-cpp", "https://github.com/abseil/abseil-cpp")
    assert "tag:" not in readme


def test_generate_readme_contains_dfetch_yaml_snippet() -> None:
    """The generated README contains a dfetch.yaml code block."""
    m = _manifest()
    readme = CatalogDetail.generate_readme(m, "abseil-cpp", "https://github.com/abseil/abseil-cpp")
    assert "dfetch.yaml" in readme


def test_generate_readme_uses_provided_url() -> None:
    """The URL passed in appears verbatim in the dfetch.yaml snippet."""
    m = _manifest()
    readme = CatalogDetail.generate_readme(m, "myrepo", "https://gitlab.com/myorg/myrepo")
    assert "https://gitlab.com/myorg/myrepo" in readme


def test_generate_readme_monorepo_includes_src_line() -> None:
    """Monorepo components include a 'src:' line with the subpath."""
    m = _manifest(subpath="mylib")
    readme = CatalogDetail.generate_readme(m, "mymonorepo", "https://github.com/org/mymonorepo")
    assert "src: mylib" in readme


def test_generate_readme_monorepo_uses_subpath_as_local_name() -> None:
    """The local checkout name (ext/<name>) uses subpath, not the repo name."""
    m = _manifest(subpath="mylib")
    readme = CatalogDetail.generate_readme(m, "mymonorepo", "https://github.com/org/mymonorepo")
    assert "ext/mylib" in readme
    assert "ext/mymonorepo" not in readme


def test_generate_readme_no_subpath_no_src_line() -> None:
    """Packages without a subpath do not emit a 'src:' line."""
    m = _manifest()
    readme = CatalogDetail.generate_readme(m, "abseil-cpp", "https://github.com/abseil/abseil-cpp")
    assert "src:" not in readme
