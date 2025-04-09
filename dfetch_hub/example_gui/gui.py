"""sample of a possible nicegui based gui"""

from nicegui import events, ui
from thefuzz import fuzz

from dfetch_hub.project.project_finder import GitProjectFinder
from dfetch_hub.project.project_sources import RemoteSource, SourceList


def main():
    """main gui runner"""
    ui.context.sl = SourceList()
    ui.context.pf = []
    header()
    with ui.column().classes("w-1/3 mx-auto mt-10"):
        show_sources()
        url_input()
        sources_input()
    ui.run(title="dfetch project viewer", reconnect_timeout=30)


def header():
    """main gui header"""
    with ui.header().classes("bg-black text-white p-4"):
        with ui.row().classes(
            "container mx-auto flex justify-between items-center space-x-4"
        ):
            ui.link("Sources", target="/sources").classes(
                "text-white hover:text-gray-400 no-underline"
            )
            ui.link("Projects", target="/projects").classes(
                "text-white hover:text-gray-400 no-underline"
            )
            ui.link("Filters", target="/filters").classes(
                "text-white hover:text-gray-400 no-underline"
            )


@ui.page("/sources")
def sources_page():
    """page to enter sources to search"""
    header()
    with ui.column().classes("w-1/3 mx-auto mt-10"):
        show_sources()
        url_input()
        sources_input()


def add_projects_to_page():
    """add list of project finder results to page"""
    if not ui.context.pf:
        ui.context.pf = []
        ui.context.projects = []
    for source in ui.context.sl.get_remotes():
        if source.url not in [pf.url for pf in ui.context.pf]:
            print(f"adding source {source.url}")
            if hasattr(source, "exclusions"):
                pf = GitProjectFinder(source.url, source.exclusions)
            else:
                pf = GitProjectFinder(source.url)
            ui.context.pf += [pf]
    for pf in ui.context.pf:
        try:
            add_project_finder_to_page(pf)
        except ValueError as e:
            ui.notification(f"{e}")


def add_project_finder_to_page(pf, projects=None):
    """add single project finder result to page"""
    if not projects:
        projects = pf.list_projects()
    ui.context.projects += [
        project for project in projects if project not in ui.context.projects
    ]
    ui.label(f"{pf.url}").classes("text-xl font-bold mb-4 text-center")
    with ui.row().classes("grid grid-cols-2 gap-4 overflow-auto max-h-screen w-2/3"):
        for project in projects:
            add_project_to_page(project)


def add_project_to_page(project):
    """add single project to page"""
    with ui.card().classes(
        "bg-black text-white p-6 rounded shadow-lg \
        text-center w-full h-40 flex justify-center items-center"
    ):
        ui.link(text=project.name, target=f"/project_data/{project.name}").classes(
            "text-white hover:text-gray-400 no-underline"
        )


@ui.page("/projects/")
def projects_page():
    """projects for source"""
    header()
    search_input = ui.input(placeholder="Search packages").classes("flex-grow")
    search_input.on_value_change(lambda e: update_autocomplete(e.value))
    ui.context.project_col = ui.column().classes("w-2/3 mx-auto mt-10")
    with ui.context.project_col:
        try:
            add_projects_to_page()
        except AttributeError as e:
            print(e)
            ui.navigate.to("/sources")


def update_autocomplete(value):
    """autocomplete for project search"""
    ui.context.project_col.clear()
    with ui.context.project_col:
        if not value:
            print("adding all projects")
            add_projects_to_page()
        else:
            print(f"adding projects matching {value}")
            for pf in ui.context.pf:
                sorted_list = []
                for project in pf.list_projects():
                    url, repo_path, src = (
                        fuzz.ratio(value, project.url),
                        -fuzz.ratio(value, project.repo_path),
                        -fuzz.ratio(value, project.src),
                    )
                    print(
                        f"ratios {project.url}{project.repo_path}{project.src}\
- {fuzz.ratio(value,project.url)}\
- {fuzz.ratio(value,project.repo_path)}\
- {fuzz.ratio(value,project.src)}"
                    )
                    ratio = max(
                        fuzz.ratio(value, project.url),
                        fuzz.ratio(value, project.repo_path),
                        fuzz.ratio(value, project.src),
                    )
                    if ratio > 30 or url > 20 or repo_path > 20 or src > 20:
                        sorted_list += [(ratio, project)]
                    sorted_list.sort(key=lambda i: i[0], reverse=True)
                for ratio, project in sorted_list:
                    add_project_to_page(project)


