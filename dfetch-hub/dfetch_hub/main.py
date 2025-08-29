from fastapi import FastAPI
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from sqlmodel import select
from dfetch_hub.models import Package
from dfetch_hub.db import init_db, get_session
from dfetch_hub.scheduler import start_scheduler

app = FastAPI(title="dfetch_hub")

frontend_dir = Path(__file__).parent / "frontend"

# Mount the frontend folder to serve index.html and static files
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

# Initialize database and background scheduler
init_db()
start_scheduler()

# API endpoint for packages
@app.get("/packages")
def list_packages(search: str = None):
    with get_session() as session:
        query = select(Package)
        if search:
            query = query.where(Package.name.contains(search))
        packages = session.exec(query).all()
        return packages
