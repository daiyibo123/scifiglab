"""Admin router — initialization, feature toggles, user management, announcements."""

import os
import json
import re
import signal
import subprocess
import threading
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings, BASE_DIR
from app.core.email import send_email
from app.core.secrets import encrypt_text, decrypt_text
from app.core.security import get_current_user, get_current_user_optional, hash_password
from app.core.templates import templates
from app.database.session import get_db
from app.database.models import User, SiteConfig, Announcement, UserAIConfig

ROLE_LABELS = {
    "user": "普通用户",
    "vip": "VIP",
    "svip": "SVIP",
    "admin": "管理员",
}

router = APIRouter(tags=["admin"])
api_router = APIRouter(tags=["admin-api"])

AI_PROVIDERS = [
    {
        "key": "openai",
        "name": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "models": [
            "gpt-4.1", "gpt-4o", "gpt-4o-mini", 
            "gpt-5", "gpt-5-mini", "gpt-5.2", "gpt-5.2-Codex", 
            "gpt-5.4", "gpt-5.4-fast", "gpt-5.5", "gpt-5.5-pro"
        ],
        "auth_type": "api_key",
        "supports_oauth": True,
    },
    {
        "key": "gemini",
        "name": "Gemini",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": [
            "gemini-2.5-pro", "gemini-2.5-flash", 
            "gemini-3.0-pro", "gemini-3.0-flash", "gemini-3.1-pro-preview"
        ],
        "auth_type": "api_key",
        "supports_oauth": True,
    },
    {
        "key": "anthropic",
        "name": "Claude",
        "default_base_url": "https://api.anthropic.com/v1",
        "models": [
            "claude-3-7-sonnet-latest", "claude-3-5-sonnet-latest", 
            "claude-3-5-haiku-latest", "claude-3-opus-latest", 
            "claude-4-sonnet", "claude-4-opus"
        ],
        "auth_type": "api_key",
        "supports_oauth": True,
    },
    {
        "key": "qwen",
        "name": "通义千问",
        "default_base_url": "https://dashscope.aliyuncs.com/api/v1",
        "models": [
            "qwen-max", "qwen-plus", "qwen-turbo", "qwen-long", 
            "qwen-vl-max", "qwen-vl-plus", 
            "qwen2.5-72B-instruct", "qwen2.5-32B-instruct", 
            "qwen3-235B-A22B", "qwen3-max", "qwen3.5-397B-A17B", 
            "qwen-deep-research", "qwen-math-plus", "qwen-omni-turbo"
        ],
        "auth_type": "api_key",
        "supports_oauth": False,
    },
    {
        "key": "zhipu",
        "name": "智谱 GLM",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": [
            "glm-4.5", "glm-4-plus", "glm-4-flash", 
            "glm-5", "glm-5-plus", "glm-5-flash"
        ],
        "auth_type": "api_key",
        "supports_oauth": True,
    },
    {
        "key": "deepseek",
        "name": "DeepSeek",
        "default_base_url": "https://api.deepseek.com",
        "models": [
            "deepseek-chat", "deepseek-reasoner", 
            "deepseek-v3", "deepseek-v3.1", "deepseek-v3.2", 
            "deepseek-v4-pro", "deepseek-v4-flash"
        ],
        "auth_type": "api_key",
        "supports_oauth": False,
    },
    {
        "key": "nvidia",
        "name": "NVIDIA",
        "default_base_url": "https://api.nvidia.com/v1",
        "models": [
            "nvidia/llama-3.1-nemotron-70b-instruct", 
            "meta/llama-3.1-405b-instruct", 
            "meta/llama-3.1-70b-instruct", 
            "mistralai/mixtral-8x7b-instruct-v0.1", 
            "nvidia/nemotron-5-340b", "nvidia/llama-4-500b", 
            "nvidia/mistral-large-2-instruct", "nvidia/codellama-70b", 
            "nvidia/llama-3.3-nemotron-super-49b-v1", 
            "nvidia/llama-3.1-nemotron-ultra-253B-v1", 
            "nvidia/deepseek-v4-pro", "gemma-4-31b-it"
        ],
        "auth_type": "api_key",
        "supports_oauth": False,
    },
    {
        "key": "xiaomi",
        "name": "Xiaomi",
        "default_base_url": "https://api.xiaomi-ai.com/v1",
        "models": [
            "MiMo-2.5-7B", "MiMo-2.5-VL-7B", "xiaomi-mimo-2.5", 
            "MiMo-2.5-10B", "MiMo-2.5-VL-10B", "MiMo-V2.5-Pro"
        ],
        "auth_type": "api_key",
        "supports_oauth": False,
    },
    {
        "key": "ollama",
        "name": "Ollama",
        "default_base_url": "http://localhost:11434/api",
        "models": [
            "llama3.1", "llama3.2", "qwen2.5", "deepseek-r1", 
            "mistral", "gemma2", "llama4", "qwen3"
        ],
        "auth_type": "none",
        "supports_oauth": False,
    },
    {
        "key": "gemma",
        "name": "Gemma",
        "default_base_url": "https://api.gemma.com/v1",
        "models": [
            "gemma-2-27b-it", "gemma-3-12b-it", "gemma-4-31b-it", 
            "gemma-3n-e2b-it", "gemma-3n-e4b-it"
        ],
        "auth_type": "api_key",
        "supports_oauth": False,
    },
]

