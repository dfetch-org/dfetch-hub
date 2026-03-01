"""Parse conan-center-index recipe directories into catalog manifests."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import yaml
from dfetch.log import get_logger

from dfetch_hub.catalog.sources import BaseManifest, fetch_readme_for_homepage

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# conanfile.py attribute extraction helpers
# ---------------------------------------------------------------------------


def _scan_paren_value(text: str, start: int) -> str:
    """Return the substring from *start* (a ``(`` character) to its matching ``)``."""
    depth = 1
    i = start + 1
    in_str = False
    str_char = ""
    while i < len(text) and depth > 0:
        ch = text[i]
        if in_str:
            if ch == "\\" and i + 1 < len(text):
                i += 1
            elif ch == str_char:
                in_str = False
        else:
            if ch in ('"', "'"):
                in_str, str_char = True, ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
        i += 1
    return text[start:i]


def _attr_literal(text: str, attr: str) -> Any:
    """Locate *attr* in *text* and return its value via ``ast.literal_eval``."""
    m = re.search(rf"^\s+{re.escape(attr)}\s*=\s*", text, re.MULTILINE)
    if not m:
        return None
    pos = m.end()
    ch = text[pos] if pos < len(text) else ""
    if ch == "(":
        value_text = _scan_paren_value(text, pos)
    elif ch in ('"', "'"):
        end_q = text.find(ch, pos + 1)
        value_text = text[pos : end_q + 1] if end_q != -1 else text[pos:]
    else:
        return None
    try:
        return ast.literal_eval(value_text)
    except (ValueError, SyntaxError):
        return None


def _extract_str_attr(text: str, attr: str) -> str | None:
    """Extract a string-valued class attribute from a ``conanfile.py``.

    Handles single-line and parenthesised (possibly multi-line) forms.
    """
    val = _attr_literal(text, attr)
    if isinstance(val, str):
        return val
    if isinstance(val, (tuple, list)) and val and isinstance(val[0], str):
        return "".join(str(v) for v in val)
    return None


def _extract_tuple_attr(text: str, attr: str) -> list[str]:
    """Extract a tuple-valued class attribute from a ``conanfile.py``.

    Handles: ``attr = ("val1", "val2")``
    """
    val = _attr_literal(text, attr)
    if isinstance(val, (tuple, list)):
        return [str(v) for v in val if isinstance(v, str)]
    return []


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ConanManifest(BaseManifest):
    """Parsed metadata for a single conan-center-index recipe.

    Attributes:
        topics: ``topics`` tuple from ``conanfile.py``.
    """

    topics: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# config.yml helpers
# ---------------------------------------------------------------------------


def _latest_version(config_path: Path) -> tuple[str | None, str]:
    """Return ``(version, subfolder)`` from ``config.yml``, or ``(None, 'all')``."""
    try:
        loaded: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return None, "all"
        versions_obj = loaded.get("versions", {})
        if not isinstance(versions_obj, dict):
            return None, "all"
        versions: dict[str, Any] = versions_obj
        if versions:
            latest = list(versions)[-1]
            latest_meta = versions.get(latest)
            folder = (
                str(latest_meta.get("folder", "all"))
                if isinstance(latest_meta, dict)
                else "all"
            )
            return latest, folder
    except (OSError, yaml.YAMLError) as exc:
        logger.debug("Could not parse %s: %s", config_path, exc)
    return None, "all"


def _find_conanfile(recipe_dir: Path, preferred_folder: str) -> Path | None:
    """Return the path to ``conanfile.py`` inside *recipe_dir*.

    Tries *preferred_folder* first, then falls back to any subdirectory.
    """
    preferred = recipe_dir / preferred_folder / "conanfile.py"
    if preferred.exists():
        return preferred

    for sub in sorted(recipe_dir.iterdir()):
        if sub.is_dir():
            candidate = sub / "conanfile.py"
            if candidate.exists():
                return candidate

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_conan_recipe(recipe_dir: Path) -> ConanManifest | None:
    """Parse a single conan-center-index recipe directory.

    The directory layout is::

        <recipe_dir>/
            config.yml          # version → subfolder mapping
            all/                # or a version-specific subfolder
                conanfile.py    # metadata: name, description, homepage, …
                conandata.yml   # source archives per version

    Args:
        recipe_dir: Path to the recipe directory (e.g. ``recipes/zlib``).

    Returns:
        A :class:`ConanManifest` on success, or ``None`` if no ``conanfile.py``
        is found or the file cannot be read.
    """
    version, preferred_folder = _latest_version(recipe_dir / "config.yml")

    conanfile = _find_conanfile(recipe_dir, preferred_folder)
    if conanfile is None:
        logger.debug("No conanfile.py found in %s", recipe_dir)
        return None

    try:
        text = conanfile.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("Could not read %s: %s", conanfile, exc)
        return None

    name = _extract_str_attr(text, "name") or recipe_dir.name
    description = _extract_str_attr(text, "description") or ""
    homepage = _extract_str_attr(text, "homepage")
    license_val = _extract_str_attr(text, "license") or None
    topics = _extract_tuple_attr(text, "topics")

    return ConanManifest(
        port_name=recipe_dir.name,
        package_name=name,
        description=description,
        homepage=homepage,
        license=license_val,
        version=version,
        topics=topics,
        readme_content=fetch_readme_for_homepage(homepage),
    )
