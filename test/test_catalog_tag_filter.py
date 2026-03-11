"""Tests for dfetch_hub.catalog.tag_filter."""

from __future__ import annotations

import pytest

from dfetch_hub.catalog.model import Tag
from dfetch_hub.catalog.tag_filter import (
    CaseMode,
    FilterRule,
    TagFilter,
    apply_tag_filter,
    normalize_tag,
    sort_tags_newest_first,
)

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_TAG_NAMES_CAMEL = [
    "LowPassFilter",
    "low-pass-filter",
    "low_pass_filter",
    "LOWPASSFILTER",
    "lowPassFilter",
]

_SEMVER_VALID = ["v1.0.0", "1.2.3", "v0.1.0-beta.1", "2.0.0+build.42", "v1.2"]
_SEMVER_INVALID = ["latest", "main", "dev", "rc1", "20240101", "foo-bar"]


def _make_tag(name: str) -> Tag:
    """Return a minimal Tag with the given name."""
    return Tag(name=name, is_tag=True)


def _make_tags(*names: str) -> list[Tag]:
    """Return a list of Tags from a sequence of name strings."""
    return [_make_tag(n) for n in names]


# ---------------------------------------------------------------------------
# normalize_tag — smart (default)
# ---------------------------------------------------------------------------


class TestNormalizeTagSmart:
    """normalize_tag with CaseMode.SMART collapses format differences."""

    @pytest.mark.parametrize("raw", _TAG_NAMES_CAMEL)
    def test_all_camel_variants_produce_same_token(self, raw: str) -> None:
        """All common formatting variants of the same name normalize identically."""
        assert normalize_tag(raw, CaseMode.SMART) == "lowpassfilter"

    def test_version_prefix_preserved_in_token(self) -> None:
        """Version prefix v is kept but lowercased."""
        assert normalize_tag("v1.2.3", CaseMode.SMART) == "v123"

    def test_version_with_separators(self) -> None:
        """Dots and hyphens in version tags are stripped by SMART mode."""
        assert normalize_tag("1.2.3-beta", CaseMode.SMART) == "123beta"

    def test_purely_lowercase_unchanged(self) -> None:
        """Already-lowercase strings with no separators are returned as-is."""
        assert normalize_tag("zlib", CaseMode.SMART) == "zlib"

    def test_multiple_separators_collapsed(self) -> None:
        """Consecutive separators are treated as a single boundary."""
        assert normalize_tag("foo--bar__baz", CaseMode.SMART) == "foobarbaz"


# ---------------------------------------------------------------------------
# normalize_tag — insensitive
# ---------------------------------------------------------------------------


class TestNormalizeTagInsensitive:
    """CaseMode.INSENSITIVE lowercases without removing separators."""

    def test_uppercase_lowercased(self) -> None:
        """Uppercase letters become lowercase."""
        assert normalize_tag("FooBar", CaseMode.INSENSITIVE) == "foobar"

    def test_separators_preserved(self) -> None:
        """Hyphens and underscores are NOT stripped."""
        assert normalize_tag("foo-bar_baz", CaseMode.INSENSITIVE) == "foo-bar_baz"

    def test_mixed_case_version(self) -> None:
        """Version strings are just lowercased."""
        assert normalize_tag("V1.2.3", CaseMode.INSENSITIVE) == "v1.2.3"


# ---------------------------------------------------------------------------
# normalize_tag — sensitive
# ---------------------------------------------------------------------------


class TestNormalizeTagSensitive:
    """CaseMode.SENSITIVE returns the string unchanged."""

    @pytest.mark.parametrize("raw", ["FooBar", "foo-bar", "v1.2.3", "UPPER"])
    def test_returns_unchanged(self, raw: str) -> None:
        """Tag is returned byte-for-byte identical."""
        assert normalize_tag(raw, CaseMode.SENSITIVE) == raw


# ---------------------------------------------------------------------------
# normalize_tag — normalize-lower / normalize-upper
# ---------------------------------------------------------------------------


class TestNormalizeTagNormalizeLower:
    """CaseMode.NORMALIZE_LOWER strips separators then lowercases."""

    def test_strips_and_lowercases(self) -> None:
        """Separators removed, result lowercased (no CamelCase split)."""
        assert normalize_tag("Low-Pass_Filter", CaseMode.NORMALIZE_LOWER) == "lowpassfilter"

    def test_camelcase_not_split(self) -> None:
        """CamelCase words are NOT split — letters stay concatenated."""
        assert normalize_tag("LowPassFilter", CaseMode.NORMALIZE_LOWER) == "lowpassfilter"