AI_PROVIDER_FLAG_KEYS = [
    "ai_provider_openai_enabled",
    "ai_provider_gemini_enabled",
    "ai_provider_anthropic_enabled",
    "ai_provider_qwen_enabled",
    "ai_provider_zhipu_enabled",
    "ai_provider_deepseek_enabled",
    "ai_provider_nvidia_enabled",
    "ai_provider_xiaomi_enabled",
    "ai_provider_ollama_enabled",
    "ai_provider_gemma_enabled",
]

OAUTH_URLS = {
    "openai": "https://api.openai.com/oauth/authorize",
    "gemini": "https://accounts.google.com/o/oauth2/v2/auth",
    "anthropic": "https://api.anthropic.com/oauth/authorize",
    "zhipu": "https://open.bigmodel.cn/oauth2/authorize",
}

OAUTH_SCOPES = {
    "openai": "offline_access model:read model:write",
    "gemini": "https://www.googleapis.com/auth/generative-language",
    "anthropic": "offline model:read model:write",
    "zhipu": "all",
}

# ── Helper: check if admin exists ────────────────────────────────────────

def _admin_exists(db: Session) -> bool:
    return db.query(User).filter(User.is_admin == True).first() is not None


def _require_admin(current_user: User):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")


def _normalize_role(role: str) -> str:
    role = (role or "").strip().lower()
    return role if role in ROLE_LABELS else "user"


def _role_label(role: str) -> str:
    return ROLE_LABELS.get(role, ROLE_LABELS["user"])


def _get_config(db: Session, key: str, default: str = "") -> str:
    row = db.query(SiteConfig).filter(SiteConfig.key == key).first()
    return row.value if row else default


def _set_config(db: Session, key: str, value: str, description: str = ""):
    row = db.query(SiteConfig).filter(SiteConfig.key == key).first()
    if row:
        row.value = value
    else:
        row = SiteConfig(key=key, value=value, description=description)
        db.add(row)
    db.commit()


def _ai_config_to_dict(cfg: UserAIConfig) -> dict:
    secret = decrypt_text(cfg.api_key_enc) if cfg.api_key_enc else ""
    return {
        "id": cfg.id,
        "provider": cfg.provider,
        "auth_type": cfg.auth_type,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "is_enabled": cfg.is_enabled,
        "api_key": secret if cfg.auth_type == "api_key" else "",
        "oauth_token": secret if cfg.auth_type == "oauth" else "",
        "has_api_key": bool(cfg.api_key_enc),
        "has_oauth_token": cfg.auth_type == "oauth" and bool(cfg.api_key_enc),
    }


