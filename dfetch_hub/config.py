"""Parse dfetch-hub.toml configuration."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class FilterRuleConfig:
    """A single include or exclude rule inside a ``[filter.*]`` block.

    Attributes:
        kind: Rule type — ``prefix``, ``regex``, or ``semver``.
        value: Pattern or prefix to match; may contain ``{{component}}``.
        case: Normalization mode — ``smart`` (default), ``insensitive``,
            ``sensitive``, ``normalize-lower``, or ``normalize-upper``.
    """

    kind: str
    value: str = ""
    case: str = "smart"


@dataclass
class TagFilterConfig:
    """A named tag filter defined in a ``[filter.*]`` block.

    Attributes:
        include: Rules that must *all* match for a tag to be kept.
        exclude: Rules where *any* match causes a tag to be dropped.
    """

    include: list[FilterRuleConfig] = field(default_factory=list)
    exclude: list[FilterRuleConfig] = field(default_factory=list)


@dataclass
class SourceConfig:  # pylint: disable=too-many-instance-attributes
    """A single ``[[source]]`` block from *dfetch-hub.toml*.

    Attributes:
        name:              Unique name for this source.
        strategy:          Discovery strategy (``subfolders``, ``catalog-file``).
        url:               URL of the remote repository or registry.
        path:              Subfolder inside the remote repo to fetch (e.g. ``ports``).
        manifest:          Manifest filename inside each subfolder (e.g. ``vcpkg.json``).
        label:             Tag added to every component found here.
        branch:            Branch to fetch; auto-detected from the remote when empty.
        ignore_if_present: Skip any subfolder that contains a file with this name
                           (e.g. ``.dfetch_data.yaml``).  Empty string disables filtering.
        filter:            Name of a ``[filter.*]`` block to apply when selecting tags
                           for components from this source.  Empty string disables
                           tag filtering.

    """

    name: str
    strategy: str
    url: str
    path: str = ""
    manifest: str = ""
    label: str = ""
    branch: str = ""
    ignore_if_present: str = ""
    filter: str = ""


@dataclass
class Settings:
    """``[settings]`` block from *dfetch-hub.toml*.

    Attributes:
        concurrency:  Number of parallel HTTP/git fetches.
        catalog_path: Where to write the generated catalog JSON.
        output_dir:   Directory for generated site artefacts.

    """

    concurrency: int = 8
    catalog_path: str = ""
    output_dir: str = "site"


@dataclass
class HubConfig:
    """Fully parsed *dfetch-hub.toml*.

    Attributes:
        settings: Global settings block.
        sources:  All ``[[source]]`` blocks, in declaration order.
        filters:  Named tag filters from ``[filter.*]`` blocks, keyed by name.

    """

    settings: Settings = field(default_factory=Settings)
    sources: list[SourceConfig] = field(default_factory=list)
    filters: dict[str, TagFilterConfig] = field(default_factory=dict)


_SOURCE_FIELDS: frozenset[str] = frozenset(f.name for f in fields(SourceConfig))
_SETTINGS_FIELDS: frozenset[str] = frozenset(f.name for f in fields(Settings))
_FILTER_RULE_FIELDS: frozenset[str] = frozenset(f.name for f in fields(FilterRuleConfig))


def _parse_filter_rules(raw_rules: object) -> list[FilterRuleConfig]:
    """Parse a list of raw rule dicts into :class:`FilterRuleConfig` objects.

    Unknown keys in each rule are silently ignored.

    Args:
        raw_rules: The raw value from the TOML table; expected to be a list
            of dicts.

    Returns:
        List of :class:`FilterRuleConfig` instances.
    """
    if not isinstance(raw_rules, list):
        return []
    return [
        FilterRuleConfig(**{k: v for k, v in r.items() if k in _FILTER_RULE_FIELDS})
        for r in raw_rules
        if isinstance(r, dict) and "kind" in r
    ]


def _parse_filters(raw_filters_obj: object) -> dict[str, TagFilterConfig]:
    """Parse the ``[filter.*]`` section into a dict of :class:`TagFilterConfig`.

    Args:
        raw_filters_obj: The raw ``filter`` value from the top-level TOML dict.
            Expected to be a dict mapping filter names to tables with optional
            ``include`` and ``exclude`` keys.

    Returns:
        Dict mapping filter name to :class:`TagFilterConfig`.
    """
    if not isinstance(raw_filters_obj, dict):
        return {}
    result: dict[str, TagFilterConfig] = {}
    for name, raw_filter in raw_filters_obj.items():
        if not isinstance(raw_filter, dict):
            continue
        result[name] = TagFilterConfig(
            include=_parse_filter_rules(raw_filter.get("include", [])),
            exclude=_parse_filter_rules(raw_filter.get("exclude", [])),
        )
    return result


def load_config(path: str = "dfetch-hub.toml") -> HubConfig:
    """Load and parse a *dfetch-hub.toml* file.

    Unknown keys in ``[settings]`` and ``[[source]]`` blocks are silently
    ignored so that future config additions don't break older code.

    Args:
        path: Filesystem path to the TOML file.

    Returns:
        A fully populated :class:`HubConfig`.

    Raises:
        FileNotFoundError: If *path* does not exist.
        tomllib.TOMLDecodeError: If the file is not valid TOML.
        TypeError: If ``[settings]`` is not a TOML table, or if ``[[source]]``
            is not an array of TOML tables.

    """
    with Path(path).open("rb") as fh:
        data = tomllib.load(fh)

    raw_settings_obj = data.get("settings", {})
    if not isinstance(raw_settings_obj, dict):
        raise TypeError("`[settings]` must be a TOML table")

    raw_sources_obj = data.get("source", [])
    if not isinstance(raw_sources_obj, list) or any(not isinstance(raw, dict) for raw in raw_sources_obj):
        raise TypeError("`[[source]]` must be an array of TOML tables")

    raw_settings = {k: v for k, v in raw_settings_obj.items() if k in _SETTINGS_FIELDS}
    settings = Settings(**raw_settings)

    sources: list[SourceConfig] = [
        SourceConfig(**{k: v for k, v in raw.items() if k in _SOURCE_FIELDS}) for raw in raw_sources_obj
    ]

    filters = _parse_filters(data.get("filter", {}))

    return HubConfig(settings=settings, sources=sources, filters=filters)
