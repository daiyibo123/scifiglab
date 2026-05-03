"""File service — placeholder for handling file uploads."""

from pathlib import Path
from app.core.config import UPLOAD_DIR


def save_upload(filename: str, content: bytes, experiment_id: int) -> str:
    """Save uploaded bytes to disk and return the stored path."""
    dest_dir = UPLOAD_DIR / str(experiment_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_bytes(content)
    return str(dest)
