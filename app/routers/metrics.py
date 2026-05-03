import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.session import get_db
from app.database.models import Experiment, Metric, Project, User
from app.services.summary_service import (
    get_metric_names,
    build_series,
    summarize_experiment,
    summarize_project,
    get_ranking_by_metric,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])
api_router = APIRouter(tags=["metrics-api"])


def _get_experiment_owned(db: Session, experiment_id: int, user_id: int):
    exp = (
        db.query(Experiment)
        .filter(Experiment.id == experiment_id, Experiment.user_id == user_id)
        .first()
    )
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    return exp


# ── 1. metric-names ──────────────────────────────────────────────────────

@api_router.get("/api/experiments/{experiment_id}/metric-names")
def api_metric_names(
    experiment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_experiment_owned(db, experiment_id, current_user.id)
    names = get_metric_names(db, experiment_id, current_user.id)
    return {"metric_names": names}


# ── 2. metrics (chart data) ─────────────────────────────────────────────

@api_router.get("/api/experiments/{experiment_id}/metrics")
def api_metrics(
    experiment_id: int,
    metric_names: List[str] = Query(default=[]),
    x_axis: str = Query(default="auto"),
    smooth_window: int = Query(default=1, ge=1, le=50),
    show_best: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exp = _get_experiment_owned(db, experiment_id, current_user.id)

    if not metric_names:
        all_names = get_metric_names(db, experiment_id, current_user.id)
        metric_names = all_names[:6]

    resolved_x, series, warnings = build_series(
        db, experiment_id, current_user.id,
        metric_names, x_axis, smooth_window, show_best,
    )

    return {
        "experiment_id": experiment_id,
        "experiment_name": exp.name,
        "x_axis": resolved_x,
        "series": series,
        "warnings": warnings,
    }


# ── 3. export-csv ────────────────────────────────────────────────────────

@api_router.get("/api/experiments/{experiment_id}/metrics/export-csv")
def api_export_csv(
    experiment_id: int,
    metric_names: List[str] = Query(default=[]),
    x_axis: str = Query(default="auto"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exp = _get_experiment_owned(db, experiment_id, current_user.id)

    if not metric_names:
        metric_names = get_metric_names(db, experiment_id, current_user.id)

    if not metric_names:
        raise HTTPException(status_code=400, detail="该实验暂无指标数据")

    resolved_x, series, _ = build_series(
        db, experiment_id, current_user.id, metric_names, x_axis,
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["experiment_name", "x_axis", "x", "epoch", "step", "time", "metric_name", "metric_value"])
    for s in series:
        for p in s["points"]:
            writer.writerow([
                exp.name,
                resolved_x,
                p["x"],
                p.get("epoch") if p.get("epoch") is not None else "",
                p.get("step") if p.get("step") is not None else "",
                p.get("time") if p.get("time") is not None else "",
                s["metric_name"],
                p["raw_y"],
            ])

    buf.seek(0)
    filename = f"experiment_{experiment_id}_metrics.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── 4. experiment summary ───────────────────────────────────────────────

@api_router.get("/api/experiments/{experiment_id}/summary")
def api_experiment_summary(
    experiment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_experiment_owned(db, experiment_id, current_user.id)
    summary = summarize_experiment(db, experiment_id, current_user.id)
    return {"experiment_id": experiment_id, "metrics": summary}


# ── 5. project summary ──────────────────────────────────────────────────

def _get_project_owned(db: Session, project_id: int, user_id: int):
    proj = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    return proj


@api_router.get("/api/projects/{project_id}/summary")
def api_project_summary(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_owned(db, project_id, current_user.id)
    summary = summarize_project(db, project_id, current_user.id)
    return summary


# ── 6. project metric-names ─────────────────────────────────────────────

@api_router.get("/api/projects/{project_id}/metric-names")
def api_project_metric_names(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_owned(db, project_id, current_user.id)
    from sqlalchemy import distinct
    rows = (
        db.query(distinct(Metric.metric_name))
        .filter(Metric.project_id == project_id, Metric.user_id == current_user.id)
        .all()
    )
    return {"metric_names": sorted([r[0] for r in rows])}


# ── 7. ranking by metric ────────────────────────────────────────────────

@api_router.get("/api/projects/{project_id}/ranking")
def api_project_ranking(
    project_id: int,
    metric_name: str = Query(...),
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_owned(db, project_id, current_user.id)
    ranking = get_ranking_by_metric(db, project_id, metric_name, current_user.id, limit)
    return {"project_id": project_id, "metric_name": metric_name, "ranking": ranking}
