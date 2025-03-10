"""test project parser functionality"""

import pytest
import yaml

from dfetch_hub.project.project_parser import ProjectParser, RemoteProject


def get_sample_project():
    name = "CppUTest"
    url = "https://github.com/cpputest/"
    src = ""
    repo_path = "cpputest.git"
    vcs = "git"
    return RemoteProject(name, url, repo_path, src, vcs)


@pytest.fixture
def project():
    return get_sample_project()


@pytest.fixture
def project_w_version():
    project = get_sample_project()
    tags = [
        ("aabbccddeeff", "1.0.0"),
        ("aaaaaaaaaaaa", "1.1.1"),
        ("bbbbbbbbbbbb", "best_tag_ever"),
    ]
    branches = [
        ("aabbccddaabb", "dev"),
        ("bbccddeeffaa", "master"),
        ("ccddeeffaabb", "some_old_forgotten_branch"),
    ]
    project.add_versions(branches, tags)
    return project


@pytest.fixture
def projects_w_version():
    project_1 = get_sample_project()
    project_2 = get_sample_project()
    tags1 = [
        ("aabbccddeeff", "1.0.0"),
        ("aaaaaaaaaaaa", "1.1.1"),
        ("bbbbbbbbbbbb", "best_tag_ever"),
    ]
    tags2 = [
        ("aabbccddeeff", "2.0.0"),
        ("bbddeeffaacc", "2.1.1"),
        ("0123456789a", "worst_tag_ever"),
    ]
    branches = [
        ("aabbccddaabb", "dev"),
        ("bbccddeeffaa", "master"),
        ("ccddeeffaabb", "some_old_forgotten_branch"),
    ]
    project_1.add_versions(branches, tags1)
    project_2.add_versions(branches, tags2)
    return (project_1, project_2)


def test_add_project(project):
    parser = ProjectParser()
    parser.add_project(project)
    assert len(parser.get_projects()) == 1
    assert parser.get_projects()[0] == project


def test_get_as_yaml(project):
    parser = ProjectParser()
    parser.add_project(project)
    yaml_proj = parser.get_projects_as_yaml()
    assert yaml.load(yaml_proj, yaml.Loader)


def test_from_yaml(project):
    parser = ProjectParser()
    yaml_file = "test/testdata/versions.yaml"
    parser = ProjectParser.from_yaml(yaml_file)
    assert len(parser.get_projects()) == 1
    assert parser.get_projects()[0] == project


def test_project_version(project_w_version):
    parser = ProjectParser()
    project = project_w_version
    parser.add_project(project)
    assert len(parser.get_projects()) == 1
    assert parser.get_projects()[0] == project
    assert "1.0.0" in project.versions.tags
    assert "dev" in project.versions.branches


def test_two_projects_version(projects_w_version):
    parser = ProjectParser()
    project1, project2 = projects_w_version
    parser.add_project(project1)
    parser.add_project(project2)
    assert len(parser.get_projects()) == 1
    assert parser.get_projects()[0] == project1
    assert "1.0.0" in project1.versions.tags
    assert "dev" in project1.versions.branches
    assert "2.0.0" not in project1.versions.tags
    assert "2.0.0" in project2.versions.tags
    assert "dev" in project2.versions.branches


def test_versions_from_yaml(projects_w_version):
    parser = ProjectParser()
    yaml_file = "test/testdata/versions01.yaml"
    parser = ProjectParser.from_yaml(yaml_file)
    project1, project2 = projects_w_version
    project2.name = "project_2"
    project_1_from_file = parser.get_projects()[0]
    assert len(parser.get_projects()) == 2
    assert project_1_from_file == project1
    assert parser.get_projects()[1] == project2
    assert project_1_from_file.versions == project1.versions
