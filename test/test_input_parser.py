"""test input parser functionality"""

import pytest
from test_common import Args

from dfetch_hub.project.input_parser import InputParser


def test_input_url():
    url = "http://www.github.com"
    mock = Args(url)
    assert [url] == InputParser(mock).get_urls()


def test_input_multiple_url():
    url = ["http://www.github.com", "http://www.example.com"]
    mock = Args(url)
    assert url == InputParser(mock).get_urls()


def test_input_dfetch_single_remote():
    dfetch_file_name = "test/testdata/dfetch00.yaml"
    mock = Args(dfetch_source=dfetch_file_name)
    assert [
        "https://github.com/cpputest/cpputest.git",
        "https://github.com/zserge/jsmn.git",
    ] == InputParser(mock).get_urls()


def test_input_dfetch_multiple_remotes():
    dfetch_file_name = "test/testdata/dfetch01.yaml"
    mock = Args(dfetch_source=dfetch_file_name)
    urls = InputParser(mock).get_urls()
    assert 3 == len(urls)
    assert [
        "https://github.com/cpputest/cpputest.git",
        "https://github.com/zserge/jsmn.git",
        "https://gitlab.com/ShacharKraus/pyfixed",
    ] == urls
