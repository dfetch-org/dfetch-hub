"""Catalog entry data model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from dfetch_hub.catalog.model import Tag, VCSLocation

if TYPE_CHECKING:
    from dfetch_hub.catalog.sources import BaseManifest


class CatalogEntry:  # pylint: disable=too-many-instance-attributes,too-many-locals
    """Represents a single library in the catalog.json index.

    Each entry describes a library available from one or more package sources.
    The catalog ID (e.g., "github/abseil/abseil-cpp") uniquely identifies it.
    For monorepos, subpaths are included: "github/org/monorepo/mylib".
    """

    VCS_HOST_ALIASES: ClassVar[dict[str, str]] = {
        "github.com": "github",
        "gitlab.com": "gitlab",
        "bitbucket.org": "bitbucket",
    }

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        cat_id: str = "",
        name: str = "",
        description: str | None = None,
        url: str = "",
        source_type: str = "github",
        default_branch: str = "main",
        license_str: str | None = None,
        topics: list[str] | None = None,
        stars: int = 0,
        last_updated: str = "",
        source_labels: list[str] | None = None,
        tags: list[Tag] | None = None,
    ) -> None:
        """Initialize a CatalogEntry.

        Args:
            cat_id: Unique catalog identifier.
            name: Package name.
            description: Brief description. Defaults to None.
            url: Homepage URL. Defaults to empty string.
            source_type: VCS host type. Defaults to "github".
            default_branch: Default branch name. Defaults to "main".
            license_str: SPDX license identifier. Defaults to None.
            topics: List of GitHub topics. Defaults to None.
            stars: Star count. Defaults to 0.
            last_updated: ISO-formatted update timestamp. Defaults to empty string.
            source_labels: List of source names. Defaults to None.
            tags: List of version tags. Defaults to None.
        """
        self.id = cat_id
        self.name = name
        self.description = description
        self.url = url
        self.source_type = source_type
        self.default_branch = default_branch
        self.license = license_str
        self.topics = topics or []
        self.stars = stars
        self.last_updated = last_updated
        self.source_labels = source_labels or []
        self.tags = tags or []

    @staticmethod
    def vcs_host_label(host: str) -> str:
        """Return a short, filesystem-safe label for a VCS hostname."""
        return CatalogEntry.VCS_HOST_ALIASES.get(host, host)

    @staticmethod
    def catalog_id(vcs_host: str, org: str, repo: str, subpath: str | None = None) -> str:
        """Return the catalog ID string for a package."""
        base = f"{vcs_host.lower()}/{org.lower()}/{repo.lower()}"
        return f"{base}/{subpath.lower()}" if subpath else base

    @classmethod
    def from_manifest(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        cls,
        manifest: BaseManifest,
        vcs_host: str,
        org: str,
        repo: str,
        label: str,
    ) -> CatalogEntry:
        """Create a CatalogEntry from a manifest."""
        subpath: str | None = manifest.subpath
        entry = cls(
            cat_id=VCSLocation(vcs_host, org, repo, subpath).catalog_id,
            name=manifest.package_name,
            description=manifest.description,
            url=manifest.homepage or "",
            source_type=vcs_host,
            default_branch="main",
            license_str=manifest.license,
            topics=list(getattr(manifest, "topics", [])),
            stars=0,
            last_updated=datetime.now(UTC).isoformat(),
            source_labels=[label],
            tags=[],
        )
        if manifest.version:
            entry.update_tags(manifest.version)
        return entry

    def merge_from_manifest(self, manifest: BaseManifest, is_update: bool, label: str) -> None:
        """Merge data from a manifest into this entry."""
        self.merge_topics(is_update, list(getattr(manifest, "topics", [])))

        if manifest.description and not self.description:
            self.description = manifest.description
        if manifest.license and not self.license:
            self.license = manifest.license

        if label not in self.source_labels:
            self.source_labels.append(label)

        if manifest.version:
            self.update_tags(manifest.version)

    def to_dict(self) -> dict[str, Any]:
        """Return a dict representation of this CatalogEntry."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "source_type": self.source_type,
            "default_branch": self.default_branch,
            "license": self.license,
            "topics": self.topics,
            "stars": self.stars,
            "last_updated": self.last_updated,
            "source_labels": self.source_labels,
            "tags": [t.to_dict() for t in self.tags],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogEntry:
        """Create a CatalogEntry from a dict."""
        return cls(
            cat_id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description"),
            url=data.get("url", ""),
            source_type=data.get("source_type", "github"),
            default_branch=data.get("default_branch", "main"),
            license_str=data.get("license"),
            topics=list(data.get("topics", [])),
            stars=data.get("stars", 0),
            last_updated=data.get("last_updated", ""),
            source_labels=list(data.get("source_labels", [])),
            tags=[Tag.from_dict(t) for t in data.get("tags", [])],
        )

    def merge_topics(self, is_update: bool, topics: list[str]) -> None:
        """Merge *topics* into this entry when updating an existing entry."""
        if is_update and topics:
            self.topics.extend(t for t in topics if t not in self.topics)

    def update_tags(self, version: str) -> None:
        """Update tags with the given version."""
        tag_names_normalised = {t.name.lstrip("v") for t in self.tags}
        if version.lstrip("v") not in tag_names_normalised:
            self.tags.insert(
                0,
                Tag(
                    name=version,
                    is_tag=True,
                    commit_sha=None,
                    date=None,
                ),
            )
