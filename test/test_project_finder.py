"""test project finder functionality"""

import pytest

from dfetch_hub.project.project_finder import GitProjectFinder


def test_find_cpputest_github():
    url = "https://github.com/cpputest/cpputest.git"
    gpf = GitProjectFinder(url)
    projects = gpf.list_projects()
    assert len(projects) == 13
    assert "cpputest.git" in projects
    assert "examples" in projects
    assert "CppUTest" in projects


def test_find_jasmine_github():
    url = "https://github.com/zserge/jsmn.git"
    gpf = GitProjectFinder(url)
    projects = gpf.list_projects()
    assert len(projects) == 1
    assert "jsmn.git" in projects


def test_find_pyfixed_gitlab():
    url = "https://gitlab.com/ShacharKraus/pyfixed"
    gpf = GitProjectFinder(url)
    projects = gpf.list_projects()
    assert len(projects) == 1
    assert "pyfixed" in projects


def test_find_cpputest_github_exclusion_filer():
    url = "https://github.com/cpputest/cpputest.git"
    exclusions = ["platforms.*", ".*examples.*", "scripts"]
    gpf = GitProjectFinder(url, exclusions=exclusions)
    projects = gpf.list_projects()
    assert len(projects) == 3
    assert "cpputest.git" in projects
    assert "CppUTest" in projects
    assert "Symbian" in projects


def test_find_cpputest_github_invalid_regex():
    url = "https://github.com/cpputest/cpputest.git"
    exclusions = ["*examples*"]
    with pytest.raises(ValueError):
        gpf = GitProjectFinder(url, exclusions=exclusions)
        projects = gpf.list_projects()
