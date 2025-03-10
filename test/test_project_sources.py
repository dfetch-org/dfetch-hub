"""test project sources functionality"""

import pytest

from dfetch_hub.project.project_sources import RemoteSource, SourceList


@pytest.fixture
def input_parser():
    class InputParserMock:
        def get_urls(self):
            return ["https://github.com/cpputest/cpputest.git"]

    return InputParserMock()


def test_add_remote():
    sl = SourceList()
    ps = RemoteSource(
        {"name": "cpputest", "url-base": "https://github.com/cpputest/cpputest.git"}
    )
    sl.add_remote(ps)
    assert len(sl.get_remotes()) == 1
    assert sl.get_remotes()[0] == ps


def test_add_multiple_remotes():
    sl = SourceList()
    ps1 = RemoteSource(
        {"name": "cpputest", "url-base": "https://github.com/cpputest/cpputest.git"}
    )
    ps2 = RemoteSource(
        {"name": "other_repo", "url-base": "https://github.com/cpputest/other_repo.git"}
    )
    sl.add_remote(ps1)
    sl.add_remote(ps2)
    assert len(sl.get_remotes()) == 2
    assert sl.get_remotes() == [ps1, ps2]


def test_yaml():
    sl = SourceList()
    ps1 = RemoteSource(
        {"name": "cpputest", "url-base": "https://github.com/cpputest/cpputest.git"}
    )
    ps2 = RemoteSource(
        {"name": "other_repo", "url-base": "https://github.com/cpputest/other_repo.git"}
    )
    sl.add_remote(ps1)
    sl.add_remote(ps2)
    sl2 = SourceList.from_yaml(sl.as_yaml())
    assert sl2 == sl


def test_input_parser(input_parser):
    sl = SourceList.from_input_parser(input_parser)
    assert len(sl.get_remotes()) == 1
    ps = RemoteSource(
        {"name": "cpputest.git", "url-base": "https://github.com/cpputest/cpputest.git"}
    )
    assert ps in sl.get_remotes()


def test_yaml_with_exclusions():
    sl = SourceList()
    ps = RemoteSource(
        {"name": "cpputest", "url-base": "https://github.com/cpputest/cpputest.git"}
    )
    ps.add_exclusion("test/.*")
    ps.add_exclusion("module*")
    sl.add_remote(ps)
    sl2 = SourceList.from_yaml(sl.as_yaml())
    assert sl2 == sl
