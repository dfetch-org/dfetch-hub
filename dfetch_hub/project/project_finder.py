"""project finder module"""

import logging
import os
import re
import sys
from abc import abstractmethod
from contextlib import chdir
from typing import List, Optional, Sequence, Set, Tuple, Union

from dfetch.util.cmdline import SubprocessCommandError, run_on_cmdline

from dfetch_hub.project.remote_datasource import RemoteProject

WORKDIR = "tmp"


class ProjectFinder:
    """class to find projects in repositories"""

    def __init__(self, url: str, exclusions: Optional[List[str]] = None):
        self._url = url
        self._logger = logging.getLogger()
        self._projects: list[RemoteProject] = []
        self._exclusions: List[str] = exclusions or []

    @property
    def url(self) -> str:
        """repo url"""
        return self._url

    @abstractmethod
    def list_projects(self) -> list[RemoteProject]:
        """list all projects in a repo"""
        raise AssertionError("abstractmethod")

    def filter_exclusions(self, paths: Union[List[str], Set[str]]) -> List[str]:
        """filter exclusions from list of projects"""
        filtered_paths = []
        for path in paths:
            path_allowed = True
            if self._exclusions:
                for exclusion in self._exclusions:
                    try:
                        re.compile(exclusion)
                    except re.error as exc:
                        raise ValueError(
                            f"regex of exclusion is invalid, {exclusion}"
                        ) from exc
                    path_allowed = path_allowed and not re.search(exclusion, path)
                    if not path_allowed:
                        break
                if path_allowed and path not in filtered_paths:
                    filtered_paths.append(path)
            else:
                filtered_paths = list(paths)
        return filtered_paths

    @property
    def exclusions(self) -> Optional[List[str]]:
        """get exclusion for project finder"""
        return self._exclusions

    def add_exclusion(self, exclusion: Optional[str]) -> None:
        """add an exclusion regex"""
        if exclusion:
            if not self._exclusions:
                self._exclusions = []
            self._exclusions.append(exclusion)
            print(f"exclusions are {self.exclusions}")

    def filter_projects(self) -> None:
        """filter projects on exclusions"""
        for project in self._projects:
            path = f"{project.url, project.repo_path, project.src}"
            path_allowed = True
            if self._exclusions:
                for exclusion in self._exclusions:
                    try:
                        re.compile(exclusion)
                    except re.error as exc:
                        raise ValueError(
                            f"regex of exclusion is invalid, {exclusion}"
                        ) from exc
                    path_allowed = path_allowed and not re.search(exclusion, path)
                    if not path_allowed:
                        break
            if not path_allowed:
                self._projects.remove(project)


class GitProjectFinder(ProjectFinder):
    """git implementation of project finder"""

    def list_projects(self) -> List[RemoteProject]:
        """list all git projects in a git repo"""
        if not self._projects:
            if os.path.exists(WORKDIR) and os.path.isdir(WORKDIR):
                if sys.platform == "win32":
                    os.system(f"rmdir /S /Q {WORKDIR}")
                elif sys.platform == "linux":
                    os.system(f"rm -rf {WORKDIR}")
            try:
                result = run_on_cmdline(
                    self._logger, f"git clone --no-checkout {self._url} {WORKDIR}"
                )
                with chdir(WORKDIR):
                    result = run_on_cmdline(self._logger, "git status")
                    # More matching (specific types, add interface)
                    # keep matched on (e.g. project x matched on ...)
                    res = re.findall(
                        r"\sdeleted:\s+(.*(?:README|LICENSE|CHANGELOG|Readme|readme|License|license).*)",  # pylint:disable=line-too-long
                        result.stdout.decode("utf-8"),
                    )
                    result = run_on_cmdline(
                        self._logger, "git for-each-ref refs/remotes/origin"
                    )
                    branches = re.findall(
                        r"([a-f0-9]*)\scommit\s.*/origin/(.*)",
                        result.stdout.decode("utf-8"),
                    )
                    result = run_on_cmdline(self._logger, "git for-each-ref refs/tags")
                    tags = re.findall(
                        r"([a-f0-9]*)\s(?:(?:commit)|(?:tag))\s*refs/tags/(.*)",
                        result.stdout.decode("utf-8"),
                    )
            except SubprocessCommandError as exc:
                raise ValueError(
                    f"could not find repository at url {self._url}"
                ) from exc
            finally:
                if sys.platform == "win32":
                    os.system(f"rmdir /S /Q {WORKDIR}")
                elif sys.platform == "linux":
                    os.system(f"rm -rf {WORKDIR}")
            paths = set()
            for path in res:
                if "/" in path:
                    paths.add(f"{path.rsplit("/", maxsplit=1)[0].strip(" ")}")
                else:
                    paths.add("")
            filtered_paths = self.filter_exclusions(paths)
            self._projects = self._projects_from_paths(filtered_paths, branches, tags)
        return self._projects

    def _projects_from_paths(
        self,
        paths: Sequence[str],
        branches: Sequence[Tuple[str, str]],
        tags: Sequence[Tuple[str, str]],
    ) -> List[RemoteProject]:
        projects = []
        for path in paths:
            if "/" in path:
                name = path.rsplit("/", maxsplit=1)[1]
            elif len(path) > 1:
                name = path
            else:
                name = self.url.rsplit("/", maxsplit=1)[1]
            base_url, repo_path = _base_url(self.url)
            src = path
            vcs = "git"
            project = RemoteProject(name, base_url, repo_path, src, vcs)
            project.versions.vcs = vcs
            project.add_versions(branches, tags)
            projects.append(project)
        return projects


def _base_url(url: str) -> Tuple[str, str]:
    if "://" in url:
        url = url.split("://", maxsplit=1)[1]
    if "/" in url:
        url, repo_path = url.split("/", maxsplit=1)
    else:
        repo_path = ""
    return url, repo_path
