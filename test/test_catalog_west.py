"""Tests for dfetch_hub.catalog.sources.west: west.yml parsing."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from dfetch_hub.catalog.sources.west import (
    WestProject,
    _build_remote_map,
    _build_west_project,
    _extract_groups,
    _project_url,
    parse_west_yaml,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_WEST_YAML_SIMPLE = textwrap.dedent(
    """\
    manifest:
      defaults:
        remote: upstream
      remotes:
        - name: upstream
          url-base: https://github.com/zephyrproject-rtos
        - name: babblesim
          url-base: https://github.com/BabbleSim
      projects:
        - name: mcuboot
          revision: v2.1.0+zephyr
          path: bootloader/mcuboot
        - name: hal_nordic
          revision: abc123
          path: modules/hal/nordic
          groups:
            - hal
        - name: sim_tool
          remote: babblesim
          revision: deadbeef
          path: tools/sim
          groups:
            - babblesim
            - optional
    """
)

_WEST_YAML_EXPLICIT_URL = textwrap.dedent(
    """\
    manifest:
      remotes:
        - name: upstream
          url-base: https://github.com/zephyrproject-rtos
      projects:
        - name: custom-lib
          url: https://gitlab.com/myorg/custom-lib
          revision: v1.0
        - name: mbedtls
          repo-path: mbedtls
          revision: v3.5.0
    """
)

_WEST_YAML_WITH_DESCRIPTION = textwrap.dedent(
    """\
    manifest:
      defaults:
        remote: upstream
      remotes:
        - name: upstream
          url-base: https://github.com/zephyrproject-rtos
      projects:
        - name: lvgl
          revision: v8.3.7
          description: Light and Versatile Graphics Library
    """
)

_SAMPLE_README = "# mcuboot\n\nA secure bootloader for embedded systems.\n"


@pytest.fixture
def simple_west_yaml(tmp_path: Path) -> Path:
    """Write _WEST_YAML_SIMPLE to a temporary file and return its path."""
    p = tmp_path / "west.yml"
    p.write_text(_WEST_YAML_SIMPLE, encoding="utf-8")
    return p


@pytest.fixture
def explicit_url_west_yaml(tmp_path: Path) -> Path:
    """Write _WEST_YAML_EXPLICIT_URL to a temporary file and return its path."""
    p = tmp_path / "west.yml"
    p.write_text(_WEST_YAML_EXPLICIT_URL, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _build_remote_map
# ---------------------------------------------------------------------------


def test_build_remote_map_extracts_all_remotes() -> None:
    """All remote entries are captured in the result dict."""
    remotes = [
        {"name": "upstream", "url-base": "https://github.com/zephyrproject-rtos"},
        {"name": "babblesim", "url-base": "https://github.com/BabbleSim"},
    ]
    result = _build_remote_map(remotes)

    assert result == {
        "upstream": "https://github.com/zephyrproject-rtos",
        "babblesim": "https://github.com/BabbleSim",
    }


def test_build_remote_map_strips_trailing_slash() -> None:
    """Trailing slashes on url-base values are stripped."""
    remotes = [{"name": "r", "url-base": "https://github.com/org/"}]
    result = _build_remote_map(remotes)

    assert result["r"] == "https://github.com/org"


def test_build_remote_map_ignores_non_dict_entries() -> None:
    """Non-dict entries in the remotes list are silently ignored."""
    result = _build_remote_map(["not-a-dict", {"name": "ok", "url-base": "https://x.com"}])

    assert "ok" in result
    assert len(result) == 1


def test_build_remote_map_returns_empty_for_non_list() -> None:
    """A non-list input returns an empty dict without raising."""
    assert _build_remote_map(None) == {}
    assert _build_remote_map("string") == {}
    assert _build_remote_map(42) == {}


def test_build_remote_map_ignores_entries_missing_name_or_url_base() -> None:
    """Entries lacking 'name' or 'url-base' are skipped."""
    remotes = [
        {"name": "incomplete"},
        {"url-base": "https://example.com"},
        {"name": "complete", "url-base": "https://example.com"},
    ]
    result = _build_remote_map(remotes)

    assert list(result.keys()) == ["complete"]


# ---------------------------------------------------------------------------
# _project_url
# ---------------------------------------------------------------------------

_REMOTE_BASES = {
    "upstream": "https://github.com/zephyrproject-rtos",
    "babblesim": "https://github.com/BabbleSim",
}


def test_project_url_uses_explicit_url() -> None:
    """An explicit 'url' field takes priority over remote + repo-path."""
    entry: dict[str, object] = {"name": "custom", "url": "https://gitlab.com/myorg/custom"}
    result = _project_url(entry, _REMOTE_BASES, "upstream")

    assert result == "https://gitlab.com/myorg/custom"


def test_project_url_uses_default_remote_and_name() -> None:
    """When no remote is specified, the default remote and project name are used."""
    entry: dict[str, object] = {"name": "mcuboot"}
    result = _project_url(entry, _REMOTE_BASES, "upstream")

    assert result == "https://github.com/zephyrproject-rtos/mcuboot"


def test_project_url_uses_explicit_remote() -> None:
    """An explicit 'remote' field overrides the default remote."""
    entry: dict[str, object] = {"name": "sim_tool", "remote": "babblesim"}
    result = _project_url(entry, _REMOTE_BASES, "upstream")

    assert result == "https://github.com/BabbleSim/sim_tool"


def test_project_url_uses_repo_path_over_name() -> None:
    """'repo-path' is used in place of 'name' for URL construction."""
    entry: dict[str, object] = {"name": "mbedtls", "repo-path": "mbedtls"}
    result = _project_url(entry, _REMOTE_BASES, "upstream")

    assert result == "https://github.com/zephyrproject-rtos/mbedtls"


def test_project_url_returns_none_for_unknown_remote() -> None:
    """Returns None when the remote name has no url-base in the map."""
    entry: dict[str, object] = {"name": "foo", "remote": "nonexistent"}
    result = _project_url(entry, _REMOTE_BASES, "upstream")

    assert result is None


def test_project_url_returns_none_when_no_default_remote() -> None:
    """Returns None when there is no remote and no default is configured."""
    entry: dict[str, object] = {"name": "foo"}
    result = _project_url(entry, {}, "")

    assert result is None


# ---------------------------------------------------------------------------
# _extract_groups
# ---------------------------------------------------------------------------


def test_extract_groups_returns_group_names() -> None:
    """Group names are extracted from a list of strings."""
    entry: dict[str, object] = {"groups": ["hal", "optional"]}
    assert _extract_groups(entry) == ["hal", "optional"]


def test_extract_groups_returns_empty_for_missing_key() -> None:
    """Returns empty list when 'groups' is absent."""
    assert _extract_groups({}) == []


def test_extract_groups_returns_empty_for_non_list() -> None:
    """Returns empty list when 'groups' is not a list."""
    assert _extract_groups({"groups": "hal"}) == []


# ---------------------------------------------------------------------------
# _build_west_project
# ---------------------------------------------------------------------------


def test_build_west_project_basic_fields() -> None:
    """Core fields are populated correctly from a minimal entry."""
    entry: dict[str, object] = {"name": "mcuboot", "revision": "v2.1.0"}
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        project = _build_west_project(entry, _REMOTE_BASES, "upstream")

    assert project is not None
    assert project.entry_name == "mcuboot"
    assert project.package_name == "mcuboot"
    assert project.homepage == "https://github.com/zephyrproject-rtos/mcuboot"
    assert project.version == "v2.1.0"
    assert project.license is None
    assert project.in_project_repo is False


def test_build_west_project_returns_none_for_missing_name() -> None:
    """Returns None when the entry has no 'name' field."""
    entry: dict[str, object] = {"revision": "v1.0"}
    result = _build_west_project(entry, _REMOTE_BASES, "upstream")

    assert result is None


def test_build_west_project_returns_none_for_unresolvable_url() -> None:
    """Returns None when the URL cannot be determined."""
    entry: dict[str, object] = {"name": "orphan", "remote": "missing-remote"}
    result = _build_west_project(entry, _REMOTE_BASES, "upstream")

    assert result is None


def test_build_west_project_groups_populated() -> None:
    """The groups field is populated from the entry."""
    entry: dict[str, object] = {"name": "hal_nordic", "revision": "abc", "groups": ["hal"]}
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        project = _build_west_project(entry, _REMOTE_BASES, "upstream")

    assert project is not None
    assert project.groups == ["hal"]


def test_build_west_project_description_empty_when_absent() -> None:
    """Description defaults to empty string when not present in entry."""
    entry: dict[str, object] = {"name": "mcuboot"}
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        project = _build_west_project(entry, _REMOTE_BASES, "upstream")

    assert project is not None
    assert project.description == ""


def test_build_west_project_description_from_entry() -> None:
    """Description is populated when present in the entry."""
    entry: dict[str, object] = {"name": "lvgl", "description": "Light and Versatile Graphics Library"}
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        project = _build_west_project(entry, _REMOTE_BASES, "upstream")

    assert project is not None
    assert project.description == "Light and Versatile Graphics Library"


def test_build_west_project_fetches_readme() -> None:
    """readme_content is populated via fetch_readme_for_homepage."""
    entry: dict[str, object] = {"name": "mcuboot"}
    with patch(
        "dfetch_hub.catalog.sources.west.fetch_readme_for_homepage",
        return_value=_SAMPLE_README,
    ):
        project = _build_west_project(entry, _REMOTE_BASES, "upstream")

    assert project is not None
    assert project.readme_content == _SAMPLE_README


def test_build_west_project_repository_url_in_urls() -> None:
    """The urls dict always contains a 'Repository' key."""
    entry: dict[str, object] = {"name": "mcuboot"}
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        project = _build_west_project(entry, _REMOTE_BASES, "upstream")

    assert project is not None
    assert "Repository" in project.urls
    assert project.urls["Repository"] == project.homepage


def test_build_west_project_entry_name_is_lowercased() -> None:
    """entry_name is always lowercase even when 'name' has uppercase letters."""
    entry: dict[str, object] = {"name": "HAL_Nordic"}
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        project = _build_west_project(entry, _REMOTE_BASES, "upstream")

    assert project is not None
    assert project.entry_name == "hal_nordic"
    assert project.package_name == "HAL_Nordic"


# ---------------------------------------------------------------------------
# parse_west_yaml — basic parsing
# ---------------------------------------------------------------------------


def test_parse_west_yaml_returns_all_projects(simple_west_yaml: Path) -> None:
    """All three projects in the simple fixture are returned."""
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(simple_west_yaml)

    assert len(projects) == 3


def test_parse_west_yaml_project_names(simple_west_yaml: Path) -> None:
    """Project package_names match the west.yml 'name' fields."""
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(simple_west_yaml)

    names = {p.package_name for p in projects}
    assert names == {"mcuboot", "hal_nordic", "sim_tool"}


def test_parse_west_yaml_default_remote_used(simple_west_yaml: Path) -> None:
    """Projects without an explicit remote use the manifest default remote."""
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(simple_west_yaml)

    mcuboot = next(p for p in projects if p.package_name == "mcuboot")
    assert mcuboot.homepage == "https://github.com/zephyrproject-rtos/mcuboot"


def test_parse_west_yaml_explicit_remote_used(simple_west_yaml: Path) -> None:
    """Projects with an explicit remote use that remote's url-base."""
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(simple_west_yaml)

    sim = next(p for p in projects if p.package_name == "sim_tool")
    assert sim.homepage == "https://github.com/BabbleSim/sim_tool"


