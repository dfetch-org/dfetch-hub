from apscheduler.schedulers.background import BackgroundScheduler
from  dfetch_hub.harvester import fetch_github_repo

def start_scheduler():
    scheduler = BackgroundScheduler()
    repos = ["psf/requests", "tiangolo/fastapi"]  # Example GitHub repos to track

    for repo in repos:
        # Fetch metadata every hour
        scheduler.add_job(fetch_github_repo, 'interval', minutes=1, args=[repo])

    scheduler.start()
    print("Scheduler started")
