"""Tests for the source-cloning module (currently store/fetcher.py, moving to catalog/cloner.py).

Covers:
- create_manifest: writes a valid dfetch.yaml to the destination directory.
- clone_source: drives the dfetch API and returns the expected output path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dfetch_hub.catalog.cloner import clone_source, create_manifest
from dfetch_hub.config import SourceConfig

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_SOURCE = SourceConfig(
    name="vcpkg",
    url="https://github.com/microsoft/vcpkg.git",
    strategy="subfolders",
    path="ports/",
    manifest="vcpkg.json",
    branch="master",
    label="vcpkg",
)

_SOURCE_NO_BRANCH = SourceConfig(
    name="conan",
    url="https://github.com/conan-io/conan-center-index.git",
    strategy="subfolders",
    path="recipes/",
    manifest="conandata.yml",
)


# ---------------------------------------------------------------------------
# create_manifest
# ---------------------------------------------------------------------------


def test_create_manifest_returns_yaml_path(tmp_path: Path) -> None:
    path = create_manifest(_SOURCE, tmp_path)
    assert path == tmp_path / "dfetch.yaml"


def test_create_manifest_writes_file(tmp_path: Path) -> None:
    path = create_manifest(_SOURCE, tmp_path)
    assert path.exists()


def test_create_manifest_contains_url(tmp_path: Path) -> None:
    path = create_manifest(_SOURCE, tmp_path)
    assert "https://github.com/microsoft/vcpkg.git" in path.read_text(encoding="utf-8")


def test_create_manifest_contains_source_name(tmp_path: Path) -> None:
    path = create_manifest(_SOURCE, tmp_path)
    assert "vcpkg" in path.read_text(encoding="utf-8")


def test_create_manifest_contains_src_path(tmp_path: Path) -> None:
    path = create_manifest(_SOURCE, tmp_path)
    assert "ports/" in path.read_text(encoding="utf-8")


def test_create_manifest_empty_branch_does_not_raise(tmp_path: Path) -> None:
    """create_manifest must not raise when branch is an empty string."""
    path = create_manifest(_SOURCE_NO_BRANCH, tmp_path)
    assert path.exists()


def test_create_manifest_idempotent(tmp_path: Path) -> None:
    """Calling create_manifest twice overwrites the file without error."""
    create_manifest(_SOURCE, tmp_path)
    path = create_manifest(_SOURCE, tmp_path)
    assert path.exists()


# ---------------------------------------------------------------------------
# clone_source
# ---------------------------------------------------------------------------


def _patch_dfetch(
    tmp_path: Path, source: SourceConfig
) -> tuple[Path, MagicMock, MagicMock]:
    """Create the expected output dir and return (fetched_path, mock_project, mock_sub)."""
    fetched = tmp_path / source.name
    fetched.mkdir()
    mock_project = MagicMock()
    mock_sub = MagicMock()
    return fetched, mock_project, mock_sub


def test_clone_source_returns_expected_directory(tmp_path: Path) -> None:
    fetched, mock_project, mock_sub = _patch_dfetch(tmp_path, _SOURCE)
    with (
        patch("dfetch_hub.catalog.cloner.parse_manifest") as mock_parse,
        patch("dfetch_hub.catalog.cloner.create_sub_project", return_value=mock_sub),
        patch("dfetch_hub.catalog.cloner.in_directory"),
    ):
        mock_parse.return_value.projects = [mock_project]
        result = clone_source(_SOURCE, tmp_path)
    assert result == fetched


def test_clone_source_calls_update_with_force(tmp_path: Path) -> None:
    _, mock_project, mock_sub = _patch_dfetch(tmp_path, _SOURCE)
    with (
        patch("dfetch_hub.catalog.cloner.parse_manifest") as mock_parse,
        patch("dfetch_hub.catalog.cloner.create_sub_project", return_value=mock_sub),
        patch("dfetch_hub.catalog.cloner.in_directory"),
    ):
        mock_parse.return_value.projects = [mock_project]
        clone_source(_SOURCE, tmp_path)
    mock_sub.update.assert_called_once_with(force=True)


def test_clone_source_raises_when_output_absent(tmp_path: Path) -> None:
    """clone_source must raise RuntimeError when dfetch produces no output directory."""
    mock_project = MagicMock()
    mock_sub = MagicMock()
    with (
        patch("dfetch_hub.catalog.cloner.parse_manifest") as mock_parse,
        patch("dfetch_hub.catalog.cloner.create_sub_project", return_value=mock_sub),
        patch("dfetch_hub.catalog.cloner.in_directory"),
        pytest.raises(RuntimeError, match="not found after update"),
    ):
        mock_parse.return_value.projects = [mock_project]
        clone_source(_SOURCE, tmp_path)


def test_clone_source_calls_update_for_each_project(tmp_path: Path) -> None:
    """clone_source must call .update() once per project in the manifest."""
    fetched = tmp_path / _SOURCE.name
    fetched.mkdir()
    mock_sub = MagicMock()
    with (
        patch("dfetch_hub.catalog.cloner.parse_manifest") as mock_parse,
        patch("dfetch_hub.catalog.cloner.create_sub_project", return_value=mock_sub),
        patch("dfetch_hub.catalog.cloner.in_directory"),
    ):
        mock_parse.return_value.projects = [MagicMock(), MagicMock()]
        clone_source(_SOURCE, tmp_path)
    assert mock_sub.update.call_count == 2


def test_clone_source_passes_manifest_path_to_parse(tmp_path: Path) -> None:
    """clone_source passes the written dfetch.yaml path to parse_manifest."""
    fetched = tmp_path / _SOURCE.name
    fetched.mkdir()
    mock_sub = MagicMock()
    with (
        patch("dfetch_hub.catalog.cloner.parse_manifest") as mock_parse,
        patch("dfetch_hub.catalog.cloner.create_sub_project", return_value=mock_sub),
        patch("dfetch_hub.catalog.cloner.in_directory"),
    ):
        mock_parse.return_value.projects = [MagicMock()]
        clone_source(_SOURCE, tmp_path)
    called_with = mock_parse.call_args[0][0]
    assert called_with.endswith("dfetch.yaml")
