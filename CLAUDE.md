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
- Mutable defaults must use `field(default_factory=list)` / `field(default_factory=dict)` — **never** `lambda: []` or
  `lambda: {}` (ruff PIE807).
- New manifest types inherit from `BaseManifest` (in `catalog/sources/__init__.py`). Optional extra fields (`topics`,
  `readme_content`, …) are accessed with `getattr(manifest, "field", default)` in the writer.

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

## Package resources

- **Never** use `Path(__file__)` to locate bundled files. Use `importlib.resources` instead:
  ```python
  import importlib.resources
  _DEFAULT_DATA_DIR: Path = Path(str(importlib.resources.files("dfetch_hub") / "data"))
  ```
- The `str()` + `Path()` conversion materialises the `Traversable` into a real filesystem path.
  This is safe because setuptools installs packages as directories, not zips.

## Catalog pipeline conventions

- `clone_source()` (catalog/cloner.py) uses the dfetch Python API — no `subprocess`.
- External HTTP calls use stdlib `urllib.request` only — no `requests` dependency.
- GitHub org/repo values are **always lowercased** at extraction time so catalog IDs, file paths, and JSON fields
  stay consistent.
- New source strategies: add a parser module under `catalog/sources/`, register in the `_MANIFEST_PARSERS` dict
  or add a dispatch branch in `_process_source` inside `commands/update.py`.
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

All tools live in `.venv/`. Activate the virtual environment before running any tool:

```bash
source .venv/bin/activate
pre-commit run --all-files   # full hook suite (must all pass before committing)
pytest                       # full test suite (206 tests, all mocked — no network)
```

### pre-commit hooks

| Hook | What it enforces |
|---|---|
| isort | Import order (stdlib → third-party → local, `profile = "black"`) |
| black | Code formatting, 120-char lines |
| ruff | Lint: `A B C4 E F G N PERF PIE PTH RET RSE RUF SIM T20 TCH TRY UP W` |
| pylint | Structural lint; design limits (see `[tool.pylint.design]` in `pyproject.toml`) |
| mypy | Strict type checking |
| pyright | Strict type checking (supplementary; some checks suppressed in `pyproject.toml`) |
| bandit | Security linting |
| xenon | Cyclomatic complexity: `--max-absolute B --max-modules A --max-average A` |
| pyroma | Package metadata quality |
| djlint | HTML linting |
| pydocstyle | Docstring style (Google convention) |
| doc8 | RST/Markdown style, 120-char lines |

### Code quality gotchas

- **pylint `too-many-locals`** counts function *parameters* as locals. Limit is 12 total
  (params + body variables). Inline a temporary variable or extract a helper to reduce the count.
- **ruff TC003**: imports from `collections.abc` or `pathlib` used *only in annotations* must live
  inside the `if TYPE_CHECKING:` block (safe with `from __future__ import annotations`).
- **ruff PIE807**: use `field(default_factory=list)` / `field(default_factory=dict)`, not lambdas.
- **xenon average A (≤ 5.0)**: extracting a helper lowers the module average even when the total CC
  sum stays the same — it adds a new block to the denominator.
- **suppress comments must be on the same line as the violation**, not on a trailing `)`. Black may
  move a trailing comment from `_fn(\n  arg\n)  # noqa` to the `)` line, detaching it from the
  actual offending expression. Put the comment on the opening `_fn(  # noqa` line instead.
- **`str(None) == "None"`** (truthy): when converting an `object` value to `str | None`, check
  `value` first — `return str(value) if value else None` — not `s = str(value); return s if s`.
