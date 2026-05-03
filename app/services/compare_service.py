"""Compare service — multi-experiment metric comparison."""

from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import distinct

from app.database.models import Experiment, Metric
from app.services.summary_service import get_metric_direction, smooth


def get_project_metric_names(db: Session, project_id: int, user_id: int) -> List[str]:
    """Return sorted distinct metric names across all experiments in a project."""
    rows = (
        db.query(distinct(Metric.metric_name))
        .filter(Metric.project_id == project_id, Metric.user_id == user_id)
        .all()
    )
    return sorted([r[0] for r in rows])


def compare_metrics(
    db: Session,
    experiment_ids: List[int],
    metric_name: str,
    user_id: int,
    x_axis: str = "auto",
    smooth_window: int = 1,
    show_best: bool = True,
    styles: Optional[Dict[int, dict]] = None,
) -> Tuple[str, List[dict], List[str]]:
    """Build comparison series for multiple experiments on a single metric.

    Args:
        styles: optional {experiment_id: {display_name, color, line_type, marker}} overrides.

    Returns (resolved_x_axis, series_list, warnings).
    """
    warnings: List[str] = []
    styles = styles or {}

    # Resolve x_axis from first experiment
    resolved = x_axis
    if resolved in ("auto", "time"):
        for eid in experiment_ids:
            sample = (
                db.query(Metric.epoch, Metric.step)
                .filter(Metric.experiment_id == eid, Metric.user_id == user_id, Metric.metric_name == metric_name)
                .first()
            )
            if sample:
                has_epoch = sample.epoch is not None
                has_step = sample.step is not None
                if resolved == "auto":
                    resolved = "epoch" if has_epoch else ("step" if has_step else "index")
                else:
                    warnings.append("Metric 表暂无独立 time 列，已降级为 step")
                    resolved = "step" if has_step else ("epoch" if has_epoch else "index")
                break
        else:
            resolved = "index"

    direction = get_metric_direction(metric_name)

    series_list = []
    for eid in experiment_ids:
        exp = db.query(Experiment).filter(Experiment.id == eid).first()
        if not exp:
            warnings.append(f"实验 {eid} 不存在")
            continue

        style = styles.get(eid, {})
        display_name = style.get("display_name") or exp.name

        rows = (
            db.query(Metric)
            .filter(
                Metric.experiment_id == eid,
                Metric.user_id == user_id,
                Metric.metric_name == metric_name,
            )
            .order_by(Metric.epoch.asc().nullslast(), Metric.step.asc().nullslast(), Metric.id.asc())
            .all()
        )

        if not rows:
            warnings.append(f"实验 {display_name} 无 {metric_name} 数据")
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

        points.sort(key=lambda p: p["x"])

        raw_ys = [p["raw_y"] for p in points]
        smoothed = smooth(raw_ys, smooth_window)
        for i, p in enumerate(points):
            p["y"] = round(smoothed[i], 8)

        # best / last
        if show_best:
            if direction == "lower_better":
                bp = min(points, key=lambda p: p["raw_y"])
            else:
                bp = max(points, key=lambda p: p["raw_y"])
            best_point = {"x": bp["x"], "y": bp["raw_y"], "epoch": bp.get("epoch"), "step": bp.get("step")}
        else:
            best_point = None

        last_p = points[-1]
        last_point = {"x": last_p["x"], "y": last_p["raw_y"], "epoch": last_p.get("epoch"), "step": last_p.get("step")}

        series_list.append({
            "experiment_id": eid,
            "experiment_name": exp.name,
            "display_name": display_name,
            "color": style.get("color"),
            "line_type": style.get("line_type", "solid"),
            "marker": style.get("marker", "circle"),
            "points": points,
            "best_point": best_point,
            "last_point": last_point,
            "direction": direction,
            "point_count": len(points),
        })

    return resolved, series_list, warnings
