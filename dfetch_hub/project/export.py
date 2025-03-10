"""export module"""
from abc import ABC
from dfetch.manifest.manifest import Manifest, ManifestDict
from dfetch.manifest.project import ProjectEntry, ProjectEntryDict
from dfetch.manifest.remote import Remote, RemoteDict

class Export(ABC):

    def export(self):
        pass

class DfetchExport(Export):

    def __init__(self, entries=None):
        if entries:
            self._entries = entries
        else:
            self._entries = []

    def add_entry(self, entry):
        self._entries += [entry]

    @property
    def entries(self):
        return self._entries

    def export(self, path=None):
        remotes = [] # TODO: bundle projects with shared path in remotes
        projects = [ProjectEntryDict(name=entry.name, revision=entry.revision, src=entry.src, url=entry.url, repo_path=entry.repo_path, vcs=entry.vcs) for entry in self._entries]
        as_dict = ManifestDict(version = Manifest.CURRENT_VERSION, remotes=remotes,  projects=projects)
        if not path:
            path = "dfetch.yaml"
        Manifest(as_dict).dump(path)