class TestNormalizeTagNormalizeUpper:
    """CaseMode.NORMALIZE_UPPER strips separators then uppercases."""

    def test_strips_and_uppercases(self) -> None:
        """Separators removed, result uppercased."""
        assert normalize_tag("foo-bar_baz", CaseMode.NORMALIZE_UPPER) == "FOOBARBAZ"

    def test_version_uppercased(self) -> None:
        """Version strings are uppercased."""
        assert normalize_tag("v1.2.3", CaseMode.NORMALIZE_UPPER) == "V123"


# ---------------------------------------------------------------------------
# FilterRule — prefix
# ---------------------------------------------------------------------------


class TestFilterRulePrefixSmart:
    """Prefix rule with default SMART case normalization."""

    @pytest.mark.parametrize(
        "tag",
        [
            "audio/v1.0.0",
            "audio/2.3.0",
            "audio/latest",
        ],
    )
    def test_matches_prefix(self, tag: str) -> None:
        """Tags beginning with the normalized prefix pass the rule."""
        rule = FilterRule(kind="prefix", value="audio/", case=CaseMode.SENSITIVE)
        assert rule.matches(tag) is True

    def test_no_match_different_component(self) -> None:
        """Tags for a different component do not match."""
        rule = FilterRule(kind="prefix", value="audio/", case=CaseMode.SENSITIVE)
        assert rule.matches("video/v1.0.0") is False

    def test_smart_normalizes_both_sides(self) -> None:
        """SMART mode normalizes both tag and prefix before comparing."""
        rule = FilterRule(kind="prefix", value="LowPass", case=CaseMode.SMART)
        assert rule.matches("low-pass-filter-v1") is True

    def test_prefix_component_placeholder(self) -> None:
        """{{component}} is substituted with the component name."""
        rule = FilterRule(kind="prefix", value="{{component}}/", case=CaseMode.SENSITIVE)
        assert rule.matches("audio/v1.0.0", component="audio") is True
        assert rule.matches("video/v1.0.0", component="audio") is False

    def test_placeholder_empty_when_no_component(self) -> None:
        """When component=None the placeholder becomes an empty string."""
        rule = FilterRule(kind="prefix", value="{{component}}", case=CaseMode.SENSITIVE)
        # Any tag starts with "" so all should match
        assert rule.matches("anything") is True

    def test_insensitive_case(self) -> None:
        """INSENSITIVE mode lowercases both sides."""
        rule = FilterRule(kind="prefix", value="V", case=CaseMode.INSENSITIVE)
        assert rule.matches("v1.0.0") is True
        assert rule.matches("V2.0.0") is True
        assert rule.matches("1.0.0") is False


# ---------------------------------------------------------------------------
# FilterRule — regex
# ---------------------------------------------------------------------------


class TestFilterRuleRegex:
    """Regex rule matching behaviour."""

    def test_simple_regex_match(self) -> None:
        """A matching regex returns True."""
        rule = FilterRule(kind="regex", value=r"^\d+\.\d+\.\d+$")
        assert rule.matches("1.2.3") is True

    def test_simple_regex_no_match(self) -> None:
        """A non-matching regex returns False."""
        rule = FilterRule(kind="regex", value=r"^\d+\.\d+\.\d+$")
        assert rule.matches("latest") is False

    def test_regex_case_insensitive_by_default(self) -> None:
        """Non-sensitive modes apply IGNORECASE to the regex."""
        rule = FilterRule(kind="regex", value=r"^v\d", case=CaseMode.INSENSITIVE)
        assert rule.matches("V1.0.0") is True

    def test_regex_case_sensitive(self) -> None:
        """SENSITIVE mode does not apply IGNORECASE."""
        rule = FilterRule(kind="regex", value=r"^v\d")
        rule.case = CaseMode.SENSITIVE
        assert rule.matches("V1.0.0") is False
        assert rule.matches("v1.0.0") is True

    def test_regex_component_placeholder(self) -> None:
        """{{component}} is substituted in the regex pattern."""
        rule = FilterRule(kind="regex", value=r"^{{component}}-", case=CaseMode.SENSITIVE)
        assert rule.matches("audio-v1.0", component="audio") is True
        assert rule.matches("video-v1.0", component="audio") is False


