"""Catalog detail data model."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from dfetch.log import get_logger
from dfetch.vcs.git import GitRemote

from dfetch_hub.catalog.model import CatalogSource, FetchMetadata, GitRefs, PackageContent, Tag, VCSLocation
from dfetch_hub.catalog.sources import BaseManifest

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


class CatalogDetail:  # pylint: disable=too-many-instance-attributes
    """Represents the per-project detail JSON file with rich metadata for a library.

    Each library has a detail file (e.g., "github/abseil/abseil-cpp.json") containing
    the canonical URL, which sources provide it, available version tags, installation
    README, and license information. This is displayed on the web interface and
    used to generate dfetch.yaml snippets.
    """

    def __init__(  # pylint: disable=too-many-arguments,disable=too-many-positional-arguments
        self,
        canonical_url: str = "",
        location: VCSLocation | None = None,
        catalog_sources: list[CatalogSource] | None = None,
        manifests: list[Any] | None = None,
        git_refs: GitRefs | None = None,
        package_content: PackageContent | None = None,
        urls: dict[str, str] | None = None,
        fetch_metadata: FetchMetadata | None = None,
    ) -> None:
        """Initialize a CatalogDetail.

        Args:
            canonical_url: Homepage URL. Defaults to empty string.
            location: VCS location (org, repo, subpath). Defaults to None.
            catalog_sources: List of sources. Defaults to empty list.
            manifests: List of manifests. Defaults to empty list.
            git_refs: Git tags and branches. Defaults to empty refs.
            package_content: README and license text. Defaults to empty content.
            urls: Additional URLs dict. Defaults to empty dict.
            fetch_metadata: Fetch timestamp metadata. Defaults to empty metadata.
        """
        self.canonical_url = canonical_url
        self.location = location or VCSLocation(host="", org="", repo="")
        self.catalog_sources = catalog_sources or []
        self.manifests = manifests or []
        self.git_refs = git_refs or GitRefs()
        self.package_content = package_content or PackageContent()
        self.urls = urls or {}
        self.fetch_metadata = fetch_metadata or FetchMetadata()

    @property
    def fetched_at(self) -> str:
        """ISO-formatted fetch timestamp."""
        return self.fetch_metadata.fetched_at

    @fetched_at.setter
    def fetched_at(self, value: str) -> None:
        """Set the fetch timestamp."""
        self.fetch_metadata.fetched_at = value

    @property
    def org(self) -> str:
        """Repository organization/owner."""
        return self.location.org

    @org.setter
    def org(self, value: str) -> None:
        """Set the repository organization/owner."""
        self.location.org = value

    @property
    def repo(self) -> str:
        """Repository name."""
        return self.location.repo

    @repo.setter
    def repo(self, value: str) -> None:
        """Set the repository name."""
        self.location.repo = value

    @property
    def subfolder_path(self) -> str | None:
        """Monorepo subfolder path."""
        return self.location.subpath

    @subfolder_path.setter
    def subfolder_path(self, value: str | None) -> None:
        """Set the monorepo subfolder path."""
        self.location.subpath = value

    @property
    def tags(self) -> list[Tag]:
        """List of version tags."""
        return self.git_refs.tags

    @tags.setter
    def tags(self, value: list[Tag]) -> None:
        """Set the list of version tags."""
        self.git_refs.tags = value

    @property
    def branches(self) -> list[Tag]:
        """List of branches."""
        return self.git_refs.branches

    @branches.setter
    def branches(self, value: list[Tag]) -> None:
        """Set the list of branches."""
        self.git_refs.branches = value

    @property
    def readme(self) -> str:
        """README content."""
        return self.package_content.readme

    @readme.setter
    def readme(self, value: str) -> None:
        """Set the README content."""
        self.package_content.readme = value

    @property
    def license_text(self) -> str | None:
        """License text."""
        return self.package_content.license_text

    @license_text.setter
    def license_text(self, value: str | None) -> None:
        """Set the license text."""
        self.package_content.license_text = value

    def to_dict(self) -> dict[str, Any]:
        """Return a dict representation of this CatalogDetail."""
        return {
            "canonical_url": self.canonical_url,
            "org": self.location.org,
            "repo": self.location.repo,
            "subfolder_path": self.location.subpath,
            "catalog_sources": [s.to_dict() for s in self.catalog_sources],
            "manifests": self.manifests,
            "readme": self.package_content.readme,
            "tags": self.git_refs.to_dict()["tags"],
            "branches": self.git_refs.to_dict()["branches"],
            "urls": self.urls,
            "license_text": self.package_content.license_text,
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogDetail:
        """Create a CatalogDetail from a dict."""
        return cls(
            canonical_url=data.get("canonical_url", ""),
            location=VCSLocation(
                host="",
                org=data.get("org", ""),
                repo=data.get("repo", ""),
                subpath=data.get("subfolder_path"),
            ),
            catalog_sources=[CatalogSource.from_dict(s) for s in data.get("catalog_sources", [])],
            manifests=list(data.get("manifests", [])),
            git_refs=GitRefs.from_dict(data),
            package_content=PackageContent(
                readme=data.get("readme", ""),
                license_text=data.get("license_text"),
            ),
            urls=dict(data.get("urls", {})),
            fetch_metadata=FetchMetadata.from_dict(data),
        )

    @classmethod
    def from_manifest(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        cls,
        manifest: BaseManifest,
        org: str,
        repo: str,
        source_name: str,
        label: str,
        registry_path: str,
    ) -> CatalogDetail:
        """Create a CatalogDetail from a manifest."""
        readme_content = getattr(manifest, "readme_content", None)
        detail = cls(
            canonical_url=manifest.homepage or "",
            location=VCSLocation(host="", org=org, repo=repo, subpath=manifest.subpath),
            catalog_sources=[],
            manifests=[],
            git_refs=GitRefs(branches=[Tag(name="main", is_tag=False)]),
            package_content=PackageContent(
                readme=readme_content or cls.generate_readme(manifest, repo, manifest.homepage or "")
            ),
            urls={},
            fetch_metadata=FetchMetadata(fetched_at=datetime.now(UTC).isoformat()),
        )
        detail.add_source(manifest, source_name, label, registry_path)
        return detail

    def dump(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, data_dir: Path, vcs_host: str, org: str, repo: str, subpath: str | None
    ) -> None:
        """Write this detail to the appropriate JSON file."""
        subpath = BaseManifest.sanitize_subpath(subpath)

        if subpath:
            detail_path = data_dir / vcs_host / org / repo / f"{subpath}.json"
        else:
            detail_path = data_dir / vcs_host / org / f"{repo}.json"

        detail_path.parent.mkdir(parents=True, exist_ok=True)
        with detail_path.open("w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    @classmethod
    def load(cls, path: Path) -> CatalogDetail | None:
        """Load a CatalogDetail from a JSON file, or return None if it doesn't exist."""
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    @staticmethod
    def generate_readme(manifest: BaseManifest, repo: str, url: str) -> str:
        """Generate a minimal installation README for a package."""
        local_name = manifest.subpath or repo
        src_line = f"\n    src: {manifest.subpath}" if manifest.subpath else ""
        version_line = f"\n    tag: {manifest.version}" if manifest.version else ""
        return (
            f"# {manifest.package_name}\n\n"
            f"{manifest.description}\n\n"
            "## Installation\n\n"
            "Add to your `dfetch.yaml`:\n\n"
            "```yaml\n"
            "projects:\n"
            f"  - name: ext/{local_name}\n"
            f"    url: {url}{src_line}{version_line}\n"
            "```\n\n"
            "## Usage\n\n"
            f"After running `dfetch update`, the library will be available at `ext/{local_name}/`.\n"
        )

    def update_tags(self, manifest: BaseManifest) -> None:
        """Update tags, fetching from upstream if needed."""
        if not self.tags and manifest.homepage:
            self.tags.extend(self.fetch_upstream_tags(manifest.homepage))

        if manifest.version:
            tag_names_normalised = {t.name.lstrip("v") for t in self.tags}
            if manifest.version.lstrip("v") not in tag_names_normalised:
                self.tags.insert(
                    0,
                    Tag(
                        name=manifest.version,
                        is_tag=True,
                        commit_sha=None,
                        date=None,
                    ),
                )

    @staticmethod
    def fetch_upstream_tags(url: str) -> list[Tag]:
        """Return git tags from url using dfetch's GitRemote."""
        try:
            info = GitRemote._ls_remote(url)  # pyright: ignore[reportPrivateUsage]  # pylint: disable=protected-access
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("Could not list tags for %s: %s", url, exc)  # pragma: no cover
            return []  # pragma: no cover

        return [
            Tag(
                name=ref.replace("refs/tags/", ""),
                is_tag=True,
                commit_sha=sha,
                date=None,
            )
            for ref, sha in info.items()
            if ref.startswith("refs/tags/")
        ]

    def add_source(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        manifest: BaseManifest,
        source_name: str,
        label: str,
        registry_path: str,
    ) -> None:
        """Add or update a catalog source entry."""
        new_source = CatalogSource(
            source_name=source_name,
            label=label,
            index_path=f"{registry_path}/{manifest.entry_name}",
            registry_version=manifest.version,
        )
        new_index_path = new_source.index_path

        # Purge stale entries with same index_path but different source_name
        self.catalog_sources = [
            s for s in self.catalog_sources if not (s.index_path == new_index_path and s.source_name != source_name)
        ]

        # Update existing or append new
        for s in self.catalog_sources:
            if s.source_name == source_name:
                s.index_path = new_source.index_path
                s.label = new_source.label
                s.registry_version = new_source.registry_version
                return

        self.catalog_sources.append(new_source)

    def update_from_manifest(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        manifest: BaseManifest,
        repo: str,
        source_name: str,
        label: str,
        registry_path: str,
    ) -> None:
        """Update this detail from a manifest (merges all data)."""
        self.merge_from_manifest(manifest, repo)
        self.add_source(manifest, source_name, label, registry_path)
        self.update_tags(manifest)

    def merge_from_manifest(self, manifest: BaseManifest, repo: str) -> None:
        """Merge data from a manifest into this detail."""
        readme_content = getattr(manifest, "readme_content", None)
        if readme_content:
            self.readme = readme_content
        elif not self.readme:
            self.readme = self.generate_readme(manifest, repo, manifest.homepage or "")

        self.urls.update(getattr(manifest, "urls", {}))

        if manifest.subpath:
            self.subfolder_path = manifest.subpath
