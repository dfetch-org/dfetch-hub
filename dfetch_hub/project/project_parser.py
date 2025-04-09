"""project parser module"""

from typing import Any, Dict, List

import yaml

from dfetch_hub.project.remote_datasource import RemoteProject


class ProjectParser:
    """class that parses python projects

    - used on projects found by project finder
    - parsed into sources which can be stored and monitored
    """

    def __init__(self) -> None:
        self._projects: List[RemoteProject] = []

    def add_project(self, new_project: RemoteProject) -> None:
        """add a project"""
        if new_project not in self._projects:
            self._projects += [new_project]

    def get_projects(self) -> List[RemoteProject]:
        """get all projects"""
        return self._projects

    def get_projects_as_yaml(self) -> str:
        """get yaml representation of projects"""
        yaml_str = ""
        yaml_obj: Dict[str, Any] = {"projects": []}
        for project in self._projects:
            yaml_obj["projects"] += [project.as_yaml()]
        yaml_str = yaml.dump(yaml_obj)
        return yaml_str

    @classmethod
    def from_yaml(cls, yaml_file: str) -> "ProjectParser":
        """create parser from yaml file"""
        with open(yaml_file, "r", encoding="utf-8") as yamlf:
            instance = cls()
            yaml_data = yaml.safe_load(yamlf.read())
            for project in yaml_data["projects"]:
                parsed_project = RemoteProject.from_yaml(project)
                instance.add_project(parsed_project)
        return instance
