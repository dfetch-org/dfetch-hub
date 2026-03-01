"""Format-specific source parsers (vcpkg, conan, clib)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BaseManifest:
    """Shared base fields for all catalog manifest dataclasses.

    Attributes:
        port_name:    Unique identifier within the source registry.
        package_name: Human-readable package name (may differ from port_name).
        description:  Short description of the package.
        homepage:     Upstream project URL, or ``None`` if unknown.
        license:      SPDX license expression, or ``None`` if unspecified.
        version:      Latest version string, or ``None`` if unavailable.
    """

    port_name: str
    package_name: str
    description: str
    homepage: str | None
    license: str | None
    version: str | None
