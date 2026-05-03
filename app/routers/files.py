import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.core.config import settings, DATA_DIR
from app.core.security import get_current_user
from app.database.session import get_db
from app.database.models import Experiment, Project, UploadedFile, User

# ---------------------------------------------------------------------------
# Extension → (file_type, subdirectory)
# ---------------------------------------------------------------------------
EXT_MAP = {
    ".log": ("log", "logs"),
    ".txt": ("log", "logs"),
    ".yaml": ("config", "configs"),
    ".yml": ("config", "configs"),
    ".json": ("config", "configs"),
    ".csv": ("metrics", "metrics"),
    ".xlsx": ("table", "tables"),
    ".png": ("image", "images"),
    ".jpg": ("image", "images"),
    ".jpeg": ("image", "images"),
    ".pdf": ("other", "other"),
    ".md": ("other", "other"),
}

ALLOWED_EXTS = set(EXT_MAP.keys())

FILE_TYPE_LABELS = {
    "log": "日志",
    "config": "配置",
    "metrics": "指标",
    "image": "图片",
    "table": "表格",
    "other": "其他",
}


def _get_experiment_owned(db: Session, experiment_id: int, user_id: int) -> Experiment:
    exp = (
        db.query(Experiment)
        .filter(Experiment.id == experiment_id, Experiment.user_id == user_id)
        .first()
    )
    if not exp:
        raise HTTPException(status_code=404, detail="实验不存在")
    return exp


def _file_to_dict(f: UploadedFile) -> dict:
    return {
        "id": f.id,
        "experiment_id": f.experiment_id,
        "original_name": f.original_name,
        "file_type": f.file_type,
        "file_type_label": FILE_TYPE_LABELS.get(f.file_type, f.file_type),
        "file_ext": f.file_ext,
        "file_size": f.file_size,
        "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
    }


def _validate_file_content(content: bytes, ext: str, file_type: str):
    """Validate that parseable files can actually be decoded/parsed.

    Returns an error message string if invalid, None if OK.
    """
    # Only validate text-based parseable types
    if file_type in ("image", "table", "other"):
        return None

    # Must be decodable as text
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("gbk")
        except Exception:
            return "文件无法解码为文本（需 UTF-8 或 GBK 编码）"

    if not text.strip():
        return "文件内容为空"

    # CSV: must have at least a header row
    if ext == ".csv":
        import csv
        import io
        try:
            reader = csv.reader(io.StringIO(text))
            header = next(reader, None)
            if not header or len(header) < 2:
                return "CSV 文件至少需要两列（如 step, metric）"
        except csv.Error as e:
            return f"CSV 格式错误: {e}"

    # Config: validate yaml/json
    if ext in (".yaml", ".yml"):
        import yaml
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as e:
            return f"YAML 解析失败: {e}"
    elif ext == ".json":
        import json
        try:
            json.loads(text)
        except json.JSONDecodeError as e:
            return f"JSON 解析失败: {e}"

    return None


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


# ---------------------------------------------------------------------------
# Placeholder page router (page is in experiments router)
# ---------------------------------------------------------------------------
router = APIRouter(tags=["files"])

# ---------------------------------------------------------------------------
# API router
# ---------------------------------------------------------------------------
api_router = APIRouter(tags=["files-api"])


@api_router.post("/api/experiments/{experiment_id}/upload")
async def api_upload_file(
    experiment_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exp = _get_experiment_owned(db, experiment_id, current_user.id)

    # Validate extension
    original_name = file.filename or "unknown"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        return JSONResponse(
            {"ok": False, "msg": f"不支持的文件类型: {ext}，允许: {', '.join(sorted(ALLOWED_EXTS))}"},
            status_code=400,
        )

    # Read content and check size
    max_bytes = settings.UPLOAD_MAX_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        return JSONResponse(
            {"ok": False, "msg": f"文件大小超过限制 ({settings.UPLOAD_MAX_SIZE_MB}MB)"},
            status_code=400,
        )

    file_type, subdir = EXT_MAP[ext]

    # Build safe path: data/user_{uid}/project_{pid}/experiment_{eid}/{subdir}/
    rel_dir = (
        Path(f"user_{current_user.id}")
        / f"project_{exp.project_id}"
        / f"experiment_{experiment_id}"
        / subdir
    )
    abs_dir = DATA_DIR / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    # UUID filename
    unique_name = f"{uuid.uuid4().hex}{ext}"
    abs_path = abs_dir / unique_name

    # Prevent path traversal: resolved path must be inside DATA_DIR
    if not str(abs_path.resolve()).startswith(str(DATA_DIR.resolve())):
        return JSONResponse({"ok": False, "msg": "非法文件路径"}, status_code=400)

    # Validate parseable file content before saving
    validation_error = _validate_file_content(content, ext, file_type)
    if validation_error:
        return JSONResponse(
            {"ok": False, "msg": f"文件解析失败: {validation_error}"},
            status_code=400,
        )

    # Encrypt and write
    from app.services.encryption import encrypt_bytes
    encrypted = encrypt_bytes(content, settings.SECRET_KEY)
    with open(abs_path, "wb") as fp:
        fp.write(encrypted)

    # DB record
    record = UploadedFile(
        user_id=current_user.id,
        project_id=exp.project_id,
        experiment_id=experiment_id,
        file_name=unique_name,
        original_name=original_name,
        file_type=file_type,
        file_ext=ext,
        file_size=len(content),
        file_path=str(rel_dir / unique_name),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "ok": True,
        "msg": "文件上传成功",
        "file": _file_to_dict(record),
    }


@api_router.get("/api/experiments/{experiment_id}/files")
def api_list_files(
    experiment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_experiment_owned(db, experiment_id, current_user.id)
    rows = (
        db.query(UploadedFile)
        .filter(
            UploadedFile.experiment_id == experiment_id,
            UploadedFile.user_id == current_user.id,
        )
        .order_by(UploadedFile.uploaded_at.desc())
        .all()
    )
    return [_file_to_dict(f) for f in rows]


@api_router.delete("/api/files/{file_id}")
def api_delete_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = (
        db.query(UploadedFile)
        .filter(UploadedFile.id == file_id, UploadedFile.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="文件不存在")

    # Delete physical file
    abs_path = DATA_DIR / record.file_path
    if abs_path.exists():
        try:
            abs_path.unlink()
        except OSError:
            pass

    db.delete(record)
    db.commit()
    return {"ok": True, "msg": "文件已删除"}


@api_router.get("/api/files/{file_id}/download")
def api_download_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = (
        db.query(UploadedFile)
        .filter(UploadedFile.id == file_id, UploadedFile.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="文件不存在")

    abs_path = DATA_DIR / record.file_path
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在于磁盘")

    raw = abs_path.read_bytes()

    # Decrypt if encrypted
    from app.services.encryption import is_encrypted, decrypt_bytes
    if is_encrypted(raw):
        raw = decrypt_bytes(raw, settings.SECRET_KEY) or raw

    import mimetypes
    mime = mimetypes.guess_type(record.original_name)[0] or "application/octet-stream"
    return Response(
        content=raw,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{record.original_name}"'},
    )
