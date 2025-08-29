from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Package(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str]
    repository: str
    source: str = "github"
    latest_version: Optional[str]
    tags: Optional[str]  # comma-separated
    license: Optional[str]
    last_updated: Optional[datetime]
    readme_excerpt: Optional[str]
