"""Write parsed package manifests to catalog.json and per-project detail JSONs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from dfetch.log import get_logger
from dfetch.vcs.git import GitRemote

from dfetch_hub.catalog.sources import BaseManifest, parse_vcs_slug

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# VCS host normalisation
# ---------------------------------------------------------------------------

_VCS_HOST_ALIASES: dict[str, str] = {
    "github.com": "github",
    "gitlab.com": "gitlab",
    "bitbucket.org": "bitbucket",
}


def _vcs_host_label(host: str) -> str:
    """Return a short, filesystem-safe label for a VCS hostname.

    Well-known public hosts are mapped to their common short name
    (``github``, ``gitlab``, ``bitbucket``).  Unknown hosts (e.g.
    self-hosted Gitea instances) are used verbatim.

    Args:
        host: Lowercased hostname extracted from a VCS URL.

    Returns:
        A short label string suitable for use in catalog IDs and directory names.

    """
    return _VCS_HOST_ALIASES.get(host, host)


def _catalog_id(vcs_host: str, org: str, repo: str, subpath: str | None = None) -> str:
    """Return the catalog ID string for a package.

    Args:
        vcs_host: Short VCS host label (e.g. ``"github"``).
        org:      Organisation or owner name.
        repo:     Repository name.
        subpath:  Subdirectory within the repo for monorepo components, or
                  ``None`` for repository-root packages.

    Returns:
        A slash-separated ID such as ``"github/org/repo"`` or, for monorepo
        components, ``"github/org/repo/subpath"``.

    """
    base = f"{vcs_host.lower()}/{org.lower()}/{repo.lower()}"
    return f"{base}/{subpath.lower()}" if subpath else base


def _fetch_upstream_tags(url: str) -> list[dict[str, Any]]:
    """Return git tags from *url* using dfetch's GitRemote."""
    try:
        info = GitRemote._ls_remote(url)  # pylint: disable=protected-access  # pyright: ignore[reportPrivateUsage]
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Could not list tags for %s: %s", url, exc)  # pragma: no cover
        return []  # pragma: no cover

    return [
        {
            "name": ref.replace("refs/tags/", ""),
            "is_tag": True,
            "commit_sha": sha,
            "date": None,
        }
        for ref, sha in info.items()
        if ref.startswith("refs/tags/")
    ]


# ---------------------------------------------------------------------------
# catalog.json helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> Any:
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    return None


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Catalog entry (catalog.json)
# ---------------------------------------------------------------------------


def _ensure_version_tag(tags: list[dict[str, Any]], version: str) -> None:
    """Add *version* to *tags* if not already present.

    Normalises by stripping a leading ``"v"`` so ``"6.4.0"`` matches ``"v6.4.0"``.

    Args:
        tags:    Mutable tag list to update in-place.
        version: Version string to ensure is present.
    """
    tag_names_normalised = {str(t.get("name") or "").lstrip("v") for t in tags}
    if version.lstrip("v") not in tag_names_normalised:
        tags.insert(
            0,
            {
                "name": version,
                "is_tag": True,
                "commit_sha": None,
                "date": None,
            },
        )


def _merge_topics(
    entry: dict[str, Any],
    existing: dict[str, Any] | None,
    topics: list[str],
) -> None:
    """Merge *topics* into ``entry["topics"]`` when updating an existing entry.

    No-op when *existing* is ``None`` (newly created entry already has the topics
    embedded in the initial dict) or *topics* is empty.

    Args:
        entry:    Catalog entry dict to update in-place.
        existing: Previous value of the entry, or ``None`` if newly created.
        topics:   Topics from the current manifest to add.
    """
    if existing and topics:
        existing_topics: list[str] = entry.setdefault("topics", [])
        existing_topics.extend(t for t in topics if t not in existing_topics)


