# Remote Project Overview

- [Remote Project Overview](#remote-project-overview)
  - [Idea](#idea)
  - [File types](#file-types)
    - [Source list](#source-list)
    - [Project lists](#project-lists)
    - [Output file](#output-file)

## Idea

- url to list project + versions
- dfetch.yaml formatter to output selected items

## File types

### Source list

Source list is a type used to list a collection of project sources.
A project source is a place to look for projects.
Optionally a list of exclusions can be added so certain patterns that look like potential projects but are not projects are excluded.

The source list can be used to share project locations and exclusions between users.

### Project lists

The project list is the main overview containing all the projects in the sources.
It is populated by the information gathered by the `ProjectFinder` when it is passed to the `ProjectParser` by looking in the project sources locations and parsing the information there.
The `ProjectParser` is the module that can use a project list as a source of projects and generate entries for dependency fetchers.
The current use case in mind is `dFetch`, but in the future e.g. `git submodule`'s or other dependency fetchers could be used.

### Output file

The output of this project is a source file which can be used by other tools to import the selected projects.
Our first use case is to create `dFetch` manifest files, which can then be used to import the selected versions of projects into other projects.
