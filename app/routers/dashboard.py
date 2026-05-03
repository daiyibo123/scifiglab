from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.security import get_current_user_optional
from app.core.templates import templates
from app.database.session import get_db
from app.database.models import Project, Experiment, ExperimentGroup, UploadedFile, Metric

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

RESEARCH_AREAS = {
    "deep_learning": "深度学习",
    "computer_science": "计算机科学",
    "biology": "生物学",
    "chemistry": "化学",
    "materials": "材料科学",
    "physics": "物理学",
    "engineering": "工程学",
    "medicine": "医学",
    "other": "其他",
}


@router.get("")
def dashboard(
    request: Request,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)

    uid = current_user.id

    project_count = db.query(func.count(Project.id)).filter(Project.user_id == uid).scalar()
    experiment_count = db.query(func.count(Experiment.id)).filter(Experiment.user_id == uid).scalar()
    group_count = db.query(func.count(ExperimentGroup.id)).filter(ExperimentGroup.user_id == uid).scalar()
    file_count = db.query(func.count(UploadedFile.id)).filter(UploadedFile.user_id == uid).scalar()
    metric_count = db.query(func.count(Metric.id)).filter(Metric.user_id == uid).scalar()

    # Status breakdown
    running_count = db.query(func.count(Experiment.id)).filter(
        Experiment.user_id == uid, Experiment.status == "running"
    ).scalar()
    best_count = db.query(func.count(Experiment.id)).filter(
        Experiment.user_id == uid, Experiment.is_best == True
    ).scalar()

    recent_projects = (
        db.query(Project)
        .filter(Project.user_id == uid)
        .order_by(Project.created_at.desc())
        .limit(5)
        .all()
    )
    for p in recent_projects:
        p.area_label = RESEARCH_AREAS.get(p.research_area, p.research_area)
        p.exp_count = (
            db.query(func.count(Experiment.id))
            .filter(Experiment.project_id == p.id)
            .scalar()
        )

    recently_updated = (
        db.query(Project)
        .filter(Project.user_id == uid)
        .order_by(Project.updated_at.desc())
        .limit(5)
        .all()
    )
    for p in recently_updated:
        p.area_label = RESEARCH_AREAS.get(p.research_area, p.research_area)

    # Recent experiments
    recent_experiments = (
        db.query(Experiment)
        .filter(Experiment.user_id == uid)
        .order_by(Experiment.created_at.desc())
        .limit(8)
        .all()
    )
    for e in recent_experiments:
        proj = db.query(Project).filter(Project.id == e.project_id).first()
        e.project_name = proj.name if proj else "?"

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "title": "仪表盘",
        "current_user": current_user,
        "project_count": project_count,
        "experiment_count": experiment_count,
        "group_count": group_count,
        "file_count": file_count,
        "metric_count": metric_count,
        "running_count": running_count,
        "best_count": best_count,
        "recent_projects": recent_projects,
        "recently_updated": recently_updated,
        "recent_experiments": recent_experiments,
    })
