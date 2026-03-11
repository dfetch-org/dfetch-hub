"""Tag filtering with smart normalization for per-component tag selection.

This module implements flexible tag filtering so that only the relevant version
tags are stored for each catalog component.  It is particularly useful for
monorepos, where many components share a single repository but use different
tagging conventions (``audio/v1.0``, ``VideoEncoder-2.3.0``, …).

The public API is:

* :class:`CaseMode` — how a tag string is normalized before comparison.
* :class:`FilterRule` — a single include or exclude rule.
* :class:`TagFilter` — a container of include / exclude rule lists.
* :func:`normalize_tag` — normalize a raw tag string for comparison.
* :func:`apply_tag_filter` — apply a :class:`TagFilter` to a list of tags.

The ``{{component}}`` placeholder inside rule values is replaced at match time
with the actual component name (e.g. the monorepo subfolder).  The final tag
objects returned by :func:`apply_tag_filter` always carry their *original* name
exactly as it appears in the repository.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dfetch_hub.catalog.model import Tag

# ---------------------------------------------------------------------------
# Regex constants (version sorting)
# ---------------------------------------------------------------------------

_VERSION_NUMBERS = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?")

# ---------------------------------------------------------------------------
# Regex constants
# ---------------------------------------------------------------------------

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SEPARATOR = re.compile(r"[-_\s.]+")
# Matches common version-tag semver patterns (v-prefix optional, patch optional).
_SEMVER = re.compile(
    r"^v?\d+\.\d+(\.\d+)?([.\-+][a-zA-Z0-9._+\-]*)?$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class CaseMode(StrEnum):
    """Case handling mode used when normalizing a tag for comparison.

    Attributes:
        SMART: Split CamelCase/PascalCase boundaries, strip all separators
            (hyphens, underscores, spaces, periods), then lowercase.
            ``LowPassFilter``, ``low-pass-filter``, ``low_pass_filter``,
            ``LOWPASSFILTER``, and ``lowPassFilter`` all collapse to the
            same token.
        INSENSITIVE: Lowercase only; separators are kept.
        SENSITIVE: No transformation; exact byte-level comparison.
        NORMALIZE_LOWER: Strip separators then lowercase (no CamelCase split).
        NORMALIZE_UPPER: Strip separators then uppercase (no CamelCase split).
    """

    SMART = "smart"
    INSENSITIVE = "insensitive"
    SENSITIVE = "sensitive"
    NORMALIZE_LOWER = "normalize-lower"
    NORMALIZE_UPPER = "normalize-upper"


@dataclass
class FilterRule:
    """A single include or exclude tag matching rule.

    Attributes:
        kind: Rule type — ``prefix``, ``regex``, or ``semver``.
        value: The pattern or prefix to match against. May contain the
            ``{{component}}`` placeholder which is substituted at match time.
        case: Normalization mode applied before comparison (ignored for
            ``semver`` rules which always validate the original tag string).
    """

    kind: str
    value: str
    case: CaseMode = CaseMode.SMART

    def matches(self, tag: str, component: str | None = None) -> bool:
        """Return ``True`` if this rule matches *tag*.

        For ``prefix`` rules both the tag and the prefix value are normalized
        using :attr:`case` before comparison so that the check is
        format-agnostic.  For ``regex`` rules the raw tag is tested (with
        ``re.IGNORECASE`` unless :attr:`case` is ``sensitive``).  For
        ``semver`` rules the raw tag is validated against a semver pattern.

        The ``{{component}}`` placeholder in :attr:`value` is replaced with
        *component* (or an empty string when *component* is ``None``) before
        any comparison is done.

        Args:
            tag: Raw tag string as it appears in the repository.
            component: Optional component name used for ``{{component}}``
                substitution.

        Returns:
            ``True`` when the rule matches, ``False`` otherwise.
        """
        value = self.value.replace("{{component}}", component or "")

        if self.kind == "prefix":
            return normalize_tag(tag, self.case).startswith(normalize_tag(value, self.case))
        if self.kind == "regex":
            flags = 0 if self.case == CaseMode.SENSITIVE else re.IGNORECASE
            return bool(re.search(value, tag, flags))
        if self.kind == "semver":
            return bool(_SEMVER.match(tag))
        return False


@dataclass
class TagFilter:
    """A tag filter composed of include and exclude rule lists.

    Tags pass the filter when *all* include rules match **and** *no* exclude
    rule matches.  An empty :attr:`include` list lets every tag through.

    Attributes:
        include: Rules that must *all* match for a tag to be kept.
        exclude: Rules where *any* match removes the tag.
    """

    include: list[FilterRule] = field(default_factory=list)
    exclude: list[FilterRule] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _normalize_strip_separators(tag: str, mode: CaseMode) -> str:
    """Strip separators then apply case for NORMALIZE_LOWER or NORMALIZE_UPPER."""
    stripped = _SEPARATOR.sub("", tag)
    return stripped.upper() if mode == CaseMode.NORMALIZE_UPPER else stripped.lower()


def normalize_tag(tag: str, mode: CaseMode = CaseMode.SMART) -> str:
    """Return a normalized form of *tag* suitable for comparison.

    The original tag string is never modified; this function returns a new
    string used only during filtering logic.

    Args:
        tag: The raw tag string to normalize.
        mode: The :class:`CaseMode` controlling the transformation.

    Returns:
        Normalized string for comparison purposes.
    """
    if mode == CaseMode.SENSITIVE:
        return tag
    if mode == CaseMode.INSENSITIVE:
        return tag.lower()
    if mode != CaseMode.SMART:
        return _normalize_strip_separators(tag, mode)
    # SMART: split CamelCase/PascalCase boundaries first, then strip separators, then lowercase
    split = _CAMEL_BOUNDARY.sub(" ", tag)
    return _SEPARATOR.sub("", split).lower()


def apply_tag_filter(
    tags: list[Tag],
    tag_filter: TagFilter,
    component: str | None = None,
) -> list[Tag]:
    """Filter *tags* using *tag_filter*, returning original :class:`Tag` objects.

    The filtering pipeline for each tag:

    1. Apply all include rules — the tag is kept only when *every* rule
       matches (an empty include list passes all tags).
    2. Apply all exclude rules — the tag is removed when *any* rule matches.

    Tag objects that survive both stages are appended to the result in their
    original form; the tag name is never modified.

    Args:
        tags: Sequence of :class:`~dfetch_hub.catalog.model.Tag` objects to
            filter.
        tag_filter: The :class:`TagFilter` containing include and exclude
            rules.
        component: Optional component name substituted for ``{{component}}``
            in rule values.

    Returns:
        A new list containing only the tags that pass the filter, preserving
        the original tag objects and their order.
    """
    result = []
    for tag in tags:
        name = tag.name
        if tag_filter.include and not all(r.matches(name, component) for r in tag_filter.include):
            continue
        if any(r.matches(name, component) for r in tag_filter.exclude):
            continue
        result.append(tag)
    return result


def _tag_sort_key(tag: Tag) -> tuple[int, str, tuple[int, ...]]:
    """Return a sort key for *tag* used by :func:`sort_tags_newest_first`."""
    if tag.date:
        return (1, tag.date, ())
    m = _VERSION_NUMBERS.match(tag.name)
    if m:
        nums: tuple[int, ...] = tuple(int(g) for g in m.groups() if g is not None)
        return (0, "", nums)
    return (-1, tag.name, ())


def sort_tags_newest_first(tags: list[Tag]) -> list[Tag]:
    """Return *tags* sorted newest-first.

    Sorting priority (highest priority first):

    1. Tags with a :attr:`~dfetch_hub.catalog.model.Tag.date` field — sorted
       by ISO date string descending (lexicographic order is correct for ISO dates).
    2. Tags without a date whose name starts with a numeric version prefix
       (``vX.Y.Z`` or ``X.Y.Z``) — sorted by version tuple descending.
    3. All remaining tags — sorted by name lexicographically descending.

    The original :class:`~dfetch_hub.catalog.model.Tag` objects are returned
    unchanged; tag names are never modified.

    Args:
        tags: Sequence of :class:`~dfetch_hub.catalog.model.Tag` objects to sort.

    Returns:
        A new list of the same tags ordered newest-first.
    """
    return sorted(tags, key=_tag_sort_key, reverse=True)