def _extract_ai_credential(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if value.startswith("{"):
        try:
            data = json.loads(value)
            for key in ("access_token", "api_key", "key", "token", "refresh_token", "id_token"):
                token = data.get(key)
                if isinstance(token, str) and token.strip():
                    return token.strip()
        except Exception:
            pass
    match = re.search(r"(?:access_token|api_key|key|token|code)=([^&\s]+)", value)
    if match:
        return match.group(1).strip()
    return value


def _user_to_dict(user: User) -> dict:
    role_val = "user"
    try:
        role_val = getattr(user, "role", "user") or "user"
    except Exception:
        pass
    verified = False
    try:
        verified = getattr(user, "is_email_verified", False) or False
    except Exception:
        pass
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "role": role_val,
        "role_label": _role_label(role_val),
        "is_email_verified": verified,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


# ── Default feature flags ────────────────────────────────────────────────

DEFAULT_FLAGS = {
    "allow_registration": ("true", "允许新用户注册"),
    "allow_file_upload": ("true", "允许文件上传"),
    "allow_compare": ("true", "启用多实验对比"),
    "allow_groups": ("true", "启用实验组"),
    "allow_paper_table": ("true", "启用论文表格生成"),
    "max_upload_mb": ("20", "单文件上传大小限制(MB)"),
    "site_announcement": ("", "全站公告（留空不显示）"),
    "alert_cpu_warning": ("80", "CPU 警告阈值(%)"),
    "alert_cpu_critical": ("95", "CPU 严重阈值(%)"),
    "alert_mem_warning": ("80", "内存警告阈值(%)"),
    "alert_mem_critical": ("95", "内存严重阈值(%)"),
    "alert_disk_warning": ("80", "磁盘警告阈值(%)"),
    "alert_disk_critical": ("95", "磁盘严重阈值(%)"),
    "alert_email_enabled": ("false", "启用预警邮件通知"),
    "ai_provider_openai_enabled": ("true", "启用 OpenAI 厂商"),
    "ai_provider_gemini_enabled": ("true", "启用 Gemini 厂商"),
    "ai_provider_anthropic_enabled": ("true", "启用 Anthropic 厂商"),
    "ai_provider_qwen_enabled": ("true", "启用通义千问厂商"),
    "ai_provider_zhipu_enabled": ("true", "启用智谱厂商"),
    "ai_provider_deepseek_enabled": ("true", "启用 DeepSeek 厂商"),
    "ai_provider_nvidia_enabled": ("true", "启用 NVIDIA 厂商"),
    "ai_provider_xiaomi_enabled": ("true", "启用 Xiaomi 厂商"),
    "ai_provider_ollama_enabled": ("false", "启用 Ollama 厂商"),
    "ai_provider_gemma_enabled": ("false", "启用 Gemma 厂商"),
}


def init_default_flags(db: Session):
    for key, (default, desc) in DEFAULT_FLAGS.items():
        existing = db.query(SiteConfig).filter(SiteConfig.key == key).first()
        if not existing:
            db.add(SiteConfig(key=key, value=default, description=desc))
    db.commit()


def _provider_enabled(db: Session, provider_key: str) -> bool:
    key = f"ai_provider_{provider_key}_enabled"
    return _get_config(db, key, "true").lower() == "true"


def _enabled_ai_providers(db: Session) -> list[dict]:
    providers = []
    for item in AI_PROVIDERS:
        enabled = _provider_enabled(db, item["key"])
        providers.append({
            **item,
            "enabled": enabled,
        })
    return providers


# ── Page: Admin init (first-time only) ───────────────────────────────────

@router.get("/admin/init")
def admin_init_page(
    request: Request,
    db: Session = Depends(get_db),
):
    if _admin_exists(db):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("admin_init.html", {
        "request": request,
        "title": "初始化管理员",
    })


class AdminInitRequest(BaseModel):
    username: str
    email: str
    password: str


@api_router.post("/api/admin/init")
def api_admin_init(
    req: AdminInitRequest,
    db: Session = Depends(get_db),
):
    if _admin_exists(db):
        raise HTTPException(status_code=400, detail="管理员已存在，无法重复初始化")

    if len(req.username) < 2 or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="用户名至少2位，密码至少6位")

    # Check unique
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="邮箱已被使用")
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="用户名已被使用")

    admin = User(
        email=req.email,
        username=req.username,
        password_hash=hash_password(req.password),
        is_active=True,
        is_admin=True,
        role="admin",
        is_email_verified=True,
    )
    db.add(admin)
    db.commit()

    # Init default flags
    init_default_flags(db)

    return {"ok": True, "msg": "管理员创建成功，请登录"}


class AIConfigUpsertRequest(BaseModel):
    provider: str
    auth_type: str = "api_key"
    model: str = ""
    api_key: str = ""
    oauth_token: str = ""
    base_url: str = ""
    request_model: Optional[str] = None
    is_enabled: bool = True


