# dfetch-hub — coding conventions

## Python style

- `from __future__ import annotations` at the top of every module.
- Modern union syntax: `str | None`, not `Optional[str]`.
- Use `TYPE_CHECKING` blocks for imports needed only by the type-checker (e.g. `Path`).
- `mypy --strict` must pass. Annotate every function, return type, and variable where the type is non-obvious.
- Max line length: **120** characters (enforced by pylint).
- Imports ordered: stdlib → third-party → local (`isort` + `black` via pre-commit).

## Docstrings

- Every public module, class, and function gets a docstring.
- Format: Google-style with `Args:`, `Returns:`, and `Raises:` sections where relevant.
- Dataclass docstrings list all fields under `Attributes:`.
- Private helpers may have a single-sentence summary only.

## Data model

- Use `@dataclass` for all structured data.
- Mutable defaults must use `field(default_factory=...)`.
- Shared structural interface: `ComponentManifest` Protocol in `updater.py` — new manifest types must satisfy it via
  duck-typing (no explicit inheritance needed). Optional extra fields (`topics`, `readme_content`, …) are accessed
  with `getattr(manifest, "field", default)` in the updater.

## Module structure

- Divide each module into logical sections separated by banner comments:
  ```python
  # ---------------------------------------------------------------------------
  # Section name
  # ---------------------------------------------------------------------------
  ```
- Typical sections (adapt as needed): helpers → data model → public API.
- Module-level regex/constants are compiled once at import time (UPPER_CASE names).

## Naming

| Kind | Convention |
|---|---|
| Classes | `PascalCase` |
| Functions / variables | `snake_case` |
| Module-private symbols | `_leading_underscore` |
| Constants | `UPPER_CASE` |

## Error handling

- Parsers return `None` on unrecoverable errors (never raise to the caller).
- Log unexpected conditions with `logger.warning(...)` or `logger.debug(...)`.
- Use `logger = get_logger(__name__)` from `dfetch.log`.
- Raise `RuntimeError` only for infrastructure failures (e.g. missing fetch output).

## Catalog pipeline conventions

- `fetch_source()` (fetcher.py) uses the dfetch Python API — no `subprocess`.
- External HTTP calls use stdlib `urllib.request` only — no `requests` dependency.
- GitHub org/repo values are **always lowercased** at extraction time so catalog IDs, file paths, and JSON fields
  stay consistent.
- New source strategies: add a parser module under `catalog/sources/`, register in the `_SUBFOLDER_PARSERS` dict
  or add a dispatch branch in `_process_source` inside `cli.py`.
- Limits are **per-source** (not global): slice or accept a `limit` parameter in each parser.

## Testing

- Pytest with `tmp_path` for temporary directories.
- Mock network/filesystem calls at the module boundary (`unittest.mock.patch`).
- Use `@pytest.mark.parametrize` for value-driven tests.
- Test data lives in module-level `_UPPER_CASE` constants.
- Tests must not hit the network or filesystem beyond `tmp_path`.

## Site / frontend

- The site source lives in `dfetch_hub/site/index.html` (single-file app).
- **Never edit `public/`** — that directory contains published build artifacts and is overwritten on deploy.
- Always make HTML/CSS/JS changes in `dfetch_hub/site/index.html`.

## Tooling

```
pre-commit run --all-files   # isort + black + pylint
.venv/bin/mypy dfetch_hub    # strict type check
.venv/bin/pytest             # full test suite
```
