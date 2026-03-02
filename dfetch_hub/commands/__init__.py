"""dfetch-hub subcommand modules."""

from __future__ import annotations

import sys
from pathlib import Path

from dfetch.log import get_logger

from dfetch_hub.config import HubConfig, load_config

_logger = get_logger(__name__)


def load_config_with_data_dir(
    config_path: str,
    data_dir_override: str | None,
    default_data_dir: Path,
) -> tuple[HubConfig, Path]:
    """Load *dfetch-hub.toml* and resolve the catalog data directory.

    Resolution order:
    1. *data_dir_override* (``--data-dir`` CLI flag), if provided.
    2. Parent directory of ``settings.catalog_path`` from the config, if set.
       A relative ``catalog_path`` is resolved against the directory that
       contains the config file (not the process working directory).
    3. *default_data_dir* as the final fallback.

    Args:
        config_path: Filesystem path to the TOML config file.
        data_dir_override: Explicit ``--data-dir`` value from the CLI, or ``None``.
        default_data_dir: Fallback path when neither the CLI flag nor
            ``settings.catalog_path`` is configured.

    Returns:
        A ``(config, data_dir)`` tuple.

    Raises:
        SystemExit: If the config file is not found.

    """
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        _logger.exception("Config file '%s' not found", config_path)
        sys.exit(1)

    if data_dir_override is not None:
        data_dir = Path(data_dir_override)
    elif config.settings.catalog_path:
        p = Path(config.settings.catalog_path)
        if not p.is_absolute():
            p = Path(config_path).resolve().parent / p
        data_dir = p.parent
    else:
        data_dir = default_data_dir

    return config, data_dir
