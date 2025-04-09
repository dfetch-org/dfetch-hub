"""Module that handles the export of the list of projects."""

from abc import ABC
from dataclasses import dataclass
from typing import List, Optional, Sequence, Union

from dfetch.manifest.manifest import Manifest, ManifestDict
from dfetch.manifest.project import ProjectEntryDict
from dfetch.manifest.remote import Remote, RemoteDict


@dataclass
class Entry:
    """Entry to export."""

    name: str
    revision: str
    src: str
    url: str
    repo_path: str
    vcs: str = "git"


class Export(ABC):
    """Abstract Export interface."""

    def add_entry(self, entry: Entry) -> None:
        """Add entry to export."""

    def export(self) -> None:
        """Export the projects."""


class DfetchExport(Export):
    """Dfetch specific exporter."""

    def __init__(self, entries: Optional[List[Entry]] = None):
        if entries:
            self._entries = entries
        else:
            self._entries = []

    def add_entry(self, entry: Entry) -> None:
        """Add entry to export."""
        self._entries.append(entry)

    @property
    def entries(self) -> List[Entry]:
        """All entries in export."""
        return self._entries

    def export(self, path: str = "") -> None:
        """Export the DFetch manifest to path."""
        remotes: Sequence[Union[RemoteDict, Remote]] = (
            []
        )  # Use _create_remotes from import function to bundle projects with shared path in remotes

        projects = [
            ProjectEntryDict(
                name=entry.name,
                revision=entry.revision,
                src=entry.src,
                url=entry.url,
                repo_path=entry.repo_path,
                vcs=entry.vcs,
            )
            for entry in self._entries
        ]
        as_dict = ManifestDict(
            version=Manifest.CURRENT_VERSION, remotes=remotes, projects=projects
        )
        if not path:
            path = "dfetch.yaml"
        Manifest(as_dict).dump(path)
