"""Tests for dfetch_hub.commands.update internals.

Covers:
- _process_subfolders_source: subfolder_path is set on parsed manifests.
- _filter_sentinel: directories with the sentinel file are removed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from dfetch_hub.commands.update import _filter_sentinel, _process_subfolders_source
from dfetch_hub.config import SourceConfig

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCE_WITH_PATH = SourceConfig(
    name="vcpkg",
    strategy="subfolders",
    url="https://github.com/microsoft/vcpkg",
    path="ports",
    manifest="readme",
)

_SOURCE_WITHOUT_PATH = SourceConfig(
    name="pkgs",
    strategy="subfolders",
    url="https://github.com/example/pkgs",
    path="",
    manifest="readme",
)


# ---------------------------------------------------------------------------
# _process_subfolders_source — subfolder_path propagation
# ---------------------------------------------------------------------------


def test_subfolder_path_includes_source_path_prefix(tmp_path: Path) -> None:
    """When source.path is set, subfolder_path = '<source.path>/<dir_name>'."""
    pkg_dir = tmp_path / "abseil"
    pkg_dir.mkdir()
    (pkg_dir / "README.md").write_text("# abseil\nC++ library.", encoding="utf-8")

    captured: list[object] = []

    def fake_write_catalog(manifests, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured.extend(manifests)
        return 0, 0

    with (
        patch(
            "dfetch_hub.commands.update.clone_source",
            return_value=tmp_path,
        ),
        patch(
            "dfetch_hub.commands.update.write_catalog",
            side_effect=fake_write_catalog,
        ),
    ):
        _process_subfolders_source(_SOURCE_WITH_PATH, tmp_path, limit=None)

    assert len(captured) == 1
    assert captured[0].subfolder_path == "ports/abseil"  # type: ignore[union-attr]


def test_subfolder_path_uses_dir_name_when_no_source_path(tmp_path: Path) -> None:
    """When source.path is empty, subfolder_path = '<dir_name>' only."""
    pkg_dir = tmp_path / "mylib"
    pkg_dir.mkdir()
    (pkg_dir / "README.md").write_text("# mylib\nA library.", encoding="utf-8")

    captured: list[object] = []

    def fake_write_catalog(manifests, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured.extend(manifests)
        return 0, 0

    with (
        patch(
            "dfetch_hub.commands.update.clone_source",
            return_value=tmp_path,
        ),
        patch(
            "dfetch_hub.commands.update.write_catalog",
            side_effect=fake_write_catalog,
        ),
    ):
        _process_subfolders_source(_SOURCE_WITHOUT_PATH, tmp_path, limit=None)

    assert len(captured) == 1
    assert captured[0].subfolder_path == "mylib"  # type: ignore[union-attr]


def test_subfolder_path_set_for_multiple_entries(tmp_path: Path) -> None:
    """Every parsed manifest gets its own correct subfolder_path."""
    for name in ("alpha", "beta"):
        pkg_dir = tmp_path / name
        pkg_dir.mkdir()
        (pkg_dir / "README.md").write_text(f"# {name}\nDesc.", encoding="utf-8")

    captured: list[object] = []

    def fake_write_catalog(manifests, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured.extend(manifests)
        return 0, 0

    with (
        patch("dfetch_hub.commands.update.clone_source", return_value=tmp_path),
        patch(
            "dfetch_hub.commands.update.write_catalog",
            side_effect=fake_write_catalog,
        ),
    ):
        _process_subfolders_source(_SOURCE_WITH_PATH, tmp_path, limit=None)

    paths = {m.subfolder_path for m in captured}  # type: ignore[union-attr]
    assert paths == {"ports/alpha", "ports/beta"}


# ---------------------------------------------------------------------------
# _filter_sentinel
# ---------------------------------------------------------------------------


def test_filter_sentinel_removes_dirs_with_sentinel(tmp_path: Path) -> None:
    """Directories that contain the sentinel file are excluded."""
    keep = tmp_path / "keep"
    drop = tmp_path / "drop"
    keep.mkdir()
    drop.mkdir()
    (drop / ".sentinel").touch()

    source = MagicMock()
    source.ignore_if_present = ".sentinel"
    source.name = "test"

    result = _filter_sentinel(source, [keep, drop])
    assert result == [keep]


def test_filter_sentinel_noop_when_empty_string(tmp_path: Path) -> None:
    """An empty ignore_if_present disables filtering entirely."""
    dirs = [tmp_path / "a", tmp_path / "b"]
    source = MagicMock()
    source.ignore_if_present = ""

    result = _filter_sentinel(source, dirs)
    assert result == dirs


@pytest.mark.parametrize(
    "names, limit, expected_count",
    [
        (["a", "b", "c"], 2, 2),
        (["a", "b"], None, 2),
        (["a", "b", "c"], 0, 0),
    ],
)
def test_limit_applied_to_entry_dirs(
    tmp_path: Path, names: list[str], limit: int | None, expected_count: int
) -> None:
    """Only the first *limit* entries are processed."""
    for name in names:
        d = tmp_path / name
        d.mkdir()
        (d / "README.md").write_text(f"# {name}\nDesc.", encoding="utf-8")

    captured: list[object] = []

    def fake_write_catalog(manifests, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured.extend(manifests)
        return 0, 0

    with (
        patch("dfetch_hub.commands.update.clone_source", return_value=tmp_path),
        patch(
            "dfetch_hub.commands.update.write_catalog",
            side_effect=fake_write_catalog,
        ),
    ):
        _process_subfolders_source(_SOURCE_WITHOUT_PATH, tmp_path, limit=limit)

    assert len(captured) == expected_count
