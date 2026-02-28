"""Parse dfetch-hub.toml configuration."""

from __future__ import annotations

from dataclasses import dataclass, field

import tomllib


@dataclass
class SourceConfig:
    """A single ``[[source]]`` block from *dfetch-hub.toml*.

    Attributes:
        name:     Unique name for this source.
        strategy: Discovery strategy (``subfolders``, ``single``, …).
        url:      URL of the remote repository or registry.
        path:     Subfolder inside the remote repo to fetch (e.g. ``ports``).
        manifest: Manifest filename inside each subfolder (e.g. ``vcpkg.json``).
        label:    Tag added to every component found here.
        branch:   Branch to fetch; auto-detected from the remote when empty.

    """

    name: str
    strategy: str
    url: str
    path: str = ""
    manifest: str = ""
    label: str = ""
    branch: str = ""


@dataclass
class Settings:
    """``[settings]`` block from *dfetch-hub.toml*.

    Attributes:
        concurrency:  Number of parallel HTTP/git fetches.
        catalog_path: Where to write the generated catalog JSON.
        output_dir:   Directory for generated site artefacts.

    """

    concurrency: int = 8
    catalog_path: str = ".dfetch-hub/catalog.json"
    output_dir: str = "site"


@dataclass
class HubConfig:
    """Fully parsed *dfetch-hub.toml*.

    Attributes:
        settings: Global settings block.
        sources:  All ``[[source]]`` blocks, in declaration order.

    """

    settings: Settings = field(default_factory=Settings)
    sources: list[SourceConfig] = field(default_factory=list)


_SOURCE_FIELDS: frozenset[str] = frozenset(SourceConfig.__dataclass_fields__)
_SETTINGS_FIELDS: frozenset[str] = frozenset(Settings.__dataclass_fields__)


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

    """
    with open(path, "rb") as fh:
        data = tomllib.load(fh)

    raw_settings = {
        k: v for k, v in data.get("settings", {}).items() if k in _SETTINGS_FIELDS
    }
    settings = Settings(**raw_settings)

    sources: list[SourceConfig] = [
        SourceConfig(**{k: v for k, v in raw.items() if k in _SOURCE_FIELDS})
        for raw in data.get("source", [])
    ]

    return HubConfig(settings=settings, sources=sources)
