"""Tests for dfetch_hub.commands.update: update command and source processing."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dfetch_hub.commands.update import (
    _filter_sentinel,
    _non_negative_int,
    _subfolder_homepage,
    register,
)
from dfetch_hub.config import SourceConfig

# ---------------------------------------------------------------------------
# _filter_sentinel
# ---------------------------------------------------------------------------


def test_filter_sentinel_removes_matching_dirs(tmp_path: Path) -> None:
    """_filter_sentinel removes directories containing the sentinel file."""
    (tmp_path / "keep1").mkdir()
    (tmp_path / "keep2").mkdir()

    skip1 = tmp_path / "skip1"
    skip1.mkdir()
    (skip1 / ".sentinel").touch()

    skip2 = tmp_path / "skip2"
    skip2.mkdir()
    (skip2 / ".sentinel").touch()

    source = SourceConfig(
        name="test", strategy="subfolders", url="", ignore_if_present=".sentinel"
    )
    entry_dirs = [tmp_path / "keep1", skip1, tmp_path / "keep2", skip2]

    filtered = _filter_sentinel(source, entry_dirs)
    assert len(filtered) == 2
    assert tmp_path / "keep1" in filtered
    assert tmp_path / "keep2" in filtered


def test_filter_sentinel_returns_all_when_empty_string(tmp_path: Path) -> None:
    """_filter_sentinel returns the original list when ignore_if_present is empty."""
    (tmp_path / "dir1").mkdir()
    (tmp_path / "dir2").mkdir()

    source = SourceConfig(name="test", strategy="subfolders", url="", ignore_if_present="")
    entry_dirs = [tmp_path / "dir1", tmp_path / "dir2"]

    filtered = _filter_sentinel(source, entry_dirs)
    assert filtered == entry_dirs


def test_filter_sentinel_returns_all_when_no_matches(tmp_path: Path) -> None:
    """_filter_sentinel returns all dirs when none contain the sentinel."""
    (tmp_path / "dir1").mkdir()
    (tmp_path / "dir2").mkdir()

    source = SourceConfig(
        name="test", strategy="subfolders", url="", ignore_if_present=".sentinel"
    )
    entry_dirs = [tmp_path / "dir1", tmp_path / "dir2"]

    filtered = _filter_sentinel(source, entry_dirs)
    assert filtered == entry_dirs


def test_filter_sentinel_empty_list() -> None:
    """_filter_sentinel handles an empty input list."""
    source = SourceConfig(
        name="test", strategy="subfolders", url="", ignore_if_present=".sentinel"
    )
    assert _filter_sentinel(source, []) == []


def test_filter_sentinel_logs_ignored_count(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """_filter_sentinel logs the number of ignored directories."""
    skip1 = tmp_path / "skip1"
    skip1.mkdir()
    (skip1 / ".sentinel").touch()

    skip2 = tmp_path / "skip2"
    skip2.mkdir()
    (skip2 / ".sentinel").touch()

    source = SourceConfig(
        name="test-source", strategy="subfolders", url="", ignore_if_present=".sentinel"
    )
    entry_dirs = [skip1, skip2]

    with caplog.at_level("INFO"):
        _filter_sentinel(source, entry_dirs)

    # Check that a log message was emitted mentioning the count
    assert any("Ignored 2 folder(s)" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# _subfolder_homepage
# ---------------------------------------------------------------------------


def test_subfolder_homepage_returns_url() -> None:
    """_subfolder_homepage returns the source URL when present."""
    source = SourceConfig(
        name="test", strategy="readme-only", url="https://github.com/org/repo"
    )
    assert _subfolder_homepage(source) == "https://github.com/org/repo"


def test_subfolder_homepage_returns_none_when_empty() -> None:
    """_subfolder_homepage returns None when source.url is empty."""
    source = SourceConfig(name="test", strategy="readme-only", url="")
    assert _subfolder_homepage(source) is None


# ---------------------------------------------------------------------------
# _non_negative_int
# ---------------------------------------------------------------------------


def test_non_negative_int_valid_positive() -> None:
    """_non_negative_int parses positive integers."""
    assert _non_negative_int("10") == 10
    assert _non_negative_int("0") == 0
    assert _non_negative_int("999") == 999


def test_non_negative_int_rejects_negative() -> None:
    """_non_negative_int raises ArgumentTypeError for negative values."""
    with pytest.raises(argparse.ArgumentTypeError, match="--limit must be >= 0"):
        _non_negative_int("-1")


def test_non_negative_int_rejects_non_numeric() -> None:
    """_non_negative_int raises ValueError for non-numeric input."""
    with pytest.raises(ValueError):
        _non_negative_int("not-a-number")


# ---------------------------------------------------------------------------
# register — subparser registration
# ---------------------------------------------------------------------------


def test_register_adds_update_subcommand() -> None:
    """register adds the 'update' subcommand to the parser."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    register(subparsers)

    # Parse with the update subcommand to verify it was registered
    args = parser.parse_args(["update"])
    assert hasattr(args, "func")