@router.get("/settings/ai")
def ai_settings_page(
    request: Request,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("ai_settings.html", {
        "request": request,
        "title": "AI 设置",
        "current_user": current_user,
    })


@api_router.get("/api/ai/oauth/{provider}")
def api_ai_oauth_start(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    provider = provider.strip().lower()
    provider_meta = next((p for p in AI_PROVIDERS if p["key"] == provider), None)
    if not provider_meta or "oauth" not in provider_meta.get("auth_types", []):
        raise HTTPException(status_code=404, detail="该厂商不支持 OAuth")

    client_id = os.environ.get(f"{provider.upper()}_OAUTH_CLIENT_ID", "").strip()
    redirect_uri = os.environ.get(f"{provider.upper()}_OAUTH_REDIRECT_URI", "").strip()
    if not client_id or not redirect_uri:
        provider_name = provider_meta["name"]
        fallback_url = provider_meta.get("auth_url") or "#"
        return HTMLResponse(
            f"""
            <html><head><meta charset="utf-8"><title>{provider_name} OAuth</title></head>
            <body style="font-family:system-ui;padding:32px;line-height:1.7">
                <h2>{provider_name} 账号授权</h2>
                <p>当前没有配置专用 OAuth Client，因此先使用手动授权/账号凭据导入模式：</p>
                <ol>
                    <li>打开 <a href="{fallback_url}" target="_blank" rel="noopener">{provider_name} 授权/密钥页面</a> 登录账号。</li>
                    <li>复制页面返回的 token / code / JSON 凭据。</li>
                    <li>回到 SciFigLab 的 AI 设置，在 OAuth 模式下粘贴到「授权结果」输入框并保存。</li>
                </ol>
                <p>如果后续凭据失效，调用时会提示账号凭据错误，重新授权即可。</p>
                <hr>
                <p>如果你要改成自动跳转回调模式，需要配置：</p>
                <pre>{provider.upper()}_OAUTH_CLIENT_ID=你的客户端ID
{provider.upper()}_OAUTH_REDIRECT_URI=你的回调地址</pre>
            </body></html>
            """
        )

    from urllib.parse import urlencode
    query = urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": OAUTH_SCOPES[provider],
        "state": f"user:{current_user.id}:provider:{provider}",
        "access_type": "offline",
        "prompt": "consent",
    })
    return RedirectResponse(url=f"{OAUTH_URLS[provider]}?{query}", status_code=302)


@api_router.get("/api/admin/ai-config")
def api_get_user_ai_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(UserAIConfig).filter(UserAIConfig.user_id == current_user.id).order_by(UserAIConfig.updated_at.desc()).all()
    return {
        "providers": _enabled_ai_providers(db),
        "configs": [_ai_config_to_dict(row) for row in rows],
    }


@api_router.put("/api/admin/ai-config")
def api_save_user_ai_config(
    req: AIConfigUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    provider = req.provider.strip().lower()
    provider_meta = next((p for p in AI_PROVIDERS if p["key"] == provider), None)
    if provider != "custom":
        if not provider_meta:
            raise HTTPException(status_code=400, detail="不支持的模型厂商")
        if not _provider_enabled(db, provider):
            raise HTTPException(status_code=400, detail="该模型厂商已被管理员关闭")
    auth_type = req.auth_type
    model = req.model.strip()
    if provider != "custom" and provider_meta:
        if auth_type not in provider_meta["auth_types"]:
            auth_type = provider_meta["auth_types"][0]
        model = model or provider_meta.get("default_model", "")
    if not model:
        raise HTTPException(status_code=400, detail="请填写模型名称")
    cfg = db.query(UserAIConfig).filter(
        UserAIConfig.user_id == current_user.id,
        UserAIConfig.provider == provider,
    ).first()
    if not cfg:
        cfg = UserAIConfig(user_id=current_user.id, provider=provider)
        db.add(cfg)
    if auth_type == "oauth":
        credential = _extract_ai_credential(req.oauth_token or req.api_key)
    else:
        credential = _extract_ai_credential(req.api_key)
    cfg.auth_type = auth_type
    cfg.model = model
    cfg.api_key_enc = encrypt_text(credential) if credential else ""
    cfg.base_url = req.base_url.strip() or (provider_meta["default_base_url"] if provider_meta else "")
    cfg.is_enabled = bool(req.is_enabled)
    db.commit()
    db.refresh(cfg)
    return {"ok": True, "config": _ai_config_to_dict(cfg)}


@api_router.delete("/api/admin/ai-config/{config_id}")
def api_delete_user_ai_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cfg = db.query(UserAIConfig).filter(
        UserAIConfig.id == config_id,
        UserAIConfig.user_id == current_user.id,
    ).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="配置不存在")
    db.delete(cfg)
    db.commit()
    return {"ok": True}