def _merge_catalog_entry(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    existing: dict[str, Any] | None,
    manifest: BaseManifest,
    vcs_host: str,
    org: str,
    repo: str,
    label: str,
) -> dict[str, Any]:
    """Create or update a catalog.json entry for this package."""
    subpath: str | None = manifest.subpath
    topics: list[str] = list(getattr(manifest, "topics", []))
    entry: dict[str, Any] = existing or {
        "id": _catalog_id(vcs_host, org, repo, subpath),
        "name": manifest.package_name,
        "description": manifest.description,
        "url": manifest.homepage or "",
        "source_type": vcs_host,
        "default_branch": "main",
        "license": manifest.license,
        "topics": topics,
        "stars": 0,
        "last_updated": _now_iso(),
        "source_labels": [],
        "tags": [],
    }

    _merge_topics(entry, existing, topics)

    # Update fields that the manifest knows about and the catalog may be stale on
    if manifest.description and not entry.get("description"):
        entry["description"] = manifest.description
    if manifest.license and not entry.get("license"):
        entry["license"] = manifest.license

    # Ensure our label is in source_labels
    labels: list[str] = entry.setdefault("source_labels", [])
    if label not in labels:
        labels.append(label)

    if manifest.version:
        _ensure_version_tag(entry.setdefault("tags", []), manifest.version)

    return entry


# ---------------------------------------------------------------------------
# Detail JSON (data/<vcs_host>/<org>/<repo>.json)
# ---------------------------------------------------------------------------


def _catalog_source_entry(
    manifest: BaseManifest,
    source_name: str,
    label: str,
    registry_path: str,
) -> dict[str, Any]:
    return {
        "source_name": source_name,
        "label": label,
        "index_path": f"{registry_path}/{manifest.entry_name}",
        "registry_version": manifest.version,
    }


def _merge_catalog_sources(
    detail: dict[str, Any],
    manifest: BaseManifest,
    source_name: str,
    label: str,
    registry_path: str,
) -> None:
    """Update the ``catalog_sources`` list in *detail* for this manifest.

    Purges stale entries that share the same ``index_path`` but carry an
    outdated ``source_name`` (e.g. after a source rename in ``dfetch-hub.toml``),
    then upserts the current source entry.

    Args:
        detail:        Per-project detail dict to update in-place.
        manifest:      Package manifest supplying entry metadata.
        source_name:   Internal name of the catalog source.
        label:         Human-readable label for the source.
        registry_path: Sub-path used to build the ``index_path``.
    """
    sources: list[dict[str, Any]] = detail.setdefault("catalog_sources", [])
    new_source = _catalog_source_entry(manifest, source_name, label, registry_path)
    new_index_path = new_source["index_path"]
    detail["catalog_sources"] = sources = [
        s for s in sources if not (s.get("index_path") == new_index_path and s.get("source_name") != source_name)
    ]
    existing_source = next((s for s in sources if s.get("source_name") == source_name), None)
    if existing_source is None:
        sources.append(new_source)
    else:
        existing_source.update(new_source)


def _merge_detail(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    existing: dict[str, Any] | None,
    manifest: BaseManifest,
    org: str,
    repo: str,
    source_name: str,
    label: str,
    registry_path: str,
) -> dict[str, Any]:
    """Create or update a per-project detail JSON."""
    fetched_readme: str | None = getattr(manifest, "readme_content", None)
    detail: dict[str, Any] = existing or {
        "canonical_url": manifest.homepage or "",
        "org": org,
        "repo": repo,
        "subfolder_path": manifest.subpath,
        "catalog_sources": [],
        "manifests": [],
        "readme": fetched_readme or _generate_readme(manifest, repo, manifest.homepage or ""),
        "tags": [],
        "branches": [
            {"name": "main", "is_tag": False, "commit_sha": None, "date": None},
        ],
        "urls": {},
        "license_text": None,
        "fetched_at": _now_iso(),
    }

    # When we have a real upstream README, always overwrite the placeholder
    if fetched_readme:
        detail["readme"] = fetched_readme

    # Merge named URLs from this manifest into the detail's url map
    detail.setdefault("urls", {}).update(getattr(manifest, "urls", {}))

    _merge_catalog_sources(detail, manifest, source_name, label, registry_path)

    # Populate tags from the upstream repo when the list is empty
    tags: list[dict[str, Any]] = detail.setdefault("tags", [])
    if not tags and manifest.homepage:
        tags.extend(_fetch_upstream_tags(manifest.homepage))

    if manifest.version:
        _ensure_version_tag(tags, manifest.version)

    return detail


