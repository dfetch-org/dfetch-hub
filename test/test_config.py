"""Tests for dfetch_hub.config: TOML configuration parsing."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import tomllib

from dfetch_hub.config import HubConfig, Settings, SourceConfig, load_config

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_config(tmp_path: Path) -> Path:
    """Create a minimal dfetch-hub.toml configuration."""
    config_text = textwrap.dedent(
        """\
        [settings]
        concurrency = 4
        catalog_path = "data/catalog.json"
        output_dir = "public"

        [[source]]
        name = "vcpkg"
        strategy = "subfolders"
        url = "https://github.com/microsoft/vcpkg"
        path = "ports"
        manifest = "vcpkg.json"
        label = "vcpkg"
        branch = "master"
        ignore_if_present = ""

        [[source]]
        name = "conan"
        strategy = "subfolders"
        url = "https://github.com/conan-io/conan-center-index"
        path = "recipes"
        manifest = "conandata.yml"
        label = "conan-center"
        """
    )
    config_path = tmp_path / "dfetch-hub.toml"
    config_path.write_text(config_text, encoding="utf-8")
    return config_path


# ---------------------------------------------------------------------------
# SourceConfig dataclass
# ---------------------------------------------------------------------------


def test_source_config_defaults() -> None:
    """SourceConfig has sensible defaults for optional fields."""
    src = SourceConfig(name="test", strategy="subfolders", url="https://example.com")
    assert src.path == ""
    assert src.manifest == ""
    assert src.label == ""
    assert src.branch == ""
    assert src.ignore_if_present == ""


def test_source_config_all_fields() -> None:
    """SourceConfig stores all provided fields."""
    src = SourceConfig(
        name="vcpkg",
        strategy="subfolders",
        url="https://github.com/microsoft/vcpkg",
        path="ports",
        manifest="vcpkg.json",
        label="vcpkg",
        branch="master",
        ignore_if_present=".dfetch_data.yaml",
    )
    assert src.name == "vcpkg"
    assert src.strategy == "subfolders"
    assert src.url == "https://github.com/microsoft/vcpkg"
    assert src.path == "ports"
    assert src.manifest == "vcpkg.json"
    assert src.label == "vcpkg"
    assert src.branch == "master"
    assert src.ignore_if_present == ".dfetch_data.yaml"


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------


def test_settings_defaults() -> None:
    """Settings has sensible defaults for all fields."""
    settings = Settings()
    assert settings.concurrency == 8
    assert settings.catalog_path == ""
    assert settings.output_dir == "site"


def test_settings_custom_values() -> None:
    """Settings stores custom values."""
    settings = Settings(
        concurrency=16, catalog_path="custom/catalog.json", output_dir="build"
    )
    assert settings.concurrency == 16
    assert settings.catalog_path == "custom/catalog.json"
    assert settings.output_dir == "build"


# ---------------------------------------------------------------------------
# HubConfig dataclass
# ---------------------------------------------------------------------------


def test_hub_config_defaults() -> None:
    """HubConfig has default settings and an empty sources list."""
    config = HubConfig()
    assert isinstance(config.settings, Settings)
    assert config.sources == []


def test_hub_config_with_sources() -> None:
    """HubConfig stores multiple sources."""
    src1 = SourceConfig(name="vcpkg", strategy="subfolders", url="https://example.com")
    src2 = SourceConfig(name="conan", strategy="subfolders", url="https://example.com")
    config = HubConfig(sources=[src1, src2])
    assert len(config.sources) == 2
    assert config.sources[0].name == "vcpkg"
    assert config.sources[1].name == "conan"


# ---------------------------------------------------------------------------
# load_config — basic parsing
# ---------------------------------------------------------------------------


def test_load_config_parses_settings(simple_config: Path) -> None:
    """load_config extracts all settings fields."""
    config = load_config(str(simple_config))
    assert config.settings.concurrency == 4
    assert config.settings.catalog_path == "data/catalog.json"
    assert config.settings.output_dir == "public"


def test_load_config_parses_sources(simple_config: Path) -> None:
    """load_config extracts all [[source]] entries in order."""
    config = load_config(str(simple_config))
    assert len(config.sources) == 2
    assert config.sources[0].name == "vcpkg"
    assert config.sources[1].name == "conan"


def test_load_config_vcpkg_source_fields(simple_config: Path) -> None:
    """load_config correctly parses all fields from the vcpkg source."""
    config = load_config(str(simple_config))
    vcpkg = config.sources[0]
    assert vcpkg.strategy == "subfolders"
    assert vcpkg.url == "https://github.com/microsoft/vcpkg"
    assert vcpkg.path == "ports"
    assert vcpkg.manifest == "vcpkg.json"
    assert vcpkg.label == "vcpkg"
    assert vcpkg.branch == "master"
    assert vcpkg.ignore_if_present == ""


def test_load_config_conan_source_fields(simple_config: Path) -> None:
    """load_config correctly parses all fields from the conan source."""
    config = load_config(str(simple_config))
    conan = config.sources[1]
    assert conan.name == "conan"
    assert conan.strategy == "subfolders"
    assert conan.url == "https://github.com/conan-io/conan-center-index"
    assert conan.path == "recipes"
    assert conan.manifest == "conandata.yml"
    assert conan.label == "conan-center"


# ---------------------------------------------------------------------------
# load_config — defaults and missing fields
# ---------------------------------------------------------------------------


def test_load_config_default_settings(tmp_path: Path) -> None:
    """load_config uses Settings defaults when [settings] is absent."""
    config_text = textwrap.dedent(
        """\
        [[source]]
        name = "test"
        strategy = "subfolders"
        url = "https://example.com"
        """
    )
    config_path = tmp_path / "dfetch-hub.toml"
    config_path.write_text(config_text, encoding="utf-8")

    config = load_config(str(config_path))
    assert config.settings.concurrency == 8
    assert config.settings.catalog_path == ""
    assert config.settings.output_dir == "site"


def test_load_config_partial_settings(tmp_path: Path) -> None:
    """load_config merges provided settings with defaults."""
    config_text = textwrap.dedent(
        """\
        [settings]
        concurrency = 2

        [[source]]
        name = "test"
        strategy = "subfolders"
        url = "https://example.com"
        """
    )
    config_path = tmp_path / "dfetch-hub.toml"
    config_path.write_text(config_text, encoding="utf-8")

    config = load_config(str(config_path))
    assert config.settings.concurrency == 2
    assert config.settings.catalog_path == ""
    assert config.settings.output_dir == "site"


def test_load_config_source_missing_optional_fields(tmp_path: Path) -> None:
    """load_config uses SourceConfig defaults for missing optional fields."""
    config_text = textwrap.dedent(
        """\
        [[source]]
        name = "minimal"
        strategy = "subfolders"
        url = "https://example.com"
        """
    )
    config_path = tmp_path / "dfetch-hub.toml"
    config_path.write_text(config_text, encoding="utf-8")

    config = load_config(str(config_path))
    src = config.sources[0]
    assert src.path == ""
    assert src.manifest == ""
    assert src.label == ""
    assert src.branch == ""
    assert src.ignore_if_present == ""


# ---------------------------------------------------------------------------
# load_config — unknown fields
# ---------------------------------------------------------------------------


def test_load_config_ignores_unknown_setting_fields(tmp_path: Path) -> None:
    """load_config silently ignores unknown fields in [settings]."""
    config_text = textwrap.dedent(
        """\
        [settings]
        concurrency = 4
        unknown_field = "ignored"

        [[source]]
        name = "test"
        strategy = "subfolders"
        url = "https://example.com"
        """
    )
    config_path = tmp_path / "dfetch-hub.toml"
    config_path.write_text(config_text, encoding="utf-8")

    config = load_config(str(config_path))
    assert config.settings.concurrency == 4


def test_load_config_ignores_unknown_source_fields(tmp_path: Path) -> None:
    """load_config silently ignores unknown fields in [[source]]."""
    config_text = textwrap.dedent(
        """\
        [[source]]
        name = "test"
        strategy = "subfolders"
        url = "https://example.com"
        future_field = "value"
        """
    )
    config_path = tmp_path / "dfetch-hub.toml"
    config_path.write_text(config_text, encoding="utf-8")

    config = load_config(str(config_path))
    assert config.sources[0].name == "test"


# ---------------------------------------------------------------------------
# load_config — error cases
# ---------------------------------------------------------------------------


def test_load_config_missing_file() -> None:
    """load_config raises FileNotFoundError when the file does not exist."""
    with pytest.raises(FileNotFoundError):
        load_config("nonexistent.toml")


def test_load_config_invalid_toml(tmp_path: Path) -> None:
    """load_config raises TOMLDecodeError for malformed TOML."""
    config_path = tmp_path / "bad.toml"
    config_path.write_text("not valid toml [", encoding="utf-8")

    with pytest.raises(tomllib.TOMLDecodeError):
        load_config(str(config_path))


def test_load_config_settings_not_a_table(tmp_path: Path) -> None:
    """load_config raises ValueError when [settings] is not a table."""
    config_text = textwrap.dedent(
        """\
        settings = "not a table"

        [[source]]
        name = "test"
        strategy = "subfolders"
        url = "https://example.com"
        """
    )
    config_path = tmp_path / "bad.toml"
    config_path.write_text(config_text, encoding="utf-8")

    with pytest.raises(ValueError, match="`\\[settings\\]` must be a TOML table"):
        load_config(str(config_path))


def test_load_config_source_not_an_array(tmp_path: Path) -> None:
    """load_config raises ValueError when [[source]] is not an array of tables."""
    config_text = textwrap.dedent(
        """\
        [source]
        name = "test"
        """
    )
    config_path = tmp_path / "bad.toml"
    config_path.write_text(config_text, encoding="utf-8")

    with pytest.raises(ValueError, match="`\\[\\[source\\]\\]` must be an array"):
        load_config(str(config_path))


# ---------------------------------------------------------------------------
# load_config — edge cases
# ---------------------------------------------------------------------------


def test_load_config_empty_sources(tmp_path: Path) -> None:
    """load_config accepts a config with no sources."""
    config_text = textwrap.dedent(
        """\
        [settings]
        concurrency = 8
        """
    )
    config_path = tmp_path / "dfetch-hub.toml"
    config_path.write_text(config_text, encoding="utf-8")

    config = load_config(str(config_path))
    assert config.sources == []


def test_load_config_multiple_sources(tmp_path: Path) -> None:
    """load_config handles multiple [[source]] blocks correctly."""
    config_text = textwrap.dedent(
        """\
        [[source]]
        name = "src1"
        strategy = "subfolders"
        url = "https://example.com/1"

        [[source]]
        name = "src2"
        strategy = "git-wiki"
        url = "https://example.com/2"

        [[source]]
        name = "src3"
        strategy = "readme-only"
        url = "https://example.com/3"
        """
    )
    config_path = tmp_path / "dfetch-hub.toml"
    config_path.write_text(config_text, encoding="utf-8")

    config = load_config(str(config_path))
    assert len(config.sources) == 3
    assert config.sources[0].name == "src1"
    assert config.sources[1].name == "src2"
    assert config.sources[2].name == "src3"


def test_load_config_preserves_source_order(tmp_path: Path) -> None:
    """load_config preserves the declaration order of [[source]] blocks."""
    config_text = textwrap.dedent(
        """\
        [[source]]
        name = "alpha"
        strategy = "subfolders"
        url = "https://example.com/a"

        [[source]]
        name = "beta"
        strategy = "subfolders"
        url = "https://example.com/b"

        [[source]]
        name = "gamma"
        strategy = "subfolders"
        url = "https://example.com/g"
        """
    )
    config_path = tmp_path / "dfetch-hub.toml"
    config_path.write_text(config_text, encoding="utf-8")

    config = load_config(str(config_path))
    names = [src.name for src in config.sources]
    assert names == ["alpha", "beta", "gamma"]