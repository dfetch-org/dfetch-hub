"""input parser module"""

from typing import Sequence

from dfetch.manifest.manifest import Manifest


class InputParser:  # pylint:disable=too-few-public-methods
    """parser for url or dfetch file input"""

    def __init__(self, args):
        self.args = args

    def get_urls(self) -> Sequence[str]:
        """get urls for input"""
        if self.args.url:
            if isinstance(self.args.url, list):
                return self.args.url
            return [self.args.url]
        return self._parse_dfetch_remotes(self.args.dfetch_source)

    def _parse_dfetch_remotes(self, dfetch_path) -> Sequence[str]:
        manifest = Manifest.from_file(dfetch_path)
        return [project.remote_url for project in manifest.projects]
