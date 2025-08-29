import requests
from dfetch_hub.db import get_session
from dfetch_hub.models import Package
from datetime import datetime

GITHUB_API = "https://api.github.com/repos"

def fetch_github_repo(repo_full_name: str):
    """
    Fetch GitHub repo metadata and insert/update in DB.
    Example: repo_full_name = "psf/requests"
    """
    url = f"{GITHUB_API}/{repo_full_name}"
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"Failed to fetch {repo_full_name}")
        return

    data = resp.json()
    package = Package(
        name=data["name"],
        description=data.get("description"),
        repository=data["html_url"],
        source="github",
        latest_version=data.get("default_branch"),
        tags=",".join(data.get("topics", [])) if "topics" in data else None,
        license=data["license"]["name"] if data.get("license") else None,
        last_updated=datetime.strptime(data["updated_at"], "%Y-%m-%dT%H:%M:%SZ"),
        readme_excerpt=None
    )

    with get_session() as session:
        existing = session.query(Package).filter(Package.repository == package.repository).first()
        if existing:
            package.id = existing.id
            session.merge(package)
        else:
            session.add(package)
        session.commit()
        print(f"Saved {package.name}")
