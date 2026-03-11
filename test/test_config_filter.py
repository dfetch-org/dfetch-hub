"""Tests for filter configuration parsing in dfetch_hub.config."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

from dfetch_hub.config import _parse_filter_rules  # noqa: PLC2701
from dfetch_hub.config import _parse_filters  # noqa: PLC2701
from dfetch_hub.config import (  # noqa: PLC2701
    FilterRuleConfig,
    HubConfig,
    TagFilterConfig,
    load_config,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _write_toml(tmp_path: Path, content: str) -> Path:
    """Write *content* to a temporary dfetch-hub.toml and return its path."""
    cfg = tmp_path / "dfetch-hub.toml"
    cfg.write_text(textwrap.dedent(content), encoding="utf-8")
    return cfg


# ---------------------------------------------------------------------------
# _parse_filter_rules
# ---------------------------------------------------------------------------


class TestParseFilterRules:
    """Unit tests for _parse_filter_rules."""

    def test_empty_list_returns_empty(self) -> None:
        """An empty input list produces an empty result."""
        assert _parse_filter_rules([]) == []

    def test_non_list_returns_empty(self) -> None:
        """A non-list value (e.g. None, str) returns an empty list."""
        assert _parse_filter_rules(None) == []  # type: ignore[arg-type]
        assert _parse_filter_rules("invalid") == []  # type: ignore[arg-type]

    def test_single_rule_with_all_fields(self) -> None:
        """A rule dict with all known fields is parsed correctly."""
        rules = _parse_filter_rules([{"kind": "prefix", "value": "v", "case": "sensitive"}])
        assert len(rules) == 1
        assert rules[0].kind == "prefix"
        assert rules[0].value == "v"
        assert rules[0].case == "sensitive"

    def test_rule_defaults_applied(self) -> None:
        """When 'value' and 'case' are absent the dataclass defaults are used."""
        rules = _parse_filter_rules([{"kind": "semver"}])
        assert rules[0].value == ""
        assert rules[0].case == "smart"

    def test_unknown_keys_ignored(self) -> None:
        """Unknown keys inside a rule dict are silently ignored."""
        rules = _parse_filter_rules([{"kind": "regex", "value": r"^v\d", "extra": "ignored"}])
        assert len(rules) == 1
        assert rules[0].kind == "regex"

    def test_rule_without_kind_skipped(self) -> None:
        """A rule dict missing the required 'kind' key is skipped."""
        rules = _parse_filter_rules([{"value": "v", "case": "smart"}])
        assert rules == []

    def test_non_dict_items_skipped(self) -> None:
        """Non-dict items inside the list are silently skipped."""
        rules = _parse_filter_rules(["not-a-dict", {"kind": "semver"}])
        assert len(rules) == 1
        assert rules[0].kind == "semver"

    def test_multiple_rules_preserved_in_order(self) -> None:
        """Multiple rules are returned in declaration order."""
        raw = [
            {"kind": "prefix", "value": "audio/"},
            {"kind": "semver", "value": ""},
        ]
        rules = _parse_filter_rules(raw)
        assert [r.kind for r in rules] == ["prefix", "semver"]


# ---------------------------------------------------------------------------
# _parse_filters
# ---------------------------------------------------------------------------


class TestParseFilters:
    """Unit tests for _parse_filters."""

    def test_empty_dict_returns_empty(self) -> None:
        """An empty filter section produces an empty dict."""
        assert _parse_filters({}) == {}

    def test_non_dict_returns_empty(self) -> None:
        """A non-dict value produces an empty dict without raising."""
        assert _parse_filters(None) == {}  # type: ignore[arg-type]
        assert _parse_filters("bad") == {}  # type: ignore[arg-type]

    def test_single_filter_with_include_and_exclude(self) -> None:
        """A filter with both include and exclude lists is parsed correctly."""
        raw = {
            "my-filter": {
                "include": [{"kind": "prefix", "value": "v"}],
                "exclude": [{"kind": "regex", "value": r"-rc\d"}],
            }
        }
        result = _parse_filters(raw)
        assert "my-filter" in result
        cfg = result["my-filter"]
        assert isinstance(cfg, TagFilterConfig)
        assert len(cfg.include) == 1
        assert cfg.include[0].kind == "prefix"
        assert len(cfg.exclude) == 1
        assert cfg.exclude[0].kind == "regex"

    def test_filter_with_only_include(self) -> None:
        """A filter with only include rules has an empty exclude list."""
        raw = {"semver-only": {"include": [{"kind": "semver"}]}}
        result = _parse_filters(raw)
        assert result["semver-only"].exclude == []

    def test_filter_with_only_exclude(self) -> None:
        """A filter with only exclude rules has an empty include list."""
        raw = {"no-rc": {"exclude": [{"kind": "regex", "value": r"-rc\d"}]}}
        result = _parse_filters(raw)
        assert result["no-rc"].include == []

    def test_multiple_filters_all_present(self) -> None:
        """Multiple named filters are all present in the result dict."""
        raw = {
            "filter-a": {"include": [{"kind": "semver"}]},
            "filter-b": {"exclude": [{"kind": "prefix", "value": "dev"}]},
        }
        result = _parse_filters(raw)
        assert set(result.keys()) == {"filter-a", "filter-b"}

    def test_non_dict_filter_value_skipped(self) -> None:
        """A non-dict filter value is silently skipped."""
        raw = {"bad-filter": "not-a-dict", "good-filter": {"include": [{"kind": "semver"}]}}
        result = _parse_filters(raw)
        assert "bad-filter" not in result
        assert "good-filter" in result


# ---------------------------------------------------------------------------
# load_config — filter integration
# ---------------------------------------------------------------------------


class TestLoadConfigFilters:
    """Integration tests: filter blocks round-trip through load_config."""

    def test_no_filter_section_returns_empty_filters(self, tmp_path: Path) -> None:
        """A config without a [filter.*] section has an empty filters dict."""
        cfg_path = _write_toml(
            tmp_path,
            """
            [[source]]
            name = "vcpkg"
            strategy = "subfolders"
            url = "https://github.com/microsoft/vcpkg"
            """,
        )
        config = load_config(str(cfg_path))
        assert config.filters == {}

    def test_single_named_filter_loaded(self, tmp_path: Path) -> None:
        """A [filter.X] block is loaded and accessible by name."""
        cfg_path = _write_toml(
            tmp_path,
            """
            [[source]]
            name = "mono"
            strategy = "subfolders"
            url = "https://github.com/example/mono"
            filter = "monorepo"

            [filter.monorepo]
            include = [{kind = "prefix", value = "{{component}}/", case = "sensitive"}]
            exclude = [{kind = "regex", value = "-rc"}]
            """,
        )
        config = load_config(str(cfg_path))
        assert "monorepo" in config.filters
        flt = config.filters["monorepo"]
        assert len(flt.include) == 1
        assert flt.include[0].kind == "prefix"
        assert flt.include[0].value == "{{component}}/"
        assert flt.include[0].case == "sensitive"
        assert len(flt.exclude) == 1
        assert flt.exclude[0].kind == "regex"
        assert flt.exclude[0].value == "-rc"

    def test_source_filter_field_loaded(self, tmp_path: Path) -> None:
        """The 'filter' field of a [[source]] block is loaded into SourceConfig."""
        cfg_path = _write_toml(
            tmp_path,
            """
            [[source]]
            name = "mono"
            strategy = "subfolders"
            url = "https://github.com/example/mono"
            filter = "my-filter"

            [filter.my-filter]
            include = [{kind = "semver"}]
            """,
        )
        config = load_config(str(cfg_path))
        assert config.sources[0].filter == "my-filter"  # noqa: A003

    def test_multiple_named_filters_all_loaded(self, tmp_path: Path) -> None:
        """Multiple [filter.*] blocks are all loaded into HubConfig.filters."""
        cfg_path = _write_toml(
            tmp_path,
            """
            [[source]]
            name = "s1"
            strategy = "subfolders"
            url = "https://github.com/example/s1"

            [filter.semver-only]
            include = [{kind = "semver"}]

            [filter.no-rc]
            exclude = [{kind = "regex", value = "-rc"}]
            """,
        )
        config = load_config(str(cfg_path))
        assert set(config.filters.keys()) == {"semver-only", "no-rc"}
        assert config.filters["semver-only"].include[0].kind == "semver"
        assert config.filters["no-rc"].exclude[0].value == "-rc"

    def test_source_without_filter_field_defaults_to_empty_string(self, tmp_path: Path) -> None:
        """SourceConfig.filter defaults to empty string when not specified."""
        cfg_path = _write_toml(
            tmp_path,
            """
            [[source]]
            name = "plain"
            strategy = "subfolders"
            url = "https://github.com/example/plain"
            """,
        )
        config = load_config(str(cfg_path))
        assert config.sources[0].filter == ""  # noqa: A003

    def test_filter_rule_defaults(self, tmp_path: Path) -> None:
        """Rules with only 'kind' use default values for 'value' and 'case'."""
        cfg_path = _write_toml(
            tmp_path,
            """
            [[source]]
            name = "s"
            strategy = "subfolders"
            url = "https://github.com/example/s"

            [filter.defaults-test]
            include = [{kind = "semver"}]
            """,
        )
        config = load_config(str(cfg_path))
        rule = config.filters["defaults-test"].include[0]
        assert rule.value == ""
        assert rule.case == "smart"

    def test_hubconfig_is_hubconfig_instance(self, tmp_path: Path) -> None:
        """The returned object is a HubConfig with all expected attributes."""
        cfg_path = _write_toml(
            tmp_path,
            """
            [[source]]
            name = "s"
            strategy = "subfolders"
            url = "https://github.com/example/s"

            [filter.f]
            include = [{kind = "prefix", value = "v"}]
            """,
        )
        config = load_config(str(cfg_path))
        assert isinstance(config, HubConfig)
        assert isinstance(config.filters, dict)
        assert isinstance(config.filters["f"], TagFilterConfig)
        assert isinstance(config.filters["f"].include[0], FilterRuleConfig)


# ---------------------------------------------------------------------------
# _build_tag_filter (integration via update module)
# ---------------------------------------------------------------------------


def test_build_tag_filter_returns_none_without_filter_field() -> None:
    """_build_tag_filter returns None when SourceConfig.filter is empty."""
    from dfetch_hub.commands.update import _build_tag_filter  # noqa: PLC2701
    from dfetch_hub.config import SourceConfig

    source = SourceConfig(name="s", strategy="subfolders", url="https://example.com")
    assert _build_tag_filter(source, {}) is None


def test_build_tag_filter_warns_and_returns_none_for_missing_filter(caplog: pytest.LogCaptureFixture) -> None:
    """_build_tag_filter logs a warning and returns None when filter name is not in filters dict."""
    import logging

    from dfetch_hub.commands.update import _build_tag_filter  # noqa: PLC2701
    from dfetch_hub.config import SourceConfig

    source = SourceConfig(name="s", strategy="subfolders", url="https://example.com", filter="missing")
    with caplog.at_level(logging.WARNING):
        result = _build_tag_filter(source, {})
    assert result is None
    assert "missing" in caplog.text


def test_build_tag_filter_creates_filter_from_config() -> None:
    """_build_tag_filter converts TagFilterConfig into a usable TagFilter."""
    from dfetch_hub.catalog.tag_filter import CaseMode, TagFilter
    from dfetch_hub.commands.update import _build_tag_filter  # noqa: PLC2701
    from dfetch_hub.config import FilterRuleConfig, SourceConfig, TagFilterConfig

    source = SourceConfig(name="s", strategy="subfolders", url="https://example.com", filter="f")
    filters = {
        "f": TagFilterConfig(
            include=[FilterRuleConfig(kind="prefix", value="v", case="sensitive")],
            exclude=[FilterRuleConfig(kind="regex", value=r"-rc")],
        )
    }
    result = _build_tag_filter(source, filters)
    assert isinstance(result, TagFilter)
    assert len(result.include) == 1
    assert result.include[0].kind == "prefix"
    assert result.include[0].case == CaseMode.SENSITIVE
    assert len(result.exclude) == 1
    assert result.exclude[0].kind == "regex"
