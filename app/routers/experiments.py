import datetime
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.core.security import get_current_user, get_current_user_optional
from app.core.templates import templates
from app.database.session import get_db
from app.database.models import Experiment, Metric, Project, UploadedFile, User

STATUS_LABELS = {
    "pending": "待开始",
    "running": "进行中",
    "completed": "已完成",
    "failed": "失败",
    "interrupted": "中断",
    "abandoned": "废弃",
    "paper_used": "论文采用",
}

STATUS_COLORS = {
    "pending": "warning",
    "running": "primary",
    "completed": "success",
    "failed": "danger",
    "interrupted": "secondary",
    "abandoned": "dark",
    "paper_used": "info",
}

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


def _generate_experiment_code(db: Session, project_id: int) -> str:
    """Generate experiment code like EXP-20260503-001."""
    today = datetime.date.today().strftime("%Y%m%d")
    prefix = f"EXP-{today}-"
    last = (
        db.query(Experiment)
        .filter(
            Experiment.project_id == project_id,
            Experiment.experiment_code.like(f"{prefix}%"),
        )
        .order_by(Experiment.experiment_code.desc())
        .first()
    )
    if last and last.experiment_code:
        try:
            seq = int(last.experiment_code.split("-")[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:03d}"


def _get_experiment_owned(db: Session, experiment_id: int, user_id: int):
    exp = (
        db.query(Experiment)
        .filter(Experiment.id == experiment_id, Experiment.user_id == user_id)
        .first()
    )
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    return exp


def _get_project_owned(db: Session, project_id: int, user_id: int):
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == user_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def _exp_to_dict(exp: Experiment) -> dict:
    return {
        "id": exp.id,
        "project_id": exp.project_id,
        "name": exp.name,
        "experiment_code": exp.experiment_code,
        "description": exp.description,
        "status": exp.status,
        "tags": exp.tags,
        "started_at": exp.started_at.isoformat() if exp.started_at else None,
        "ended_at": exp.ended_at.isoformat() if exp.ended_at else None,
        "created_at": exp.created_at.isoformat() if exp.created_at else None,
        "updated_at": exp.updated_at.isoformat() if exp.updated_at else None,
        "is_best": exp.is_best,
        "is_paper_used": exp.is_paper_used,
        "is_archived": exp.is_archived,
        "note": exp.note,
        "metadata_json": exp.metadata_json,
    }


# ---------------------------------------------------------------------------
# Page router
# ---------------------------------------------------------------------------
router = APIRouter(tags=["experiments"])


@router.get("/projects/{project_id}/experiments/new")
def page_experiment_new(
    request: Request,
    project_id: int,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    project = _get_project_owned(db, project_id, current_user.id)
    project.area_label = RESEARCH_AREAS.get(project.research_area, project.research_area)
    return templates.TemplateResponse("experiment_form.html", {
        "request": request,
        "title": "新建实验",
        "current_user": current_user,
        "project": project,
        "experiment": None,
        "status_labels": STATUS_LABELS,
    })


@router.get("/experiments/{experiment_id}")
def page_experiment_detail(
    request: Request,
    experiment_id: int,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    exp = _get_experiment_owned(db, experiment_id, current_user.id)
    project = db.query(Project).filter(Project.id == exp.project_id).first()
    project.area_label = RESEARCH_AREAS.get(project.research_area, project.research_area)

    # parse metadata_json for display
    try:
        metadata = json.loads(exp.metadata_json) if exp.metadata_json else {}
    except (json.JSONDecodeError, TypeError):
        metadata = {}

    return templates.TemplateResponse("experiment_detail.html", {
        "request": request,
        "title": exp.name,
        "current_user": current_user,
        "project": project,
        "experiment": exp,
        "metadata": metadata,
        "status_labels": STATUS_LABELS,
        "status_colors": STATUS_COLORS,
    })


@router.get("/experiments/{experiment_id}/edit")
def page_experiment_edit(
    request: Request,
    experiment_id: int,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    exp = _get_experiment_owned(db, experiment_id, current_user.id)
    project = db.query(Project).filter(Project.id == exp.project_id).first()
    project.area_label = RESEARCH_AREAS.get(project.research_area, project.research_area)
    return templates.TemplateResponse("experiment_form.html", {
        "request": request,
        "title": f"编辑实验 — {exp.name}",
        "current_user": current_user,
        "project": project,
        "experiment": exp,
        "status_labels": STATUS_LABELS,
    })


@router.get("/experiments/{experiment_id}/upload")
def upload_page(
    request: Request,
    experiment_id: int,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    exp = _get_experiment_owned(db, experiment_id, current_user.id)
    project = db.query(Project).filter(Project.id == exp.project_id).first()
    project.area_label = RESEARCH_AREAS.get(project.research_area, project.research_area)
    from app.core.config import settings as _settings
    return templates.TemplateResponse("upload.html", {
        "request": request,
        "title": "上传文件",
        "current_user": current_user,
        "project": project,
        "experiment": exp,
        "max_size_mb": _settings.UPLOAD_MAX_SIZE_MB,
    })


# ---------------------------------------------------------------------------
# API router
# ---------------------------------------------------------------------------
api_router = APIRouter(tags=["experiments-api"])


class ExperimentCreate(BaseModel):
    name: str
    description: str = ""
    status: str = "pending"
    tags: str = ""
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    is_best: bool = False
    is_paper_used: bool = False
    note: str = ""
    metadata_json: str = "{}"


class ExperimentUpdate(BaseModel):
    name: str
    description: str = ""
    status: str = "pending"
    tags: str = ""
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    is_best: bool = False
    is_paper_used: bool = False
    is_archived: bool = False
    note: str = ""
    metadata_json: str = "{}"


class ExperimentToggle(BaseModel):
    value: bool


def _parse_dt(s: Optional[str]) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@api_router.get("/api/projects/{project_id}/experiments")
def api_list_experiments(
    project_id: int,
    status: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sort: str = Query("created_desc"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_owned(db, project_id, current_user.id)
    query = db.query(Experiment).filter(
        Experiment.project_id == project_id,
        Experiment.user_id == current_user.id,
    )
    if status:
        query = query.filter(Experiment.status == status)
    if tag:
        query = query.filter(Experiment.tags.contains(tag))
    if q:
        query = query.filter(Experiment.name.contains(q))

    if sort == "created_asc":
        query = query.order_by(Experiment.created_at.asc())
    else:
        query = query.order_by(Experiment.created_at.desc())

    rows = query.all()
    return [_exp_to_dict(e) for e in rows]


@api_router.post("/api/projects/{project_id}/experiments")
def api_create_experiment(
    project_id: int,
    req: ExperimentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_owned(db, project_id, current_user.id)
    if not req.name or not req.name.strip():
        return JSONResponse({"ok": False, "msg": "实验名称不能为空"}, status_code=400)
    if req.status not in STATUS_LABELS:
        return JSONResponse({"ok": False, "msg": "无效的状态值"}, status_code=400)

    # validate metadata_json
    if req.metadata_json:
        try:
            json.loads(req.metadata_json)
        except json.JSONDecodeError:
            return JSONResponse({"ok": False, "msg": "metadata_json 格式不正确"}, status_code=400)

    code = _generate_experiment_code(db, project_id)
    exp = Experiment(
        user_id=current_user.id,
        project_id=project_id,
        name=req.name.strip(),
        experiment_code=code,
        description=req.description.strip(),
        status=req.status,
        tags=req.tags.strip(),
        started_at=_parse_dt(req.started_at),
        ended_at=_parse_dt(req.ended_at),
        is_best=req.is_best,
        is_paper_used=req.is_paper_used,
        note=req.note.strip(),
        metadata_json=req.metadata_json,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return {"ok": True, "msg": "实验创建成功", "experiment_id": exp.id}


@api_router.get("/api/experiments/{experiment_id}")
def api_get_experiment(
    experiment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exp = _get_experiment_owned(db, experiment_id, current_user.id)
    return _exp_to_dict(exp)


@api_router.put("/api/experiments/{experiment_id}")
def api_update_experiment(
    experiment_id: int,
    req: ExperimentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exp = _get_experiment_owned(db, experiment_id, current_user.id)
    if not req.name or not req.name.strip():
        return JSONResponse({"ok": False, "msg": "实验名称不能为空"}, status_code=400)
    if req.status not in STATUS_LABELS:
        return JSONResponse({"ok": False, "msg": "无效的状态值"}, status_code=400)
    if req.metadata_json:
        try:
            json.loads(req.metadata_json)
        except json.JSONDecodeError:
            return JSONResponse({"ok": False, "msg": "metadata_json 格式不正确"}, status_code=400)

    exp.name = req.name.strip()
    exp.description = req.description.strip()
    exp.status = req.status
    exp.tags = req.tags.strip()
    exp.started_at = _parse_dt(req.started_at)
    exp.ended_at = _parse_dt(req.ended_at)
    exp.is_best = req.is_best
    exp.is_paper_used = req.is_paper_used
    exp.is_archived = req.is_archived
    exp.note = req.note.strip()
    exp.metadata_json = req.metadata_json
    db.commit()
    return {"ok": True, "msg": "实验更新成功"}


@api_router.delete("/api/experiments/{experiment_id}")
def api_delete_experiment(
    experiment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exp = _get_experiment_owned(db, experiment_id, current_user.id)
    db.delete(exp)
    db.commit()
    return {"ok": True, "msg": "实验已删除"}


@api_router.post("/api/experiments/{experiment_id}/toggle-best")
def api_toggle_best(
    experiment_id: int,
    req: ExperimentToggle,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exp = _get_experiment_owned(db, experiment_id, current_user.id)
    exp.is_best = req.value
    db.commit()
    return {"ok": True, "msg": "已更新最优标记"}


@api_router.post("/api/experiments/{experiment_id}/toggle-paper")
def api_toggle_paper(
    experiment_id: int,
    req: ExperimentToggle,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exp = _get_experiment_owned(db, experiment_id, current_user.id)
    exp.is_paper_used = req.value
    db.commit()
    return {"ok": True, "msg": "已更新论文采用标记"}


@api_router.post("/api/experiments/{experiment_id}/toggle-archive")
def api_toggle_archive(
    experiment_id: int,
    req: ExperimentToggle,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exp = _get_experiment_owned(db, experiment_id, current_user.id)
    exp.is_archived = req.value
    db.commit()
    return {"ok": True, "msg": "已更新归档状态"}


class ParseLogRequest(BaseModel):
    file_id: int
    overwrite: bool = False


@api_router.post("/api/experiments/{experiment_id}/parse-log")
def api_parse_log(
    experiment_id: int,
    req: ParseLogRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 验证实验归属
    exp = _get_experiment_owned(db, experiment_id, current_user.id)

    # 验证文件归属
    fobj = (
        db.query(UploadedFile)
        .filter(
            UploadedFile.id == req.file_id,
            UploadedFile.user_id == current_user.id,
            UploadedFile.experiment_id == experiment_id,
        )
        .first()
    )
    if not fobj:
        return JSONResponse({"ok": False, "msg": "文件不存在"}, status_code=404)

    # 仅允许日志类文件
    if fobj.file_ext not in (".log", ".txt", ".csv", ".json"):
        return JSONResponse({"ok": False, "msg": f"不支持解析 {fobj.file_ext} 类型文件"}, status_code=400)

    # 读取文件
    from app.core.config import DATA_DIR
    abs_path = DATA_DIR / fobj.file_path
    if not abs_path.exists():
        return JSONResponse({"ok": False, "msg": "文件不存在于磁盘"}, status_code=404)

    try:
        raw = abs_path.read_bytes()
        from app.services.encryption import is_encrypted, decrypt_bytes
        if is_encrypted(raw):
            from app.core.config import settings as _s
            raw = decrypt_bytes(raw, _s.SECRET_KEY) or raw
        file_text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        return JSONResponse({"ok": False, "msg": f"读取文件失败: {e}"}, status_code=500)

    # 解析
    from app.services.log_parser import LogParser
    parser = LogParser()
    result = parser.parse_text(file_text)

    if not result.records:
        return {
            "ok": True,
            "msg": "未解析到任何指标",
            "parsed_records_count": 0,
            "metric_names": [],
            "epoch_min": None,
            "epoch_max": None,
            "step_min": None,
            "step_max": None,
            "line_count": result.line_count,
            "parsed_line_count": result.parsed_line_count,
            "skipped_line_count": result.skipped_line_count,
            "warnings": result.warnings,
        }

    # overwrite: 删除该 file 之前解析出的指标
    if req.overwrite:
        db.query(Metric).filter(
            Metric.experiment_id == experiment_id,
            Metric.source_file_id == req.file_id,
            Metric.user_id == current_user.id,
        ).delete(synchronize_session=False)
        db.flush()

    # 去重：查已有记录
    existing = set()
    if not req.overwrite:
        rows = (
            db.query(Metric.metric_name, Metric.epoch, Metric.step)
            .filter(
                Metric.experiment_id == experiment_id,
                Metric.source_file_id == req.file_id,
                Metric.user_id == current_user.id,
            )
            .all()
        )
        existing = {(r.metric_name, r.epoch, r.step) for r in rows}

    # 批量写入
    inserted = 0
    for rec in result.records:
        dup_key = (rec.metric_name, rec.epoch, rec.step)
        if dup_key in existing:
            continue
        existing.add(dup_key)
        db.add(Metric(
            user_id=current_user.id,
            project_id=exp.project_id,
            experiment_id=experiment_id,
            metric_name=rec.metric_name,
            metric_value=rec.metric_value,
            epoch=rec.epoch,
            step=rec.step,
            source_file_id=req.file_id,
        ))
        inserted += 1

    db.commit()

    return {
        "ok": True,
        "msg": f"成功解析 {inserted} 条指标",
        "parsed_records_count": inserted,
        "metric_names": result.metric_names,
        "epoch_min": result.epoch_min,
        "epoch_max": result.epoch_max,
        "step_min": result.step_min,
        "step_max": result.step_max,
        "line_count": result.line_count,
        "parsed_line_count": result.parsed_line_count,
        "skipped_line_count": result.skipped_line_count,
        "warnings": result.warnings,
    }


class ImportCsvRequest(BaseModel):
    file_id: int
    overwrite: bool = False


@api_router.post("/api/experiments/{experiment_id}/import-csv")
def api_import_csv(
    experiment_id: int,
    req: ImportCsvRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 验证实验归属
    exp = _get_experiment_owned(db, experiment_id, current_user.id)

    # 验证文件归属
    fobj = (
        db.query(UploadedFile)
        .filter(
            UploadedFile.id == req.file_id,
            UploadedFile.user_id == current_user.id,
            UploadedFile.experiment_id == experiment_id,
        )
        .first()
    )
    if not fobj:
        return JSONResponse({"ok": False, "msg": "文件不存在"}, status_code=404)

    if fobj.file_ext != ".csv":
        return JSONResponse({"ok": False, "msg": f"仅支持 .csv 文件，当前为 {fobj.file_ext}"}, status_code=400)

    from app.core.config import DATA_DIR
    abs_path = DATA_DIR / fobj.file_path
    if not abs_path.exists():
        return JSONResponse({"ok": False, "msg": "文件不存在于磁盘"}, status_code=404)

    try:
        raw = abs_path.read_bytes()
        from app.services.encryption import is_encrypted, decrypt_bytes
        if is_encrypted(raw):
            from app.core.config import settings as _s
            raw = decrypt_bytes(raw, _s.SECRET_KEY) or raw
        file_text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        return JSONResponse({"ok": False, "msg": f"读取文件失败: {e}"}, status_code=500)

    from app.services.metric_service import import_metrics_from_csv
    result = import_metrics_from_csv(
        db=db,
        file_text=file_text,
        user_id=current_user.id,
        project_id=exp.project_id,
        experiment_id=experiment_id,
        source_file_id=req.file_id,
        overwrite=req.overwrite,
    )

    return {
        "ok": True,
        "msg": f"成功导入 {result.imported_records_count} 条指标",
        "imported_records_count": result.imported_records_count,
        "metric_names": result.metric_names,
        "epoch_min": result.epoch_min,
        "epoch_max": result.epoch_max,
        "step_min": result.step_min,
        "step_max": result.step_max,
        "time_min": result.time_min,
        "time_max": result.time_max,
        "skipped_columns": result.skipped_columns,
        "skipped_rows": result.skipped_rows,
        "warnings": result.warnings,
    }


# ── Config file parsing ─────────────────────────────────────────────────

@api_router.get("/api/experiments/{experiment_id}/parse-config/{file_id}")
def api_parse_config(
    experiment_id: int,
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Parse a config file (YAML/JSON/TOML/INI) and return flattened hyperparameters."""
    exp = _get_experiment_owned(db, experiment_id, current_user.id)

    record = (
        db.query(UploadedFile)
        .filter(UploadedFile.id == file_id, UploadedFile.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="文件不存在")

    from app.core.config import BASE_DIR
    abs_path = BASE_DIR / "data" / record.file_path
    from app.services.config_parser import parse_config_file
    flat, fmt = parse_config_file(str(abs_path), secret=settings.SECRET_KEY)
    if flat is None:
        return {"ok": False, "msg": f"无法解析配置文件 (format={fmt})", "params": {}, "format": fmt}

    return {"ok": True, "params": flat, "format": fmt, "param_count": len(flat)}
