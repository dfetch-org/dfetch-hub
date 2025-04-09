"""export module"""

from abc import ABC
from dataclasses import dataclass
from typing import List, Optional, Sequence, Union

from dfetch.manifest.manifest import Manifest, ManifestDict
from dfetch.manifest.project import ProjectEntryDict
from dfetch.manifest.remote import Remote, RemoteDict


@dataclass
class Entry:
    name: str
    revision: str
    src: str
    url: str
    repo_path: str
    vcs: str = "git"


class Export(ABC):

    def export(self) -> None:
        pass


class DfetchExport(Export):

    def __init__(self, entries: Optional[List[Entry]] = None):
        if entries:
            self._entries = entries
        else:
            self._entries = []

    def add_entry(self, entry: Entry) -> None:
        self._entries += [entry]

    @property
    def entries(self) -> List[Entry]:
        return self._entries

    def export(self, path: str = "") -> None:
        remotes: Sequence[Union[RemoteDict, Remote]] = (
            []
        )  # TODO: bundle projects with shared path in remotes
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
