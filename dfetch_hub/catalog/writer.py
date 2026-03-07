"""Catalog writer: builds the dfetch-hub package catalog from multiple sources.

The catalog is the central index that dfetch-hub builds up from package sources
like vcpkg, Conan, and clib. Each entry represents a library that developers can
vendor into their projects.

Developers browse the catalog to find appropriate packages, then add them to their
project's ``dfetch.yaml`` manifest. dfetch then clones the specified version
(typically a git tag) into the project's ``ext/`` directory.

The writer produces two artifacts:
- ``catalog.json``: The main index mapping catalog IDs to library entries.
- ``<vcs>/<org>/<repo>.json``: Per-project detail files with rich metadata including
  available versions, installation instructions, and which sources provide the package.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from dfetch.log import get_logger

from dfetch_hub.catalog.detail import CatalogDetail
from dfetch_hub.catalog.entry import CatalogEntry
from dfetch_hub.catalog.sources import BaseManifest, parse_vcs_slug

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class Catalog:
    """Represents the catalog.json index of all available libraries.

    This is the main index developers browse to find packages. Each key is a catalog
    ID like "github/abseil/abseil-cpp" and the value is a CatalogEntry with metadata.
    """

    def __init__(self, entries: dict[str, CatalogEntry] | None = None) -> None:
        """Initialize a Catalog.

        Args:
            entries: Dictionary mapping catalog IDs to entries. Defaults to empty dict.
        """
        self.entries = entries or {}

    def to_dict(self) -> dict[str, Any]:
        """Return a dict representation of this Catalog."""
        return {k: v.to_dict() for k, v in self.entries.items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Catalog:
        """Create a Catalog from a dict.

        Args:
            data: Dictionary representation of the catalog.

        Returns:
            A new Catalog instance.
        """
        return cls(entries={k: CatalogEntry.from_dict(v) for k, v in data.items()})

    @classmethod
    def load(cls, path: Path) -> Catalog:
        """Load a Catalog from a JSON file, or return empty if it doesn't exist.

        Args:
            path: Path to the catalog.json file.

        Returns:
            A Catalog instance, or an empty catalog if the file doesn't exist.
        """
        if not path.exists():
            return cls()
        with path.open(encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def dump(self, path: Path) -> None:
        """Save this Catalog to a JSON file.

        Args:
            path: Path to write the catalog.json file.

        Raises:
            OSError: If the file cannot be written.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    def get_or_create_entry(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        manifest: BaseManifest,
        vcs_host: str,
        org: str,
        repo: str,
        label: str,
    ) -> tuple[CatalogEntry, bool]:
        """Get or create a catalog entry for this manifest.

        Args:
            manifest: The package manifest containing metadata.
            vcs_host: The VCS host (e.g., "github").
            org: The organization/owner.
            repo: The repository name.
            label: The source label.

        Returns:
            A tuple of (entry, is_new) where is_new is True if entry was newly created.
        """
        cat_id = CatalogEntry.catalog_id(vcs_host, org, repo, manifest.subpath)
        existing = self.entries.get(cat_id)
        if existing:
            existing.merge_from_manifest(manifest, is_update=True, label=label)
            return existing, False

        entry = CatalogEntry.from_manifest(manifest, vcs_host, org, repo, label)
        self.entries[cat_id] = entry
        return entry, True

    def remove_entry(self, vcs_host: str, org: str, repo: str) -> bool:
        """Remove a catalog entry for a repo-root (no subpath).

        This is used when migrating from a repo-root entry to a subpath entry
        for monorepo packages.

        Args:
            vcs_host: The VCS host (e.g., "github").
            org: The organization/owner.
            repo: The repository name.

        Returns:
            True if an entry was removed, False otherwise.
        """
        root_id = CatalogEntry.catalog_id(vcs_host, org, repo, None)
        if root_id in self.entries:
            del self.entries[root_id]
            return True
        return False


# ---------------------------------------------------------------------------
# CatalogWriter
# ---------------------------------------------------------------------------


class CatalogWriter:
    """Handles writing package manifests to the catalog and detail JSON files.

    This is the main entry point for updating the catalog. Given a list of manifests
    from a package source (vcpkg, Conan, clib, etc.), it updates both the catalog
    index and individual detail files.
    """

    def __init__(
        self,
        data_dir: Path,
        source_name: str,
        label: str,
        registry_path: str,
    ) -> None:
        """Initialize a CatalogWriter.

        Args:
            data_dir: Root directory for catalog data.
            source_name: Name of the package source.
            label: Human-readable label for the source.
            registry_path: Path within the source registry.
        """
        self.data_dir = data_dir
        self.source_name = source_name
        self.label = label
        self.registry_path = registry_path

    def write(self, manifests: list[BaseManifest]) -> tuple[int, int]:
        """Write all manifests to the catalog."""
        catalog = Catalog.load(self.data_dir / "catalog.json")
        added = 0
        updated = 0

        for manifest in manifests:
            was_added, was_updated = self.write_manifest(manifest, catalog)
            added += was_added
            updated += was_updated

        catalog.dump(self.data_dir / "catalog.json")
        return added, updated

    def write_manifest(self, manifest: BaseManifest, catalog: Catalog) -> tuple[bool, bool]:
        """Write a single manifest to catalog and detail files."""
        if not manifest.homepage:
            logger.warning("cannot determine upstream repo without a URL of %s", manifest.entry_name)
            return False, False

        parsed = parse_vcs_slug(manifest.homepage)
        if not parsed:
            logger.warning("skipping entry without recognized VCS URL: %s", manifest.homepage)
            return False, False

        vcs_host, org, repo = parsed
        vcs_host = CatalogEntry.vcs_host_label(vcs_host)

        sanitized = manifest.sanitized_subpath
        if sanitized:
            root_id = CatalogEntry.catalog_id(vcs_host, org, repo, None)
            existing_root = catalog.entries.get(root_id)
            if existing_root and self.label in existing_root.source_labels:
                catalog.remove_entry(vcs_host, org, repo)

        _, is_new = catalog.get_or_create_entry(manifest, vcs_host, org, repo, self.label)

        self._write_detail(vcs_host, org, repo, manifest)

        return is_new, not is_new

    def _write_detail(
        self,
        vcs_host: str,
        org: str,
        repo: str,
        manifest: BaseManifest,
    ) -> None:
        """Write the detail JSON for a manifest."""
        subpath = manifest.sanitized_subpath

        if subpath:
            detail_path = self.data_dir / vcs_host / org / repo / f"{subpath}.json"
        else:
            detail_path = self.data_dir / vcs_host / org / f"{repo}.json"

        existing = CatalogDetail.load(detail_path)
        if existing:
            detail = existing
        else:
            detail = CatalogDetail.from_manifest(manifest, org, repo, self.source_name, self.label, self.registry_path)

        detail.update_from_manifest(manifest, repo, self.source_name, self.label, self.registry_path)
        detail.dump(self.data_dir, vcs_host, org, repo, subpath)
