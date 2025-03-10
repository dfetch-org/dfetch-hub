"""

"""

import argparse

from dfetch_hub.project.input_parser import InputParser
from dfetch_hub.project.project_finder import GitProjectFinder
from dfetch_hub.project.project_parser import ProjectParser
from dfetch_hub.project.project_sources import SourceList

# from project.cli_disp import CliDisp


def main(parser: argparse.ArgumentParser):
    """main command line interface for program"""
    args = parser.parse_args()
    if not args.url and not args.dfetch_source:
        parser.print_help()
        raise ValueError("no url or dfetch manifest found")
    input_args_parser = InputParser(args)
    url_list = input_args_parser.get_urls()
    if args.persist_sources:
        sources_list = SourceList.from_input_parser(input_args_parser)
        with open("sources.yaml", "w", encoding="utf-8") as sources_file:
            sources_file.write(sources_list.as_yaml())
    parser = ProjectParser()
    for url in url_list:
        gpf = GitProjectFinder(url, args.project_exclude_pattern)
        projects = gpf.list_projects()
        for project in projects:
            parser.add_project(project)
        with open("projects.yaml", "w", encoding="utf-8") as datasource:
            datasource.write(parser.get_projects_as_yaml())


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("-u", "--url", required=False, nargs="+")
    arg_parser.add_argument("-ds", "--dfetch-source", required=False)
    arg_parser.add_argument(
        "-pep", "--project-exclude-pattern", required=False, nargs="+"
    )
    arg_parser.add_argument(
        "-ps", "--persist-sources", required=False, action="store_true"
    )
    main(arg_parser)
