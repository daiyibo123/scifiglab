from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.security import get_current_user_optional
from app.database.init_db import init_db
from app.database.session import get_db
from app.routers import (
    admin,
    auth,
    dashboard,
    projects,
    experiments,
    files,
    metrics,
    compare,
    groups,
    diagrams,
)

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.debug,
)

app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

from app.core.templates import templates  # noqa: E402

app.include_router(auth.router)
app.include_router(auth.api_router)
app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(projects.api_router)
app.include_router(experiments.router)
app.include_router(experiments.api_router)
app.include_router(files.router)
app.include_router(files.api_router)
app.include_router(metrics.router)
app.include_router(metrics.api_router)
app.include_router(compare.router)
app.include_router(compare.api_router)
app.include_router(groups.router)
app.include_router(groups.api_router)
app.include_router(diagrams.router)
app.include_router(diagrams.api_router)
app.include_router(admin.router)
app.include_router(admin.api_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/", tags=["home"])
async def home(
    request: Request,
    current_user=Depends(get_current_user_optional),
    db=Depends(get_db),
):
    from app.database.models import User
    admin_exists = db.query(User).filter(User.is_admin == True).first() is not None
    if not admin_exists:
        return RedirectResponse(url="/admin/init", status_code=302)
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("landing.html", {
        "request": request,
        "current_user": current_user,
    })
