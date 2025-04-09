"""remote datasource module"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class RemoteRef:
    """representation of a single remote reference"""

    name: str
    revision: str  # chosen for dfetch naming

    def as_yaml(self) -> Dict[str, str]:
        """yaml representation of reference"""
        yamldata = {"name": self.name, "revision": self.revision}
        return {k: v for k, v in yamldata.items() if v}

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.name == other
        if isinstance(other, RemoteRef):
            return self.name == other.name and self.revision == other.revision
        return False


class RemoteProjectVersions:
    """representation of collection of versions for project"""

    def __init__(self, vcs: str = ""):
        self.tags: List[RemoteRef] = []
        self.branches: List[RemoteRef] = []
        self.vcs = vcs

    def add_tags(self, tags: Sequence[Tuple[str, str]]) -> None:
        """add tags"""
        for hash_val, tag_name in tags:
            if tag_name not in [tag.name for tag in self.tags]:
                self.tags.append(RemoteRef(tag_name, hash_val))

    def add_branches(self, branches: Sequence[Tuple[str, str]]) -> None:
        """add branches"""
        for hash_val, branch_name in branches:
            if branch_name not in [branch.name for branch in self.branches]:
                self.branches.append(RemoteRef(branch_name, hash_val))

    @property
    def default(self) -> str:
        """get default branch"""
        if not self.vcs or self.vcs == "git":
            return "main" if "main" in self.branches else "master"
        if self.vcs == "svn":
            return "trunk"
        raise ValueError("no default version known for repository")

    def as_yaml(self) -> Dict[str, Any]:
        """get yaml representation"""
        default = None
        try:
            default = self.default
        except ValueError:
            pass
        yamldata = {
            "default": default,
            "tags": [tag.as_yaml() for tag in self.tags],
            "branches": [branch.as_yaml() for branch in self.branches],
        }
        return {k: v for k, v in yamldata.items() if v}

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, RemoteProjectVersions):
            return other.branches == self.branches and other.tags == self.tags
        return False


class RemoteProject:
    """representation of remote repository project"""

    def __init__(
        self,
        name: str,
        url: str,
        repo_path: str,
        src: str,
        vcs: str,
        versions: Optional[RemoteProjectVersions] = None,
    ):  # pylint:disable=too-many-arguments,too-many-positional-arguments
        self.name = name
        self.url = url
        self.repo_path = repo_path
        self.src = src
        self.vcs = vcs
        self.versions = versions if versions else RemoteProjectVersions()

    def add_versions(
        self, branches: Sequence[Tuple[str, str]], tags: Sequence[Tuple[str, str]]
    ) -> None:
        """add branches and tags"""
        if not hasattr(self, "versions"):
            self.versions = RemoteProjectVersions(self.vcs)
        self.versions.add_branches(branches)
        self.versions.add_tags(tags)

    def as_yaml(self) -> Dict[str, Any]:
        """get yaml representation"""
        yamldata = {
            "name": self.name,
            "versions": (
                None if not hasattr(self, "versions") else self.versions.as_yaml()
            ),
            "src": self.src,
            "url": self.url,
            "repo-path": self.repo_path,
            "vcs": None if not hasattr(self, "vcs") else self.vcs,
        }
        return {k: v for k, v in yamldata.items() if v}

    @classmethod
    def from_yaml(cls, yaml_data: Dict[str, Any]) -> "RemoteProject":
        """build project from yaml representation"""
        src = "" if "src" not in yaml_data else yaml_data["src"]
        versions = None if "versions" not in yaml_data else yaml_data["versions"]
        parsed = cls(
            yaml_data["name"],
            yaml_data["url"],
            yaml_data["repo-path"],
            src,
            vcs=yaml_data["vcs"],
        )
        if versions:
            branches = [
                (branch["revision"], branch["name"]) for branch in versions["branches"]
            ]
            tags = [(tag["revision"], tag["name"]) for tag in versions["tags"]]
            parsed.add_versions(branches=branches, tags=tags)
        return parsed

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return other == self.name
        if isinstance(other, RemoteProject):
            return (
                other.name == self.name
                and other.url == self.url
                and other.repo_path == self.repo_path
            )
        return False