# ---------------------------------------------------------------------------
# FilterRule — semver
# ---------------------------------------------------------------------------


class TestFilterRuleSemver:
    """Semver rule validates tags against a semver pattern."""

    @pytest.mark.parametrize("tag", _SEMVER_VALID)
    def test_valid_semver_matches(self, tag: str) -> None:
        """Valid semver tags match the semver rule."""
        rule = FilterRule(kind="semver", value="")
        assert rule.matches(tag) is True

    @pytest.mark.parametrize("tag", _SEMVER_INVALID)
    def test_invalid_semver_does_not_match(self, tag: str) -> None:
        """Non-semver tags do not match the semver rule."""
        rule = FilterRule(kind="semver", value="")
        assert rule.matches(tag) is False

    def test_case_field_ignored_for_semver(self) -> None:
        """The case field has no effect on semver validation."""
        rule_smart = FilterRule(kind="semver", value="", case=CaseMode.SMART)
        rule_sensitive = FilterRule(kind="semver", value="", case=CaseMode.SENSITIVE)
        assert rule_smart.matches("v1.2.3") == rule_sensitive.matches("v1.2.3")


# ---------------------------------------------------------------------------
# FilterRule — unknown kind
# ---------------------------------------------------------------------------


def test_filter_rule_unknown_kind_returns_false() -> None:
    """An unrecognised rule kind never matches."""
    rule = FilterRule(kind="unknown", value="anything")
    assert rule.matches("v1.0.0") is False


# ---------------------------------------------------------------------------
# apply_tag_filter — include rules
# ---------------------------------------------------------------------------


class TestApplyTagFilterInclude:
    """Include rules: all must match for a tag to be kept."""

    def test_no_include_rules_passes_all(self) -> None:
        """An empty include list passes every tag unchanged."""
        tags = _make_tags("v1.0.0", "latest", "main")
        result = apply_tag_filter(tags, TagFilter())
        assert [t.name for t in result] == ["v1.0.0", "latest", "main"]

    def test_single_prefix_include(self) -> None:
        """Only tags matching the prefix rule are kept."""
        tags = _make_tags("audio/v1.0", "video/v1.0", "audio/v2.0")
        filt = TagFilter(include=[FilterRule(kind="prefix", value="audio/", case=CaseMode.SENSITIVE)])
        result = apply_tag_filter(tags, filt)
        assert [t.name for t in result] == ["audio/v1.0", "audio/v2.0"]

    def test_single_semver_include(self) -> None:
        """Non-semver tags are filtered out when a semver rule is in include."""
        tags = _make_tags("v1.0.0", "latest", "main", "2.3.4")
        filt = TagFilter(include=[FilterRule(kind="semver", value="")])
        result = apply_tag_filter(tags, filt)
        assert [t.name for t in result] == ["v1.0.0", "2.3.4"]

    def test_multiple_include_rules_all_must_match(self) -> None:
        """A tag is kept only when ALL include rules match."""
        tags = _make_tags("v1.0.0", "latest", "v2.0.0-rc1", "1.2.3")
        filt = TagFilter(
            include=[
                FilterRule(kind="prefix", value="v", case=CaseMode.SENSITIVE),
                FilterRule(kind="semver", value=""),
            ]
        )
        result = apply_tag_filter(tags, filt)
        # "v1.0.0" starts with "v" AND is semver → kept
        # "latest" does NOT start with "v" → excluded by prefix rule
        # "v2.0.0-rc1" starts with "v" AND is semver → kept
        # "1.2.3" is semver but does NOT start with "v" → excluded by prefix rule
        assert [t.name for t in result] == ["v1.0.0", "v2.0.0-rc1"]

    def test_component_placeholder_in_include(self) -> None:
        """{{component}} is substituted with the component name in include rules."""
        tags = _make_tags("audio/v1.0", "video/v1.0", "audio/v2.0")
        filt = TagFilter(include=[FilterRule(kind="prefix", value="{{component}}/", case=CaseMode.SENSITIVE)])
        result = apply_tag_filter(tags, filt, component="audio")
        assert [t.name for t in result] == ["audio/v1.0", "audio/v2.0"]

    def test_original_tag_objects_returned_unchanged(self) -> None:
        """Returned Tag objects are the same instances; names are unmodified."""
        tag = _make_tag("Audio-Component/v1.0")
        filt = TagFilter(include=[FilterRule(kind="prefix", value="audio", case=CaseMode.SMART)])
        result = apply_tag_filter([tag], filt)
        assert len(result) == 1
        assert result[0] is tag
        assert result[0].name == "Audio-Component/v1.0"