def test_parse_west_yaml_groups_populated(simple_west_yaml: Path) -> None:
    """Groups are correctly extracted for projects that declare them."""
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(simple_west_yaml)

    hal = next(p for p in projects if p.package_name == "hal_nordic")
    sim = next(p for p in projects if p.package_name == "sim_tool")
    mcuboot = next(p for p in projects if p.package_name == "mcuboot")

    assert hal.groups == ["hal"]
    assert set(sim.groups) == {"babblesim", "optional"}
    assert mcuboot.groups == []


def test_parse_west_yaml_version_from_revision(simple_west_yaml: Path) -> None:
    """The 'revision' field becomes the version of the WestProject."""
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(simple_west_yaml)

    mcuboot = next(p for p in projects if p.package_name == "mcuboot")
    assert mcuboot.version == "v2.1.0+zephyr"


# ---------------------------------------------------------------------------
# parse_west_yaml — explicit URL and repo-path
# ---------------------------------------------------------------------------


def test_parse_west_yaml_explicit_url_project(explicit_url_west_yaml: Path) -> None:
    """A project with an explicit 'url' field uses that URL as homepage."""
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(explicit_url_west_yaml)

    custom = next((p for p in projects if p.package_name == "custom-lib"), None)
    assert custom is not None
    assert custom.homepage == "https://gitlab.com/myorg/custom-lib"


