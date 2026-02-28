"""Parse dfetch-hub.toml configuration."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class SourceConfig:
    """A single [[source]] block from dfetch-hub.toml."""

    name: str
    strategy: str
    url: str
    path: str = ""       # subfolder inside the remote repo (e.g. "ports")
    manifest: str = ""   # manifest file inside each subfolder (e.g. "vcpkg.json")
    label: str = ""
    branch: str = ""     # explicit branch; if empty, auto-detected from remote


@dataclass
class Settings:
    """[settings] block from dfetch-hub.toml."""

    concurrency: int = 8
    catalog_path: str = ".dfetch-hub/catalog.json"
    output_dir: str = "site"


@dataclass
class HubConfig:
    """Parsed dfetch-hub.toml."""

    settings: Settings = field(default_factory=Settings)
    sources: List[SourceConfig] = field(default_factory=list)


_SOURCE_FIELDS = {f for f in SourceConfig.__dataclass_fields__}
_SETTINGS_FIELDS = {f for f in Settings.__dataclass_fields__}


def load_config(path: str = "dfetch-hub.toml") -> HubConfig:
    """Load and parse dfetch-hub.toml."""
    with open(path, "rb") as fh:
        data = tomllib.load(fh)

    raw_settings = {k: v for k, v in data.get("settings", {}).items() if k in _SETTINGS_FIELDS}
    settings = Settings(**raw_settings)

    sources: List[SourceConfig] = []
    for raw in data.get("source", []):
        kwargs = {k: v for k, v in raw.items() if k in _SOURCE_FIELDS}
        sources.append(SourceConfig(**kwargs))

    return HubConfig(settings=settings, sources=sources)