# ---------------------------------------------------------------------------
# apply_tag_filter — exclude rules
# ---------------------------------------------------------------------------


class TestApplyTagFilterExclude:
    """Exclude rules: any match removes the tag."""

    def test_single_exclude_removes_matching(self) -> None:
        """Tags matching the exclude rule are removed."""
        tags = _make_tags("v1.0.0", "v1.0.0-rc1", "v2.0.0-alpha", "v3.0.0")
        filt = TagFilter(exclude=[FilterRule(kind="regex", value=r"-(rc|alpha|beta)")])
        result = apply_tag_filter(tags, filt)
        assert [t.name for t in result] == ["v1.0.0", "v3.0.0"]

    def test_multiple_exclude_rules_any_removes(self) -> None:
        """A tag is removed when ANY exclude rule matches."""
        tags = _make_tags("v1.0.0", "v1.0.0-rc1", "latest", "v2.0.0")
        filt = TagFilter(
            exclude=[
                FilterRule(kind="regex", value=r"-rc\d"),
                FilterRule(kind="regex", value=r"^latest$"),
            ]
        )
        result = apply_tag_filter(tags, filt)
        assert [t.name for t in result] == ["v1.0.0", "v2.0.0"]

    def test_empty_exclude_keeps_all(self) -> None:
        """No exclude rules means all tags pass through."""
        tags = _make_tags("v1.0.0", "latest", "main")
        filt = TagFilter(exclude=[])
        result = apply_tag_filter(tags, filt)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# apply_tag_filter — combined include + exclude
# ---------------------------------------------------------------------------


class TestApplyTagFilterCombined:
    """Include and exclude rules work together in the pipeline."""

    def test_include_then_exclude(self) -> None:
        """Include narrows the set; exclude removes pre-release tags from it."""
        tags = _make_tags(
            "audio/v1.0.0",
            "audio/v2.0.0-rc1",
            "video/v1.0.0",
            "audio/v3.0.0",
            "audio/latest",
        )
        filt = TagFilter(
            include=[FilterRule(kind="prefix", value="{{component}}/", case=CaseMode.SENSITIVE)],
            exclude=[FilterRule(kind="regex", value=r"-(rc|alpha|beta)")],
        )
        result = apply_tag_filter(tags, filt, component="audio")
        # Include keeps only audio/* tags: audio/v1.0.0, audio/v2.0.0-rc1, audio/v3.0.0, audio/latest
        # Exclude removes -rc tags: audio/v2.0.0-rc1 dropped
        assert [t.name for t in result] == ["audio/v1.0.0", "audio/v3.0.0", "audio/latest"]

    def test_empty_filter_passes_everything(self) -> None:
        """A TagFilter with no rules passes all tags."""
        tags = _make_tags("v1.0.0", "latest", "main", "dev")
        result = apply_tag_filter(tags, TagFilter())
        assert len(result) == 4

    def test_no_tags_returns_empty_list(self) -> None:
        """Filtering an empty list returns an empty list."""
        filt = TagFilter(include=[FilterRule(kind="prefix", value="v")])
        assert apply_tag_filter([], filt) == []

    def test_all_tags_excluded_returns_empty_list(self) -> None:
        """When all tags are excluded the result is an empty list."""
        tags = _make_tags("v1.0.0", "v2.0.0")
        filt = TagFilter(exclude=[FilterRule(kind="regex", value=r".*")])
        assert apply_tag_filter(tags, filt) == []


# ---------------------------------------------------------------------------
# apply_tag_filter — smart normalization across formats
# ---------------------------------------------------------------------------


class TestSmartNormalizationEndToEnd:
    """Smart normalization makes CamelCase / kebab / snake / UPPER all comparable."""

    @pytest.mark.parametrize("prefix_value", _TAG_NAMES_CAMEL)
    def test_prefix_matches_any_format_variant(self, prefix_value: str) -> None:
        """A prefix written in any format matches tags in all other formats."""
        tags = _make_tags(*_TAG_NAMES_CAMEL)
        filt = TagFilter(include=[FilterRule(kind="prefix", value=prefix_value, case=CaseMode.SMART)])
        result = apply_tag_filter(tags, filt)
        # All five variants should match the normalized prefix
        assert len(result) == len(_TAG_NAMES_CAMEL)

    def test_semver_not_affected_by_smart_normalization(self) -> None:
        """Semver validation always works on the original tag, not normalized form."""
        rule = FilterRule(kind="semver", value="", case=CaseMode.SMART)
        assert rule.matches("v1.2.3") is True
        assert rule.matches("latest") is False


