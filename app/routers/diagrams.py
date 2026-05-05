from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user, get_current_user_optional
from app.core.templates import templates
from app.database.session import get_db
from app.database.models import Diagram, Project, User
from app.services.ai_service import AIRequest, generate_diagram_plan

router = APIRouter(prefix="/diagrams", tags=["diagrams"])
api_router = APIRouter(tags=["diagrams-api"])


# ── Pydantic schemas ─────────────────────────────────────────────────────

class DiagramCreate(BaseModel):
    title: str = "未命名流程图"
    description: str = ""
    project_id: Optional[int] = None
    xml_data: str = ""
    thumbnail: str = ""
    layout_direction: str = "TB"
    color_scheme: str = "default"


class DiagramUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    project_id: Optional[int] = None
    xml_data: Optional[str] = None
    thumbnail: Optional[str] = None
    layout_direction: Optional[str] = None
    color_scheme: Optional[str] = None


class DiagramAiRequest(BaseModel):
    prompt: str


# ── Page routes ──────────────────────────────────────────────────────────

@router.get("")
def diagram_list_page(
    request: Request,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    diagrams = (
        db.query(Diagram)
        .filter(Diagram.user_id == current_user.id)
        .order_by(Diagram.updated_at.desc())
        .all()
    )
    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.name)
        .all()
    )
    return templates.TemplateResponse("diagrams.html", {
        "request": request,
        "current_user": current_user,
        "diagrams": diagrams,
        "projects": projects,
    })


@router.get("/new")
def diagram_new_page(
    request: Request,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.name)
        .all()
    )
    return templates.TemplateResponse("diagram_editor.html", {
        "request": request,
        "current_user": current_user,
        "diagram": None,
        "projects": projects,
    })


@router.get("/{diagram_id}/edit")
def diagram_edit_page(
    diagram_id: int,
    request: Request,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    diagram = db.query(Diagram).filter(
        Diagram.id == diagram_id,
        Diagram.user_id == current_user.id,
    ).first()
    if not diagram:
        raise HTTPException(status_code=404, detail="流程图不存在")
    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.name)
        .all()
    )
    return templates.TemplateResponse("diagram_editor.html", {
        "request": request,
        "current_user": current_user,
        "diagram": diagram,
        "projects": projects,
    })


# ── API routes ───────────────────────────────────────────────────────────

@api_router.get("/api/diagrams")
def api_list_diagrams(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    diagrams = (
        db.query(Diagram)
        .filter(Diagram.user_id == current_user.id)
        .order_by(Diagram.updated_at.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "title": d.title,
            "description": d.description,
            "project_id": d.project_id,
            "layout_direction": d.layout_direction,
            "color_scheme": d.color_scheme,
            "thumbnail": d.thumbnail[:100] + "..." if d.thumbnail and len(d.thumbnail) > 100 else d.thumbnail,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        }
        for d in diagrams
    ]


@api_router.post("/api/diagrams")
def api_create_diagram(
    req: DiagramCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    diagram = Diagram(
        user_id=current_user.id,
        title=req.title or "未命名流程图",
        description=req.description,
        project_id=req.project_id,
        xml_data=req.xml_data,
        thumbnail=req.thumbnail,
        layout_direction=req.layout_direction,
        color_scheme=req.color_scheme,
    )
    db.add(diagram)
    db.commit()
    db.refresh(diagram)
    return {"ok": True, "diagram_id": diagram.id}


@api_router.get("/api/diagrams/{diagram_id}")
def api_get_diagram(
    diagram_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    d = db.query(Diagram).filter(
        Diagram.id == diagram_id,
        Diagram.user_id == current_user.id,
    ).first()
    if not d:
        raise HTTPException(status_code=404, detail="流程图不存在")
    return {
        "id": d.id,
        "title": d.title,
        "description": d.description,
        "project_id": d.project_id,
        "xml_data": d.xml_data,
        "thumbnail": d.thumbnail,
        "layout_direction": d.layout_direction,
        "color_scheme": d.color_scheme,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


@api_router.put("/api/diagrams/{diagram_id}")
def api_update_diagram(
    diagram_id: int,
    req: DiagramUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    d = db.query(Diagram).filter(
        Diagram.id == diagram_id,
        Diagram.user_id == current_user.id,
    ).first()
    if not d:
        raise HTTPException(status_code=404, detail="流程图不存在")
    if req.title is not None:
        d.title = req.title
    if req.description is not None:
        d.description = req.description
    if "project_id" in req.model_fields_set:
        d.project_id = req.project_id if req.project_id > 0 else None
    if req.xml_data is not None:
        d.xml_data = req.xml_data
    if req.thumbnail is not None:
        d.thumbnail = req.thumbnail
    if req.layout_direction is not None:
        d.layout_direction = req.layout_direction
    if req.color_scheme is not None:
        d.color_scheme = req.color_scheme
    db.commit()
    return {"ok": True}


@api_router.delete("/api/diagrams/{diagram_id}")
def api_delete_diagram(
    diagram_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    d = db.query(Diagram).filter(
        Diagram.id == diagram_id,
        Diagram.user_id == current_user.id,
    ).first()
    if not d:
        raise HTTPException(status_code=404, detail="流程图不存在")
    db.delete(d)
    db.commit()
    return {"ok": True}


@api_router.post("/api/diagrams/ai-plan")
def api_ai_plan(
    req: DiagramAiRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.routers.admin import _enabled_ai_providers
    from app.core.secrets import decrypt_text
    from app.database.models import UserAIConfig

    cfg = db.query(UserAIConfig).filter(
        UserAIConfig.user_id == current_user.id,
        UserAIConfig.is_enabled == True,
    ).order_by(UserAIConfig.updated_at.desc()).first()
    if not cfg:
        raise HTTPException(status_code=400, detail="请先在 AI 设置中配置并启用一个模型厂商")

    try:
        plan = generate_diagram_plan(AIRequest(
            provider=cfg.provider,
            model=cfg.model,
            prompt=req.prompt,
            base_url=cfg.base_url,
            api_key=decrypt_text(cfg.api_key_enc) if cfg.api_key_enc else "",
            auth_type=cfg.auth_type,
        ))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "plan": plan}
