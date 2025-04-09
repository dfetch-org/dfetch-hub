"""test dfetch export functionality"""

import os
from dataclasses import dataclass

import pytest

from dfetch_hub.project.export import DfetchExport


@dataclass
class EntryMock:
    name: str
    revision: str
    src: str
    url: str
    repo_path: str
    vcs: str = "git"


@pytest.fixture
def entry():
    return EntryMock(
        "test", "0123456789abcdef", "/src", "http://test.test", "test_path"
    )


@pytest.fixture
def entries():
    entry = EntryMock(
        "test", "0123456789abcdef", "/src", "http://test.test", "test_path"
    )
    entry2 = EntryMock(
        "test2", "0123456789abcdef2", "/src2", "http://test.test2", "test_path2"
    )
    return [entry, entry2]


def test_add_entry(entry):
    export = DfetchExport()
    export.add_entry(entry)
    assert len(export.entries) == 1
    assert entry in export.entries


def test_from_entry(entry):
    export = DfetchExport([entry])
    assert len(export.entries) == 1
    assert entry in export.entries


def test_multiple_entries(entries):
    export = DfetchExport()
    for entry in entries:
        export.add_entry(entry)
    assert len(export.entries) == len(entries)
    for entry in entries:
        assert entry in export.entries


def test_yaml_file(entries):
    export = DfetchExport()
    for entry in entries:
        export.add_entry(entry)
    export.export("test/testdata/dfetch_export.yaml")
    assert os.path.exists("test/testdata/dfetch_export.yaml")
