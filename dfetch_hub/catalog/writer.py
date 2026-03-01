"""Write parsed package manifests to catalog.json and per-project detail JSONs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from dfetch.log import get_logger
from dfetch.vcs.git import GitRemote

from dfetch_hub.catalog.sources import BaseManifest, _parse_github_slug

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


def _catalog_id(org: str, repo: str) -> str:
    return f"github/{org.lower()}/{repo.lower()}"


def _fetch_upstream_tags(url: str) -> list[dict[str, Any]]:
    """Return git tags from *url* using dfetch's GitRemote."""
    try:
        info = GitRemote._ls_remote(url)  # pylint: disable=protected-access
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Could not list tags for %s: %s", url, exc)  # pragma: no cover
        return []  # pragma: no cover

    return [
        {
            "name": ref.replace("refs/tags/", ""),
            "is_tag": True,
            "commit_sha": sha[:14],
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
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Catalog entry (catalog.json)
# ---------------------------------------------------------------------------


def _merge_catalog_entry(
    existing: dict[str, Any] | None,
    manifest: BaseManifest,
    org: str,
    repo: str,
    label: str,
) -> dict[str, Any]:
    """Create or update a catalog.json entry for this package."""
    topics: list[str] = list(getattr(manifest, "topics", []))
    entry: dict[str, Any] = existing or {
        "id": _catalog_id(org, repo),
        "name": manifest.package_name,
        "description": manifest.description,
        "url": manifest.homepage or f"https://github.com/{org}/{repo}",
        "source_type": "github",
        "default_branch": "main",
        "license": manifest.license,
        "topics": topics,
        "stars": 0,
        "last_updated": _now_iso(),
        "source_labels": [],
        "tags": [],
    }

    # Merge in topics from the current source if the entry already existed
    if existing and topics:
        existing_topics: list[str] = entry.setdefault("topics", [])
        existing_topics.extend(t for t in topics if t not in existing_topics)

    # Update fields that the manifest knows about and the catalog may be stale on
    if manifest.description and not entry.get("description"):
        entry["description"] = manifest.description
    if manifest.license and not entry.get("license"):
        entry["license"] = manifest.license

    # Ensure our label is in source_labels
    labels: list[str] = entry.setdefault("source_labels", [])
    if label not in labels:
        labels.append(label)

    # Add a version tag if we have one and it's not already listed.
    # Normalise by stripping a leading "v" so "6.4.0" matches "v6.4.0".
    if manifest.version:
        tags: list[dict[str, Any]] = entry.setdefault("tags", [])
        tag_names_normalised = {str(t.get("name") or "").lstrip("v") for t in tags}
        if manifest.version.lstrip("v") not in tag_names_normalised:
            tags.insert(
                0,
                {
                    "name": manifest.version,
                    "is_tag": True,
                    "commit_sha": None,
                    "date": None,
                },
            )

    return entry


# ---------------------------------------------------------------------------
# Detail JSON (data/github/<org>/<repo>.json)
# ---------------------------------------------------------------------------


def _catalog_source_entry(
    manifest: BaseManifest,
    source_name: str,
    label: str,
    ports_path: str,
) -> dict[str, Any]:
    return {
        "source_name": source_name,
        "label": label,
        "index_path": f"{ports_path}/{manifest.port_name}",
        "registry_version": manifest.version,
    }


def _merge_detail(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    existing: dict[str, Any] | None,
    manifest: BaseManifest,
    org: str,
    repo: str,
    source_name: str,
    label: str,
    ports_path: str,
) -> dict[str, Any]:
    """Create or update a per-project detail JSON."""
    fetched_readme: str | None = getattr(manifest, "readme_content", None)
    detail: dict[str, Any] = existing or {
        "canonical_url": manifest.homepage or f"https://github.com/{org}/{repo}",
        "org": org,
        "repo": repo,
        "subfolder_path": None,
        "catalog_sources": [],
        "manifests": [],
        "readme": fetched_readme or _generate_readme(manifest, org, repo),
        "tags": [],
        "branches": [
            {"name": "main", "is_tag": False, "commit_sha": None, "date": None},
        ],
        "license_text": None,
        "fetched_at": _now_iso(),
    }

    # When we have a real upstream README, always overwrite the placeholder
    if fetched_readme:
        detail["readme"] = fetched_readme

    # Update or add the catalog source for this label
    sources: list[dict[str, Any]] = detail.setdefault("catalog_sources", [])
    existing_source = next(
        (s for s in sources if s.get("source_name") == source_name),
        None,
    )
    new_source = _catalog_source_entry(manifest, source_name, label, ports_path)
    if existing_source is None:
        sources.append(new_source)
    else:
        existing_source.update(new_source)

    # Populate tags from the upstream repo when the list is empty
    tags: list[dict[str, Any]] = detail.setdefault("tags", [])
    if not tags and manifest.homepage:
        tags.extend(_fetch_upstream_tags(manifest.homepage))

    # Ensure the current version appears in the tag list.
    # Normalise by stripping a leading "v" so that "6.4.0" matches "v6.4.0".
    if manifest.version:
        tag_names_normalised = {t.get("name", "").lstrip("v") for t in tags}
        if manifest.version.lstrip("v") not in tag_names_normalised:
            tags.insert(
                0,
                {
                    "name": manifest.version,
                    "is_tag": True,
                    "commit_sha": None,
                    "date": None,
                },
            )

    return detail


def _generate_readme(manifest: BaseManifest, org: str, repo: str) -> str:
    version_line = f"\n    tag: {manifest.version}" if manifest.version else ""
    return (
        f"# {manifest.package_name}\n\n"
        f"{manifest.description}\n\n"
        "## Installation\n\n"
        "Add to your `dfetch.yaml`:\n\n"
        "```yaml\n"
        "projects:\n"
        f"  - name: ext/{repo}\n"
        f"    url: https://github.com/{org}/{repo}{version_line}\n"
        "```\n\n"
        "## Usage\n\n"
        f"After running `dfetch update`, the library will be available at `ext/{repo}/`.\n"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_catalog(  # pylint: disable=too-many-locals
    manifests: list[BaseManifest],
    data_dir: Path,
    source_name: str,
    label: str,
    ports_path: str,
) -> tuple[int, int]:
    """Write *manifests* into catalog.json and per-project detail JSONs under *data_dir*.

    Args:
        manifests:   Parsed package manifests from any source strategy.
        data_dir:    Root of the catalog data directory.
        source_name: Internal name of the source (e.g. ``"vcpkg"``).
        label:       Human-readable label added to each entry's ``source_labels``.
        ports_path:  Sub-path used to build the ``index_path`` in the detail JSON.

    Returns:
        A ``(added, updated)`` tuple with the count of new and existing entries written.

    """
    catalog_path = data_dir / "catalog.json"
    catalog: dict[str, Any] = _load_json(catalog_path) or {}

    added = 0
    updated = 0

    for manifest in manifests:
        if not manifest.homepage:
            logger.warning(
                f"cannot determine upstream repo without a URL of {manifest.port_name}"
            )
            continue

        parsed = _parse_github_slug(manifest.homepage)
        if not parsed:
            logger.warning("skipping non-GitHub URL: %s", manifest.homepage)
            continue

        org, repo = parsed
        cat_id = _catalog_id(org, repo)

        existing_entry = catalog.get(cat_id)
        catalog[cat_id] = _merge_catalog_entry(
            existing_entry,
            manifest,
            org,
            repo,
            label,
        )
        if existing_entry is None:
            added += 1
        else:
            updated += 1

        # Per-project detail JSON
        detail_path = data_dir / "github" / org / f"{repo}.json"
        existing_detail = _load_json(detail_path)
        merged_detail = _merge_detail(
            existing_detail,
            manifest,
            org,
            repo,
            source_name,
            label,
            ports_path,
        )
        _save_json(detail_path, merged_detail)

    _save_json(catalog_path, catalog)
    return added, updated