def test_parse_west_yaml_no_default_remote_skips_project(explicit_url_west_yaml: Path) -> None:
    """A project with no remote and no manifest default is skipped (URL cannot be resolved)."""
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(explicit_url_west_yaml)

    # mbedtls in this fixture has no remote and the manifest has no default remote
    names = {p.package_name for p in projects}
    assert "mbedtls" not in names


def test_parse_west_yaml_with_description(tmp_path: Path) -> None:
    """The optional 'description' field is surfaced in WestProject.description."""
    p = tmp_path / "west.yml"
    p.write_text(_WEST_YAML_WITH_DESCRIPTION, encoding="utf-8")

    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(p)

    lvgl = next(p for p in projects if p.package_name == "lvgl")
    assert lvgl.description == "Light and Versatile Graphics Library"


# ---------------------------------------------------------------------------
# parse_west_yaml — limit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [1, 2])
def test_parse_west_yaml_limit(simple_west_yaml: Path, limit: int) -> None:
    """limit=N returns at most N projects."""
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(simple_west_yaml, limit=limit)

    assert len(projects) == limit


def test_parse_west_yaml_limit_none_returns_all(simple_west_yaml: Path) -> None:
    """limit=None returns all projects."""
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(simple_west_yaml, limit=None)

    assert len(projects) == 3


