"""test cli module"""

import pytest
from test_common import ParserMock

from dfetch_hub.project.cli import main


@pytest.fixture
def parser_no_args():
    return ParserMock()


@pytest.fixture
def parser_url():
    return ParserMock(url="https://github.com/cpputest/")


@pytest.fixture
def parser_dfetch():
    return ParserMock(dfetch_source="test/dfetch.yaml")


def test_no_parameters(parser_no_args):
    with pytest.raises(ValueError):
        main(parser_no_args)


def test_url_parameter(parser_url):
    with pytest.raises(ValueError):
        main(parser_url)


def test_dfetch_parameter(parser_dfetch):
    with pytest.raises(FileNotFoundError):
        main(parser_dfetch)
