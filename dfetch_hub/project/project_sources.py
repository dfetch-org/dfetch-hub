"""project sources module"""

from typing import Optional, Sequence

import yaml
from dfetch.manifest.remote import Remote

from dfetch_hub.project.input_parser import InputParser


class RemoteSource(Remote):
    """class representing source for projects"""

    def __init__(self, args):
        super().__init__(args)
        self.exclusions: Optional[Sequence] = None

    def add_exclusion(self, exclusion_regex: str):
        """add exclusion to project source"""
        if not self.exclusions:
            self.exclusions = [exclusion_regex]
        else:
            self.exclusions += [exclusion_regex]

    def as_yaml(self):
        """get yaml representation"""
        yaml_data = super().as_yaml()
        yaml_data["exclusions"] = self.exclusions
        return {k: v for k, v in yaml_data.items() if v}

    def __eq__(self, other):
        if isinstance(other, RemoteSource):
            if hasattr(self, "exclusions"):
                if not hasattr(other, "exclusions"):
                    return False
                return (
                    self.name == other.name
                    and self.url == other.url
                    and self.exclusions == other.exclusions
                )
            if hasattr(other, "exclusions"):
                return False
            return self.name == other.name and self.url == other.url
        return False


class SourceList:
    """class representing a sequence of project sources"""

    CURRENT_VERSION = "0.0"

    def __init__(self):
        self._sources: Sequence[RemoteSource] = []

    def add_remote(self, source: RemoteSource):
        """add source"""
        self._sources += [source]

    def get_remotes(self) -> list[RemoteSource]:
        """get list of sources"""
        return self._sources

    def as_yaml(self):
        """yaml representation"""
        versiondata = {"version": self.CURRENT_VERSION}
        remotes_data = {"remotes": [source.as_yaml() for source in self._sources]}
        yamldata = {"source-list": [versiondata, remotes_data]}
        return yaml.dump(yamldata)

    @classmethod
    def from_yaml(cls, yaml_data):
        """load from sources files"""
        if not yaml_data:
            raise ValueError("failed to load data from file")
        instance = cls()
        yaml_data = yaml.load(yaml_data, Loader=yaml.Loader)
        assert yaml_data, "file should have data"
        assert yaml_data["source-list"], "file should have list of sources"
        version = [i["version"] for i in yaml_data["source-list"] if "version" in i][0]
        remotes = [i["remotes"] for i in yaml_data["source-list"] if "remotes" in i][0]
        if version != cls.CURRENT_VERSION:
            raise ValueError("invalid version")

        for source in remotes:
            src = RemoteSource({"name": source["name"], "url-base": source["url-base"]})
            if "exclusions" in source:
                for excl in source["exclusions"]:
                    src.add_exclusion(excl)
            instance.add_remote(src)
        return instance

    @classmethod
    def from_input_parser(cls, parser: InputParser):
        """generate instance from parser"""
        instance = cls()
        for url in parser.get_urls():
            name = url.split("/")[-1]
            src = RemoteSource({"name": name, "url-base": url})
            instance.add_remote(src)
        return instance

    def __eq__(self, other):
        if isinstance(other, SourceList):
            return (
                self._sources == other._sources
                and self.CURRENT_VERSION == other.CURRENT_VERSION
            )
        return False
