"""Tests for dfetch_hub.catalog.writer: catalog JSON writing pipeline.

Covers:
- parse_vcs_slug: URL parsing and lowercase normalisation.
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

from dfetch_hub.catalog.sources import BaseManifest, parse_vcs_slug
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
    entry_name: str = "abseil",
    package_name: str = "abseil-cpp",
    description: str = "Abseil C++ libraries from Google",
    homepage: str | None = "https://github.com/abseil/abseil-cpp",
    license_: str | None = "Apache-2.0",
    version: str | None = "20240116.2",
) -> BaseManifest:
    """Build a minimal BaseManifest with sensible defaults for testing."""
    return BaseManifest(
        entry_name=entry_name,
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
# parse_vcs_slug
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
    ],
)
def test_parse_vcs_slug_valid(url: str, expected: tuple[str, str, str]) -> None:
    """Parses host, owner and repo from any https://host/owner/repo URL."""
    assert parse_vcs_slug(url) == expected


def test_parse_vcs_slug_lowercases_all_parts() -> None:
    """All three parts of the returned tuple are lowercased."""
    assert parse_vcs_slug("https://GitHub.COM/ABSEIL/Abseil-CPP") == (
        "github.com",
        "abseil",
        "abseil-cpp",
    )


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "",
        "https://github.com/only-org",
    ],
)
def test_parse_vcs_slug_invalid_returns_none(url: str) -> None:
    """Returns None for URLs that do not match host/owner/repo."""
    assert parse_vcs_slug(url) is None


# ---------------------------------------------------------------------------
# _catalog_id
# ---------------------------------------------------------------------------


def test_catalog_id_format() -> None:
    """Produces vcs_host/org/repo format."""
    assert _catalog_id("github", "abseil", "abseil-cpp") == "github/abseil/abseil-cpp"


def test_catalog_id_lowercases_inputs() -> None:
    """All components are lowercased."""
    assert _catalog_id("GITHUB", "Abseil", "Abseil-CPP") == "github/abseil/abseil-cpp"


def test_catalog_id_gitlab() -> None:
    """Works for non-GitHub VCS hosts."""
    assert _catalog_id("gitlab", "org", "repo") == "gitlab/org/repo"


# ---------------------------------------------------------------------------
# _merge_catalog_entry
# ---------------------------------------------------------------------------


