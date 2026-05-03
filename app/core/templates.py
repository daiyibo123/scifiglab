"""Shared Jinja2 templates instance with global variables."""

from pathlib import Path
from fastapi.templating import Jinja2Templates
from app.core.config import settings

TEMPLATES_DIR = str(Path(__file__).resolve().parent.parent / "templates")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["github_repo_url"] = settings.GITHUB_REPO_URL
