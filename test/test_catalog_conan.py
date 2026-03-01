"""Tests for dfetch_hub.catalog.conan: conanfile.py attribute parsing and recipe discovery."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from dfetch_hub.catalog.sources.conan import (
    ConanManifest,
    _extract_str_attr,
    _extract_tuple_attr,
    _latest_version,
    parse_conan_recipe,
)

# ---------------------------------------------------------------------------
# Shared conanfile.py fixtures
# ---------------------------------------------------------------------------

_CONANFILE_SIMPLE = textwrap.dedent(
    """\
    from conan import ConanFile

    class AbseilConan(ConanFile):
        name = "abseil"
        description = "Abseil Common Libraries (C++) from Google"
        topics = ("algorithm", "container", "google", "common", "utility")
        homepage = "https://github.com/abseil/abseil-cpp"
        url = "https://github.com/conan-io/conan-center-index"
        license = "Apache-2.0"

        def build(self):
            pass
    """
)

_CONANFILE_MULTILINE_DESC = textwrap.dedent(
    """\
    from conan import ConanFile

    class ZlibConan(ConanFile):
        name = "zlib"
        description = ("A Massively Spiffy Yet Delicately Unobtrusive Compression Library "
                       "(Also Free, Not to Mention Unencumbered by Patents)")
        homepage = "https://zlib.net"
        license = "Zlib"
        topics = ("compression", "deflate")
        url = "https://github.com/conan-io/conan-center-index"
    """
)

_CONFIG_YML = textwrap.dedent(
    """\
    versions:
      "1.0.0":
        folder: all
      "2.0.0":
        folder: all
      "3.1.0":
        folder: all
    """
)


@pytest.fixture(autouse=True)
def _mock_fetch_readme() -> object:
    """Prevent real network calls to fetch_readme in all conan tests."""
    with patch(
        "dfetch_hub.catalog.sources.conan.fetch_readme_for_homepage", return_value=None
    ):
        yield


@pytest.fixture
def recipe_dir(tmp_path: Path) -> Path:
    """Create a minimal recipe directory tree."""
    all_dir = tmp_path / "all"
    all_dir.mkdir()
    (all_dir / "conanfile.py").write_text(_CONANFILE_SIMPLE, encoding="utf-8")
    (tmp_path / "config.yml").write_text(_CONFIG_YML, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# _extract_str_attr
# ---------------------------------------------------------------------------


def test_extract_str_attr_simple() -> None:
    assert _extract_str_attr(_CONANFILE_SIMPLE, "name") == "abseil"


def test_extract_str_attr_homepage() -> None:
    assert (
        _extract_str_attr(_CONANFILE_SIMPLE, "homepage")
        == "https://github.com/abseil/abseil-cpp"
    )


def test_extract_str_attr_license() -> None:
    assert _extract_str_attr(_CONANFILE_SIMPLE, "license") == "Apache-2.0"


def test_extract_str_attr_multiline_description() -> None:
    desc = _extract_str_attr(_CONANFILE_MULTILINE_DESC, "description")
    assert desc is not None
    assert "Massively Spiffy" in desc
    assert "Unencumbered by Patents" in desc


def test_extract_str_attr_missing() -> None:
    assert _extract_str_attr(_CONANFILE_SIMPLE, "nonexistent") is None


# ---------------------------------------------------------------------------
# _extract_tuple_attr
# ---------------------------------------------------------------------------


def test_extract_tuple_attr_topics() -> None:
    topics = _extract_tuple_attr(_CONANFILE_SIMPLE, "topics")
    assert "algorithm" in topics
    assert "google" in topics
    assert len(topics) == 5


def test_extract_tuple_attr_missing() -> None:
    assert _extract_tuple_attr(_CONANFILE_SIMPLE, "nonexistent") == []


# ---------------------------------------------------------------------------
# _latest_version
# ---------------------------------------------------------------------------


def test_latest_version_returns_last_key(tmp_path: Path) -> None:
    config = tmp_path / "config.yml"
    config.write_text(_CONFIG_YML, encoding="utf-8")
    version, folder = _latest_version(config)
    assert version == "3.1.0"
    assert folder == "all"


def test_latest_version_missing_file(tmp_path: Path) -> None:
    version, folder = _latest_version(tmp_path / "config.yml")
    assert version is None
    assert folder == "all"


def test_latest_version_single_entry(tmp_path: Path) -> None:
    config = tmp_path / "config.yml"
    config.write_text('versions:\n  "1.3.1":\n    folder: all\n', encoding="utf-8")
    version, _ = _latest_version(config)
    assert version == "1.3.1"


# ---------------------------------------------------------------------------
# parse_conan_recipe
# ---------------------------------------------------------------------------


def test_parse_conan_recipe_basic(recipe_dir: Path) -> None:
    m = parse_conan_recipe(recipe_dir)
    assert m is not None
    assert m.package_name == "abseil"
    assert m.description == "Abseil Common Libraries (C++) from Google"
    assert m.homepage == "https://github.com/abseil/abseil-cpp"
    assert m.license == "Apache-2.0"
    assert "algorithm" in m.topics
    assert "google" in m.topics


def test_parse_conan_recipe_latest_version(recipe_dir: Path) -> None:
    m = parse_conan_recipe(recipe_dir)
    assert m is not None
    assert m.version == "3.1.0"


def test_parse_conan_recipe_port_name_is_dir_name(recipe_dir: Path) -> None:
    m = parse_conan_recipe(recipe_dir)
    assert m is not None
    assert m.port_name == recipe_dir.name


def test_parse_conan_recipe_no_conanfile_returns_none(tmp_path: Path) -> None:
    (tmp_path / "config.yml").write_text(
        'versions:\n  "1.0":\n    folder: all\n', encoding="utf-8"
    )
    # No conanfile.py created
    assert parse_conan_recipe(tmp_path) is None


def test_parse_conan_recipe_falls_back_to_any_subfolder(tmp_path: Path) -> None:
    """When config.yml points to a missing folder, fall back to scanning subdirs."""
    (tmp_path / "config.yml").write_text(
        'versions:\n  "1.0":\n    folder: 1.x\n', encoding="utf-8"
    )
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / "conanfile.py").write_text(_CONANFILE_SIMPLE, encoding="utf-8")

    m = parse_conan_recipe(tmp_path)
    assert m is not None
    assert m.package_name == "abseil"


def test_parse_conan_recipe_multiline_description(tmp_path: Path) -> None:
    all_dir = tmp_path / "all"
    all_dir.mkdir()
    (all_dir / "conanfile.py").write_text(_CONANFILE_MULTILINE_DESC, encoding="utf-8")
    (tmp_path / "config.yml").write_text(
        'versions:\n  "1.3.1":\n    folder: all\n', encoding="utf-8"
    )

    m = parse_conan_recipe(tmp_path)
    assert m is not None
    assert "Massively Spiffy" in m.description
    assert m.license == "Zlib"
    assert "compression" in m.topics
