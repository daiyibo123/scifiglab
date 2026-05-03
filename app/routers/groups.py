from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user, get_current_user_optional
from app.core.templates import templates
from app.database.session import get_db
from app.database.models import (
    Experiment, ExperimentGroup, ExperimentGroupItem, Project, User,
)

router = APIRouter(prefix="/groups", tags=["groups"])
api_router = APIRouter(tags=["groups-api"])

GROUP_TYPE_LABELS = {
    "ablation": "消融实验",
    "comparison": "方法对比",
    "parameter": "参数搜索",
    "final": "最终结果",
    "custom": "自定义",
}


# ── Page routes ──────────────────────────────────────────────────────────

@router.get("")
def group_list(
    request: Request,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    groups = (
        db.query(ExperimentGroup)
        .filter(ExperimentGroup.user_id == current_user.id)
        .order_by(ExperimentGroup.created_at.desc())
        .all()
    )
    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return templates.TemplateResponse("groups.html", {
        "request": request,
        "title": "实验组",
        "current_user": current_user,
        "groups": groups,
        "projects": projects,
        "group_type_labels": GROUP_TYPE_LABELS,
    })


@router.get("/{group_id}")
def group_detail(
    request: Request,
    group_id: int,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    group = (
        db.query(ExperimentGroup)
        .filter(ExperimentGroup.id == group_id, ExperimentGroup.user_id == current_user.id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=404, detail="实验组不存在")
    project = db.query(Project).filter(Project.id == group.project_id).first()
    return templates.TemplateResponse("group_detail.html", {
        "request": request,
        "title": group.name,
        "current_user": current_user,
        "group": group,
        "project": project,
        "group_type_labels": GROUP_TYPE_LABELS,
    })


# ── Helpers ──────────────────────────────────────────────────────────────

def _group_to_dict(g: ExperimentGroup) -> dict:
    return {
        "id": g.id,
        "project_id": g.project_id,
        "name": g.name,
        "group_type": g.group_type,
        "description": g.description,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "item_count": len(g.items) if g.items else 0,
    }


def _item_to_dict(item: ExperimentGroupItem, db: Session) -> dict:
    exp = db.query(Experiment).filter(Experiment.id == item.experiment_id).first()
    return {
        "id": item.id,
        "experiment_id": item.experiment_id,
        "experiment_name": exp.name if exp else "?",
        "experiment_code": exp.experiment_code if exp else "?",
        "display_name": item.display_name or (exp.name if exp else ""),
        "sort_order": item.sort_order,
        "curve_color": item.curve_color,
        "curve_style": item.curve_style,
        "marker_symbol": item.marker_symbol,
    }


# ── API: CRUD ────────────────────────────────────────────────────────────

@api_router.get("/api/groups")
def api_list_groups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    groups = (
        db.query(ExperimentGroup)
        .filter(ExperimentGroup.user_id == current_user.id)
        .order_by(ExperimentGroup.created_at.desc())
        .all()
    )
    return [_group_to_dict(g) for g in groups]


class GroupCreate(BaseModel):
    project_id: int
    name: str
    group_type: str = "custom"
    description: str = ""


@api_router.post("/api/groups")
def api_create_group(
    req: GroupCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proj = db.query(Project).filter(Project.id == req.project_id, Project.user_id == current_user.id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="组名不能为空")

    group = ExperimentGroup(
        user_id=current_user.id,
        project_id=req.project_id,
        name=req.name.strip(),
        group_type=req.group_type if req.group_type in GROUP_TYPE_LABELS else "custom",
        description=req.description.strip(),
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return {"ok": True, "msg": "实验组创建成功", "group": _group_to_dict(group)}


@api_router.get("/api/groups/{group_id}")
def api_get_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = (
        db.query(ExperimentGroup)
        .filter(ExperimentGroup.id == group_id, ExperimentGroup.user_id == current_user.id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=404, detail="实验组不存在")
    items = [_item_to_dict(i, db) for i in sorted(group.items, key=lambda i: i.sort_order)]
    d = _group_to_dict(group)
    d["items"] = items
    return d


class GroupUpdate(BaseModel):
    name: str
    group_type: str = "custom"
    description: str = ""


@api_router.put("/api/groups/{group_id}")
def api_update_group(
    group_id: int,
    req: GroupUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = db.query(ExperimentGroup).filter(ExperimentGroup.id == group_id, ExperimentGroup.user_id == current_user.id).first()
    if not group:
        raise HTTPException(status_code=404, detail="实验组不存在")
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="组名不能为空")
    group.name = req.name.strip()
    group.group_type = req.group_type if req.group_type in GROUP_TYPE_LABELS else "custom"
    group.description = req.description.strip()
    db.commit()
    return {"ok": True, "msg": "更新成功"}


@api_router.delete("/api/groups/{group_id}")
def api_delete_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = db.query(ExperimentGroup).filter(ExperimentGroup.id == group_id, ExperimentGroup.user_id == current_user.id).first()
    if not group:
        raise HTTPException(status_code=404, detail="实验组不存在")
    db.delete(group)
    db.commit()
    return {"ok": True, "msg": "实验组已删除"}


# ── API: Items ───────────────────────────────────────────────────────────

class ItemAdd(BaseModel):
    experiment_id: int
    display_name: str = ""
    sort_order: int = 0
    curve_color: str = ""
    curve_style: str = ""
    marker_symbol: str = ""


@api_router.post("/api/groups/{group_id}/items")
def api_add_item(
    group_id: int,
    req: ItemAdd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = db.query(ExperimentGroup).filter(ExperimentGroup.id == group_id, ExperimentGroup.user_id == current_user.id).first()
    if not group:
        raise HTTPException(status_code=404, detail="实验组不存在")

    exp = db.query(Experiment).filter(
        Experiment.id == req.experiment_id,
        Experiment.user_id == current_user.id,
        Experiment.project_id == group.project_id,
    ).first()
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在或不属于该项目")

    # Check duplicate
    exists = db.query(ExperimentGroupItem).filter(
        ExperimentGroupItem.group_id == group_id,
        ExperimentGroupItem.experiment_id == req.experiment_id,
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="该实验已在组中")

    item = ExperimentGroupItem(
        user_id=current_user.id,
        group_id=group_id,
        experiment_id=req.experiment_id,
        display_name=req.display_name.strip(),
        sort_order=req.sort_order,
        curve_color=req.curve_color.strip(),
        curve_style=req.curve_style.strip(),
        marker_symbol=req.marker_symbol.strip(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"ok": True, "msg": "实验已添加到组", "item": _item_to_dict(item, db)}


class ItemUpdate(BaseModel):
    display_name: str = ""
    sort_order: int = 0
    curve_color: str = ""
    curve_style: str = ""
    marker_symbol: str = ""


@api_router.put("/api/groups/{group_id}/items/{item_id}")
def api_update_item(
    group_id: int,
    item_id: int,
    req: ItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.query(ExperimentGroupItem).filter(
        ExperimentGroupItem.id == item_id,
        ExperimentGroupItem.group_id == group_id,
        ExperimentGroupItem.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="成员不存在")
    item.display_name = req.display_name.strip()
    item.sort_order = req.sort_order
    item.curve_color = req.curve_color.strip()
    item.curve_style = req.curve_style.strip()
    item.marker_symbol = req.marker_symbol.strip()
    db.commit()
    return {"ok": True, "msg": "更新成功"}


@api_router.delete("/api/groups/{group_id}/items/{item_id}")
def api_delete_item(
    group_id: int,
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.query(ExperimentGroupItem).filter(
        ExperimentGroupItem.id == item_id,
        ExperimentGroupItem.group_id == group_id,
        ExperimentGroupItem.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="成员不存在")
    db.delete(item)
    db.commit()
    return {"ok": True, "msg": "已移除"}


# ── API: Paper table ─────────────────────────────────────────────────────

@api_router.get("/api/groups/{group_id}/available-metrics")
def api_group_available_metrics(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = db.query(ExperimentGroup).filter(
        ExperimentGroup.id == group_id, ExperimentGroup.user_id == current_user.id
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="实验组不存在")
    from sqlalchemy import distinct
    exp_ids = [i.experiment_id for i in group.items]
    if not exp_ids:
        return {"metric_names": []}
    from app.database.models import Metric
    rows = (
        db.query(distinct(Metric.metric_name))
        .filter(Metric.experiment_id.in_(exp_ids), Metric.user_id == current_user.id)
        .all()
    )
    return {"metric_names": sorted([r[0] for r in rows])}


class PaperTableRequest(BaseModel):
    metric_names: List[str]
    decimals: int = 4
    bold_best: bool = True
    mark_second: bool = False


@api_router.post("/api/groups/{group_id}/table")
def api_generate_table(
    group_id: int,
    req: PaperTableRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not req.metric_names:
        raise HTTPException(status_code=400, detail="请选择至少一个指标")
    from app.services.table_exporter import generate_paper_table
    result = generate_paper_table(
        db, group_id, current_user.id, req.metric_names,
        req.decimals, req.bold_best, req.mark_second,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@api_router.get("/api/groups/{group_id}/table/download-csv")
def api_download_table_csv(
    group_id: int,
    metric_names: List[str] = Query(default=[]),
    decimals: int = Query(default=4),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not metric_names:
        raise HTTPException(status_code=400, detail="请指定指标")
    from app.services.table_exporter import generate_paper_table
    result = generate_paper_table(db, group_id, current_user.id, metric_names, decimals)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    from fastapi.responses import StreamingResponse
    filename = f"group_{group_id}_paper_table.csv"
    return StreamingResponse(
        iter([result["csv_text"]]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@api_router.get("/api/groups/{group_id}/table/download-word")
def api_download_table_word(
    group_id: int,
    metric_names: List[str] = Query(default=[]),
    decimals: int = Query(default=4),
    bold_best: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not metric_names:
        raise HTTPException(status_code=400, detail="请指定指标")
    from app.services.table_exporter import generate_paper_table, export_word_bytes
    result = generate_paper_table(db, group_id, current_user.id, metric_names, decimals, bold_best)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Re-build raw rows for export_word_bytes (need _display_name + metric values)
    raw_rows = []
    for r in result["rows"]:
        row = {"_display_name": r["display_name"]}
        row.update(r["values"])
        raw_rows.append(row)

    docx_bytes = export_word_bytes(
        raw_rows, result["metric_names"], result["directions"],
        result["best_map"], decimals, bold_best,
    )
    from fastapi.responses import Response
    filename = f"group_{group_id}_paper_table.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