@ui.page("/project_data/{name}")
def projects_data_page(name: str):
    """data for project"""
    header()
    with ui.column().classes("w-5/6 items-center mx-auto mt-10"):
        try:
            found_project = None
            for project in ui.context.projects:
                if project.name == name:
                    found_project = project
                    break
            if found_project:
                project_representation(found_project)
            else:
                ui.label(
                    f"could not find project in \
{[project.name for project in ui.context.projects]}"
                )
        except AttributeError:
            ui.label(f"{name} was not found")


@ui.page("/filters")
def filters_page():
    """page showing exclusions per source"""
    header()
    ui.notify("no sources present, redirecting to sources")
    if hasattr(ui.context, "pf") and len(ui.context.pf) > 0:
        with ui.column():
            for pf in ui.context.pf:
                with ui.row():
                    ui.label(f"{pf.url}")
                    filter_in = ui.input(placeholder="enter filter regex")
                    ui.button(
                        "add exclusion",
                        on_click=lambda pf=pf, filter_in=filter_in: add_exclusion(
                            pf, filter_in.value
                        ),
                    )
                    if (
                        hasattr(pf, "exclusions")
                        and pf.exclusions
                        and len(pf.exclusions) > 0
                    ):
                        with ui.column():
                            for excl in pf.exclusions:
                                ui.label(f"{excl}")
            ui.button("store", on_click=presist_sources)
    else:
        ui.navigate.to("/sources")


def add_exclusion(pf, regex):
    """add exclusion for the project finder for a source"""
    ui.notify(f"adding exclusion {regex} to projects on url {pf.url}")
    project = [
        project for project in ui.context.sl.get_remotes() if project.url == pf.url
    ][0]
    project.add_exclusion(regex)
    pf.add_exclusion(regex)
    pf.filter_projects()


def presist_sources():
    """persist entered sources to file"""
    sl = ui.context.sl
    ui.download(sl.as_yaml().encode("utf-8"), filename="sources.yaml")


def url_input():
    """url input page"""
    url_search_field = ui.input(placeholder="enter url to list packages").classes(
        "w-full p-2 text-lg border border-gray-300 rounded"
    )
    ui.button(
        text="get projects", on_click=lambda a: get_projects(url_search_field.value)
    ).classes("bg-black text-white px-4 py-2 rounded hover:bg-gray-800 mt-4")


def sources_input():
    """input sources file"""
    ui.upload(
        on_upload=lambda e: handle_upload(e)  # pylint:disable = unnecessary-lambda
    ).props("accept=.yaml").classes("max-w-full")


def handle_upload(file: events.UploadEventArguments):
    """handle upload of sources file"""
    ui.context.sl = SourceList.from_yaml(file.content.read())
    ui.notify(f"uploaded {file.name}")


def get_projects(url):
    """handling of project search"""
    if url and len(url) > 5:  # what is min valid url len?
        name = url.split("/")[-1]
        ui.context.sl.add_remote(RemoteSource({"name": name, "url-base": url}))
    ui.navigate.to("/projects/")


def project_representation(project):
    """project representation"""
    ui.label(project.name).classes("text-h5 text-black mb-5")

    with ui.row().classes("justify-between m-20"):
        # Empty space in column 1 (1-2)
        with ui.column().classes("w-full sm:w-1/12"):
            pass  # No content here (empty)

        # Column 1 (2-4), spanning 3 parts
        with ui.column().classes("w-full sm:w-3/12"):
            ui.link(
                project.url, target=f"http://{project.url}/{project.repo_path}"
            ).classes("text-body1 text-black")
            ui.label(f"Source - {project.src if project.src else "/"}").classes(
                "text-body2 text-black"
            )
            ui.label(f"vcs - {project.vcs}")

        # Column 2 (4-7), spanning 3 parts
        with ui.column().classes("w-full sm:w-3/12"):
            ui.label("branches").classes("text-h5 text-black mb-3")
            for branch in project.versions.branches:
                revision_representation(branch)

        # Column 3 (7-10), spanning 3 parts
        with ui.column().classes("w-full sm:w-3/12"):
            ui.label("tags").classes("text-h5 text-black mb-3")
            for tag in project.versions.tags:
                revision_representation(tag)

        # Empty space in column 3 (10-12)
        with ui.column().classes("w-full sm:w-1/12"):
            pass  # No content here (empty)


def revision_representation(rev):
    """revision representation"""
    ui.label(f"revision {rev.name} - {rev.revision}").classes(
        "text-body2 text-black mb-2"
    )


def show_sources():
    """show sources in source view"""
    if hasattr(ui.context, "pf"):
        for pf in ui.context.pf:
            ui.label(f"{pf.url}")


if __name__ in ("__main__", "__mp_main__"):
    main()
