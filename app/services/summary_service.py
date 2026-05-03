"""Summary service — metric direction, smoothing, experiment/project summaries."""

from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct

from app.database.models import Metric, Experiment, Project

# ─── Metric direction ──────────────────────────────────────────────────

LOWER_BETTER_KEYWORDS = [
    "loss", "error", "mae", "mse", "rmse", "latency", "time_cost",
]
HIGHER_BETTER_KEYWORDS = [
    "psnr", "ssim", "dice", "iou", "acc", "accuracy", "precision",
    "recall", "f1", "auc", "efficiency", "yield", "score",
]


def get_metric_direction(metric_name: str) -> str:
    """Return 'lower_better' or 'higher_better' for a metric name."""
    name = metric_name.lower()
    for kw in LOWER_BETTER_KEYWORDS:
        if kw in name:
            return "lower_better"
    for kw in HIGHER_BETTER_KEYWORDS:
        if kw in name:
            return "higher_better"
    return "higher_better"


# ─── Smoothing ──────────────────────────────────────────────────────────

def smooth(values: List[float], window: int) -> List[float]:
    """Simple moving average; boundary uses available window."""
    if window <= 1 or len(values) == 0:
        return list(values)
    result = []
    for i in range(len(values)):
        lo = max(0, i - window // 2)
        hi = min(len(values), i + window // 2 + 1)
        result.append(sum(values[lo:hi]) / (hi - lo))
    return result


# ─── Best / Last point helpers ──────────────────────────────────────────

def _best_point(points: list, direction: str) -> Optional[dict]:
    """Find best point from a list of dicts with 'x' and 'raw_y'."""
    if not points:
        return None
    if direction == "lower_better":
        best = min(points, key=lambda p: p["raw_y"])
    else:
        best = max(points, key=lambda p: p["raw_y"])
    return {"x": best["x"], "y": best["raw_y"], "epoch": best.get("epoch"), "step": best.get("step"), "time": best.get("time")}


def _last_point(points: list) -> Optional[dict]:
    if not points:
        return None
    last = points[-1]
    return {"x": last["x"], "y": last["raw_y"], "epoch": last.get("epoch"), "step": last.get("step"), "time": last.get("time")}


# ─── Query helpers ──────────────────────────────────────────────────────

def get_metric_names(db: Session, experiment_id: int, user_id: int) -> List[str]:
    """Return sorted distinct metric names for an experiment."""
    rows = (
        db.query(distinct(Metric.metric_name))
        .filter(Metric.experiment_id == experiment_id, Metric.user_id == user_id)
        .all()
    )
    return sorted([r[0] for r in rows])


def build_series(
    db: Session,
    experiment_id: int,
    user_id: int,
    metric_names: List[str],
    x_axis: str = "auto",
    smooth_window: int = 1,
    show_best: bool = True,
) -> Tuple[str, List[dict], List[str]]:
    """Build chart series for given metrics.

    Returns (resolved_x_axis, series_list, warnings).
    """
    warnings: List[str] = []

    # Determine x_axis
    resolved = x_axis
    if resolved == "auto" or resolved == "time":
        # check what axes are available
        sample = (
            db.query(Metric.epoch, Metric.step)
            .filter(Metric.experiment_id == experiment_id, Metric.user_id == user_id)
            .first()
        )
        has_epoch = sample is not None and sample.epoch is not None
        has_step = sample is not None and sample.step is not None
        if resolved == "auto":
            resolved = "epoch" if has_epoch else ("step" if has_step else "index")
        elif resolved == "time":
            warnings.append("Metric 表暂无独立 time 列，已降级为 step")
            resolved = "step" if has_step else ("epoch" if has_epoch else "index")

    series_list = []
    for mname in metric_names:
        rows = (
            db.query(Metric)
            .filter(
                Metric.experiment_id == experiment_id,
                Metric.user_id == user_id,
                Metric.metric_name == mname,
            )
            .order_by(Metric.epoch.asc().nullslast(), Metric.step.asc().nullslast(), Metric.id.asc())
            .all()
        )
        if not rows:
            warnings.append(f"指标 {mname} 无数据")
            continue

        points = []
        for idx, r in enumerate(rows):
            if resolved == "epoch":
                x = r.epoch if r.epoch is not None else idx + 1
            elif resolved == "step":
                x = r.step if r.step is not None else idx + 1
            else:
                x = idx + 1
            points.append({
                "x": x,
                "raw_y": r.metric_value,
                "epoch": r.epoch,
                "step": r.step,
                "time": None,
            })

        # sort by x
        points.sort(key=lambda p: p["x"])

        # smooth
        raw_ys = [p["raw_y"] for p in points]
        smoothed = smooth(raw_ys, smooth_window)
        for i, p in enumerate(points):
            p["y"] = round(smoothed[i], 8)

        direction = get_metric_direction(mname)
        bp = _best_point(points, direction) if show_best else None
        lp = _last_point(points)

        series_list.append({
            "metric_name": mname,
            "points": points,
            "best_point": bp,
            "last_point": lp,
            "direction": direction,
            "point_count": len(points),
        })

    return resolved, series_list, warnings


# ─── Experiment summary ─────────────────────────────────────────────────

def summarize_experiment(db: Session, experiment_id: int, user_id: int) -> List[dict]:
    """Return per-metric summary for an experiment."""
    names = get_metric_names(db, experiment_id, user_id)
    result = []
    for mname in names:
        rows = (
            db.query(Metric)
            .filter(Metric.experiment_id == experiment_id, Metric.user_id == user_id, Metric.metric_name == mname)
            .order_by(Metric.epoch.asc().nullslast(), Metric.step.asc().nullslast(), Metric.id.asc())
            .all()
        )
        if not rows:
            continue
        direction = get_metric_direction(mname)
        values = [r.metric_value for r in rows]
        if direction == "lower_better":
            best_idx = values.index(min(values))
        else:
            best_idx = values.index(max(values))
        best_row = rows[best_idx]
        last_row = rows[-1]
        result.append({
            "metric_name": mname,
            "direction": direction,
            "best_value": best_row.metric_value,
            "best_epoch": best_row.epoch,
            "best_step": best_row.step,
            "best_time": None,
            "last_value": last_row.metric_value,
            "last_epoch": last_row.epoch,
            "last_step": last_row.step,
            "last_time": None,
            "record_count": len(rows),
        })
    return result


# ─── Project summary ────────────────────────────────────────────────────

def summarize_project(db: Session, project_id: int, user_id: int) -> dict:
    """Project-level experiment counts & status breakdown."""
    exps = (
        db.query(Experiment)
        .filter(Experiment.project_id == project_id, Experiment.user_id == user_id)
        .all()
    )
    status_counts: Dict[str, int] = {}
    best_count = 0
    paper_count = 0
    for e in exps:
        status_counts[e.status] = status_counts.get(e.status, 0) + 1
        if e.is_best:
            best_count += 1
        if e.is_paper_used:
            paper_count += 1
    return {
        "project_id": project_id,
        "experiment_count": len(exps),
        "status_counts": status_counts,
        "best_count": best_count,
        "paper_count": paper_count,
    }


# ─── Dashboard summary ──────────────────────────────────────────────────

def get_user_dashboard_summary(db: Session, user_id: int) -> dict:
    """Aggregate stats for the dashboard."""
    project_count = db.query(func.count(Project.id)).filter(Project.user_id == user_id).scalar() or 0
    exp_count = db.query(func.count(Experiment.id)).filter(Experiment.user_id == user_id).scalar() or 0

    status_rows = (
        db.query(Experiment.status, func.count(Experiment.id))
        .filter(Experiment.user_id == user_id)
        .group_by(Experiment.status)
        .all()
    )
    status_counts = {s: c for s, c in status_rows}

    best_count = db.query(func.count(Experiment.id)).filter(Experiment.user_id == user_id, Experiment.is_best == True).scalar() or 0
    paper_count = db.query(func.count(Experiment.id)).filter(Experiment.user_id == user_id, Experiment.is_paper_used == True).scalar() or 0

    return {
        "project_count": project_count,
        "experiment_count": exp_count,
        "completed_count": status_counts.get("completed", 0),
        "running_count": status_counts.get("running", 0),
        "failed_count": status_counts.get("failed", 0),
        "interrupted_count": status_counts.get("interrupted", 0),
        "best_count": best_count,
        "paper_count": paper_count,
        "status_counts": status_counts,
    }


# ─── Ranking ─────────────────────────────────────────────────────────────

RECOMMENDED_METRICS = ["psnr", "ssim", "accuracy", "acc", "f1", "dice", "val_loss", "loss"]


def get_ranking_by_metric(
    db: Session, project_id: int, metric_name: str, user_id: int, limit: int = 5
) -> List[dict]:
    """Return top experiments for a metric within a project."""
    direction = get_metric_direction(metric_name)

    # subquery: best value per experiment
    from sqlalchemy import case
    if direction == "lower_better":
        agg = func.min(Metric.metric_value)
    else:
        agg = func.max(Metric.metric_value)

    rows = (
        db.query(
            Metric.experiment_id,
            agg.label("best_value"),
        )
        .filter(
            Metric.project_id == project_id,
            Metric.user_id == user_id,
            Metric.metric_name == metric_name,
        )
        .group_by(Metric.experiment_id)
        .all()
    )

    # sort
    ranked = sorted(rows, key=lambda r: r.best_value, reverse=(direction == "higher_better"))
    ranked = ranked[:limit]

    result = []
    for rank, r in enumerate(ranked, 1):
        exp = db.query(Experiment).filter(Experiment.id == r.experiment_id).first()
        if not exp:
            continue
        # find the actual best row for epoch/step
        if direction == "lower_better":
            best_row = (
                db.query(Metric)
                .filter(Metric.experiment_id == r.experiment_id, Metric.user_id == user_id, Metric.metric_name == metric_name)
                .order_by(Metric.metric_value.asc())
                .first()
            )
        else:
            best_row = (
                db.query(Metric)
                .filter(Metric.experiment_id == r.experiment_id, Metric.user_id == user_id, Metric.metric_name == metric_name)
                .order_by(Metric.metric_value.desc())
                .first()
            )
        result.append({
            "rank": rank,
            "experiment_id": exp.id,
            "experiment_name": exp.name,
            "best_value": r.best_value,
            "best_epoch": best_row.epoch if best_row else None,
            "best_step": best_row.step if best_row else None,
            "is_best": exp.is_best,
            "is_paper_used": exp.is_paper_used,
        })
    return result
