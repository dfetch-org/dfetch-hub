"""Tag and source data models for the catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VCSLocation:
    """Represents a VCS repository location.

    Attributes:
        host: The VCS host label (e.g., "github", "gitlab").
        org: The organization/owner name.
        repo: The repository name.
        subpath: Optional subpath for monorepo components.
    """

    host: str
    org: str
    repo: str
    subpath: str | None = None

    @property
    def catalog_id(self) -> str:
        """Return the catalog ID for this location."""
        base = f"{self.host.lower()}/{self.org.lower()}/{self.repo.lower()}"
        return f"{base}/{self.subpath.lower()}" if self.subpath else base


@dataclass
class GitRefs:
    """Represents git references (tags and branches) from a repository."""

    tags: list[Tag] = field(default_factory=list)
    branches: list[Tag] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a dict representation of this GitRefs."""
        return {
            "tags": [t.to_dict() for t in self.tags],
            "branches": [t.to_dict() for t in self.branches],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GitRefs:
        """Create a GitRefs from a dict."""
        return cls(
            tags=[Tag.from_dict(t) for t in data.get("tags", [])],
            branches=[Tag.from_dict(t) for t in data.get("branches", [])],
        )


@dataclass
class PackageContent:
    """Represents package content fetched from the repository.

    Attributes:
        readme: Raw README text.
        license_text: Full license text, or ``None`` if unavailable.
        changelog: Raw CHANGELOG text, or ``None`` if unavailable.
    """

    readme: str = ""
    license_text: str | None = None
    changelog: str | None = None


@dataclass
class FetchMetadata:
    """Represents metadata about when the package was fetched."""

    fetched_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a dict representation."""
        return {"fetched_at": self.fetched_at}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FetchMetadata:
        """Create from dict."""
        return cls(fetched_at=data.get("fetched_at", ""))


@dataclass
class Tag:
    """Represents a Git tag or branch reference from a remote repository.

    Tags identify specific versions (e.g., "v1.2.3") while branches track lines
    of development. Both are fetched via ``git ls-remote`` when updating the catalog.
    """

    name: str
    is_tag: bool = True
    commit_sha: str | None = None
    date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a dict representation of this Tag."""
        return {
            "name": self.name,
            "is_tag": self.is_tag,
            "commit_sha": self.commit_sha,
            "date": self.date,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tag:
        """Create a Tag from a dict."""
        return cls(
            name=data.get("name", ""),
            is_tag=data.get("is_tag", True),
            commit_sha=data.get("commit_sha"),
            date=data.get("date"),
        )


@dataclass
class CatalogSource:
    """Represents a package source within a project's detail JSON.

    Each library can be available from multiple package managers (vcpkg, Conan, clib, etc.).
    This tracks which sources include the library and where their registry entry lives.
    """

    source_name: str
    label: str
    index_path: str
    registry_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a dict representation of this CatalogSource."""
        return {
            "source_name": self.source_name,
            "label": self.label,
            "index_path": self.index_path,
            "registry_version": self.registry_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogSource:
        """Create a CatalogSource from a dict."""
        return cls(
            source_name=data.get("source_name", ""),
            label=data.get("label", ""),
            index_path=data.get("index_path", ""),
            registry_version=data.get("registry_version"),
        )