def test_merge_catalog_entry_new_has_correct_id() -> None:
    """New entry has the correct vcs_host/org/repo ID."""
    entry = _merge_catalog_entry(
        None, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert entry["id"] == "github/abseil/abseil-cpp"


def test_merge_catalog_entry_new_populates_name() -> None:
    """New entry takes package_name from the manifest."""
    entry = _merge_catalog_entry(
        None, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert entry["name"] == "abseil-cpp"


def test_merge_catalog_entry_new_populates_description() -> None:
    """New entry takes description from the manifest."""
    entry = _merge_catalog_entry(
        None, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert entry["description"] == "Abseil C++ libraries from Google"


def test_merge_catalog_entry_new_populates_license() -> None:
    """New entry takes license from the manifest."""
    entry = _merge_catalog_entry(
        None, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert entry["license"] == "Apache-2.0"


def test_merge_catalog_entry_source_type_matches_vcs_host() -> None:
    """source_type equals the vcs_host passed in."""
    github_entry = _merge_catalog_entry(
        None, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert github_entry["source_type"] == "github"

    gitlab_entry = _merge_catalog_entry(
        None,
        _manifest(homepage="https://gitlab.com/org/repo"),
        "gitlab",
        "org",
        "repo",
        "some-source",
    )
    assert gitlab_entry["source_type"] == "gitlab"


def test_merge_catalog_entry_adds_source_label() -> None:
    """Label is present in source_labels of the new entry."""
    entry = _merge_catalog_entry(
        None, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert "vcpkg" in entry["source_labels"]


def test_merge_catalog_entry_adds_version_tag() -> None:
    """Version is recorded in the tags list."""
    entry = _merge_catalog_entry(
        None, _manifest(version="20240116.2"), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    tag_names = {t["name"] for t in entry["tags"]}
    assert "20240116.2" in tag_names


def test_merge_catalog_entry_no_duplicate_version_tag() -> None:
    """The same version is not added a second time."""
    existing = _existing_catalog_entry()
    existing["tags"] = [
        {"name": "20240116.2", "is_tag": True, "commit_sha": None, "date": None}
    ]
    entry = _merge_catalog_entry(
        existing,
        _manifest(version="20240116.2"),
        "github",
        "abseil",
        "abseil-cpp",
        "vcpkg",
    )
    assert sum(1 for t in entry["tags"] if t["name"] == "20240116.2") == 1


def test_merge_catalog_entry_merges_source_labels() -> None:
    """Updating an existing entry preserves its other labels."""
    existing = _existing_catalog_entry(label="conan")
    entry = _merge_catalog_entry(
        existing, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert "conan" in entry["source_labels"]
    assert "vcpkg" in entry["source_labels"]


def test_merge_catalog_entry_no_duplicate_label() -> None:
    """Applying the same label twice does not duplicate it."""
    existing = _existing_catalog_entry(label="vcpkg")
    entry = _merge_catalog_entry(
        existing, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert entry["source_labels"].count("vcpkg") == 1


def test_merge_catalog_entry_url_uses_homepage() -> None:
    """New entry uses manifest.homepage as the package URL."""
    entry = _merge_catalog_entry(
        None, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert entry["url"] == "https://github.com/abseil/abseil-cpp"


def test_merge_catalog_entry_no_version_no_tag_added() -> None:
    """No tag entry is created when version is None."""
    entry = _merge_catalog_entry(
        None, _manifest(version=None), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert not entry["tags"]


def test_merge_catalog_entry_backfills_missing_description() -> None:
    """Existing entry with no description is backfilled from the manifest."""
    existing = _existing_catalog_entry()
    existing["description"] = None
    entry = _merge_catalog_entry(
        existing, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert entry["description"] == "Abseil C++ libraries from Google"


def test_merge_catalog_entry_does_not_overwrite_existing_description() -> None:
    """An already-populated description must not be replaced by the manifest."""
    existing = _existing_catalog_entry()  # description = "old description"
    entry = _merge_catalog_entry(
        existing, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert entry["description"] == "old description"


def test_merge_catalog_entry_backfills_missing_license() -> None:
    """Existing entry with no license is backfilled from the manifest."""
    existing = _existing_catalog_entry()  # license = None by default
    entry = _merge_catalog_entry(
        existing, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert entry["license"] == "Apache-2.0"


def test_merge_catalog_entry_does_not_overwrite_existing_license() -> None:
    """An already-populated license must not be replaced by the manifest."""
    existing = _existing_catalog_entry()
    existing["license"] = "MIT"
    entry = _merge_catalog_entry(
        existing, _manifest(), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert entry["license"] == "MIT"


def test_merge_catalog_entry_v_prefix_tag_not_duplicated() -> None:
    """Version '1.2.3' is not added if 'v1.2.3' already exists in the tag list."""
    existing = _existing_catalog_entry()
    existing["tags"] = [
        {"name": "v1.2.3", "is_tag": True, "commit_sha": None, "date": None}
    ]
    entry = _merge_catalog_entry(
        existing, _manifest(version="1.2.3"), "github", "abseil", "abseil-cpp", "vcpkg"
    )
    assert sum(1 for t in entry["tags"] if t["name"].lstrip("v") == "1.2.3") == 1


# ---------------------------------------------------------------------------
# _generate_readme
# ---------------------------------------------------------------------------


def test_generate_readme_contains_package_name() -> None:
    """Package name appears in the generated README heading."""
    assert "abseil-cpp" in _generate_readme(
        _manifest(), "abseil-cpp", "https://github.com/abseil/abseil-cpp"
    )


def test_generate_readme_contains_description() -> None:
    """Package description appears in the generated README."""
    assert "Abseil C++ libraries" in _generate_readme(
        _manifest(), "abseil-cpp", "https://github.com/abseil/abseil-cpp"
    )


def test_generate_readme_contains_version_tag() -> None:
    """Version tag appears in the dfetch.yaml snippet."""
    assert "20240116.2" in _generate_readme(
        _manifest(version="20240116.2"),
        "abseil-cpp",
        "https://github.com/abseil/abseil-cpp",
    )


def test_generate_readme_omits_tag_when_no_version() -> None:
    """No 'tag:' line is emitted when version is None."""
    readme = _generate_readme(
        _manifest(version=None), "abseil-cpp", "https://github.com/abseil/abseil-cpp"
    )
    assert "tag:" not in readme


def test_generate_readme_contains_dfetch_yaml_snippet() -> None:
    """The generated README contains a dfetch.yaml code block."""
    readme = _generate_readme(
        _manifest(), "abseil-cpp", "https://github.com/abseil/abseil-cpp"
    )
    assert "dfetch.yaml" in readme


def test_generate_readme_uses_provided_url() -> None:
    """The URL passed in appears verbatim in the dfetch.yaml snippet."""
    readme = _generate_readme(_manifest(), "myrepo", "https://gitlab.com/myorg/myrepo")
    assert "https://gitlab.com/myorg/myrepo" in readme


# ---------------------------------------------------------------------------
# _merge_detail
# ---------------------------------------------------------------------------


def test_merge_detail_new_sets_org_and_repo() -> None:
    """New detail record stores org and repo."""
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        detail = _merge_detail(
            None, _manifest(), "abseil", "abseil-cpp", "vcpkg", "vcpkg", "ports"
        )
    assert detail["org"] == "abseil"
    assert detail["repo"] == "abseil-cpp"


def test_merge_detail_new_adds_catalog_source() -> None:
    """New detail record contains exactly one catalog source entry."""
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
        entry_name="clibs/buffer",
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
        entry_name="clibs/buffer",
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
    """A catalog.json file is created in data_dir."""
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            registry_path="ports",
        )
    assert (tmp_path / "catalog.json").exists()


def test_write_catalog_entry_in_catalog_json(tmp_path: Path) -> None:
    """GitHub entries appear under github/org/repo keys in catalog.json."""
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            registry_path="ports",
        )
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert "github/abseil/abseil-cpp" in catalog


def test_write_catalog_writes_detail_json(tmp_path: Path) -> None:
    """Detail JSON is written to data/github/org/repo.json for GitHub packages."""
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            registry_path="ports",
        )
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
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        added, updated = write_catalog(
            [_manifest(), boost],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            registry_path="ports",
        )
    assert added == 2
    assert updated == 0


def test_write_catalog_returns_updated_count(tmp_path: Path) -> None:
    """Processing the same package twice increments the updated counter."""
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            registry_path="ports",
        )
        added, updated = write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            registry_path="ports",
        )
    assert added == 0
    assert updated == 1


def test_write_catalog_skips_manifest_without_homepage(tmp_path: Path) -> None:
    """Manifests with no homepage at all are silently skipped."""
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        added, updated = write_catalog(
            [_manifest(homepage=None)],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            registry_path="ports",
        )
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert len(catalog) == 0
    assert added == 0
    assert updated == 0


def test_write_catalog_skips_unrecognized_url(tmp_path: Path) -> None:
    """Manifests whose homepage cannot be parsed as host/owner/repo are skipped."""
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        added, updated = write_catalog(
            [_manifest(homepage="https://example.com/not-a-repo")],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            registry_path="ports",
        )
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert len(catalog) == 0
    assert added == 0
    assert updated == 0


def test_write_catalog_accepts_gitlab_homepage(tmp_path: Path) -> None:
    """GitLab-hosted packages are written under the gitlab/ directory."""
    gitlab_manifest = _manifest(
        entry_name="mylib",
        package_name="mylib",
        homepage="https://gitlab.com/myorg/mylib",
        description="A library on GitLab",
    )
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        added, updated = write_catalog(
            [gitlab_manifest],
            tmp_path,
            source_name="some-source",
            label="some-source",
            registry_path="packages",
        )
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert "gitlab/myorg/mylib" in catalog
    assert added == 1
    assert updated == 0
    detail_path = tmp_path / "gitlab" / "myorg" / "mylib.json"
    assert detail_path.exists()


def test_write_catalog_merges_across_two_sources(tmp_path: Path) -> None:
    """Same package from two separate sources should be merged into one entry."""
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            registry_path="ports",
        )
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="conan",
            label="conan",
            registry_path="recipes",
        )
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    entry = catalog["github/abseil/abseil-cpp"]
    assert "vcpkg" in entry["source_labels"]
    assert "conan" in entry["source_labels"]


def test_write_catalog_detail_json_has_both_sources(tmp_path: Path) -> None:
    """Detail JSON lists both sources after two write_catalog calls."""
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            registry_path="ports",
        )
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="conan",
            label="conan",
            registry_path="recipes",
        )
    detail = json.loads(
        (tmp_path / "github" / "abseil" / "abseil-cpp.json").read_text(encoding="utf-8")
    )
    source_names = [s["source_name"] for s in detail["catalog_sources"]]
    assert "vcpkg" in source_names
    assert "conan" in source_names


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


def test_merge_catalog_entry_topics_from_manifest() -> None:
    """_merge_catalog_entry includes topics from manifests with a topics attribute."""
    from dfetch_hub.catalog.sources.conan import ConanManifest

    manifest = ConanManifest(
        entry_name="abseil",
        package_name="abseil-cpp",
        description="Abseil C++ libraries",
        homepage="https://github.com/abseil/abseil-cpp",
        license="Apache-2.0",
        version="20240116.2",
        topics=["algorithm", "container", "google"],
    )

    entry = _merge_catalog_entry(None, manifest, "github", "abseil", "abseil-cpp", "conan")
    assert "algorithm" in entry["topics"]
    assert "container" in entry["topics"]
    assert "google" in entry["topics"]


def test_merge_catalog_entry_merges_topics_no_duplicates() -> None:
    """_merge_catalog_entry merges topics without duplicating existing ones."""
    from dfetch_hub.catalog.sources.conan import ConanManifest

    existing = _existing_catalog_entry()
    existing["topics"] = ["algorithm", "existing-topic"]

    manifest = ConanManifest(
        entry_name="abseil",
        package_name="abseil-cpp",
        description="Abseil C++ libraries",
        homepage="https://github.com/abseil/abseil-cpp",
        license="Apache-2.0",
        version="20240116.2",
        topics=["algorithm", "new-topic"],
    )

    entry = _merge_catalog_entry(
        existing, manifest, "github", "abseil", "abseil-cpp", "conan"
    )
    assert entry["topics"].count("algorithm") == 1
    assert "existing-topic" in entry["topics"]
    assert "new-topic" in entry["topics"]


def test_generate_readme_escapes_special_chars() -> None:
    """_generate_readme handles package names and descriptions with special characters."""
    manifest = BaseManifest(
        entry_name="test-pkg",
        package_name="Test & Package <special>",
        description='Description with "quotes" and special chars',
        homepage="https://github.com/org/repo",
        license=None,
        version=None,
    )

    readme = _generate_readme(manifest, "repo", "https://github.com/org/repo")
    assert 'Test & Package <special>' in readme
    assert 'Description with "quotes"' in readme


def test_merge_detail_tags_fetched_when_empty() -> None:
    """_merge_detail fetches tags from upstream when the tag list is empty."""
    upstream_tags = [
        {"name": "v1.0.0", "is_tag": True, "commit_sha": "abc123", "date": None},
        {"name": "v2.0.0", "is_tag": True, "commit_sha": "def456", "date": None},
    ]

    with patch(
        "dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=upstream_tags
    ):
        detail = _merge_detail(
            None, _manifest(), "abseil", "abseil-cpp", "vcpkg", "vcpkg", "ports"
        )

    tag_names = [t["name"] for t in detail["tags"]]
    assert "v1.0.0" in tag_names
    assert "v2.0.0" in tag_names


def test_merge_detail_no_fetch_when_tags_exist() -> None:
    """_merge_detail does not fetch tags when the tag list is already populated."""
    existing = _existing_detail()
    existing["tags"] = [
        {"name": "v1.0.0", "is_tag": True, "commit_sha": "abc", "date": None}
    ]

    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags") as mock_fetch:
        _merge_detail(
            existing, _manifest(), "abseil", "abseil-cpp", "vcpkg", "vcpkg", "ports"
        )

    # Should not be called since tags already exist
    mock_fetch.assert_not_called()


def test_catalog_id_with_special_characters() -> None:
    """_catalog_id handles org/repo names with hyphens and underscores."""
    assert _catalog_id("github", "my-org", "my_repo-v2") == "github/my-org/my_repo-v2"


def test_write_catalog_creates_subdirectories(tmp_path: Path) -> None:
    """write_catalog creates nested subdirectories for detail JSONs."""
    with patch("dfetch_hub.catalog.writer._fetch_upstream_tags", return_value=[]):
        write_catalog(
            [_manifest()],
            tmp_path,
            source_name="vcpkg",
            label="vcpkg",
            registry_path="ports",
        )

    # Verify directory structure was created
    assert (tmp_path / "github").exists()
    assert (tmp_path / "github" / "abseil").exists()
    assert (tmp_path / "github" / "abseil" / "abseil-cpp.json").exists()