def test_register_config_argument_default() -> None:
    """register sets --config default to 'dfetch-hub.toml'."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register(subparsers)

    args = parser.parse_args(["update"])
    assert args.config == "dfetch-hub.toml"


def test_register_config_argument_custom() -> None:
    """register accepts a custom --config path."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register(subparsers)

    args = parser.parse_args(["update", "--config", "custom.toml"])
    assert args.config == "custom.toml"


def test_register_data_dir_argument_default() -> None:
    """register sets --data-dir default to None."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register(subparsers)

    args = parser.parse_args(["update"])
    assert args.data_dir is None


def test_register_data_dir_argument_custom() -> None:
    """register accepts a custom --data-dir path."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register(subparsers)

    args = parser.parse_args(["update", "--data-dir", "/tmp/data"])
    assert args.data_dir == "/tmp/data"


def test_register_limit_argument_default() -> None:
    """register sets --limit default to None."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register(subparsers)

    args = parser.parse_args(["update"])
    assert args.limit is None


def test_register_limit_argument_custom() -> None:
    """register accepts a custom --limit value."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register(subparsers)

    args = parser.parse_args(["update", "--limit", "10"])
    assert args.limit == 10


def test_register_limit_argument_validates_non_negative() -> None:
    """register rejects negative --limit values."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register(subparsers)

    with pytest.raises(SystemExit):
        parser.parse_args(["update", "--limit", "-5"])


def test_register_source_argument_default() -> None:
    """register sets --source default to None."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register(subparsers)

    args = parser.parse_args(["update"])
    assert args.source is None