def _generate_readme(manifest: BaseManifest, repo: str, url: str) -> str:
    """Generate a minimal installation README for a package.

    Args:
        manifest: Package metadata supplying name, description, version, and
                  optional subpath (for monorepo components).
        repo:     Repository name used as the local checkout directory name
                  when *manifest.subpath* is not set.
        url:      Full VCS URL to embed in the dfetch.yaml snippet.

    Returns:
        A Markdown string with a package heading, description, and dfetch
        installation snippet.  Monorepo components (those with a non-``None``
        ``manifest.subpath``) include a ``src:`` line that selects the correct
        subdirectory, and use the subpath name as the local checkout name.

    """
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _write_detail_json(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    data_dir: Path,
    vcs_host: str,
    org: str,
    repo: str,
    subpath: str | None,
    manifest: BaseManifest,
    source_name: str,
    label: str,
    registry_path: str,
) -> None:
    """Write or update the per-project detail JSON for one package.

    Args:
        data_dir:      Root of the catalog data directory.
        vcs_host:      Short VCS host label (e.g. ``"github"``).
        org:           Repository owner / organisation (lowercased).
        repo:          Repository name (lowercased).
        subpath:       Optional subpath in repo
        manifest:      Package manifest supplying metadata.
        source_name:   Internal name of the catalog source.
        label:         Human-readable label for the source.
        registry_path: Sub-path used to build the ``index_path``.
    """
    # Per-project detail JSON — monorepo components get their own file
    # inside a <repo>/ subdirectory so each sub-component is kept separate.
    if subpath:
        detail_path = data_dir / vcs_host / org / repo / f"{subpath}.json"
    else:
        detail_path = data_dir / vcs_host / org / f"{repo}.json"

    _save_json(
        detail_path,
        _merge_detail(
            _load_json(detail_path),
            manifest,
            org,
            repo,
            source_name,
            label,
            registry_path,
        ),
    )


def _process_manifest(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    manifest: BaseManifest,
    catalog: dict[str, Any],
    data_dir: Path,
    source_name: str,
    label: str,
    registry_path: str,
) -> tuple[bool, bool]:
    """Update *catalog* and write the detail JSON for one manifest.

    Args:
        manifest:      Package manifest to process.
        catalog:       Mutable catalog dict to update in-place.
        data_dir:      Root of the catalog data directory.
        source_name:   Internal name of the catalog source.
        label:         Human-readable source label.
        registry_path: Sub-path used to build the ``index_path``.

    Returns:
        ``(added, updated)`` booleans — exactly one is ``True`` when the manifest
        was successfully written; both are ``False`` when the manifest is skipped.
    """
    if not manifest.homepage:
        logger.warning("cannot determine upstream repo without a URL of %s", manifest.entry_name)
        return False, False

    parsed = parse_vcs_slug(manifest.homepage)
    if not parsed:
        logger.warning("skipping entry without recognized VCS URL: %s", manifest.homepage)
        return False, False

    vcs_host, org, repo = parsed
    vcs_host = _vcs_host_label(vcs_host)
    cat_id = _catalog_id(vcs_host, org, repo, manifest.subpath)

    existing_entry = catalog.get(cat_id)
    catalog[cat_id] = _merge_catalog_entry(existing_entry, manifest, vcs_host, org, repo, label)
    _write_detail_json(data_dir, vcs_host, org, repo, manifest.subpath, manifest, source_name, label, registry_path)
    return existing_entry is None, existing_entry is not None


def write_catalog(
    manifests: list[BaseManifest],
    data_dir: Path,
    source_name: str,
    label: str,
    registry_path: str,
) -> tuple[int, int]:
    """Write *manifests* into catalog.json and per-project detail JSONs under *data_dir*.

    Args:
        manifests:     Parsed package manifests from any source strategy.
        data_dir:      Root of the catalog data directory.
        source_name:   Internal name of the source (e.g. ``"vcpkg"``).
        label:         Human-readable label added to each entry's ``source_labels``.
        registry_path: Sub-path used to build the ``index_path`` in the detail JSON.

    Returns:
        A ``(added, updated)`` tuple with the count of new and existing entries written.

    """
    catalog_path = data_dir / "catalog.json"
    catalog: dict[str, Any] = _load_json(catalog_path) or {}
    added = 0
    updated = 0

    for manifest in manifests:
        was_added, was_updated = _process_manifest(manifest, catalog, data_dir, source_name, label, registry_path)
        added += was_added
        updated += was_updated

    _save_json(catalog_path, catalog)
    return added, updated
