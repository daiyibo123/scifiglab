from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.security import get_current_user, get_current_user_optional
from app.core.templates import templates
from app.database.session import get_db
from app.database.models import Project, Experiment, User

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

# ---------------------------------------------------------------------------
# Page router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/projects", tags=["projects"])


def _login_or_404(current_user, db, project_id):
    """Return (user, project) or raise appropriate response."""
    if current_user is None:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.get("")
def page_project_list(
    request: Request,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)

    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.updated_at.desc())
        .all()
    )
    # attach experiment count
    for p in projects:
        p.exp_count = (
            db.query(func.count(Experiment.id))
            .filter(Experiment.project_id == p.id)
            .scalar()
        )
        p.area_label = RESEARCH_AREAS.get(p.research_area, p.research_area)

    return templates.TemplateResponse("projects.html", {
        "request": request,
        "title": "项目列表",
        "current_user": current_user,
        "projects": projects,
        "research_areas": RESEARCH_AREAS,
    })


@router.get("/new")
def page_project_new(
    request: Request,
    current_user=Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("project_form.html", {
        "request": request,
        "title": "新建项目",
        "current_user": current_user,
        "research_areas": RESEARCH_AREAS,
        "project": None,
    })


@router.get("/{project_id}")
def page_project_detail(
    request: Request,
    project_id: int,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    project = _login_or_404(current_user, db, project_id)
    project.area_label = RESEARCH_AREAS.get(project.research_area, project.research_area)

    experiments = (
        db.query(Experiment)
        .filter(Experiment.project_id == project_id, Experiment.user_id == current_user.id)
        .order_by(Experiment.updated_at.desc())
        .all()
    )

    return templates.TemplateResponse("project_detail.html", {
        "request": request,
        "title": project.name,
        "current_user": current_user,
        "project": project,
        "experiments": experiments,
    })


@router.get("/{project_id}/edit")
def page_project_edit(
    request: Request,
    project_id: int,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    project = _login_or_404(current_user, db, project_id)
    return templates.TemplateResponse("project_form.html", {
        "request": request,
        "title": f"编辑项目 — {project.name}",
        "current_user": current_user,
        "research_areas": RESEARCH_AREAS,
        "project": project,
    })


# ---------------------------------------------------------------------------
# API router
# ---------------------------------------------------------------------------
api_router = APIRouter(prefix="/api/projects", tags=["projects-api"])


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    research_area: str = "other"


class ProjectUpdate(BaseModel):
    name: str
    description: str = ""
    research_area: str = "other"


@api_router.get("")
def api_list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.updated_at.desc())
        .all()
    )
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "research_area": p.research_area,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in rows
    ]


@api_router.post("")
def api_create_project(
    req: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not req.name or not req.name.strip():
        return JSONResponse({"ok": False, "msg": "项目名称不能为空"}, status_code=400)
    project = Project(
        user_id=current_user.id,
        name=req.name.strip(),
        description=req.description.strip(),
        research_area=req.research_area,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"ok": True, "msg": "项目创建成功", "project_id": project.id}


@api_router.put("/{project_id}")
def api_update_project(
    project_id: int,
    req: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        return JSONResponse({"ok": False, "msg": "项目不存在"}, status_code=404)
    if not req.name or not req.name.strip():
        return JSONResponse({"ok": False, "msg": "项目名称不能为空"}, status_code=400)

    project.name = req.name.strip()
    project.description = req.description.strip()
    project.research_area = req.research_area
    db.commit()
    return {"ok": True, "msg": "项目更新成功"}


@api_router.delete("/{project_id}")
def api_delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        return JSONResponse({"ok": False, "msg": "项目不存在"}, status_code=404)
    db.delete(project)
    db.commit()
    return {"ok": True, "msg": "项目已删除"}
