"""Update catalog.json and per-project detail JSONs with data from vcpkg.json files."""

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dfetch_hub.catalog.vcpkg import VcpkgManifest


# ---------------------------------------------------------------------------
# GitHub URL helpers
# ---------------------------------------------------------------------------

_GITHUB_RE = re.compile(
    r"https?://github\.com/([^/]+)/([^/\s#?]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def _parse_github_url(url: str) -> Optional[Tuple[str, str]]:
    """Return (org, repo) extracted from a GitHub URL, or None."""
    m = _GITHUB_RE.match(url.strip())
    return (m.group(1), m.group(2)) if m else None


def _catalog_id(org: str, repo: str) -> str:
    return f"github/{org.lower()}/{repo.lower()}"


def _fetch_upstream_tags(url: str) -> List[Dict[str, Any]]:
    """Return git tags from *url* via git ls-remote, newest first."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", url],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            return []

        # Build a dict of tag_name -> sha, preferring the peeled (^{}) SHA
        # because that points to the actual commit for annotated tags.
        tags: Dict[str, str] = {}
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 2:
                continue
            sha, ref = parts
            if not ref.startswith("refs/tags/"):
                continue
            name = ref[len("refs/tags/"):]
            if name.endswith("^{}"):
                tags[name[:-3]] = sha[:14]   # peeled → real commit
            elif name not in tags:
                tags[name] = sha[:14]

        return [
            {"name": name, "is_tag": True, "commit_sha": sha, "date": None}
            for name, sha in tags.items()
        ]
    except (subprocess.SubprocessError, OSError):
        return []


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
    existing: Optional[Dict[str, Any]],
    manifest: VcpkgManifest,
    org: str,
    repo: str,
    label: str,
) -> Dict[str, Any]:
    """Create or update a catalog.json entry for this package."""
    entry: Dict[str, Any] = existing or {
        "id": _catalog_id(org, repo),
        "name": manifest.package_name,
        "description": manifest.description,
        "url": manifest.homepage or f"https://github.com/{org}/{repo}",
        "source_type": "github",
        "default_branch": "main",
        "license": manifest.license,
        "topics": [],
        "stars": 0,
        "last_updated": _now_iso(),
        "source_labels": [],
        "tags": [],
    }

    # Update fields that vcpkg knows about and the catalog may be stale on
    if manifest.description and not existing:
        entry["description"] = manifest.description
    if manifest.license and not existing:
        entry["license"] = manifest.license

    # Ensure our label is in source_labels
    labels: List[str] = entry.setdefault("source_labels", [])
    if label not in labels:
        labels.append(label)

    # Add a version tag if we have one and it's not already listed
    if manifest.version:
        tags: List[Dict[str, Any]] = entry.setdefault("tags", [])
        tag_names = {t.get("name") for t in tags}
        if manifest.version not in tag_names:
            tags.insert(0, {
                "name": manifest.version,
                "is_tag": True,
                "commit_sha": None,
                "date": None,
            })

    return entry


# ---------------------------------------------------------------------------
# Detail JSON (data/github/<org>/<repo>.json)
# ---------------------------------------------------------------------------

def _catalog_source_entry(
    manifest: VcpkgManifest,
    source_name: str,
    label: str,
    ports_path: str,
) -> Dict[str, Any]:
    return {
        "source_name": source_name,
        "label": label,
        "index_path": f"{ports_path}/{manifest.port_name}",
        "registry_version": manifest.version,
    }


def _merge_detail(
    existing: Optional[Dict[str, Any]],
    manifest: VcpkgManifest,
    org: str,
    repo: str,
    source_name: str,
    label: str,
    ports_path: str,
) -> Dict[str, Any]:
    """Create or update a per-project detail JSON."""
    detail: Dict[str, Any] = existing or {
        "canonical_url": manifest.homepage or f"https://github.com/{org}/{repo}",
        "org": org,
        "repo": repo,
        "subfolder_path": None,
        "catalog_sources": [],
        "manifests": [],
        "readme": _generate_readme(manifest, org, repo),
        "tags": [],
        "branches": [{"name": "main", "is_tag": False, "commit_sha": None, "date": None}],
        "license_text": None,
        "fetched_at": _now_iso(),
    }

    # Update or add the catalog source for this label
    sources: List[Dict[str, Any]] = detail.setdefault("catalog_sources", [])
    existing_source = next(
        (s for s in sources if s.get("source_name") == source_name), None
    )
    new_source = _catalog_source_entry(manifest, source_name, label, ports_path)
    if existing_source is None:
        sources.append(new_source)
    else:
        existing_source.update(new_source)

    # Populate tags from the upstream repo when the list is empty
    tags: List[Dict[str, Any]] = detail.setdefault("tags", [])
    if not tags and manifest.homepage:
        tags.extend(_fetch_upstream_tags(manifest.homepage))

    # Ensure the current vcpkg version appears in the tag list.
    # Normalise by stripping a leading "v" so that "6.4.0" matches "v6.4.0".
    if manifest.version:
        tag_names_normalised = {t.get("name", "").lstrip("v") for t in tags}
        if manifest.version.lstrip("v") not in tag_names_normalised:
            tags.insert(0, {
                "name": manifest.version,
                "is_tag": True,
                "commit_sha": None,
                "date": None,
            })

    return detail


def _generate_readme(manifest: VcpkgManifest, org: str, repo: str) -> str:
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

def update_catalog(
    manifests: List[VcpkgManifest],
    data_dir: Path,
    source_name: str,
    label: str,
    ports_path: str,
) -> Tuple[int, int]:
    """Update catalog.json and per-project detail JSONs.

    Returns (added, updated) counts.
    """
    catalog_path = data_dir / "catalog.json"
    catalog: Dict[str, Any] = _load_json(catalog_path) or {}

    added = 0
    updated = 0

    for manifest in manifests:
        if not manifest.homepage:
            continue  # cannot determine upstream repo without a URL

        parsed = _parse_github_url(manifest.homepage)
        if not parsed:
            continue  # skip non-GitHub URLs for now

        org, repo = parsed
        cat_id = _catalog_id(org, repo)

        existing_entry = catalog.get(cat_id)
        catalog[cat_id] = _merge_catalog_entry(existing_entry, manifest, org, repo, label)
        if existing_entry is None:
            added += 1
        else:
            updated += 1

        # Per-project detail JSON
        detail_path = data_dir / "github" / org / f"{repo}.json"
        existing_detail = _load_json(detail_path)
        merged_detail = _merge_detail(
            existing_detail, manifest, org, repo, source_name, label, ports_path
        )
        _save_json(detail_path, merged_detail)

    _save_json(catalog_path, catalog)
    return added, updated