# ---------------------------------------------------------------------------
# sort_tags_newest_first
# ---------------------------------------------------------------------------


def _make_dated_tag(name: str, date: str) -> Tag:
    """Return a Tag with an ISO date string set."""
    return Tag(name=name, is_tag=True, date=date)


class TestSortTagsNewestFirst:
    """sort_tags_newest_first orders tags from newest to oldest."""

    def test_empty_list_returns_empty(self) -> None:
        """An empty input returns an empty list."""
        assert sort_tags_newest_first([]) == []

    def test_single_tag_returned_unchanged(self) -> None:
        """A single tag is returned as-is."""
        tags = _make_tags("v1.0.0")
        result = sort_tags_newest_first(tags)
        assert [t.name for t in result] == ["v1.0.0"]

    def test_semver_tags_sorted_highest_first(self) -> None:
        """Version tags are sorted by numeric tuple, newest first."""
        tags = _make_tags("v1.0.0", "v3.0.0", "v2.1.0", "v2.0.0")
        result = sort_tags_newest_first(tags)
        assert [t.name for t in result] == ["v3.0.0", "v2.1.0", "v2.0.0", "v1.0.0"]

    def test_semver_without_v_prefix(self) -> None:
        """Version tags without 'v' prefix are still sorted by version."""
        tags = _make_tags("1.0.0", "2.0.0", "1.5.0")
        result = sort_tags_newest_first(tags)
        assert [t.name for t in result] == ["2.0.0", "1.5.0", "1.0.0"]

    def test_patch_version_ordering(self) -> None:
        """Patch version differences are respected."""
        tags = _make_tags("v1.0.3", "v1.0.1", "v1.0.10", "v1.0.2")
        result = sort_tags_newest_first(tags)
        assert [t.name for t in result] == ["v1.0.10", "v1.0.3", "v1.0.2", "v1.0.1"]

    def test_dated_tags_sorted_by_date_descending(self) -> None:
        """Tags with dates are sorted newest date first."""
        tags = [
            _make_dated_tag("release-old", "2022-01-01T00:00:00"),
            _make_dated_tag("release-new", "2024-06-15T12:00:00"),
            _make_dated_tag("release-mid", "2023-03-10T00:00:00"),
        ]
        result = sort_tags_newest_first(tags)
        assert [t.name for t in result] == ["release-new", "release-mid", "release-old"]

    def test_dated_tags_come_before_semver_tags(self) -> None:
        """Tags with dates sort before tags without dates."""
        tags = [
            _make_tag("v99.0.0"),
            _make_dated_tag("v1.0.0", "2024-01-01T00:00:00"),
        ]
        result = sort_tags_newest_first(tags)
        assert result[0].name == "v1.0.0"
        assert result[1].name == "v99.0.0"

    def test_non_version_tags_sorted_lexicographically_last(self) -> None:
        """Tags that are neither dated nor version-formatted come last, sorted lexicographically descending."""
        tags = _make_tags("latest", "main", "stable")
        result = sort_tags_newest_first(tags)
        assert [t.name for t in result] == ["stable", "main", "latest"]

    def test_mixed_version_and_non_version(self) -> None:
        """Version tags appear before non-version tags."""
        tags = _make_tags("latest", "v2.0.0", "main", "v1.0.0")
        result = sort_tags_newest_first(tags)
        assert result[0].name == "v2.0.0"
        assert result[1].name == "v1.0.0"
        assert "latest" in [t.name for t in result[2:]]
        assert "main" in [t.name for t in result[2:]]

    def test_original_tag_objects_returned(self) -> None:
        """The returned list contains the same Tag objects, not copies."""
        tags = _make_tags("v2.0.0", "v1.0.0")
        result = sort_tags_newest_first(tags)
        assert result[0] is tags[0] or result[0] is tags[1]  # same object references

    def test_two_digit_minor_version_ordering(self) -> None:
        """Minor version numbers >9 are sorted numerically, not lexicographically."""
        tags = _make_tags("v1.9.0", "v1.10.0", "v1.2.0")
        result = sort_tags_newest_first(tags)
        assert [t.name for t in result] == ["v1.10.0", "v1.9.0", "v1.2.0"]
