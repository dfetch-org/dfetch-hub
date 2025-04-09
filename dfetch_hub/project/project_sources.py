"""project sources module"""

from argparse import Namespace
from typing import Any, Dict, List, Optional, Union

import yaml
from dfetch.manifest.remote import Remote

from dfetch_hub.project.input_parser import InputParser


class RemoteSource(Remote):  # type: ignore
    """class representing source for projects"""

    def __init__(self, args: Union[Namespace, Dict[str, str]]):
        super().__init__(args)
        self.exclusions: List[str] = []

    def add_exclusion(self, exclusion_regex: str) -> None:
        """add exclusion to project source"""
        if not self.exclusions:
            self.exclusions = [exclusion_regex]
        else:
            self.exclusions += [exclusion_regex]

    def as_yaml(self) -> Dict[str, Any]:
        """get yaml representation"""
        yaml_data = super().as_yaml()
        yaml_data["exclusions"] = self.exclusions
        return {k: v for k, v in yaml_data.items() if v}

    def __eq__(self, other: Any) -> bool:
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
            return bool(self.name == other.name and self.url == other.url)
        return False


class SourceList:
    """class representing a sequence of project sources"""

    CURRENT_VERSION = "0.0"

    def __init__(self) -> None:
        self._sources: List[RemoteSource] = []

    def add_remote(self, source: RemoteSource) -> None:
        """add source"""
        self._sources += [source]

    def get_remotes(self) -> List[RemoteSource]:
        """get list of sources"""
        return self._sources

    def as_yaml(self) -> str:
        """yaml representation"""
        versiondata = {"version": self.CURRENT_VERSION}
        remotes_data = {"remotes": [source.as_yaml() for source in self._sources]}
        yamldata = {"source-list": [versiondata, remotes_data]}
        return yaml.dump(yamldata)

    @classmethod
    def from_yaml(cls, yaml_data: Union[str, bytes]) -> "SourceList":
        """load from sources files"""
        if not yaml_data:
            raise ValueError("failed to load data from file")

        instance = cls()

        parsed_yaml: Optional[Dict[str, Any]] = yaml.load(yaml_data, Loader=yaml.Loader)
        if not parsed_yaml:
            raise RuntimeError("file should have data")
        assert parsed_yaml["source-list"], "file should have list of sources"
        version = [i["version"] for i in parsed_yaml["source-list"] if "version" in i][
            0
        ]
        remotes = [i["remotes"] for i in parsed_yaml["source-list"] if "remotes" in i][
            0
        ]
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
    def from_input_parser(cls, parser: InputParser) -> "SourceList":
        """generate instance from parser"""
        instance = cls()
        for url in parser.get_urls():
            name = url.split("/")[-1]
            src = RemoteSource({"name": name, "url-base": url})
            instance.add_remote(src)
        return instance

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, SourceList):
            return (
                self._sources == other._sources
                and self.CURRENT_VERSION == other.CURRENT_VERSION
            )
        return False
