from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user, get_current_user_optional
from app.core.templates import templates
from app.database.session import get_db
from app.database.models import Experiment, Project, User
from app.services.compare_service import compare_metrics, get_project_metric_names

router = APIRouter(prefix="/compare", tags=["compare"])
api_router = APIRouter(tags=["compare-api"])


@router.get("")
def compare_page(
    request: Request,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return templates.TemplateResponse("compare.html", {
        "request": request,
        "title": "实验对比",
        "current_user": current_user,
        "projects": projects,
    })


# ── API: list projects ───────────────────────────────────────────────────

@api_router.get("/api/compare/projects")
def api_compare_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return [{"id": p.id, "name": p.name} for p in projects]


# ── API: list experiments for a project ──────────────────────────────────

@api_router.get("/api/compare/projects/{project_id}/experiments")
def api_compare_experiments(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proj = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    exps = (
        db.query(Experiment)
        .filter(Experiment.project_id == project_id, Experiment.user_id == current_user.id)
        .order_by(Experiment.created_at.desc())
        .all()
    )
    return [{
        "id": e.id,
        "name": e.name,
        "experiment_code": e.experiment_code,
        "status": e.status,
        "is_best": e.is_best,
        "is_paper_used": e.is_paper_used,
    } for e in exps]


# ── API: project metric names ────────────────────────────────────────────

@api_router.get("/api/compare/projects/{project_id}/metric-names")
def api_compare_metric_names(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proj = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    names = get_project_metric_names(db, project_id, current_user.id)
    return {"metric_names": names}


# ── API: compare metrics ─────────────────────────────────────────────────

class CompareRequest(BaseModel):
    experiment_ids: List[int]
    metric_name: str
    x_axis: str = "auto"
    smooth_window: int = 1
    show_best: bool = True
    styles: Optional[dict] = None


@api_router.post("/api/compare/metrics")
def api_compare_metrics(
    req: CompareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not req.experiment_ids:
        raise HTTPException(status_code=400, detail="请选择至少一个实验")

    # validate all experiments belong to user
    for eid in req.experiment_ids:
        exp = db.query(Experiment).filter(Experiment.id == eid, Experiment.user_id == current_user.id).first()
        if not exp:
            raise HTTPException(status_code=404, detail=f"实验 {eid} 不存在或无权限")

    # parse styles: {str(eid): {...}} → {int(eid): {...}}
    styles = {}
    if req.styles:
        for k, v in req.styles.items():
            try:
                styles[int(k)] = v
            except (ValueError, TypeError):
                pass

    resolved_x, series, warnings = compare_metrics(
        db, req.experiment_ids, req.metric_name, current_user.id,
        req.x_axis, req.smooth_window, req.show_best, styles,
    )

    return {
        "metric_name": req.metric_name,
        "x_axis": resolved_x,
        "series": series,
        "warnings": warnings,
    }
