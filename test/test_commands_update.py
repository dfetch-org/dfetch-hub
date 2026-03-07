"""Tests for dfetch_hub.commands.update._parse_entry_dirs."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from dfetch_hub.catalog.sources import BaseManifest
from dfetch_hub.commands.update import _parse_entry_dirs  # noqa: PLC2701

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FALLBACK_URL = "https://github.com/org/monorepo"


def _make_manifest(
    subpath: str | None = None,
    homepage: str | None = _FALLBACK_URL,
) -> BaseManifest:
    """Return a minimal BaseManifest for use in parse_fn stubs."""
    return BaseManifest(
        entry_name="pkg",
        package_name="pkg",
        description=None,
        homepage=homepage,
        license=None,
        version=None,
        subpath=subpath,
    )


# ---------------------------------------------------------------------------
# _parse_entry_dirs — subpath handling
# ---------------------------------------------------------------------------


def test_parse_entry_dirs_assigns_dir_name_as_subpath_when_none(tmp_path: Path) -> None:
    """entry_dir.name is used as subpath when manifest.subpath is None and fallback_homepage is set."""
    pkg_dir = tmp_path / "zlib"
    pkg_dir.mkdir()

    def parse_fn(p: Path) -> BaseManifest | None:
        return _make_manifest(subpath=None)

    manifests, skipped = _parse_entry_dirs([pkg_dir], parse_fn, _FALLBACK_URL)

    assert skipped == 0
    assert len(manifests) == 1
    assert manifests[0].subpath == "zlib"


def test_parse_entry_dirs_preserves_parser_provided_subpath(tmp_path: Path) -> None:
    """Parser-provided subpath is not overwritten when fallback_homepage is set."""
    pkg_dir = tmp_path / "zlib"
    pkg_dir.mkdir()

    def parse_fn(p: Path) -> BaseManifest | None:
        return _make_manifest(subpath="deep/zlib")

    manifests, _ = _parse_entry_dirs([pkg_dir], parse_fn, _FALLBACK_URL)

    assert manifests[0].subpath == "deep/zlib"


def test_parse_entry_dirs_does_not_assign_subpath_without_fallback(tmp_path: Path) -> None:
    """No subpath is assigned when fallback_homepage is None."""
    pkg_dir = tmp_path / "zlib"
    pkg_dir.mkdir()

    def parse_fn(p: Path) -> BaseManifest | None:
        return _make_manifest(subpath=None, homepage="https://github.com/madler/zlib")

    manifests, _ = _parse_entry_dirs([pkg_dir], parse_fn, None)

    assert manifests[0].subpath is None


# ---------------------------------------------------------------------------
# _parse_entry_dirs — homepage fallback
# ---------------------------------------------------------------------------


def test_parse_entry_dirs_fills_homepage_from_fallback_when_none(tmp_path: Path) -> None:
    """manifest.homepage is populated from fallback_homepage when originally None."""
    pkg_dir = tmp_path / "zlib"
    pkg_dir.mkdir()

    def parse_fn(p: Path) -> BaseManifest | None:
        return _make_manifest(homepage=None)

    manifests, _ = _parse_entry_dirs([pkg_dir], parse_fn, _FALLBACK_URL)

    assert manifests[0].homepage == _FALLBACK_URL


def test_parse_entry_dirs_does_not_overwrite_existing_homepage(tmp_path: Path) -> None:
    """manifest.homepage is not replaced when the parser already set one."""
    pkg_dir = tmp_path / "zlib"
    pkg_dir.mkdir()
    upstream = "https://github.com/madler/zlib"

    def parse_fn(p: Path) -> BaseManifest | None:
        return _make_manifest(homepage=upstream)

    manifests, _ = _parse_entry_dirs([pkg_dir], parse_fn, _FALLBACK_URL)

    assert manifests[0].homepage == upstream


# ---------------------------------------------------------------------------
# _parse_entry_dirs — skip counting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_good,n_bad", [(0, 3), (2, 1), (3, 0)])
def test_parse_entry_dirs_counts_skipped_correctly(tmp_path: Path, n_good: int, n_bad: int) -> None:
    """Directories whose parse_fn returns None are counted as skipped."""
    dirs = []
    for i in range(n_good):
        d = tmp_path / f"good{i}"
        d.mkdir()
        dirs.append(d)
    for i in range(n_bad):
        d = tmp_path / f"bad{i}"
        d.mkdir()
        dirs.append(d)

    def parse_fn(p: Path) -> BaseManifest | None:
        return _make_manifest() if "good" in p.name else None

    manifests, skipped = _parse_entry_dirs(dirs, parse_fn, None)

    assert len(manifests) == n_good
    assert skipped == n_bad