# ── Page: Admin panel ────────────────────────────────────────────────────

@router.get("/admin")
def admin_panel_page(
    request: Request,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    if not current_user.is_admin:
        return RedirectResponse(url="/dashboard", status_code=302)

    # Load feature flags
    flags = {}
    for key, (default, desc) in DEFAULT_FLAGS.items():
        val = _get_config(db, key, default)
        flags[key] = {"value": val, "description": desc}

    # User stats
    user_count = db.query(func.count(User.id)).scalar()
    users = db.query(User).order_by(User.created_at.desc()).limit(50).all()

    role = "user"
    if hasattr(current_user, "role") and current_user.role:
        role = current_user.role

    return templates.TemplateResponse("admin_panel.html", {
        "request": request,
        "title": "管理后台",
        "current_user": current_user,
        "flags": flags,
        "user_count": user_count,
        "users": [_user_to_dict(u) for u in users],
        "role_labels": ROLE_LABELS,
        "role": role,
    })


# ── API: Update feature flags ────────────────────────────────────────────

class FlagUpdateRequest(BaseModel):
    key: str
    value: str


@api_router.post("/api/admin/flags")
def api_update_flag(
    req: FlagUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    if req.key not in DEFAULT_FLAGS:
        raise HTTPException(status_code=400, detail=f"未知配置项: {req.key}")
    _set_config(db, req.key, req.value)
    return {"ok": True, "msg": f"已更新 {req.key}"}


@api_router.get("/api/admin/flags")
def api_get_flags(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    flags = {}
    for key, (default, desc) in DEFAULT_FLAGS.items():
        val = _get_config(db, key, default)
        flags[key] = {"value": val, "description": desc}
    return {"flags": flags}


# ── API: Toggle user active ──────────────────────────────────────────────

@api_router.post("/api/admin/users/{user_id}/toggle-active")
def api_toggle_user_active(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")
    user.is_active = not user.is_active
    db.commit()
    return {"ok": True, "is_active": user.is_active, "user": _user_to_dict(user)}


class UserRoleUpdateRequest(BaseModel):
    role: str


class AdminUserCreateRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"


@api_router.post("/api/admin/users")
def api_create_user(
    req: AdminUserCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    username = req.username.strip()
    email = req.email.strip().lower()
    role = _normalize_role(req.role)
    if len(username) < 2:
        raise HTTPException(status_code=400, detail="用户名至少 2 位")
    if "@" not in email:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="邮箱已存在")
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(req.password),
        is_active=True,
        is_admin=role == "admin",
        role=role,
        is_email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": _user_to_dict(user)}


@api_router.post("/api/admin/users/{user_id}/role")
def api_update_user_role(
    user_id: int,
    req: UserRoleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    role = _normalize_role(req.role)
    user.role = role
    user.is_admin = role == "admin"
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": _user_to_dict(user)}


@router.get("/admin/users")
def admin_users_page(
    request: Request,
    current_user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=302)
    if not current_user.is_admin:
        return RedirectResponse(url="/dashboard", status_code=302)
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "title": "用户管理",
        "current_user": current_user,
        "users": [_user_to_dict(u) for u in users],
        "role_labels": ROLE_LABELS,
    })


# ── API: Git pull ───────────────────────────────────────────────────────

PROTECTED_GIT_PATHS = ["data", ".env", "*.db", "*.sqlite3"]


def _run_git(args: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _normalize_repo_url(url: str) -> str:
    normalized = url.strip().lower().removesuffix(".git")
    if normalized.startswith("git@github.com:"):
        normalized = normalized.replace("git@github.com:", "https://github.com/", 1)
    return normalized.rstrip("/")


def _is_docker() -> bool:
    return os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER") == "1"


def _schedule_restart() -> bool:
    if not _is_docker():
        return False

    def _restart_process():
        target_pid = os.getppid() if os.getppid() > 1 else os.getpid()
        os.kill(target_pid, signal.SIGTERM)

    threading.Timer(1.5, _restart_process).start()
    return True

@api_router.post("/api/admin/git-pull")
def api_git_pull(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    try:
        repo_check = _run_git(["rev-parse", "--is-inside-work-tree"])
        if repo_check.returncode != 0 or repo_check.stdout.strip() != "true":
            return {"ok": False, "msg": "当前部署目录不是 Git 仓库，请使用 git clone 部署项目后再使用在线更新。"}

        remote = _run_git(["remote", "get-url", "origin"])
        if remote.returncode != 0:
            return {"ok": False, "msg": "未找到 Git remote origin，请先配置 GitHub 仓库地址。"}

        expected_repo = _normalize_repo_url(settings.GITHUB_REPO_URL)
        actual_repo = _normalize_repo_url(remote.stdout)
        if expected_repo and actual_repo != expected_repo:
            return {
                "ok": False,
                "msg": f"当前 origin 不是配置的 GitHub 仓库。\n当前: {remote.stdout.strip()}\n期望: {settings.GITHUB_REPO_URL}",
            }

        tracked = _run_git(["ls-files", "--", *PROTECTED_GIT_PATHS])
        protected_files = [line for line in tracked.stdout.splitlines() if line.strip()]
        if protected_files:
            return {
                "ok": False,
                "msg": "检测到数据库、上传目录或本地配置被 Git 跟踪，已拒绝更新以保护用户数据。请先从仓库中移除这些文件：\n" + "\n".join(protected_files),
            }

        result = _run_git(["pull", "--ff-only"], timeout=60)
        output = (result.stdout + "\n" + result.stderr).strip()
        if result.returncode == 0:
            restart_scheduled = _schedule_restart()
            return {
                "ok": True,
                "output": output or "Already up to date.",
                "restart_scheduled": restart_scheduled,
            }
        return {"ok": False, "msg": output}
    except FileNotFoundError:
        return {"ok": False, "msg": "git 未安装或不在 PATH 中"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "msg": "git pull 超时"}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


# ── API: Announcement CRUD ──────────────────────────────────────────────

class AnnouncementCreate(BaseModel):
    title: str
    content: str = ""
    display_type: str = "silent"   # silent / popup
    status: str = "draft"          # draft / published / ended
    start_at: Optional[str] = None  # ISO datetime string or empty
    end_at: Optional[str] = None


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    display_type: Optional[str] = None
    status: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None


def _parse_dt(val: Optional[str]):
    """Parse ISO datetime string, return None for empty/None."""
    if not val:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(val)
    except ValueError:
        return None


def _ann_to_dict(a: Announcement) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "content": a.content,
        "display_type": a.display_type,
        "status": a.status,
        "start_at": a.start_at.isoformat() if a.start_at else None,
        "end_at": a.end_at.isoformat() if a.end_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@api_router.get("/api/admin/announcements")
def api_list_announcements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    rows = db.query(Announcement).order_by(Announcement.created_at.desc()).all()
    return [_ann_to_dict(a) for a in rows]


@api_router.post("/api/admin/announcements")
def api_create_announcement(
    req: AnnouncementCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")
    ann = Announcement(
        title=req.title.strip(),
        content=req.content,
        display_type=req.display_type if req.display_type in ("silent", "popup") else "silent",
        status=req.status if req.status in ("draft", "published", "ended") else "draft",
        start_at=_parse_dt(req.start_at),
        end_at=_parse_dt(req.end_at),
        created_by=current_user.id,
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    return {"ok": True, "announcement": _ann_to_dict(ann)}


@api_router.put("/api/admin/announcements/{ann_id}")
def api_update_announcement(
    ann_id: int,
    req: AnnouncementUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    ann = db.query(Announcement).filter(Announcement.id == ann_id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="公告不存在")
    if req.title is not None:
        ann.title = req.title.strip()
    if req.content is not None:
        ann.content = req.content
    if req.display_type is not None and req.display_type in ("silent", "popup"):
        ann.display_type = req.display_type
    if req.status is not None and req.status in ("draft", "published", "ended"):
        ann.status = req.status
    if req.start_at is not None:
        ann.start_at = _parse_dt(req.start_at)
    if req.end_at is not None:
        ann.end_at = _parse_dt(req.end_at)
    db.commit()
    return {"ok": True, "announcement": _ann_to_dict(ann)}


@api_router.delete("/api/admin/announcements/{ann_id}")
def api_delete_announcement(
    ann_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    ann = db.query(Announcement).filter(Announcement.id == ann_id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="公告不存在")
    db.delete(ann)
    db.commit()
    return {"ok": True}


# ── Public API: active announcements (for all users) ────────────────────

@api_router.get("/api/announcements/active")
def api_active_announcements(
    db: Session = Depends(get_db),
):
    """Return published announcements that are currently in their time window."""
    import datetime as _dt
    now = _dt.datetime.utcnow()
    rows = (
        db.query(Announcement)
        .filter(Announcement.status == "published")
        .order_by(Announcement.created_at.desc())
        .all()
    )
    result = []
    for a in rows:
        if a.start_at and a.start_at > now:
            continue
        if a.end_at and a.end_at < now:
            continue
        result.append(_ann_to_dict(a))
    return result


# ── API: Server monitoring ──────────────────────────────────────────────

@api_router.get("/api/admin/server-status")
def api_server_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    from app.services.monitor_service import get_server_status, check_alerts

    status = get_server_status()

    # Load thresholds from DB
    thresholds = {}
    for key in ("cpu_warning", "cpu_critical", "mem_warning", "mem_critical",
                "disk_warning", "disk_critical"):
        val = _get_config(db, f"alert_{key}", DEFAULT_FLAGS.get(f"alert_{key}", ("80",))[0])
        try:
            thresholds[key] = float(val)
        except ValueError:
            thresholds[key] = 80.0

    alerts = check_alerts(status, thresholds)

    return {"status": status, "alerts": alerts, "thresholds": thresholds}


@api_router.post("/api/admin/send-alert-email")
def api_send_alert_email(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually trigger alert email to admin with current server status."""
    _require_admin(current_user)

    email_enabled = _get_config(db, "alert_email_enabled", "false")
    if email_enabled != "true":
        return {"ok": False, "msg": "预警邮件未启用，请在功能开关中启用 alert_email_enabled"}

    from app.services.monitor_service import get_server_status, check_alerts

    status = get_server_status()
    thresholds = {}
    for key in ("cpu_warning", "cpu_critical", "mem_warning", "mem_critical",
                "disk_warning", "disk_critical"):
        val = _get_config(db, f"alert_{key}", DEFAULT_FLAGS.get(f"alert_{key}", ("80",))[0])
        try:
            thresholds[key] = float(val)
        except ValueError:
            thresholds[key] = 80.0

    alerts = check_alerts(status, thresholds)
    if not alerts:
        return {"ok": True, "msg": "当前无预警，服务器状态正常"}

    # Build email body
    lines = ["SciFigLab 服务器预警报告", "=" * 40, ""]
    for a in alerts:
        level_label = {"warning": "⚠️ 警告", "critical": "🔴 严重"}.get(a["level"], a["level"])
        lines.append(f"[{level_label}] {a['message']}")
    lines.append("")
    lines.append(f"CPU: {status['cpu_percent']}% ({status['cpu_count']} 核)")
    lines.append(f"内存: {status['memory_used_gb']}/{status['memory_total_gb']} GB ({status['memory_percent']}%)")
    lines.append(f"磁盘: {status['disk_used_gb']}/{status['disk_total_gb']} GB ({status['disk_percent']}%)")
    lines.append(f"数据目录: {status['data_dir_size_mb']} MB")
    body = "\n".join(lines)

    subject = f"[SciFigLab 预警] {'严重' if any(a['level']=='critical' for a in alerts) else '警告'}"
    try:
        ok = send_email(current_user.email, subject, body.replace("\n", "<br>"))
        if not ok:
            return {"ok": False, "msg": "邮件发送失败，请检查 SMTP/Resend 配置。"}
        return {"ok": True, "msg": f"预警邮件已发送到 {current_user.email}"}
    except Exception as e:
        return {"ok": False, "msg": f"邮件发送失败: {e}"}
