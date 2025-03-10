"""common test utilities file"""


class Args:
    def __init__(self, url=None, dfetch_source=None):
        self.url = url
        self.dfetch_source = dfetch_source
        self.project_exclude_pattern = []
        self.persist_sources = False


class ParserMock:
    def __init__(self, url=None, dfetch_source=None):
        self.args = Args(url, dfetch_source)

    def parse_args(self):
        return self.args

    def print_help(self):
        print("help")
