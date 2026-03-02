"""Tests for dfetch_hub.catalog.conan: conanfile.py attribute parsing and recipe discovery."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from dfetch_hub.catalog.sources.conan import (
    ConanManifest,
    _attr_literal,
    _extract_str_attr,
    _extract_tuple_attr,
    _find_conanfile,
    _latest_version,
    _scan_paren_value,
    parse_conan_recipe,
)

# ---------------------------------------------------------------------------
# Shared conanfile.py fixtures
# ---------------------------------------------------------------------------

_CONANFILE_SIMPLE = textwrap.dedent(
    """\
    from conan import ConanFile

    class AbseilConan(ConanFile):
        name = "abseil"
        description = "Abseil Common Libraries (C++) from Google"
        topics = ("algorithm", "container", "google", "common", "utility")
        homepage = "https://github.com/abseil/abseil-cpp"
        url = "https://github.com/conan-io/conan-center-index"
        license = "Apache-2.0"

        def build(self):
            pass
    """
)

_CONANFILE_MULTILINE_DESC = textwrap.dedent(
    """\
    from conan import ConanFile

    class ZlibConan(ConanFile):
        name = "zlib"
        description = ("A Massively Spiffy Yet Delicately Unobtrusive Compression Library "
                       "(Also Free, Not to Mention Unencumbered by Patents)")
        homepage = "https://zlib.net"
        license = "Zlib"
        topics = ("compression", "deflate")
        url = "https://github.com/conan-io/conan-center-index"
    """
)

_CONFIG_YML = textwrap.dedent(
    """\
    versions:
      "1.0.0":
        folder: all
      "2.0.0":
        folder: all
      "3.1.0":
        folder: all
    """
)


@pytest.fixture(autouse=True)
def _mock_fetch_readme() -> object:
    """Prevent real network calls to fetch_readme in all conan tests."""
    with patch(
        "dfetch_hub.catalog.sources.conan.fetch_readme_for_homepage", return_value=None
    ):
        yield


@pytest.fixture
def recipe_dir(tmp_path: Path) -> Path:
    """Create a minimal recipe directory tree."""
    all_dir = tmp_path / "all"
    all_dir.mkdir()
    (all_dir / "conanfile.py").write_text(_CONANFILE_SIMPLE, encoding="utf-8")
    (tmp_path / "config.yml").write_text(_CONFIG_YML, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# _extract_str_attr
# ---------------------------------------------------------------------------


def test_extract_str_attr_simple() -> None:
    assert _extract_str_attr(_CONANFILE_SIMPLE, "name") == "abseil"


def test_extract_str_attr_homepage() -> None:
    assert (
        _extract_str_attr(_CONANFILE_SIMPLE, "homepage")
        == "https://github.com/abseil/abseil-cpp"
    )


def test_extract_str_attr_license() -> None:
    assert _extract_str_attr(_CONANFILE_SIMPLE, "license") == "Apache-2.0"


def test_extract_str_attr_multiline_description() -> None:
    desc = _extract_str_attr(_CONANFILE_MULTILINE_DESC, "description")
    assert desc is not None
    assert "Massively Spiffy" in desc
    assert "Unencumbered by Patents" in desc


def test_extract_str_attr_missing() -> None:
    assert _extract_str_attr(_CONANFILE_SIMPLE, "nonexistent") is None


# ---------------------------------------------------------------------------
# _extract_tuple_attr
# ---------------------------------------------------------------------------


def test_extract_tuple_attr_topics() -> None:
    topics = _extract_tuple_attr(_CONANFILE_SIMPLE, "topics")
    assert "algorithm" in topics
    assert "google" in topics
    assert len(topics) == 5


def test_extract_tuple_attr_missing() -> None:
    assert _extract_tuple_attr(_CONANFILE_SIMPLE, "nonexistent") == []


# ---------------------------------------------------------------------------
# _latest_version
# ---------------------------------------------------------------------------


def test_latest_version_returns_last_key(tmp_path: Path) -> None:
    config = tmp_path / "config.yml"
    config.write_text(_CONFIG_YML, encoding="utf-8")
    version, folder = _latest_version(config)
    assert version == "3.1.0"
    assert folder == "all"


def test_latest_version_missing_file(tmp_path: Path) -> None:
    version, folder = _latest_version(tmp_path / "config.yml")
    assert version is None
    assert folder == "all"


def test_latest_version_single_entry(tmp_path: Path) -> None:
    config = tmp_path / "config.yml"
    config.write_text('versions:\n  "1.3.1":\n    folder: all\n', encoding="utf-8")
    version, _ = _latest_version(config)
    assert version == "1.3.1"


# ---------------------------------------------------------------------------
# parse_conan_recipe
# ---------------------------------------------------------------------------


def test_parse_conan_recipe_basic(recipe_dir: Path) -> None:
    m = parse_conan_recipe(recipe_dir)
    assert m is not None
    assert m.package_name == "abseil"
    assert m.description == "Abseil Common Libraries (C++) from Google"
    assert m.homepage == "https://github.com/abseil/abseil-cpp"
    assert m.license == "Apache-2.0"
    assert "algorithm" in m.topics
    assert "google" in m.topics


def test_parse_conan_recipe_latest_version(recipe_dir: Path) -> None:
    m = parse_conan_recipe(recipe_dir)
    assert m is not None
    assert m.version == "3.1.0"


def test_parse_conan_recipe_entry_name_is_dir_name(recipe_dir: Path) -> None:
    m = parse_conan_recipe(recipe_dir)
    assert m is not None
    assert m.entry_name == recipe_dir.name


def test_parse_conan_recipe_no_conanfile_returns_none(tmp_path: Path) -> None:
    (tmp_path / "config.yml").write_text(
        'versions:\n  "1.0":\n    folder: all\n', encoding="utf-8"
    )
    # No conanfile.py created
    assert parse_conan_recipe(tmp_path) is None


def test_parse_conan_recipe_falls_back_to_any_subfolder(tmp_path: Path) -> None:
    """When config.yml points to a missing folder, fall back to scanning subdirs."""
    (tmp_path / "config.yml").write_text(
        'versions:\n  "1.0":\n    folder: 1.x\n', encoding="utf-8"
    )
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / "conanfile.py").write_text(_CONANFILE_SIMPLE, encoding="utf-8")

    m = parse_conan_recipe(tmp_path)
    assert m is not None
    assert m.package_name == "abseil"


def test_parse_conan_recipe_multiline_description(tmp_path: Path) -> None:
    all_dir = tmp_path / "all"
    all_dir.mkdir()
    (all_dir / "conanfile.py").write_text(_CONANFILE_MULTILINE_DESC, encoding="utf-8")
    (tmp_path / "config.yml").write_text(
        'versions:\n  "1.3.1":\n    folder: all\n', encoding="utf-8"
    )

    m = parse_conan_recipe(tmp_path)
    assert m is not None
    assert "Massively Spiffy" in m.description
    assert m.license == "Zlib"
    assert "compression" in m.topics


def test_parse_conan_recipe_nonexistent_dir_returns_none(tmp_path: Path) -> None:
    """Returns None when the recipe directory does not exist."""
    assert parse_conan_recipe(tmp_path / "nonexistent") is None


def test_parse_conan_recipe_returns_none_on_conanfile_read_oserror(
    recipe_dir: Path,
) -> None:
    """Returns None when conanfile.py raises OSError on read."""
    with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
        result = parse_conan_recipe(recipe_dir)

    assert result is None


# ---------------------------------------------------------------------------
# _latest_version — non-dict branches
# ---------------------------------------------------------------------------


def test_latest_version_returns_none_for_non_dict_yaml(tmp_path: Path) -> None:
    """Returns (None, 'all') when YAML root is not a dict (e.g. a bare string)."""
    config = tmp_path / "config.yml"
    config.write_text("just a string\n", encoding="utf-8")

    version, folder = _latest_version(config)

    assert version is None
    assert folder == "all"


def test_latest_version_returns_none_for_non_dict_versions(tmp_path: Path) -> None:
    """Returns (None, 'all') when 'versions' key maps to a list, not a dict."""
    config = tmp_path / "config.yml"
    config.write_text("versions: [1, 2, 3]\n", encoding="utf-8")

    version, folder = _latest_version(config)

    assert version is None
    assert folder == "all"


# ---------------------------------------------------------------------------
# _scan_paren_value — escape and nesting branches
# ---------------------------------------------------------------------------


def test_scan_paren_value_handles_escaped_quote() -> None:
    """Escaped quote inside a string does not end the string early."""
    # ("hello \"world\"") → balanced parens with escape sequences
    text = '("hello \\"world\\"")'
    result = _scan_paren_value(text, 0)
    assert result == text  # entire paren group returned


def test_scan_paren_value_handles_nested_parens() -> None:
    """Nested parentheses increment and decrement depth correctly."""
    text = "(outer (inner) end)"
    result = _scan_paren_value(text, 0)
    assert result == text


# ---------------------------------------------------------------------------
# _attr_literal / _extract_str_attr — edge cases
# ---------------------------------------------------------------------------


def test_attr_literal_returns_none_for_non_string_non_paren_value() -> None:
    """Returns None when the character after '=' is neither '(' nor a quote."""
    assert _attr_literal("    version = 42", "version") is None


def test_attr_literal_returns_none_on_literal_eval_failure() -> None:
    """Returns None when ast.literal_eval raises (e.g. unclosed string)."""
    # No closing quote → end_q == -1 → value_text is unparseable
    assert _attr_literal('    name = "unclosed', "name") is None


def test_extract_str_attr_joins_tuple_of_strings() -> None:
    """A parenthesised tuple of strings is joined into a single string."""
    text = '    description = ("part one", "part two")'
    result = _extract_str_attr(text, "description")
    assert result == "part onepart two"


def test_extract_tuple_attr_with_nested_parens() -> None:
    """Nested parens inside a tuple value are scanned correctly."""
    # The inner tuple (("a", "b")) makes depth go to 2 in _scan_paren_value.
    # Only the outer string "c" passes the isinstance(v, str) filter.
    text = '    topics = (("a", "b"), "c")'
    result = _extract_tuple_attr(text, "topics")
    assert result == ["c"]


# ---------------------------------------------------------------------------
# _find_conanfile — error / fallback branches
# ---------------------------------------------------------------------------


def test_find_conanfile_returns_none_for_nonexistent_dir(tmp_path: Path) -> None:
    """Returns None when recipe_dir does not exist."""
    result = _find_conanfile(tmp_path / "nonexistent", "all")
    assert result is None


def test_find_conanfile_returns_none_on_iterdir_oserror(tmp_path: Path) -> None:
    """Returns None when iterating subdirectories raises OSError."""
    with patch.object(Path, "iterdir", side_effect=OSError("permission denied")):
        result = _find_conanfile(tmp_path, "preferred")

    assert result is None


# ---------------------------------------------------------------------------
# parse_conan_recipe — urls dict
# ---------------------------------------------------------------------------


def test_parse_conan_recipe_urls_contains_homepage(recipe_dir: Path) -> None:
    """urls dict includes 'Homepage' when conanfile.py has a homepage attribute."""
    m = parse_conan_recipe(recipe_dir)
    assert m is not None
    assert m.urls.get("Homepage") == "https://github.com/abseil/abseil-cpp"


def test_parse_conan_recipe_urls_contains_source(recipe_dir: Path) -> None:
    """urls dict includes 'Source' when conanfile.py has a url attribute."""
    m = parse_conan_recipe(recipe_dir)
    assert m is not None
    assert m.urls.get("Source") == "https://github.com/conan-io/conan-center-index"


def test_parse_conan_recipe_urls_empty_without_homepage(tmp_path: Path) -> None:
    """urls dict is empty when conanfile.py has no homepage or url attributes."""
    minimal = 'from conan import ConanFile\n\nclass Pkg(ConanFile):\n    name = "pkg"\n'
    all_dir = tmp_path / "all"
    all_dir.mkdir()
    (all_dir / "conanfile.py").write_text(minimal, encoding="utf-8")
    (tmp_path / "config.yml").write_text(
        'versions:\n  "1.0":\n    folder: all\n', encoding="utf-8"
    )

    m = parse_conan_recipe(tmp_path)
    assert m is not None
    assert m.urls == {}