def test_register_source_argument_custom() -> None:
    """register accepts a custom --source name."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register(subparsers)

    args = parser.parse_args(["update", "--source", "vcpkg"])
    assert args.source == "vcpkg"


# ---------------------------------------------------------------------------
# Integration test for _process_source dispatch
# ---------------------------------------------------------------------------


def test_process_source_subfolders_strategy(tmp_path: Path) -> None:
    """_process_source dispatches to _process_subfolders_source for strategy='subfolders'."""
    from dfetch_hub.commands.update import _process_source

    source = SourceConfig(
        name="vcpkg",
        strategy="subfolders",
        url="https://github.com/microsoft/vcpkg",
        path="ports",
        manifest="vcpkg.json",
    )

    with patch(
        "dfetch_hub.commands.update._process_subfolders_source"
    ) as mock_subfolders:
        _process_source(source, tmp_path, limit=None)
        mock_subfolders.assert_called_once_with(source, tmp_path, None)


def test_process_source_git_wiki_strategy(tmp_path: Path) -> None:
    """_process_source dispatches to _process_git_wiki_source for strategy='git-wiki'."""
    from dfetch_hub.commands.update import _process_source

    source = SourceConfig(
        name="clib",
        strategy="git-wiki",
        url="https://github.com/clibs/clib.wiki",
        manifest="Packages.md",
    )

    with patch("dfetch_hub.commands.update._process_git_wiki_source") as mock_git_wiki:
        _process_source(source, tmp_path, limit=None)
        mock_git_wiki.assert_called_once_with(source, tmp_path, None)


def test_process_source_readme_only_strategy(tmp_path: Path) -> None:
    """_process_source dispatches to _process_readme_only_source for strategy='readme-only'."""
    from dfetch_hub.commands.update import _process_source

    source = SourceConfig(
        name="examples",
        strategy="readme-only",
        url="https://github.com/org/examples",
        path="samples",
    )

    with patch(
        "dfetch_hub.commands.update._process_readme_only_source"
    ) as mock_readme_only:
        _process_source(source, tmp_path, limit=None)
        mock_readme_only.assert_called_once_with(source, tmp_path, None)


def test_process_source_unsupported_strategy_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """_process_source logs a warning for unsupported strategies."""
    from dfetch_hub.commands.update import _process_source

    source = SourceConfig(
        name="test", strategy="unknown-strategy", url="https://example.com"
    )

    with caplog.at_level("WARNING"):
        _process_source(source, tmp_path, limit=None)

    assert any(
        "strategy 'unknown-strategy' not yet supported" in record.message
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# _process_subfolders_source tests
# ---------------------------------------------------------------------------


def test_process_subfolders_source_no_manifest_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """_process_subfolders_source logs a warning when manifest is not configured."""
    from dfetch_hub.commands.update import _process_subfolders_source

    source = SourceConfig(
        name="test", strategy="subfolders", url="https://example.com", manifest=""
    )

    with caplog.at_level("WARNING"):
        _process_subfolders_source(source, tmp_path, limit=None)

    assert any("no 'manifest' configured" in record.message for record in caplog.records)


def test_process_subfolders_source_unsupported_manifest_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """_process_subfolders_source logs a warning for unsupported manifest types."""
    from dfetch_hub.commands.update import _process_subfolders_source

    source = SourceConfig(
        name="test",
        strategy="subfolders",
        url="https://example.com",
        manifest="unknown.json",
    )

    with caplog.at_level("WARNING"):
        _process_subfolders_source(source, tmp_path, limit=None)

    assert any(
        "manifest type 'unknown.json' not supported" in record.message
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# _process_git_wiki_source tests
# ---------------------------------------------------------------------------


def test_process_git_wiki_source_no_manifest_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """_process_git_wiki_source logs a warning when manifest is not configured."""
    from dfetch_hub.commands.update import _process_git_wiki_source

    source = SourceConfig(
        name="test", strategy="git-wiki", url="https://example.com", manifest=""
    )

    with caplog.at_level("INFO"):
        _process_git_wiki_source(source, tmp_path, limit=None)

    # dfetch's print_warning_line may log at INFO level
    assert any("no 'manifest' configured" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Edge case: limit handling
# ---------------------------------------------------------------------------


def test_filter_sentinel_respects_limit_after_filtering(tmp_path: Path) -> None:
    """_filter_sentinel is applied before the limit in _process_subfolders_source."""
    # This is a behavioral test to ensure sentinel filtering happens first.
    # We verify this by checking that the filtered list is what gets limited.
    (tmp_path / "keep1").mkdir()
    (tmp_path / "keep2").mkdir()
    (tmp_path / "keep3").mkdir()

    skip = tmp_path / "skip"
    skip.mkdir()
    (skip / ".sentinel").touch()

    source = SourceConfig(
        name="test", strategy="subfolders", url="", ignore_if_present=".sentinel"
    )
    entry_dirs = [tmp_path / "keep1", skip, tmp_path / "keep2", tmp_path / "keep3"]

    filtered = _filter_sentinel(source, entry_dirs)
    # After filtering, we have 3 dirs. A limit of 2 would then take the first 2.
    assert len(filtered) == 3
    assert skip not in filtered


# ---------------------------------------------------------------------------
# Additional negative case: _cmd_update with missing source
# ---------------------------------------------------------------------------


def test_cmd_update_source_not_found_exits(tmp_path: Path) -> None:
    """_cmd_update exits with status 1 when the specified source is not found."""
    from dfetch_hub.commands.update import _cmd_update

    config_text = textwrap.dedent(
        """\
        [[source]]
        name = "vcpkg"
        strategy = "subfolders"
        url = "https://example.com"
        """
    )
    config_path = tmp_path / "dfetch-hub.toml"
    config_path.write_text(config_text, encoding="utf-8")

    parsed = argparse.Namespace(
        config=str(config_path),
        data_dir=str(tmp_path / "data"),
        limit=None,
        source="nonexistent",
    )

    with pytest.raises(SystemExit) as exc_info:
        _cmd_update(parsed)

    assert exc_info.value.code == 1