def test_parse_west_yaml_limit_zero_returns_empty(simple_west_yaml: Path) -> None:
    """limit=0 returns an empty list."""
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(simple_west_yaml, limit=0)

    assert projects == []


def test_parse_west_yaml_limit_larger_than_total(simple_west_yaml: Path) -> None:
    """A limit larger than the project count returns all projects."""
    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(simple_west_yaml, limit=100)

    assert len(projects) == 3


# ---------------------------------------------------------------------------
# parse_west_yaml — error handling
# ---------------------------------------------------------------------------


def test_parse_west_yaml_returns_empty_on_bad_yaml(tmp_path: Path) -> None:
    """Returns empty list when the file contains invalid YAML."""
    p = tmp_path / "west.yml"
    p.write_text(": - not valid: yaml: content\n\t bad indent", encoding="utf-8")

    result = parse_west_yaml(p)

    assert result == []


def test_parse_west_yaml_returns_empty_for_non_mapping(tmp_path: Path) -> None:
    """Returns empty list when YAML root is not a mapping."""
    p = tmp_path / "west.yml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")

    result = parse_west_yaml(p)

    assert result == []


def test_parse_west_yaml_returns_empty_for_missing_manifest_key(tmp_path: Path) -> None:
    """Returns empty list when the 'manifest' top-level key is absent."""
    p = tmp_path / "west.yml"
    p.write_text("something: else\n", encoding="utf-8")

    result = parse_west_yaml(p)

    assert result == []


def test_parse_west_yaml_returns_empty_on_missing_file(tmp_path: Path) -> None:
    """Returns empty list when the file does not exist."""
    result = parse_west_yaml(tmp_path / "nonexistent.yml")

    assert result == []


def test_parse_west_yaml_skips_projects_with_missing_url(tmp_path: Path) -> None:
    """Projects whose URL cannot be resolved are silently skipped."""
    content = textwrap.dedent(
        """\
        manifest:
          defaults:
            remote: upstream
          remotes:
            - name: upstream
              url-base: https://github.com/zephyrproject-rtos
          projects:
            - name: good-project
              revision: v1.0
            - name: no-remote-project
              remote: nonexistent
              revision: v1.0
        """
    )
    p = tmp_path / "west.yml"
    p.write_text(content, encoding="utf-8")

    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(p)

    assert len(projects) == 1
    assert projects[0].package_name == "good-project"


def test_parse_west_yaml_skips_non_dict_project_entries(tmp_path: Path) -> None:
    """Non-dict entries in the projects list are silently skipped."""
    content = textwrap.dedent(
        """\
        manifest:
          defaults:
            remote: upstream
          remotes:
            - name: upstream
              url-base: https://github.com/zephyrproject-rtos
          projects:
            - name: good-project
            - just a string
            - 42
        """
    )
    p = tmp_path / "west.yml"
    p.write_text(content, encoding="utf-8")

    with patch("dfetch_hub.catalog.sources.west.fetch_readme_for_homepage", return_value=None):
        projects = parse_west_yaml(p)

    assert len(projects) == 1


# ---------------------------------------------------------------------------
# WestProject dataclass sanity check
# ---------------------------------------------------------------------------


def test_west_project_is_base_manifest_subclass() -> None:
    """WestProject inherits from BaseManifest."""
    from dfetch_hub.catalog.sources import BaseManifest

    assert issubclass(WestProject, BaseManifest)


def test_west_project_groups_default_is_empty_list() -> None:
    """WestProject instances start with an empty groups list."""
    project = WestProject(
        entry_name="test",
        package_name="Test",
        description="",
        homepage=None,
        license=None,
        version=None,
    )
    assert project.groups == []
    # Ensure instances don't share the same list object
    other = WestProject(
        entry_name="other",
        package_name="Other",
        description="",
        homepage=None,
        license=None,
        version=None,
    )
    project.groups.append("x")
    assert other.groups == []
