# dfetch-hub

[![Contribute with Codespaces](https://img.shields.io/static/v1?label=Codespaces&message=Open&color=blue)](https://codespaces.new/dfetch-org/dfetch-hub)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)

A catalog browser and static-site generator for [dfetch](https://dfetch-org.github.io/) package registries.
Search, discover, and compose `dfetch.yaml` manifests from thousands of reusable components —
regardless of language or build system.

---

## What problem does it solve?

[dfetch](https://dfetch-org.github.io/) ([docs](https://dfetch.readthedocs.io/)) is a
source-only, VCS-agnostic dependency aggregator. It vendors dependencies directly into your
project by cloning Git (or SVN) repositories at a specific ref — no submodules, no subtrees.
The same workflow handles C libraries, Rust crates, TypeScript packages, Kotlin modules, and
anything else that lives in a repository.

The missing piece is **discovery**. When you need a networking helper, a JSON parser, or a
logging framework, where do you look? How do you find the canonical Git URL, pick the right
tag, and wire it into your `dfetch.yaml`?

**dfetch-hub** answers that question. It:

1. **Crawls** existing package registries (vcpkg, Conan Center Index, clib, and custom sources)
   and normalises their metadata into a unified catalog.
2. **Serves** a searchable web UI so you can browse and filter components by name, description,
   license, source registry, or language.
3. **Publishes** the catalog as a fully static site that can be hosted anywhere — no server
   required.

The result is a single place to find a component, check its available tags, read its README,
and copy the `dfetch.yaml` snippet that vendors it into your project.

---

## Key concepts

| Term | Meaning |
|------|---------|
| **Component** | A self-contained, reusable unit of source code living in a Git repository. Language-agnostic. |
| **Source** | A package registry or monorepo that dfetch-hub crawls (e.g. vcpkg, Conan, clib). |
| **Catalog** | The normalized JSON database of all discovered components. |
| **dfetch.yaml** | The project manifest consumed by dfetch to vendor dependencies into your codebase. |

A `dfetch.yaml` manifest looks like this:

```yaml
manifest:
  version: '0.0'
  projects:
    - name: network-utils
      url: https://github.com/user/network-utils.git
      tag: v1.0.0
    - name: io-helpers
      url: https://github.com/org/io-helpers.git
      branch: main
```

Key manifest attributes: `url`, `tag`, `branch`, `revision` (full SHA), `src` (partial
checkout of a subfolder), `dst` (destination path), `ignore` (files to exclude).
See the [dfetch manifest reference](https://dfetch.readthedocs.io/en/latest/manifest.html)
for the full syntax.

dfetch does not care whether the component is C, Rust, Java, or TypeScript — it clones the
source tree. dfetch-hub supplies the metadata (Git URL, available tags, README, license) so
you can make that choice confidently.

---

## Supported source registries

| Registry | Manifest parsed | Notes |
|----------|----------------|-------|
| [vcpkg](https://github.com/microsoft/vcpkg) | `vcpkg.json` + `portfile.cmake` | Upstream repo extracted from `vcpkg_from_github()` |
| [Conan Center Index](https://github.com/conan-io/conan-center-index) | `conandata.yml` + `conanfile.py` | Full attribute extraction via AST |
| [clib](https://github.com/clibs/clib) | `Packages.md` wiki + per-package `package.json` | Category tags preserved |
| Custom Git repos | `README` (fallback) | Works for monorepos with subfolder components |

New sources are added by writing a small manifest parser and registering it in `dfetch-hub.toml`.

---

## Installation

**Requirements:** Python 3.11 or later.

```console
pip install dfetch-hub
```

For development (includes all linters, formatters, and test dependencies):

```console
git clone https://github.com/dfetch-org/dfetch-hub.git
cd dfetch-hub
pip install -e ".[development]"
pre-commit install
```

---

## Quick start

### 1. Update the catalog

Pull fresh metadata from all configured sources:

```console
dfetch-hub update
```

Use `--limit N` during development to cap the number of packages fetched per source:

```console
dfetch-hub update --limit 10
```

Target a single source by name:

```console
dfetch-hub update --source vcpkg
```

### 2. Browse the catalog locally

Launch a local web server and open the browser automatically:

```console
dfetch-hub serve
```

Navigate to `http://127.0.0.1:8000`, type a package name in the search bar, and explore.
Press `/` to jump to the search box. Press `Ctrl+K` for keyboard shortcuts.

### 3. Publish a static site

Build a deployable artifact (suitable for GitHub Pages, Netlify, etc.):

```console
dfetch-hub publish
```

The output lands in `public/` by default. All paths are rewritten so the site works
without a local dev server.

---

## Configuration

dfetch-hub is configured with a `dfetch-hub.toml` file in the current working directory.

```toml
[settings]
concurrency = 8          # parallel fetch workers
catalog_path = "dfetch_hub/data"
output_dir   = "public"

[[source]]
name     = "vcpkg"
strategy = "subfolders"
url      = "https://github.com/microsoft/vcpkg"
path     = "ports"
manifest = "vcpkg.json"
label    = "vcpkg"

[[source]]
name     = "conan"
strategy = "subfolders"
url      = "https://github.com/conan-io/conan-center-index"
path     = "recipes"
manifest = "conandata.yml"
label    = "conan"

[[source]]
name     = "clib"
strategy = "git-wiki"
url      = "https://github.com/clibs/clib.wiki.git"
manifest = "Packages.md"
label    = "clib"

[auth]
github_token = "GITHUB_TOKEN"   # environment variable name (not the token itself)
```

### Source strategies

| Strategy | Description |
|----------|-------------|
| `subfolders` | Each subdirectory under `path` is treated as one component. |
| `git-wiki` | Clones a Git wiki and parses a markdown index file for component URLs. |

### `ignore_if_present`

Skip a subfolder if it contains a specific file or directory — useful for filtering
versioned recipe trees like Conan's:

```toml
[[source]]
name              = "conan"
strategy          = "subfolders"
url               = "https://github.com/conan-io/conan-center-index"
path              = "recipes"
manifest          = "conandata.yml"
ignore_if_present = "conanfile.py"   # skip top-level recipe dir; descend into version dirs
```

---

## Workflow overview

```
Git Repos (any language)
        │
        ▼
 Crawler & Manifest Parsers
 (vcpkg · Conan · clib · README)
        │
        ▼
  Catalog JSON files
  (catalog.json + per-project detail files)
        │
        ▼
  Static Web UI  ──▶  dfetch-hub serve / dfetch-hub publish
        │
        ▼
  User selects a component and ref
        │
        ▼
  dfetch.yaml snippet  ──▶  dfetch update  ──▶  vendored sources
```

---

## CLI reference

```
dfetch-hub <command> [options]

Commands:
  update    Fetch sources and rebuild the catalog.
  serve     Launch a local web server to browse the catalog.
  publish   Build a deployable static site from catalog data.

dfetch-hub update
  --config FILE        Path to dfetch-hub.toml  [default: dfetch-hub.toml]
  --data-dir DIR       Catalog output directory  [default: from config]
  --limit N            Max packages per source (useful for testing)
  --source NAME        Process only this source

dfetch-hub serve
  --port PORT          HTTP port  [default: 8000]

dfetch-hub publish
  --config FILE        Path to dfetch-hub.toml  [default: dfetch-hub.toml]
  --output DIR         Output directory          [default: public/]
```

---

## Development

```console
# Activate the virtual environment
source .venv/bin/activate

# Run the full test suite (206 tests, fully mocked — no network required)
pytest

# Run all pre-commit hooks
pre-commit run --all-files
```

The test suite mocks all network and filesystem calls. Tests must not hit the network or
write outside `tmp_path`.

---

## License

MIT — see [LICENSE](LICENSE).
