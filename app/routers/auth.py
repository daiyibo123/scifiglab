from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, TOKEN_COOKIE_KEY
from app.core.templates import templates
from app.database.session import get_db
from app.services.auth_service import (
    create_user,
    authenticate_user,
    get_user_by_email,
    get_user_by_username,
)
from app.services.email_service import send_verification_code, verify_code

# ---------------------------------------------------------------------------
# Page router — no prefix, serves /login and /register
# ---------------------------------------------------------------------------
router = APIRouter(tags=["auth-pages"])


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "title": "登录"})


@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "title": "注册"})


# ---------------------------------------------------------------------------
# API router — prefix /api/auth
# ---------------------------------------------------------------------------
api_router = APIRouter(prefix="/api/auth", tags=["auth-api"])


class SendCodeRequest(BaseModel):
    email: str
    purpose: str = "register"


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    code: str


class LoginRequest(BaseModel):
    email: str
    password: str


@api_router.post("/send-code")
def api_send_code(req: SendCodeRequest, db: Session = Depends(get_db)):
    if req.purpose == "register":
        if get_user_by_email(db, req.email):
            return JSONResponse({"ok": False, "msg": "该邮箱已注册"}, status_code=400)

    ok, msg = send_verification_code(db, req.email, req.purpose)
    if not ok:
        return JSONResponse({"ok": False, "msg": msg}, status_code=400)
    return {"ok": True, "msg": msg}


@api_router.post("/register")
def api_register(req: RegisterRequest, db: Session = Depends(get_db)):
    if not req.username or len(req.username) < 2:
        return JSONResponse({"ok": False, "msg": "用户名至少 2 个字符"}, status_code=400)
    if not req.password or len(req.password) < 6:
        return JSONResponse({"ok": False, "msg": "密码至少 6 个字符"}, status_code=400)

    if get_user_by_email(db, req.email):
        return JSONResponse({"ok": False, "msg": "该邮箱已注册"}, status_code=400)
    if get_user_by_username(db, req.username):
        return JSONResponse({"ok": False, "msg": "该用户名已被占用"}, status_code=400)

    ok, msg = verify_code(db, req.email, req.code, "register")
    if not ok:
        return JSONResponse({"ok": False, "msg": msg}, status_code=400)

    create_user(db, req.username, req.email, req.password, is_email_verified=True)
    return {"ok": True, "msg": "注册成功，请登录"}


@api_router.post("/login")
def api_login(req: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, req.email, req.password)
    if not user:
        return JSONResponse({"ok": False, "msg": "邮箱或密码错误"}, status_code=400)
    if not user.is_email_verified:
        return JSONResponse({"ok": False, "msg": "邮箱未验证，请先完成注册验证"}, status_code=400)
    if not user.is_active:
        return JSONResponse({"ok": False, "msg": "账号已被禁用"}, status_code=400)

    token = create_access_token(user_id=user.id, email=user.email)
    response = JSONResponse({"ok": True, "msg": "登录成功"})
    response.set_cookie(
        key=TOKEN_COOKIE_KEY,
        value=token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return response


@api_router.post("/logout")
def api_logout():
    response = JSONResponse({"ok": True, "msg": "已退出登录"})
    response.delete_cookie(TOKEN_COOKIE_KEY)
    return response
